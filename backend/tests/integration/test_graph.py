"""The deterministic knowledge graph built from the fixture corpus, against real Postgres."""

import shutil

import pytest
from sqlalchemy import func, select
from sqlalchemy import text as text_sql

from app.config import settings
from app.db.models import Edge, Node, Source
from app.services.graph import queries
from app.services.ingestion.pipeline import Pipeline, start_run


@pytest.fixture
def sources_root(tmp_path, corpus, monkeypatch):
    root = tmp_path / "sources"
    shutil.copytree(corpus, root / "fixture")
    monkeypatch.setattr(settings, "sources_root", str(root))
    return root


async def index(sessions, name="fixture"):
    async with sessions() as session:
        source = (
            await session.execute(select(Source).where(Source.name == name))
        ).scalar_one_or_none()
        if source is None:
            source = Source(name=name, kind="local", uri=name)
            session.add(source)
            await session.commit()
        run_id = await start_run(session, source.id)
    return source.id, await Pipeline(sessions, source.id, run_id).run()


async def stack(session, project_name: str) -> dict[str, set[str]]:
    project = (
        await session.execute(select(Node).where(Node.kind == "project", Node.name == project_name))
    ).scalar_one()
    result = await queries.project_stack(session, project.id)
    return {
        "technologies": {t.name for t in result["technologies"]},
        "packages": {p.name for p in result["packages"]},
        "notes": {n.name for n in result["notes"]},
    }


async def test_projects_and_stacks(sessions, sources_root):
    _, stats = await index(sessions)
    assert stats["graph"]["projects"] == 5
    async with sessions() as session:
        names = set(
            (await session.execute(select(Node.name).where(Node.kind == "project"))).scalars()
        )
        assert names == {"auth-service", "task-board", "link-checker", "vecstore", "inventory-api"}

        auth = await stack(session, "auth-service")
        # asyncpg -> PostgreSQL and python-jose -> JWT are aliases, not string matches.
        assert {"Python", "FastAPI", "PostgreSQL", "Redis", "SQLAlchemy", "JWT", "Argon2"} <= (
            auth["technologies"]
        )
        assert "asyncpg" in auth["packages"]
        # Notes that link to the project with a [[wikilink]].
        assert "Student Portal architecture" in auth["notes"]

        board = await stack(session, "task-board")
        assert {"TypeScript", "React", "Zustand", "Vite", "Vitest"} <= board["technologies"]
        assert "PostgreSQL" not in board["technologies"]

        inventory = await stack(session, "inventory-api")
        assert {"Java", "Spring Boot", "PostgreSQL", "Maven"} <= inventory["technologies"]

        assert "Rust" in (await stack(session, "vecstore"))["technologies"]
        assert "Go" in (await stack(session, "link-checker"))["technologies"]


async def test_which_projects_use_postgres(sessions, sources_root):
    await index(sessions)
    async with sessions() as session:
        [entity] = await queries.resolve_entities(session, "postgres")
        assert (entity.kind, entity.name) == ("technology", "PostgreSQL")
        projects = await queries.projects_using(session, entity)
        assert [p.name for p in projects] == ["auth-service", "inventory-api"]
        auth = projects[0]
        manifest = [e for e in auth.evidence if e.extractor == "manifest"]
        assert manifest and manifest[0].path == "repos/auth-service/pyproject.toml"
        assert manifest[0].evidence == "asyncpg>=0.29" and manifest[0].line is not None
        # Evidence points into the index: the chunk holding that manifest line.
        assert manifest[0].chunk_ids


async def test_every_edge_has_provenance_and_rebuild_is_idempotent(sessions, sources_root):
    source_id, _ = await index(sessions)
    async with sessions() as session:
        edges_before = await session.scalar(select(func.count()).select_from(Edge))
        nodes_before = await session.scalar(select(func.count()).select_from(Node))
        # Git authorship aside (no file), every edge names the document it came from.
        orphans = await session.scalar(
            select(func.count())
            .select_from(Edge)
            .where(Edge.document_id.is_(None), Edge.extractor != "git")
        )
        assert orphans == 0

    # A re-index with nothing changed rebuilds the graph to the same thing.
    await index(sessions)
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(Edge)) == edges_before
        assert await session.scalar(select(func.count()).select_from(Node)) == nodes_before

    # Deleting the source takes its projects, notes and edges with it, and shared nodes
    # nothing points at any more are pruned on the next build.
    async with sessions() as session:
        await session.delete(await session.get(Source, source_id))
        await session.commit()
        assert await session.scalar(select(func.count()).select_from(Edge)) == 0
        owned = await session.scalar(
            select(func.count()).select_from(Node).where(Node.source_id.is_not(None))
        )
        assert owned == 0


async def test_resolve_entities_prefers_longest_match(sessions, sources_root):
    await index(sessions)
    async with sessions() as session:
        entities = await queries.resolve_entities(session, "projects with spring boot")
        assert [e.name for e in entities] == ["Spring Boot"]
        entities = await queries.resolve_entities(session, "the auth-service project")
        assert [(e.kind, e.name) for e in entities] == [("project", "auth-service")]
        assert await queries.resolve_entities(session, "nothing relevant here") == []


async def test_neighbourhood(sessions, sources_root):
    await index(sessions)
    async with sessions() as session:
        project = (
            await session.execute(
                select(Node).where(Node.kind == "project", Node.name == "auth-service")
            )
        ).scalar_one()
        ego = await queries.neighbourhood(session, project.id, depth=1, limit=50)
        names = {n["name"] for n in ego["nodes"]}
        assert {"auth-service", "FastAPI", "PostgreSQL", "Student Portal architecture"} <= names
        assert all(e["src"] == project.id or e["dst"] == project.id for e in ego["edges"])
        assert len(ego["nodes"]) <= 50


async def test_llm_concepts_are_verified_cached_and_kept_across_rebuilds(
    sessions, sources_root, monkeypatch
):
    from app.schemas.extraction import ConceptExtraction, ExtractedConcept
    from app.services.graph import concepts

    source_id, _ = await index(sessions)
    first = await concepts.extract_concepts(sessions, source_id)
    assert first.chunks > 0 and first.called == first.chunks and first.cached == 0
    assert first.edges > 0 and first.stopped is None
    async with sessions() as session:
        llm = (await session.execute(select(Edge).where(Edge.extractor == "llm"))).scalars().all()
        # Provenance on every LLM edge: the chunk, the document, the model and prompt.
        assert all(e.chunk_ids and e.document_id and e.confidence == 0.7 for e in llm)
        assert all(e.meta["prompt"] == "concepts.v1" for e in llm)
        count = len(llm)

    # Unchanged text is never sent to a model twice.
    second = await concepts.extract_concepts(sessions, source_id)
    assert second.called == 0 and second.cached == first.chunks and second.edges == count

    # A deterministic rebuild (re-index) leaves the LLM layer alone.
    await index(sessions)
    async with sessions() as session:
        kept = await session.scalar(
            select(func.count()).select_from(Edge).where(Edge.extractor == "llm")
        )
        assert kept == count

    # A quote the text does not contain is a hallucination: dropped, not written.
    async def invented(target, prompt_text):
        return ConceptExtraction(
            concepts=[ExtractedConcept(name="Quantum", kind="concept", evidence="qubits galore")]
        ), "stub"

    async with sessions() as session:
        await session.execute(Edge.__table__.delete().where(Edge.extractor == "llm"))
        await session.execute(text_sql("TRUNCATE llm_extractions"))
        await session.commit()
    monkeypatch.setattr(concepts, "_extract_one", invented)
    third = await concepts.extract_concepts(sessions, source_id)
    assert third.edges == 0 and third.dropped_unverified == third.chunks
