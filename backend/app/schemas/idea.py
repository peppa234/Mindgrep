from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

IdeaStatus = Literal["implemented", "partial", "unimplemented", "abandoned"]


class ProjectRef(BaseModel):
    id: int
    name: str


class IdeaCandidate(BaseModel):
    """One project matching looked at, with the evidence for and against it."""

    project_id: int
    project: str
    coverage: float = Field(description="IDF-weighted share of the idea's words in the project")
    similarity: float | None = Field(
        None, description="Reranker score of the idea against the project's best chunk"
    )
    matched: list[str] = Field(default_factory=list, description="The idea's words it contains")
    linked: bool = Field(False, description="The idea's note links to it with a [[wikilink]]")
    best: dict[str, Any] | None = Field(None, description="The chunk most like the idea")
    best_document: dict[str, Any] | None = Field(None, description="The file with most words")

    @property
    def closeness(self) -> float:
        return max(self.coverage, self.similarity or 0.0)


class IdeaOut(BaseModel):
    id: int
    title: str
    summary: str
    extractor: str = Field(description="note | inline | llm")
    source_id: int
    source_name: str
    document_id: int
    path: str
    line: int | None
    chunk_id: int | None = Field(None, description="The chunk holding the idea, for links")
    node_id: int | None = Field(None, description="The idea's node in the knowledge graph")
    written_on: date | None
    tags: list[str]

    status: IdeaStatus = Field(description="After the user's and the note's own say")
    origin: Literal["match", "declared", "user"] = Field(description="Who decided the status")
    project: ProjectRef | None
    matched_status: str = Field(description="What matching alone concluded")
    score: float = Field(description="How close the closest project came (0..1)")
    closest: IdeaCandidate | None
    candidates: list[IdeaCandidate]
    missing: list[str] = Field(description="Distinctive words of the idea no project contains")
    signals: list[str] = Field(description="coverage, and similarity when the reranker ran")
    declared_status: str | None
    declared_project: str | None
    user_note: str | None
    matched_at: datetime | None


class IdeaOverride(BaseModel):
    status: IdeaStatus
    project_id: int | None = Field(None, description="The project that implements it, if any")
    note: str | None = Field(None, max_length=2000)


class IdeaSummary(BaseModel):
    total: int
    by_status: dict[str, int]
    projects: int
    signals: list[str]
