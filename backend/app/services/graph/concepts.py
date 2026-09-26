"""LLM extraction, layered on the deterministic graph: which technologies and concepts a note
(or a project README) is about. The fuzzy half of the graph, so it is fenced in:

  * Tiered: notes and READMEs only. Source files already have exact facts from manifests and
    imports, and running a model over every function would burn a free tier for noise.
  * Cached by (chunk content hash, prompt version): a re-run costs nothing for unchanged text.
  * Verified: an extracted item survives only if its evidence quote really occurs in the
    chunk. A model that invents a quote invents the fact with it.
  * Conservative resolution: a technology joins the curated node only on an exact alias
    match; everything else becomes a `concept` keyed by its normalised name. Nothing is
    merged on similarity.
  * Provenance: every edge carries the chunk it came from, at confidence 0.7.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Chunk, Document, Edge, LlmExtraction, Node
from app.schemas.extraction import ConceptExtraction
from app.services.graph import technologies
from app.services.graph.builder import GRAPH_LOCK, prune_orphans
from app.services.graph.technologies import normalize
from app.services.llm.base import LLMUnavailable
from app.services.llm.factory import get_extraction_chat
from app.services.llm.prompt import load as load_prompt

log = logging.getLogger(__name__)

LLM_CONFIDENCE = 0.7
MAX_CHUNK_CHARS = 6000
MIN_CHUNK_CHARS = 80  # a heading and one line says nothing worth a model call
STOP_CONCEPTS = {
    "code", "database", "project", "system", "app", "application", "api", "service",
    "data", "model", "server", "client", "library", "framework", "tool", "idea", "notes",
}  # fmt: skip


@dataclass
class ExtractionStats:
    chunks: int = 0
    cached: int = 0
    called: int = 0
    failed: int = 0
    edges: int = 0
    dropped_unverified: int = 0
    stopped: str | None = None
    by_kind: dict[str, int] = field(default_factory=dict)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def verified(quote: str, chunk_text: str) -> bool:
    """The evidence must be in the text (whitespace and case aside), give or take trailing
    punctuation the model may add or drop."""
    needle = _squash(quote).strip(" .,;:\"'`")
    return len(needle) >= 3 and needle in _squash(chunk_text)


@dataclass
class _Target:
    node_id: int
    chunk_id: int
    document_id: int
    content_hash: str
    text: str


async def _targets(session: AsyncSession, source_id: int, limit: int) -> list[_Target]:
    """Chunks worth extracting from: notes (markdown outside any project) and project
    READMEs, each attached to the node the edges will come from."""
    nodes = (await session.execute(select(Node).where(Node.source_id == source_id))).scalars().all()
    notes = {n.meta.get("path"): n.id for n in nodes if n.kind == "note"}
    projects = sorted(
        ((n.meta.get("root") or "", n.id) for n in nodes if n.kind == "project"),
        key=lambda p: -len(p[0]),
    )
    rows = (
        await session.execute(
            select(Chunk.id, Chunk.document_id, Chunk.content_hash, Chunk.header, Chunk.content)
            .join(Document, Document.id == Chunk.document_id)
            .where(Chunk.source_id == source_id, Document.kind == "markdown")
            .add_columns(Document.path)
            .order_by(Document.path, Chunk.ordinal)
        )
    ).all()
    targets = []
    for row in rows:
        node_id = notes.get(row.path)
        if node_id is None and row.path.rsplit("/", 1)[-1].lower().startswith("readme"):
            node_id = next(
                (pid for root, pid in projects if not root or row.path.startswith(root + "/")),
                None,
            )
        if node_id is None or len(row.content) < MIN_CHUNK_CHARS:
            continue
        text = f"{row.header}\n\n{row.content}"[:MAX_CHUNK_CHARS]
        targets.append(_Target(node_id, row.id, row.document_id, row.content_hash, text))
    return targets[:limit]


async def _extract_one(target: _Target, prompt_text: str) -> tuple[ConceptExtraction, str]:
    chat = get_extraction_chat()
    if chat is None:
        raise LLMUnavailable("no extraction model configured")
    completion = await chat.complete(
        [
            {"role": "system", "content": prompt_text},
            {"role": "user", "content": f"Text:\n{target.text}"},
        ],
        schema=ConceptExtraction,
        max_tokens=800,
    )
    text = completion.text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    payload = json.loads(fence.group(1) if fence else text)
    return ConceptExtraction.model_validate(payload), completion.model


async def extract_concepts(
    sessions: async_sessionmaker[AsyncSession], source_id: int, max_chunks: int = 500
) -> ExtractionStats:
    """Run (or re-use cached) extraction over a source and replace its LLM edges."""
    prompt = load_prompt("concepts")
    stats = ExtractionStats()
    async with sessions() as session:
        targets = await _targets(session, source_id, max_chunks)
        hashes = list({t.content_hash for t in targets})
        cache = {
            row.content_hash: row.result
            for row in (
                await session.execute(
                    select(LlmExtraction).where(
                        LlmExtraction.content_hash.in_(hashes or [""]),
                        LlmExtraction.prompt_version == prompt.version,
                    )
                )
            ).scalars()
        }
    stats.chunks = len(targets)

    results: list[tuple[_Target, ConceptExtraction, str]] = []
    for target in targets:
        if target.content_hash in cache:
            stats.cached += 1
            cached = cache[target.content_hash]
            extraction = ConceptExtraction.model_validate(cached["extraction"])
            results.append((target, extraction, cached["model"]))
            continue
        try:
            extraction, model = await _extract_one(target, prompt.text)
        except LLMUnavailable as exc:
            # Out of quota or offline: keep what was done, the cache makes a re-run resume.
            stats.stopped = str(exc)[:300]
            log.warning("concept extraction stopped: %s", exc)
            break
        except (ValueError, ValidationError) as exc:  # json.JSONDecodeError is a ValueError
            stats.failed += 1
            log.info("unusable extraction for chunk %s: %s", target.chunk_id, exc)
            continue
        stats.called += 1
        cache[target.content_hash] = {"extraction": extraction.model_dump(), "model": model}
        async with sessions() as session:
            await session.execute(
                pg_insert(LlmExtraction)
                .values(
                    content_hash=target.content_hash,
                    prompt_version=prompt.version,
                    model=model,
                    result=cache[target.content_hash],
                )
                .on_conflict_do_nothing()
            )
            await session.commit()
        results.append((target, extraction, model))

    async with sessions() as session:
        await _write_edges(session, source_id, results, prompt.version, stats)
        await session.commit()
    return stats


async def _write_edges(
    session: AsyncSession,
    source_id: int,
    results: list[tuple[_Target, ConceptExtraction, str]],
    prompt_version: str,
    stats: ExtractionStats,
) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": GRAPH_LOCK})
    await session.execute(delete(Edge).where(Edge.source_id == source_id, Edge.extractor == "llm"))
    rows = []
    seen: set[tuple[int, str, str]] = set()
    for target, extraction, model in results:
        for item in extraction.concepts:
            if not verified(item.evidence, target.text):
                stats.dropped_unverified += 1
                continue
            tech = technologies.by_name(item.name)
            if tech is not None:
                kind, key, name, meta = (
                    "technology",
                    tech.key,
                    tech.name,
                    {"category": tech.category},
                )
            else:
                key = normalize(item.name)
                if len(key) < 2 or key in STOP_CONCEPTS:
                    continue
                kind, name, meta = "concept", item.name.strip(), {}
            identity = (target.node_id, kind, key)
            if identity in seen:
                continue
            seen.add(identity)
            node_id = (
                await session.execute(
                    pg_insert(Node)
                    .values(kind=kind, key=key, name=name, meta=meta)
                    .on_conflict_do_update(constraint="uq_nodes_kind", set_={"kind": kind})
                    .returning(Node.id)
                )
            ).scalar_one()
            rows.append(
                {
                    "src_id": target.node_id,
                    "dst_id": node_id,
                    "type": "mentions",
                    "source_id": source_id,
                    "document_id": target.document_id,
                    "chunk_ids": [target.chunk_id],
                    "evidence": item.evidence[:500],
                    "extractor": "llm",
                    "confidence": LLM_CONFIDENCE,
                    "meta": {"model": model, "prompt": prompt_version},
                }
            )
            stats.by_kind[kind] = stats.by_kind.get(kind, 0) + 1
    if rows:
        await session.execute(pg_insert(Edge), rows)
    stats.edges = len(rows)
    await prune_orphans(session)
