"""The idea <-> implementation gap on the fixture corpus, against real Postgres: detection,
matching, the layers of status (user > note > matching), the graph, the API and the chat."""

import shutil

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.config import settings
from app.db.models import Edge, Idea, Node, Source
from app.deps import get_arq, get_session, get_sessionmaker
from app.main import app
from app.services.graph import queries
from app.services.ideas.service import match_all
from app.services.ingestion.pipeline import Pipeline, start_run
from tests.integration.test_api import FakeQueue
from tests.integration.test_chat import answer, ask


@pytest.fixture
def sources_root(tmp_path, corpus, monkeypatch):
    root = tmp_path / "sources"
    shutil.copytree(corpus, root / "fixture")
    monkeypatch.setattr(settings, "sources_root", str(root))
    return root


async def index(sessions) -> dict:
    async with sessions() as session:
        source = (
            await session.execute(select(Source).where(Source.name == "fixture"))
        ).scalar_one_or_none()
        if source is None:
            source = Source(name="fixture", kind="local", uri="fixture")
            session.add(source)
            await session.commit()
        run_id = await start_run(session, source.id)
    return await Pipeline(sessions, source.id, run_id).run()


async def by_title(sessions) -> dict[str, Idea]:
    async with sessions() as session:
        return {i.title: i for i in (await session.execute(select(Idea))).scalars()}


async def project_id(sessions, name: str) -> int:
    async with sessions() as session:
        return (
            await session.execute(select(Node.id).where(Node.kind == "project", Node.name == name))
        ).scalar_one()


@pytest.fixture
async def client(sessions, sources_root):
    await index(sessions)

    async def session_override():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_sessionmaker] = lambda: sessions
    queue = FakeQueue()
    app.dependency_overrides[get_arq] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        http.queue = queue  # type: ignore[attr-defined]
        yield http
    app.dependency_overrides.clear()


async def test_ideas_are_found_and_matched(sessions, sources_root):
    stats = await index(sessions)
    assert stats["ideas"]["found"] == 7 and stats["ideas"]["ideas"] == 7
    ideas = await by_title(sessions)
    link_checker = await project_id(sessions, "link-checker")

    crawler = ideas["Broken link crawler"]
    assert (crawler.status, crawler.implemented_by_id) == ("implemented", link_checker)
    assert crawler.effective == ("implemented", link_checker, "match")
    best = crawler.match["candidates"][0]
    assert best["project"] == "link-checker" and "robots.txt" in best["matched"]
    assert best["best_document"]["path"].startswith("repos/link-checker/")

    # Nothing in the code: unimplemented, with the words nobody has as the evidence.
    darija = ideas["RAG for Darija"]
    assert darija.effective == ("unimplemented", None, "match")
    assert "darija" in darija.match["missing"] and darija.implemented_by_id is None

    # The note's own frontmatter outranks matching...
    kanban = ideas["Kanban board for the study group"]
    assert kanban.effective == ("implemented", await project_id(sessions, "task-board"), "declared")
    habit = ideas["Habit tracker"]
    assert habit.effective == ("abandoned", None, "declared")
    # ...but matching still ran, and agrees for the kanban board.
    assert kanban.match["candidates"][0]["project"] == "task-board"

    changelog = next(i for i in ideas.values() if i.extractor == "inline")
    assert changelog.line == 10 and changelog.status == "unimplemented"
    # Lexical coverage alone does not see that vecstore is half of this idea (the reranker
    # does); the closest project is still the right one.
    vector = ideas["Vector database from scratch"]
    assert vector.match["candidates"][0]["project"] == "vecstore"


async def test_the_graph_links_notes_ideas_and_projects(sessions, sources_root):
    await index(sessions)
    ideas = await by_title(sessions)
    crawler = ideas["Broken link crawler"]
    async with sessions() as session:
        node = await session.get(Node, crawler.node_id)
        assert node.kind == "idea" and node.meta["status"] == "implemented"
        edges = {
            (e.type, e.extractor)
            for e in (
                await session.execute(
                    select(Edge).where((Edge.src_id == node.id) | (Edge.dst_id == node.id))
                )
            ).scalars()
        }
        assert edges == {("proposes", "idea"), ("implemented_by", "idea")}
        link_checker = await project_id(sessions, "link-checker")
        around = await queries.neighbourhood(session, link_checker)
        assert "Broken link crawler" in {n["name"] for n in around["nodes"]}
        # The walk can be limited to some kinds; the focal node is always there.
        only = await queries.neighbourhood(session, link_checker, depth=2, kinds=["idea", "note"])
        assert {(n["kind"], n["name"]) for n in only["nodes"]} == {
            ("project", "link-checker"),
            ("idea", "Broken link crawler"),
            ("note", "Broken link crawler"),
        }
        # implemented_by carries its evidence like every other edge: the closest code.
        [edge] = (
            (await session.execute(select(Edge).where(Edge.type == "implemented_by")))
            .scalars()
            .all()[:1]
        )
        assert edge.document_id is not None and edge.chunk_ids and "robots.txt" in edge.evidence
    # Rebuilding the deterministic graph keeps the idea nodes.
    await index(sessions)
    assert (await by_title(sessions))["Broken link crawler"].node_id is not None


async def test_an_override_survives_reindexing(sessions, sources_root):
    await index(sessions)
    darija = (await by_title(sessions))["RAG for Darija"]
    vecstore = await project_id(sessions, "vecstore")
    async with sessions() as session:
        idea = await session.get(Idea, darija.id)
        idea.user_status, idea.user_project_id = "partial", vecstore
        await session.commit()
    await index(sessions)
    again = (await by_title(sessions))["RAG for Darija"]
    assert again.id == darija.id
    assert again.effective == ("partial", vecstore, "user")
    assert again.status == "unimplemented"  # matching's own view is kept apart


async def test_a_deleted_idea_note_takes_its_idea_with_it(sessions, sources_root):
    await index(sessions)
    (sources_root / "fixture" / "notes" / "ideas" / "habit-tracker.md").unlink()
    stats = await index(sessions)
    assert stats["ideas"]["ideas"] == 6
    assert "Habit tracker" not in await by_title(sessions)
    async with sessions() as session:
        names = set((await session.execute(select(Node.name).where(Node.kind == "idea"))).scalars())
    assert "Habit tracker" not in names and len(names) == 6


async def test_thresholds_decide(sessions, sources_root, monkeypatch):
    await index(sessions)
    monkeypatch.setattr(settings, "idea_coverage_implemented", 0.99)
    await match_all(sessions)
    crawler = (await by_title(sessions))["Broken link crawler"]
    assert crawler.status == "partial"  # 0.67 clears partial (0.3) but not 0.99
    monkeypatch.setattr(settings, "idea_coverage_partial", 0.99)
    await match_all(sessions)
    crawler = (await by_title(sessions))["Broken link crawler"]
    assert crawler.status == "unimplemented" and crawler.implemented_by_id is None


async def test_ideas_api(client):
    ideas = (await client.get("/api/v1/ideas", params={"status": "unimplemented"})).json()
    titles = [i["title"] for i in ideas]
    # Oldest first.
    assert titles == [
        "Vector database from scratch",
        "Code review bot",
        "RAG for Darija",
        "A CLI that turns the git log of every repository into a weekly changelog",
    ]
    darija = next(i for i in ideas if i["title"] == "RAG for Darija")
    assert darija["origin"] == "match" and darija["chunk_id"] is not None
    assert darija["tags"] == ["idea", "nlp", "rag"] and "darija" in darija["missing"]

    closest = (await client.get("/api/v1/ideas", params={"sort": "closest"})).json()
    assert closest[0]["title"] == "Broken link crawler"

    vecstore = next(
        p["id"] for p in (await client.get("/api/v1/graph/projects")).json()
        if p["name"] == "vecstore"
    )  # fmt: skip
    marked = await client.put(
        f"/api/v1/ideas/{darija['id']}/override",
        json={"status": "implemented", "project_id": vecstore, "note": "prototype in vecstore"},
    )
    assert marked.status_code == 200, marked.text
    body = marked.json()
    assert (body["status"], body["origin"], body["project"]["name"]) == (
        "implemented",
        "user",
        "vecstore",
    )
    assert body["matched_status"] == "unimplemented"
    summary = (await client.get("/api/v1/ideas/summary")).json()
    assert summary["total"] == 7 and summary["by_status"]["implemented"] == 3

    # Abandoned carries no project, whatever the request says.
    dropped = await client.put(
        f"/api/v1/ideas/{darija['id']}/override",
        json={"status": "abandoned", "project_id": vecstore},
    )
    assert dropped.json()["project"] is None

    cleared = (await client.delete(f"/api/v1/ideas/{darija['id']}/override")).json()
    assert (cleared["status"], cleared["origin"]) == ("unimplemented", "match")

    bad = await client.put(
        f"/api/v1/ideas/{darija['id']}/override",
        json={"status": "implemented", "project_id": darija["document_id"] + 10_000},
    )
    assert bad.status_code == 422
    assert (await client.get("/api/v1/ideas/999999")).status_code == 404

    refresh = await client.post("/api/v1/ideas/refresh")
    assert refresh.status_code == 202 and client.queue.jobs[-1] == ("refresh_ideas",)


async def test_what_ai_ideas_have_i_never_implemented(client):
    text, sources, done = answer(await ask(client, "What AI ideas have I never implemented?"))
    assert done["intent"] == "ideas" and done["model"] == "graph"
    assert "Code review bot" in text and "RAG for Darija" in text
    assert "Broken link crawler" not in text and "Vector database" not in text
    assert "**2 of 2 ideas** about **AI**" in text
    assert {s["path"] for s in sources} == {
        "notes/ideas/code-review-bot.md",
        "notes/ideas/rag-for-darija.md",
    }
    assert done["citations"] == [1, 2]
    # The evidence against: words of the idea that no project contains.
    assert "darija" in text.lower()


async def test_which_ideas_did_i_build(client):
    text, _, done = answer(await ask(client, "Which of my ideas did I build?"))
    assert done["intent"] == "ideas"
    assert "Broken link crawler" in text and "**link-checker**" in text
    assert "Kanban board for the study group" in text and "its note says so" in text
    assert "RAG for Darija" not in text
