"""組件庫（Motion Module Library）：持久化可版本化動作模組（impl-04 / ADR-017）。

MotionModule：模組元資料（scope/owner/status/current_version）。
MotionModuleVersion：不可變版本快照（rows JSONB + 引擎算出的 total_tmu/narrative_zh）。

版本列發布後禁 UPDATE（service 層擋）；修改＝發新版 current_version+1。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class MotionModule(Base, TimestampMixin):
    """動作模組（multi-cycle 組件單元，可含 1..n 列）。"""

    __tablename__ = "motion_modules"

    id: Mapped[UUID] = uuid_pk()
    site_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="SET NULL"),
        nullable=True,
    )
    name_zh: Mapped[str] = mapped_column(Text, nullable=False)
    # ADR-024 §4：只作為 ADR-022 的兩層判別值（'action' ／ 'wi-template'），
    # 不得再承載領域分類（取放／組裝／鎖附…）。
    # 值域由兩個約束合力守住（D9b）：
    #   - NOT NULL（v2_0023）              不能沒有值
    #   - ck_motion_modules_category_valid 只能是這兩個值
    # ⚠️ 兩者缺一不可：CHECK 只在謂詞為 FALSE 時拒絕，而 `NULL IN (...)` 求值為 NULL，
    # 所以單靠 CHECK 擋不住 NULL——而 NULL 的模組兩層皆不屬，正是隱形列 bug 的原始形狀。
    category: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )
    scope: Mapped[str] = mapped_column(Text, nullable=False)   # personal / site / global
    owner: Mapped[str | None] = mapped_column(Text)            # 員工編號；personal 必填
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'draft'")
    )  # draft / standard / retired
    current_version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )  # 0 = 尚無發布版

    versions: Mapped[list[MotionModuleVersion]] = relationship(
        back_populates="module",
        order_by="MotionModuleVersion.version_no",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "scope IN ('personal','site','global')", name="ck_motion_modules_scope_valid"
        ),
        CheckConstraint(
            "status IN ('draft','standard','retired')", name="ck_motion_modules_status_valid"
        ),
        CheckConstraint(
            "scope != 'personal' OR owner IS NOT NULL", name="ck_motion_modules_personal_owner"
        ),
        # ADR-024 §4（v2_0022 建立 CHECK，v2_0023 補 NOT NULL）。見上方欄位註解。
        CheckConstraint(
            "category IN ('action','wi-template')", name="ck_motion_modules_category_valid"
        ),
    )


class MotionModuleVersion(Base):
    """不可變版本快照（發布後禁 UPDATE）。"""

    __tablename__ = "motion_module_versions"

    id: Mapped[UUID] = uuid_pk()
    module_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("motion_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("rule_sets.id", ondelete="RESTRICT"),
        nullable=False,
    )  # 快照：發布當下規則版
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)
    # [{sub_activity?, hand, frequency, simo_pair_index?, vocab_refs{...}, cycle: CycleIn}]
    narrative_zh: Mapped[str | None] = mapped_column(Text)    # 可重生快取
    total_tmu: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    total_seconds: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    published_by: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    module: Mapped[MotionModule] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint(
            "module_id", "version_no",
            name="uq_motion_module_versions_module_id_version_no",
        ),
    )
