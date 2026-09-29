from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Node(TimestampMixin, Base):
    """A graph entity. Identity is (kind, key): the key is normalised, the name is for display.

    Projects and notes belong to the source they were found in and disappear with it.
    Technologies, packages, people and topics are shared across sources.
    """

    __tablename__ = "nodes"
    __table_args__ = (
        UniqueConstraint("kind", "key"),
        Index(
            "ix_nodes_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # project | technology | package | person | note | topic | concept | idea
    kind: Mapped[str] = mapped_column(String(16))
    key: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    # project: root, manifests; technology: category, curated; note: document_id; ...
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class Edge(Base):
    """A typed, directed fact with its provenance. No edge exists without evidence.

    Several edges may connect the same two nodes: one per piece of evidence (the manifest
    line and the imports, say). Queries aggregate; provenance stays exact.
    """

    __tablename__ = "edges"
    __table_args__ = (
        Index("ix_edges_src_id_type", "src_id", "type"),
        Index("ix_edges_dst_id_type", "dst_id", "type"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    src_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    dst_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    # uses | depends_on | authored | mentions | links_to | tagged | proposes | implemented_by
    type: Mapped[str] = mapped_column(String(24))
    # The source whose indexing produced this edge; rebuilding a source replaces its edges.
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    # Provenance: the file (and line, and chunks) the fact was read from.
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    line: Mapped[int | None] = mapped_column(Integer)
    chunk_ids: Mapped[list[int]] = mapped_column(
        ARRAY(BigInteger), default=list, server_default="{}"
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    # manifest | import | docker | compose | language | git | wikilink | tag | llm | idea
    extractor: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1")
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmExtraction(Base):
    """Cache of LLM extraction results, keyed by what was extracted and how.

    Re-running extraction after a re-index costs nothing for unchanged chunks, and a prompt
    change (a new version) invalidates exactly the results it should.
    """

    __tablename__ = "llm_extractions"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    prompt_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(128))
    result: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
