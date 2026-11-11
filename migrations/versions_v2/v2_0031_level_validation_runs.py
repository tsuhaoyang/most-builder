"""v2_0031: level_validation_runs（R2b / ADR-027 §9）

Revision ID: v2_0031
Revises: v2_0030
Create Date: 2026-08-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0031"
down_revision = "v2_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "level_validation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worksheet_revision", sa.BigInteger(), nullable=False),
        sa.Column("level_policy_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column(
            "issues_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_contract_version", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["worksheet_id"], ["most_worksheets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["level_policy_version_id"],
            ["level_policy_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "trigger IN ('interactive','save','publish','revalidate')",
            name="ck_level_validation_runs_trigger",
        ),
        sa.UniqueConstraint(
            "worksheet_id",
            "worksheet_revision",
            "level_policy_version_id",
            "input_hash",
            name="uq_level_validation_runs_ws_rev_policy_hash",
        ),
    )
    op.create_index(
        "ix_level_validation_runs_ws_rev_created",
        "level_validation_runs",
        ["worksheet_id", "worksheet_revision", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_level_validation_runs_ws_rev_created",
        table_name="level_validation_runs",
    )
    op.drop_table("level_validation_runs")
