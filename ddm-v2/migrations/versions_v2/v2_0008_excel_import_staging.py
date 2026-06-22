"""v2 Excel 匯入暫存（ADR-013, Phase 2a）：excel_imports + import_profiles；wi_rows.provenance 加 'imported'。

Revision ID: v2_0008
Revises: v2_0007
Create Date: 2026-06-21
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0008"
down_revision = "v2_0007"
branch_labels = None
depends_on = None

_UUID = postgresql.UUID(as_uuid=True)
_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "excel_imports",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("worksheet_id", _UUID),
        sa.Column("source_name", sa.Text()),
        sa.Column("status", sa.Text(), server_default=sa.text("'uploaded'"), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("sheet", sa.Text()),
        sa.Column("header_row", sa.Integer()),
        sa.Column("column_map", postgresql.JSONB()),
        sa.Column("time_unit", sa.Text()),
        sa.Column("staged_rows", postgresql.JSONB()),
        sa.Column("imported_by", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_excel_imports"),
        sa.ForeignKeyConstraint(["worksheet_id"], ["most_worksheets.id"], ondelete="SET NULL", name="fk_excel_imports_worksheet"),
        sa.CheckConstraint("status IN ('uploaded','mapped','committed','failed')", name="status"),
    )
    op.create_table(
        "import_profiles",
        sa.Column("id", _UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sheet_hint", sa.Text()),
        sa.Column("header_row", sa.Integer()),
        sa.Column("column_map", postgresql.JSONB(), nullable=False),
        sa.Column("time_unit", sa.Text()),
        sa.Column("owner", sa.Text()),
        sa.Column("created_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", _TS, server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_import_profiles"),
    )
    # 註：wi_rows.provenance 加 'imported' 留到 2b（提交 staged→worksheet 時）；
    #     屆時用 raw SQL 以實際約束名 ck_wi_rows_ck_wi_rows_provenance 處理，避免命名慣例雙前綴。


def downgrade() -> None:
    op.drop_table("import_profiles")
    op.drop_table("excel_imports")
