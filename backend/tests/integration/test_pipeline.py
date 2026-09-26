"""The indexing pipeline and search against a real Postgres, with the hashing embedder."""

import shutil

import pytest
from sqlalchemy import func, select, update

from app.config import settings
from app.db.models import Chunk, Document, Source
from app.schemas.search import SearchFilters, SearchRequest
from app.services.ingestion.pipeline import Pipeline, embed_pending, resolve_local, start_run
from app.services.retrieval.search import search


@pytest.fixture
def sources_root(tmp_path, corpus, monkeypatch):
    """A writable copy of the fixture corpus, mounted as the sources root."""
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


async def test_index_is_complete_and_idempotent(sessions, sources_root):
    source_id, first = await index(sessions)
    # go.mod and pom.xml are indexed as text so graph evidence always links to a document.
    assert first["files_total"] == 33
    assert first["indexed"] == 32
    assert first["needs_ocr"] == 1  # the scanned whiteboard PDF
    assert first["failed"] == 0
    assert first["embedded"] == first["chunks_written"] > 40
    assert first["documents_by_kind"] == {"code": 17, "markdown": 9, "pdf": 2, "text": 5}

    _, second = await index(sessions)
    assert second["unchanged"] == 33
    assert second["chunks_written"] == 0
    assert second["embedded"] == 0

    # Change one file, delete another: exactly that work is redone.
    target = sources_root / "fixture" / "repos" / "task-board" / "src" / "hooks" / "useDebounce.ts"
    target.write_text(target.read_text() + "\nexport const DEFAULT_DELAY_MS = 300;\n")
    (sources_root / "fixture" / "notes" / "cheatsheets" / "docker.md").unlink()
    _, third = await index(sessions)
    assert third["indexed"] == 1
    assert third["deleted"] == 1
    assert third["unchanged"] == 31
    async with sessions() as session:
        paths = set(
            (
                await session.execute(select(Document.path).where(Document.source_id == source_id))
            ).scalars()
        )
    assert "notes/cheatsheets/docker.md" not in paths


async def test_embeddings_from_another_model_are_replaced(sessions, sources_root):
    source_id, _ = await index(sessions)
    async with sessions() as session:
        await session.execute(
            update(Chunk).where(Chunk.ordinal == 0).values(embedding_model="old-model")
        )
        await session.commit()
    embedded, pending, warning = await embed_pending(sessions, source_id)
    assert embedded > 0 and pending == 0 and warning is None
    async with sessions() as session:
        stale = await session.scalar(
            select(func.count()).where(Chunk.embedding_model == "old-model")
        )
    assert stale == 0


async def test_search_modes_and_filters(sessions, sources_root):
    await index(sessions)

    async def run(q, **kwargs):
        async with sessions() as session:
            return await search(session, SearchRequest(q=q, **kwargs))

    exact = await run("create_access_token", mode="lexical")
    assert exact.hits[0].path == "repos/auth-service/app/security.py"
    assert "create_access_token" in exact.hits[0].symbols
    # Full-text alone ranks the login route (which calls it) close; the symbol channel pins it.
    assert exact.hits[0].ranks.get("symbol") == 1

    partial = await run("limit_login", mode="hybrid")
    assert "limit_login_attempts" in partial.hits[0].symbols
    assert "symbol" in partial.hits[0].ranks  # found by the trigram identifier channel

    hybrid = await run("exponential backoff retry", mode="hybrid", k=5)
    assert hybrid.mode == "hybrid" and not hybrid.degraded
    assert any("fetchWithRetry" in h.symbols for h in hybrid.hits)
    assert hybrid.hits[0].header.startswith("fixture/")

    notes_only = await run("postgres", k=20, filters=SearchFilters(doc_kinds=["markdown"]))
    assert notes_only.hits and all(h.doc_kind == "markdown" for h in notes_only.hits)

    in_repo = await run("token", k=20, filters=SearchFilters(path_prefix="repos/auth-service/"))
    assert in_repo.hits and all(h.path.startswith("repos/auth-service/") for h in in_repo.hits)

    # Without a reranker configured, auto falls back to hybrid rather than failing.
    auto = await run("jwt")
    assert auto.mode == "hybrid"

    rerank = await run("jwt", mode="rerank")
    assert rerank.degraded == ["rerank: no reranker configured"]


def test_local_paths_must_stay_inside_the_sources_root(sources_root):
    assert resolve_local("fixture") == (sources_root / "fixture").resolve()
    for bad in ("../../etc", "/etc", str(sources_root.parent)):
        with pytest.raises(ValueError):
            resolve_local(bad)
