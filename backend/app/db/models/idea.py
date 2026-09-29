from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin

# implemented | partial | unimplemented are what matching can conclude; abandoned is only
# ever said by a person (frontmatter or an override), never inferred.
STATUSES = ("implemented", "partial", "unimplemented", "abandoned")


class Idea(TimestampMixin, Base):
    """An idea written down in a note, and whether any indexed project implements it.

    Three layers of status, the most deliberate one wins: what the user set here (`user_*`),
    what the note itself declares in its frontmatter (`declared_*`), and what matching
    concluded from the projects' code (`status`, `implemented_by_id`). A re-index recomputes
    the last layer and never touches the first.
    """

    __tablename__ = "ideas"
    __table_args__ = (
        UniqueConstraint("source_id", "key"),
        CheckConstraint("status IN ('implemented', 'partial', 'unimplemented')", name="status"),
        CheckConstraint(
            "user_status IS NULL OR user_status IN "
            "('implemented', 'partial', 'unimplemented', 'abandoned')",
            name="user_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # The idea's node in the graph (note -proposes-> idea -implemented_by-> project).
    node_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"))
    # Stable across re-indexing: "note:<path>" or "line:<path>:<normalised title>".
    key: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    # note: the whole note is the idea | inline: an "Idea:" line | llm: extracted, verified
    extractor: Mapped[str] = mapped_column(String(16))
    line: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[str | None] = mapped_column(Text)
    # When the idea was written: frontmatter `created`/`date`, else the file's last commit.
    written_on: Mapped[date | None] = mapped_column(Date, index=True)

    # --- what matching concluded
    status: Mapped[str] = mapped_column(String(16), default="unimplemented")
    score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    # The nullable foreign key that answers "which ideas did I never implement?".
    implemented_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL"), index=True
    )
    # Signals, matched and missing terms, best chunk, runner-up projects: the "why".
    match: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- what the note declares (status: done, implemented_by: task-board)
    declared_status: Mapped[str | None] = mapped_column(String(16))
    declared_project: Mapped[str | None] = mapped_column(Text)  # the name as written
    declared_project_id: Mapped[int | None] = mapped_column(
        ForeignKey("nodes.id", ondelete="SET NULL")
    )

    # --- what the user said, which survives every re-index
    user_status: Mapped[str | None] = mapped_column(String(16))
    user_project_id: Mapped[int | None] = mapped_column(ForeignKey("nodes.id", ondelete="SET NULL"))
    user_note: Mapped[str | None] = mapped_column(Text)
    overridden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def effective(self) -> tuple[str, int | None, str]:
        """(status, project id, origin) after applying the layers, most deliberate first."""
        if self.user_status:
            return self.user_status, self.user_project_id, "user"
        if self.declared_status:
            project = self.declared_project_id if self.declared_status != "abandoned" else None
            return self.declared_status, project, "declared"
        return self.status, self.implemented_by_id, "match"
