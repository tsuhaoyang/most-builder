"""AI operational tables（WI AI Parser L0＋L4 批次）。

Spec：docs/llm/wi-ai-parser-implementation-spec.md §12（AI 表）／§13（L4 批次邊界）
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk


class AiDeploymentBundle(Base):
    __tablename__ = "ai_deployment_bundles"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_ai_deployment_bundles_code"),
        CheckConstraint("kind IN ('rule_based', 'llm')", name="kind"),
        CheckConstraint(
            "status IN ('draft', 'shadow', 'active', 'retired')",
            name="status",
        ),
    )


class AiParseRun(Base):
    __tablename__ = "ai_parse_runs"

    id: Mapped[UUID] = uuid_pk()
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    worksheet_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    import_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    import_row_index: Mapped[int | None] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    context_hash: Mapped[str] = mapped_column(Text, nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bundle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_deployment_bundles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    slot_candidates: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    drafts: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    llm_raw_response: Mapped[dict | None] = mapped_column(JSONB)
    routing_status: Mapped[str] = mapped_column(Text, nullable=False)
    routing_reasons: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cached: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    latency: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[dict | None] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    # R1：綁 worksheet 時的來源 revision（未綁則 NULL）；與 migration BigInteger 對齊
    source_revision: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('interactive', 'import_row')",
            name="source_kind",
        ),
        CheckConstraint(
            "routing_status IN ('auto', 'review', 'abstain', 'invalid')",
            name="routing_status",
        ),
        sa.Index("ix_ai_parse_runs_input_hash", "input_hash"),
        sa.Index("ix_ai_parse_runs_created_at", "created_at"),
        sa.Index("ix_ai_parse_runs_bundle_id", "bundle_id"),
        UniqueConstraint(
            "input_hash",
            "bundle_id",
            name="uq_ai_parse_runs_input_hash_bundle_id",
        ),
    )


class AiReviewEvent(Base):
    __tablename__ = "ai_review_events"

    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_parse_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict | None] = mapped_column(JSONB)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(Text, nullable=False)
    ui_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            "'accept_plan','split_action','merge_actions','reorder_action',"
            "'add_action','delete_action','replace_role','replace_candidate',"
            "'change_sequence_model','change_quantity_policy','mark_missing',"
            "'accept_all')",
            name="event_type",
        ),
        sa.Index("ix_ai_review_events_run_id", "run_id"),
    )


class AiFeedbackCandidate(Base):
    __tablename__ = "ai_feedback_candidates"

    id: Mapped[UUID] = uuid_pk()
    review_event_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_review_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'candidate'")
    )
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('synonym', 'few_shot', 'gold', 'calibration')",
            name="kind",
        ),
        CheckConstraint(
            "status IN ('candidate', 'approved', 'rejected', 'promoted')",
            name="status",
        ),
    )


class AiParseJob(Base):
    """批次 parse job（spec §13；schema 佈局同 §12 的 AI 表批次）。"""

    __tablename__ = "ai_parse_jobs"

    id: Mapped[UUID] = uuid_pk()
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    import_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("excel_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    deployment_bundle_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_deployment_bundles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rule_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    projection_hash: Mapped[str | None] = mapped_column(Text)
    # R2a：可 NULL（job 未 pin）；有值則 RESTRICT 回放
    modeling_policy_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("modeling_policy_versions.id", ondelete="RESTRICT"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        # idempotency 以 import 為範圍（security F3）：key 是 client 可控字串，
        # 全域唯一會讓跨 import 撞 key 的人拿到（或擋掉）別人的 job。
        UniqueConstraint(
            "import_id",
            "idempotency_key",
            name="uq_ai_parse_jobs_import_idempotency_key",
        ),
        CheckConstraint(
            "status IN ('queued','running','partial','completed','failed','cancelled')",
            name="status",
        ),
        sa.Index("ix_ai_parse_jobs_import_id", "import_id"),
        # worker 的 _runnable_jobs 掃描（status IN runnable ORDER BY created_at）：
        # partial index 只收在途列，終態列堆積不拖慢輪詢。
        sa.Index(
            "ix_ai_parse_jobs_active_created",
            "created_at",
            postgresql_where=sa.text("status IN ('queued','running')"),
        ),
    )


class AiParseJobItem(Base):
    """Job 內單列 work item（lease／retry）。"""

    __tablename__ = "ai_parse_job_items"

    id: Mapped[UUID] = uuid_pk()
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_parse_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    import_row_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_rows.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_parse_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ai_parse_runs.id", ondelete="SET NULL"),
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'queued'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    lease_owner: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint("job_id", "import_row_id", name="uq_ai_parse_job_items_job_row"),
        CheckConstraint(
            "status IN ("
            "'queued','leased','running','review','ready','failed','cancelled')",
            name="status",
        ),
        sa.Index("ix_ai_parse_job_items_claim", "status", "available_at"),
    )
