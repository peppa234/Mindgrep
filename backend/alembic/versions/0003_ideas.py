"""ideas: extracted from notes, matched against projects, overridable by the user

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _node_fk(column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        [column], ["nodes.id"], ondelete="SET NULL", name=f"fk_ideas_{column}_nodes"
    )


def upgrade() -> None:
    op.create_table(
        "ideas",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("node_id", sa.BigInteger()),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("extractor", sa.String(16), nullable=False),
        sa.Column("line", sa.Integer()),
        sa.Column("evidence", sa.Text()),
        sa.Column("written_on", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("implemented_by_id", sa.BigInteger()),
        sa.Column("match", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("matched_at", sa.DateTime(timezone=True)),
        sa.Column("declared_status", sa.String(16)),
        sa.Column("declared_project", sa.Text()),
        sa.Column("declared_project_id", sa.BigInteger()),
        sa.Column("user_status", sa.String(16)),
        sa.Column("user_project_id", sa.BigInteger()),
        sa.Column("user_note", sa.Text()),
        sa.Column("overridden_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_ideas"),
        sa.UniqueConstraint("source_id", "key", name="uq_ideas_source_id"),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], ondelete="CASCADE", name="fk_ideas_source_id_sources"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE",
            name="fk_ideas_document_id_documents",
        ),
        _node_fk("node_id"),
        _node_fk("implemented_by_id"),
        _node_fk("declared_project_id"),
        _node_fk("user_project_id"),
        sa.CheckConstraint(
            "status IN ('implemented', 'partial', 'unimplemented')", name="ck_ideas_status"
        ),
        sa.CheckConstraint(
            "user_status IS NULL OR user_status IN "
            "('implemented', 'partial', 'unimplemented', 'abandoned')",
            name="ck_ideas_user_status",
        ),
    )
    op.create_index("ix_ideas_source_id", "ideas", ["source_id"])
    op.create_index("ix_ideas_document_id", "ideas", ["document_id"])
    op.create_index("ix_ideas_written_on", "ideas", ["written_on"])
    op.create_index("ix_ideas_implemented_by_id", "ideas", ["implemented_by_id"])


def downgrade() -> None:
    op.drop_table("ideas")
