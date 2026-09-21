# 開放問題 E 技術評估：v4 獨立 sequence／mi-statement／process-routes 實體的去留

> **裁決結果（User 2026-09-04）：同意 — 全部對映到 v2 現有實體，零新增資料模型、零 schema 變更。**
> 以下為裁決依據原文。
>
> 目的：為 v4 整合裁決提供依據——v4 的獨立實體（MostSequenceItem / MostMiStatement /
> ActionModuleTemplate / WITemplate / ProcessRoute / WISetProject）要在 v2 建對應資料模型，
> 還是全部對映到 v2 現有 worksheet / wi_row / motion_module / wi_set？
> 方法：實讀 v4 與 v2 相關程式碼，附 `檔案:行號`。唯讀分析，不改任何 v4/v2 程式碼。
> 優先序：**P3**。日期：2026-09-04

## 結論（先講）

**全部對映到 v2 現有實體，一律不新增資料模型。零 schema 變更。**

逐實體裁決：

| v4 實體 | v2 對應 | 建議 | 理由（一句） |
|---|---|---|---|
| `MostSequenceItem`（中段動作列） | `wi_row` + `most_cycle` | **對映，不新增** | 都是「一列 GM/CM 七格填值 + TMU」 |
| `MostMiStatement`（WI 大綱/多列聚合） | `most_worksheet` + 其 `wi_rows` | **對映，不新增** | v2 worksheet 就是「多列 + 表頭 total」的聚合容器 |
| `MostMiStatementItem`（WI 擁有的子動作快照） | `wi_row`（worksheet 內即獨立列） | **對映，不新增** | v2 worksheet 的列天生 WI-owned，本就不共享 |
| `ActionModuleTemplate`（Level 1 動作模組庫） | `motion_module`（category=`action`） | **對映，不新增** | v2 已有動作模組庫，且已版本化（ADR-017） |
| `WITemplate`（Level 2 WI 範本庫） | `motion_module`（category=`wi-template`） | **對映，不新增** | v2 已刻意用同一表 + 判別值承載 WI 範本 |
| `ProcessRoute`（Level 3 流程） | `wi_set_project` + `wi_set_item` | **對映，不新增** | 語義完全等價（快照 + 排序的 WI 集合） |
| `WISetProject`（專案包） | `wi_set_project` + `wi_set_item` | **對映，不新增** | v2 已有同名同義模型 |

**關鍵發現：v2 早已把 v4 的四層鏈（Action Module→WI Template→Process Route→WI Set）
壓縮成 `motion_module`(兩層判別值) → `worksheet/wi_row` → `wi_set` 三支現有實體。
v4 的六個獨立實體沒有一個在 v2 缺對應，且 v2 的 schema 註解就明寫「對應 v3」。**

---

## 逐實體對照（附證據）

### 1. `MostSequenceItem` → v2 `wi_row` + `most_cycle`

v4 `MostSequenceItem`（`models/most.py:28-63`）是「Sequence Model Editing Area 完成的一列」：
- `action_type`（GENERAL_MOVE/CONTROLLED_MOVE）、`sequence_pattern`、`hand_type`（`most.py:33-36`）
- `selected_slots_json`（權威 slot 選擇 payload，`most.py:38`）
- `tmu` / `effective_tmu` / `ct_seconds` / `is_simo` / `frequency`（`most.py:47-59`）
- `system_generated_sentence_zh` / `user_edited_sentence_zh`（`most.py:41-42`）

v2 `wi_row`（`models/v2/worksheet.py:106-160`）+ 1:1 `most_cycle`（`worksheet.py:163-181`）承載完全相同的資訊：
- `wi_row.hand` / `frequency` / `simo_group_id`（`worksheet.py:116/121/122`）
- `most_cycle.seq_kind`（GM/CM，`worksheet.py:172`）、`slot_inputs`（JSONB 權威原始輸入，`worksheet.py:174`）
- `most_cycle.total_tmu` / `total_seconds`（升欄，`worksheet.py:178-179`）
- `most_cycle.narrative_zh` / `narrative_en`（`worksheet.py:176-177`，比 v4 多一個 `_en`，符合 ADR-032）

**差異且 v2 更佳**：v4 把 slot payload、TMU 全存在同一列上（`selected_slots_json` 與各 float 欄並存）；
v2 把「權威原始輸入」(`slot_inputs`) 與「可重生快取」(`computed`/`total_*`) 分層（`worksheet.py` §1.5 註解 line 4）。
這正是「TMU 單一權威」的架構要求——v4 把算好的 float 值冷凍成欄（`most.py:47-59`）、
且在 route 端自算 TMU（`routes/most.py:api_calculate_row`），若照搬會**污染 TMU 單一權威**。
對映到 v2 則由 v2 引擎重算，golden GM=28/CM=29 不受影響。

裁決：**對映，不新增。** v4 這一列 = v2 一個 `wi_row` +其 `most_cycle`。

### 2. `MostMiStatement` → v2 `most_worksheet`（含其 `wi_rows`）

v4 `MostMiStatement`（`models/most.py:65-97`）是「把多列 sequence item 組成一個帶 total 的分析容器」：
- `name`、`total_tmu` / `total_seconds`（`most.py:70/85-86`）
- 透過 link 表 `MostMiStatementSequence`（`most.py:100-112`）連到多個 sequence item，帶 `sequence_order`
- `items`：`MostMiStatementItem`（`most.py:92-95`，見下條）

v2 `most_worksheet`（`worksheet.py:63-104`）本就是「WI 表頭 + 多列」的聚合：
- 表頭 metadata（`model_label`/`analyst`/`allowance_percent`，`worksheet.py:76-88`）
- `rows` relationship，`order_by="WiRow.seq_no"`（`worksheet.py:100`）——即「有序的多列」
- total 可由 `most_cycle.total_tmu` 聚合（`worksheet.py:178`，升欄設計就是為了可聚合）

v4 用「link 表 + sequence_order」表達有序多列；v2 用「`wi_rows` + `seq_no` 唯一約束」（`worksheet.py:158`）
表達同一件事。v2 的 `most_worksheet` = v4 `MostMiStatement`（一個 WI = 有序多列 + 表頭 total）。

裁決：**對映，不新增。** v2 worksheet 與 v4 MI statement 等價；v2 無需新建「statement」層。

### 3. `MostMiStatementItem` → v2 `wi_row`（worksheet 內即為獨立列）

這是 v4 為了修「WI 之間共享列」而補的實體。v4 `MostMiStatementItem`（`models/most.py:106-149`）
的 docstring 直說（`most.py:107-113`）：

> A WI-owned snapshot of a child action inside an MI statement (WI 大綱).
> Decoupled from the source MostSequenceItem: editing a WI child action mutates
> only this snapshot, never the original row...

v4 需要這個實體，是因為它的 `MostSequenceItem` 是**跨 WI 共享的中段清單列**，
所以 WI 內要另存一份可獨立編輯的快照（`routes/most.py:_ensure_statement_items` 做一次性 copy、
`routes/most.py:_recalc_statement_totals` 註解「snapshots are the source of truth」）。

v2 **天生沒有這個問題**：v2 的 `wi_row` FK→`most_worksheet`（`worksheet.py:113`），
一列只屬於一個 worksheet、由 `worksheet_id + seq_no` 唯一（`worksheet.py:158`）。
worksheet 之間不共享列，所以「WI-owned、編輯不影響他人」在 v2 是**結構本質**，不需另立快照實體。
v2 的複製/血緣由 `wi_row.source_row_id`（clone 血緣，`worksheet.py:130`）與
`source_module_id`/`source_module_version`（模組實體化追溯，`worksheet.py:132-137`）表達。

裁決：**對映，不新增。** v4 這個實體是「補 v4 共享列缺陷」的產物，v2 架構天生無此缺陷 → 直接落在 `wi_row`。

### 4. `ActionModuleTemplate`（Level 1）→ v2 `motion_module`（category=`action`）

v4 `ActionModuleTemplate`（`models/most.py:151-183`）= 「Action Module Pool 的可重用動作模組」：
`action_type`/`hand_type`/`slot_selections_json`/`base_tmu`/`source`(manual/ai/copied)/`order_index`。
CRUD 在 `routes/most_workbench_v3.py:288-455`（create/list/update/delete/clone/reorder）。

v2 `MotionModule`（`models/v2/motion_module.py:29-89`）就是動作模組庫，且**已版本化**（ADR-017）：
- `scope`（personal/site/global）、`owner`、`status`（draft/standard/retired）、`current_version`（`motion_module.py:60-72`）
- 不可變版本快照 `MotionModuleVersion`（`motion_module.py:92-140`）：`rows`(JSONB)、引擎算出的 `total_tmu`/`narrative_zh`
- `category` 兩層判別值 `'action'`／`'wi-template'`（`motion_module.py:49` + CHECK `motion_module.py:80`）

v4 的 ActionModuleTemplate 對應 `category='action'` 的 MotionModule。
v2 額外提供了 v4 **沒有**的治理（scope/status 標準草稿、published 後禁 UPDATE 的不可變版本），更完整。

裁決：**對映，不新增。** 落 `motion_module` category=`action`。

### 5. `WITemplate`（Level 2）→ v2 `motion_module`（category=`wi-template`）

v4 `WITemplate`（`models/most.py:186-217`）= 「由動作模組實例組成的可重用 WI 範本」，
子項 `WITemplateItem`（`most.py:220-242`）是 ActionModule 的快照複本（`source_module_id` 為 optional ref）。
建立時從 module 快照複製（`most_workbench_v3.py:create_wi_template`，見 `wi-templates` POST）。

v2 **早已刻意**用同一 `motion_module` 表 + 判別值承載 WI 範本。直接證據在 v2 schema 註解：

- `schemas/v2/motion_module.py:79`：
  > `- 'wi-template'：WI 大綱項（rows = 動作快照複本；對應 v3 MI statements）`
- `schemas/v2/motion_module.py:82`：
  > `工作台濾 'action'、WI 庫濾 'wi-template'`

即 v2 的設計文件本身就把 v4（v3）的 WI-template/MI-statement 明確對映到
`motion_module` category=`wi-template`，其 `rows`(JSONB) 即「動作快照複本」——與 v4 `WITemplateItem` 同義。

裁決：**對映，不新增。** 落 `motion_module` category=`wi-template`；rows 存動作快照。

### 6. `ProcessRoute`（Level 3）→ v2 `wi_set_project` + `wi_set_item`

v4 `ProcessRoute`（`models/most.py:245-276`）= 「由 WI 實例組成的完整流程」，
子項 `ProcessRouteItem`（`most.py:279-297`）快照一個 WI（`source_wi_template_id` soft ref +
`module_instances_json` 全量快照 + `order_index`）。CRUD 在 `most_workbench_v3.py:process-routes`。

v2 `WiSetItem`（`models/v2/wi_set.py:66-107`）語義完全等價：
- `wi_template_id`：soft ref（nullable UUID，**不加 FK** 避免刪版本時 cascade 破壞包，`wi_set.py:7/76-79`）
  → 與 v4 `ProcessRouteItem.source_wi_template_id`(nullable，`most.py:283`) 完全同策略
- `seq_no`（排序，`wi_set.py:74`）+ `project_id+seq_no` 唯一（`wi_set.py:103-105`）→ v4 `order_index`
- 快照欄 `wi_code_snapshot`/`wi_name_snapshot`/`action_count_snapshot`/`total_tmu_snapshot`/`total_seconds_snapshot`
  （`wi_set.py:83-96`）→ v4 `ProcessRouteItem` 的 `wi_name`/`total_tmu`/`module_count` 等快照

且 v2 service 已實作「從 wi-template module 解析回填快照」的路徑：
- `services/v2/wi_set_service.py:64`：`if module.category != "wi-template":` → 明確要求入包的來源是 wi-template module
- `schemas/v2/wi_set.py:48-50`：`有 wi_template_id → 快照由伺服器從 motion module（含 current version）解析回填`

這正是 v4 `most_workbench_v3.py:create_process_route`「從 WITemplate 快照 items」的 v2 版，且更嚴謹
（v2 快照由 server 從 module current version 回填，而非信任 client）。

裁決：**對映，不新增。** v4 ProcessRoute ＝ v2 `wi_set_project`；ProcessRouteItem ＝ `wi_set_item`。

### 7. `WISetProject`（專案包）→ v2 `wi_set_project`（同名同義）

v4 `WISetProject`（`models/most.py:300-338`）與 v2 `WiSetProject`（`wi_set.py:33-63`）幾乎逐欄同名：
- `project_code`/`project_name`(v2:`name`)/`site`/`bu`/`process`/`family`/`model`/`description`/`status`
  （v4 `most.py:308-316` vs v2 `wi_set.py:41-52`）
- `status`：v4 draft/active/archived（`most.py:316`）= v2 draft/active/archived（`wi_set.py:54-58` + CHECK `wi_set.py:60-62`）
- 子項快照：v4 `WISetProjectItem`（`most.py:341-378`）`wi_snapshot_json`/`*_snapshot` = v2 `WiSetItem` 快照欄

**注意 v4 有兩個平行的「WI Set」概念**：`ProcessRoute`（`most_workbench_v3.py` 三層鏈的 Level 3）
與 `WISetProject`（獨立專案包，`most.py:300`，被 `wi_set_builder.py` 消費）。兩者在 v2 都對映到同一支
`wi_set_project`——這也印證 v4 自身有實體重疊，v2 用單一 `wi_set` 收斂更乾淨。

裁決：**對映，不新增。** 直接用 v2 既有 `wi_set_project`/`wi_set_item`。

---

## process_routes 專節（User 特別關注：v2 無此表）

表面上 v2 沒有 `process_routes` 表，像是缺口。實讀後結論：**不是缺口，是 v4 的實體重疊。**

- v4 有**兩條**「WI 集合」實作並存：三層鏈末端的 `ProcessRoute`（`most.py:245`）與獨立的
  `WISetProject`（`most.py:300`）。兩者都是「快照一組 WI + 排序」，欄位高度重複
  （`total_tmu`/`total_seconds`/`wi_count`/`module_count` vs `total_tmu`/`total_seconds`/`total_wi_count`）。
- v2 把這兩者收斂成單一 `wi_set_project`/`wi_set_item`（`wi_set.py`），語義涵蓋兩者。
- v2 甚至已有對應的 builder route（`api/routes/v2/wi_set.py`）與 service（`services/v2/wi_set_service.py`），
  且已實作「來源必須是 wi-template module、快照 server 回填」的規則（`wi_set_service.py:64`）。

因此 process_routes 「v2 無對應表」的正確解讀是：**v2 用 wi_set 一支表達 v4 的兩支重疊實體**，
新增 process_routes 反而會把 v4 的實體重疊複製進 v2。

## mi-statement 專節（User 特別關注：worksheet 是否等價）

**等價，且 v2 更貼合 WI 語義。** 對照三點：

1. **聚合結構**：v4 MI statement = link 表串起有序 sequence items（`most.py:100-112`）；
   v2 worksheet = `wi_rows` + `seq_no` 唯一（`worksheet.py:100/158`）。都是「有序多列 + 表頭 total」。
2. **WI-owned 子動作**：v4 需 `MostMiStatementItem`（`most.py:106`）另存快照，因為它的 sequence item 跨 WI 共享；
   v2 worksheet 的 `wi_row` 本就 1:1 屬於單一 worksheet（`worksheet.py:113/158`），天生 WI-owned，不需這層。
3. **TMU 權威**：v4 MI statement 的 total 由 route 自算（`routes/most.py:_recalc_statement_totals`、
   `most_workbench.py:save_mi_statement` 直接 `sum`/`max`）；v2 由引擎算 `most_cycle.total_tmu` 再聚合。
   對映到 v2 = 交回 v2 單一引擎，**不污染 golden**。

唯一「v2 需要在 UX/service 補」的不是資料模型，而是「一次把多列從中段清單複製進 worksheet」的**動作**——
但這已是 v2 既有能力（`wi_row.source_module_id` 模組實體化、`source_row_id` clone 血緣，`worksheet.py:130-137`）。

---

## 建議與優先序

**裁決建議：全部對映到 v2 現有實體，零新增資料模型、零 schema 變更。**

理由：
1. **無缺口**：逐一實讀後，v4 六個獨立實體在 v2 都有現成對應，且多處 v2 schema 註解
   （`schemas/v2/motion_module.py:79`、`wi_set.py:48`）本就明寫「對應 v3」——對映是 v2 的既定設計，不是將就。
2. **v2 更佳**：v2 的分層（權威 `slot_inputs` vs 快取 `computed`/`total_*`）、模組治理（scope/status/不可變版本）、
   WI 天生不共享列、快照 server 回填——都比 v4「float 冷凍成欄 + route 自算 TMU + 共享列再補快照」更乾淨、
   更符合「TMU 單一權威」與 ADR-032 `_zh`/`_en`。
3. **新增即污染**：照搬 v4 實體會把 v4 的 route-side TMU 自算與實體重疊（ProcessRoute vs WISetProject）
   帶進 v2，違反單一權威與最小加法（ADR-011 精神）。
4. **可逆**：這是唯讀對映決策，不動任何 v2 schema；未來若真出現 v2 無法表達的 v4 語義，再以加法補。

**優先序（P3）落地順序建議**（皆為「在 v2 既有實體上做 UX/匯入對映」，非建模）：
- P3-a：中段動作列 → `wi_row`+`most_cycle` 對映（配合問題 D 的引擎重算路徑）。
- P3-b：WI 大綱（MI statement）→ worksheet 對映（含「多列複製進 worksheet」的既有能力串接）。
- P3-c：Action/WI 範本庫 → `motion_module` 兩 category 對映（庫已存在，主要是匯入/UX）。
- P3-d：ProcessRoute/WISetProject → `wi_set` 對映（收斂 v4 兩支為一支）。

## 一句話

v4 的 sequence／mi-statement／process-routes／template 六個獨立實體，在 v2 全部有現成對應
（`wi_row`+`most_cycle` / `worksheet` / `motion_module` 兩判別值 / `wi_set`），
且 v2 schema 註解本就明寫「對應 v3」——**一律對映、零新增資料模型**；
process_routes「v2 無表」實為 v4 自身實體重疊，用 v2 單一 `wi_set` 收斂更乾淨。
