"""Transactional outbox（R3b / ADR-027 §5 / domain-evolution §11.2）。

Append-only 列；成功發布改 status，不刪。Consumer at-least-once，以 id 去重。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

_STATUS_CK = "status IN ('pending','published','failed','dead_letter')"


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id: Mapped[UUID] = uuid_pk()
    event_no: Mapped[int] = mapped_column(BigInteger, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    aggregate_revision: Mapped[int | None] = mapped_column(BigInteger)
    payload_schema_version: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_STATUS_CK, name="status"),
        CheckConstraint("event_no >= 1", name="event_no_pos"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonneg"),
        UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "event_no",
            name="uq_outbox_events_aggregate_event_no",
        ),
        Index(
            "ix_outbox_events_claim",
            "status",
            "next_attempt_at",
            "created_at",
        ),
        Index(
            "ix_outbox_events_aggregate",
            "aggregate_type",
            "aggregate_id",
            "event_no",
        ),
    )
