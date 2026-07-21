"""v2_0022：清理 category 語意未遷移的隱形模組 + 加 CHECK + 拔除範本內寫死的 V1（ADR-024 §3-2 / §4）。

## 背景（ADR-024「事後剖析」節）

`v2_0012_motion_templates_seed.py` 把範本庫 16 筆轉為 motion_modules，`category` 原封抄自
`motion_templates` 的**中文領域分類**（取放／組裝／鎖附…），`total_tmu` 留 0 作 placeholder。
其後 **ADR-022 把 `category` 的語意改為兩層判別值（'action'／'wi-template'）卻沒遷移既有資料**，
於是那 16 筆落在舊語意裡：工作台濾 'action'、WI 庫濾 'wi-template'，兩邊都不列出 → 完全隱形。

## 本 migration 做三件事

1. **刪除隱形模組**：`category NOT IN ('action','wi-template') OR category IS NULL`。
   `motion_module_versions` 由 FK ON DELETE CASCADE 連帶刪除。
   冪等：已無此類列時為 no-op（DELETE 影響 0 列不報錯）。

2. **加 CHECK 約束**擋住第三種值。⚠️ **本版 CHECK 允許 NULL，與 ADR-024 §4 的目標尚有落差**——
   §4 要求連 NULL 一起擋（NULL 的模組同樣兩層皆不屬，會重演隱形問題）。
   之所以暫不擋 NULL：`MotionModuleCreate.category` 目前是 `str | None = None`，
   `POST /api/v2/motion-modules` 不帶 category 是**現行合法用法**（integration 測試 45 處
   POST 有 43 處不帶）。實測加上 `category IS NOT NULL` 後 integration 由 322 passed
   變成 58 failed / 264 passed。收緊 schema（category 改必填或給預設）屬行為變更，
   須由協調者裁決後另開 migration，不在本 migration 自行決定。

   ⚠️ SQL 陷阱備忘：`CHECK (category IN ('action','wi-template'))` 對 NULL 求值為 NULL，
   而 CHECK **只在求值為 FALSE 時才拒絕**——所以這條約束對 NULL 是放行的。
   要擋 NULL 必須寫成 `category IS NOT NULL AND category IN (...)`（或另加 NOT NULL）。
   若日後誤以為「加了 CHECK 就不會有 NULL」，隱形問題會原樣重演。

3. **拔除 `motion_templates.cycle_template` 內寫死的 `rule_set_code`**（16 筆全是
   `MINIMOST_FACTORY_V1`，legacy 版本）。ADR-023 D1 已清除**程式碼**中所有寫死的
   rule-set code，但**資料內部這一份沒被清到**。
   ⚠️ **P2 把 `/motion-templates/match` 接上匯入流程時，套用範本必須解析 active rule-set
   （ADR-023 §3.5：不得寫死預設；取不到 active 是錯誤狀態，不是 fallback 的理由）。**
   否則會用 V1 的值算出靜默錯誤的 TMU。
   產生源 `scripts/dev_seed_templates.py` 與 API 寫入路徑同步改為 dump 時排除該欄。

   注意：**只動 `motion_templates.cycle_template`**。`motion_module_versions.rows[].cycle`
   內的 `rule_set_code` 是 ADR-023 §3.4 回放鐵則的權威快照，**不得移除**。

## downgrade 取捨

downgrade **只移除 CHECK 約束，不還原任何資料**：

- 被刪的 16 筆是 `total_tmu=0` 的 placeholder（來源 `motion_templates` 同名列全部仍在，
  且無任何 `wi_rows` 引用），本身不含使用者資料；而 `v2_0012` 仍在 migration 鏈上，
  一路 downgrade 到 v2_0011 以下再 upgrade 回來時會由 `v2_0012` 原樣重建，
  不需要（也不該）在此重複一份還原邏輯。
- 被拔掉的 `rule_set_code` 是寫死的 legacy 值，還原它等於把已知缺陷寫回資料。
  範本套用本來就該解析 active，缺這個 key 是正確狀態而非資訊遺失。

Revision ID: v2_0022
Revises: v2_0021
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op

revision = "v2_0022"
down_revision = "v2_0021"
branch_labels = None
depends_on = None

# 與 models/v2/base.py 的 naming_convention（ck_%(table_name)s_%(constraint_name)s）
# 套用在 model 端 name="ck_motion_modules_category_valid" 後的實際 DB 名稱。
# 既有的 scope/status 約束也是這個雙前綴形狀，此處刻意保持一致以免 model↔DB 對不上。
_CK_NAME = "ck_motion_modules_ck_motion_modules_category_valid"


# ── SQL 常數 ────────────────────────────────────────────────────────────
# 刻意抽成模組層常數：tests/integration/test_migration_v2_0022_category_and_template_ruleset.py
# 直接 import 並執行
# 這幾條**同一份** SQL（在 rollback fixture 的 transaction 內），確保測到的是 migration
# 真正跑的語句，而非測試裡另抄一份的近似品（抄一份的話 migration 改了測試不會變紅）。

# 1. 刪除 category 落在舊語意（或 NULL）的隱形模組。
# NOT IN 對 NULL 求值為 NULL，故必須顯式 OR IS NULL，否則 NULL 列刪不到。
# motion_module_versions 由 ON DELETE CASCADE 連帶刪除，無孤兒。
SQL_DELETE_INVISIBLE_MODULES = """
    DELETE FROM motion_modules
    WHERE category IS NULL
       OR category NOT IN ('action', 'wi-template')
"""

# 2. CHECK：擋住第三種值（NULL 暫時放行，理由見 docstring §2）。
SQL_ADD_CATEGORY_CHECK = f"""
    ALTER TABLE motion_modules
    ADD CONSTRAINT {_CK_NAME}
    CHECK (category IN ('action', 'wi-template'))
"""

# 3. 拔除範本 cycle_template 內寫死的 rule_set_code。
# `-` 運算子移除 top-level key；key 不存在時回傳原值，故重跑安全。
# 只更新真的含該 key 的列，避免無謂的 row 重寫。
SQL_STRIP_TEMPLATE_RULE_SET_CODE = """
    UPDATE motion_templates
    SET    cycle_template = cycle_template - 'rule_set_code'
    WHERE  cycle_template ? 'rule_set_code'
"""

SQL_DROP_CATEGORY_CHECK = (
    f"ALTER TABLE motion_modules DROP CONSTRAINT IF EXISTS {_CK_NAME}"
)


def upgrade() -> None:
    op.execute(SQL_DELETE_INVISIBLE_MODULES)
    op.execute(SQL_ADD_CATEGORY_CHECK)
    op.execute(SQL_STRIP_TEMPLATE_RULE_SET_CODE)


def downgrade() -> None:
    # 只移除 CHECK；資料不還原（取捨理由見 module docstring「downgrade 取捨」）。
    op.execute(SQL_DROP_CATEGORY_CHECK)
