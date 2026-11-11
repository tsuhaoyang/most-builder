"""Gold 基線釘值的**唯一出處**（測試共用，不得各檔硬寫）。

- `SEED_GOLD_N`：seed gold 集（A5 fixture 白名單）的筆數——**seed 基線不動**。
- `PROMOTED_GOLD_N`：IE 覆核核准後轉正的正式 gold 筆數（D3-019 首批 21 筆＋
  D3-021 第二批 3 筆（g27–g29）＋D3-022 重切裁決落地 4 筆（g30–g33）＋
  D3-023 第三批 7 筆（g34–g40：判型旗照預設確認後解鎖的取放/取組配對 GM）＋
  D3-026 第五批 9 筆（g41–g49：X/I 型分五型處置——g41＝E 型純 I 句窄豁免帶
  真 TMU 6.0，其餘 8 筆 incomplete 裁決（expected_incomplete_reason 逐型
  釘值）誠實轉正等佈局），以上全部 2026-08-17；＋D3-028 第六批 8 筆
  （g50–g57：Q1/Q2/Q3 切分批次確認解鎖 5 筆（g50–g52 帶真 TMU 3.0、
  g53/g54 誠實 incomplete `distance_unstated`——g54 即 distance-rulings C11
  的結案「維持資訊不足」）＋Q5 判型答案 3 筆（g55–g57，`ie_modified: true`）），
  2026-08-17；核准人全部 IEC141289）。
- `IE_MODIFIED_GOLD_N`：其中 `ie_modified: true` 的筆數（D3-022 IE 重切的
  g30/g31/g32＋D3-028 IE 判型答案的 g55/g56/g57——IE 改過 plan 內容＝真實
  ground truth，**計入** planner 段 Plan 層指標；其餘轉正案例全部
  `ie_modified: false` 原樣核准 → 自我指涉排除。分數變化逐輪誠實記錄：
  seed 基線 0.6667／0.5714 → D3-022 後 0.3333／0.2353（重切 3 筆進分母，
  rule planner 恆單 action 對多 action gold 必然拿 0，**下降**是預期）→
  D3-028 後 0.5556／0.4348（判型答案 3 筆進分母，各為單 action 且 span 與
  planner 輸出相同 → 三筆全對，**上移**是預期）。
  **上移的誠實邊界**：g55–g57 的 IE 修改內容是 `action_type`（判型），
  evidence span 與 action 數維持 planner 輸出——boundary span 那 3 分是
  「planner 自己的 span 經 IE 覆核未改」，證據力弱於 IE 重新劃界的案例；
  引用 boundary F1 時必須連這句一起講。把 ie_modified=true 案例錯誤排除
  （分數回跳前一輪）即紅。）
- `GOLD_TOTAL_N`：tests/gold/wi_plans/ 的總筆數（compile 段與報告 n 用）。
- `G01_TOTAL_TMU`：g01_acquire_dimm 的引擎實算 TMU（A0 B0 G6 A0 B0 P0 A0＝6.0）。

使用者：`test_planner_eval.py`（基線釘值＋CLI 報告）、
`test_gold_harvest_recompile.py`（relock 重算後值不變）、
`test_gold_promotion.py`（轉正守門）。
新增 gold case 或引擎/rule-set 重鎖時只改這裡與對應的分數釘值。
"""
from __future__ import annotations

SEED_GOLD_N = 3
PROMOTED_GOLD_N = 52
IE_MODIFIED_GOLD_N = 6
GOLD_TOTAL_N = SEED_GOLD_N + PROMOTED_GOLD_N
G01_TOTAL_TMU = 6.0
