"""Deterministic graph extraction: what a source's files say for certain, with provenance.

  folders + manifests  -> Project nodes
  manifests            -> Project -depends_on-> Package, Project -uses-> Technology
  Dockerfile, compose  -> Project -uses-> Technology (images: postgres -> PostgreSQL)
  file languages       -> Project -uses-> Technology (Python, TypeScript, ...)
  imports              -> Project -uses-> Technology (only curated technologies)
  git log              -> Person -authored-> Project
  notes                -> Note -links_to-> Note, Note -mentions-> Project/Technology
                          (wikilinks), Note -tagged-> Topic

No LLM is involved, so every edge is exact and costs nothing. Extraction is a pure function
of the documents (run in a thread); persistence replaces the source's deterministic edges in
one transaction, so a rebuild is idempotent and never leaves a half-built graph visible.
LLM-extracted edges (services/graph/concepts.py) are kept across rebuilds.
"""

import asyncio
import logging
import os
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from sqlalchemy import delete, exists, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Chunk, Document, Edge, Node, Source
from app.services.graph import technologies
from app.services.graph.imports import modules_in
from app.services.graph.manifests import Manifest, find_line, manifest_kind, parse_manifest
from app.services.graph.technologies import Tech, normalize, normalize_package
from app.services.ingestion import git

log = logging.getLogger(__name__)

# Manifests that make their folder a project. A Dockerfile or compose file alone does not:
# `docker/Dockerfile` is part of a project, not one.
ROOT_MANIFESTS = {
    "pyproject", "requirements", "pipfile", "setup.py", "package.json", "composer", "go.mod",
    "cargo", "maven", "gradle", "gemfile",
}  # fmt: skip
# Folder names that say nothing on their own: `frontend` becomes `myapp/frontend`.
GENERIC_DIRS = {
    "app", "api", "backend", "frontend", "client", "server", "web", "src", "service",
    "services", "packages", "apps", "lib", "core", "ui", "site", "docs", "www",
}  # fmt: skip
# A language counts as part of a project's stack above this share of its code files
# (or this many files): one helper script does not make a Go project a Bash project.
LANGUAGE_MIN_SHARE = 0.1
LANGUAGE_MIN_FILES = 5
IMPORT_CONFIDENCE = 0.9
GRAPH_LOCK = 0x6D656D6F  # advisory lock id: one graph writer at a time

# Deterministic extractors; everything else (llm) survives a rebuild.
DETERMINISTIC = (
    "manifest", "import", "docker", "compose", "language", "git", "wikilink", "tag",
)  # fmt: skip

NodeKey = tuple[str, str]  # (kind, key)


@dataclass
class NodeDraft:
    kind: str
    key: str
    name: str
    source_id: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EdgeDraft:
    src: NodeKey
    dst: NodeKey
    type: str
    extractor: str
    evidence: str | None = None
    document_id: int | None = None
    line: int | None = None
    confidence: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class DocInfo:
    id: int
    path: str
    kind: str
    language: str | None
    title: str | None
    meta: dict[str, Any]


@dataclass
class GraphDraft:
    nodes: dict[NodeKey, NodeDraft] = field(default_factory=dict)
    edges: list[EdgeDraft] = field(default_factory=list)

    def node(self, draft: NodeDraft) -> NodeKey:
        key = (draft.kind, draft.key)
        existing = self.nodes.get(key)
        if existing is None:
            self.nodes[key] = draft
        else:
            existing.meta.update({k: v for k, v in draft.meta.items() if k not in existing.meta})
        return key

    def tech(self, tech: Tech) -> NodeKey:
        return self.node(
            NodeDraft("technology", tech.key, tech.name, meta={"category": tech.category})
        )


def project_key(source_id: int, root: str) -> str:
    return f"{source_id}:{root}"


def package_key(ecosystem: str, name: str) -> str:
    return f"{ecosystem}:{normalize_package(ecosystem, name)}"


def _contains(root: str, path: str) -> bool:
    return root == "" or path == root or path.startswith(root + "/")


def _dirname(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "" if parent == "." else parent


# --------------------------------------------------------------------------- extraction


@dataclass
class Project:
    root: str
    key: NodeKey
    name: str
    manifests: list[Manifest] = field(default_factory=list)


def find_project_roots(
    documents: list[DocInfo], manifests: dict[str, Manifest], repo_roots: list[str]
) -> list[str]:
    """Git working trees are projects. Outside them, the shallowest folder holding a root
    manifest is. A source with code but neither is one project."""
    roots = sorted(set(repo_roots), key=lambda r: (r.count("/"), r))
    candidates = sorted(
        {_dirname(path) for path, m in manifests.items() if m.kind in ROOT_MANIFESTS},
        key=lambda r: (r.count("/") if r else -1, r),
    )
    for candidate in candidates:
        if not any(_contains(root, candidate) for root in roots):
            roots.append(candidate)
    if not roots and any(d.kind == "code" for d in documents):
        roots.append("")
    return roots


def _project_name(root: str, manifests: list[Manifest], source_name: str) -> str:
    for manifest in manifests:
        if _dirname(manifest.path) == root and manifest.project_name:
            return manifest.project_name
    if root == "":
        return source_name
    parts = root.split("/")
    if parts[-1].lower() in GENERIC_DIRS:
        parent = parts[-2] if len(parts) > 1 else source_name
        return f"{parent}/{parts[-1]}"
    return parts[-1]


def extract(
    source_id: int,
    source_name: str,
    documents: list[DocInfo],
    read_text: Callable[[str], str | None],
    repo_roots: list[str],
    authors_of: Callable[[str], list[git.AuthorStats]] | None = None,
) -> GraphDraft:
    """Everything the documents say for certain, as nodes and edges with provenance."""
    graph = GraphDraft()
    docs_by_path = {d.path: d for d in documents}

    manifests: dict[str, Manifest] = {}
    for doc in documents:
        if manifest_kind(doc.path) is None:
            continue
        text = read_text(doc.path)
        manifest = parse_manifest(doc.path, text) if text is not None else None
        if manifest is not None:
            manifests[doc.path] = manifest

    roots = find_project_roots(documents, manifests, repo_roots)
    projects: list[Project] = []
    for root in roots:
        own = [m for p, m in manifests.items() if _contains(root, p)]
        name = _project_name(root, own, source_name)
        key = graph.node(
            NodeDraft(
                "project",
                project_key(source_id, root),
                name,
                source_id,
                {"root": root, "manifests": sorted(m.path for m in own)},
            )
        )
        projects.append(Project(root, key, name))

    def owner(path: str) -> Project | None:
        best = None
        for project in projects:
            if _contains(project.root, path) and (
                best is None or len(project.root) > len(best.root)
            ):
                best = project
        return best

    for path, manifest in manifests.items():
        project = owner(path)
        if project is not None:
            project.manifests.append(manifest)

    package_names = {  # local package name -> project, for project-to-project dependencies
        normalize(p.name): p for p in projects
    }

    for project in projects:
        _manifest_edges(graph, project, docs_by_path, package_names)
    _language_edges(graph, projects, documents, owner)
    _import_edges(graph, documents, owner, read_text)
    if authors_of is not None:
        _author_edges(graph, projects, authors_of)
    _note_edges(graph, source_id, documents, owner, read_text, projects)
    return graph


def _manifest_edges(
    graph: GraphDraft,
    project: Project,
    docs: dict[str, DocInfo],
    local_packages: dict[str, Project],
) -> None:
    for manifest in project.manifests:
        document_id = docs[manifest.path].id if manifest.path in docs else None
        for name in manifest.implies:
            graph.edges.append(
                EdgeDraft(
                    project.key,
                    graph.tech(technologies.get(name)),
                    "uses",
                    "docker" if manifest.kind in ("dockerfile", "compose") else "manifest",
                    PurePosixPath(manifest.path).name,
                    document_id,
                    None,
                )
            )
        for dep in manifest.dependencies:
            local = local_packages.get(normalize(dep.name))
            if local is not None and local is not project:
                graph.edges.append(
                    EdgeDraft(
                        project.key,
                        local.key,
                        "depends_on",
                        "manifest",
                        dep.spec,
                        document_id,
                        dep.line,
                        meta={"dev": dep.dev},
                    )
                )
                continue
            package = graph.node(
                NodeDraft(
                    "package",
                    package_key(dep.ecosystem, dep.name),
                    dep.name,
                    meta={"ecosystem": dep.ecosystem},
                )
            )
            graph.edges.append(
                EdgeDraft(
                    project.key,
                    package,
                    "depends_on",
                    "manifest",
                    dep.spec,
                    document_id,
                    dep.line,
                    meta={"dev": dep.dev},
                )
            )
            for tech in technologies.by_package(dep.ecosystem, dep.name):
                graph.edges.append(
                    EdgeDraft(
                        project.key,
                        graph.tech(tech),
                        "uses",
                        "manifest",
                        dep.spec,
                        document_id,
                        dep.line,
                        meta={"dev": dep.dev, "via": dep.name},
                    )
                )
        for image in manifest.images:
            for tech in technologies.by_image(image.image):
                graph.edges.append(
                    EdgeDraft(
                        project.key,
                        graph.tech(tech),
                        "uses",
                        "compose" if manifest.kind == "compose" else "docker",
                        image.evidence,
                        document_id,
                        image.line,
                        meta={"image": image.image},
                    )
                )


def _language_edges(graph, projects, documents, owner) -> None:
    files: dict[NodeKey, Counter[str]] = defaultdict(Counter)
    first: dict[tuple[NodeKey, str], DocInfo] = {}
    for doc in sorted(documents, key=lambda d: d.path):
        if doc.kind != "code" or not doc.language:
            continue
        tech = technologies.language_tech(doc.language)
        project = owner(doc.path)
        if tech is None or project is None:
            continue
        files[project.key][tech.name] += 1
        first.setdefault((project.key, tech.name), doc)
    for pkey, counts in files.items():
        total = sum(counts.values())
        for name, count in counts.items():
            if count >= LANGUAGE_MIN_FILES or count / total >= LANGUAGE_MIN_SHARE:
                noun = "file" if count == 1 else "files"
                graph.edges.append(
                    EdgeDraft(
                        pkey,
                        graph.tech(technologies.get(name)),
                        "uses",
                        "language",
                        f"{count} {name} {noun}",
                        first[(pkey, name)].id,
                        meta={"files": count, "share": round(count / total, 3)},
                    )
                )


def _import_edges(graph, documents, owner, read_text) -> None:
    # One edge per (project, technology): the first file that imports it, and a count.
    found: dict[tuple[NodeKey, str], dict[str, Any]] = {}
    for doc in sorted(documents, key=lambda d: d.path):
        statements = doc.meta.get("imports") if doc.kind == "code" else None
        project = owner(doc.path)
        if not statements or project is None:
            continue
        seen_here: set[str] = set()
        for statement in statements:
            for module in modules_in(statement, doc.language or ""):
                for tech in technologies.by_module(doc.language or "", module):
                    if tech.name in seen_here:
                        continue
                    seen_here.add(tech.name)
                    entry = found.setdefault(
                        (project.key, tech.name),
                        {"tech": tech, "doc": doc, "statement": statement, "files": 0},
                    )
                    entry["files"] += 1
    texts: dict[str, str | None] = {}
    for (pkey, _), entry in found.items():
        doc: DocInfo = entry["doc"]
        if doc.path not in texts:
            texts[doc.path] = read_text(doc.path)
        content = texts[doc.path]
        line = find_line(content, entry["statement"]) if content else None
        graph.edges.append(
            EdgeDraft(
                pkey,
                graph.tech(entry["tech"]),
                "uses",
                "import",
                entry["statement"],
                doc.id,
                line,
                IMPORT_CONFIDENCE,
                meta={"files": entry["files"]},
            )
        )


def _author_edges(graph, projects, authors_of) -> None:
    for project in projects:
        for author in authors_of(project.root):
            person = graph.node(
                NodeDraft(
                    "person",
                    (author.email or author.name).lower(),
                    author.name,
                    meta={"email": author.email},
                )
            )
            graph.edges.append(
                EdgeDraft(
                    person,
                    project.key,
                    "authored",
                    "git",
                    f"{author.commits} commit{'s' if author.commits != 1 else ''}",
                    meta={
                        "commits": author.commits,
                        "first": author.first.isoformat(),
                        "last": author.last.isoformat(),
                    },
                )
            )


def _note_edges(graph, source_id, documents, owner, read_text, projects) -> None:
    notes = [d for d in documents if d.kind == "markdown" and owner(d.path) is None]
    if not notes:
        return
    by_title: dict[str, NodeKey] = {}
    note_keys: dict[int, NodeKey] = {}
    for doc in notes:
        key = graph.node(
            NodeDraft(
                "note",
                f"{source_id}:{doc.path}",
                doc.title or PurePosixPath(doc.path).stem,
                source_id,
                {"document_id": doc.id, "path": doc.path},
            )
        )
        note_keys[doc.id] = key
        by_title.setdefault(normalize(PurePosixPath(doc.path).stem), key)
        if doc.title:
            by_title.setdefault(normalize(doc.title), key)
    project_names = {normalize(p.name): p.key for p in projects}

    for doc in notes:
        note = note_keys[doc.id]
        links = doc.meta.get("links") or []
        content = read_text(doc.path) if links else None
        for target in links:
            normalized = normalize(target)
            line = find_line(content, f"[[{target}") if content else None
            destination, type_ = None, "mentions"
            if normalized in by_title and by_title[normalized] != note:
                destination, type_ = by_title[normalized], "links_to"
            elif normalized in project_names:
                destination = project_names[normalized]
            elif (tech := technologies.by_name(target)) is not None:
                destination = graph.tech(tech)
            if destination is not None:
                graph.edges.append(
                    EdgeDraft(note, destination, type_, "wikilink", f"[[{target}]]", doc.id, line)
                )
        for tag in doc.meta.get("tags") or []:
            # `#postgres` is PostgreSQL, not a topic that happens to share its name.
            if (tech := technologies.by_name(tag)) is not None:
                graph.edges.append(
                    EdgeDraft(note, graph.tech(tech), "mentions", "tag", f"#{tag}", doc.id)
                )
                continue
            topic = graph.node(NodeDraft("topic", tag.lower(), tag))
            graph.edges.append(EdgeDraft(note, topic, "tagged", "tag", f"#{tag}", doc.id))


# --------------------------------------------------------------------------- persistence


async def _upsert_nodes(session: AsyncSession, drafts: list[NodeDraft]) -> dict[NodeKey, int]:
    ids: dict[NodeKey, int] = {}
    for start in range(0, len(drafts), 500):
        batch = drafts[start : start + 500]
        stmt = pg_insert(Node).values(
            [
                {"kind": d.kind, "key": d.key, "name": d.name, "source_id": d.source_id,
                 "meta": d.meta}
                for d in batch
            ]
        )  # fmt: skip
        stmt = stmt.on_conflict_do_update(
            constraint="uq_nodes_kind",
            set_={
                "name": stmt.excluded.name,
                "meta": stmt.excluded.meta,
                "source_id": stmt.excluded.source_id,
                "updated_at": text("now()"),
            },
        ).returning(Node.id, Node.kind, Node.key)
        for row in (await session.execute(stmt)).all():
            ids[(row.kind, row.key)] = row.id
    return ids


def _chunk_for_line(spans: list[tuple[int, int | None, int | None]], line: int | None) -> list[int]:
    if line is None:
        return []
    for chunk_id, start, end in spans:
        if start is not None and end is not None and start <= line <= end:
            return [chunk_id]
    return []


async def persist(session: AsyncSession, source_id: int, graph: GraphDraft) -> dict[str, int]:
    """Replace the source's deterministic graph with `graph`. Caller commits."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": GRAPH_LOCK})
    ids = await _upsert_nodes(session, list(graph.nodes.values()))

    doc_ids = {e.document_id for e in graph.edges if e.document_id is not None and e.line}
    spans: dict[int, list] = defaultdict(list)
    if doc_ids:
        for row in (
            await session.execute(
                select(Chunk.id, Chunk.document_id, Chunk.start_line, Chunk.end_line).where(
                    Chunk.document_id.in_(doc_ids)
                )
            )
        ).all():
            spans[row.document_id].append((row.id, row.start_line, row.end_line))

    await session.execute(
        delete(Edge).where(Edge.source_id == source_id, Edge.extractor.in_(DETERMINISTIC))
    )
    rows, seen = [], set()
    for e in graph.edges:
        identity = (e.src, e.dst, e.type, e.extractor, e.document_id, e.line, e.evidence)
        if identity in seen or e.src == e.dst:
            continue
        seen.add(identity)
        rows.append(
            {
                "src_id": ids[e.src],
                "dst_id": ids[e.dst],
                "type": e.type,
                "source_id": source_id,
                "document_id": e.document_id,
                "line": e.line,
                "chunk_ids": _chunk_for_line(spans.get(e.document_id or 0, []), e.line),
                "evidence": (e.evidence or "")[:500] or None,
                "extractor": e.extractor,
                "confidence": e.confidence,
                "meta": e.meta,
            }
        )
    for start in range(0, len(rows), 1000):
        await session.execute(pg_insert(Edge), rows[start : start + 1000])

    # Projects and notes that no longer exist in the source; their LLM edges go with them.
    owned = [i for (kind, _), i in ids.items() if kind in ("project", "note")]
    await session.execute(
        delete(Node).where(Node.source_id == source_id, Node.id.not_in(owned or [0]))
    )
    await prune_orphans(session)
    return {
        "projects": sum(1 for k in graph.nodes if k[0] == "project"),
        "notes": sum(1 for k in graph.nodes if k[0] == "note"),
        "technologies": len({e.dst for e in graph.edges if e.dst[0] == "technology"}),
        "edges": len(rows),
    }


async def prune_orphans(session: AsyncSession) -> None:
    """Shared nodes (technologies, packages, people, topics) that nothing points at."""
    await session.execute(
        delete(Node).where(
            Node.source_id.is_(None),
            ~exists().where(or_(Edge.src_id == Node.id, Edge.dst_id == Node.id)),
        )
    )


# --------------------------------------------------------------------------- entry point


def _author_resolver(root: Path, repo_roots: list[str]) -> Callable[[str], list[git.AuthorStats]]:
    """Maps a project root (relative to the source) to `git log` of the right repository."""
    outer = None if "" in repo_roots else git.toplevel(root)

    def authors_of(project_root: str) -> list[git.AuthorStats]:
        repos = sorted(repo_roots, key=len, reverse=True)
        for repo_rel in repos:
            if _contains(repo_rel, project_root):
                sub = project_root[len(repo_rel) :].lstrip("/")
                return git.authors(root / repo_rel if repo_rel else root, sub)
        if outer is not None:
            target = (root / project_root).resolve() if project_root else root.resolve()
            sub = os.path.relpath(target, outer.resolve()).replace(os.sep, "/")
            return git.authors(outer, "" if sub == "." else sub)
        return []

    return authors_of


async def load_documents(session: AsyncSession, source_id: int) -> list[DocInfo]:
    rows = (
        await session.execute(
            select(
                Document.id,
                Document.path,
                Document.kind,
                Document.language,
                Document.title,
                Document.meta,
            ).where(Document.source_id == source_id, Document.status == "indexed")
        )
    ).all()
    return [DocInfo(r.id, r.path, r.kind, r.language, r.title, r.meta or {}) for r in rows]


async def build_source_graph(
    sessions: async_sessionmaker[AsyncSession],
    source_id: int,
    root: Path,
    repo_roots: list[str],
    with_authors: bool = True,
) -> dict[str, int]:
    """Rebuild the deterministic graph of one indexed source from its files on disk."""
    async with sessions() as session:
        source = await session.get(Source, source_id)
        if source is None:
            raise ValueError(f"source {source_id} does not exist")
        source_name = source.name
        documents = await load_documents(session, source_id)

    def read_text(path: str) -> str | None:
        try:
            return (root / path).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            return None

    authors_of = _author_resolver(root, repo_roots) if with_authors else None
    graph = await asyncio.to_thread(
        extract, source_id, source_name, documents, read_text, repo_roots, authors_of
    )
    async with sessions() as session:
        stats = await persist(session, source_id, graph)
        await session.commit()
    log.info("graph for source %s: %s", source_id, stats)
    return stats
