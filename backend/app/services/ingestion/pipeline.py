"""The indexing pipeline: sync -> walk -> parse -> embed.

Idempotent by construction. A file is re-parsed only when its content hash or the parser
version changed; files that disappeared are deleted; chunks whose embedding came from a
different model are re-embedded. Running it twice in a row does no work the second time.
"""

import asyncio
import hashlib
import logging
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import Chunk, Document, IndexRun, Source
from app.services.chunking.identifiers import identifier_terms, path_terms, symbol_terms
from app.services.chunking.types import PARSER_VERSION, ChunkDraft, ParsedDocument
from app.services.embedding.base import ModelUnavailable
from app.services.embedding.factory import get_embedder
from app.services.ingestion import git
from app.services.ingestion.walker import WalkedFile, walk
from app.services.parsing.dispatch import parse_document

log = logging.getLogger(__name__)

COMMIT_EVERY = 50  # files per transaction
PROGRESS_EVERY_S = 1.5
EMBED_TEXT_MAX_CHARS = 8000


class IndexingError(RuntimeError):
    pass


# ---------------------------------------------------------------- source roots


def allowed_roots() -> list[Path]:
    return [Path(settings.sources_root).resolve(), Path(settings.eval_corpus_dir).resolve()]


def resolve_local(uri: str) -> Path:
    """A local source must resolve inside an allowed root: the API is not a way to read
    arbitrary paths from the container's filesystem."""
    roots = allowed_roots()
    path = Path(uri)
    candidate = (path if path.is_absolute() else roots[0] / path).resolve()
    if not any(candidate.is_relative_to(root) for root in roots):
        raise ValueError(f"{uri!r} is outside {roots[0]} (the folder mounted from SOURCES_DIR)")
    if not candidate.is_dir():
        raise ValueError(f"{candidate} is not a directory")
    return candidate


def repo_dir(source_id: int) -> Path:
    return Path(settings.repos_dir) / f"source-{source_id}"


# ---------------------------------------------------------------- chunk rows


def build_header(source_name: str, path: str, title: str | None, draft: ChunkDraft) -> str:
    location = ""
    if draft.start_line is not None:
        location = f"lines {draft.start_line}-{draft.end_line}"
    elif "page_start" in draft.meta:
        location = draft.symbol or ""
    label = draft.symbol if draft.kind != "pdf_page" else (title or "")
    first = f"{source_name}/{path}"
    if label:
        first += f" :: {label}"
    if location:
        first += f" ({location})"
    return "\n".join([first, *draft.context])


def chunk_rows(
    source: Source, document_id: int, path: str, parsed: ParsedDocument
) -> list[dict[str, Any]]:
    rows = []
    for ordinal, draft in enumerate(parsed.chunks):
        header = build_header(source.name, path, parsed.title, draft)
        symbols = [s for s in draft.symbols if s]
        terms = [symbol_terms(symbols), path_terms(path)]
        if parsed.kind in ("markdown", "pdf") and parsed.title:
            terms.append(parsed.title)
        rows.append(
            {
                "document_id": document_id,
                "source_id": source.id,
                "ordinal": ordinal,
                "kind": draft.kind,
                "symbol": draft.symbol,
                "symbols": symbols,
                "symbol_text": " ".join(symbols).lower(),
                "header": header,
                "content": draft.content,
                "start_line": draft.start_line,
                "end_line": draft.end_line,
                "token_count": max(1, (len(header) + len(draft.content)) // 4),
                "content_hash": hashlib.sha256(
                    (header + "\n" + draft.content).encode()
                ).hexdigest(),
                "search_terms": " ".join(t for t in terms if t),
                "identifier_terms": identifier_terms(draft.content),
                "meta": draft.meta,
            }
        )
    return rows


def embedding_text(header: str, content: str) -> str:
    return (header + "\n\n" + content)[:EMBED_TEXT_MAX_CHARS]


# ---------------------------------------------------------------- the pipeline


class Pipeline:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], source_id: int, run_id: int):
        self.sessions = sessions
        self.source_id = source_id
        self.run_id = run_id
        self.stats: dict[str, Any] = {
            "files_total": 0,
            "files_done": 0,
            "indexed": 0,
            "unchanged": 0,
            "failed": 0,
            "needs_ocr": 0,
            "deleted": 0,
            "chunks_written": 0,
            "embedded": 0,
            "embed_pending": 0,
            "skipped": {},
            "warnings": [],
        }
        self._last_progress = 0.0

    async def _save_run(self, **fields: Any) -> None:
        async with self.sessions() as session:
            await session.execute(
                update(IndexRun)
                .where(IndexRun.id == self.run_id)
                .values(stats=dict(self.stats), **fields)
            )
            await session.commit()

    async def _progress(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or now - self._last_progress >= PROGRESS_EVERY_S:
            self._last_progress = now
            await self._save_run()

    async def run(self) -> dict[str, Any]:
        async with self.sessions() as session:
            source = await session.get(Source, self.source_id)
            if source is None:
                raise IndexingError(f"source {self.source_id} does not exist")
            source.status = "indexing"
            source.error = None
            await session.commit()
            session.expunge(source)
        self.source = source

        await self._save_run(status="running", stage="sync", started_at=datetime.now(UTC))
        try:
            root = await self._sync()
            await self._save_run(stage="walk")
            walked = await asyncio.to_thread(
                walk, root, settings.max_file_bytes, settings.max_pdf_bytes
            )
            self.stats["skipped"] = dict(walked.skipped)
            self.stats["files_total"] = len(walked.files)
            history = await asyncio.to_thread(self._git_history, root, walked.repo_roots)

            await self._save_run(stage="parse")
            await self._parse_all(root, walked.files, history)

            await self._save_run(stage="embed")
            await self._embed()

            await self._finish(root)
        except Exception as exc:
            log.exception("indexing source %s failed", self.source_id)
            async with self.sessions() as session:
                await session.execute(
                    update(Source)
                    .where(Source.id == self.source_id)
                    .values(status="failed", error=str(exc)[:2000])
                )
                await session.commit()
            await self._save_run(
                status="failed", stage=None, error=str(exc)[:2000], finished_at=datetime.now(UTC)
            )
            raise
        return self.stats

    async def _sync(self) -> Path:
        if self.source.kind == "git":
            dest = repo_dir(self.source.id)
            await asyncio.to_thread(git.clone_or_update, self.source.uri, dest)
            return dest
        return resolve_local(self.source.uri)

    @staticmethod
    def _git_history(root: Path, repo_roots: list[str]) -> dict[str, git.FileCommit]:
        """Per-file last commit for every repository found inside the source."""
        history: dict[str, git.FileCommit] = {}
        if "" not in repo_roots:
            # The source may itself sit inside a repository (a subfolder of a monorepo).
            top = git.toplevel(root)
            if top is not None:
                prefix = root.relative_to(top.resolve()).as_posix() if root != top.resolve() else ""
                for path, info in git.file_history(top).items():
                    if not prefix:
                        history[path] = info
                    elif path.startswith(prefix + "/"):
                        history[path[len(prefix) + 1 :]] = info
        for repo_rel in repo_roots:
            for path, info in git.file_history(root / repo_rel).items():
                history[f"{repo_rel}/{path}" if repo_rel else path] = info
        return history

    async def _parse_all(
        self, root: Path, files: list[WalkedFile], history: dict[str, git.FileCommit]
    ) -> None:
        async with self.sessions() as session:
            existing = {
                row.path: row
                for row in (
                    await session.execute(
                        select(
                            Document.id,
                            Document.path,
                            Document.content_hash,
                            Document.parser_version,
                        ).where(Document.source_id == self.source_id)
                    )
                ).all()
            }

            seen: set[str] = set()
            pending = 0
            for walked in files:
                seen.add(walked.rel_path)
                try:
                    data = await asyncio.to_thread(walked.abs_path.read_bytes)
                except OSError as exc:
                    self.stats["failed"] += 1
                    log.warning("cannot read %s: %s", walked.abs_path, exc)
                    continue
                if walked.route.kind != "pdf" and b"\x00" in data[:8192]:
                    self.stats["skipped"]["binary"] = self.stats["skipped"].get("binary", 0) + 1
                    self.stats["files_total"] -= 1
                    seen.discard(walked.rel_path)
                    continue

                content_hash = hashlib.sha256(data).hexdigest()
                previous = existing.get(walked.rel_path)
                if (
                    previous is not None
                    and previous.content_hash == content_hash
                    and previous.parser_version == PARSER_VERSION
                ):
                    self.stats["unchanged"] += 1
                    self.stats["files_done"] += 1
                    continue

                await self._index_file(session, walked, data, content_hash, previous, history)
                self.stats["files_done"] += 1
                pending += 1
                if pending >= COMMIT_EVERY:
                    await session.commit()
                    pending = 0
                await self._progress()

            gone = [row.id for path, row in existing.items() if path not in seen]
            if gone:
                await session.execute(delete(Document).where(Document.id.in_(gone)))
                self.stats["deleted"] = len(gone)
            await session.commit()
        await self._progress(force=True)

    async def _index_file(
        self,
        session: AsyncSession,
        walked: WalkedFile,
        data: bytes,
        content_hash: str,
        previous: Any,
        history: dict[str, git.FileCommit],
    ) -> None:
        try:
            parsed = await asyncio.to_thread(parse_document, walked.rel_path, data, walked.route)
        except Exception as exc:  # one bad file must not fail the whole source
            log.warning("parse failed for %s: %r", walked.rel_path, exc)
            parsed = ParsedDocument(
                kind=walked.route.kind,
                language=walked.route.language,
                title=None,
                chunks=[],
                status="error",
                error=repr(exc)[:1000],
            )

        commit = history.get(walked.rel_path)
        values = {
            "source_id": self.source_id,
            "path": walked.rel_path,
            "kind": parsed.kind,
            "language": parsed.language,
            "title": parsed.title,
            "size_bytes": walked.size,
            "content_hash": content_hash,
            "parser_version": PARSER_VERSION,
            "status": parsed.status,
            "error": parsed.error,
            "modified_at": commit.date if commit else datetime.fromtimestamp(walked.mtime, UTC),
            "git_commit": commit.commit if commit else None,
            "git_author": commit.author if commit else None,
            "meta": parsed.meta,
        }
        if previous is not None:
            document_id = previous.id
            await session.execute(
                update(Document).where(Document.id == document_id).values(**values)
            )
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        else:
            document_id = (
                await session.execute(insert(Document).values(**values).returning(Document.id))
            ).scalar_one()

        rows = chunk_rows(self.source, document_id, walked.rel_path, parsed)
        if rows:
            await session.execute(insert(Chunk), rows)
        self.stats["chunks_written"] += len(rows)
        if parsed.status == "needs_ocr":
            self.stats["needs_ocr"] += 1
        elif parsed.status == "error":
            self.stats["failed"] += 1
        else:
            self.stats["indexed"] += 1

    async def _embed(self) -> None:
        embedded, pending, warning = await embed_pending(
            self.sessions, self.source_id, self._on_embedded
        )
        self.stats["embedded"] = embedded
        self.stats["embed_pending"] = pending
        if warning:
            self.stats["warnings"].append(warning)

    async def _on_embedded(self, count: int) -> None:
        self.stats["embedded"] = count
        await self._progress()

    async def _finish(self, root: Path) -> None:
        commit = None
        if self.source.kind == "git" or git.is_repo(root):
            commit = await asyncio.to_thread(git.head_commit, root)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(Document.kind, func.count(Document.id))
                    .where(Document.source_id == self.source_id)
                    .group_by(Document.kind)
                )
            ).all()
            self.stats["documents_by_kind"] = {kind: count for kind, count in rows}
            self.stats["chunks_total"] = (
                await session.execute(
                    select(func.count(Chunk.id)).where(Chunk.source_id == self.source_id)
                )
            ).scalar_one()
            await session.execute(
                update(Source)
                .where(Source.id == self.source_id)
                .values(status="ready", last_indexed_at=datetime.now(UTC), last_commit=commit)
            )
            await session.commit()
        await self._save_run(status="succeeded", stage="done", finished_at=datetime.now(UTC))


async def embed_pending(
    sessions: async_sessionmaker[AsyncSession],
    source_id: int | None,
    on_progress: Any = None,
) -> tuple[int, int, str | None]:
    """Embed every chunk with no embedding, or one from a different model.

    Returns (embedded, still pending, warning). A missing model server is a warning, not a
    failure: the chunks are already searchable lexically, and a later run picks them up.
    """
    embedder = get_embedder()
    if embedder is None:
        return 0, 0, None

    def needs_embedding(model: str):
        condition = (Chunk.embedding.is_(None)) | (Chunk.embedding_model != model)
        if source_id is not None:
            condition = condition & (Chunk.source_id == source_id)
        return condition

    embedded = 0
    try:
        model = await embedder.model_name()
        last_id = 0
        batch = settings.embed_batch_size
        while True:
            async with sessions() as session:
                rows = (
                    await session.execute(
                        select(Chunk.id, Chunk.header, Chunk.content)
                        .where(needs_embedding(model) & (Chunk.id > last_id))
                        .order_by(Chunk.id)
                        .limit(batch * 8)
                    )
                ).all()
                if not rows:
                    break
                for start in range(0, len(rows), batch):
                    part = rows[start : start + batch]
                    vectors = await embedder.embed(
                        [embedding_text(r.header, r.content) for r in part], "document"
                    )
                    await session.execute(
                        update(Chunk),
                        [
                            {"id": r.id, "embedding": v, "embedding_model": model}
                            for r, v in zip(part, vectors, strict=True)
                        ],
                    )
                    embedded += len(part)
                await session.commit()
                last_id = rows[-1].id
            if on_progress is not None:
                await on_progress(embedded)
        return embedded, 0, None
    except ModelUnavailable as exc:
        async with sessions() as session:
            condition = Chunk.embedding.is_(None)
            if source_id is not None:
                condition = condition & (Chunk.source_id == source_id)
            pending = (
                await session.execute(select(func.count(Chunk.id)).where(condition))
            ).scalar_one()
        log.warning("embedding stopped: %s", exc)
        return embedded, pending, f"embedding incomplete ({pending} chunks pending): {exc}"


async def start_run(session: AsyncSession, source_id: int) -> int:
    """Record a queued run and mark the source queued. Commits."""
    run = IndexRun(source_id=source_id, status="queued")
    session.add(run)
    await session.execute(update(Source).where(Source.id == source_id).values(status="queued"))
    await session.commit()
    return run.id


def summarize(stats: dict[str, Any]) -> str:
    skipped = Counter(stats.get("skipped", {}))
    reasons = ", ".join(f"{k}={v}" for k, v in skipped.most_common())
    return (
        f"{stats['indexed']} indexed, {stats['unchanged']} unchanged, {stats['deleted']} deleted, "
        f"{stats['failed']} failed, {stats['needs_ocr']} need OCR; "
        f"{stats['chunks_written']} chunks written, {stats['embedded']} embedded; "
        f"skipped {sum(skipped.values())} ({reasons})"
    )
