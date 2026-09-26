from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

EMBEDDING_DIM = 1024

# Weighted full-text vector. A = symbol names and path, B = the text itself,
# C = camelCase/snake_case identifiers split into words, which the Postgres
# parser cannot do on its own ("generateJwtToken" -> "generate jwt token").
TSV_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(search_terms, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(content, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(identifier_terms, '')), 'C')"
)


class Document(Base):
    """One file from a source."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "path"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    # Path relative to the source root, always with forward slashes.
    path: Mapped[str] = mapped_column(Text)
    # code | markdown | pdf | text
    kind: Mapped[str] = mapped_column(String(16))
    language: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    # Bumped when parsing/chunking logic changes, forcing a re-chunk of unchanged files.
    parser_version: Mapped[int] = mapped_column(Integer)
    # indexed | needs_ocr | error
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(Text)
    # Last git commit touching the file if the source is a repo, else the file mtime.
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    git_commit: Mapped[str | None] = mapped_column(String(64))
    git_author: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )


class Chunk(Base):
    """The retrievable unit: a function, a class, a Markdown section, a PDF page."""

    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_chunks_symbol_text_trgm",
            "symbol_text",
            postgresql_using="gin",
            postgresql_ops={"symbol_text": "gin_trgm_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # Denormalised from the document so search filters avoid a join.
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    # function | method | class | interface | type | module | markdown_section | pdf_page | text
    kind: Mapped[str] = mapped_column(String(24))
    # Primary qualified name, e.g. "AuthService.create_token" or a heading path.
    symbol: Mapped[str | None] = mapped_column(Text)
    # Every name defined in the chunk (grouped small functions have several).
    symbols: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    symbol_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    # "repo/path/file.py :: Class.method (lines 40-92)" plus imports; prepended when embedding.
    header: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    search_terms: Mapped[str] = mapped_column(Text, default="", server_default="")
    identifier_terms: Mapped[str] = mapped_column(Text, default="", server_default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed(TSV_EXPRESSION, persisted=True))

    document: Mapped[Document] = relationship(back_populates="chunks")
