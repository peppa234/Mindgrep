"""The chat pipeline, one question at a time:

  condense (follow-ups only) -> intent -> graph answer            (no model involved)
                                       -> retrieve -> abstain?   (reranker below threshold)
                                                   -> stream     (NO_ANSWER sentinel = abstain)

It is a function, not an agent framework: classify, retrieve, synthesize. Every step is
recorded in the assistant message's trace, so a bad answer can be debugged after the fact.
Events go out in a fixed order: `meta`, `sources` (before any token), `token`*, `done`,
or `error` at any point after `meta`.
"""

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import Conversation, Message
from app.schemas.chat import ChatRequest, ChatSource
from app.schemas.search import SearchFilters, SearchRequest
from app.services.chat import graph_answer
from app.services.chat.context import (
    assemble,
    citations,
    detect_abstention,
    render_sources,
    strip_citations,
)
from app.services.chat.intent import QueryIntent, detect
from app.services.llm.base import LLMUnavailable, Messages, Served, Usage
from app.services.llm.factory import get_chat
from app.services.llm.prompt import load as load_prompt
from app.services.retrieval.search import search

log = logging.getLogger(__name__)

ABSTAIN_TEXT = (
    "I couldn't find this in your notes, papers or code. The closest matches are listed "
    "below in case one of them is what you meant."
)
UNAVAILABLE_TEXT = (
    "Every configured chat model failed just now (rate limit or outage), so here are the "
    "most relevant sources instead. Try again in a minute."
)
NO_MODEL_TEXT = (
    "No chat model is configured, so here are the most relevant sources instead. Set "
    "GEMINI_API_KEY or GROQ_API_KEY (or OLLAMA_MODEL) in .env to get written answers."
)
TEMPORAL_HINT = {
    "earliest": "(The question is about the original or earliest version. Prefer older "
    "sources, and say which version you describe.)",
    "latest": "(The question is about the current state. Prefer the most recently changed "
    "sources.)",
}
CONDENSE_MAX_TOKENS = 200


@dataclass
class Event:
    name: str
    data: dict[str, Any]


class Turn:
    """State of one question as it moves through the pipeline."""

    def __init__(self, request: ChatRequest) -> None:
        self.request = request
        self.started = time.perf_counter()
        self.timings: dict[str, float] = {}
        self.trace: dict[str, Any] = {}
        self.sources: list[ChatSource] = []
        self.text = ""
        self.abstained = False
        self.intent = "rag"
        self._lap = self.started

    def lap(self, name: str) -> None:
        now = time.perf_counter()
        self.timings[name] = round((now - self._lap) * 1000, 1)
        self._lap = now


async def _history(session: AsyncSession, conversation_id: int) -> list[Message]:
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(settings.chat_history_turns * 2)
        )
    ).scalars()
    return list(reversed(list(rows)))


def _history_messages(history: list[Message]) -> Messages:
    out: Messages = []
    for message in history:
        content = message.content if message.role == "user" else strip_citations(message.content)
        if message.role == "assistant" and (message.abstained or not content):
            content = "(I could not answer that from the sources.)"
        out.append({"role": message.role, "content": content[:2000]})
    return out


async def _condense(question: str, history: list[Message], turn: Turn) -> str:
    """A follow-up ("and where is it tested?") is rewritten into a standalone question before
    retrieval, because search only ever sees one string."""
    if not history:
        return question
    chat = get_chat()
    previous = next((m.content for m in reversed(history) if m.role == "user"), "")
    if chat is None:
        return f"{previous} {question}".strip()
    prompt = load_prompt("condense")
    transcript = "\n".join(f"{m['role']}: {m['content'][:600]}" for m in _history_messages(history))
    try:
        completion = await chat.complete(
            [
                {"role": "system", "content": prompt.text},
                {
                    "role": "user",
                    "content": f"Conversation:\n{transcript}\n\nLast message: {question}",
                },
            ],
            max_tokens=CONDENSE_MAX_TOKENS,
        )
        rewritten = completion.text.strip().strip('"')
        turn.trace["condensed"] = {"question": rewritten, "model": completion.model}
        return rewritten or question
    except LLMUnavailable as exc:
        turn.trace["condensed"] = {"error": str(exc)[:300]}
        return f"{previous} {question}".strip()


async def respond(
    sessions: async_sessionmaker[AsyncSession], request: ChatRequest
) -> AsyncIterator[Event]:
    turn = Turn(request)
    async with sessions() as session:
        conversation = None
        if request.conversation_id is not None:
            conversation = await session.get(Conversation, request.conversation_id)
        if conversation is None:
            conversation = Conversation(title=request.message.strip().splitlines()[0][:120])
            session.add(conversation)
            await session.flush()
        history = await _history(session, conversation.id)
        user_message = Message(
            conversation_id=conversation.id, role="user", content=request.message
        )
        session.add(user_message)
        await session.commit()
        conversation_id, user_message_id = conversation.id, user_message.id

    yield Event("meta", {"conversation_id": conversation_id, "user_message_id": user_message_id})

    try:
        question = await _condense(request.message, history, turn)
        turn.lap("condense")
        intent = detect(question)
        turn.trace["intent"] = {
            "kind": intent.kind, "subject": intent.subject, "temporal": intent.temporal,
        }  # fmt: skip

        answered = False
        if intent.kind != "rag" and intent.subject:
            async for event in _graph(sessions, intent, turn):
                answered = True
                yield event
        if not answered:
            async for event in _rag(sessions, question, intent, history, turn):
                yield event
    except Exception as exc:  # the stream is already open: report, don't drop the connection
        log.exception("chat turn failed")
        turn.trace["error"] = repr(exc)[:500]
        await _save(sessions, conversation_id, turn)
        yield Event("error", {"message": str(exc) or type(exc).__name__})
        return

    message_id = await _save(sessions, conversation_id, turn)
    turn.timings["total"] = round((time.perf_counter() - turn.started) * 1000, 1)
    yield Event(
        "done",
        {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "intent": turn.intent,
            "abstained": turn.abstained,
            "citations": turn.trace.get("citations", []),
            "grounded": turn.trace.get("grounded", True),
            "model": turn.trace.get("model"),
            "degraded": turn.trace.get("degraded", []),
            "timings_ms": turn.timings,
        },
    )


async def _graph(
    sessions: async_sessionmaker[AsyncSession], intent: QueryIntent, turn: Turn
) -> AsyncIterator[Event]:
    async with sessions() as session:
        entities = await graph_answer.resolve(session, intent.kind, intent.subject or "")
        turn.lap("resolve")
        if not entities:
            turn.trace["graph_miss"] = intent.subject
            return
        turn.trace["entities"] = [{"id": e.id, "kind": e.kind, "name": e.name} for e in entities]
        if intent.kind == "graph_projects":
            answer = await graph_answer.projects_using(session, entities)
        else:
            answer = await graph_answer.project_stack(session, entities)
        turn.lap("graph")
    turn.intent = intent.kind
    turn.sources = answer.sources
    turn.text = answer.text
    turn.trace["model"] = "graph"
    turn.trace["citations"] = citations(answer.text, len(answer.sources))
    yield Event("sources", {"sources": [s.model_dump(mode="json") for s in answer.sources]})
    for paragraph in answer.text.split("\n"):
        yield Event("token", {"text": paragraph + "\n"})


async def _rag(
    sessions: async_sessionmaker[AsyncSession],
    question: str,
    intent: QueryIntent,
    history: list[Message],
    turn: Turn,
) -> AsyncIterator[Event]:
    turn.intent = "rag"
    async with sessions() as session:
        project = await graph_answer.project_scope(session, question)
        scope = None
        if project is not None:
            root = project.meta.get("root") or ""
            scope = SearchFilters(
                source_ids=[project.source_id] if project.source_id else None,
                path_prefix=f"{root}/" if root else None,
            )
            turn.trace["scope"] = {"project": project.name, "root": root}
        result = await search(
            session,
            SearchRequest(
                q=question[:2000],
                k=min(50, settings.chat_context_chunks * 2),
                filters=turn.request.filters,
            ),
            scope=scope,
        )
    turn.lap("retrieve")
    turn.trace["retrieval"] = {
        "mode": result.mode,
        "candidates": result.candidates,
        "hits": [
            {"chunk_id": h.chunk_id, "score": h.score, "rerank": h.rerank_score}
            for h in result.hits
        ],
        "timings_ms": result.timings_ms,
    }
    degraded = list(result.degraded)
    turn.trace["degraded"] = degraded

    turn.sources = assemble(result.hits, settings.chat_context_chunks, settings.chat_context_tokens)
    top = result.hits[0].rerank_score if result.hits else None
    if not turn.sources or (top is not None and top < settings.abstain_threshold):
        # Retrieval-level abstention: nothing relevant enough to show a model at all.
        turn.abstained = True
        turn.text = ABSTAIN_TEXT
        turn.trace["abstain"] = {"reason": "retrieval", "top_score": top}
        yield Event("sources", {"sources": [s.model_dump(mode="json") for s in turn.sources]})
        yield Event("token", {"text": ABSTAIN_TEXT})
        return

    yield Event("sources", {"sources": [s.model_dump(mode="json") for s in turn.sources]})

    chat = get_chat()
    if chat is None:
        degraded.append("chat: no model configured")
        turn.text = NO_MODEL_TEXT
        turn.trace["model"] = None
        yield Event("token", {"text": NO_MODEL_TEXT})
        return

    prompt = load_prompt("answer")
    user = f"Sources:\n\n{render_sources(turn.sources)}\n\n---\nQuestion: {question}"
    if intent.temporal:
        user += "\n" + TEMPORAL_HINT[intent.temporal]
    messages: Messages = [
        {"role": "system", "content": prompt.text},
        *_history_messages(history),
        {"role": "user", "content": user},
    ]
    turn.trace["prompt"] = prompt.version

    usage: dict[str, int | None] = {}

    async def text_parts() -> AsyncIterator[str]:
        async for part in chat.stream(messages, temperature=0.2):
            if isinstance(part, Served):
                turn.trace["model"] = part.model
            elif isinstance(part, Usage):
                usage.update(prompt=part.prompt_tokens, completion=part.completion_tokens)
            else:
                yield part

    first = True
    try:
        async for text in detect_abstention(text_parts()):
            if first:
                turn.lap("first_token")
                first = False
            if text is None:
                turn.abstained = True
                turn.text = ABSTAIN_TEXT
                turn.trace["abstain"] = {"reason": "model"}
                yield Event("token", {"text": ABSTAIN_TEXT})
                break
            turn.text += text
            yield Event("token", {"text": text})
    except LLMUnavailable as exc:
        if turn.text:
            raise  # mid-answer: the error event tells the user the answer is cut short
        degraded.append(f"chat: {exc}"[:300])
        turn.text = UNAVAILABLE_TEXT
        turn.trace["model"] = None
        yield Event("token", {"text": UNAVAILABLE_TEXT})
        return
    turn.lap("generate")
    turn.trace["usage"] = usage

    if not turn.abstained:
        cited = citations(turn.text, len(turn.sources))
        turn.trace["citations"] = cited
        # An answer that cites nothing is flagged, not hidden: the UI says so.
        turn.trace["grounded"] = bool(cited)


async def _save(
    sessions: async_sessionmaker[AsyncSession], conversation_id: int, turn: Turn
) -> int:
    turn.trace["timings_ms"] = turn.timings
    async with sessions() as session:
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=turn.text,
            intent=turn.intent,
            abstained=turn.abstained,
            sources=[s.model_dump(mode="json") for s in turn.sources],
            citations=turn.trace.get("citations", []),
            trace=turn.trace,
        )
        session.add(message)
        await session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=func.now())
        )
        await session.commit()
        return message.id
