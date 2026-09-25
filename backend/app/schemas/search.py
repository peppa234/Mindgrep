from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SearchMode = Literal["auto", "vector", "lexical", "hybrid", "rerank"]


class SearchFilters(BaseModel):
    source_ids: list[int] | None = None
    doc_kinds: list[Literal["code", "markdown", "pdf", "text"]] | None = None
    languages: list[str] | None = None
    chunk_kinds: list[str] | None = None
    path_prefix: str | None = Field(None, description="Only documents whose path starts with this")
    modified_after: datetime | None = None
    modified_before: datetime | None = None


class SearchRequest(BaseModel):
    q: str = Field(min_length=1, max_length=2000)
    k: int = Field(10, ge=1, le=50)
    mode: SearchMode = Field(
        "auto",
        description=(
            "auto = rerank when a reranker is configured, else hybrid. The explicit modes "
            "exist so the eval harness can measure each stage's contribution."
        ),
    )
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchHit(BaseModel):
    chunk_id: int
    document_id: int
    source_id: int
    source_name: str
    path: str
    doc_kind: str
    language: str | None
    title: str | None
    chunk_kind: str
    symbol: str | None
    symbols: list[str]
    start_line: int | None
    end_line: int | None
    header: str
    content: str
    modified_at: datetime | None
    git_commit: str | None
    meta: dict[str, Any]
    score: float = Field(description="Fused RRF score, or the reranker score in rerank mode")
    rerank_score: float | None = None
    ranks: dict[str, int] = Field(description="1-based rank of this hit in each channel")


class SearchResponse(BaseModel):
    query: str
    mode: SearchMode
    hits: list[SearchHit]
    candidates: int
    degraded: list[str] = Field(
        default_factory=list, description="Channels that were skipped and why"
    )
    timings_ms: dict[str, float]
