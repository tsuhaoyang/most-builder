"""BOM 暫存與料表（Q3 預留）：bom_imports(staging) → bom_items(料表)。

依據 data-model-and-storage-spec §4。外部 BOM 先落 staging 驗證，再併入 bom_items；
日後「BOM→sequence model 草稿產生器」讀 bom_items 產出 wi_row 草稿（provenance=bom_draft）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class BomImport(Base, TimestampMixin):
    """外部 BOM 匯入暫存（不直接進核心表）。"""

    __tablename__ = "bom_imports"

    id: Mapped[UUID] = uuid_pk()
    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'plm'"))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pending'"))
    imported_by: Mapped[str | None] = mapped_column(Text)  # 員工編號（RBAC）
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (CheckConstraint("status IN ('pending','validated','merged','failed')", name="status"),)


class BomItem(Base, TimestampMixin):
    """併入後的 BOM 料表（樹狀；元件對應 work_vocab_items kind=component）。"""

    __tablename__ = "bom_items"

    id: Mapped[UUID] = uuid_pk()
    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    parent_item_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("bom_items.id", ondelete="CASCADE"))
    component_vocab_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, server_default=text("1"))
    bom_level: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
