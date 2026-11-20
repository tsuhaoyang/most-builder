"""v2_0050: 外部 ai_service 的 run 落地欄位（ADR-037 S3 第一步；全部為加法）

## 做三件事

1. `ai_deployment_bundles.kind` 的 CHECK 加 `'external'`。
   計畫寫的「`ai_parse_runs.kind`」實際上是 bundle 的 kind：`ai_parse_runs` 沒有 kind 欄，
   一筆 run 的種類由它指向的 bundle 決定（`bundle_id` NOT NULL）。
2. `ai_parse_runs` 新增兩個可為 NULL 的欄位（舊列不受影響，舊程式不讀不寫也不會壞）：
   - `provenance JSONB`：ai_service 的去敏出處，鍵來自 `ai_integration/adapter.py`／`guard.py`
     實際輸出（request_id、run_id、shared_run_id、bundle_code、bundle_status、model_served、
     prompt_variant、prompt_version、retry_count、attempts、latency_ms、upstream_code、http_status）。
     金鑰、員工編號、原文一律不得進來（ADR-037 D7）；寫入端（S3 後續 PR）要以 allow-list 約束鍵。
     ai_parse_runs 沒有 prompt_version 欄，有那欄的是 ai_deployment_bundles，所以外部 run 的
     prompt 版本放這裡。只對外部 run 有意義，其他 run 為 NULL。
   - `upstream_run_id TEXT`（加索引）：從 provenance 取出的 ai_service `run_id`，ADR-037 D7 用它
     和 ai_service 對帳。合併請求的等待者沒有自己的外送，這欄為 NULL（`shared_run_id` 只在 provenance）。
3. 佔位 bundle `external-ai-service`（kind=external、status=active、config={}）。
   所有外部 run 都指向它；實際使用的 ai_service bundle 代碼記在 `provenance.bundle_code`。

## CHECK 約束名稱

實際名稱是雙前綴 `ck_ai_deployment_bundles_ck_ai_deployment_bundles_kind`（v2_0026 用全名建，
再被 models/v2/base.py 的 naming_convention 加一次前綴；v2_0022、v2_0015 也記過這個陷阱）。
新約束沿用同一個名稱，不增加第二種形狀。已在真 DB 以 pg_constraint 確認。

## downgrade：遇到 external 資料就拒絕，不刪資料

把 CHECK 收回成 ('rule_based','llm') 前，若有 run 指向 external bundle、或存在佔位以外的
external bundle，就 `RuntimeError` 並說明原因（`ai_parse_runs.bundle_id` 是 RESTRICT；
`ai_review_events` 會跟著 run CASCADE，直接刪等於悄悄清掉稽核資料）。
沒有這些資料時才刪佔位 bundle、移除欄位與索引、還原約束。

Revision ID: v2_0050
Revises: v2_0049
Create Date: 2026-11-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2_0050"
down_revision = "v2_0049"
branch_labels = None
depends_on = None

# 下列兩個模組常數會用 f-string 組進 DDL／SQL（DDL 無法 bind 參數）。
# 它們必須維持字面常數，**不得改成外部輸入或環境變數**。
# 實際 DB 名稱（雙前綴）；見檔頭。
_CK_NAME = "ck_ai_deployment_bundles_ck_ai_deployment_bundles_kind"
PLACEHOLDER_BUNDLE_CODE = "external-ai-service"

# 刻意抽成模組層常數：integration 測試直接 import 並執行同一份 SQL。
SQL_SEED_PLACEHOLDER_BUNDLE = f"""
    INSERT INTO ai_deployment_bundles
        (id, code, kind, model, prompt_version, config, status, created_by)
    VALUES
        (gen_random_uuid(), '{PLACEHOLDER_BUNDLE_CODE}', 'external', NULL, NULL, '{{}}'::jsonb, 'active', 'system')
    ON CONFLICT (code) DO NOTHING
"""

# downgrade 前的檢查：有幾筆 run 指向 external bundle、有幾個佔位以外的 external bundle。
SQL_COUNT_EXTERNAL_RUNS = """
    SELECT COUNT(*) FROM ai_parse_runs r
    JOIN ai_deployment_bundles b ON b.id = r.bundle_id
    WHERE b.kind = 'external'
"""
SQL_COUNT_OTHER_EXTERNAL_BUNDLES = f"""
    SELECT COUNT(*) FROM ai_deployment_bundles
    WHERE kind = 'external' AND code <> '{PLACEHOLDER_BUNDLE_CODE}'
"""
# ai_parse_jobs.deployment_bundle_id 也是 RESTRICT FK：有 job 指向 external bundle 時，刪佔位會以 FK 錯誤失敗，
# 先數出來才能給友善的拒絕訊息。
SQL_COUNT_EXTERNAL_JOBS = """
    SELECT COUNT(*) FROM ai_parse_jobs j
    JOIN ai_deployment_bundles b ON b.id = j.deployment_bundle_id
    WHERE b.kind = 'external'
"""
SQL_PLACEHOLDER_IS_EXTERNAL = f"""
    SELECT COUNT(*) FROM ai_deployment_bundles
    WHERE code = '{PLACEHOLDER_BUNDLE_CODE}' AND kind = 'external'
"""
SQL_DELETE_PLACEHOLDER_BUNDLE = f"""
    DELETE FROM ai_deployment_bundles WHERE code = '{PLACEHOLDER_BUNDLE_CODE}' AND kind = 'external'
"""


def upgrade() -> None:
    op.execute(sa.text(f"ALTER TABLE ai_deployment_bundles DROP CONSTRAINT IF EXISTS {_CK_NAME}"))
    op.execute(
        sa.text(
            f"ALTER TABLE ai_deployment_bundles ADD CONSTRAINT {_CK_NAME} "
            "CHECK (kind IN ('rule_based', 'llm', 'external'))"
        )
    )
    op.add_column("ai_parse_runs", sa.Column("provenance", postgresql.JSONB(), nullable=True))
    op.add_column("ai_parse_runs", sa.Column("upstream_run_id", sa.Text(), nullable=True))
    op.create_index("ix_ai_parse_runs_upstream_run_id", "ai_parse_runs", ["upstream_run_id"])
    op.execute(sa.text(SQL_SEED_PLACEHOLDER_BUNDLE))
    # ON CONFLICT DO NOTHING 會在同代碼已被別的 kind 佔用時靜默略過；不能留下「沒有佔位 bundle」的庫
    if not op.get_bind().execute(sa.text(SQL_PLACEHOLDER_IS_EXTERNAL)).scalar_one():
        raise RuntimeError(
            f"v2_0050: bundle code '{PLACEHOLDER_BUNDLE_CODE}' already exists with a kind other than 'external'; "
            "rename or remove it deliberately, then upgrade again."
        )


def downgrade() -> None:
    bind = op.get_bind()
    # 先鎖再檢查：避免「檢查通過後、刪除前」被併發寫入，讓拒絕變成確定的 RuntimeError 而不是事後的 FK／CHECK 錯誤
    op.execute(sa.text("LOCK TABLE ai_deployment_bundles, ai_parse_runs, ai_parse_jobs IN SHARE ROW EXCLUSIVE MODE"))
    runs = bind.execute(sa.text(SQL_COUNT_EXTERNAL_RUNS)).scalar_one()
    jobs = bind.execute(sa.text(SQL_COUNT_EXTERNAL_JOBS)).scalar_one()
    others = bind.execute(sa.text(SQL_COUNT_OTHER_EXTERNAL_BUNDLES)).scalar_one()
    if runs or jobs or others:
        raise RuntimeError(
            f"v2_0050 downgrade refused: {runs} ai_parse_runs row(s) and {jobs} ai_parse_jobs row(s) point to "
            f"external bundles and {others} external bundle(s) other than '{PLACEHOLDER_BUNDLE_CODE}' exist. "
            "Deleting them would silently remove audit data (ai_review_events cascade from runs). "
            "Export or remove these rows deliberately, then downgrade again."
        )
    op.execute(sa.text(SQL_DELETE_PLACEHOLDER_BUNDLE))
    op.drop_index("ix_ai_parse_runs_upstream_run_id", table_name="ai_parse_runs")
    op.drop_column("ai_parse_runs", "upstream_run_id")
    op.drop_column("ai_parse_runs", "provenance")
    op.execute(sa.text(f"ALTER TABLE ai_deployment_bundles DROP CONSTRAINT IF EXISTS {_CK_NAME}"))
    op.execute(
        sa.text(
            f"ALTER TABLE ai_deployment_bundles ADD CONSTRAINT {_CK_NAME} "
            "CHECK (kind IN ('rule_based', 'llm'))"
        )
    )
