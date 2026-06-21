"""v2 動作範本庫 motion_templates（建表效率 + 匯入自動建 MOST 的核心資產）。

Revision ID: v2_0006
Revises: v2_0005
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0006"
down_revision = "v2_0005"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "motion_templates",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("site_id", _UUID),
        sa.Column("name_zh", sa.Text(), nullable=False),
        sa.Column("name_en", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False),
        sa.Column("seq_kind", sa.Text(), nullable=False),
        sa.Column("cycle_template", postgresql.JSONB(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("created_by", sa.Text()),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_motion_templates"),
        sa.CheckConstraint("seq_kind IN ('GM','CM')", name="seq_kind"),
    )


def downgrade() -> None:
    op.drop_table("motion_templates")
