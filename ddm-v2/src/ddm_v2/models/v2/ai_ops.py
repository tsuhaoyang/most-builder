"""AI operational tables（WI AI Parser L0）。

Spec：docs/llm/wi-ai-parser-implementation-spec.md §12
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
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
