"""DSX a3 距離建議快照（DSX 整合 API 契約 v2 §2.2；ADR-031 D4／I4）。

**不是**權威——未經 IE 確認的距離不得寫入 `most_cycles.slot_inputs`。這張表只存
「查詢結果與出處」，供 UI 顯示建議值＋事後追溯（R5：採用率／改值率，非 MVP 必須）。

⚠️ 契約 v2 §2.2 的更正：不與既有 `wi_row_contexts` 共用同一列——後者是
`extra="forbid"` 的品保/安全備註固定欄位集、且整列覆蓋（`UniqueConstraint(wi_row_id)`），
塞距離建議進去要嘛被 pydantic 直接拒絕，要嘛在 IE 編輯 safety_notes 時被靜默覆蓋掉。
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk

_A_SLOT_KEY_CK = "a_slot_key IN ('a3')"


class WiRowDsxSuggestion(Base, TimestampMixin):
    """一筆 DSX 查詢結果快照（`(wi_row_id, a_slot_key)` upsert，同鍵第二次查詢覆蓋舊筆）。"""

    __tablename__ = "wi_row_dsx_suggestions"

    id: Mapped[UUID] = uuid_pk()
    wi_row_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("wi_rows.id", ondelete="CASCADE"), nullable=False
    )
    # MVP 只會出現 'a3'；先開好欄位，a0／a6 解禁（ADR-031 §0.2）後不必改表。
    a_slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    from_vocab_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"), nullable=False
    )
    to_vocab_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"), nullable=False
    )
    raw_distance_cm: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    # DSX 回應原樣保存（I1：不做任何轉換或取整）。
    dsx_response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    queried_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "accepted_as_reach" | "accepted_as_foot" | "overridden" | "dismissed"；加分項非 MVP 必須。
    ie_action: Mapped[str | None] = mapped_column(Text)
    # 比照 WiRowContext：查詢者員編（require_role("analyst") 保證非匿名）。
    created_by: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("wi_row_id", "a_slot_key", name="uq_wi_row_dsx_suggestions_row_slot"),
        CheckConstraint(_A_SLOT_KEY_CK, name="a_slot_key"),
    )
