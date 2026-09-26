"""Answers read straight off the knowledge graph. No model writes them, so they cannot be
wrong in ways the graph is not: every line cites the manifest line, import or file the fact
came from, and "none of your projects use X" is a real answer, not an abstention."""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Node
from app.schemas.chat import ChatSource
from app.services.graph import queries
from app.services.graph.queries import CATEGORY_ORDER, Entity, Evidence, Related

# Which evidence to cite when there are several: a declared dependency beats an import,
# which beats "there are Python files here".
EXTRACTOR_RANK = {
    "manifest": 0, "compose": 1, "docker": 2, "import": 3, "language": 4, "wikilink": 5,
    "tag": 6, "llm": 7, "git": 8,
}  # fmt: skip
CATEGORY_LABEL = {
    "language": "Languages", "framework": "Frameworks", "database": "Databases",
    "ai": "AI / ML", "auth": "Auth & security", "infra": "Infrastructure",
    "library": "Libraries", "tool": "Tooling",
}  # fmt: skip
MAX_LISTED = 25
EVIDENCE_CONTEXT_LINES = 3


@dataclass
class GraphAnswer:
    text: str
    sources: list[ChatSource] = field(default_factory=list)


class _Citer:
    """Numbers evidence as sources, reusing a number when the same line is cited twice."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.sources: list[ChatSource] = []
        self._seen: dict[tuple, int] = {}

    async def cite(self, evidence: Evidence) -> int:
        key = (evidence.document_id, evidence.line, evidence.evidence)
        if key in self._seen:
            return self._seen[key]
        content = evidence.evidence or ""
        start = end = evidence.line
        chunk_id = evidence.chunk_ids[0] if evidence.chunk_ids else None
        if chunk_id is not None:
            chunk = await self.session.get(Chunk, chunk_id)
            if chunk is not None:  # show the manifest around the line, not just the line
                content, start, end = _window(chunk, evidence.line)
        n = len(self.sources) + 1
        self.sources.append(
            ChatSource(
                n=n,
                kind="evidence",
                chunk_id=chunk_id,
                document_id=evidence.document_id,
                source_name=evidence.source_name,
                path=evidence.path,
                start_line=start,
                end_line=end,
                symbol=f"line {evidence.line}" if evidence.line else None,
                content=content,
                score=evidence.confidence,
            )
        )
        self._seen[key] = n
        return n


def _window(chunk: Chunk, line: int | None) -> tuple[str, int | None, int | None]:
    """A few lines either side of the cited line, so it is in view without scrolling."""
    if line is None or chunk.start_line is None:
        return chunk.content, chunk.start_line, chunk.end_line
    lines = chunk.content.split("\n")
    at = line - chunk.start_line
    lo, hi = max(0, at - EVIDENCE_CONTEXT_LINES), min(len(lines), at + EVIDENCE_CONTEXT_LINES + 1)
    return "\n".join(lines[lo:hi]), chunk.start_line + lo, chunk.start_line + hi - 1


def _best(evidence: list[Evidence]) -> Evidence:
    return min(evidence, key=lambda e: (EXTRACTOR_RANK.get(e.extractor, 9), -e.confidence))


def _describe(evidence: Evidence) -> str:
    file = (evidence.path or "").rsplit("/", 1)[-1]
    if evidence.extractor == "language":
        return evidence.evidence or ""
    if evidence.extractor == "import":
        return f"imported in `{file}`"
    if evidence.extractor in ("docker", "compose", "manifest") and evidence.line is None:
        return f"`{file}`"
    return f"`{evidence.evidence}` in `{file}`"


async def projects_using(session: AsyncSession, entities: list[Entity]) -> GraphAnswer:
    citer = _Citer(session)
    paragraphs = []
    for entity in entities:
        projects = await queries.projects_using(session, entity)
        noun = "project" if len(projects) == 1 else "projects"
        if not projects:
            paragraphs.append(
                f"No indexed project declares, imports or runs **{entity.name}** (checked: "
                "dependency manifests, Dockerfiles, compose files and imports)."
            )
        else:
            lines = [f"**{entity.name}** is used in {len(projects)} {noun}:", ""]
            for project in projects[:MAX_LISTED]:
                best = _best(project.evidence)
                n = await citer.cite(best)
                extra = len({(e.document_id, e.line) for e in project.evidence}) - 1
                more = f" (+{extra} more)" if extra > 0 else ""
                dev = " (dev only)" if all(e.meta.get("dev") for e in project.evidence) else ""
                lines.append(f"- **{project.name}**{dev}: {_describe(best)} [{n}]{more}")
            if len(projects) > MAX_LISTED:
                lines.append(f"- … and {len(projects) - MAX_LISTED} more")
            paragraphs.append("\n".join(lines))
        notes = await queries.notes_mentioning(session, entity.id)
        if notes:
            cited = []
            for note in notes[:10]:
                cited.append(f"**{note.name}** [{await citer.cite(_best(note.evidence))}]")
            paragraphs.append(f"Notes that mention {entity.name}: " + ", ".join(cited) + ".")
    return GraphAnswer("\n\n".join(paragraphs), citer.sources)


def _group(technologies: list[Related]) -> dict[str, list[Related]]:
    groups: dict[str, list[Related]] = {}
    for tech in sorted(technologies, key=lambda t: t.name.lower()):
        groups.setdefault(tech.meta.get("category") or "library", []).append(tech)
    return dict(sorted(groups.items(), key=lambda kv: CATEGORY_ORDER.get(kv[0], 99)))


async def project_stack(session: AsyncSession, entities: list[Entity]) -> GraphAnswer:
    citer = _Citer(session)
    paragraphs = []
    for entity in entities:
        project = await session.get(Node, entity.id)
        if project is None:
            continue
        stack = await queries.project_stack(session, entity.id)
        lines = [f"**{project.name}**"]
        if not stack["technologies"]:
            lines.append("No technologies were detected (no manifest or code files).")
        for category, items in _group(stack["technologies"]).items():
            cited = []
            for tech in items:
                cited.append(f"{tech.name} [{await citer.cite(_best(tech.evidence))}]")
            lines.append(f"- {CATEGORY_LABEL.get(category, category)}: " + ", ".join(cited))
        if stack["packages"]:
            lines.append(f"- {len(stack['packages'])} declared dependencies in total")
        if stack["depends_on"]:
            names = ", ".join(p.name for p in stack["depends_on"])
            lines.append(f"- Depends on your own: {names}")
        if stack["authors"]:
            names = ", ".join(
                f"{a.name} ({a.evidence[0].meta.get('commits', '?')} commits)"
                for a in stack["authors"][:5]
            )
            lines.append(f"- Commits by: {names}")
        if stack["notes"]:
            cited = [f"{n.name} [{await citer.cite(_best(n.evidence))}]" for n in stack["notes"]]
            lines.append("- Mentioned in notes: " + ", ".join(cited))
        paragraphs.append("\n".join(lines))
    return GraphAnswer("\n\n".join(paragraphs), citer.sources)


async def resolve(session: AsyncSession, kind: str, subject: str) -> list[Entity]:
    """Entities for a graph intent: technologies/packages for 'which projects use X', projects
    for 'what does P use'. Empty means the question goes to RAG instead."""
    if kind == "graph_projects":
        entities = await queries.resolve_entities(session, subject, ("technology", "package"))
        # "Which projects use auth-service?" means depends_on another project.
        if not entities:
            entities = await queries.resolve_entities(session, subject, ("project",))
        return entities
    return await queries.resolve_entities(session, subject, ("project",))


async def project_scope(session: AsyncSession, question: str) -> Node | None:
    """The one project a RAG question names, if exactly one: used to softly scope search."""
    entities = await queries.resolve_entities(session, question, ("project",))
    if len(entities) != 1:
        return None
    return (await session.execute(select(Node).where(Node.id == entities[0].id))).scalar_one()
