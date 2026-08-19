"""v2_0042：拔掉範本庫 M 格的「計價維度佔位」分量（`m_hand`／`m_foot` 且量值為 0）。

## 背景

`motion_templates.cycle_template` 是「怎麼填七格」的樣板（ADR-024 §3-2，不帶 `rule_set_code`，
套用時解析 active rule-set）。其中「掃描/檢查」一筆的 M 格填了：

    {"verb_code": "m_hand", "angle_deg": 0.0, "distance_cm": 0.0, "revolutions": 1, "diameter_cm": 0.0}

`m_hand`／`m_foot` 在認證字典裡的 `pricing_kind` 是 `hand`／`foot`——它們是**計價維度**
（按手轉角度／腳步距離查表），不是動作動詞。這一格真正的工作在 X（`x_scan_bar` 刷條碼），
手並沒有受控移動。而且 `angle_deg=0` ⇒ M 恆為 0 TMU：這顆分量從頭到尾只是佔位。

**M 格本來就可以是空的**（`m_components: []` → M0，引擎完全合法），不需要佔位。

## 為什麼非修不可

1. 敘事層照著分量生句子 → 這筆範本產出的每個 cycle 都帶一句假的「以手度實施移動」
   （實測 DB 有 2 筆 `most_cycles` 是這樣來的）。
2. 引擎即將加上「M 格若含 `pricing_kind='hand'/'foot'` 的分量，必須同時有真動詞分量」
   （依據＝認證字典的 `verb.required=true`）。這條一上線，這筆範本就是**非法輸入**：
   匯入預覽對「掃/檢查/測/scan/check/test/inspect」這組 keywords 會整批 422。

TMU 不受影響：修前修後同為 `A10 B0 G3 M0 X6 I6 A0` = 25 TMU（M 本來就是 0）。

## 範圍：只動 `motion_templates`

`most_cycles.slot_inputs` 與 `motion_module_versions.rows[].cycle` **不動**——那是 ADR-023
§3.4 回放鐵則的權威快照，歷史案件當初就是那樣算的，改它才是破壞回放（同 v2_0035 的分寸）。
落地前實測：`motion_templates` 命中 1 筆、`most_cycles` 有 2 筆含 `m_hand`（保留不動）、
`motion_module_versions` 0 筆。

## WHERE 的分寸：只拔「零量值的孤兒佔位」

只有「整個 M 格就這麼一顆、且是 `m_hand` 角度 0／`m_foot` 距離 0」才拔。
- 帶真動詞的多分量（例：`m_push` + `m_hand`）不動——那是合法的複合 M，拔了會改 TMU。
- `m_hand` 角度非 0 不動——那是真的有值的一格（10 TMU 之類），拔了就是竄改工時。
於是本 migration 對 TMU **恆等**，這是它敢在既有資料上跑的前提。

`CASE` 而非串接 `AND`：`jsonb_array_length()` 遇到非陣列（例如 JSON null）會丟錯，
而 SQL 的 `AND` 不保證由左而右求值。用 `CASE` 把型別守衛的求值順序釘死。
`jsonb_set` 的 create_missing=false：只改既有 key，不替形狀不完整的列補欄位。
跑過一次後選不到列 → 重跑為 no-op（冪等）。

## downgrade 取捨

**不還原**。把佔位寫回去等於把一個已知缺陷（假敘事 + 即將被引擎判非法）寫回資料——
與 v2_0035／v2_0022 同一個取捨。downgrade 因此是**明示的 no-op**（不是忘了寫）。

Revision ID: v2_0042
Revises: v2_0041
Create Date: 2026-08-19
"""
from __future__ import annotations

from alembic import op

revision = "v2_0042"
down_revision = "v2_0041"
branch_labels = None
depends_on = None


# 刻意抽成模組層常數：integration 測試直接 import 並在 rollback transaction 內執行**同一份**
# SQL（不是測試裡另抄一份的近似品），改了 migration 測試才會跟著變紅。（同 v2_0035）
SQL_STRIP_M_PLACEHOLDER = """
    UPDATE motion_templates
    SET    cycle_template = jsonb_set(cycle_template, '{m3,m_components}', '[]'::jsonb, false)
    WHERE  CASE
               WHEN jsonb_typeof(cycle_template -> 'm3' -> 'm_components') <> 'array' THEN false
               ELSE jsonb_array_length(cycle_template -> 'm3' -> 'm_components') = 1
                    AND (cycle_template -> 'm3' -> 'm_components'
                             @> '[{"verb_code": "m_hand", "angle_deg": 0}]'::jsonb
                         OR cycle_template -> 'm3' -> 'm_components'
                             @> '[{"verb_code": "m_foot", "distance_cm": 0}]'::jsonb)
           END
"""


def upgrade() -> None:
    op.execute(SQL_STRIP_M_PLACEHOLDER)


def downgrade() -> None:
    # 明示 no-op：把計價維度佔位寫回去等於把已知缺陷還原（理由見 module docstring）。
    pass
