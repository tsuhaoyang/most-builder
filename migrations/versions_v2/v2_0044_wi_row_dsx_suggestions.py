"""v2_0044: wi_row_dsx_suggestions（DSX 整合 API 契約 v2 §2.2；ADR-031 D4／I4）

Revision ID: v2_0044
Revises: v2_0043
Create Date: 2026-08-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0044"
down_revision = "v2_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wi_row_dsx_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("wi_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("a_slot_key", sa.Text(), nullable=False),
        sa.Column("from_vocab_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("to_vocab_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("raw_distance_cm", sa.Numeric(10, 3), nullable=False),
        sa.Column(
            "dsx_response",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ie_action", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["from_vocab_id"], ["work_vocab_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["to_vocab_id"], ["work_vocab_items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "wi_row_id", "a_slot_key", name="uq_wi_row_dsx_suggestions_row_slot"
        ),
        sa.CheckConstraint("a_slot_key IN ('a3')", name="ck_wi_row_dsx_suggestions_a_slot_key"),
    )


def downgrade() -> None:
    op.drop_table("wi_row_dsx_suggestions")
