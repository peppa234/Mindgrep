"""Graph reads. "Which projects use PostgreSQL?" is one hop: an indexed join, not a graph
database (ADR-0001). The neighbourhood query is the only recursive one."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ARRAY, Text, bindparam, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Edge, Node, Source
from app.services.graph import technologies
from app.services.graph.technologies import normalize

# The kinds a person names in a question.
ENTITY_KINDS = ("technology", "project", "package")


@dataclass
class Entity:
    id: int
    kind: str
    name: str
    matched: str  # the words of the question that named it


@dataclass
class Evidence:
    edge_id: int
    type: str
    extractor: str
    evidence: str | None
    confidence: float
    document_id: int | None
    path: str | None
    source_name: str | None
    line: int | None
    chunk_ids: list[int]
    meta: dict[str, Any]


@dataclass
class Related:
    node_id: int
    kind: str
    name: str
    meta: dict[str, Any]
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return max((e.confidence for e in self.evidence), default=0.0)


# --------------------------------------------------------------------------- entities

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#./_-]*")


def ngrams(phrase: str, longest: int = 4) -> list[str]:
    """Candidate names in a phrase, longest first: 'student portal app' -> 'student portal
    app', 'student portal', 'portal app', 'student', ..."""
    tokens = [t.rstrip(".") for t in _TOKEN_RE.findall(phrase)]
    out = []
    for size in range(min(longest, len(tokens)), 0, -1):
        for start in range(len(tokens) - size + 1):
            out.append(" ".join(tokens[start : start + size]))
    return out


async def resolve_entities(
    session: AsyncSession, phrase: str, kinds: tuple[str, ...] = ENTITY_KINDS
) -> list[Entity]:
    """Nodes the phrase names, by exact normalised match: curated aliases for technologies,
    names for projects and packages. Longer matches win and consume their words, so
    'spring boot' is Spring Boot and not also Spring."""
    candidates = ngrams(phrase)
    if not candidates:
        return []
    wanted: dict[str, str] = {}  # normalised key -> matched words
    tech_names: dict[str, str] = {}
    for candidate in candidates:
        key = normalize(candidate)
        if not key or key in wanted:
            continue
        wanted[key] = candidate
        tech = technologies.by_name(candidate)
        if tech is not None:
            tech_names.setdefault(tech.name, candidate)

    conditions = []
    if "technology" in kinds and tech_names:
        conditions.append((Node.kind == "technology") & Node.name.in_(list(tech_names)))
    other = [k for k in kinds if k != "technology"]
    if other:
        # regexp_replace mirrors technologies.normalize for the common punctuation.
        normalized_name = func.regexp_replace(func.lower(Node.name), r"[\s_.'\"/()-]+", "", "g")
        conditions.append(Node.kind.in_(other) & normalized_name.in_(list(wanted)))
    if not conditions:
        return []
    rows = (
        await session.execute(select(Node.id, Node.kind, Node.name).where(or_(*conditions)))
    ).all()

    found: list[Entity] = []
    for row in rows:
        matched = (
            tech_names.get(row.name)
            if row.kind == "technology"
            else wanted.get(normalize(row.name))
        )
        if matched:
            found.append(Entity(row.id, row.kind, row.name, matched))
    # A package named like a curated technology (npm "react") is the technology.
    tech_matches = {normalize(e.matched) for e in found if e.kind == "technology"}
    found = [e for e in found if e.kind != "package" or normalize(e.matched) not in tech_matches]
    # Longest match first; drop matches whose words sit inside a longer one.
    found.sort(key=lambda e: (-len(e.matched), e.kind != "project", e.name))
    kept: list[Entity] = []
    for entity in found:
        words = entity.matched.lower()
        if not any(
            words != k.matched.lower() and re.search(rf"\b{re.escape(words)}\b", k.matched.lower())
            for k in kept
        ):
            kept.append(entity)
    return kept


# --------------------------------------------------------------------------- one hop


def _evidence_columns():
    return (
        Edge.id,
        Edge.type,
        Edge.extractor,
        Edge.evidence,
        Edge.confidence,
        Edge.document_id,
        Edge.line,
        Edge.chunk_ids,
        Edge.meta.label("edge_meta"),
        Document.path,
        Source.name.label("source_name"),
    )


def _evidence(row) -> Evidence:
    return Evidence(
        row.id, row.type, row.extractor, row.evidence, row.confidence, row.document_id,
        row.path, row.source_name, row.line, list(row.chunk_ids or []), row.edge_meta or {},
    )  # fmt: skip


async def related(
    session: AsyncSession,
    node_id: int,
    direction: str,
    types: tuple[str, ...],
    kinds: tuple[str, ...] | None = None,
) -> list[Related]:
    """Neighbours one hop away along edges of `types`, each with every piece of evidence.
    direction: "out" (node -> x) or "in" (x -> node)."""
    near, far = (Edge.src_id, Edge.dst_id) if direction == "out" else (Edge.dst_id, Edge.src_id)
    stmt = (
        select(Node.id.label("node_id"), Node.kind, Node.name, Node.meta, *_evidence_columns())
        .select_from(Edge)
        .join(Node, Node.id == far)
        .outerjoin(Document, Document.id == Edge.document_id)
        .join(Source, Source.id == Edge.source_id)
        .where(near == node_id, Edge.type.in_(types))
        .order_by(Node.name, Edge.confidence.desc(), Edge.id)
    )
    if kinds:
        stmt = stmt.where(Node.kind.in_(kinds))
    grouped: dict[int, Related] = {}
    for row in (await session.execute(stmt)).all():
        item = grouped.setdefault(
            row.node_id, Related(row.node_id, row.kind, row.name, row.meta or {})
        )
        item.evidence.append(_evidence(row))
    return list(grouped.values())


async def projects_using(session: AsyncSession, node: Node | Entity) -> list[Related]:
    """Projects with a `uses` (technology) or `depends_on` (package, project) edge to node."""
    types = ("uses",) if node.kind == "technology" else ("depends_on",)
    projects = await related(session, node.id, "in", types, kinds=("project",))
    return sorted(projects, key=lambda p: (-p.confidence, p.name.lower()))


async def notes_mentioning(session: AsyncSession, node_id: int) -> list[Related]:
    return await related(session, node_id, "in", ("mentions", "links_to"), kinds=("note",))


async def project_stack(session: AsyncSession, project_id: int) -> dict[str, list[Related]]:
    """Everything known about one project, grouped for display."""
    return {
        "technologies": await related(session, project_id, "out", ("uses",), ("technology",)),
        "packages": await related(session, project_id, "out", ("depends_on",), ("package",)),
        "depends_on": await related(session, project_id, "out", ("depends_on",), ("project",)),
        "used_by": await related(session, project_id, "in", ("depends_on",), ("project",)),
        "authors": await related(session, project_id, "in", ("authored",), ("person",)),
        "notes": await notes_mentioning(session, project_id),
    }


async def list_projects(session: AsyncSession) -> list[dict[str, Any]]:
    """Every project with its curated stack (technology names by category) and counts."""
    projects = (
        await session.execute(
            select(Node, Source.name.label("source_name"))
            .join(Source, Source.id == Node.source_id)
            .where(Node.kind == "project")
            .order_by(func.lower(Node.name))
        )
    ).all()
    ids = [row.Node.id for row in projects]
    stacks: dict[int, dict[str, dict[str, Any]]] = defaultdict(dict)
    packages: dict[int, int] = defaultdict(int)
    if ids:
        rows = (
            await session.execute(
                select(Edge.src_id, Edge.type, Edge.extractor, Node.name, Node.kind, Node.meta)
                .join(Node, Node.id == Edge.dst_id)
                .where(Edge.src_id.in_(ids), Edge.type.in_(("uses", "depends_on")))
            )
        ).all()
        for row in rows:
            if row.kind == "technology":
                entry = stacks[row.src_id].setdefault(
                    row.name,
                    {
                        "name": row.name,
                        "category": (row.meta or {}).get("category"),
                        "via": set(),
                    },
                )
                entry["via"].add(row.extractor)
            elif row.kind == "package":
                packages[row.src_id] += 1
    out = []
    for row in projects:
        node = row.Node
        stack = sorted(
            ({**t, "via": sorted(t["via"])} for t in stacks[node.id].values()),
            key=lambda t: (CATEGORY_ORDER.get(t["category"], 99), t["name"].lower()),
        )
        out.append(
            {
                "id": node.id,
                "name": node.name,
                "source_id": node.source_id,
                "source_name": row.source_name,
                "root": node.meta.get("root", ""),
                "manifests": node.meta.get("manifests", []),
                "technologies": stack,
                "package_count": packages[node.id],
            }
        )
    return out


CATEGORY_ORDER = {
    "language": 0, "framework": 1, "database": 2, "ai": 3, "auth": 4, "infra": 5,
    "library": 6, "tool": 7,
}  # fmt: skip


# --------------------------------------------------------------------------- neighbourhood

NEIGHBOURHOOD_SQL = text(
    """
    WITH RECURSIVE walk(node_id, depth) AS (
        SELECT CAST(:start AS BIGINT), 0
      UNION
        SELECT n.id, w.depth + 1
        FROM walk w
        JOIN edges e ON e.src_id = w.node_id OR e.dst_id = w.node_id
        JOIN nodes n ON n.id = CASE WHEN e.src_id = w.node_id THEN e.dst_id ELSE e.src_id END
        WHERE w.depth < :depth AND (CAST(:kinds AS TEXT[]) IS NULL OR n.kind = ANY(:kinds))
    )
    SELECT node_id, MIN(depth) AS depth FROM walk GROUP BY node_id
    ORDER BY MIN(depth), node_id
    LIMIT :limit
    """
).bindparams(bindparam("kinds", type_=ARRAY(Text)))


async def neighbourhood(
    session: AsyncSession,
    node_id: int,
    depth: int = 1,
    limit: int = 50,
    kinds: list[str] | None = None,
) -> dict[str, Any]:
    """The ego network around one node: nodes within `depth` hops (both directions, capped
    at `limit`, nearest first) and the edges among them, collapsed to one per (src, dst,
    type) with the number of pieces of evidence. `kinds` limits the walk to those node kinds
    (the focal node always counts): a project's 300 packages would crowd out everything."""
    rows = (
        await session.execute(
            NEIGHBOURHOOD_SQL,
            {"start": node_id, "depth": depth, "limit": limit, "kinds": kinds or None},
        )
    ).all()
    depths = {r.node_id: r.depth for r in rows}
    if not depths:
        return {"nodes": [], "edges": []}
    nodes = (await session.execute(select(Node).where(Node.id.in_(list(depths))))).scalars()
    edges = (
        await session.execute(
            select(
                Edge.src_id,
                Edge.dst_id,
                Edge.type,
                func.count().label("evidence"),
                func.max(Edge.confidence).label("confidence"),
            )
            .where(Edge.src_id.in_(list(depths)), Edge.dst_id.in_(list(depths)))
            .group_by(Edge.src_id, Edge.dst_id, Edge.type)
        )
    ).all()
    return {
        "nodes": [
            {"id": n.id, "kind": n.kind, "name": n.name, "depth": depths[n.id], "meta": n.meta}
            for n in sorted(nodes, key=lambda n: (depths[n.id], n.name.lower()))
        ],
        "edges": [
            {
                "src": e.src_id,
                "dst": e.dst_id,
                "type": e.type,
                "evidence": e.evidence,
                "confidence": e.confidence,
            }
            for e in edges
        ],
    }


async def search_nodes(
    session: AsyncSession, q: str, kinds: list[str] | None = None, limit: int = 20
) -> list[Node]:
    similarity = func.similarity(Node.name, q)
    escaped = q.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    contains = Node.name.ilike(f"%{escaped}%", escape="\\")
    stmt = select(Node).where(or_(contains, similarity > 0.3))
    if kinds:
        stmt = stmt.where(Node.kind.in_(kinds))
    stmt = stmt.order_by(similarity.desc(), Node.name).limit(limit)
    return list((await session.execute(stmt)).scalars())
