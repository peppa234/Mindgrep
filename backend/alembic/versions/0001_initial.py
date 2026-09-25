"""initial schema: sources, index runs, documents, chunks

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV_EXPRESSION = (
    "setweight(to_tsvector('english', coalesce(search_terms, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(content, '')), 'B') || "
    "setweight(to_tsvector('english', coalesce(identifier_terms, '')), 'C')"
)


def upgrade() -> None:
    # The compose init script already does this, but CI and reused volumes may not have run it.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "sources",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="idle"),
        sa.Column("error", sa.Text()),
        sa.Column("last_commit", sa.String(64)),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("name", name="uq_sources_name"),
    )

    op.create_table(
        "index_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(16)),
        sa.Column("stats", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_index_runs"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE",
            name="fk_index_runs_source_id_sources",
        ),
    )
    op.create_index("ix_index_runs_source_id", "index_runs", ["source_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("language", sa.String(32)),
        sa.Column("title", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("modified_at", sa.DateTime(timezone=True)),
        sa.Column("git_commit", sa.String(64)),
        sa.Column("git_author", sa.Text()),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE",
            name="fk_documents_source_id_sources",
        ),
        sa.UniqueConstraint("source_id", "path", name="uq_documents_source_id"),
    )
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_modified_at", "documents", ["modified_at"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("symbol", sa.Text()),
        sa.Column("symbols", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("symbol_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("header", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer()),
        sa.Column("end_line", sa.Integer()),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("search_terms", sa.Text(), nullable=False, server_default=""),
        sa.Column("identifier_terms", sa.Text(), nullable=False, server_default=""),
        sa.Column("embedding", Vector(1024)),
        sa.Column("embedding_model", sa.String(128)),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "tsv", postgresql.TSVECTOR(), sa.Computed(TSV_EXPRESSION, persisted=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_chunks"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE",
            name="fk_chunks_document_id_documents",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE",
            name="fk_chunks_source_id_sources",
        ),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunks_symbol_text_trgm", "chunks", ["symbol_text"],
        postgresql_using="gin", postgresql_ops={"symbol_text": "gin_trgm_ops"},
    )
    # HNSW over cosine distance. m/ef_construction are pgvector's defaults, made explicit so
    # tuning them later shows up as a migration rather than a silent change.
    op.create_index(
        "ix_chunks_embedding_hnsw", "chunks", ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("index_runs")
    op.drop_table("sources")
