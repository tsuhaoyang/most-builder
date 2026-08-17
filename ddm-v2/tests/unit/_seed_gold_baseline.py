"""Gold 基線釘值的**唯一出處**（測試共用，不得各檔硬寫）。

- `SEED_GOLD_N`：seed gold 集（A5 fixture 白名單）的筆數——**seed 基線不動**。
- `PROMOTED_GOLD_N`：IE 覆核核准後轉正的正式 gold 筆數（D3-019 首批 21 筆＋
  D3-021 第二批 3 筆（g27–g29）＋D3-022 重切裁決落地 4 筆（g30–g33），
  全部 2026-08-17，IEC141289）。
- `IE_MODIFIED_GOLD_N`：其中 `ie_modified: true` 的筆數（D3-022 IE 重切的
  g30/g31/g32——IE 改過 plan 內容＝真實 ground truth，**計入** planner 段
  Plan 層指標；其餘轉正案例全部 `ie_modified: false` 原樣核准 → 自我指涉
  排除。rule planner 恆單 action，對多 action gold 必然拿 0——Plan 層指標自
  seed 基線 0.6667／0.5714 降為 0.3333／0.2353 是**預期且誠實**的分數變化，
  不是迴歸；把 ie_modified=true 案例錯誤排除（分數回跳）即紅）。
- `GOLD_TOTAL_N`：tests/gold/wi_plans/ 的總筆數（compile 段與報告 n 用）。
- `G01_TOTAL_TMU`：g01_acquire_dimm 的引擎實算 TMU（A0 B0 G6 A0 B0 P0 A0＝6.0）。

使用者：`test_planner_eval.py`（基線釘值＋CLI 報告）、
`test_gold_harvest_recompile.py`（relock 重算後值不變）、
`test_gold_promotion.py`（轉正守門）。
新增 gold case 或引擎/rule-set 重鎖時只改這裡與對應的分數釘值。
"""
from __future__ import annotations

SEED_GOLD_N = 3
PROMOTED_GOLD_N = 28
IE_MODIFIED_GOLD_N = 3
GOLD_TOTAL_N = SEED_GOLD_N + PROMOTED_GOLD_N
G01_TOTAL_TMU = 6.0
