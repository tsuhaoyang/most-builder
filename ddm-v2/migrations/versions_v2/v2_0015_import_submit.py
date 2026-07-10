"""Phase 2b 匯入提交：provenance CHECK 加 'imported'、wi_rows.source_import_id、excel_imports.submitted_worksheet_id。
另補：excel_imports.status 加 'submitted'、work_vocab_items.source_system 加 'imported'（供 _lookup_or_create_vocab）。

Revision ID: v2_0015
Revises: v2_0014
Create Date: 2026-07-10

修正說明（Fix-C1）：
  NAMING_CONVENTION "ck": "ck_%(table_name)s_%(constraint_name)s" 對 v2_0001 已含 ck_ 前綴的約束名
  會再套一層，產生實際 DB 名稱：
    wi_rows.provenance         → ck_wi_rows_ck_wi_rows_provenance
    work_vocab_items.source_system → ck_work_vocab_items_ck_work_vocab_items_source_system
  excel_imports.status 在 v2_0008 以 name="status" 建立 → 實際名 ck_excel_imports_status。
  此處改用 raw SQL 並嘗試所有可能名稱的 DROP IF EXISTS，確保無論歷史名稱為何都能正確移除。
  ADD CONSTRAINT 使用單一前綴的標準名（與 model naming_convention short-name 一致）。
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "v2_0015"
down_revision = "v2_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. wi_rows.provenance：DROP（嘗試所有可能的歷史名）+ ADD ──
    # v2_0001 建立時 name="ck_wi_rows_provenance" + naming_convention → 實際名 ck_wi_rows_ck_wi_rows_provenance
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS ck_wi_rows_ck_wi_rows_provenance"))
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS ck_wi_rows_provenance"))
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS provenance"))
    op.execute(text(
        "ALTER TABLE wi_rows ADD CONSTRAINT ck_wi_rows_provenance "
        "CHECK (provenance IN ('manual','bom_draft','imported'))"
    ))

    # ── 2. wi_rows.source_import_id FK ──
    op.execute(text(
        "ALTER TABLE wi_rows ADD COLUMN IF NOT EXISTS source_import_id UUID NULL "
        "REFERENCES excel_imports(id) ON DELETE SET NULL"
    ))

    # ── 3. excel_imports.submitted_worksheet_id FK ──
    op.execute(text(
        "ALTER TABLE excel_imports ADD COLUMN IF NOT EXISTS submitted_worksheet_id UUID NULL "
        "REFERENCES most_worksheets(id) ON DELETE SET NULL"
    ))

    # ── 4. excel_imports.status：加 'submitted'（服務層用） ──
    # v2_0008 建立時 name="status" + naming_convention → 實際名 ck_excel_imports_status
    op.execute(text("ALTER TABLE excel_imports DROP CONSTRAINT IF EXISTS ck_excel_imports_status"))
    op.execute(text("ALTER TABLE excel_imports DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "ALTER TABLE excel_imports ADD CONSTRAINT ck_excel_imports_status "
        "CHECK (status IN ('uploaded','mapped','submitted','committed','failed'))"
    ))

    # ── 5. work_vocab_items.source_system：加 'imported'（_lookup_or_create_vocab 用） ──
    # v2_0001 建立時 name="ck_work_vocab_items_source_system" + naming_convention
    # → 實際名 ck_work_vocab_items_ck_work_vocab_items_source_system
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS ck_work_vocab_items_ck_work_vocab_items_source_system"))
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS ck_work_vocab_items_source_system"))
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS source_system"))
    op.execute(text(
        "ALTER TABLE work_vocab_items ADD CONSTRAINT ck_work_vocab_items_source_system "
        "CHECK (source_system IN ('local','mes','erp','plm','imported'))"
    ))


def downgrade() -> None:
    # ── 5. 還原 work_vocab_items.source_system（移除 'imported'）──
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS ck_work_vocab_items_source_system"))
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS ck_work_vocab_items_ck_work_vocab_items_source_system"))
    op.execute(text("ALTER TABLE work_vocab_items DROP CONSTRAINT IF EXISTS source_system"))
    op.execute(text(
        "ALTER TABLE work_vocab_items ADD CONSTRAINT ck_work_vocab_items_source_system "
        "CHECK (source_system IN ('local','mes','erp','plm'))"
    ))

    # ── 4. 還原 excel_imports.status（移除 'submitted'）──
    op.execute(text("ALTER TABLE excel_imports DROP CONSTRAINT IF EXISTS ck_excel_imports_status"))
    op.execute(text("ALTER TABLE excel_imports DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "ALTER TABLE excel_imports ADD CONSTRAINT ck_excel_imports_status "
        "CHECK (status IN ('uploaded','mapped','committed','failed'))"
    ))

    # ── 3. 移除 excel_imports.submitted_worksheet_id ──
    op.execute(text("ALTER TABLE excel_imports DROP COLUMN IF EXISTS submitted_worksheet_id"))

    # ── 2. 移除 wi_rows.source_import_id ──
    op.execute(text("ALTER TABLE wi_rows DROP COLUMN IF EXISTS source_import_id"))

    # ── 1. 還原 wi_rows.provenance（移除 'imported'）──
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS ck_wi_rows_provenance"))
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS ck_wi_rows_ck_wi_rows_provenance"))
    op.execute(text("ALTER TABLE wi_rows DROP CONSTRAINT IF EXISTS provenance"))
    op.execute(text(
        "ALTER TABLE wi_rows ADD CONSTRAINT ck_wi_rows_provenance "
        "CHECK (provenance IN ('manual','bom_draft'))"
    ))
