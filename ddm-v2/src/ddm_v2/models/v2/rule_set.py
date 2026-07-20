"""版本化 MOST 規則集（表頭）。子表（A 三分量 / B / G / P / M / X / I）見 rule_set_tables.py（2b）。

依據 data-model-and-storage-spec §1.5（規則為版本化資料）、system-architecture-v2 §3（單一引擎讀此）。
治理：IE 編 draft、manager+ publish；發布前須通過完整性檢查（E5）。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class RuleSet(Base, TimestampMixin):
    __tablename__ = "rule_sets"

    id: Mapped[UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # 例 MINIMOST_FACTORY_V1
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    # ADR-023 §3.2：治理旗標。全庫恆有且僅有一個 true（partial unique index 於 DB 層保證）。
    # ⚠️ 只在「選擇」時生效；load_rule_set_from_db 的回放路徑不得依此過濾（§3.4 鐵則）。
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # ADR-023 §3.3 規則 3：認證血緣。certified_import＝由 import_v3_dictionary.py → seed 產生（ADR-014），
    # 該類版本 D2 起禁任何選項級寫入（即使 status='draft'）。
    provenance: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    system_tmu_multiplier: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False, server_default=text("1"))
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[str | None] = mapped_column(Text)  # 員工編號（manager+）
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('draft','published','retired')", name="status"),
        CheckConstraint("provenance IN ('certified_import','manual','cloned')", name="provenance"),
        # 單一 active 版本：partial unique index on 常數表示式（併發雙 activate 撞 unique）。
        Index("uq_rule_sets_single_active", text("(true)"), unique=True, postgresql_where=text("is_active")),
    )
