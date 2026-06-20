"""動作範本庫（Motion Template Library）。

一魚兩吃：
- 建表效率：把常用 cycle 存成具名範本，一鍵插入再微調。
- 匯入自動建 MOST（P2）：以 `keywords` 比對匯入描述 → 套用 `cycle_template` 草擬 MOST。
`cycle_template` 直接存 CycleIn 形狀（payload）→ 前端 payloadToState 即可載入編輯器。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class MotionTemplate(Base, TimestampMixin):
    __tablename__ = "motion_templates"

    id: Mapped[UUID] = uuid_pk()
    site_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))  # NULL=全域；先不設 FK，保留彈性
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)           # 取放 / 鎖附 / 檢測 …
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    seq_kind: Mapped[str] = mapped_column(Text, nullable=False)  # GM / CM
    cycle_template: Mapped[dict] = mapped_column(JSONB, nullable=False)  # CycleIn 形狀
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))  # draft 個人草稿 / standard 廠標準
    owner: Mapped[str | None] = mapped_column(Text)              # 草稿擁有者員工編號（標準＝None）
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    created_by: Mapped[str | None] = mapped_column(Text)         # 員工編號

    __table_args__ = (
        CheckConstraint("seq_kind IN ('GM','CM')", name="seq_kind"),
        CheckConstraint("status IN ('draft','standard')", name="status"),
    )
