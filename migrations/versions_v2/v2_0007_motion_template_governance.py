"""v2 動作範本庫 混合治理：status(draft/standard) + owner。

既有(種入的起手範本)設為 standard＝廠標準。新建預設 draft＝個人草稿。

Revision ID: v2_0007
Revises: v2_0006
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0007"
down_revision = "v2_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("motion_templates", sa.Column("status", sa.Text(), server_default=sa.text("'draft'"), nullable=False))
    op.add_column("motion_templates", sa.Column("owner", sa.Text()))
    op.create_check_constraint("status", "motion_templates", "status IN ('draft','standard')")
    # 既有起手範本＝廠標準
    op.execute("UPDATE motion_templates SET status='standard' WHERE status='draft'")


def downgrade() -> None:
    op.drop_constraint("status", "motion_templates", type_="check")
    op.drop_column("motion_templates", "owner")
    op.drop_column("motion_templates", "status")
