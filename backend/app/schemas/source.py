from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
        description="Short handle shown in citations, e.g. `notes` or `student-portal`",
    )
    kind: Literal["local", "git"]
    uri: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "local: a folder relative to SOURCES_DIR (e.g. `notes`), or an absolute path "
            "under /sources. git: a public https URL."
        ),
    )
    index_now: bool = True


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    stage: str | None
    stats: dict[str, Any]
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    uri: str
    status: str
    error: str | None
    last_commit: str | None
    last_indexed_at: datetime | None
    created_at: datetime
    documents: int = 0
    chunks: int = 0
    embedded: int = 0
    documents_by_kind: dict[str, int] = Field(default_factory=dict)
    latest_run: RunOut | None = None


class StatsOut(BaseModel):
    sources: int
    documents: int
    chunks: int
    embedded: int
    documents_by_kind: dict[str, int]
    documents_by_language: dict[str, int]
    chunks_by_kind: dict[str, int]
    needs_ocr: int
    failed: int
