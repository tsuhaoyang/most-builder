"""v2_0048: level_entries.machine_unattended（第 9 個 LB 標記，三態；ADR-035 D10 §3.4 / B7）

Boolean NULL 三態：null=未回答、false=人要顧、true=人不用顧。
語意：role_type=machine ⇔ CM ∧ x_seconds≥1 ∧ machine_unattended==true（事實在 MOST、政策在 LB）。
加法演進（ADR-011）：nullable，不設 server_default（未回答＝NULL）。

Revision ID: v2_0048
Revises: v2_0047
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0048"
down_revision = "v2_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("level_entries", sa.Column("machine_unattended", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("level_entries", "machine_unattended")
