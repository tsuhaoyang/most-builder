"""v2_0027: UNIQUE(input_hash, bundle_id) for ai_parse_runs idempotency

Code review L0 P2：並發同輸入不得雙 INSERT。
先清重複列（保留最新），再加唯一約束。

Revision ID: v2_0027
Revises: v2_0026
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0027"
down_revision = "v2_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM ai_parse_runs a
            USING ai_parse_runs b
            WHERE a.input_hash = b.input_hash
              AND a.bundle_id = b.bundle_id
              AND a.created_at < b.created_at
            """
        )
    )
    # 同時間戳殘餘：保留較新 id
    op.execute(
        sa.text(
            """
            DELETE FROM ai_parse_runs a
            USING ai_parse_runs b
            WHERE a.input_hash = b.input_hash
              AND a.bundle_id = b.bundle_id
              AND a.id < b.id
            """
        )
    )
    op.create_unique_constraint(
        "uq_ai_parse_runs_input_hash_bundle_id",
        "ai_parse_runs",
        ["input_hash", "bundle_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_ai_parse_runs_input_hash_bundle_id",
        "ai_parse_runs",
        type_="unique",
    )
