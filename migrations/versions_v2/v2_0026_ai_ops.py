"""v2_0026: WI AI operational tables + rule_based deployment bundle seed

ai_deployment_bundles / ai_parse_runs / ai_review_events / ai_feedback_candidates
Spec: docs/llm/wi-ai-parser-implementation-spec.md §12

Revision ID: v2_0026
Revises: v2_0025
Create Date: 2026-08-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0026"
down_revision = "v2_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_deployment_bundles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.UniqueConstraint("code", name="uq_ai_deployment_bundles_code"),
        sa.CheckConstraint("kind IN ('rule_based', 'llm')", name="ck_ai_deployment_bundles_kind"),
        sa.CheckConstraint(
            "status IN ('draft', 'shadow', 'active', 'retired')",
            name="ck_ai_deployment_bundles_status",
        ),
    )

    op.create_table(
        "ai_parse_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_kind", sa.Text(), nullable=False),
        sa.Column("worksheet_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("import_row_index", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("input_hash", sa.Text(), nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("context_hash", sa.Text(), nullable=False),
        sa.Column(
            "rule_set_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rule_sets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "bundle_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_deployment_bundles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column(
            "slot_candidates",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "drafts",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("llm_raw_response", postgresql.JSONB(), nullable=True),
        sa.Column("routing_status", sa.Text(), nullable=False),
        sa.Column(
            "routing_reasons",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "cached",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("latency", postgresql.JSONB(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('interactive', 'import_row')",
            name="ck_ai_parse_runs_source_kind",
        ),
        sa.CheckConstraint(
            "routing_status IN ('auto', 'review', 'abstain', 'invalid')",
            name="ck_ai_parse_runs_routing_status",
        ),
    )
    op.create_index("ix_ai_parse_runs_input_hash", "ai_parse_runs", ["input_hash"])
    op.create_index("ix_ai_parse_runs_created_at", "ai_parse_runs", ["created_at"])
    op.create_index("ix_ai_parse_runs_bundle_id", "ai_parse_runs", ["bundle_id"])

    op.create_table(
        "ai_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_parse_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("target", postgresql.JSONB(), nullable=True),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.Text(), nullable=False),
        sa.Column("ui_version", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'accept_plan','split_action','merge_actions','reorder_action',"
            "'add_action','delete_action','replace_role','replace_candidate',"
            "'change_sequence_model','change_quantity_policy','mark_missing',"
            "'accept_all')",
            name="ck_ai_review_events_event_type",
        ),
    )
    op.create_index("ix_ai_review_events_run_id", "ai_review_events", ["run_id"])

    op.create_table(
        "ai_feedback_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "review_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ai_review_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'candidate'"),
        ),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "kind IN ('synonym', 'few_shot', 'gold', 'calibration')",
            name="ck_ai_feedback_candidates_kind",
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected', 'promoted')",
            name="ck_ai_feedback_candidates_status",
        ),
    )

    # Seed active rule-based bundle (wi-ai-dev-000)
    op.execute(
        sa.text(
            """
            INSERT INTO ai_deployment_bundles
                (id, code, kind, model, prompt_version, config, status, created_by)
            VALUES
                (
                    gen_random_uuid(),
                    'wi-ai-dev-000',
                    'rule_based',
                    NULL,
                    NULL,
                    '{"response_format_mode": "none"}'::jsonb,
                    'active',
                    'system'
                )
            ON CONFLICT (code) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("ai_feedback_candidates")
    op.drop_index("ix_ai_review_events_run_id", table_name="ai_review_events")
    op.drop_table("ai_review_events")
    op.drop_index("ix_ai_parse_runs_bundle_id", table_name="ai_parse_runs")
    op.drop_index("ix_ai_parse_runs_created_at", table_name="ai_parse_runs")
    op.drop_index("ix_ai_parse_runs_input_hash", table_name="ai_parse_runs")
    op.drop_table("ai_parse_runs")
    op.drop_table("ai_deployment_bundles")
