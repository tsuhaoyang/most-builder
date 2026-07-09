"""motion_templates → motion_modules 資料遷移（impl-04 §4）。

把 is_active=TRUE 的 motion_templates 記錄轉換為：
  - motion_modules（scope 從 site_id 推導；current_version=1）
  - motion_module_versions（version_no=1；rows=單列；total_tmu/total_seconds=0 placeholder）

total_tmu / total_seconds 置 0，待 scripts/backfill_module_totals.py 引擎補算；
migration 本身不 import 應用程式碼（避免 model coupling）。

若 motion_templates 無資料（fresh DB / migration-before-seed 場景），upgrade 為 no-op。

Revision ID: v2_0012
Revises: v2_0011
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op

revision = "v2_0012"
down_revision = "v2_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 步驟 1：建臨時映射表（原 template row → 新 module UUID）─────────
    # gen_random_uuid() 在每列產生不同 UUID，確保 PK 不衝突。
    op.execute("""
        CREATE TEMP TABLE _tmpl_to_module AS
        SELECT
            mt.id                  AS template_id,
            gen_random_uuid()      AS module_id,
            mt.name_zh,
            mt.category,
            mt.keywords,
            mt.site_id,
            mt.owner,
            mt.status,
            mt.cycle_template,
            mt.created_at,
            mt.updated_at
        FROM motion_templates mt
        WHERE mt.is_active = TRUE
    """)

    # ── 步驟 2：INSERT motion_modules ────────────────────────────────
    # scope 邏輯：site_id IS NULL → 'global'；有 site_id → 'site'
    # current_version：若 MINIMOST_FACTORY_V2 存在則設 1（版本 INSERT 會執行）；
    #   否則設 0（跳過版本 INSERT，模組本體仍建但尚無任何發布版）。
    op.execute("""
        INSERT INTO motion_modules
            (id, site_id, name_zh, category, keywords,
             scope, owner, status, current_version,
             created_at, updated_at)
        SELECT
            module_id,
            site_id,
            name_zh,
            category,
            keywords,
            CASE WHEN site_id IS NULL THEN 'global' ELSE 'site' END,
            owner,
            status,
            CASE WHEN EXISTS (
                SELECT 1 FROM rule_sets WHERE code = 'MINIMOST_FACTORY_V2'
            ) THEN 1 ELSE 0 END,
            created_at,
            updated_at
        FROM _tmpl_to_module
    """)

    # ── 步驟 3：INSERT motion_module_versions ────────────────────────
    # rows 格式：[{sub_activity, hand, frequency, simo_pair_index, vocab_refs, cycle}]
    #   - 每個 motion_template 只有一個 cycle（single-row module）
    #   - hand 預設 'RH'（右手）；frequency=1
    # total_tmu / total_seconds 先置 0（backfill 腳本補算，避免 migration→engine 耦合）
    # rule_set_id 取 MINIMOST_FACTORY_V2；若 DB 無此 rule_set，整個 INSERT 跳過
    # （WHERE EXISTS 確保子查詢不回 NULL，避免 NOT NULL constraint 違反）。
    op.execute("""
        INSERT INTO motion_module_versions
            (id, module_id, version_no, rule_set_id,
             rows, narrative_zh,
             total_tmu, total_seconds,
             published_by, published_at)
        SELECT
            gen_random_uuid(),
            module_id,
            1,
            (SELECT rs.id
             FROM   rule_sets rs
             WHERE  rs.code = 'MINIMOST_FACTORY_V2'
             ORDER  BY rs.created_at
             LIMIT  1),
            jsonb_build_array(
                jsonb_build_object(
                    'sub_activity',    NULL,
                    'hand',            'RH',
                    'frequency',       1,
                    'simo_pair_index', NULL,
                    'vocab_refs',      '{}'::jsonb,
                    'cycle',           cycle_template
                )
            ),
            NULL,
            0,
            0,
            'SYSTEM',
            NOW()
        FROM _tmpl_to_module
        WHERE EXISTS (
            SELECT 1 FROM rule_sets WHERE code = 'MINIMOST_FACTORY_V2'
        )
    """)

    # ── 步驟 4：清理臨時表 ─────────────────────────────────────────────
    op.execute("DROP TABLE _tmpl_to_module")


def downgrade() -> None:
    # 刪由本 migration 建立的 motion_modules（motion_module_versions 由 CASCADE 自動刪除）。
    # 識別依據雙重確認：
    #   1. name_zh 在 motion_templates 中有對應（is_active=TRUE）
    #   2. 版本記錄 published_by='SYSTEM' 且 version_no=1（migration 標記）
    # 確保只刪 migration 建立的記錄，不誤刪使用者後來手建的同名模組。
    op.execute("""
        DELETE FROM motion_modules mm
        WHERE EXISTS (
            SELECT 1
            FROM   motion_templates mt
            WHERE  mt.name_zh  = mm.name_zh
              AND  mt.is_active = TRUE
        )
        AND EXISTS (
            SELECT 1
            FROM   motion_module_versions mmv
            WHERE  mmv.module_id    = mm.id
              AND  mmv.published_by = 'SYSTEM'
              AND  mmv.version_no   = 1
        )
    """)
