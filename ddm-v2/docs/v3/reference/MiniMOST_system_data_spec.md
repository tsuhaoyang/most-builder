# MiniMOST 系統資料結構規格 v0.1

來源檔案：`MiniMOST_rag.xlsx`。本規格把 Excel 中的「一般移動」與「控制移動」拆成可供系統、資料庫、API 與 RAG 使用的標準資料結構。

## 1. 設計原則

1. **字典版本化**：所有分析結果必須綁定 `dictionary_version_id`，避免日後字典修改後舊報表無法追溯。
2. **句型、詞庫、index、規則分離**：不要把顯示文字、TMU index、勾選規則、升級規則混在同一欄。
3. **同一參數不同角色要分開**：`A` 在取得、移動、返回都會出現，系統應用 `slot_key` 區分。
4. **支援人工覆寫，但要留紀錄**：MiniMOST 的判斷常需要 IE 工程師確認，所以覆寫 index 或選項時要記錄原因。
5. **計算過程可稽核**：系統不只存總 TMU，也要存每個 slot 的 base index、規則調整、頻次與換算結果。

## 2. Excel 到系統資料的分層

| 層級 | 來源 | 系統意義 |
|---|---|---|
| 常數層 | 第 1 列 | TMU 與秒數換算 |
| 模型層 | 一般移動、控制移動標題與句型 | sequence model + sentence template |
| 參數卡層 | A/B/G/P/M/X/I 區塊 | parameter slot + parameter option |
| 詞庫層 | 手別、目標物、從哪裡、到哪裡 | lexical option |
| 規則層 | 單選、複選、升級索引、顯示規則 | rule engine |
| 分析層 | 使用者實際建立的動作步驟 | analysis case / step / calculation result |

## 3. 核心資料表

### `system_constants`
- 目的：系統換算常數
- 主要欄位：`key, value, unit, source`
- 說明：例如 TMU_TO_SECOND = 0.036；SECOND_TO_TMU = 27.8

### `dictionary_version`
- 目的：MiniMOST 字典版本
- 主要欄位：`version_id, name, locale, status, effective_from, source_file`
- 說明：每次 Excel 匯入都應生成版本；分析結果要綁定版本以便追溯

### `sequence_model`
- 目的：序列模型
- 主要欄位：`model_id, code, name, template_text, selector_mode`
- 說明：General Move = ABGABPA；Controlled Move = ABGMXIA

### `parameter_slot`
- 目的：模型中的參數位置
- 主要欄位：`slot_id, model_id, slot_order, parameter_code, role, aggregation_rule`
- 說明：同一參數 A 可能出現多次，要用 role 區分：obtain/move/return

### `parameter_option`
- 目的：A/B/G/P/M/X/I 的 index 選項
- 主要欄位：`option_id, parameter_code, action_label, checkbox_label, index_value, unit, threshold_text, display_text`
- 說明：來源於 Excel 上方兩塊參數卡

### `lexical_option`
- 目的：語句字典
- 主要欄位：`option_id, dictionary_type, text, locale, normalized_text, active`
- 說明：包含左手/右手/雙手、目標物、從哪裡、到哪裡、where 等詞庫

### `rule`
- 目的：選項規則
- 主要欄位：`rule_id, trigger_option_id, rule_type, effect_type, effect_value, message`
- 說明：例如升一級索引、升二級索引、只顯示此字樣、不顯示字樣、相依條件

### `analysis_case`
- 目的：一次動作分析文件
- 主要欄位：`case_id, product, station, operation, analyst, allowance_percent, dictionary_version_id`
- 說明：使用者建立的某站別某工序分析

### `analysis_step`
- 目的：單一步驟分析
- 主要欄位：`step_id, case_id, step_no, hand, model_id, frequency, notes, video_range`
- 說明：一個 method step 對應一組 MiniMOST sequence

### `step_slot_value`
- 目的：步驟中每個 slot 的選項值
- 主要欄位：`step_id, slot_id, option_id, manual_index_value, selected_text, rationale`
- 說明：支援人工覆寫與稽核

### `step_rule_application`
- 目的：步驟套用規則紀錄
- 主要欄位：`step_id, rule_id, before_index, after_index, reason`
- 說明：保存計算過程，方便審核

### `calculation_result`
- 目的：計算結果
- 主要欄位：`step_id, base_tmu, rule_adjustment_tmu, total_tmu, normal_time_sec, standard_time_sec`
- 說明：不要只存結果；也要存版本與拆解明細

## 4. Sequence Model / Slot 定義

| model_id | slot_order | slot_key | parameter_code | role | selector/aggregation | 說明 |
|---|---:|---|---|---|---|---|
| general_move | 1 | A_obtain | A | obtain_distance | single_max | 取得目標物前的手距離、手度、腳步距離取較大值 |
| general_move | 2 | B_obtain | B | obtain_body | single | 取得前身體動作，例如眼部動作、起身/彎腰/坐、站立 |
| general_move | 3 | G | G | gain_control | single_or_multi_by_option | 取得控制，例如接觸、抓握、抓取、拿取、拔出 |
| general_move | 4 | A_move | A | move_distance | single_max | 移動目標物距離；若選手度需觸發翻轉+目標物顯示規則 |
| general_move | 5 | B_move | B | move_body | single | 移動過程身體動作 |
| general_move | 6 | P | P | placement | single_or_multi | 釋放、放置、組、對準、插入、卡合、施加壓力等 |
| general_move | 7 | A_return | A | return_distance | single | 手返回距離 |
| controlled_move | 1 | A_obtain | A | obtain_distance | single_max | 取得目標物前的手距離、手度、腳步距離取較大值 |
| controlled_move | 2 | B_obtain | B | obtain_body | single | 取得前身體動作 |
| controlled_move | 3 | G | G | gain_control | single_or_multi_by_option | 取得控制 |
| controlled_move | 4 | M | M | controlled_motion | single_max_or_fixed | 按鈕、推、拉、貼附、去除、撕除、折、擦拭、旋轉、撕開、腳步等 |
| controlled_move | 5 | X | X | process_time | single | 壓合、卡合&壓合、熱熔、點膠、鎖附、鐳雕、掃碼等處理時間 |
| controlled_move | 6 | I | I | alignment_inspection | single | 檢查、確認、對準、對齊，包含視線範圍/點/線/兩點 |
| controlled_move | 7 | A_return | A | return_distance | single | 手返回距離 |

## 5. 規則引擎建議

| rule_type | effect_type | effect_value | 適用位置 | 說明 |
|---|---|---|---|---|
| selector | aggregate | max_index | A obtain / A move / M | 同一 slot 有手距離、手度、腳步時取較大 index |
| selector | aggregate | single | B / G / X / I / return A | 同一 slot 只允許選一項 |
| selector | aggregate | multi | P / 特定 G | 允許複選，需逐項套用 display 與 index 規則 |
| display | show_only_this_text | True | P 插入 / 卡合 | 勾選後句子只顯示該字樣，不顯示完整原始選項 |
| display | hide_text | True | P 較難處理 / 施加壓力 | 選項影響計算但不輸出到句子 |
| index_adjustment | upgrade_index_level | 1 | P 組/對準/較難處理 | 依目前 P index 往上升一級；需由 index_ladder 定義升級後值 |
| index_adjustment | upgrade_index_level | 2 | P 卡合/施加壓力 | 依目前 P index 往上升二級 |
| dependency | require_display_token | 翻轉+目標物 | A_move 手度 | 如果移動 A 選手度，句子需出現翻轉+目標物 |
| calculation | convert_seconds_to_tmu | seconds*27.8 | X process_time | 處理時間可用秒數轉 TMU；若已有固定 TMU 則直接使用 |

## 6. 計算邏輯

```text
slot_effective_tmu = base_index_tmu + rule_adjustment_tmu
step_base_tmu = Σ(slot_effective_tmu)
step_total_tmu = step_base_tmu × frequency
normal_time_sec = step_total_tmu × 0.036
standard_time_sec = normal_time_sec × (1 + allowance_percent / 100)
```

對 `X` 處理時間，建議支援兩種模式：

```text
calculation_mode = fixed_tmu          # 字典已給定 TMU
calculation_mode = seconds_to_tmu     # 使用者輸入秒數，再乘以 27.8
```

## 7. Excel 匯入 Mapping

| Excel 區域 | 系統表 | 說明 |
|---|---|---|
| A1:K1 | `system_constants` | 時間換算常數 |
| A2:C2 | `sequence_model + sentence_template` | 一般移動模板：從 + 從哪裡 + A+B + G + 對象/目標物 + A+B + P + A + 到哪裡 |
| A48:C48 | `sequence_model + sentence_template` | 控制移動模板：從 + 從哪裡 + A+B + G + 對象/目標物 + M + X + I + A + 到哪裡 |
| D4:AU18 | `parameter_slot + parameter_option + rule` | 一般移動參數卡與 P 額外規則 |
| B21:AW47 | `lexical_option` | 一般移動語句詞庫：手別、目標物、從哪裡、釋放對象、到哪裡 |
| D50:AU66 | `parameter_slot + parameter_option + rule` | 控制移動參數卡，包含 M/X/I |
| B67:AW94 | `lexical_option` | 控制移動語句詞庫：手別、目標物、從哪裡、控制到哪裡、where、返回 |
| AQ89 | `ignore_or_comment` | 看起來是暫存公式結果 200000/43600，匯入時建議忽略或標記為 orphan_cell |

## 8. JSON 範例

```json
{
  "dictionary_version": {
    "version_id": "minimost_2026_06_v1",
    "locale": "zh-TW",
    "source_file": "MiniMOST_rag.xlsx",
    "tmu_to_second": 0.036,
    "second_to_tmu": 27.8
  },
  "sequence_models": [
    {
      "model_id": "general_move",
      "code": "ABGABPA",
      "name": "一般移動",
      "template": "{hand} 從 {from_location} {A_obtain}{B_obtain}{G} {object} {A_move}{B_move}{P} {to_location} {A_return}"
    },
    {
      "model_id": "controlled_move",
      "code": "ABGMXIA",
      "name": "控制移動",
      "template": "{hand} 從 {from_location} {A_obtain}{B_obtain}{G} {object} {M} {controlled_to} {X} {I} {where} {A_return}"
    }
  ],
  "analysis_step_example": {
    "step_no": 1,
    "hand": "右手",
    "model_id": "general_move",
    "object": "導電布",
    "from_location": "捡料架",
    "to_location": "MB",
    "frequency": 1,
    "slot_values": [
      {
        "slot_key": "A_obtain",
        "selected_option": "伸手 <=4(10)",
        "index_value": 3
      },
      {
        "slot_key": "B_obtain",
        "selected_option": "無",
        "index_value": 0
      },
      {
        "slot_key": "G",
        "selected_option": "抓握",
        "index_value": 16
      },
      {
        "slot_key": "A_move",
        "selected_option": "伸手 <=8(20)",
        "index_value": 6
      },
      {
        "slot_key": "B_move",
        "selected_option": "無",
        "index_value": 0
      },
      {
        "slot_key": "P",
        "selected_option": "放 無方向",
        "index_value": 6
      },
      {
        "slot_key": "A_return",
        "selected_option": "返回 <=2(5)",
        "index_value": 1
      }
    ],
    "calculation": {
      "base_tmu": 32,
      "frequency": 1,
      "total_tmu": 32,
      "normal_time_sec": 1.152
    }
  }
}
```

## 9. 建議的 API / 服務邊界

| API | 用途 |
|---|---|
| `POST /dictionary/import` | 匯入 Excel，建立新版字典 |
| `GET /dictionary/{version_id}/sequence-models` | 取得一般移動/控制移動模型 |
| `GET /dictionary/{version_id}/options?slot_key=P` | 依 slot 取得可選選項 |
| `POST /analysis-cases` | 建立分析文件 |
| `POST /analysis-steps/preview` | 預覽句子與 TMU，不儲存 |
| `POST /analysis-steps` | 儲存一個 MiniMOST step |
| `GET /analysis-cases/{case_id}/report` | 取得完整標準工時報表 |

## 10. 待確認事項

1. `手度` 建議標準化命名為「手部角度」或「手腕/手部翻轉角度」。
2. `眼步動作` 可能是「眼部動作」，建議統一。
3. `理` 可能是錯字或現場術語，需確認是否代表某個 M 控制移動。
4. 簡繁體混用建議用 `normalized_text` 保留統一詞，原始 Excel 詞放 `raw_text`。
5. `AQ89 = 4.587155963302752` 看起來像暫存計算，匯入器應忽略或標記為 orphan cell。
