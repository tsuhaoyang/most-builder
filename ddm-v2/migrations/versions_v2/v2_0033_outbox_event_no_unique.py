"""v2_0033: outbox_events UNIQUE(aggregate_type, aggregate_id, event_no)

Revision ID: v2_0033
Revises: v2_0032
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op

revision = "v2_0033"
down_revision = "v2_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_outbox_events_aggregate_event_no",
        "outbox_events",
        ["aggregate_type", "aggregate_id", "event_no"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_outbox_events_aggregate_event_no",
        "outbox_events",
        type_="unique",
    )
