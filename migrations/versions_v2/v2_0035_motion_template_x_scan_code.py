"""v2_0035：修復範本庫裡的 V1 遺留 X 碼 `x_scan` → `x_scan_bar`（ADR-014 值權威）。

## 背景

`motion_templates.cycle_template` 是「怎麼填七格」的樣板，**依 ADR-024 §3-2 不帶
`rule_set_code`**——套用時一律解析 active rule-set（ADR-023 §3.5），也就是 V2 認證字典
（`MINIMOST_FACTORY_V2`）。

但範本庫的產生源 `scripts/dev_seed_templates.py` 是在 V1 時代寫的，其中「掃描/檢查」一筆用
`x_scan`（V1 的「刷條碼(固定)」）。V2 認證字典把它改名分家為 `x_scan_bar`／`x_scan_ppid`／
`x_scan_wo`（三者同為 `mode='fixed'` 0.216 秒），**`x_scan` 在 V2 不存在**。
於是那一筆對 active rule-set 恆定算不出來：`SequenceError [X_UNKNOWN] 未知 X 選項：x_scan`。

## 為什麼非修不可（不是「少一個範本」而已）

1. **匯入預覽**（`import_service.preview` 對每個範本試算一次）：這筆固定得到
   `computed_tmu: null` + error，前端判定不可採用 → 描述含「掃/檢查/測/scan/check/test/
   inspect」的列全部無法自動建模（這些關鍵字正好是它的 keywords）。
2. **繞過 UI 直接採用**（`import_service` 落地路徑的 `compute_cycle` 不在 try 內）→ 整份匯入 500。

## 範圍：只動 `motion_templates`

`motion_module_versions.rows[].cycle` **不動**——那裡的 `rule_set_code` 是 ADR-023 §3.4 回放
鐵則的權威快照，掛在 V1 快照下的 `x_scan` 是**正確的歷史值**，改它才是破壞回放。
（本次落地前實測該表與 `most_cycles` 皆為 0 筆含 `x_scan`。）

`x_seconds` 一併正規化為 0：`mode='fixed'` 的秒數由字典提供、`x_seconds` 不參與計算，
既有值 1.5 純屬誤導；歸零後與修好的 seed 腳本在新環境產出的內容一致（新舊環境一致性，
同 v2_0022 的理由）。

## downgrade 取捨

**不還原**。`x_scan` 不在 V2 認證字典裡，還原它等於把一個已知缺陷寫回資料——
與 v2_0022 拔除寫死 `rule_set_code` 後不還原是同一個取捨。本 migration 的 downgrade
因此是**明示的 no-op**（不是忘了寫）。

Revision ID: v2_0035
Revises: v2_0034
Create Date: 2026-08-11
"""
from __future__ import annotations

from alembic import op

revision = "v2_0035"
down_revision = "v2_0034"
branch_labels = None
depends_on = None


# 刻意抽成模組層常數：integration 測試直接 import 並在 rollback transaction 內執行**同一份**
# SQL（不是測試裡另抄一份的近似品），改了 migration 測試才會跟著變紅。
#
# WHERE 以 `-> 'x4' ->> 'x_code'` 精確定位：GM 範本沒有 x4（值為 null）→ `->>` 回 NULL →
# 不等於 'x_scan' → 不被選中，不會誤傷。跑過一次後選不到列 → 重跑為 no-op（冪等）。
# jsonb_set 的 create_missing=false：只改既有 key，不替形狀不完整的列補欄位。
SQL_FIX_TEMPLATE_X_SCAN = """
    UPDATE motion_templates
    SET    cycle_template = jsonb_set(
               jsonb_set(cycle_template, '{x4,x_code}', '"x_scan_bar"'::jsonb, false),
               '{x4,x_seconds}', '0'::jsonb, false)
    WHERE  cycle_template -> 'x4' ->> 'x_code' = 'x_scan'
"""


def upgrade() -> None:
    op.execute(SQL_FIX_TEMPLATE_X_SCAN)


def downgrade() -> None:
    # 明示 no-op：還原 `x_scan` 等於把 V2 字典裡不存在的碼寫回資料（理由見 module docstring）。
    pass
