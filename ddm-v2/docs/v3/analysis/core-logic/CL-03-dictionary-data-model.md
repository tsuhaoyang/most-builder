# CL-03：字典資料關聯模型（可執行核心邏輯）

> 分類：核心邏輯 ｜ 來源：v3 `models/dictionary.py`＋`default_dictionary_seed.py`＋`dictionary_import.py`（實碼）
> 這是 v3 的資料關聯真理：**一切值都是版本化字典資料、一切分析物綁版本、一切計算存快照**。v2 載體＝rule-set 體系（對映見 §4）。

## 1. 關聯圖（v3 概念，保留）

```
DictionaryVersion（版本；全系統唯一 is_active）
 ├─ 1─* SequenceModel（GM/CM；code、sequence_pattern）
 │        └─ 1─* ParameterSlot（slot_key、parameter_code、slot_order、每模型 7 格）
 │                 └─ 1─* ParameterOption（選項＝值的最小單位）
 └─ 1─* LexicalOption（語彙：hand/object/from_location/to_location/tool/process_term）

每個分析物（sequence/module/WI/case）→ dictionary_version_id（凍結語境）
每次計算 → calculation_snapshot_json（凍結結果，可稽核可回放）
```

## 2. ParameterOption——值的最小單位（欄位語意）

| 欄位群 | 欄位 | 語意 |
|---|---|---|
| 識別 | option_code（版本+slot 內唯一）、control_key | code 首字母＝參數；control_key 區分同 slot 多控制（reach_distance/hand_degree/foot_step/verb/base_action/modifier/option/x_option） |
| 顯示 | display_text_zh／helper_text_zh | UI 標籤／輔助說明 |
| 句子 | sentence_text_zh／display_rule | 組句用字／P 三態（CL-02） |
| 計值 | tmu_value／fixed_seconds／seconds_source | 直接值／X 固定秒／X 值來源（fixed_seconds｜user_input_seconds） |
| 檢索 | normalized_text_zh／synonyms_json | 正規化字（**必須經 normalization 產生**——v3 實況常直接 copy，DISC）／同義詞 |
| 治理 | is_active／sort_order | 軟停用／排序 |

## 3. 版本生命週期（規則）

```
建立：Excel 匯入（is_active=False）｜ seed（首次 active）｜ clone（深拷貝成 draft）
編輯：僅 draft 版可改值；選項刪除＝draft 硬刪、active 軟刪
發佈 publish：驗「A~I 每參數 ≥1 active 選項」→ 全域唯一 active 切換 → 失效同義詞快取
發佈後：值不可變（v3 實況可改——DISC-05，不移植）；唯同義詞可增補（僅影響建議層）
```

## 4. v2 落地對映

| v3 | v2 載體 | 差異 |
|---|---|---|
| DictionaryVersion | `rule_sets`（code+status published 凍結） | v2 多血緣/快照回放 |
| ParameterOption（泛型單表） | `rule_a_bands`…`rule_i_options`（強型別子表） | 匯入器負責轉換；DB 約束更強 |
| LexicalOption | `work_vocab_items` | v2 多中英名/external_code |
| synonyms_json（JSONB on option） | `rule_option_synonyms` 表＋UNIQUE 防歧義 | impl-05 §2（S3） |
| is_active 全域切換 | worksheet 的 default_rule_set_id＋cycle 快照 | v2 允許多版本並用（依快照），不需全域唯一 active |
| calculation_snapshot_json | `most_cycles.computed`＋`rule_set_id` 快照 | 同哲學 |

## 5. 驗收條件

- Given draft 版缺 X 參數 active 選項，When publish，Then 400/422 且不切換。
- Given active 版，When 改選項 TMU，Then 拒絕（v2：409 published 不可變）。
- Given 同義詞增補於 published 版，Then 允許且建議層快取即時失效。
- Given clone，Then 新版本與來源逐列相等、is_active=False、可獨立編輯。
- Given 任一分析物，Then 必存在其值版本參照，且重算（同版本）結果與快照一致。
