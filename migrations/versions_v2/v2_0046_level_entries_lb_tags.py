"""v2_0046: level_entries 加 8 個 LB 標記欄（ADR-035 D7；加法演進 ADR-011）

worker_cub text / offline bool / segment text / station_pin int /
is_general bool / general_role text / merge_lock bool / action_type text
（machine_count／manpower 保留，僅停止匯出 D16；本 migration 不動）

Revision ID: v2_0046
Revises: v2_0045
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0046"
down_revision = "v2_0045"
branch_labels = None
depends_on = None

_BOOL_COLS = ("offline", "is_general", "merge_lock")
_TEXT_COLS = ("worker_cub", "segment", "general_role", "action_type")


def upgrade() -> None:
    for col in _BOOL_COLS:
        op.add_column(
            "level_entries",
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    for col in _TEXT_COLS:
        op.add_column("level_entries", sa.Column(col, sa.Text(), nullable=True))
    op.add_column("level_entries", sa.Column("station_pin", sa.Integer(), nullable=True))
    # general_role 值域護欄（Spec §5.7）：NULL 或三值之一
    op.create_check_constraint(
        "general_role_enum",
        "level_entries",
        "general_role IS NULL OR general_role IN ('take_unit','scanner','transport')",
    )


def downgrade() -> None:
    op.drop_constraint("general_role_enum", "level_entries", type_="check")
    for col in ("station_pin", *_TEXT_COLS, *_BOOL_COLS):
        op.drop_column("level_entries", col)
