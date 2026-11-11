"""v2 Level 巢狀：level_entries.parent_countersignature（C2，支援 sub⊃cub）。

依據 level-system-core-logic-spec（巢狀深度 main→sub→cub）。

Revision ID: v2_0005
Revises: v2_0004
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0005"
down_revision = "v2_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("level_entries", sa.Column("parent_countersignature", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("level_entries", "parent_countersignature")
