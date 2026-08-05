"""Allow worksheet rows without object vocabulary.

Motion-module rows may legitimately omit object_vocab_id (for example machine or
fixture operations). Calculation uses cycle inputs, not vocabulary metadata, so
requiring an object caused from-module instantiation to drop otherwise valid rows.

Revision ID: v2_0025
Revises: v2_0024
Create Date: 2026-08-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0025"
down_revision = "v2_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "wi_rows",
        "object_vocab_id",
        existing_type=sa.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "wi_rows",
        "object_vocab_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
