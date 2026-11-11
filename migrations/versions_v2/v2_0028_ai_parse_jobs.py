"""v2_0028: import_rows + ai_parse_jobs / ai_parse_job_items（L4 / ADR-027 §12）

Revision ID: v2_0028
Revises: v2_0027
Create Date: 2026-08-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0028"
down_revision = "v2_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("excel_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("raw_data", postgresql.JSONB(), nullable=True),
        sa.Column("normalized_data", postgresql.JSONB(), nullable=False),
        sa.Column(
            "schema_version",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'import-row-v1'"),
        ),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'staged'")),
        sa.Column(
            "selected_for_submit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
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
            "import_id", "source_row_no", name="uq_import_rows_import_source_row"
        ),
        sa.CheckConstraint(
            "status IN ("
            "'staged','queued','processing','review','ready','failed','skipped','submitted')",
            name="ck_import_rows_status",
        ),
    )
    op.create_index("ix_import_rows_import_id", "import_rows", ["import_id"])

    op.create_table(
        "ai_parse_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column(
            "import_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("excel_imports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deployment_bundle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_deployment_bundles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "rule_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("projection_hash", sa.Text(), nullable=True),
        sa.Column("modeling_policy_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("processed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("succeeded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("requested_by", sa.Text(), nullable=False),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_ai_parse_jobs_idempotency_key"),
        sa.CheckConstraint(
            "status IN ('queued','running','partial','completed','failed','cancelled')",
            name="ck_ai_parse_jobs_status",
        ),
    )
    op.create_index("ix_ai_parse_jobs_import_id", "ai_parse_jobs", ["import_id"])

    op.create_table(
        "ai_parse_job_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_parse_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "import_row_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("import_rows.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ai_parse_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_parse_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", postgresql.JSONB(), nullable=True),
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
        sa.UniqueConstraint("job_id", "import_row_id", name="uq_ai_parse_job_items_job_row"),
        sa.CheckConstraint(
            "status IN ("
            "'queued','leased','running','review','ready','failed','cancelled')",
            name="ck_ai_parse_job_items_status",
        ),
    )
    op.create_index(
        "ix_ai_parse_job_items_claim",
        "ai_parse_job_items",
        ["status", "available_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_parse_job_items_claim", table_name="ai_parse_job_items")
    op.drop_table("ai_parse_job_items")
    op.drop_index("ix_ai_parse_jobs_import_id", table_name="ai_parse_jobs")
    op.drop_table("ai_parse_jobs")
    op.drop_index("ix_import_rows_import_id", table_name="import_rows")
    op.drop_table("import_rows")
