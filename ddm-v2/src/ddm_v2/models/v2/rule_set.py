"""版本化 MOST 規則集（表頭）。子表（A 三分量 / B / G / P / M / X / I）見 rule_set_tables.py（2b）。

依據 data-model-and-storage-spec §1.5（規則為版本化資料）、system-architecture-v2 §3（單一引擎讀此）。
治理：IE 編 draft、manager+ publish；發布前須通過完整性檢查（E5）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class RuleSet(Base, TimestampMixin):
    __tablename__ = "rule_sets"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # 例 MINIMOST_FACTORY_V1
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    system_tmu_multiplier: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("1"))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(Text)  # 員工編號（manager+）
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (CheckConstraint("status IN ('draft','published','retired')", name="status"),)
