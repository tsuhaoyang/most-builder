"""v2_0034: wi_row_contexts（R3a / ADR-027 §4 / domain-evolution §7.2）

Revision ID: v2_0034
Revises: v2_0033
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0034"
down_revision = "v2_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wi_row_contexts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("wi_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column(
            "context_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("context_hash", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(["wi_row_id"], ["wi_rows.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("wi_row_id", name="uq_wi_row_contexts_wi_row_id"),
        sa.CheckConstraint(
            "source IN ('manual','imported','ai_assisted','system')",
            name="ck_wi_row_contexts_source",
        ),
    )
    op.create_index("ix_wi_row_contexts_schema_version", "wi_row_contexts", ["schema_version"])


def downgrade() -> None:
    op.drop_index("ix_wi_row_contexts_schema_version", table_name="wi_row_contexts")
    op.drop_table("wi_row_contexts")
