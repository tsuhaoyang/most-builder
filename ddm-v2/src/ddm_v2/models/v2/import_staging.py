"""Excel 匯入暫存（Phase 2a，ADR-013）：excel_imports(staging) + import_profiles(可重用欄位對應)。

資料驅動 + 暫存緩衝：外部 Excel 先落 staging（raw_payload），經欄位對應(profile)正規化成 staged_rows，
**不直接進 worksheet**（提交政策屬 2b）。仿既有 bom_imports。
"""
from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class ExcelImport(Base, TimestampMixin):
    """一次匯入的暫存。raw_payload=原始格；column_map=欄位對應；staged_rows=正規化預覽結果。"""

    __tablename__ = "excel_imports"

    id: Mapped[UUID] = uuid_pk()
    worksheet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="SET NULL")
    )  # 目標 worksheet（2b 提交用）；可後綁
    source_name: Mapped[str | None] = mapped_column(Text)  # 檔名
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'uploaded'"))
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {sheets:[{name,grid,n_rows,n_cols}]}
    sheet: Mapped[str | None] = mapped_column(Text)
    header_row: Mapped[int | None] = mapped_column(Integer)
    column_map: Mapped[dict | None] = mapped_column(JSONB)  # {our_field: col_index}
    time_unit: Mapped[str | None] = mapped_column(Text)  # 'sec' | 'min'
    staged_rows: Mapped[list | None] = mapped_column(JSONB)  # 正規化後的列
    imported_by: Mapped[str | None] = mapped_column(Text)
    submitted_worksheet_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("most_worksheets.id", ondelete="SET NULL"), nullable=True
    )  # 2b: 提交後回填目標 worksheet
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('uploaded','mapped','submitted','committed','failed')", name="status"),
    )


class ImportProfile(Base, TimestampMixin):
    """可重用的欄位對應設定（資料驅動：新格式＝加一筆 profile，不改程式）。"""

    __tablename__ = "import_profiles"

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sheet_hint: Mapped[str | None] = mapped_column(Text)
    header_row: Mapped[int | None] = mapped_column(Integer)
    column_map: Mapped[dict] = mapped_column(JSONB, nullable=False)
    time_unit: Mapped[str | None] = mapped_column(Text)
    owner: Mapped[str | None] = mapped_column(Text)  # 員工編號（建立者）


class ImportRow(Base, TimestampMixin):
    """正規化後的單列（ADR-027 §12.3）：支援 row lock／retry／parse lineage。"""

    __tablename__ = "import_rows"

    id: Mapped[UUID] = uuid_pk()
    import_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("excel_imports.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    normalized_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    schema_version: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'import-row-v1'"))
    input_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'staged'"))
    selected_for_submit: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=text("false")
    )
    last_error: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        UniqueConstraint("import_id", "source_row_no", name="uq_import_rows_import_source_row"),
        CheckConstraint(
            "status IN ("
            "'staged','queued','processing','review','ready','failed','skipped','submitted')",
            name="status",
        ),
        sa.Index("ix_import_rows_import_id", "import_id"),
    )
