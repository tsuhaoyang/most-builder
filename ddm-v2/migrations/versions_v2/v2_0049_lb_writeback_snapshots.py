"""v2_0049: LB 回寫消費——lb_writeback_snapshots + lb_row_placements（ADR-036 B1/B2）

回寫落地為快照（ADR-036 D4）：每次取得存一筆 snapshot（含原始 payload）＋逐列 placement。
加法演進（ADR-011）：兩張新表，不動既有表。snapshot 另帶 applied_at／applied_rows（B6 套用紀錄）。

Revision ID: v2_0049
Revises: v2_0048
Create Date: 2026-09-17
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0049"
down_revision = "v2_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lb_writeback_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contract_version", sa.Text(), nullable=False),
        sa.Column("lb_project_id", sa.Text(), nullable=False),
        sa.Column("lb_version_id", sa.Text(), nullable=False),
        sa.Column("lb_result_id", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("unattended_machine_policy", sa.Text(), nullable=False),
        sa.Column("unattended_machine_policy_source", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=False),
        # B6 套用紀錄（apply-offline）：套用時間與套用的列（含傳染），未套用為 NULL。
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_rows", postgresql.JSONB(), nullable=True),
    )
    op.create_index(
        "ix_lb_writeback_snapshots_worksheet_fetched",
        "lb_writeback_snapshots", ["worksheet_id", sa.text("fetched_at DESC")],
    )

    op.create_table(
        "lb_row_placements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("lb_writeback_snapshots.id", ondelete="CASCADE"), nullable=False),
        # source_wi_row_id 不設 FK：可能指向已刪除或別份 worksheet 的列（比對在應用層）。
        sa.Column("source_wi_row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=True),
        sa.Column("station_index", sa.Integer(), nullable=True),
        sa.Column("workers", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("units", postgresql.JSONB(), nullable=True),
        sa.Column("offline_flag", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_lb_row_placements_snapshot", "lb_row_placements", ["snapshot_id"])
    op.create_index("ix_lb_row_placements_snapshot_source",
                    "lb_row_placements", ["snapshot_id", "source_wi_row_id"])


def downgrade() -> None:
    op.drop_index("ix_lb_row_placements_snapshot_source", table_name="lb_row_placements")
    op.drop_index("ix_lb_row_placements_snapshot", table_name="lb_row_placements")
    op.drop_table("lb_row_placements")
    op.drop_index("ix_lb_writeback_snapshots_worksheet_fetched", table_name="lb_writeback_snapshots")
    op.drop_table("lb_writeback_snapshots")
