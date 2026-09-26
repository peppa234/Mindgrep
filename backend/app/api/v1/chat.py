import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Conversation, Feedback, Message
from app.deps import get_session, get_sessionmaker
from app.schemas.chat import (
    ChatRequest,
    ConversationDetail,
    ConversationOut,
    MessageOut,
)
from app.schemas.chat import Feedback as FeedbackIn
from app.services.chat.service import Event, respond

router = APIRouter(tags=["chat"])


def sse(event: Event) -> str:
    return f"event: {event.name}\ndata: {json.dumps(event.data, default=str)}\n\n"


@router.post(
    "/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat(
    body: ChatRequest,
    sessions: async_sessionmaker[AsyncSession] = Depends(get_sessionmaker),
) -> StreamingResponse:
    """Ask a question; the answer streams back as Server-Sent Events.

    Events, in order: `meta` (conversation and message ids), `sources` (the numbered sources,
    always before the first token, so citations resolve as they appear), `token` (answer
    text, many), then `done` (citations actually used, abstained or not, model, timings) or
    `error`. Questions about which projects use a technology, or what a project is built
    with, are answered from the knowledge graph without a model.
    """

    async def stream() -> AsyncIterator[str]:
        async for event in respond(sessions, body):
            yield sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # no-transform: keeps proxies (and Next's compression) from buffering the stream.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    limit: int = 50, session: AsyncSession = Depends(get_session)
) -> list[ConversationOut]:
    counts = (
        select(Message.conversation_id, func.count().label("n"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Conversation, func.coalesce(counts.c.n, 0))
            .outerjoin(counts, counts.c.conversation_id == Conversation.id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(min(limit, 200))
        )
    ).all()
    out = []
    for conversation, n in rows:
        item = ConversationOut.model_validate(conversation)
        item.messages = n
        out.append(item)
    return out


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int, session: AsyncSession = Depends(get_session)
) -> ConversationDetail:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    rows = (
        await session.execute(
            select(Message, Feedback.rating)
            .outerjoin(Feedback, Feedback.message_id == Message.id)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id)
        )
    ).all()
    detail = ConversationDetail.model_validate(conversation)
    for message, rating in rows:
        turn = MessageOut.model_validate(message)
        turn.feedback = rating
        detail.turns.append(turn)
    detail.messages = len(detail.turns)
    return detail


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    result = await session.execute(delete(Conversation).where(Conversation.id == conversation_id))
    if result.rowcount == 0:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    await session.commit()


@router.post("/messages/{message_id}/feedback", response_model=MessageOut)
async def give_feedback(
    message_id: int, body: FeedbackIn, session: AsyncSession = Depends(get_session)
) -> MessageOut:
    """Thumbs up or down on an answer. Voting again replaces the earlier vote. This is the
    signal for tuning the abstention threshold and building the chat eval set."""
    message = await session.get(Message, message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "answer not found")
    stmt = pg_insert(Feedback).values(
        message_id=message_id, rating=body.rating, comment=body.comment
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[Feedback.message_id],
            set_={"rating": stmt.excluded.rating, "comment": stmt.excluded.comment},
        )
    )
    await session.commit()
    out = MessageOut.model_validate(message)
    out.feedback = body.rating
    return out
