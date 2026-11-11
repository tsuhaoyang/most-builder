"""Level validation run 證據（R2b / ADR-027 §3 / domain-evolution §9.4–9.5）。

Append-only：不可作為 level_entries 的第二份可寫真相。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

_TRIGGER_CK = "trigger IN ('interactive','save','publish','revalidate')"


class LevelValidationRun(Base):
    __tablename__ = "level_validation_runs"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("most_worksheets.id", ondelete="CASCADE"),
        nullable=False,
    )
    worksheet_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    level_policy_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("level_policy_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    issues_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    output_json: Mapped[dict | None] = mapped_column(JSONB)
    output_contract_version: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    __table_args__ = (
        UniqueConstraint(
            "worksheet_id",
            "worksheet_revision",
            "level_policy_version_id",
            "input_hash",
            name="uq_level_validation_runs_ws_rev_policy_hash",
        ),
        CheckConstraint(_TRIGGER_CK, name="trigger"),
        Index(
            "ix_level_validation_runs_ws_rev_created",
            "worksheet_id",
            "worksheet_revision",
            "created_at",
        ),
    )
