# 萃取證據：v3 前端使用邏輯（IE 實際操作流，自 Vue 程式碼直接萃取）

> 產出方式：2026-07-05 由查證 agent 直讀 `ddm-v3/apps/web/src/`（router/pages/components/api/stores）萃取。此為 analysis/features 各規格「使用邏輯」段的證據底稿（唯讀）。

## A. 頁面地圖

| Route | Page | 用途 | 前端守衛 |
|---|---|---|---|
| /login | LoginPage | 登入 | public |
| / | DashboardPage | 啟用字典、案件統計、近期案件 | 登入 |
| /users | UsersPage | 使用者管理 | admin |
| /dictionaries、/dictionaries/import | DictionariesPage、DictionaryImportPage | 字典版本/選項/匯入 | admin |
| /cases、/cases/new、/cases/:id、/cases/:id/report | CaseList/CaseEditor/CaseReport | 分析案件＋審核＋報表 | 登入（new 限 analyst/admin；編輯權由 canEdit 計算） |
| /most-workbench | MostWorkbenchPage | 一代主工作台（序列→WI） | 登入 |
| /most-workbench-v3 | MostWorkbenchV3Page | **三層工作台（模組→WI→流程）** | 登入 |
| /wi-set-builder | WISetBuilderPage | WI Set 專案 | 登入 |
| /level-system | LevelSystemPage | **WI Set 唯讀檢視器（名稱誤導：非 Level System）** | 登入 |

守衛：`beforeEach` 未登入→/login；`meta.roles` 不符→回 Dashboard。角色 computed：isAdmin/isAnalyst/isReviewer/isApprover（admin 恆真）。

## B. 關鍵操作流

### B1. 一代工作台（MostWorkbenchPage）— 建一條 Sequence

1. 選 model（GENERAL_MOVE/CONTROLLED_MOVE）＋handType（left/right/both）＋showHandInSentence。
2. 填 contextFields（from/target_object/component/to［＋where（CM）］）。
3. 逐 slot 點開 **SlotModal**：
   - A：ADistanceSelector（reach＋hand_degree＋foot_step，顯示取 max 公式）
   - B/G/I：單選 select（B 自動確認；G/I 需確認）
   - P：base_action select＋modifiers checkbox（**前端強制 ≤2、P_INSERT⊥P_SNAP_FIT**）
   - M：verb＋hand_degree＋foot_step（顯示取 max 公式）
   - X：select＋秒數輸入（seconds_source=user_input_seconds 時必填）
   - 部分 slot 支援 repeat_count（≥1）
4. 任何變更 → debounce 400ms → `POST /most/calculate-row` → 顯示 TMU/秒/句子。
   ⚠️ 另有**前端 computed sentencePreview 自行組句**（與後端組句並存）。
5. 儲存：`POST /most/sequences`（可帶 user_edited_sentence 覆寫句子）→ 加入 savedSequences。

**模型切換遷移規則（前端寫死）**：保留 A1/B1/G/A3＋context；清掉對方獨有 slot；**轉 GM 時 B2 空→自動填 B_EYE_MOVE（badge 預設值）、有 to_location 且 P 空→推 P_PLACE_NO_DIRECTION（badge AI 推斷）、A2 空→badge 待確認**；轉 CM 無自動預填。

### B2. NL 快速預填（NlDraftInput）

輸入文字→`POST /most/nl-draft`→回 suggested model/confidence/context_fields/slot_suggestions（每格 option_code+tmu+confidence+source+badge）/missing_fields/warnings。若編輯區已有內容→詢問「覆蓋 / 只填空白」。badge 四態：推斷/預設值/待確認/明確（el-tag 着色）。套用後照常 calculate-row。

### B3. 序列清單 → MI 語句（WI）

- 清單列操作：拖拉排序、checkbox 多選、SIMO toggle（`is_simo` 切換→該列貢獻歸零並劃線）、頻率直編、編輯/複製/刪除、全文搜尋（前端 filter）。
- 多選＋WI 名稱（未填則以句子串接前 80 字）→`POST /most/mi-statements`（sequence_item_ids 依當前順序）→後端 backfill 子快照 items。
- WI 大綱卡片：展開細項（#/手/句子/SIMO/TMU/頻率）；點子項→WiItemInspector drawer 編輯 slot/context/frequency/is_simo→`PUT items/{id}`→整個 WI 重算回傳→前端 reconcile。子項拖拉→items/reorder。

### B4. 三層工作台（MostWorkbenchV3Page，三分頁）

- **Tab1 動作模組**：Builder（同 B1 的編輯器）→「儲存為動作模組」`POST /most/action-modules`；Pool 卡片（搜尋/複製/刪除/拖拉排序）；多選→「傳送至 WI Pool」→自動切 Tab2 並入 Composer。
- **Tab2 WI Pool**：Module Picker 多選加入 Composer→排序/複製/移除→WI 名稱+敘述→`POST /most/wi-templates`（module_ids）；WI Pool 卡片（clone/刪/inspector 編輯子項）；多選→「傳送至作業流程」→切 Tab3。
- **Tab3 作業流程**：WI Picker 多選→`POST /most/process-routes`（wi_template_ids，**建立即快照**）；流程內 WI 實例排序/複製/刪除/inspector；**apply-to-template**（把流程實例改動回寫來源 WI 範本）。

### B5. WI Set Builder

專案元數據（project_code/name/site/bu/process/family/model/description/status）→WIPoolSearch（debounce 搜 `GET /most/wi-library?q=`，搜的是**一代 MI 語句庫**）→多選「加入」`POST items`（快照複製）→拖拉排序/移除/備註→Summary（總 WI/Action/TMU/秒）。

### B6. 分析案件（CaseEditor）

建案（product/station/operation/allowance%/字典版）→步驟 Dialog（選 sequence model＋逐 slot 選項＋frequency→preview→存）→狀態按鈕依角色/狀態顯示（送審/審核/退回/核准/封存）→簽核時間軸→匯出 xlsx。canEdit：draft|changes_requested 時 analyst 本人或 admin。

### B7. 字典管理（DictionariesPage）

版本清單（標示 active）→啟用/複製(clone)/發佈(publish)/編輯器；編輯器按參數 A~I 分頁→選項清單（依 control_key 分組）→新增（含 suggest-code）/編輯（含同義詞）/軟刪/複製。

## C. 前端隱含規則與問題

1. **值邏輯洩漏到前端**：模型切換自動預填 B_EYE_MOVE、P_PLACE_NO_DIRECTION 是前端寫死的預設值（不在字典資料）。
2. **雙份組句**：前端 sentencePreview 與後端 _compose_full_sentence 並存（漂移風險）。
3. **前端才有的驗證**：P ≤2 修飾與互斥（後端也有）；repeat_count 無上限（僅 >5 提示）；Case 表單必填。
4. **Dead fields**：display_rule（前端未用）、video_range_start/end（未實作影片標記）、SequenceModel.template_text。
5. SIMO：純 per-row toggle，無配對 UI（simo_with_row_id 前端幾乎未用）。
6. 計算一律走後端（無前端 TMU 計算）——正確。

## D. API client 對照（節錄）

authApi(login/me/changePassword)；usersApi(list/create/update/deactivate/setRoles)；dictionaryApi(list/get/seedDefault/import/getSequenceModels/getOptionsByParam/updateOption/createOption/duplicateOption/deleteOption/cloneVersion/publishVersion/suggestCode/getLexicalOptions/activate/archive/exportVersion)；analysisApi(listCases/getCase/createCase/updateCase/steps CRUD/preview/submit/review/requestChanges/approve/archive/getApprovalEvents/exportExcel)；mostApi(getActiveDictionary/getWorkbenchOptions/calculateRow/sequences CRUD/miStatements CRUD＋items/nlDraft/actionModules CRUD＋clone＋reorder/wiTemplates CRUD＋items＋clone/processRoutes CRUD＋clone＋applyToTemplate/wiLibrary/wiSetProjects CRUD＋items)。
