"""WI 聚合：process_version(1:1)most_worksheet → wi_row(1:1)most_cycle，wi_row →(o)level_entry。

依據 data-model-and-storage-spec §2.4–2.9（含生命週期/另存新檔、儲存策略 §1.5）。
- most_cycle：slot_inputs(JSONB) 為權威原始輸入；seq_kind/rule_set_version_id/total_* 升為欄（可查/聚合）；computed/narrative 為可重生快取。
- wi_row.id：同一版本編輯期內穩定，改 MOST 不丟 level（level_entry FK→wi_row）。
- created_by/published_by：暫為純 UUID，待 RBAC v2 補 FK→users。
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk

_STATUS_CK = "status IN ('draft','approved','retired')"


class ProcessVersion(Base, TimestampMixin):
    """版本（輕量 SOP）。1:1 對 most_worksheet。發布即凍結；改→另存新檔。"""

    __tablename__ = "process_versions"

    id: Mapped[UUID] = uuid_pk()
    sku_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("skus.id", ondelete="CASCADE"), nullable=False)
    version_no: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    source_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("process_versions.id", ondelete="SET NULL")
    )  # 另存新檔血緣
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(Text)      # 員工編號（RBAC）
    published_by: Mapped[str | None] = mapped_column(Text)     # 員工編號（manager+）
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    worksheet: Mapped[MostWorksheet | None] = relationship(back_populates="process_version", uselist=False)

    __table_args__ = (
        CheckConstraint(_STATUS_CK, name="status"),
        UniqueConstraint("sku_id", "version_no", name="uq_process_versions_sku_id_version_no"),
    )


class MostWorksheet(Base, TimestampMixin):
    """MOST 工序單（WI 表頭）。嚴格 1:1 對 process_version。"""

    __tablename__ = "most_worksheets"

    id: Mapped[UUID] = uuid_pk()
    process_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("process_versions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    model_label: Mapped[str | None] = mapped_column(Text)
    analyst: Mapped[str | None] = mapped_column(Text)
    study_date: Mapped[date | None] = mapped_column(Date)
    default_rule_set_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("rule_sets.id", ondelete="RESTRICT")
    )
    allowance_percent: Mapped[float | None] = mapped_column(Numeric(6, 3))  # 工序表級寬放%（data-model §2.5）
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'draft'"))
    # R1 / ADR-027：內容 revision 樂觀鎖
    revision_no: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("1")
    )
    content_hash: Mapped[str | None] = mapped_column(Text)
    last_edited_by: Mapped[str | None] = mapped_column(Text)
    last_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    process_version: Mapped[ProcessVersion] = relationship(back_populates="worksheet")
    rows: Mapped[list[WiRow]] = relationship(back_populates="worksheet", order_by="WiRow.seq_no")

    __table_args__ = (
        CheckConstraint(_STATUS_CK, name="status"),
        CheckConstraint("allowance_percent IS NULL OR allowance_percent >= 0", name="ck_most_worksheets_allowance_nonneg"),
    )


class WiRow(Base, TimestampMixin):
    """方法步（工序列）。id 在同版本編輯期內穩定。"""

    __tablename__ = "wi_rows"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False)
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sub_activity: Mapped[str | None] = mapped_column(Text)
    key_parts: Mapped[str | None] = mapped_column(Text)
    hand: Mapped[str | None] = mapped_column(Text)
    object_vocab_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"))
    from_vocab_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"))
    to_vocab_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"))
    tool_vocab_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("work_vocab_items.id", ondelete="RESTRICT"))
    frequency: Mapped[float] = mapped_column(Numeric(10, 3), nullable=False, server_default=text("1"))
    simo_group_id: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'manual'"))
    source_row_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))  # clone 血緣
    # impl-04：模組實體化追溯（同 NULL 或同非 NULL）
    source_module_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("motion_modules.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_module_version: Mapped[int | None] = mapped_column(Integer)
    source_import_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("excel_imports.id", ondelete="SET NULL"), nullable=True
    )  # 2b: 匯入批次血緣

    worksheet: Mapped[MostWorksheet] = relationship(back_populates="rows")
    cycle: Mapped[MostCycle | None] = relationship(back_populates="wi_row", uselist=False, cascade="all, delete-orphan")
    level_entry: Mapped[LevelEntry | None] = relationship(back_populates="wi_row", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        # 短名 + naming_convention "ck_%(table_name)s_%(constraint_name)s" → 實際 DB 名帶 ck_wi_rows_ 前綴。
        # v2_0001 誤用長名（已含 ck_ 前綴）導致雙前綴；v2_0015 migration 已用 raw SQL DROP IF EXISTS 修正。
        CheckConstraint("hand IS NULL OR hand IN ('LH','RH','BH')", name="hand"),
        CheckConstraint("provenance IN ('manual','bom_draft','imported')", name="provenance"),  # 2b: 加 imported
        CheckConstraint("frequency > 0", name="frequency_pos"),
        UniqueConstraint("worksheet_id", "seq_no", name="uq_wi_rows_worksheet_id_seq_no"),
    )


class MostCycle(Base, TimestampMixin):
    """GM/CM 七格填值。slot_inputs 為權威原始輸入；其餘為升欄/快取（§1.5）。"""

    __tablename__ = "most_cycles"

    id: Mapped[UUID] = uuid_pk()
    wi_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("wi_rows.id", ondelete="CASCADE"), nullable=False, unique=True)
    seq_kind: Mapped[str] = mapped_column(Text, nullable=False)  # GM / CM（升欄）
    rule_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("rule_sets.id", ondelete="RESTRICT"), nullable=False)  # 快照
    slot_inputs: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 權威原始輸入（Pydantic 驗形狀）
    computed: Mapped[dict | None] = mapped_column(JSONB)  # 可重生快取：每格 tmu/tech_line
    narrative_zh: Mapped[str | None] = mapped_column(Text)  # 可重生快取：METHOD 敘述
    total_tmu: Mapped[float | None] = mapped_column(Numeric(12, 3))  # 升欄：可聚合
    total_seconds: Mapped[float | None] = mapped_column(Numeric(12, 4))
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    wi_row: Mapped[WiRow] = relationship(back_populates="cycle")

    __table_args__ = (CheckConstraint("seq_kind IN ('GM','CM')", name="seq_kind"),)


class LevelEntry(Base, TimestampMixin):
    """層級系統標註（R1–R9 由引擎驗）。FK→wi_row（穩定 id），改 MOST 不丟。"""

    __tablename__ = "level_entries"

    id: Mapped[UUID] = uuid_pk()
    wi_row_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("wi_rows.id", ondelete="CASCADE"), nullable=False, unique=True)
    worksheet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="CASCADE"), nullable=False)
    raw_seconds: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, server_default=text("0"))
    coefficient: Mapped[float] = mapped_column(Numeric(6, 3), nullable=False, server_default=text("1"))
    second: Mapped[float] = mapped_column(Numeric(12, 4), Computed("raw_seconds * coefficient", persisted=True))
    number: Mapped[str | None] = mapped_column(Text)
    number_count: Mapped[int | None] = mapped_column(Integer)
    ascription: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(Text)  # '1' / '1~2' / '1/3'
    countersignature: Mapped[str | None] = mapped_column(Text)       # 本列所屬（最內層）群組 sub*/cub*
    parent_countersignature: Mapped[str | None] = mapped_column(Text)  # 巢狀：外層群組（cub 在 sub 內時 = 該 sub）；C2
    order_in_group: Mapped[int | None] = mapped_column(Integer)
    machine_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    manpower: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    wi_row: Mapped[WiRow] = relationship(back_populates="level_entry")

    __table_args__ = (
        CheckConstraint("coefficient > 0", name="coefficient_pos"),
        CheckConstraint("ascription IS NULL OR ascription = 'main'", name="ascription"),
        CheckConstraint("machine_count >= 1 AND manpower >= 1", name="resources_pos"),
    )
