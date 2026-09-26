from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SearchFilters

Intent = Literal["rag", "graph_projects", "graph_stack"]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: int | None = Field(None, description="Omit to start a new conversation")
    filters: SearchFilters = Field(default_factory=SearchFilters)


class ChatSource(BaseModel):
    """A numbered source the answer may cite as [n]: a retrieved chunk, or for graph answers
    the manifest line (or file) a fact was read from."""

    n: int
    kind: Literal["chunk", "evidence"]
    chunk_id: int | None
    document_id: int | None
    source_name: str | None
    path: str | None
    doc_kind: str | None = None
    language: str | None = None
    symbol: str | None = None
    title: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    page: int | None = None
    modified_at: datetime | None = None
    content: str = Field("", description="What the model was shown (chunks) or the evidence")
    score: float | None = None


class Feedback(BaseModel):
    rating: Literal[1, -1]
    comment: str | None = Field(None, max_length=2000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    intent: str | None
    abstained: bool
    sources: list[ChatSource]
    citations: list[int]
    trace: dict[str, Any]
    created_at: datetime
    feedback: Literal[1, -1] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: int = 0


class ConversationDetail(ConversationOut):
    turns: list[MessageOut] = Field(default_factory=list)
