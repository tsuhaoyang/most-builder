"""v2_0019：建立 wi_set_projects 與 wi_set_items 資料表。

Revision ID: v2_0019
Revises: v2_0018
Create Date: 2026-07-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0019"
down_revision = "v2_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wi_set_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("site", sa.Text(), nullable=True),
        sa.Column("bu", sa.Text(), nullable=True),
        sa.Column("process", sa.Text(), nullable=True),
        sa.Column("family", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "status IN ('draft','active','archived')",
            name="ck_wi_set_projects_status_valid",
        ),
        sa.UniqueConstraint("project_code", name="uq_wi_set_projects_project_code"),
    )

    op.create_table(
        "wi_set_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wi_set_projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq_no", sa.Integer(), nullable=False),
        sa.Column("wi_template_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("wi_code_snapshot", sa.Text(), nullable=True),
        sa.Column("wi_name_snapshot", sa.Text(), nullable=False),
        sa.Column(
            "action_count_snapshot",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_tmu_snapshot",
            sa.Numeric(12, 3),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_seconds_snapshot",
            sa.Numeric(12, 4),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "project_id", "seq_no", name="uq_wi_set_items_project_id_seq_no"
        ),
    )


def downgrade() -> None:
    op.drop_table("wi_set_items")
    op.drop_table("wi_set_projects")
