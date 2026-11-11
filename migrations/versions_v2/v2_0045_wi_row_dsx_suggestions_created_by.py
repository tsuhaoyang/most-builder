"""v2_0045: wi_row_dsx_suggestions.created_by／updated_by（checkpoint 修正輪，RBAC 稽核）

Revision ID: v2_0045
Revises: v2_0044
Create Date: 2026-08-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0045"
down_revision = "v2_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "wi_row_dsx_suggestions", sa.Column("created_by", sa.Text(), nullable=True)
    )
    op.add_column(
        "wi_row_dsx_suggestions", sa.Column("updated_by", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("wi_row_dsx_suggestions", "updated_by")
    op.drop_column("wi_row_dsx_suggestions", "created_by")
