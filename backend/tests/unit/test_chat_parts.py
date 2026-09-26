"""Chat building blocks: intent, context assembly, citations, abstention, and the LLM layer
(stream parsing, fallback, think-tag stripping) against a mocked HTTP transport."""

import json
from datetime import UTC, datetime

import httpx
import pytest

from app.schemas.extraction import ConceptExtraction
from app.schemas.search import SearchHit
from app.services.chat.context import (
    assemble,
    citations,
    detect_abstention,
    render_sources,
    strip_citations,
)
from app.services.chat.intent import detect
from app.services.graph.concepts import verified
from app.services.llm.base import LLMUnavailable, Served, Usage
from app.services.llm.fake import FakeChat
from app.services.llm.openai_compat import OpenAICompatible, ThinkStripper
from app.services.llm.prompt import load
from app.services.llm.router import FallbackChat


@pytest.mark.parametrize(
    "question,kind,subject",
    [
        ("Which project used PostgreSQL?", "graph_projects", "PostgreSQL"),
        ("Show every project where I used FastAPI", "graph_projects", "FastAPI"),
        ("which of my repos use postgres and redis?", "graph_projects", "postgres and redis"),
        ("Have I ever used Kafka?", "graph_projects", "Kafka"),
        ("what projects have I built with Spring Boot", "graph_projects", "Spring Boot"),
        ("What stack does auth-service use?", "graph_stack", "auth-service"),
        ("tech stack of task-board", "graph_stack", "task-board"),
        ("Where did I implement JWT authentication?", "rag", None),
        ("how does the rate limiter work", "rag", None),
    ],
)
def test_intent(question, kind, subject):
    intent = detect(question)
    assert (intent.kind, intent.subject) == (kind, subject)


def test_temporal_intent():
    assert detect("What was my original architecture for Student Portal?").temporal == "earliest"
    assert detect("how is auth done currently").temporal == "latest"
    assert detect("where is the retry logic").temporal is None


def hit(i, doc, start, end, content="x" * 400, score=1.0):
    return SearchHit(
        chunk_id=i, document_id=doc, source_id=1, source_name="repo", path=f"f{doc}.py",
        doc_kind="code", language="python", title=None, chunk_kind="function",
        symbol=f"fn{i}", symbols=[], start_line=start, end_line=end, header=f"h{i}",
        content=content, modified_at=datetime(2024, 3, 2, tzinfo=UTC), git_commit=None,
        meta={}, score=score, ranks={},
    )  # fmt: skip


def test_assemble_dedupes_overlaps_and_respects_budget():
    hits = [hit(1, 1, 10, 50), hit(2, 1, 20, 30), hit(3, 2, 1, 5), hit(4, 3, 1, 5)]
    sources = assemble(hits, max_sources=8, budget_tokens=10_000)
    # Chunk 2 sits inside chunk 1 of the same file: dropped. Numbering stays contiguous.
    assert [(s.n, s.chunk_id) for s in sources] == [(1, 1), (2, 3), (3, 4)]
    assert len(assemble(hits, max_sources=2, budget_tokens=10_000)) == 2

    big = [hit(1, 1, 1, 9, "y" * 4000), hit(2, 2, 1, 9, "z" * 4000)]
    sources = assemble(big, max_sources=8, budget_tokens=1500)
    assert len(sources) == 2 and sources[1].content.endswith("[… truncated]")

    rendered = render_sources(sources[:1])
    assert rendered.startswith(
        "[1] repo/f1.py :: fn1 (lines 1-9) · python · last changed 2024-03-02"
    )


def test_citations_are_validated():
    assert citations("See [2] and [1][2], also [3, 1] and [9].", count=3) == [2, 1, 3]
    assert citations("no citations here", count=3) == []
    assert strip_citations("It is here [1] and there [2, 3].") == "It is here and there."


async def _collect(parts):
    async def gen():
        for part in parts:
            yield part

    return [p async for p in detect_abstention(gen())]


async def test_detect_abstention():
    assert await _collect(["NO_", "ANSWER"]) == [None]
    assert await _collect(["  NO_ANSWER\n"]) == [None]
    assert await _collect([""]) == [None]
    assert await _collect(["The ", "answer is [1]."]) == ["The ", "answer is [1]."]
    assert await _collect(["NO", " worries, it is in [1]"]) == ["NO worries, it is in [1]"]
    assert await _collect(["NO"]) == ["NO"]  # a short real answer is still an answer


def test_think_stripper_handles_split_tags():
    stripper = ThinkStripper()
    out = "".join(
        stripper.feed(part)
        for part in ["<thi", "nk>reasoning here</th", "ink>\nThe answer", " is <b>42</b>."]
    )
    assert out + stripper.flush() == "The answer is <b>42</b>."


def _model(handler, provider="p"):
    return OpenAICompatible(
        provider, "http://llm.test/v1", "m", "key", transport=httpx.MockTransport(handler)
    )


async def test_openai_compatible_stream():
    def handler(request):
        assert request.headers["authorization"] == "Bearer key"
        body = json.loads(request.content)
        assert body["stream"] is True and body["model"] == "m"
        chunks = [
            {"choices": [{"delta": {"content": "Hel"}}]},
            {"choices": [{"delta": {"content": "lo [1]"}}]},
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3}},
        ]
        lines = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"
        return httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})

    parts = [p async for p in _model(handler).stream([{"role": "user", "content": "hi"}])]
    assert parts == [Served("p:m"), "Hel", "lo [1]", Usage(12, 3)]


async def test_openai_compatible_errors_become_unavailable():
    model = _model(lambda request: httpx.Response(429, text="slow down"))
    with pytest.raises(LLMUnavailable) as caught:
        [p async for p in model.stream([{"role": "user", "content": "hi"}])]
    assert caught.value.status == 429


async def test_complete_falls_back_from_json_schema_to_json_mode():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["response_format"]["type"])
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, text="response_format json_schema not supported")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"concepts": []}'}}]})

    completion = await _model(handler).complete(
        [{"role": "user", "content": "x"}], schema=ConceptExtraction
    )
    assert seen == ["json_schema", "json_object"] and completion.text == '{"concepts": []}'


class Broken:
    def __init__(self, name, status=503, after=None):
        self.name, self.status, self.after, self.calls = name, status, after, 0

    async def stream(self, messages, **kwargs):
        self.calls += 1
        if self.after is not None:
            yield Served(self.name)
            yield self.after
        raise LLMUnavailable(f"{self.name} down", self.status)

    async def complete(self, messages, **kwargs):
        self.calls += 1
        raise LLMUnavailable(f"{self.name} down", self.status)


async def test_fallback_chain_moves_on_and_cools_down_rate_limited_models():
    limited = Broken("limited", status=429)
    chain = FallbackChat([limited, FakeChat()])
    messages = [{"role": "user", "content": "Sources:\n\n[1] a.py · x\n\nQuestion: q"}]
    parts = [p async for p in chain.stream(messages)]
    assert parts[0] == Served("fake:extractive") and "[1]" in "".join(
        p for p in parts if isinstance(p, str)
    )
    # The rate-limited model goes to the back of the line for a while.
    assert chain._order()[0].name == "fake:extractive"
    completion = await chain.complete([{"role": "user", "content": "Last message: hi"}])
    assert completion.model == "fake:extractive" and limited.calls == 1


async def test_fallback_never_switches_models_mid_answer():
    chain = FallbackChat([Broken("half", after="The answer is"), FakeChat()])
    with pytest.raises(LLMUnavailable):
        [p async for p in chain.stream([{"role": "user", "content": "q"}])]


async def test_fallback_reports_every_failure():
    chain = FallbackChat([Broken("a"), Broken("b")])
    with pytest.raises(LLMUnavailable, match="a down.*b down"):
        await chain.complete([{"role": "user", "content": "q"}])


def test_evidence_must_be_a_real_quote():
    text = "## HNSW\nThe ef_search parameter trades recall for latency.\n"
    assert verified("ef_search parameter trades recall", text)
    assert verified("The EF_SEARCH  parameter\ntrades recall for latency.", text)
    assert not verified("HNSW uses product quantization", text)
    assert not verified("a", text)


def test_prompts_are_versioned():
    for name in ("answer", "condense", "concepts"):
        prompt = load(name)
        assert prompt.version.startswith(f"{name}.v") and prompt.text
    assert "NO_ANSWER" in load("answer").text
