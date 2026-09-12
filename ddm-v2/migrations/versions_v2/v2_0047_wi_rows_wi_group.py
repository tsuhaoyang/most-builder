"""v2_0047: wi_rows.wi_group（作業名稱；ADR-035 D10 作業版 UI）

同一 worksheet 內同名＝同一作業的候選成員；四條輸入路徑（手動／AI 草稿／Excel 匯入／
模組實體化）在建列時填。加法演進（ADR-011）：nullable，不影響既有列。

Revision ID: v2_0047
Revises: v2_0046
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0047"
down_revision = "v2_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("wi_rows", sa.Column("wi_group", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("wi_rows", "wi_group")
