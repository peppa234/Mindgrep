from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Source(TimestampMixin, Base):
    """A registered folder or Git repository. The unit of indexing."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    # "local": a folder under settings.sources_root. "git": a remote URL we clone.
    kind: Mapped[str] = mapped_column(String(16))
    uri: Mapped[str] = mapped_column(Text)
    # idle -> queued -> indexing -> ready | failed
    status: Mapped[str] = mapped_column(String(16), default="idle", server_default="idle")
    error: Mapped[str | None] = mapped_column(Text)
    last_commit: Mapped[str | None] = mapped_column(String(64))
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    runs: Mapped[list["IndexRun"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )


class IndexRun(Base):
    """One execution of the indexing pipeline over a source. Kept as history."""

    __tablename__ = "index_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    # queued -> running -> succeeded | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", server_default="queued")
    # sync -> walk -> parse -> graph -> embed -> done
    stage: Mapped[str | None] = mapped_column(String(16))
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="runs")
