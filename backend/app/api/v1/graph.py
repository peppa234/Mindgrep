from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Edge, Node
from app.deps import get_session
from app.schemas.graph import (
    Neighbourhood,
    NodeDetail,
    NodeOut,
    ProjectSummary,
    RelatedOut,
)
from app.services.graph import queries

router = APIRouter(prefix="/graph", tags=["graph"])

NODE_KINDS = ("project", "technology", "package", "person", "note", "topic", "concept")
KIND_HELP = f"Any of: {', '.join(NODE_KINDS)}"


def _related_out(item: queries.Related) -> RelatedOut:
    return RelatedOut(
        node_id=item.node_id,
        kind=item.kind,
        name=item.name,
        meta=item.meta,
        confidence=item.confidence,
        evidence=[asdict(e) for e in item.evidence],
    )


@router.get("/projects", response_model=list[ProjectSummary])
async def list_projects(
    uses: str | None = Query(
        None, description="Only projects using this technology or package (any alias: postgres)"
    ),
    session: AsyncSession = Depends(get_session),
) -> list[ProjectSummary]:
    """Every detected project with its stack. Projects are found from Git working trees and
    dependency manifests; stacks from manifests, Dockerfiles, imports and file languages."""
    projects = await queries.list_projects(session)
    if uses:
        entities = await queries.resolve_entities(session, uses, ("technology", "package"))
        if not entities:
            return []
        keep: set[int] = set()
        for entity in entities:
            keep |= {p.node_id for p in await queries.projects_using(session, entity)}
        projects = [p for p in projects if p["id"] in keep]
    return [ProjectSummary.model_validate(p) for p in projects]


@router.get("/nodes", response_model=list[NodeOut])
async def search_nodes(
    q: str = Query(min_length=1, max_length=200),
    kind: list[str] | None = Query(None, description=KIND_HELP),
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[NodeOut]:
    nodes = await queries.search_nodes(session, q, kind, limit)
    return [NodeOut.model_validate(n, from_attributes=True) for n in nodes]


@router.get("/nodes/{node_id}", response_model=NodeDetail)
async def get_node(node_id: int, session: AsyncSession = Depends(get_session)) -> NodeDetail:
    """A node and everything one hop away, with the evidence for every relation."""
    node = await session.get(Node, node_id)
    if node is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found")
    detail = NodeDetail.model_validate(node, from_attributes=True)
    types = (
        await session.execute(
            select(Edge.type, Edge.src_id == node_id)
            .where((Edge.src_id == node_id) | (Edge.dst_id == node_id))
            .distinct()
        )
    ).all()
    for type_, outgoing in types:
        direction = "out" if outgoing else "in"
        items = await queries.related(session, node_id, direction, (type_,))
        target = detail.outgoing if outgoing else detail.incoming
        target[type_] = [_related_out(i) for i in items]
    return detail


@router.get("/nodes/{node_id}/neighbourhood", response_model=Neighbourhood)
async def neighbourhood(
    node_id: int,
    depth: int = Query(1, ge=1, le=3),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> Neighbourhood:
    """The ego network around one node (recursive CTE, both directions, nearest first).
    Capped on purpose: a global graph of everything is unreadable."""
    if await session.get(Node, node_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "node not found")
    return Neighbourhood.model_validate(await queries.neighbourhood(session, node_id, depth, limit))
