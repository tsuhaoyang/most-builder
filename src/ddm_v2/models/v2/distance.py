"""距離建議（ADR-038 D5.6；migration v2_0055）。

一列一格；是建議不是值（ADR-031 I4）。`wi_row_id` 是軟參考、沒有 FK（整份存檔會刪除重建 wi_rows，id 沿用；
有 FK 會每次存檔都連帶刪掉建議）。列被刪後留下的建議由讀取時過濾、下次計算時清掉。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

SUGGESTION_SLOTS = ("a0", "a3", "m3", "a6")
SUGGESTION_STATUSES = ("suggested", "needs_ie", "unavailable")


class WiRowDistanceSuggestion(Base):
    __tablename__ = "wi_row_distance_suggestions"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False
    )
    wi_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    slot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # suggested 時要填哪個欄位：a0／a3 的 reach_cm｜foot_cm、a6 的 reach_cm、m3 的 distance_cm（ladder 動詞）
    field: Mapped[str | None] = mapped_column(Text)
    distance_cm: Mapped[Decimal | None] = mapped_column(Numeric(8, 1))
    reason: Mapped[str | None] = mapped_column(Text)
    # {"from": Endpoint, "to": Endpoint}；Endpoint 見 distance_service.Endpoint.as_json
    endpoints: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    snapshot_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("sku_placement_snapshots.id", ondelete="SET NULL")
    )
    threshold_cm: Mapped[Decimal] = mapped_column(Numeric(8, 1), nullable=False)
    person_offset_cm: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    modeling_policy_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("modeling_policy_versions.id", ondelete="RESTRICT")
    )
    computed_by: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    applied_by: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("worksheet_id", "wi_row_id", "slot", name="uq_wi_row_distance_suggestions_ws_row_slot"),
        CheckConstraint("slot IN ('a0','a3','m3','a6')", name="slot"),
        CheckConstraint("status IN ('suggested','needs_ie','unavailable')", name="status"),
        CheckConstraint("field IS NULL OR field IN ('reach_cm','foot_cm','distance_cm')", name="field"),
        CheckConstraint(
            "status <> 'suggested' OR (field IS NOT NULL AND distance_cm IS NOT NULL)", name="suggested_has_value"
        ),
        Index("ix_wi_row_distance_suggestions_worksheet", "worksheet_id", "wi_row_id"),
    )


class ModelingPolicyDefault(Base):
    """新建工時表用哪個建模政策版本（明確指定，不以 MAX(version_no) 隱式選版；R2a）。"""

    __tablename__ = "modeling_policy_defaults"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("modeling_policy_versions.id", ondelete="RESTRICT"), nullable=False
    )
    set_by: Mapped[str] = mapped_column(Text, nullable=False)
    set_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
