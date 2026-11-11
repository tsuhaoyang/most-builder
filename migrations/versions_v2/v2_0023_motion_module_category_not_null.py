"""v2_0023：把 motion_modules.category 的 CHECK 收緊到連 NULL 一起擋（ADR-024 §4 補完 / D9b）。

## 為什麼需要第二個 migration

`v2_0022` 只加了 `CHECK (category IN ('action','wi-template'))`。那條約束**擋不住 NULL**：

    postgres=# select (null in ('action','wi-template')) is null;   -- t

SQL 的 CHECK **只在謂詞求值為 FALSE 時拒絕**；`NULL IN (...)` 求值為 NULL（不是 FALSE），
所以看起來明顯正確的那個寫法會讓 NULL 整批溜過去。而 NULL category 的模組
**兩層皆不屬**（工作台濾 'action'、WI 庫濾 'wi-template'，兩邊都列不出來），
正好是 ADR-024「事後剖析」那 16 筆隱形模組的原始形狀。

v2_0022 當時暫不擋 NULL，是因為 `MotionModuleCreate.category` 允許省略、
integration 45 處 POST 有 43 處不帶（實測套上嚴格約束 → 58 failed / 264 passed），
「category 可省略」屬現行契約而非測試草率，收緊需裁決。

D9b 已裁決：**收緊為必填**（不是放寬 §4）。`MotionModuleCreate.category` 改為
`Literal['action','wi-template']` 必填，呼叫端省略即 422；前端 `ActionModuleWorkspace.tsx`
兩處本來就明送 'action'／'wi-template'，不受影響。本 migration 補上 DB 端的另一半。

## 做法

v2_0022 的 CHECK 原樣保留（它負責「只能是這兩個值」），本 migration 只補上欄位層的
`SET NOT NULL`（負責「不能沒有值」）。兩者合起來＝ADR-024 §4 要的完整值域。

用 `NOT NULL` 而非把 `IS NOT NULL` 併進 CHECK 謂詞：NOT NULL 是欄位層的一等約束，
規劃器能利用、`\\d` 一眼看得到，且與 model 端 `nullable=False` 對得起來
（避免日後 autogenerate 產生假 diff）。

前置條件：無 NULL 殘留。`v2_0022` 已刪除所有 `category IS NULL OR NOT IN (...)` 的列，
且自 v2_0022 起 CHECK 已擋掉非法值、schema 收緊後也不會再產生 NULL。
保險起見仍在 SET NOT NULL 前重跑一次刪除（冪等，正常情況影響 0 列）——
若某個環境在 v2_0022 之後、schema 收緊之前經由 API 建了 NULL 模組，
沒有這步的話 SET NOT NULL 會直接失敗擋住升級。

## downgrade

對稱回到 v2_0022 的狀態：移除 NOT NULL（v2_0022 的 CHECK 留著，本 migration 沒動它，
移除 NOT NULL 後它自然回到 NULL-放行的行為）。
資料不還原（理由同 v2_0022 docstring「downgrade 取捨」：被刪的是 total_tmu=0 的
placeholder，來源仍在且 v2_0012 在鏈上可重建）。

Revision ID: v2_0023
Revises: v2_0022
Create Date: 2026-07-22
"""
from __future__ import annotations

from alembic import op

revision = "v2_0023"
down_revision = "v2_0022"
branch_labels = None
depends_on = None

# 與 v2_0022 相同的清理語句（冪等；此處作為 SET NOT NULL 的前置保險）。
SQL_DELETE_INVISIBLE_MODULES = """
    DELETE FROM motion_modules
    WHERE category IS NULL
       OR category NOT IN ('action', 'wi-template')
"""

SQL_SET_NOT_NULL = "ALTER TABLE motion_modules ALTER COLUMN category SET NOT NULL"
SQL_DROP_NOT_NULL = "ALTER TABLE motion_modules ALTER COLUMN category DROP NOT NULL"


def upgrade() -> None:
    op.execute(SQL_DELETE_INVISIBLE_MODULES)
    op.execute(SQL_SET_NOT_NULL)


def downgrade() -> None:
    op.execute(SQL_DROP_NOT_NULL)
