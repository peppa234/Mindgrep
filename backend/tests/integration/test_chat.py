"""The chat API end to end: SSE event order, graph answers, RAG with citations, both kinds of
abstention, degraded modes, persistence and feedback. The fake chat model stands in."""

import json
import shutil

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.db.models import Source
from app.deps import get_arq, get_session, get_sessionmaker
from app.main import app
from app.services.chat import service
from app.services.chat.service import ABSTAIN_TEXT, NO_MODEL_TEXT, UNAVAILABLE_TEXT
from app.services.ingestion.pipeline import Pipeline, start_run
from app.services.llm.base import LLMUnavailable, Served
from tests.integration.test_api import FakeQueue


@pytest.fixture
async def client(sessions, tmp_path, corpus, monkeypatch):
    root = tmp_path / "sources"
    shutil.copytree(corpus, root / "fixture")
    monkeypatch.setattr(settings, "sources_root", str(root))
    async with sessions() as session:
        source = Source(name="fixture", kind="local", uri="fixture")
        session.add(source)
        await session.commit()
        run_id = await start_run(session, source.id)
    await Pipeline(sessions, source.id, run_id).run()

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


async def ask(client, message, **body) -> list[tuple[str, dict]]:
    events = []
    async with client.stream("POST", "/api/v1/chat", json={"message": message, **body}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        buffer = ""
        async for chunk in response.aiter_text():
            buffer += chunk
            while "\n\n" in buffer:
                raw, buffer = buffer.split("\n\n", 1)
                name = raw.split("\n")[0].removeprefix("event: ")
                data = json.loads(raw.split("\n", 1)[1].removeprefix("data: "))
                events.append((name, data))
    return events


def answer(events) -> tuple[str, list[dict], dict]:
    names = [name for name, _ in events]
    assert names[0] == "meta" and names[1] == "sources" and names[-1] == "done", names
    assert set(names[2:-1]) <= {"token"}
    text = "".join(data["text"] for name, data in events if name == "token")
    return text, events[1][1]["sources"], events[-1][1]


async def test_which_project_used_postgres_is_a_graph_answer(client):
    text, sources, done = answer(await ask(client, "Which project used PostgreSQL?"))
    assert done["intent"] == "graph_projects" and done["model"] == "graph"
    assert "auth-service" in text and "inventory-api" in text
    assert "task-board" not in text
    # Every citation resolves to evidence, and the evidence is the manifest line.
    assert done["citations"] and all(1 <= n <= len(sources) for n in done["citations"])
    paths = {s["path"] for s in sources}
    assert "repos/auth-service/pyproject.toml" in paths
    assert "repos/inventory-api/pom.xml" in paths


async def test_every_project_where_i_used_fastapi(client):
    text, _, done = answer(await ask(client, "Show every project where I used FastAPI"))
    assert done["intent"] == "graph_projects"
    assert "**FastAPI** is used in 1 project" in text and "auth-service" in text


async def test_graph_question_about_something_unseen_goes_to_rag(client):
    # Nothing in the graph references Kubernetes, so there is no evidence either way: search
    # answers (and abstains if it finds nothing) rather than the graph claiming "never".
    _, _, done = answer(await ask(client, "Which projects use Kubernetes?"))
    assert done["intent"] == "rag"
    _, _, done = answer(await ask(client, "Which projects use the flux capacitor?"))
    assert done["intent"] == "rag"


async def test_project_stack(client):
    text, _, done = answer(await ask(client, "What stack does task-board use?"))
    assert done["intent"] == "graph_stack"
    assert "React" in text and "Zustand" in text and "TypeScript" in text


async def test_rag_answer_is_cited_and_persisted(client):
    events = await ask(client, "Where did I implement JWT authentication?")
    text, sources, done = answer(events)
    assert done["intent"] == "rag" and done["model"] == "fake:extractive"
    assert not done["abstained"] and done["grounded"]
    assert done["citations"] == [1, 2]
    assert "[1]" in text
    assert any(s["path"] == "repos/auth-service/app/security.py" for s in sources[:3])
    assert all(s["kind"] == "chunk" and s["chunk_id"] for s in sources)

    conversation_id = events[0][1]["conversation_id"]
    detail = (await client.get(f"/api/v1/conversations/{conversation_id}")).json()
    assert [t["role"] for t in detail["turns"]] == ["user", "assistant"]
    assistant = detail["turns"][1]
    assert assistant["citations"] == [1, 2]
    assert assistant["sources"][0]["chunk_id"] == sources[0]["chunk_id"]
    assert assistant["trace"]["prompt"] == "answer.v1"
    assert assistant["trace"]["retrieval"]["hits"]

    listed = (await client.get("/api/v1/conversations")).json()
    assert listed[0]["id"] == conversation_id and listed[0]["messages"] == 2


async def test_original_architecture_question_finds_the_v1_design(client):
    text, sources, done = answer(
        await ask(client, "What was my original architecture for Student Portal?")
    )
    assert done["intent"] == "rag"
    assert sources[0]["path"] == "notes/projects/student-portal-architecture.md"


async def test_follow_up_uses_the_conversation(client):
    first = await ask(client, "Where did I implement JWT authentication?")
    conversation_id = first[0][1]["conversation_id"]
    events = await ask(client, "and the refresh token?", conversation_id=conversation_id)
    _, _, done = answer(events)
    assert done["conversation_id"] == conversation_id
    detail = (await client.get(f"/api/v1/conversations/{conversation_id}")).json()
    assert len(detail["turns"]) == 4
    assert "condensed" in detail["turns"][3]["trace"]


async def test_abstains_when_retrieval_finds_nothing(client):
    text, sources, done = answer(
        await ask(client, "kubernetes helm charts", filters={"path_prefix": "does/not/exist/"})
    )
    assert done["abstained"] and text == ABSTAIN_TEXT and sources == []


async def test_abstains_below_the_rerank_threshold(client, monkeypatch):
    real_search = service.search

    async def low_scores(*args, **kwargs):
        result = await real_search(*args, **kwargs)
        for hit in result.hits:
            hit.rerank_score = 0.01
        return result

    monkeypatch.setattr(service, "search", low_scores)
    monkeypatch.setattr(settings, "abstain_threshold", 0.1)
    text, sources, done = answer(await ask(client, "what is the capital of France"))
    assert done["abstained"] and text == ABSTAIN_TEXT
    assert sources  # the closest matches are still shown, marked as not an answer


class ScriptedChat:
    name = "scripted"
    models: list = []

    def __init__(self, parts=None, error=None):
        self.parts, self.error = parts or [], error

    async def stream(self, messages, **kwargs):
        if self.error:
            raise self.error
        yield Served("scripted:model")
        for part in self.parts:
            yield part

    async def complete(self, messages, **kwargs):
        raise LLMUnavailable("not used")


async def test_model_level_abstention_hides_the_sentinel(client, monkeypatch):
    monkeypatch.setattr(service, "get_chat", lambda: ScriptedChat(["NO_", "ANS", "WER"]))
    text, sources, done = answer(await ask(client, "Where did I implement JWT authentication?"))
    assert done["abstained"] and text == ABSTAIN_TEXT and "NO_ANSWER" not in text
    assert sources


async def test_uncited_answer_is_flagged(client, monkeypatch):
    monkeypatch.setattr(service, "get_chat", lambda: ScriptedChat(["It is in the ", "code."]))
    text, _, done = answer(await ask(client, "Where did I implement JWT authentication?"))
    assert text == "It is in the code." and done["grounded"] is False


async def test_without_a_model_sources_still_come_back(client, monkeypatch):
    monkeypatch.setattr(service, "get_chat", lambda: None)
    text, sources, done = answer(await ask(client, "Where did I implement JWT authentication?"))
    assert text == NO_MODEL_TEXT and sources and "chat: no model configured" in done["degraded"]


async def test_model_outage_degrades_to_sources(client, monkeypatch):
    chat = ScriptedChat(error=LLMUnavailable("every chat model failed: 429"))
    monkeypatch.setattr(service, "get_chat", lambda: chat)
    text, sources, done = answer(await ask(client, "Where did I implement JWT authentication?"))
    assert text == UNAVAILABLE_TEXT and sources and done["degraded"]


async def test_feedback_is_recorded_and_replaced(client):
    events = await ask(client, "Where did I implement JWT authentication?")
    message_id = events[-1][1]["message_id"]
    conversation_id = events[0][1]["conversation_id"]
    for rating in (1, -1):
        response = await client.post(
            f"/api/v1/messages/{message_id}/feedback", json={"rating": rating}
        )
        assert response.status_code == 200, response.text
    detail = (await client.get(f"/api/v1/conversations/{conversation_id}")).json()
    assert detail["turns"][1]["feedback"] == -1
    bad = await client.post(f"/api/v1/messages/{message_id}/feedback", json={"rating": 5})
    assert bad.status_code == 422
    user_turn = detail["turns"][0]["id"]
    missing = await client.post(f"/api/v1/messages/{user_turn}/feedback", json={"rating": 1})
    assert missing.status_code == 404


async def test_delete_conversation(client):
    events = await ask(client, "Which project used PostgreSQL?")
    conversation_id = events[0][1]["conversation_id"]
    assert (await client.delete(f"/api/v1/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/api/v1/conversations/{conversation_id}")).status_code == 404


async def test_graph_api(client):
    projects = (await client.get("/api/v1/graph/projects")).json()
    assert {p["name"] for p in projects} >= {"auth-service", "task-board"}
    auth = next(p for p in projects if p["name"] == "auth-service")
    assert {"name": "PostgreSQL", "category": "database", "via": ["manifest"]} in (
        auth["technologies"]
    )
    using = (await client.get("/api/v1/graph/projects", params={"uses": "postgres"})).json()
    assert [p["name"] for p in using] == ["auth-service", "inventory-api"]

    detail = (await client.get(f"/api/v1/graph/nodes/{auth['id']}")).json()
    assert "uses" in detail["outgoing"] and "mentions" in detail["incoming"]
    ego = (await client.get(f"/api/v1/graph/nodes/{auth['id']}/neighbourhood")).json()
    assert any(n["name"] == "FastAPI" for n in ego["nodes"])
    found = (await client.get("/api/v1/graph/nodes", params={"q": "postgres"})).json()
    assert found and found[0]["name"] == "PostgreSQL"
    assert (await client.get("/api/v1/graph/nodes/999999")).status_code == 404


async def test_concept_extraction_endpoint_needs_a_model(client, monkeypatch):
    from app.api.v1 import sources as sources_api

    source_id = (await client.get("/api/v1/sources")).json()[0]["id"]
    response = await client.post(f"/api/v1/sources/{source_id}/extract")
    assert response.status_code == 202 and client.queue.jobs == [
        ("extract_source_concepts", source_id, 500)
    ]
    monkeypatch.setattr(sources_api, "get_extraction_chat", lambda: None)
    response = await client.post(f"/api/v1/sources/{source_id}/extract")
    assert response.status_code == 409


def test_sse_format():
    from app.api.v1.chat import sse

    assert (
        sse(service.Event("token", {"text": "a\nb"})) == 'event: token\ndata: {"text": "a\\nb"}\n\n'
    )
