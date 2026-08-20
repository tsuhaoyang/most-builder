"""v2_0043: i18n_review_state 加 target_sha256 ＋ 指派欄（ADR-032 D6 覆核 mutation，純加法）

四件事，全部加法（前三件在 `i18n_review_state`，第四件在 `workflow_audit_log`）：

1. **`target_sha256 text NULL`**——與既有 `source_sha256` 對稱：後者記「覆核當下的
   **中文來源**」，前者記「覆核當下的**英文譯文**」，同一支 `norm_sha256`。
   ADR-032 D6 末尾（第四輪複審 M1）park 的設計題就是這一格：`source_sha256` 只追蹤
   來源中文的變化，**不追蹤目標英文**，所以「覆核完之後有人改了 `label_en`」讀取端
   看不出來，那條英文會一直顯示「已覆核」。本次採 D6 列的候選方案一（side table 增加
   `target_sha256`），不採方案二（限制覆核只能對 active 版進行）——後者會讓 draft 專屬
   選項（D4 明文允許 IE 在 draft 新增 active 沒有的選項）永遠無法覆核。

   **既有列一律 NULL**（它們從未被覆核過，實測 `reviewed_by` 全 NULL）。
   `target_sha256 IS NULL` ＝沒有基準可比較 → **不算「變了」**，比照 `source_changed`
   對 `review_sha256 is None` 的既有處理（ADR-032 D6 L3）。

2. **`assigned_to text NULL` ＋ `assigned_at timestamptz NULL`**——D6 驗收定義寫的是
   「每條**可指派**、可標記完成」，而側表原本只有「翻譯／覆核」兩組事實，沒有指派。
   `assigned_to` 存員工號（與 `reviewed_by`／`translated_by` 同形，刻意不建 FK 到
   `app_users`：`reviewed_by` 也沒有，且 gateway 模式的身分來源是 header 注入的員編，
   JIT 建立列之前不一定存在）。取消指派＝兩欄一起回 NULL。

3. **`source` 值域加 `'untranslated'`**（drop ＋ recreate CHECK）。**為什麼非加不可**：
   指派必須能指派**還沒有譯文的那些列**（`never_translated` 正是最需要有人認領的一種），
   但要存 `assigned_to` 就得先有側表列，而 `source`／`source_sha256` 都是 NOT NULL——
   舊值域三個值（machine／human／legacy_seed）**每一個都是在描述「譯文的來源」**，
   對一條還沒有譯文的列填其中任何一個都是謊。與其把 `source` 放寬成 nullable
   （減法、且會弱化「每列都說得出譯文從哪來」這個不變式），不如加一個誠實的值：
   `'untranslated'` ＝「這列側表存在只是為了記指派，尚無譯文」。
   讀取端把它與 machine／legacy_seed 同列為 `unreviewed`（見 `i18n_service._classify`）。

4. **`workflow_audit_log.entity_type` 值域加 `'vocab_item'`**（drop ＋ recreate CHECK）。
   覆核 mutation 走既有的 `log_audit` 留痕（D5：「覆蓋寫入由既有 `workflow_audit_log`
   承接即可」——側表是 last-write-wins，覆蓋掉的前一次覆核只有 audit log 說得清）。
   被覆核的對象有三類，其中 `rule_option` 記在它所屬的 `rule_set` 上、
   `motion_template` 早就在值域裡，**只有 `vocab_item` 不在**——它與 `motion_template`
   同為 ADR-024 的主數據，值域裡缺它純粹是因為詞彙庫過去沒有任何走 audit 的寫入路徑。

**downgrade 的兩處非對稱，寫在這裡而不是靜默處理**：

- **`source='untranslated'` 的列會被刪掉**：那些列的唯一內容就是本次新增的指派欄，
  欄位一旦被 drop，它們會變成「source 不在舊值域、又沒有任何譯文事實」的孤兒，
  無法通過還原後的 CHECK。
- **`entity_type='vocab_item'` 的稽核列原地保留，舊 CHECK 以 `NOT VALID` 加回**：
  `workflow_audit_log` 自 **v2_0018** 起由 `trg_audit_no_delete`
  （`BEFORE DELETE FOR EACH ROW → RAISE EXCEPTION`）在 DB 層強制 append-only
  （ADR-018 裁決 3），v2_0018 < v2_0043，所以 downgrade 時 trigger 還在——本 migration
  第一版在這裡下 `DELETE FROM workflow_audit_log WHERE entity_type='vocab_item'`，
  一旦本功能被用過一次（有列可刪）就會被 trigger 中止、整個 downgrade 卡在 v2_0043
  （已在拋棄式 DB 上實測）。零筆時 `FOR EACH ROW` 不觸發，所以那一版是「假性通過」。
  刪稽核列本來就違反 ADR-018；`NOT VALID` 的語意正好是這裡要的：**既有列不驗證、
  保留原狀，新寫入仍受舊值域約束**——還原的目的是「以後不准再寫 vocab_item」，
  不是「抹掉曾經寫過 vocab_item 這件事」。代價是還原後的 CHECK 帶著 NOT VALID 旗標
  （`pg_constraint.convalidated = false`），要轉正需人工 `VALIDATE CONSTRAINT`，
  而那必然失敗——那正是「這批稽核列真實存在」的忠實表述。

Revision ID: v2_0043
Revises: v2_0042
Create Date: 2026-08-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "v2_0043"
down_revision = "v2_0042"
branch_labels = None
depends_on = None

_TABLE = "i18n_review_state"
_AUDIT_TABLE = "workflow_audit_log"
# v2_0017 以 raw SQL 建表、CHECK 內聯未具名 → Postgres 自動命名為
# `{table}_{column}_check`（實測 `pg_constraint` 確認）。**這裡必須用 raw SQL 改**：
# `op.drop_constraint()` 會套用 metadata 的 naming_convention（`ck_%(table_name)s_…`），
# 把名字變成 `ck_workflow_audit_log_workflow_audit_log_entity_type_check` 而找不到目標。
_AUDIT_CK = "workflow_audit_log_entity_type_check"
_AUDIT_TYPES_OLD = "entity_type IN ('process_version','motion_module','rule_set','motion_template')"
_AUDIT_TYPES_NEW = (
    "entity_type IN ('process_version','motion_module','rule_set','motion_template','vocab_item')"
)
_SOURCE_CK = "ck_i18n_review_state_source"
_SOURCE_CK_OLD = "source IN ('machine','human','legacy_seed')"
_SOURCE_CK_NEW = "source IN ('machine','human','legacy_seed','untranslated')"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("target_sha256", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("assigned_to", sa.Text(), nullable=True))
    op.add_column(_TABLE, sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint(_SOURCE_CK, _TABLE, type_="check")
    op.create_check_constraint(_SOURCE_CK, _TABLE, _SOURCE_CK_NEW)
    op.execute(sa.text(f"ALTER TABLE {_AUDIT_TABLE} DROP CONSTRAINT {_AUDIT_CK}"))
    op.execute(sa.text(
        f"ALTER TABLE {_AUDIT_TABLE} ADD CONSTRAINT {_AUDIT_CK} CHECK ({_AUDIT_TYPES_NEW})"
    ))


def downgrade() -> None:
    # 舊值域以 **NOT VALID** 加回，**不刪任何稽核列**（見檔頭第二點：audit 是
    # append-only，DB 層有 trigger 擋著，刪列會讓整個 downgrade 中止）。
    op.execute(sa.text(f"ALTER TABLE {_AUDIT_TABLE} DROP CONSTRAINT {_AUDIT_CK}"))
    op.execute(sa.text(
        f"ALTER TABLE {_AUDIT_TABLE} ADD CONSTRAINT {_AUDIT_CK} "
        f"CHECK ({_AUDIT_TYPES_OLD}) NOT VALID"
    ))
    # 見檔頭：'untranslated' 的列在舊 schema 下無法存在（它們只承載指派，而指派欄
    # 正要被 drop），故先刪列再收窄 CHECK——不是「順手清資料」，是還原的前提。
    op.execute(sa.text(f"DELETE FROM {_TABLE} WHERE source = 'untranslated'"))  # noqa: S608
    op.drop_constraint(_SOURCE_CK, _TABLE, type_="check")
    op.create_check_constraint(_SOURCE_CK, _TABLE, _SOURCE_CK_OLD)
    op.drop_column(_TABLE, "assigned_at")
    op.drop_column(_TABLE, "assigned_to")
    op.drop_column(_TABLE, "target_sha256")
