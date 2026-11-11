# 03 · 資料模型與 AI 字典對照（v4 → v2）

> 唯讀審查文件。所有結論以實讀程式碼／schema 為據，證據標注 `檔案:行號`。
> 本文件不修改 v4、不改 v2 程式碼。
>
> - v4 = `minimost_level/minimost/apps/api`（另一位 IE 獨立延伸開發）
> - v2 = `ddm-v2`（現行系統，MOST engine 為單一權威，TMU 黃金值鎖 GM=28 / CM=29）
>
> 審查日期：2026-09-04

---

## 0. TL;DR（給整合決策者）

1. **字典/規則資料層概念相同，實作分歧**：兩邊都源自同一份 `minimost_ai_dictionary_v1.json`（metadata `created_at` 完全相同：`2026-06-25T08:08:19`）。但 v4 把字典**正規化成通用 5 表**（`sequence_models` / `parameter_slots` / `parameter_options` / `lexical_options` + 版本頭 `dictionary_versions`），v2 把它**攤平成 MOST-domain 專用的七張規則子表**（`rule_a_bands` / `rule_b_options` / `rule_g_actions` / `rule_p_bases` / `rule_p_addons` / `rule_m_*`(5 表) / `rule_x_options` / `rule_i_options`）＋ `rule_sets` 版本頭。
2. **字典內容有實際差異，且會影響 TMU**：v2 版比 v4 版**多一個 M 選項 `M_PRESS`（按壓 / fixed 3 TMU）**，且 v2 版把 CONTROLLED_MOVE 的返回槽命名為 **`A2`**，v4 版已改名為 **`A3`**（v4 有專門 migration `58a3d1cca6f1` 做此改名）。詳見 §3。
3. **v4 有大量 v2 完全沒有的資料物件**：ESOP Builder（5 表）、Line Balance Scenario、Line Balance Layout Scenario、Level System Plan（3 表，獨立 plan-level 快照）、Analysis Case 審批工作流（3 表）、Action Module / WI Template / Process Route / WI Set Project「四層範本鏈」（8 表）。詳見 §4。
4. **Level System 是最大的模型哲學衝突點**。v2 的 level 是 `level_entry` **1:1 掛在 `wi_row`（活資料，隨 worksheet 版本）**；v4 的 level 是 `level_system_plans` **獨立快照層（複製 WI Set item，永不回寫源）**。兩者不可直接對映，整合時必須明確選邊。詳見 §2.4 與 §4.3。
5. **整合對計算正確性的風險點**：v4 的 TMU 是「凍結在 JSON 快照」（`calculation_snapshot_json` 遍布各表），而 v2 的鐵則是「引擎為單一權威、`slot_inputs` 為唯一權威輸入、其餘皆可重生快取」。若把 v4 的快照 TMU 直接匯入 v2，等於引入**第二份可寫真相**，違反 v2 的回放鐵則（`rule_set_tables.py:14` 明列 `load_rule_set_from_db` 永不得依 is_active 過濾，同源原則）。整合必須以 v2 引擎重算，不得信任 v4 快照值。

---

## 1. 版本頭與字典組織：v4「通用字典」vs v2「MOST 專用規則集」

### 1.1 v4：`DictionaryVersion` + 5 個通用表

證據：`app/models/dictionary.py`

| v4 表 | 檔案:行號 | 角色 |
|---|---|---|
| `dictionary_versions` | `dictionary.py:26`（`class DictionaryVersion`, `__tablename__` :27） | 字典版本頭；`version_name` unique、`is_active`、`import_warnings_json` |
| `sequence_models` | `dictionary.py:44`（`__tablename__` :45） | 序列模型（`code`=GENERAL_MOVE/CONTROLLED_MOVE、`sequence_pattern`="A B G A B P A"） |
| `parameter_slots` | `dictionary.py:59`（`__tablename__` :60） | 槽位定義（`slot_key`=A1/B1/G/A2/B2/P/A3、`parameter_code`=A/B/G/P/M/X/I、`slot_order`、`is_required`） |
| `parameter_options` | `dictionary.py:77`（`__tablename__` :78） | 槽位選項（通用一表容納所有 A/B/G/P/M/X/I 的值） |
| `lexical_options` | `dictionary.py:113`（`__tablename__` :114） | 詞彙（`category`=hand/object/from_location/to_location/tool/process_term） |

關鍵設計：`parameter_options` 是**單一大表**，靠欄位承載所有參數型別的差異：
`option_code` / `control_key`（reach_distance/hand_degree/foot_step/verb/base_action/modifier）/ `index_value` / `tmu_value` / `fixed_seconds` / `seconds_source`（'fixed_seconds' | 'user_input_seconds'）/ `display_rule`（'prefix_visible_term' | 'show_self' | 'hidden'）/ `rule_type` / `rule_effect`(JSON) / `synonyms_json`（`dictionary.py:80-104`）。

### 1.2 v2：`RuleSet` + 七類規則子表（實際 12 張表）

證據：`src/ddm_v2/models/v2/rule_set.py`、`rule_set_tables.py`

| v2 表 | 檔案:行號 | 對應 MOST 參數 |
|---|---|---|
| `rule_sets` | `rule_set.py:18`（`class RuleSet`） | 版本頭；`code` unique、`status`(draft/published/retired)、`is_active`（全庫僅一 true，partial unique index `rule_set.py:48`）、`provenance`(certified_import/manual/cloned)、`system_tmu_multiplier` |
| `rule_a_bands` | `rule_set_tables.py:38`（`class RuleABand`） | A（三分量 reach/twist/foot，取 max；`max_value` NULL=overflow） |
| `rule_b_options` | `rule_set_tables.py:54` | B（身體動作，1205 值） |
| `rule_g_actions` | `rule_set_tables.py:74` | G（`requires_modifier` gating 為程式邏輯） |
| `rule_p_bases` | `rule_set_tables.py:95` | P base |
| `rule_p_addons` | `rule_set_tables.py:116` | P addon（`needs_precision`、`max_select`、`display_rule` 三態） |
| `rule_m_ladder_bands` | `rule_set_tables.py:141` | M 距離階梯 |
| `rule_m_foot_bands` | `rule_set_tables.py:154` | M 腳步帶 |
| `rule_m_verbs` | `rule_set_tables.py:169` | M 動詞（`pricing_kind`=fixed/ladder/foot/hand/rotate） |
| `rule_m_rotation_bands` | `rule_set_tables.py:192` | M 旋轉（直徑×圈數） |
| `rule_m_hand_bands` | `rule_set_tables.py:206` | M 手度（角度） |
| `rule_x_options` | `rule_set_tables.py:219` | X（`mode`=zero/seconds/fixed，seconds→引擎 ceil(sec/0.036)） |
| `rule_i_options` | `rule_set_tables.py:242` | I（`vision_scope`=normal/outside） |

詞彙在 v2 是獨立主數據表 `work_vocab_items`（`vocab.py:26`，`kind`=object/component/tool/from/to/hand），非掛在 rule_set 下。

### 1.3 對照結論

| 面向 | v4 | v2 | 整合含意 |
|---|---|---|---|
| 字典組織 | 通用 5 表，`parameter_options` 一表打天下 | MOST 專用 12 表，每參數一張（或多張） | v4→v2 需寫一個「通用選項 → 分表」的映射器；v2 分表把 MOST 語意編碼進 schema（CHECK 約束、`pricing_kind`、`max_value` overflow 語意），這是刻意的計算正確性防線 |
| M 參數 | 全部 M 選項擠在 `parameter_options`（v4 M 有 ~66 個 leaf entry，見 §3） | 分成 5 張表（ladder/foot/verb/rotation/hand）＋動詞 pricing_kind 決定計價法 | v4 的 M「一表」對映 v2「五表」是最複雜的映射；必須逐 `option_code` / `control_key` 判定落入哪張 v2 表 |
| 版本啟用 | `is_active`(bool) | `is_active`(bool) + partial unique index 強制全庫僅一 true + `load_rule_set` **不得依 is_active 過濾**（`rule_set_tables.py:13-18` docstring 闡明回放鐵則） | v2 有明確的「治理旗標 vs 回放」分離；v4 未見等價鐵則，匯入時不可沿用 v4 的啟用語意 |
| 詞彙 | `lexical_options`（掛字典版本） | `work_vocab_items`（獨立主數據，含 site_id 全域/站別、source_system 守門、軟刪） | v2 詞彙模型遠比 v4 完整（多租戶/來源治理），v4 詞彙可視為 v2 vocab 的子集匯入 |

---

## 2. WI/Cycle 核心資料鏈對照

### 2.1 v4 的 MOST workbench 鏈

證據：`app/models/most.py`

- `MostSequenceItem`（`most.py:28`）：workbench 完成的單筆序列模型。權威輸入 = `selected_slots_json`(Text)（`most.py:41`）；`calculation_snapshot_json`(Text)（:42）= 凍結計算結果供 audit。TMU 直接存欄：`tmu`/`effective_tmu`/`total_contribution_tmu`/`ct_seconds`（:52-62）。含 SIMO 語意（`is_simo`、`simo_with_row_id`，:57-58）。
- `MostMiStatement`（`most.py:65`）：分析容器（多 MI row 合計），`total_tmu`/`total_seconds`（:83-84）。
- `MostMiStatementSequence`（`most.py:93`）：MI ↔ sequence item 連結表 + 排序。
- `MostMiStatementItem`（`most.py:106`，`__tablename__` :114）：WI 大綱內「子動作快照」。刻意與源 `MostSequenceItem` 解耦（`source_sequence_id` 僅溯源、非活連結，:130-133 註解）。同樣把 TMU 存欄 + `calculation_snapshot_json`(:141)。

### 2.2 v2 的 WI 鏈

證據：`src/ddm_v2/models/v2/worksheet.py`

- `ProcessVersion`（`worksheet.py:48`）：輕量 SOP 版本頭，1:1 對 worksheet；發布凍結、改→另存新檔（`source_version_id` 血緣 :57）。
- `MostWorksheet`（`worksheet.py:62`，`__tablename__="most_worksheets"` :65）：WI 表頭，1:1 對 process_version；`default_rule_set_id`、`modeling_policy_version_id`、`level_policy_version_id`（policy 快照）、`revision_no`（樂觀鎖）。
- `WiRow`（`worksheet.py:103`，`__tablename__="wi_rows"` :106）：方法步；`id` 在同版本編輯期內穩定（改 MOST 不丟 level）；含 `object/from/to/tool_vocab_id` FK→`work_vocab_items`、`frequency`、`simo_group_id`、`provenance`(manual/bom_draft/imported)、`source_module_id`（模組實體化溯源）。
- `MostCycle`（`worksheet.py:147`，`__tablename__="most_cycles"` :150）：**GM/CM 七格填值**。`slot_inputs`(JSONB) = **權威原始輸入**；`computed`(JSONB)/`narrative_*`/`total_tmu`/`total_seconds` = **可重生快取**（`worksheet.py` MostCycle docstring 明列「slot_inputs 為權威，其餘升欄/快取」）。`rule_set_id`(RESTRICT) = 快照。
- `LevelEntry`（`worksheet.py:169`，`__tablename__="level_entries"` :172）：見 §2.4。

### 2.3 對照：權威輸入 vs 凍結快照（**計算正確性的關鍵分歧**）

| 面向 | v4 | v2 |
|---|---|---|
| 權威來源 | `selected_slots_json` + **凍結** `calculation_snapshot_json`（`most.py:41-42`） | `slot_inputs`(JSONB) 唯一權威；TMU/narrative **皆可由引擎重生**（`most_cycles` docstring） |
| TMU 存放 | 直接存多個 Float 欄（`tmu`/`effective_tmu`/`ct_seconds`/`total_contribution_*`，`most.py:52-62`），且各層（sequence item / MI item / template item）各存一份 | 存 `total_tmu`/`total_seconds` 升欄，但語意是「聚合快取」，源自單一引擎 |
| 單一權威 | 無明確「引擎為唯一權威」鐵則；快照散布多表 | 明確：backend engine 單一權威、黃金值鎖 GM=28/CM=29 |
| SIMO | `is_simo` + `simo_with_row_id`（row 級，`most.py:57-58`） | `wi_rows.simo_group_id`(Text，群組，`worksheet.py`) |

> **整合風險（務必落實）**：v4 每一層都自帶一份 TMU 快照。若整合時直接採信 v4 的 `calculation_snapshot_json` / `tmu` 欄寫入 v2，會在 v2 內產生「與引擎重算結果不一致」的第二真相，污染單一權威。**正確做法**：只匯入 v4 的 `selected_slots_json`（原始選擇）→ 映射成 v2 `slot_inputs` → 用 v2 引擎重算 → 比對 v4 快照值僅作為「移轉驗證」，不作為權威。

### 2.4 Level System 模型哲學衝突（重點）

| 面向 | v4 `LevelSystemPlan*` | v2 `LevelEntry` |
|---|---|---|
| 檔案 | `app/models/most.py:357`（`class LevelSystemPlan`, `level_system_plans`）、`LevelSystemPlanItem`(:389)、`LevelSystemNumberRule`(:437) | `worksheet.py:169`（`class LevelEntry`, `level_entries` :172） |
| 定位 | **獨立快照層**：由 WI Set Project 複製一份，永不回寫源（`most.py` LevelSystemPlan docstring：「Stores its own snapshot… never mutates the source project」） | **活資料**：1:1 掛 `wi_row`（FK→wi_rows, unique），隨 worksheet 版本 |
| 生命週期 | plan 有自己的 `status`(draft/released/archived) + `version` + `source_plan_id`（另存血緣）+ `released_at`/`archived_at`（migration `d4e5f6a7b8c9` 補欄） | 無獨立生命週期；跟隨 `most_worksheets.status`；驗證證據存 `level_validation_runs`（append-only，`level_validation.py:26`） |
| main/sub/cub | `main_group`/`main_instance_id`/`main_instance_name`/`sub_group`/`cub_group`/`cub_order`/`is_cub_locked`（`most.py` LevelSystemPlanItem 欄） | `level`(Text '1'/'1~2'/'1/3')、`countersignature`/`parent_countersignature`（巢狀 sub⊃cub）、`ascription`(僅 'main')、`order_in_group`（`worksheet.py` LevelEntry 欄） |
| nb（不可分割/站別限制） | `number_tag`/`number_limit`（item 級）＋ **plan 級 `LevelSystemNumberRule` 為 source of truth**（`most.py` docstring） | `number`/`number_count`（`worksheet.py` LevelEntry），無獨立 rule 表 |
| 難度/CT 調整 | `difficulty_factor` + `adjusted_ct_seconds`（`most.py` LevelSystemPlanItem） | `coefficient` + `second`（Computed `raw_seconds*coefficient` persisted，`worksheet.py` LevelEntry） |

> **對映結論**：v4 與 v2 的 Level System **不是同一資料形狀**。v4 是「WI Set → Level Plan 快照 → Line Balance」的分層流水線；v2 是「level 直接標註在 wi_row，供 LB 演算法讀」。整合時二選一：
> - (A) 把 v4 Level Plan 當成 v2 之上的「新分析層」平移進來（新增表），保留 v2 `level_entries` 不動；
> - (B) 用 v2 `level_entries` 語意吸收 v4 Level Plan 欄位（`difficulty_factor`→`coefficient`、`number_tag/limit`→`number/number_count`、`cub`→`countersignature`），放棄 v4 的獨立快照生命週期。
> 這是後續整合設計必須先拍板的分叉點，牽涉 §4.3。

---

## 3. AI 字典逐項差異（v4 `app/data` vs v2 `docs/v3/reference`）

兩檔同名 `minimost_ai_dictionary_v1.json`，同結構（top keys 皆為 `['metadata','sequence_models','slot_definitions','parameters']`），`metadata` **完全相同**（`version`=1.0、`created_at`=2026-06-25T08:08:19、`seconds_per_tmu`=0.036、notes 三條逐字相同）。

差異來自對兩檔做正規化（`json.dumps(sort_keys=True, indent=2)`）後 `diff`，共 **3 處實質差異**：

### 差異 1：v2 多出 M 選項 `M_PRESS`（按壓 / 3 TMU）

- v2 有、v4 無：
  ```json
  {
    "display_text_zh": "按壓",
    "input_type": "fixed_tmu",
    "option_code": "M_PRESS",
    "sentence_text_zh": "按壓",
    "source_note": "v3 現場字典同步 2026-07-14（v3 DB draft 版 v1_draft_202606290707 讀出：按壓 / fixed 3 TMU；IE 裁決補齊）",
    "tmu_value": 3
  }
  ```
- 證據：v2 檔於 M 參數末尾（`M_ROTATE_D50_2` 之後）多此節點；leaf 計數 v2 的 M = **67**，v4 的 M = **66**（其餘參數 A/B/G/P/X/I 計數兩邊相同：A=16,B=3,G=11,P=0,X=10,I=8）。
- 含意：**這是會影響 TMU 的差異**。v2 版字典包含 v4 缺少的「按壓 fixed 3 TMU」M 選項。若整合以 v4 字典為基準，會遺失此選項；若以 v2 為基準，v4 既有序列若曾用到等價動作會對不上。

### 差異 2：CONTROLLED_MOVE 返回槽命名 v2=`A2` vs v4=`A3`

- v2 `sequence_models` 中 CONTROLLED_MOVE 的 `slots` 末項為 `"A2"`；v4 為 `"A3"`。
- 兩邊 CM 的 `sequence` 皆為 `"A B G M X I A"`（相同），差異僅在最後一個 A 槽的 key。
- v4 有**專門 migration** 做此改名：`alembic/versions/58a3d1cca6f1_cm_rename_a2_to_a3_return_slot.py`
  - docstring（:1-9）：「The CONTROLLED_MOVE model's return distance slot should be A3 (consistent with General Move convention: A1=obtain, A2=move, A3=return)」
  - upgrade 把 `parameter_slots.slot_key` A2→A3、`display_name_zh`='距離(A)-返回'，並改寫既存 `most_sequence_items.selected_slots_json` / `calculation_snapshot_json` 內的 `"A2"`→`"A3"`（:37-79）。
- 含意：**v4 的資料模型比 v2 字典新**。v4 已把 CM 返回槽正規化為 A3；v2 的 `docs/v3/reference` 字典仍停在 A2 命名。整合時需以此對齊 slot_key，否則 CM 序列的槽對映會錯位（影響 narrative 與 slot→rule 對映，不改變 TMU 數值本身，但改變槽識別）。

### 差異 3：v2 多一個 `source_note` 欄（純溯源註解）

- diff 第 1250 行：v2 在某 P/一般節點多一 `source_note`（「ddm-v3/apps/api/... 逐字複製；IE 裁決補齊」）。
- 含意：純資料溯源註記，無計算含意；顯示 v2 版字典是「v3 現場字典 2026-07-14 同步 + IE 裁決補齊」的後續版本。

### 3.1 AI 字典差異小結

| # | 差異 | v4 | v2 | 影響 TMU？ |
|---|---|---|---|---|
| 1 | M `M_PRESS` 按壓 | 無 | 有（fixed 3 TMU） | **是** |
| 2 | CM 返回槽 key | `A3`（已 migration 改名） | `A2`（舊命名） | 否（僅 slot 識別/對映） |
| 3 | `source_note` 溯源 | 無 | 有 | 否 |

> 兩檔血緣：同一 2026-06-25 原始字典。v4 走了 code/migration 路線演進（A2→A3）；v2 的 `docs/v3/reference` 檔走了「2026-07-14 現場同步 + 補 M_PRESS」路線。**兩邊各有對方沒有的更新**，整合時不能單方覆蓋，需逐項合併並經 v2 引擎黃金測試驗證（GM=28/CM=29 不得破）。
> 注意：v2 現行**權威**規則資料是 DB 的 `rule_sets` 七表（由 `scripts/import_v3_dictionary.py` 匯入 seed），`docs/v3/reference/*.json` 僅為參考檔；整合實際對象是 v2 DB 規則集，本節字典差異需再對 v2 seed 後的實表值複核（本文件範圍限於 JSON 對照，DB 實值複核建議列入整合實作階段）。

---

## 4. v4 有、v2 無的資料物件（整合新增表清單）

以下皆為 v2 `models/v2/` **完全查無對應表**（已 grep 確認 v2 無 `esop`/`line_balance`/`line_layout`/`layout_scenario`/`station` 任何 tablename）。

### 4.1 ESOP Builder（5 表）—— v2 完全沒有

證據：`app/models/esop.py`、migration `b8c9d0e1f2a3_add_esop_tables.py`

| 表 | 檔案:行號 | 說明 |
|---|---|---|
| `esop_documents` | `esop.py:27`（`class EsopDocument`, `__tablename__` :29） | Station-based E-SOP 文件，快照式（source_type=line_balance/layout，凍結 CT/TMU），`source_snapshot_hash` 做 drift 偵測（僅警告） |
| `esop_station_pages` | `esop.py:71`（`class EsopStationPage`, :73） | 一個 Station = 一頁 SOP |
| `esop_steps` | `esop.py:97`（`class EsopStep`, :99） | 一個 WI = 一個 Step；`action_list_status`=ok/partial/missing（不靜默空白） |
| `esop_assets` | `esop.py:141`（`class EsopAsset`, :143） | Step 附圖（`file_path`=storage key，非 URL） |
| `esop_annotations` | `esop.py:168`（`class EsopAnnotation`, :170） | 圖片標註層（原圖永遠保留，1:1 對 asset） |

### 4.2 Line Balance（2 表）—— v2 完全沒有

證據：`app/models/most.py`、migrations `d4e5f6a7b8c9`、`e5f6a7b8c9d0`

| 表 | 檔案:行號 | 說明 |
|---|---|---|
| `line_balance_scenarios` | `most.py:454`（`class LineBalanceScenario`, :461） | 產線平衡模擬情境；自帶 Level Plan 快照 + 站別分派 JSON（`summary_json`/`stations_json`/`source_level_plan_snapshot_json`）、`algorithm_version` |
| `line_balance_layout_scenarios` | `most.py:483`（`class LineBalanceLayoutScenario`, :490） | 視覺化站別佈局（layout_type=free/straight/u_shape/l_shape/two_sided、canvas/zoom/pan、`sync_group_layout_json` 節拍群組、`rhythm_snapshot_json`） |

> v2 README 提到「LB CSV／LB API 接口」屬**匯出**能力，v2 並無把 LB 情境/佈局**持久化**的資料物件。v4 這 2 表是全新的持久化 LB 模擬層。

### 4.3 Level System Plan（3 表）—— v2 用 `level_entries` 但形狀不同

見 §2.4。v4：`level_system_plans`(`most.py:357`) / `level_system_plan_items`(:389) / `level_system_number_rules`(:437)（migration `f1a2b3c4d5e7`）。v2 對等物是掛在 wi_row 的 `level_entries`(`worksheet.py:169`) + `level_validation_runs`(`level_validation.py:41`)，**不是獨立快照 plan**。整合屬「模型哲學決策」，非單純加表。

### 4.4 Analysis Case 審批工作流（3 表）—— v2 無等價審批鏈

證據：`app/models/analysis.py`、`app/models/audit.py`

| 表 | 檔案:行號 | 說明 |
|---|---|---|
| `analysis_cases` | `analysis.py:22`（`class AnalysisCase`） | 分析案；`status`(draft/…)、`case_no` unique、`allowance_percent`、`submitted_at`/`reviewed_at`/`approved_at` 審批時間戳 |
| `analysis_steps` | `analysis.py:50`（`class AnalysisStep`） | 案內步驟；綁 `sequence_model_id`、`step_tmu`、`normal_time_seconds`/`standard_time_seconds`、`video_timestamp_start/end`（影片時間碼） |
| `analysis_step_slots` | `analysis.py:73`（`class AnalysisStepSlot`） | 步驟槽值；`selected_option_id`→`parameter_options`、`index_value`/`tmu_value`、`rule_applied_json` |
| `workflow_audit_logs` | `audit.py:22`（`class WorkflowAuditLog`） | 案狀態流轉稽核（from_status→to_status + comment + actor） |

> v2 對「審批/工作流」的等價物：`process_versions.status`(draft/approved/retired) + `published_by`/`published_at` + `workflow_audit_log`（v2 亦有同名表，見 §5）。但 v2 沒有 v4 這種「分析案 + video timestamp + 三段審批時戳（submit/review/approve）」的獨立工作流實體。v4 的 `video_timestamp_start/end` 是 v2 完全缺的欄位（影片工時研究）。

### 4.5 範本四層鏈（8 表）—— 與 v2 `motion_modules`/`wi_set` 概念重疊但更深

證據：`app/models/most.py`

| v4 層 | 表 | 檔案:行號 | v2 對等物 |
|---|---|---|---|
| L1 動作模組池 | `action_module_templates` | `most.py:151`（`class ActionModuleTemplate`） | v2 `motion_modules` + `motion_module_versions`（`motion_module.py:33/88`，但 v2 是**版本化不可變快照**，v4 是可編輯範本 + `source`(manual/ai/copied)） |
| L2 WI 範本 | `wi_templates` / `wi_template_items` | `most.py:186` / `most.py:211` | v2 無獨立 WI 範本表（WI 表現為 `most_worksheets`+`wi_rows`） |
| L3 製程路線 | `process_routes` / `process_route_items` | `most.py:245` / `most.py:270` | v2 無 |
| — WI Set 專案 | `wi_set_projects` / `wi_set_project_items` | `most.py:300` / `most.py:330` | v2 **有同名概念** `wi_set_projects`/`wi_set_items`（`wi_set.py:34/67`），但欄位/血緣策略不同（見下） |

**`wi_set_projects` 同名不同構**（重要陷阱）：

| 欄位/策略 | v4 `WISetProject`（`most.py`） | v2 `WiSetProject`（`wi_set.py:34`） |
|---|---|---|
| 識別欄 | `project_code`(nullable) + `project_name` + `site`/`bu`/`process`/`family`/`model`（皆 nullable=False） | `project_code`(**unique, NOT NULL**) + `name` + `site`/`bu`/`process`/`family`/`model`（皆 nullable） |
| item 溯源 | `WISetProjectItem`(`most.py:330`) `source_wi_id`(nullable) + `wi_snapshot_json`(full) | `WiSetItem`(`wi_set.py:67`) `wi_template_id`(**soft ref, 不加 FK** 避免 cascade 破包) |
| 合計欄 | `total_wi_count`/`total_action_count`/`total_tmu`/`total_seconds` | `total_tmu_snapshot`/`total_seconds_snapshot`/`action_count_snapshot`（item 級快照） |
| status | draft/active/archived（`most.py`） | draft/active/archived（`wi_set.py` CHECK） — **相同** |

> 兩邊 `wi_set_projects` 名稱撞名、生命週期(status)相同，但**主鍵/溯源/合計欄結構不同**。整合時絕不可假設同名即同表；需明確 rename 或映射，否則 migration 會直接衝突。

---

## 5. 共有但需注意的表（審計/使用者）

| 概念 | v4 | v2 | 註 |
|---|---|---|---|
| 使用者/角色 | `users`(`user.py:41`) + `roles`(`user.py:31`) + `user_roles`(M:N, `user.py:23`) | v2 有 `app_users`（tablename `app_users`）＋ RBAC（另見 auth.py/policy） | v4 是 email/password_hash 本地帳號 + M:N role；v2 是聯邦認證(Traefik ForwardAuth)+本地角色。認證模型不同 |
| 工作流稽核 | `workflow_audit_logs`（綁 analysis_case，`audit.py:22`） | `workflow_audit_log`（tablename，見 §4 grep 結果 `:33`） | 兩邊都有稽核表但綁定對象不同（v4 綁 analysis_case，v2 綁 v2 自身流程） |

---

## 6. 整合建議（資料模型層面，供後續設計採用）

1. **規則/字典**：以 v2 的 12 表 `rule_sets` 為權威落點。寫 v4→v2 映射器把 `parameter_options`（依 `parameter_code` + `control_key` + `input_type`）分流到對應 v2 子表。**M 參數映射最複雜**（v4 一表 → v2 五表 + pricing_kind），需逐選項驗。
2. **AI 字典差異**：合併而非覆蓋。納入 v2 的 `M_PRESS`（3 TMU）與 v4 的 CM `A2→A3` 改名；合併後**必過 v2 黃金測試 GM=28/CM=29**（`scripts/core_logic/run_all.py`）才可採用。
3. **TMU 快照鐵則**：v4 各表的 `calculation_snapshot_json` / TMU 欄**只作移轉驗證**，不進 v2 作權威。v2 一律以 `slot_inputs` + 引擎重算。這是保護單一權威、不污染計算正確性的硬底線。
4. **Level System**：先決策 §2.4 的 (A)新增獨立 plan 層 vs (B)吸收進 `level_entries`。建議 (A)（平移為 v2 之上的分析層），因 v4 plan 的快照/生命週期語意與 v2 `level_entries`（活資料、跟 worksheet 版本）不相容，強行 (B) 會破壞 v2「改 MOST 不丟 level」的 wi_row 穩定 id 設計（`worksheet.py` WiRow docstring）。
5. **全新物件（ESOP 5 表 / LineBalance 2 表 / Analysis 3 表 / 範本 L2-L3 4 表）**：以新增表方式平移，命名加前綴避免與 v2 撞名（特別是 `wi_set_projects`——**必改名**，見 §4.5）。
6. **撞名風險清單**（migration 前必查）：`wi_set_projects`、`workflow_audit_log(s)`、`users`/`app_users`、`motion_modules`(概念)。

---

## 附錄 A · 證據索引（本文件實讀檔案）

**v4（唯讀）**
- `app/models/most.py`（25KB，全讀）— MostSequenceItem/MI/範本鏈/LevelSystemPlan/LineBalance*
- `app/models/dictionary.py`（全讀）— DictionaryVersion/SequenceModel/ParameterSlot/ParameterOption/LexicalOption
- `app/models/esop.py`（全讀）— Esop 5 表
- `app/models/analysis.py`（全讀）— AnalysisCase/Step/StepSlot
- `app/models/audit.py`、`app/models/user.py`、`app/models/__init__.py`（全讀）
- `app/data/minimost_ai_dictionary_v1.json`（正規化後 diff）
- `alembic/versions/`：`58a3d1cca6f1`（CM A2→A3）、`f1a2b3c4d5e7`（level system）、`e5f6a7b8c9d0`（layout scenario）、`d4e5f6a7b8c9`（level lifecycle + line balance）、`b8c9d0e1f2a3`（esop）——全讀或讀頭

**v2（唯讀）**
- `src/ddm_v2/models/v2/rule_set.py`、`rule_set_tables.py`（全讀）
- `src/ddm_v2/models/v2/worksheet.py`（全讀）— ProcessVersion/MostWorksheet/WiRow/MostCycle/LevelEntry
- `src/ddm_v2/models/v2/vocab.py`、`motion_module.py`、`wi_set.py`、`level_validation.py`（全讀）
- `docs/v3/reference/minimost_ai_dictionary_v1.json`（正規化後 diff）
- tablename 全清單（grep 確認 v2 無 esop/line_balance/layout/station 表）

> 註：本文件所有表名、class 名、行號均由實讀檔案內容（`read` 逐行）與 `grep -n` 定位確認。AI 字典差異由對兩份 JSON 正規化（`json.dumps(sort_keys=True, indent=2)`）後 `diff` 得出，並以 leaf-option 計數交叉驗證（M：v2=67 / v4=66）。v2「無 esop/line_balance/layout/station 表」結論由對 `src/ddm_v2/models/` 全量 grep 確認（0 命中）。
