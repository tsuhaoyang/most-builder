# 07 — Level System 前端 UX 對照與差距分析（v4 → v2）

> 唯讀分析文件，供 implementation spec 使用。**不改任何程式碼。**
>
> **整合共識（背景）**：抄 v4 的 Level System UX 手感，但**資料留在 v2 既有的 `level_entries` 活資料模型**（掛 `wi_row`、跟 worksheet 版本走），**不引入 v4 的獨立 Plan 快照層與版本管理**。因此本文件只比對「互動與呈現」層面；每個 v4 UX 特徵都對應「它背後改動什麼資料」，再對應到 v2 的等價欄位。

## 0. 實讀範圍（證據來源）

**v4 前端（Vue，Element Plus）**
- `minimost/apps/web/src/pages/LevelSystemPage.vue`（頁面殼、node/table 雙模式、save/reload/dirty）
- `minimost/apps/web/src/components/level-system/LevelNodeBoard.vue`（**核心拖拉編排 UX**）
- `minimost/apps/web/src/components/level-system/LevelMatrixEditor.vue`（表格微調模式）
- `minimost/apps/web/src/components/level-system/LevelNodeDetailDrawer.vue`（WI 明細抽屜、難度係數）
- `minimost/apps/web/src/components/level-system/LevelStructurePreview.vue`（結構預覽）
- `minimost/apps/web/src/components/level-system/LevelSummary.vue`（統計卡）
- `minimost/apps/web/src/components/level-system/LevelValidationPanel.vue`（驗證面板）
- `minimost/apps/web/src/components/level-system/LevelProjectSelector.vue`（Plan 版本選擇器）

**v4 後端**
- `minimost/apps/api/app/api/routes/level_system.py`（`items/bulk`、`items/reorder`、`items/{id}`、`_apply_item_fields`、`_validate_plan`）

**v2 前端（React，Tailwind + zustand + TanStack Query）**
- `src/frontend/src/features/level-system/LevelSystem.tsx`
- `src/frontend/src/features/level-system/logic.ts`
- `src/frontend/src/features/level-system/store.ts`
- `src/frontend/src/features/level-system/api.ts`

**v2 資料模型**
- `src/ddm_v2/models/v2/worksheet.py`（`LevelEntry` = `level_entries`）
- `src/ddm_v2/most_engine/level.py`（R1–R9 引擎、derive/validate 權威）

---

## 1. v4 Level System 完整 UX 清單（操作方式 + 背後資料異動）

v4 的欄位命名（`LevelSystemPlanItem`）：`main_group / main_instance_id / main_instance_name / sub_group / order_index / cub_group / cub_order / is_cub_locked / number_tag / number_limit / difficulty_factor / adjusted_ct_seconds / station_code / sequence_index / source_order_index`（`level_system.py:56-95`）。

### 1.1 雙模式切換：Node 編排 / 表格編輯
- **操作**：頁面頂部 radio 切 `node` ↔ `table`（`LevelSystemPage.vue:224-227`）。兩模式綁定**同一組 `editItems` reactive 物件**，即時同步（`LevelSystemPage.vue:33-36`）。
- **資料**：純前端狀態；不落地欄位。

### 1.2 拖拉編排（Node board — 核心）
- **操作**：卡片左側 `⠿` 握把才能起拖（`armDrag`/`dragArmedId`，讓 checkbox/標題/按鈕仍可點）（`LevelNodeBoard.vue:227-234`, `316-345`）。
  - 原生 HTML5 DnD；藍色 placeholder bar 顯示落點；hover 卡片上半＝插前、下半＝插後（`onCardOver` `LevelNodeBoard.vue:349-355`）。
  - 「放到群組底部」附加區（`onBottomOver` `:361-365`）。
  - 拖曳時邊緣 auto-scroll（`onBoardDragOver`/`startAutoScroll` `:398-430`）。
- **背後資料**：`placeInGroup` 設定被拖項的 `main_group`（層級號）、`main_instance_id`（群組硬鏈）、`main_instance_name`，重排群組內 `order_index`，再 `reindexAll()` 全盤重編 `sequence_index`（`LevelNodeBoard.vue:196-234`）。存檔時打 `items/reorder`（`sequence_index`）+ `items/bulk`（`main_group/main_instance_id/order_index/...`）（`LevelSystemPage.vue:141-160`）。

### 1.3 層級（main）與群組（main instance）建立
- **操作**：「＋ 新增層級」建立一個 main layer（`addLayer` 自動遞增號碼 `:277-281`）；層級內「＋ 群組」建立 group（`addGroup` `:283-285`）。空群組/空層級可刪（`removeEmptyGroup`/`removeEmptyLayer` `:287-305`）。
- **背後資料**：`main_group` = layer 號（字串），`main_instance_id` = 前端產生的隨機 uuid（`uuid()` `:60-62`），`main_instance_name` = 群組顯示名。**一個 main layer 可含多個 group**（instance）。
- **關鍵語意 — 「同層可互換」**：同一 `main_group` 下有 ≥2 個 instance 時，UI 標「同層可互換」tag（`LevelNodeBoard.vue:487`；`LevelStructurePreview.vue`, `interchangeable` 計算 `:70-72`）。這是 **hidden group identity 硬鏈**：`main_group` 是「哪一層」、`main_instance_id` 是「這一層的哪一個具體群組」，兩者分離。

### 1.4 群組內排序
- **操作**：拖拉，或每個 slot 的 ▲▼ 按鈕（`moveSlot` `:433-448`）。
- **背後資料**：重排 `order_index`（群組內 1-based）+ `reindexAll` 重編 `sequence_index`。

### 1.5 未編排 Pool（右欄）
- **操作**：未指派 WI（`main_instance_id` 為空）落在右欄「未編排 WI」；**保留原始 WI Set 順序**（依 `source_order_index` 排，非 live 順序）（`poolAll` `:118-123`）。可搜尋（`poolSearch` `:125-131`）。拖回 pool＝清空群組欄位（`sendToPool` `:236-246`）。
- **背後資料**：pool 判定 = `!main_instance_id`；移出時把 `main_group/main_instance_id/main_instance_name/order_index/cub_group=null`、`is_cub_locked=false`。

### 1.6 批次「加入選取 WI 到群組」
- **操作**：pool 卡片有 checkbox（`poolSel`），群組頭有「加入選取 WI」按鈕（`addSelectedToGroup` `:433...`, 定義 `:? addSelectedToGroup`）。勾選多筆一次加入，依原始順序附加。
- **背後資料**：同 1.2，批次設定 `main_*` + `order_index`。

### 1.7 cub（不可拆）標記
- **操作**：群組內卡片有 checkbox（`nodeSel`），選 **≥2 筆且必須連續**，按「設為不可拆」（`setCub` `:? canSetCub`/`setCub`）。不連續會被擋（`ElMessage.warning`）。cub 區塊有橘色框、「解除」按鈕（`clearCub`）。
- **背後資料**：`cub_group` = 前端產生 id（`c-<uuid>`），`is_cub_locked = true`。連續的同 `cub_group` 成員在 board 上合併為一個「slot」整塊移動（`slotsOf` `:143-166`；拖 cub 成員會帶整塊 `placeInGroup` `:200-206`）。
- **驗證**：後端檢查同 `cub_group` 必須在 `sequence_index` 上連續，否則 warning（不擋存）（`_validate_plan` cub_continuity `level_system.py:? cub_positions`）。
- **注意**：`cub_order` 欄位存在於 model/schema，但前端 board 未見寫入（由 `order_index` 表達群組內序）。

### 1.8 sub（子群組）
- **後端有欄位** `sub_group`（`level_system.py:78`, `_apply_item_fields` 可寫）。
- **前端狀態**：`LevelMatrixEditor.vue:12-14` 註解明言「V1 exposes only difficulty / main / order / cub；**nb / sub / station / label / status stay hidden**」。Node board 亦無 sub 分組 UI。→ **v4 前端未實作 sub 的互動**，僅後端保留欄位。

### 1.9 nb（number rule）
- **後端有**：plan 層級的 `number-rules`（`number_tag`/`limit_count`），item 層級 `number_tag`/`number_limit`（`level_system.py`）。
- **前端狀態**：同 1.8，nb 在 V1 前端**被隱藏、保留不動**（`LevelMatrixEditor.vue:12-14`）。→ **v4 前端未實作 nb 的互動**。

### 1.10 難度係數 difficulty_factor
- **操作**：表格模式「難易度係數」`el-input-number`（`LevelMatrixEditor.vue:onDifficulty` + 欄位 `難易度係數`），或明細抽屜（`LevelNodeDetailDrawer.vue:onFactor`）。
- **背後資料**：`difficulty_factor`（>0，否則 422 blocking `_blocking_numeric_errors` `level_system.py`）；即時算 `adjusted_ct_seconds = ct_seconds_snapshot * difficulty_factor`（前端預覽 + 後端 `_recompute_adjusted_ct` 權威）。
- **呈現**：board / table / drawer 三處都顯示「調整CT」= `ct × factor`（`adjustedOf` `LevelNodeBoard.vue:? adjustedOf`；`adjustedCt` `LevelMatrixEditor.vue`）。

### 1.11 即時 CT / TMU / 統計呈現
- **操作**：`LevelSummary.vue` 頂部 5 張卡：項目數、main 群組數、Total 調整CT、Total 原始CT、Total TMU（`LevelSummary.vue:8-40`）。隨 `editItems` 即時重算。
- **背後資料**：讀 `adjusted_ct_seconds` / `ct_seconds_snapshot` / `tmu_snapshot`（都是 **snapshot 欄位**，來自 WI Set 快照）。

### 1.12 結構預覽
- **操作**：`LevelStructurePreview.vue` 依 `main_instance_id` 分群，顯示 main 號、群組名、「同層可互換」、cub 區塊、每列 order（`:44-95`）。唯讀鏡像。

### 1.13 驗證面板（即時，但需按鈕觸發）
- **操作**：`LevelValidationPanel.vue` 顯示 blocking（擋存）/ warning（不擋）分類。載 plan/存檔後呼叫 `validateLevelPlan`（`LevelSystemPage.vue:refreshValidation`）。
- **規則**：`invalid_numeric`（difficulty≤0、order≤0，blocking）、`unassigned`（未編排，warning）、`cub_continuity`（warning）（`level_system.py:_validate_plan`）。

### 1.14 station 指派
- **後端有欄位** `station_code`（`level_system.py:79`）。
- **前端狀態**：同 1.8，station 在 V1 前端**被隱藏**（`LevelMatrixEditor.vue:12-14`）。→ **v4 Level System 前端未實作 station 指派 UI**（station 屬於 Line Balance / Layout 頁面，見 §4）。

### 1.15 Plan 版本管理（Project Selector）
- **操作**：`LevelProjectSelector.vue` — 選 WI Set 專案 → 建立/開啟/複製/重新命名/發布(release)/封存(archive)/刪除 Level Plan；列出各版本（V001…）、狀態（draft/released/archived）、更新時間、scenario 數（`LevelProjectSelector.vue` 全檔）。
- **背後資料**：`LevelSystemPlan`（獨立快照表：`version`/`status`/`source_plan_id`/`released_at`/`archived_at`）。
- **§4 標記**：這整層是 v4 的**獨立 Plan 快照 + 版本管理**，明確**不整合**。

### 1.16 展開/收合、自動整理
- **操作**：全部展開/收合層級與群組（`expandAll`/`collapseAll` `:266-275`）、「自動整理順序」（`autoTidy` → `reindexAll` `:? autoTidy`）、表格「依群組自動產生 order」（`autoFillOrder` `LevelMatrixEditor.vue`）。
- **背後資料**：`autoTidy`/`normalize` 重編 `order_index` + `sequence_index`。

### 1.17 存檔 / 還原 / dirty 追蹤
- **操作**：工具列「未儲存變更」tag、「還原」（reload）、「儲存」（`LevelSystemPage.vue:229-241`）。存檔＝`reorder` + `bulk`（`handleSave` `:135-166`）。blocking 錯誤回 422 擋存。
- **背後資料**：批次寫全部可編輯欄位。

---

## 2. v2 現有 Level System UX 清單（逐項對照）

v2 資料落點：`level_entries`（`worksheet.py:172-195`），前端狀態 = `LevelCell`（`logic.ts:3-7`）：
`coefficient / number / number_count / level / countersignature / machine_count / manpower`
＋ 群組 `GroupMeta { type: 'sub'|'cub'; parent; seq }`（前端態）。
`derive()` 推導 `ascription / level / countersignature / parent_countersignature / order`（`logic.ts:36-70`）送後端 R1–R9 驗證（`api.ts`）。

**重要架構差異**：v2 **沒有獨立 Plan**。Level 直接掛在當前 worksheet 的 `wi_rows`（`LevelSystem.tsx` 讀 `useWiStore(s => s.rows)`），跟 worksheet 版本走。WI 列由 WI 工時表決定，Level System 不自建列。

| # | v4 UX 特徵 | v2 狀態 | 說明 |
|---|-----------|---------|------|
| 1.1 | Node/Table 雙模式 | **v2 沒有** | v2 只有單一 Container 巢狀拖拉視圖，無表格微調模式 |
| 1.2 | 握把拖拉 + placeholder + auto-scroll | **兩邊做法不同** | v2 有拖拉（`Card draggable` + `Container onDrop` → `moveTo` `LevelSystem.tsx:117-137`, `152-163`）；但**整卡可拖、無 `⠿` 握把 arming、無插入點 placeholder bar、無 hover 上下半判定、無邊緣 auto-scroll、無群組內精準排序落點** |
| 1.3 | main layer + main_instance 群組（hidden identity 硬鏈） | **兩邊做法不同（重點）** | v2 用 `countersignature`（sub*/cub* 標籤）+ `GroupMeta` 表達分組；**沒有 main_group/main_instance_id 的「層 vs 具體群組」二層拆分**，也沒有「同層可互換」語意。詳見 §3.1 |
| 1.4 | 群組內 ▲▼ 排序 | **v2 沒有** | v2 靠拖拉改歸屬，`order` 由 `derive()` 依列在 sheet 的自然順序推導（`logic.ts:44-49`），**無群組內顯式重排 UI**；WI 列順序由 WI 工時表掌控 |
| 1.5 | 未編排 Pool（保留原序 + 搜尋） | **v2 沒有** | v2 無「pool」概念；所有列都在 sheet 上，root container = 未分組列（`Container label=""`）。無搜尋、無「原始順序保留」設計 |
| 1.6 | 批次「加入選取 WI」 | **v2 沒有** | v2 無多選加入群組；拖拉一次一列 |
| 1.7 | cub（不可拆） | **兩邊做法不同** | 兩邊都有 cub。v2 用 `createGroup('cub', parent)` + `Box` 巢狀盒（`store.ts:createGroup`；`LevelSystem.tsx:Box`），cub 可**巢狀在 sub 內**（`parent_countersignature`）。v4 cub = 群組內連續成員合併 slot（`cub_group`+`is_cub_locked`），**不支援 sub⊃cub 巢狀**（因 sub 前端未做）。v2 更完整 |
| 1.8 | sub（子群組） | **v2 有、v4 前端沒有** | v2 有完整 sub UI（`createGroup('sub')`、`Box` sub 盒、`createCubChild`、`dissolveGroup`）（`LevelSystem.tsx:Box`）。v4 sub 僅後端欄位 |
| 1.9 | nb（number rule） | **v2 有、v4 前端沒有** | v2 有 `NbArea`：`nbMode`/`nbPick`/`confirmNb(count)`/`removeNb`，產生 `nb1/nb2…` + `number_count`（`LevelSystem.tsx:NbArea`；`store.ts:confirmNb`）。v4 nb 僅後端欄位 |
| 1.10 | difficulty_factor 難度係數 | **兩邊做法不同（重點）** | v2 有 `coefficient`（`LevelCell.coefficient`；`level_entries.coefficient` `worksheet.py:184`），語意等價（乘 raw_seconds → second）。但 **v2 前端目前沒有調 coefficient 的 UI 輸入**（`Card` 只暴露 main order 輸入 `LevelSystem.tsx:? patchCell(level)`；`blankCell` 固定 `coefficient:1`）。詳見 §3.2 |
| 1.11 | 即時 CT/TMU/統計卡 | **v2 沒有** | v2 前端無 Summary 統計卡；卡片只顯示單列 `row.seconds + 's'`（`LevelSystem.tsx:Card`）。無 Total 調整CT/原始CT/TMU 匯總 |
| 1.12 | 結構預覽 | **v2 沒有** | v2 無獨立結構預覽鏡像；編排視圖本身即結構 |
| 1.13 | 驗證面板（blocking/warning 分類） | **兩邊做法不同** | v2 有即時 R1–R9 驗證（`useValidateLevel`，改動即打 `/api/v2/level/validate` `LevelSystem.tsx:useEffect`），但**呈現為單一 `<pre>` 文字清單 + 行內紅框**，無 blocking/warning 分級卡片 UI。v2 引擎規則其實**更嚴格**（R1–R9） |
| 1.14 | station 指派 | **兩邊都沒有（前端）** | 見 §4，屬 LB/Layout |
| 1.15 | Plan 版本管理 | **v2 沒有（且不整合）** | 見 §4 |
| 1.16 | 展開/收合、自動整理 | **v2 沒有** | v2 無 collapse/expand、無 autoTidy |
| 1.17 | dirty 追蹤 + 手動存檔/還原 | **兩邊做法不同** | v4 顯式 dirty + 手動 save（`items/bulk`）。v2 Level 態存 zustand，隨 worksheet 存檔一起落地（`level_entries`），無獨立 Level 存檔按鈕 |

---

## 3. 差距清單（v4 有、v2 沒有 → 要補什麼）

> 每項：v4 怎麼做 / 背後資料 / v2 要補什麼 / 對應 v2 `level_entries` 欄位或需新增欄位。

### 3.1 【重點】main_group / main_instance「二層 hidden identity 硬鏈」＋「同層可互換」

- **v4 怎麼做**：`main_group`＝「第幾層」（可互換的邏輯層），`main_instance_id`＝「這一層裡的哪一個具體群組」（前端 uuid 硬鏈）。同一 `main_group` 有多個 `main_instance_id` → UI 標「同層可互換」（`LevelNodeBoard.vue:487`, `LevelStructurePreview.vue:70-72`）。拖拉時項目綁到 `main_instance_id`（`placeInGroup` `:196-234`）。
- **背後資料**：`main_group`(str) + `main_instance_id`(uuid) + `main_instance_name`(str)，三欄分離。
- **v2 現況**：v2 只有 `countersignature`（群組標籤 sub*/cub*）+ `GroupMeta.parent`（巢狀）+ `ascription='main'` / `level`（主序層號）。v2 的 `countersignature`/`parent_countersignature` **不等價於 main_instance 硬鏈**：
  - v2 `countersignature` = 「本列屬於哪個 sub/cub 群組」（群組成員關係），偏向 v4 的 group 概念；
  - v2 `level`（配 `ascription='main'`）= 主序的層號，偏向 v4 的 `main_group` 概念；
  - **但 v2 沒有「同一主序層可以有多個可互換的具體群組實例」這個 identity 拆分**。v2 一個群組 = 一個 `countersignature` 標籤，沒有「層 vs 實例」兩級。
- **v2 要補**：
  - 若要抄 v4「同層可互換」手感，需在 `level_entries` **新增欄位** `main_instance_id`（穩定群組身分）與 `main_instance_name`（顯示名），並讓 `level`（或新增 `main_group`）承擔「層號」。
  - **替代（貼合 v2 既有模型）**：用「同一 `level` 值 + 不同 `countersignature`」表達可互換群組，避免加欄位；但需前端補「同層可互換」的推導與呈現，且需確認 R1–R9 引擎不會把「同 level 多群」判為 R8 重複。
  - 對應欄位：`level_entries.countersignature` / `level` / `parent_countersignature`（既有）；**若走硬鏈路線需新增** `main_instance_id`、`main_instance_name`。

### 3.2 【重點】難度係數輸入 UI（difficulty_factor ↔ coefficient）

- **v4 怎麼做**：表格欄 + 明細抽屜 `el-input-number` 調 `difficulty_factor`（min 0），即時算 `adjusted_ct = ct × factor`（`LevelMatrixEditor.vue:onDifficulty`, `LevelNodeDetailDrawer.vue:onFactor`）。
- **背後資料**：`difficulty_factor`（>0，blocking 驗證）+ 衍生 `adjusted_ct_seconds`。
- **v2 現況**：**資料層已等價** — `level_entries.coefficient`（`>0` check `worksheet.py:191`）+ computed `second = raw_seconds × coefficient`（`worksheet.py:180`）。引擎 `level.py:37` `raw_seconds * coefficient`、`level.py:85-86` 驗 `coefficient>0`（`COEF_INVALID`）。前端 `LevelCell.coefficient` 也存在。**唯一缺的是前端輸入 UI**：`blankCell` 固定 `coefficient:1`，`Card` 未提供調整 coefficient 的欄位（只提供 main `level` 輸入）。
- **v2 要補**：在 `Card`（或新增明細抽屜）加一個 coefficient `input`，`patchCell(id, { coefficient })`；並顯示 `調整秒 = seconds`（v2 `row.seconds` 已是原始秒，需釐清 `row.seconds` 是否已含 coefficient，或另顯示 `raw × coefficient`）。
- **對應欄位**：`level_entries.coefficient`（既有，**不需新增**）。**結論：difficulty_factor ≈ v2 coefficient，資料等價，只缺 UX。**

### 3.3 拖拉手感升級（握把 / placeholder / 上下半插入 / auto-scroll / 群組內排序）

- **v4 怎麼做**：`⠿` 握把 arming 防誤拖、藍色 placeholder bar、hover 上下半判定插前/插後、邊緣 auto-scroll、群組內 ▲▼ 與精準落點（`LevelNodeBoard.vue:316-448`）。
- **背後資料**：`sequence_index`（全盤序）+ `order_index`（群組內序）。
- **v2 現況**：有基本拖拉（整卡可拖、drop 到 container 改 `countersignature`），但**無握把、無 placeholder、無上下半、無 auto-scroll、無群組內顯式排序**。v2 的 `order` 由 `derive()` 依列在 sheet 的自然位置推導（`logic.ts:44-49`），列順序由 WI 工時表掌控。
- **v2 要補**：純前端 UX 強化（握把/placeholder/上下半/auto-scroll）。**群組內排序若要做**，需釐清：v2 `order` 目前是推導值，若要支援「群組內顯式重排且不動 WI sheet 全局順序」，需把 `order_in_group`（`level_entries.order_in_group` 已存在！`worksheet.py:186`）改為可寫並前端可調。
- **對應欄位**：`level_entries.order_in_group`（**既有**，目前 v2 前端未直接編輯，靠 derive）；`sequence_index` 概念對應 WI row 的 `seq_no`（由 WI sheet 管）。

### 3.4 未編排 Pool + 搜尋 + 批次加入

- **v4 怎麼做**：右欄 pool（未指派項，保留原始順序 + 搜尋），checkbox 多選「加入選取 WI」（`LevelNodeBoard.vue:118-131`, `addSelectedToGroup`）。
- **背後資料**：pool 判定 = `!main_instance_id`；加入＝批次寫 `main_*`。
- **v2 現況**：無 pool 概念（所有列都在 sheet；root container = 未分組列）。
- **v2 要補**：可把「未帶 `countersignature` 的列」視為 pool 呈現（v2 已有此語意：root Container `label=""`），補搜尋 + 多選批次 `moveTo`。**不需新增欄位**（用既有 `countersignature` 空值即 pool）。
- **對應欄位**：`level_entries.countersignature`（空 = 未編排）。

### 3.5 即時統計卡（Summary）與結構預覽

- **v4 怎麼做**：`LevelSummary.vue`（項目數 / main 群組數 / Total 調整CT / 原始CT / TMU）、`LevelStructurePreview.vue` 結構鏡像。
- **背後資料**：唯讀彙總 `adjusted_ct_seconds` / `ct_seconds_snapshot` / `tmu_snapshot`。
- **v2 現況**：無 Summary、無結構預覽。v2 有各列 `row.seconds` 與後端 TMU 引擎，但前端未彙總呈現。
- **v2 要補**：純前端彙總元件，讀 `useWiStore` rows 的 `seconds` + coefficient 算 Total。**不需新增欄位**。v2 沒有 `ct_seconds_snapshot`/`tmu_snapshot`「快照」欄位（因無 Plan 快照層），要改讀活資料（rows 的 seconds / TMU）。
- **對應欄位**：讀 `wi_rows`/`most_cycles` 的活算值 + `level_entries.coefficient`；**無快照欄位**（刻意，符合共識）。

### 3.6 驗證面板分級 UI（blocking / warning）

- **v4 怎麼做**：`LevelValidationPanel.vue` 分 blocking（擋存，紅）/ warning（不擋，黃）卡片。
- **背後資料**：`_validate_plan` 三規則。
- **v2 現況**：v2 R1–R9 驗證**更嚴格且已即時**（`useValidateLevel`），但呈現為 `<pre>` 文字 + 行內紅框，無分級卡片。
- **v2 要補**：純前端呈現升級 — 把 `LevelIssue[]`（`api.ts`）依 code 分級渲染成卡片。**不需新增欄位/後端改動**（v2 引擎已回 issues）。
- **對應**：`/api/v2/level/validate` 既有回傳。

### 3.7 雙模式（Table 微調）、展開/收合、自動整理、dirty/存檔

- **v4 怎麼做**：Table 模式微調 + collapse/expand + autoTidy + 顯式 dirty/save。
- **v2 現況**：皆無（v2 隨 worksheet 存檔落地）。
- **v2 要補**：可選的前端便利功能；**Table 模式若做**，綁同一 zustand 態即可，不需新增欄位。dirty/save 在 v2 屬 worksheet 存檔範疇，需決定 Level 是否要獨立存檔按鈕（建議沿用 worksheet 存檔以維持「跟 worksheet 版本走」共識）。

---

## 4. 依賴「不整合的東西」的 v4 UX 特徵（**不列入要補的差距**）

這些 v4 UX 依賴 v2 明確不採用的獨立 Plan 快照層 / LB / Layout，**故不納入 Level System UX 補齊清單**：

| v4 UX 特徵 | 依賴 | 證據 | 為何排除 |
|-----------|------|------|---------|
| Plan 版本管理（建立/複製/發布/封存/刪除、V001…、draft/released/archived） | 獨立 Plan 快照層 + 版本管理 | `LevelProjectSelector.vue` 全檔；`level_system.py` release/archive/duplicate/version | 共識：不引入獨立 Plan；v2 資料跟 worksheet 版本走 |
| WI Set Project Selector（從 WI Set 專案建 Plan、快照 WI 項） | WI Set Project 快照 | `LevelSystemPage.vue:handleCreatePlan`；`create_plan_from_wi_set` `level_system.py` | v2 直接掛活 `wi_rows`，無快照建立步驟 |
| snapshot 欄位（`ct_seconds_snapshot`/`tmu_snapshot`/`wi_snapshot_json`/`source_order_index`） | Plan 快照 | `level_system.py:82-90`, serialize | v2 無快照層，改讀活資料 |
| 「情境數 scenario_count」欄與刪除保護 | Line Balance Scenario | `LevelProjectSelector.vue:? scenario`；`_scenario_count` `level_system.py` | LB 不在本次整合範圍 |
| station 指派（`station_code`） | Line Balance / Layout（站位規劃） | `level_system.py:79`；前端隱藏 `LevelMatrixEditor.vue:12-14` | v4 前端本身未做；station 屬 LB/Layout 頁面，非 Level System UX |
| plan 層 nb `number-rules`（每站限量） | LB 站位限制 | `level_system.py:set_number_rules` | v2 item 層 nb（`number`/`number_count`）已由 `NbArea` 覆蓋；plan 層每站規則屬 LB |

---

## 5. 一頁總結（給 spec 的行動清單）

**資料層已等價、只缺 v2 前端 UX（優先）**
- **difficulty_factor → `coefficient`**：資料 100% 等價（`level_entries.coefficient` + computed `second`），**只需補前端輸入 UI**（§3.2）。
- **order 群組內排序 → `order_in_group`**：欄位已存在（`worksheet.py:186`），目前靠 derive，若要顯式排序需前端可編 + 後端可寫（§3.3）。
- **pool → `countersignature` 空值**：語意已在，補搜尋/多選（§3.4）。
- **驗證分級 UI**：後端 issues 已回，純前端呈現升級（§3.6）。
- **Summary / 結構預覽**：純前端彙總活資料（§3.5）。

**需要設計決策 / 可能新增欄位**
- **main_instance 硬鏈 + 「同層可互換」**（§3.1）：v2 `countersignature`/`parent_countersignature` **不等價**於 v4 的「層 vs 具體群組」二級 identity。要嘛（a）新增 `main_instance_id`/`main_instance_name` 到 `level_entries`，要嘛（b）用「同 `level` + 不同 `countersignature`」土法表達可互換並補推導/呈現（需驗 R8 不誤判）。**這是最大的資料/語意缺口，需 spec 拍板。**

**純前端手感強化（無資料改動）**
- 拖拉握把 `⠿` / placeholder bar / 上下半插入 / 邊緣 auto-scroll / collapse-expand / autoTidy / Table 雙模式（§3.3, §3.7）。

**明確排除（不整合）**：Plan 版本管理、WI Set 快照建立、snapshot 欄位、scenario、station_code、plan 層 nb 每站規則（§4）。

**v2 反而比 v4 前端「更完整」之處（保留、勿退化）**：sub 子群組 UI（v4 前端無）、nb item 層互動（v4 前端無）、sub⊃cub 巢狀（v4 無）、R1–R9 完整驗證（v4 只有 3 條規則）。
