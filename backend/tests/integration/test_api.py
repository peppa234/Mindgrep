"""HTTP API with the database pointed at the test database and a fake job queue."""

import shutil
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db.models import Source
from app.deps import get_arq, get_session
from app.main import app
from app.services.ingestion.pipeline import Pipeline, start_run


@dataclass
class FakeJob:
    job_id: str


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, *args))
        return FakeJob(kwargs.get("_job_id", name))


@pytest.fixture
async def client(sessions, tmp_path, corpus, monkeypatch):
    root = tmp_path / "sources"
    shutil.copytree(corpus / "notes", root / "notes")
    monkeypatch.setattr(settings, "sources_root", str(root))
    queue = FakeQueue()

    async def session_override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_arq] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        http.queue = queue  # type: ignore[attr-defined]
        yield http
    app.dependency_overrides.clear()


async def test_register_local_source_enqueues_indexing(client):
    response = await client.post(
        "/api/v1/sources", json={"name": "notes", "kind": "local", "uri": "notes"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["latest_run"]["status"] == "queued"
    assert client.queue.jobs == [("index_source", body["id"], body["latest_run"]["id"])]

    duplicate = await client.post(
        "/api/v1/sources", json={"name": "notes", "kind": "local", "uri": "notes"}
    )
    assert duplicate.status_code == 409

    busy = await client.post(f"/api/v1/sources/{body['id']}/index")
    assert busy.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "escape", "kind": "local", "uri": "../../etc"},
        {"name": "missing", "kind": "local", "uri": "does-not-exist"},
        {"name": "ssh", "kind": "git", "uri": "git@github.com:a/b.git"},
        {"name": "bad name!", "kind": "local", "uri": "notes"},
    ],
)
async def test_invalid_sources_are_rejected(client, payload):
    response = await client.post("/api/v1/sources", json=payload)
    assert response.status_code == 422
    assert client.queue.jobs == []


async def test_search_documents_and_stats(client, sessions):
    async with sessions() as session:
        source = Source(name="notes", kind="local", uri="notes")
        session.add(source)
        await session.commit()
        run_id = await start_run(session, source.id)
    await Pipeline(sessions, source.id, run_id).run()

    found = await client.get("/api/v1/search", params={"q": "deadlock lock order", "k": 3})
    assert found.status_code == 200
    top = found.json()["hits"][0]
    assert top["path"] == "journal/2024-03-12.md"  # relative to the source root
    assert top["source_name"] == "notes"

    document = await client.get(f"/api/v1/documents/{top['document_id']}")
    assert document.status_code == 200
    assert document.json()["chunks"][0]["embedded"] is True

    stats = (await client.get("/api/v1/stats")).json()
    assert stats["documents_by_kind"] == {"markdown": 13}
    assert stats["chunks"] == stats["embedded"] > 0

    listed = (await client.get("/api/v1/sources")).json()
    assert listed[0]["documents"] == 13 and listed[0]["status"] == "ready"

    async with sessions() as session:
        assert (await session.execute(select(Source.last_indexed_at))).scalar_one() is not None
    assert (await client.delete(f"/api/v1/sources/{source.id}")).status_code == 204
    assert (await client.get("/api/v1/sources")).json() == []
