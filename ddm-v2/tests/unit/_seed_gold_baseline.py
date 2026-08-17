"""Gold 基線釘值的**唯一出處**（測試共用，不得各檔硬寫）。

- `SEED_GOLD_N`：seed gold 集（A5 fixture 白名單）的筆數——**seed 基線不動**。
- `PROMOTED_GOLD_N`：IE 覆核核准後轉正的正式 gold 筆數（D3-019 首批 21 筆，
  2026-08-17，IEC141289；全部 `ie_modified: false` 原樣核准 → planner 段
  Plan 層指標**全數排除**，指標必須維持 seed 基線 0.6667／0.5714——
  轉正後指標上跳＝自我指涉假象，橡皮圖章回歸就是守這個）。
- `GOLD_TOTAL_N`：tests/gold/wi_plans/ 的總筆數（compile 段與報告 n 用）。
- `G01_TOTAL_TMU`：g01_acquire_dimm 的引擎實算 TMU（A0 B0 G6 A0 B0 P0 A0＝6.0）。

使用者：`test_planner_eval.py`（基線釘值＋CLI 報告）、
`test_gold_harvest_recompile.py`（relock 重算後值不變）、
`test_gold_promotion.py`（轉正守門）。
新增 gold case 或引擎/rule-set 重鎖時只改這裡與對應的分數釘值。
"""
from __future__ import annotations

SEED_GOLD_N = 3
PROMOTED_GOLD_N = 21
GOLD_TOTAL_N = SEED_GOLD_N + PROMOTED_GOLD_N
G01_TOTAL_TMU = 6.0
