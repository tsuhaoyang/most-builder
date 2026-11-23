"""工作區編輯區的草稿列（ADR-038 D2／D3；migration v2_0051）。

一列＝一個 motion（審核單位）。同一句 WI 拆出的 motion 共用 `group_key`。草稿不是工時表：
未經「寫入工時表」（`wi_draft_service.commit_drafts`）的內容不得出現在工時表、匯出、LB 投影或核准流程（ADR-038 I2）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, uuid_pk

DRAFT_SOURCES = ("manual", "ai_service", "rule_based", "imported")
DRAFT_STATUSES = ("pending", "confirmed", "committed")
STALE_REASONS = ("rule_set_changed", "import_row_changed")


class WiDraftRow(Base):
    __tablename__ = "wi_draft_rows"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False
    )
    group_key: Mapped[str] = mapped_column(Text, nullable=False)
    order_in_group: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    # 一列的完整輸入（schemas/v2/wi_draft.WiDraftContent 驗證）
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # AI 給的候選（顯示「哪些格是 AI 填的」用；不進計算）
    ai_candidates: Mapped[dict | None] = mapped_column(JSONB)
    ai_parse_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("ai_parse_runs.id", ondelete="SET NULL")
    )
    import_row_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("import_rows.id", ondelete="SET NULL")
    )
    source_revision: Mapped[int | None] = mapped_column(BigInteger)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_by: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    confirmed_by: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    committed_by: Mapped[str | None] = mapped_column(Text)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 軟參考（見 migration v2_0051 檔頭：整份取代的存檔會讓 FK 擋住或連帶刪除）
    committed_wi_row_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    # v2_0053（W3）：建立或最後確認時工時表的規則版本；改綁後已確認的草稿寫入時轉過期
    source_rule_set_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rule_sets.id", ondelete="SET NULL")
    )
    # v2_0053：解析產生的草稿在建立當下的紀錄（complete／issues／cycle_hash／import_input_hash／ai_status）
    parse_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    stale_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("source IN ('manual','ai_service','rule_based','imported')", name="source"),
        CheckConstraint("status IN ('pending','confirmed','committed')", name="status"),
        CheckConstraint(
            "stale_reason IS NULL OR stale_reason IN ('rule_set_changed','import_row_changed')", name="stale_reason"
        ),
        CheckConstraint(
            "status = 'pending' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
            name="confirmed_has_actor",
        ),
        CheckConstraint(
            "status <> 'committed' OR (committed_by IS NOT NULL AND committed_at IS NOT NULL "
            "AND committed_wi_row_id IS NOT NULL)",
            name="committed_has_actor",
        ),
        Index("ix_wi_draft_rows_worksheet_status", "worksheet_id", "status"),
        Index("ix_wi_draft_rows_worksheet_sort", "worksheet_id", "sort_order"),
    )
