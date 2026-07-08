# MiniMOST AI Dictionary v1

本檔案是給 AI / Claude / Copilot / Backend 使用的 MiniMOST 字典規格。  
主要用途：讓系統可以建立 Vue3 前端選項、FastAPI 計算邏輯、MI 語句生成、Excel 匯出與測試案例。

## 全域換算

- 1 TMU = 0.036 秒
- X 製程時間：`TMU = seconds / 0.036`

## Sequence Models

| code | 中文 | sequence | slot keys |
|---|---|---|---|
| GENERAL_MOVE | 一般移動 | A B G A B P A | A1, B1, G, A2, B2, P, A3 |
| CONTROLLED_MOVE | 控制移動 | A B G M X I A | A1, B1, G, M, X, I, A2 |

## Slot 設計原則

General Move 的三個 A 必須拆成 `A1`, `A2`, `A3`，避免系統混淆：

- A1：取得前距離，modal，伸手距離 / 手度 / 腳步取最大值
- A2：移動距離，modal，伸手距離 / 手度 / 腳步取最大值
- A3：返回距離，只看伸手距離
- B1/B2：身體動作，單選，沒有 0 TMU 選項
- G：取得控制，單選
- P：基礎動作單選 + 附加條件複選最多 2 個
- M：控制移動，Verb / 手度 / 腳步取最大值
- X：製程時間，固定秒數或 user 輸入秒數換算 TMU
- I：對位/檢查，單選

## 主要計算邏輯

### A

```text
A1_TMU = max(reach_distance_tmu, hand_degree_tmu, foot_step_tmu)
A2_TMU = max(reach_distance_tmu, hand_degree_tmu, foot_step_tmu)
A3_TMU = selected_reach_distance_tmu
```

### B / G / I

```text
TMU = selected_option.tmu_value
```

### P

```text
P_TMU = selected_base_action.tmu_value + sum(selected_modifiers.tmu_value)
selected_modifiers.count <= 2
not both(P_INSERT, P_SNAP_FIT)
```

P 的 MI 文字規則：

- 對準：作為前綴，例如 `對準組`、`對準插入`、`對準卡合`
- 插入：顯示自身
- 卡合：顯示自身
- 較難處理：只計算，不顯示
- 施加壓力：只計算，不顯示
- 插入 + 卡合：不允許同時選

### M

```text
M_TMU = max(verb_tmu, hand_degree_tmu, foot_step_tmu)
```

手度未選時預設 0 TMU；腳步未選時預設 0 TMU。

### X

```text
固定秒數項目：X_TMU = fixed_seconds / 0.036
機台製程項目：X_TMU = user_input_seconds / 0.036
```

固定 0.216 秒的項目 = 6 TMU。

## 測試案例

| 情境 | 計算 | 結果 |
|---|---|---|
| P: 組(一種方向)+對準+較難處理 | 16+8+8 | 32 TMU, MI=對準組 |
| P: 放(一種方向)+對準+插入 | 16+8+8 | 32 TMU, MI=對準插入 |
| P: 放(一種方向)+對準+卡合 | 16+8+16 | 40 TMU, MI=對準卡合 |
| M: 理<=4(10)+手度<=180+無腳步 | max(6,10,0) | 10 TMU, MI=理 |
| X: 刷PPID | 0.216/0.036 | 6 TMU |

## AI 使用方式

Claude/Copilot 可以直接讀 `minimost_ai_dictionary_v1.json`，依據以下欄位產生系統：

- `sequence_models`：決定 workbench 上的 slot 順序
- `slot_definitions`：決定每個 slot 的 UI 型態
- `parameters`：決定選項、TMU、MI 顯示與計算規則
- `rules`：產生 backend validation / unit tests
- `examples`：產生 acceptance tests

請勿直接把 `A B G A B P A` 寫成重複欄位，必須使用 `A1/B1/G/A2/B2/P/A3`。
