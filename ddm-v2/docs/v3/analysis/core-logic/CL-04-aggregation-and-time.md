# CL-04：列合計、SIMO 與時間鏈（可執行核心邏輯）

> 分類：核心邏輯 ｜ 來源：`calculation_v2.calculate_row / calculate_analysis_total`（v3 實碼）＋裁決（SIMO：UX v3／引擎 max）
> 合計只能有一個實作（DISC-03：v3 有四處、其一漏排 SIMO——本文件為唯一規格）。

## 1. 列（row）計算

```
base_tmu     = Σ slot_tmu（CL-01）           …quantize 3 位
effective_tmu = base_tmu × frequency          …frequency 為 float > 0（400/422 擋 ≤0）
effective_seconds = effective_tmu × 0.036     …quantize 4 位
```

`frequency`（整列重複）與 `repeat_count`（單格重複，CL-01）語意不同、可並存。

## 2. SIMO（雙手同時）——裁決後規格

- **輸入（UX，沿用 v3 心智）**：列可標 `simo_with_row_id` 指向配對列（同 worksheet 內、不可自指、目標存在——422 `SIMO_PAIR_INVALID`；v3 實況不驗證，DISC）。
- **儲存**：service 以 union-find 把配對收斂為 `simo_group_id`。
- **合計（引擎，v2 裁決＝group-max）**：
```
total_tmu = Σ(非SIMO列 effective_tmu) + Σ(每個 simo_group 的 max(effective_tmu))
```
- （v3 實況＝標記列貢獻 0、由主列計時；標錯方向會低估——已裁決不移植，UX 不變、數學更安全。報表如需顯示「被覆蓋列」，以 `covered_by` 標示。）

## 3. 時間鏈（normal / standard）

```
normal_seconds   = total_tmu × 0.036
standard_seconds = normal_seconds × (1 + allowance_percent/100)   …allowance 掛 worksheet（案件）級
```
- v3 實況：allowance 只在 AnalysisCase 層接線、workbench 層無（DISC-04 的一部分）；v2 統一掛 worksheet，並與 Level System 的列級 `coefficient`（難度係數）語意分離——OQ-002 追蹤命名/預設。
- 匯出同時給 normal 與 standard 兩欄；對 LB 的輸出合約給 normal（寬放屬 MOST 端政策）。

## 4. 快照與重算

- 每列存 `slot_inputs`（原始輸入＝真相）＋`computed`（可重生快取）＋值版本參照。
- 重算觸發點：slot/context/frequency/SIMO 變更、worksheet 儲存；合計隨列重算原子更新（同交易）。
- 專案/範本層的 totals 一律由列快照經**本規格**重新聚合，禁止另寫加總（v3 WI Set bug 的教訓）。

## 5. 驗收條件

- Given 兩列配對 SIMO（29 與 28），Then 合計取 29；交換標記方向合計不變。
- Given freq=0，Then 422。
- Given 非 SIMO 三列 28/29/6，Then 合計 63、normal=2.268s。
- Given allowance=10%，Then standard=normal×1.1（4 位）。
- Given 刪除群組其中一列，Then 群組合計立即重算。
