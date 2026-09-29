"""Ideas end to end: store what detection found in a source's notes, match every idea against
every project, and mirror the outcome into the graph (note -proposes-> idea
-implemented_by-> project), so the ego-network view and the chat see it too.

Detection runs per source, while indexing (it reads the notes from disk). Matching runs over
all ideas at once, because a new commit in any repository can implement an idea written in
any notes folder: after every index run, after LLM extraction, and on demand.
"""

import asyncio
import logging
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Document, Edge, Idea, Node
from app.services.graph.builder import GRAPH_LOCK
from app.services.graph.technologies import normalize
from app.services.ideas.detect import IdeaDraft, NoteDoc, detect
from app.services.ideas.matching import Projects, corpus_size, match_idea

log = logging.getLogger(__name__)

DETERMINISTIC = ("note", "inline")


def idea_text(idea: Idea) -> str:
    return f"{idea.title}. {idea.summary}".strip()


async def note_documents(session: AsyncSession, source_id: int) -> list[NoteDoc]:
    """Markdown files that belong to no project: the graph builder made each a note node."""
    doc_ids = [
        int(node_meta["document_id"])
        for node_meta in (
            await session.execute(
                select(Node.meta).where(Node.source_id == source_id, Node.kind == "note")
            )
        ).scalars()
        if node_meta.get("document_id") is not None
    ]
    if not doc_ids:
        return []
    rows = (
        await session.execute(
            select(Document.id, Document.path, Document.title, Document.meta, Document.modified_at)
            .where(Document.id.in_(doc_ids))
            .order_by(Document.path)
        )
    ).all()
    return [NoteDoc(r.id, r.path, r.title, r.meta or {}, r.modified_at) for r in rows]


async def store(
    session: AsyncSession,
    source_id: int,
    drafts: list[IdeaDraft],
    extractors: tuple[str, ...] = DETERMINISTIC,
) -> int:
    """Upsert the drafts and drop this source's ideas (of these extractors) that are gone.
    Matching results and the user's overrides on surviving ideas are left alone."""
    for draft in drafts:
        values = {
            "document_id": draft.document_id,
            "title": draft.title,
            "summary": draft.summary,
            "extractor": draft.extractor,
            "line": draft.line,
            "evidence": draft.evidence,
            "written_on": draft.written_on,
            "declared_status": draft.declared_status,
            "declared_project": draft.declared_project,
        }
        stmt = pg_insert(Idea).values(
            source_id=source_id, key=draft.key, status="unimplemented", **values
        )
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_ideas_source_id",
                set_={**values, "updated_at": text("now()")},
            )
        )
    await session.execute(
        delete(Idea).where(
            Idea.source_id == source_id,
            Idea.extractor.in_(extractors),
            Idea.key.not_in([d.key for d in drafts] or [""]),
        )
    )
    return len(drafts)


async def detect_source(
    sessions: async_sessionmaker[AsyncSession], source_id: int, root: Path
) -> int:
    """Find the ideas in one source's notes (read from disk) and store them."""
    async with sessions() as session:
        notes = await note_documents(session, source_id)

    def read_all() -> list[IdeaDraft]:
        drafts: list[IdeaDraft] = []
        for note in notes:
            try:
                content = (root / note.path).read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            drafts.extend(detect(note, content))
        return drafts

    drafts = await asyncio.to_thread(read_all)
    async with sessions() as session:
        count = await store(session, source_id, drafts)
        await session.commit()
    return count


async def _links(session: AsyncSession) -> dict[int, set[int]]:
    """document id of a note -> projects it names with a [[wikilink]]."""
    note = Node.__table__.alias("note")
    project = Node.__table__.alias("project")
    rows = (
        await session.execute(
            select(note.c.meta, Edge.dst_id)
            .select_from(Edge)
            .join(note, note.c.id == Edge.src_id)
            .join(project, project.c.id == Edge.dst_id)
            .where(note.c.kind == "note", project.c.kind == "project")
        )
    ).all()
    links: dict[int, set[int]] = defaultdict(set)
    for meta, project_id in rows:
        if (meta or {}).get("document_id") is not None:
            links[int(meta["document_id"])].add(project_id)
    return links


async def match_all(sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Re-match every idea against every project, then rewrite the ideas' graph."""
    async with sessions() as session:
        projects = await Projects.load(session)
        total = await corpus_size(session)
        links = await _links(session)
        by_name = {normalize(p.name): p.id for p in projects.all}
        ideas = list((await session.execute(select(Idea).order_by(Idea.id))).scalars())
        now = datetime.now(UTC)
        signals: set[str] = set()
        for idea in ideas:
            linked = links.get(idea.document_id, set()) if idea.extractor == "note" else set()
            match = await match_idea(session, idea_text(idea), projects, total, linked)
            signals.update(match.details["signals"])
            idea.status = match.status
            idea.score = round(match.score, 4)
            idea.implemented_by_id = match.project.id if match.project else None
            idea.match = match.details
            idea.matched_at = now
            idea.declared_project_id = (
                by_name.get(normalize(idea.declared_project)) if idea.declared_project else None
            )
        await session.flush()
        await sync_graph(session, ideas)
        await session.commit()
        counts = Counter(i.effective[0] for i in ideas)
    stats = {"ideas": len(ideas), "projects": len(projects.all), "signals": sorted(signals)}
    stats.update(counts)
    log.info("ideas matched: %s", stats)
    return stats


def _implementation_evidence(idea: Idea, project_id: int, origin: str) -> dict[str, Any]:
    """Provenance for idea -implemented_by-> project, as for every edge: the code that
    matched (its closest chunk), or the note itself when the note or the user said so."""
    if origin == "match":
        candidate = next(
            (c for c in (idea.match or {}).get("candidates", []) if c["project_id"] == project_id),
            None,
        )
        if candidate is not None:
            best, document = candidate.get("best"), candidate.get("best_document")
            words = ", ".join(candidate.get("matched", [])[:8])
            if best is not None:
                return {
                    "document_id": best["document_id"],
                    "chunk_ids": [best["chunk_id"]],
                    "evidence": f"closest code; shares: {words}"[:500],
                }
            if document is not None:
                return {"document_id": document["document_id"], "evidence": f"shares: {words}"}
    said = "you marked it" if origin == "user" else "the note says so"
    return {"document_id": idea.document_id, "evidence": said}


async def sync_graph(session: AsyncSession, ideas: list[Idea]) -> None:
    """Idea nodes and their edges are derived data: rewritten whole, under the graph lock."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": GRAPH_LOCK})
    await session.execute(delete(Edge).where(Edge.extractor == "idea"))
    if not ideas:
        await session.execute(delete(Node).where(Node.kind == "idea"))
        return
    paths = {
        row.id: row.path
        for row in (
            await session.execute(
                select(Document.id, Document.path).where(
                    Document.id.in_({i.document_id for i in ideas})
                )
            )
        ).all()
    }
    note_ids = {
        (row.source_id, row.key): row.id
        for row in (
            await session.execute(
                select(Node.id, Node.source_id, Node.key).where(Node.kind == "note")
            )
        ).all()
    }
    keep: list[int] = []
    edges: list[dict[str, Any]] = []
    for idea in ideas:
        status, project_id, origin = idea.effective
        node_id = (
            await session.execute(
                pg_insert(Node)
                .values(
                    kind="idea",
                    key=f"{idea.source_id}:{idea.key}",
                    name=idea.title,
                    source_id=idea.source_id,
                    meta={"idea_id": idea.id, "status": status, "origin": origin},
                )
                .on_conflict_do_update(
                    constraint="uq_nodes_kind",
                    set_={
                        "name": idea.title,
                        "meta": {"idea_id": idea.id, "status": status, "origin": origin},
                        "updated_at": text("now()"),
                    },
                )
                .returning(Node.id)
            )
        ).scalar_one()
        idea.node_id = node_id
        keep.append(node_id)
        path = paths.get(idea.document_id)
        note_id = note_ids.get((idea.source_id, f"{idea.source_id}:{path}"))
        base = {"source_id": idea.source_id, "extractor": "idea", "chunk_ids": []}
        if note_id is not None:
            edges.append(
                {
                    **base,
                    "src_id": note_id,
                    "dst_id": node_id,
                    "type": "proposes",
                    "document_id": idea.document_id,
                    "line": idea.line,
                    "evidence": (idea.evidence or idea.title)[:500],
                    "confidence": 1.0,
                    "meta": {"extractor": idea.extractor},
                }
            )
        if project_id is not None and status in ("implemented", "partial"):
            edges.append(
                {
                    **base,
                    **_implementation_evidence(idea, project_id, origin),
                    "src_id": node_id,
                    "dst_id": project_id,
                    "type": "implemented_by",
                    "line": None,
                    "confidence": 1.0 if origin != "match" else min(1.0, idea.score),
                    "meta": {"status": status, "origin": origin},
                }
            )
    await session.execute(delete(Node).where(Node.kind == "idea", Node.id.not_in(keep)))
    if edges:
        await session.execute(pg_insert(Edge), edges)
