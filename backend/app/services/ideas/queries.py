"""Reading ideas back, with everything a page or an answer needs to show its evidence."""

from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, Idea, Node, Source
from app.schemas.idea import IdeaCandidate, IdeaOut, ProjectRef

Sort = Literal["oldest", "newest", "closest"]


def _chunk_for(chunks: list[tuple[int, int | None, int | None]], line: int | None) -> int | None:
    """The chunk holding the idea's line, else the document's first chunk."""
    if not chunks:
        return None
    if line is not None:
        for chunk_id, start, end in chunks:
            if start is not None and end is not None and start <= line <= end:
                return chunk_id
    return chunks[0][0]


async def list_ideas(
    session: AsyncSession,
    status: str | None = None,
    sort: Sort = "oldest",
    ids: list[int] | None = None,
) -> list[IdeaOut]:
    stmt = (
        select(Idea, Document.path, Document.meta.label("doc_meta"), Source.name.label("source"))
        .join(Document, Document.id == Idea.document_id)
        .join(Source, Source.id == Idea.source_id)
    )
    if ids is not None:
        stmt = stmt.where(Idea.id.in_(ids or [0]))
    rows = (await session.execute(stmt)).all()
    ideas = [r.Idea for r in rows]

    project_ids = {
        pid
        for i in ideas
        for pid in (i.implemented_by_id, i.declared_project_id, i.user_project_id)
        if pid is not None
    }
    names = {
        row.id: row.name
        for row in (
            await session.execute(select(Node.id, Node.name).where(Node.id.in_(project_ids or [0])))
        ).all()
    }
    chunks: dict[int, list[tuple[int, int | None, int | None]]] = {}
    doc_ids = {i.document_id for i in ideas}
    for row in (
        await session.execute(
            select(Chunk.id, Chunk.document_id, Chunk.start_line, Chunk.end_line)
            .where(Chunk.document_id.in_(doc_ids or [0]))
            .order_by(Chunk.document_id, Chunk.ordinal)
        )
    ).all():
        chunks.setdefault(row.document_id, []).append((row.id, row.start_line, row.end_line))

    out: list[IdeaOut] = []
    for row in rows:
        idea: Idea = row.Idea
        effective, project_id, origin = idea.effective
        if status and status != "all" and effective != status:
            continue
        match: dict[str, Any] = idea.match or {}
        candidates = [IdeaCandidate.model_validate(c) for c in match.get("candidates", [])]
        out.append(
            IdeaOut(
                id=idea.id,
                title=idea.title,
                summary=idea.summary,
                extractor=idea.extractor,
                source_id=idea.source_id,
                source_name=row.source,
                document_id=idea.document_id,
                path=row.path,
                line=idea.line,
                chunk_id=_chunk_for(chunks.get(idea.document_id, []), idea.line),
                node_id=idea.node_id,
                written_on=idea.written_on,
                tags=sorted({str(t).lower() for t in (row.doc_meta or {}).get("tags") or []}),
                status=effective,
                origin=origin,
                project=(
                    ProjectRef(id=project_id, name=names[project_id])
                    if project_id in names
                    else None
                ),
                matched_status=idea.status,
                score=idea.score,
                closest=candidates[0] if candidates else None,
                candidates=candidates,
                missing=match.get("missing", []),
                signals=match.get("signals", []),
                declared_status=idea.declared_status,
                declared_project=idea.declared_project,
                user_note=idea.user_note,
                matched_at=idea.matched_at,
            )
        )
    if sort == "closest":
        out.sort(key=lambda i: (-i.score, i.title.lower()))
    else:
        # Undated ideas last either way; ties by title so the order is stable.
        dated = sorted(
            (i for i in out if i.written_on),
            key=lambda i: (i.written_on, i.title.lower()),
            reverse=sort == "newest",
        )
        out = dated + sorted((i for i in out if not i.written_on), key=lambda i: i.title.lower())
    return out


async def counts(session: AsyncSession) -> dict[str, Any]:
    ideas = list((await session.execute(select(Idea))).scalars())
    by_status: dict[str, int] = {}
    signals: set[str] = set()
    for idea in ideas:
        by_status[idea.effective[0]] = by_status.get(idea.effective[0], 0) + 1
        signals.update((idea.match or {}).get("signals", []))
    projects = (
        await session.execute(select(func.count(Node.id)).where(Node.kind == "project"))
    ).scalar_one()
    return {
        "total": len(ideas),
        "by_status": by_status,
        "projects": projects,
        "signals": sorted(signals),
    }
