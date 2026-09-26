"""knowledge graph (nodes, edges, llm extraction cache) and chat (conversations, messages,
feedback)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_id", sa.BigInteger()),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_nodes"),
        sa.UniqueConstraint("kind", "key", name="uq_nodes_kind"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE", name="fk_nodes_source_id_sources"
        ),
    )
    op.create_index("ix_nodes_source_id", "nodes", ["source_id"])
    op.create_index(
        "ix_nodes_name_trgm", "nodes", ["name"],
        postgresql_using="gin", postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.create_table(
        "edges",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("src_id", sa.BigInteger(), nullable=False),
        sa.Column("dst_id", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(24), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger()),
        sa.Column("line", sa.Integer()),
        sa.Column("chunk_ids", postgresql.ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("evidence", sa.Text()),
        sa.Column("extractor", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_edges"),
        sa.ForeignKeyConstraint(["src_id"], ["nodes.id"], ondelete="CASCADE", name="fk_edges_src_id_nodes"),
        sa.ForeignKeyConstraint(["dst_id"], ["nodes.id"], ondelete="CASCADE", name="fk_edges_dst_id_nodes"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE", name="fk_edges_source_id_sources"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE",
            name="fk_edges_document_id_documents",
        ),
    )
    op.create_index("ix_edges_src_id_type", "edges", ["src_id", "type"])
    op.create_index("ix_edges_dst_id_type", "edges", ["dst_id", "type"])
    op.create_index("ix_edges_source_id", "edges", ["source_id"])
    op.create_index("ix_edges_document_id", "edges", ["document_id"])

    op.create_table(
        "llm_extractions",
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("content_hash", "prompt_version", name="pk_llm_extractions"),
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("conversation_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(24)),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sources", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("citations", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"),
        sa.Column("trace", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE",
            name="fk_messages_conversation_id_conversations",
        ),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_feedback"),
        sa.UniqueConstraint("message_id", name="uq_feedback_message_id"),
        sa.ForeignKeyConstraint(
            ["message_id"], ["messages.id"], ondelete="CASCADE",
            name="fk_feedback_message_id_messages",
        ),
        sa.CheckConstraint("rating IN (-1, 1)", name="ck_feedback_rating"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("llm_extractions")
    op.drop_table("edges")
    op.drop_table("nodes")
