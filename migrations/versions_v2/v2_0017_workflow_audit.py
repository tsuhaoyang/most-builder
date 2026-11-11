"""impl-06b：workflow_audit_log 表 + published→approved 狀態改名 + 歷史回填。

依 ADR-018 裁決：approved 承接 published 語意；僅追加 audit log（無 update/delete 路徑）。
歷史 published 工序表回填 actor="system_migration"。

MostWorksheet / ProcessVersion 的 status CHECK 約束原始名稱（v2_0001 建立）：
  ck_most_worksheets_status
  ck_process_versions_status
使用多重 DROP IF EXISTS（同 v2_0015 先例），確保無論歷史名稱為何皆可移除。

RuleSet 的 status 值域 ('draft','published','retired') 不變，本 migration 不動。

Revision ID: v2_0017
Revises: v2_0016
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text

revision = "v2_0017"
down_revision = "v2_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. 建立 workflow_audit_log（僅追加，無 FK 強制，允許實體刪除後 log 留存）──
    op.execute(text("""
        CREATE TABLE IF NOT EXISTS workflow_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            entity_type TEXT NOT NULL CHECK (entity_type IN ('process_version','motion_module','rule_set','motion_template')),
            entity_id UUID NOT NULL,
            action TEXT NOT NULL,
            from_status TEXT,
            to_status TEXT,
            actor TEXT NOT NULL,
            comment TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_audit_entity "
        "ON workflow_audit_log (entity_type, entity_id, created_at)"
    ))

    # ── 2a. most_worksheets.status：存量值 published → approved ──
    # 順序：DROP 舊約束 → UPDATE 值 → ADD 新約束
    # （PostgreSQL 在 UPDATE 執行時即時驗證 CHECK，必須先移除舊約束）
    op.execute(text("ALTER TABLE most_worksheets DROP CONSTRAINT IF EXISTS ck_most_worksheets_ck_most_worksheets_status"))
    op.execute(text("ALTER TABLE most_worksheets DROP CONSTRAINT IF EXISTS ck_most_worksheets_status"))
    op.execute(text("ALTER TABLE most_worksheets DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "UPDATE most_worksheets SET status='approved' WHERE status='published'"
    ))
    op.execute(text(
        "ALTER TABLE most_worksheets ADD CONSTRAINT ck_most_worksheets_status "
        "CHECK (status IN ('draft','approved','retired'))"
    ))

    # ── 2b. process_versions.status：存量值 published → approved ──
    # 順序：DROP 舊約束 → UPDATE 值 → ADD 新約束
    op.execute(text("ALTER TABLE process_versions DROP CONSTRAINT IF EXISTS ck_process_versions_ck_process_versions_status"))
    op.execute(text("ALTER TABLE process_versions DROP CONSTRAINT IF EXISTS ck_process_versions_status"))
    op.execute(text("ALTER TABLE process_versions DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "UPDATE process_versions SET status='approved' WHERE status='published'"
    ))
    op.execute(text(
        "ALTER TABLE process_versions ADD CONSTRAINT ck_process_versions_status "
        "CHECK (status IN ('draft','approved','retired'))"
    ))

    # ── 3. 歷史回填 audit log（actor = "system_migration"）──
    op.execute(text("""
        INSERT INTO workflow_audit_log
            (id, entity_type, entity_id, action, from_status, to_status, actor, comment, created_at)
        SELECT
            gen_random_uuid(),
            'process_version',
            pv.id,
            'approve',
            'draft',
            'approved',
            'system_migration',
            '歷史 published→approved 回填（impl-06b migration）',
            COALESCE(pv.published_at, now())
        FROM process_versions pv
        WHERE pv.status = 'approved'
    """))


def downgrade() -> None:
    # ── 3. 移除回填記錄 ──
    op.execute(text("DELETE FROM workflow_audit_log WHERE actor = 'system_migration'"))

    # ── 2b. process_versions.status：approved → published，還原約束 ──
    # 順序：DROP 新約束 → UPDATE 值 → ADD 舊約束
    # （現有列含 'approved'，ADD 舊約束前必須先改值，否則 ADD CONSTRAINT 即時驗證失敗）
    op.execute(text("ALTER TABLE process_versions DROP CONSTRAINT IF EXISTS ck_process_versions_status"))
    op.execute(text("ALTER TABLE process_versions DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "UPDATE process_versions SET status='published' WHERE status='approved'"
    ))
    op.execute(text(
        "ALTER TABLE process_versions ADD CONSTRAINT ck_process_versions_status "
        "CHECK (status IN ('draft','published','retired'))"
    ))

    # ── 2a. most_worksheets.status：approved → published，還原約束 ──
    # 順序：DROP 新約束 → UPDATE 值 → ADD 舊約束
    op.execute(text("ALTER TABLE most_worksheets DROP CONSTRAINT IF EXISTS ck_most_worksheets_status"))
    op.execute(text("ALTER TABLE most_worksheets DROP CONSTRAINT IF EXISTS status"))
    op.execute(text(
        "UPDATE most_worksheets SET status='published' WHERE status='approved'"
    ))
    op.execute(text(
        "ALTER TABLE most_worksheets ADD CONSTRAINT ck_most_worksheets_status "
        "CHECK (status IN ('draft','published','retired'))"
    ))

    # ── 1. 移除 workflow_audit_log ──
    op.execute(text("DROP INDEX IF EXISTS ix_audit_entity"))
    op.execute(text("DROP TABLE IF EXISTS workflow_audit_log"))
