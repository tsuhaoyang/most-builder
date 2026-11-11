"""v2_0029: most_worksheets revision optimistic locking（R1 / ADR-027 §2）

Revision ID: v2_0029
Revises: v2_0028
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0029"
down_revision = "v2_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "most_worksheets",
        sa.Column(
            "revision_no",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column("most_worksheets", sa.Column("content_hash", sa.Text(), nullable=True))
    op.add_column("most_worksheets", sa.Column("last_edited_by", sa.Text(), nullable=True))
    op.add_column(
        "most_worksheets",
        sa.Column("last_edited_at", sa.DateTime(timezone=True), nullable=True),
    )

    # AI run 綁定 worksheet 時記錄來源 revision（ADR-027 §2 / spec §6.4）
    op.add_column(
        "ai_parse_runs",
        sa.Column("source_revision", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_parse_runs", "source_revision")
    op.drop_column("most_worksheets", "last_edited_at")
    op.drop_column("most_worksheets", "last_edited_by")
    op.drop_column("most_worksheets", "content_hash")
    op.drop_column("most_worksheets", "revision_no")
