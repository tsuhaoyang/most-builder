"""Seed gold 基線釘值的**唯一出處**（測試共用，不得各檔硬寫）。

- `SEED_GOLD_N`：目前 seed gold 集（tests/gold/wi_plans/）的筆數。
- `G01_TOTAL_TMU`：g01_acquire_dimm 的引擎實算 TMU（A0 B0 G6 A0 B0 P0 A0＝6.0）。

使用者：`test_planner_eval.py`（基線釘值＋CLI 報告）、
`test_gold_harvest_recompile.py`（relock 重算後值不變）。
新增 gold case 或引擎/rule-set 重鎖時只改這裡與對應的分數釘值。
"""
from __future__ import annotations

SEED_GOLD_N = 3
G01_TOTAL_TMU = 6.0
