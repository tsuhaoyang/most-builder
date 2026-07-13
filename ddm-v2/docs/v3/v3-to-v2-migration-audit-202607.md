# v3 → v2 移植審查報告（2026-07-12）

> **審查性質**：v3（`ddm-v3/`，唯讀）的核心邏輯與 UX 為使用者驗證過的權威版本；v2 為移植目標。本報告列出 v2 相對 v3 的所有未完成項、行為偏差與程式漏洞，並附解決方案與實作細節。
>
> **審查方法**：
> 1. Playwright 實機走查 — v3（:5173，10 頁全數成功截圖）與 v2（:8877，Docker 部署版）
> 2. 前端元件邏輯對等性審查（agent 完整回報，34 項發現）→ §1~§4
> 3. 核心邏輯對比（v3 引擎 vs v2 most_engine）→ **§7（已完成）**
> 4. 後端 API 對等性審查 — **進行中**，完成後補 §9（文末）

---

## 0. P0 阻斷性缺陷（Playwright 實測發現，最優先）

### 0.1 【CRITICAL】點擊「WI 組裝」→ 整站白屏崩潰（Docker :8877 實測可重現）

- **現象**：走查腳本點擊 sidebar「WI 組裝」後頁面變全白，`document.body.innerText === ""`，之後所有導覽按鈕永久消失。
- **Console 錯誤**：`TypeError: Cannot read properties of undefined (reading '0')`
- **根因 A（直接炸點）**：`features/workbench-v3/ActionModuleWorkspace.tsx` 多處寫 `mod.rows[0]?.cycle`（:408、:414、:606）。Optional chaining `?.` 放在 `[0]` **之後**，當 `mod.rows` 本身是 `undefined` 時 `mod.rows[0]` 直接 throw。
- **根因 B（合約不符，經 code-review 更正）**：後端 `MotionModuleResponse` **從不回傳 top-level `rows`/`total_tmu`** — 兩者巢狀於 `current_version_detail`（list 端點該欄為 `null`，detail 端點才有值；`schemas/v2/motion_module.py:87-117`、`motion_module_service.py:95-126`）。前端型別 `MotionModuleSummary.rows`/`total_tmu` 是**幽靈欄位**，在 list 與 detail 兩種回應下都恆為 `undefined` — 所有讀取點顯示的 TMU=0、手別=—、動作數=0 全是錯誤資料。正解＝改讀 `current_version_detail.rows`/`.total_tmu`，不是把型別改 optional 了事。
- **根因 C（放大器）**：v2 全站**沒有任何 React Error Boundary**，單一元件 render 期例外 → React 整樹 unmount → 白屏且無法自救。
- **解決方案**：
  1. `App.tsx` 加一個 `ErrorBoundary` 元件包住 `renderContent()`，fallback 顯示錯誤訊息＋「回儀表板」按鈕（約 30 行）。
  2. 前端統一改為 `mod.rows?.[0]?.cycle`（`?.` 放在 `rows` 之後）；同檔 :359 `loadModule` 亦同。`WIPoolWorkspace.tsx` :270-272、:368 同樣寫法需一併修。
  3. 決定合約真相：若 list 端點本來就不給 rows（效能考量合理），前端型別應拆成 `MotionModuleListItem`（無 rows）與 `MotionModuleDetail`（有 rows），需要 rows 時打 detail 端點；若要 list 附摘要 rows，則後端補欄位。**建議前者**，並跑 `npm run gen:api` 讓型別以 OpenAPI 為準，不准手寫。
- **派工**：ddm-frontend（修 1、2）＋ ddm-backend（確認 3 合約）＋ ddm-testing（補 e2e：點遍所有 sidebar tab 不得白屏 — 本次走查腳本可直接改成 regression test）。

### 0.2 【HIGH】v2 Docker 資料庫被測試資料汙染

- **現象**：`GET /api/v2/motion-modules` 回 113 筆，幾乎全是 `UT-Pub-788df8` 之類的單元測試殘留（`status: draft`、`current_version: 0`、`current_version_detail: null`）。
- **影響**：任何依賴模組庫的頁面（WI 組裝三個 tab、WI 專案建立的搜尋）在真實部署上顯示垃圾資料；`current_version: 0` 且無版本明細的模組也是 0.1 崩潰的直接資料來源。
- **解決方案**：integration test 不得打正式 DB（應使用獨立 test database / transaction rollback fixture）；提供 `scripts/cleanup_test_data.py` 清除 `UT-` 開頭殘留；docker entrypoint 的 seed 與測試資料分離。
- **派工**：ddm-testing（test fixture 隔離）＋ ddm-backend（清理腳本）。
- **補充發現（2026-07-13，經 ddm-testing 深查更正診斷）**：`tests/integration/test_motion_modules.py` 的 8+1 個既有失敗，根因**不是種子過期**——`p_lay` 從未存在於任何值權威（v3 字典 JSON、converter `P_BASE_MAP`、V1/V2 seed 全歷史均無；dev DB 的 `rule_p_bases` 與現行 seed 完全一致）。真正原因：測試（d31af5d 引入）引用了只存在於「某個曾被手動加過 p_lay 的環境 DB」的代碼。**裁決（方案 1）**：測試改用認證代碼 `p_place_none`，不動值權威。附帶發現：`dev_seed_v2.py` 對 rule-set 是 skip-if-exists，永不更新既有 DB 值——未來字典改值需顯式 upsert/migration 路徑。

---

## 1. MOST 工作台（v3 `MostWorkbenchPage.vue` → v2 `wi-workbench/WiWorkbench.tsx`）

> v3 此頁是**主要生產工具**：AI 快速建模 → 逐格建動作 → 動作清單管理 → 勾選組成 WI。v2 已有骨架（slot 色塊、DnD、WI 大綱、NL 輸入列），但關鍵工作流缺失如下。

### 1.1 【HIGH／錯誤】Slot 與情境欄位未交錯排列
- v3：`SequenceSlotBuilder.vue:46-85` 單一流式排列 — GM：`使用手|從哪裡|A1|B1|G|目標物|元件|A2|B2|P|到哪裡|A3`；CM：`…|M|到哪裡|X|I|哪裡|A3`。情境欄（米黃卡片）內嵌在 slot 之間，這是使用者驗證過的「照句子順序填」心智模型。
- v2：`WiWorkbench.tsx:566-571` 三個詞彙下拉獨立一列，slot 色塊另一列；且缺「元件」「哪裡（CM）」兩個情境欄；使用手不在流內。
- **修法**：建 `builderItems: Array<{type:'context'|'slot', …}>` 依 v3 順序渲染於單一 `flex flex-wrap` 列；`cycle.ts` 的 `CycleState.nv` 增加 `component`、`where` 兩鍵並接入 `shortNarr`。

### 1.2 【MEDIUM／缺】「顯示於MI」checkbox
- v3：`SequenceSlotBuilder.vue:109-114` 使用手下方 checkbox，控制 MI 語句是否含手勢前綴，並隨存檔保存（`MostWorkbenchPage.vue:325`）。
- v2：無此狀態；`shortNarr`（`cycle.ts:75-80`）永遠加手勢前綴。
- **修法**：`CycleState` 加 `showHandInMi: boolean`；checkbox 放在手勢選單旁；`shortNarr` 依旗標決定前綴。

### 1.3 【MEDIUM／缺】Slot AI 徽章（AI 推斷／預設值／待確認）
- v3：`SequenceSlotBuilder.vue:138-147` 每個 slot 下方徽章，依類型著色（綠/琥珀/紅）；由 NL 解析結果填入（`MostWorkbenchPage.vue:431-444`），slot 清除時同步清除。
- v2：無。
- **修法**：`useState<Record<SlotKey,string>>` 存徽章；`nlDraftPatch` 回傳「填了哪些 slot、哪些沒有 chosen（→待確認）」；slot 按鈕內加絕對定位徽章；使用者開該 slot 的 modal 時刪除徽章。

### 1.4 【MEDIUM／部分】Slot modal 缺「清除」與「動作次數」
- v3：`SlotModal.vue:44-57` G/P/M/X/I 有次數欄；`:66-74` 清除鈕；`SlotBlock.vue:154-159` hover 顯示 × 清除；B slot 選了即自動確認。
- v2：modal（`WiWorkbench.tsx:816-853`）只有確認/關閉；slot 無法清空回未填。
- **修法**：已填 slot 色塊 hover 顯示 ×，點擊重置該 slot 至預設值。**次數欄需後端 `CycleIn` 先支援**，先向 ddm-backend 確認，勿在前端假乘。

### 1.5 【HIGH／部分】即時摘要列與漸進式 MI 語句預覽
- v3：`SequenceSummaryBar.vue:18-60` 顯示動作類型/使用手/基礎TMU/頻率/有效TMU/CT/SIMO/納入/MI語句，語句隨填隨組。
- v2：`WiWorkbench.tsx:592-604` 只有 tech line＋「本列 X TMU ≈ Y 秒」，頻率/SIMO 改了預覽不動。
- **修法**：抽 `SummaryBar` 元件；`effTmu = tmu * cur.freq`；MI 語句欄即時渲染 `shortNarr(cur, label, vname)`。

### 1.6 【MEDIUM／缺】WI 語句人工覆寫欄
- v3：`MostWorkbenchPage.vue:964-974` `editedSentence` 輸入框（placeholder 為系統句），存為 `user_edited_sentence_zh`。
- v2：`narr` 永遠取 `shortNarr(...)`（:466-472）。
- **修法**：加 `editedNarr` state；`add()` 時 `editedNarr.trim() || shortNarr(...)`。

### 1.7 【CRITICAL／缺】列編輯迴路（更新動作／取消編輯）
- v3：`MostWorkbenchPage.vue:557-600` 點列 ✏️ 把 model/手/slots/情境全部載回建立器；更新走完整重算、保留頻率/SIMO/列位置（:308-343）；編輯中列琥珀高亮（`MiCompositionTable.vue:121-128`）。
- v2：列只有「刪」（:711-719）。**存了的動作無法修正，只能刪掉重建** — 這是生產工具的核心工作流缺失。且 v2 其實已有反向轉換 `payloadToState`（`cycle.ts:57-72`）**閒置未用**。
- **修法**（約 60 行）：加 `editingRowId` state；✏️ 按鈕 → `setCur(payloadToState(r.payload))` 並帶回 hand/freq/simo/nv → 按鈕文案切「更新動作」＋「取消編輯」→ 更新時以現 TMU 重算結果覆寫該列；`r.id === editingRowId` 時列加 `bg-amber-50`。

### 1.8 【HIGH／缺】列複製再製（📋 rework）
- v3：`MostWorkbenchPage.vue:563-567` 載入列狀態但不設 editingRowId → 存為新動作。
- v2：無。
- **修法**：同 1.7 的載入器，但不設 `editingRowId`；操作欄加 📋。

### 1.9 【MEDIUM／缺】刪除確認
- v3：列刪除與 WI 刪除皆有 `ElMessageBox.confirm`。
- v2：`delRow(r.id)` 直接執行（:713）；WI 群組刪除亦無確認（:429-432）。
- **修法**：`window.confirm('確定刪除？')`（workbench-v3 已有相同慣例）。

### 1.10 【MEDIUM／缺】動作清單搜尋框＋筆數
- v3：`MostWorkbenchPage.vue:990-994` 依語句過濾＋「共 N 筆」。
- v2：無。
- **修法**：`q` state 過濾 `r.narr.includes(q)`；過濾狀態下停用拖曳（index 對映會亂）。

### 1.11 【LOW／部分】已選列的 TMU/秒 合計
- v3 顯示「已選 N 筆 · X TMU / Ys」；v2 只有筆數（:731-733）。
- **修法**：對 `selectedRowIds` 加總 `r.tmu * r.freq` 顯示。

### 1.12 【LOW／部分】拖曳排序缺半列精度
- v3：`MiCompositionTable.vue:41-72` 以列中線判斷插上/插下，3px 藍線指示。
- v2：只插在 hover 列上緣（:385-399），拖到下半格會差一格。
- **修法**：`e.clientY` vs `rect.top + rect.height/2` 判斷，補下緣指示線。

### 1.13 【HIGH／部分】NL 快速建模缺「覆蓋 vs 只填空白」對話框與結果面板
- v3：`NlDraftInput.vue:38-52` 編輯器有內容時詢問兩種模式；逐欄逐 slot 實作 fill-empty（`MostWorkbenchPage.vue:389-449`）；結果面板顯示信心%、建議模型、情境 chips、逐 slot 徽章、警告（`NlDraftInput.vue:107-155`）。
- v2：`runNlDraft`（:439-463）**永遠 merge-patch，靜默覆蓋使用者已填的 slot**；`overall_confidence` 收了直接丟棄，無任何結果顯示。
- **修法**：偵測 `hasEditorContent`（nv 有值或任一 slot 非預設）→ 自製兩鍵小 modal 選模式；fill-empty 模式只套用「目前為空/預設」的鍵；NL 列下方加結果條（信心徽章＋suggested_seq＋逐 slot 命中/缺漏清單）。

### 1.14 【CRITICAL／錯誤】WI 群組僅存前端記憶體，且共享活列參照
- v3：「加入 WI」即呼叫 `saveMiStatement` 持久化（`MostWorkbenchPage.vue:649-663`）；子項為**深拷貝快照**（copy-on-write，:698-758），重載後仍在（:194-198）；WI 名稱可留空 → 自動以選中句子串接命名（:642-647）。
- v2：`addToWi`（:415-420）只 push `{id,name,rowIds}` 進 `useState` — **重新整理/切 tab 即消失**；群組只存 `rowIds`，`wiGroupTmu`（:433-436）讀活列：改列頻率 WI 合計默默變動、刪列 WI 默默縮水；WI 名稱強制必填（:744）無自動命名。
- **修法（最小）**：快照列資料進群組（`rows: selectedRows.map(structuredClone)`）＋自動命名。**修法（完整）**：需要後端「MI statement」等價 API（v2 目前無），由 ddm-backend 開；過渡期先以 `localStorage` keyed by `activeWs` 持久化並標示「僅本機暫存」。

### 1.15 【HIGH／缺】WI 大綱編輯套件（改名/子項排序/子項刪除/已微調徽章）
- v3：`WiOutline.vue:33-78` 行內改名（非空、≤200 字、Enter/Esc）；:141-185 statement 與子項皆可拖曳排序（後端持久化）；子項單獨刪除；「已微調」徽章。
- v2：大綱（:759-813）只有展開＋整組刪除＋列高亮。
- **修法**：依 1.14 快照模型後補：行內改名、子項 ✕、展開清單內 DnD（模式同動作表）。

### 1.16 【CRITICAL／缺】WiItemInspector 抽屜（WI 微調工作流的入口）
- v3：`WiItemInspector.vue` 右側抽屜 — 點大綱子項 → copy-on-write 編輯 model/手/slots/情境/頻率/SIMO → `updateMiStatementItem` 後端權威重算 → statement 回寫。
- v2：無；大綱子項是唯讀文字列（:798-805）。
- **修法**：建 `WiItemInspector.tsx` 固定右抽屜，重用 slot modal 的選值區塊。**先決條件**：slot 編輯區塊（aBlock…iBlock）目前在 `WiWorkbench.tsx:198-286` 與 `workbench-v3/ActionModuleWorkspace.tsx:155-279` **逐字複製兩份**，Inspector 是第三個使用者 — 先抽成共用元件再做。依賴 1.14 的持久層。

### 1.17 【LOW／部分】GM/CM 切換的狀態遷移
- v3：保留共用 A1/B1/G/A3、丟不相容 slot、預設 B2=眼部動作（徽章「預設值」）、由「到哪裡」推斷 P=放（徽章「AI 推斷」）、A2 標「待確認」。
- v2：radio 只翻 `cur.seq`，兩組 slot 並存所以不丟資料，但無預設/推斷/徽章。
- **修法**（選配）：切 GM 時若 `!cur.b4` 且 `!cur.p_base && cur.nv.to` 給預設＋徽章。

### 1.18 【MEDIUM／缺】計算錯誤未呈現給使用者
- v3：`formatCalcError`＋`el-alert` 顯示具體原因。
- v2：`onError: () => { setTmu(null); setTech('') }`（:175）— TMU 變 — 使用者不知為何。
- **修法**：`calcError` state＋slot 列下紅色警示列。

**已確認移植正確（Area 1）**：slot 點擊→modal 即時 TMU 預覽；slot 色彩／已填未填狀態；⠿ 拖曳＋checkbox 多選＋行內頻率＋SIMO checkbox＋納入欄劃線；debounce 後端計算；RBAC 停用新增/儲存。

---

## 2. WI 組裝三層工作台（v3 `MostWorkbenchV3Page.vue` → v2 `workbench-v3/*`）

### 2.1 【MEDIUM／錯誤】Tab 徽章語義錯了
- v3：徽章＝**庫存量**（模組數/WI 數/流程 WI 數，`MostWorkbenchV3Page.vue:100-111`），常駐。
- v2：徽章＝待傳送數（`MostWorkbenchV3.tsx:34-44`），消化後即消失。
- **修法**：shell 撈三個 list 的 count 常駐顯示；待傳送藍徽章降為次要指示。

### 2.2 【MEDIUM／缺】作用中 tab 無 URL 持久化（`?mode=`）
- v3：`route.query.mode` 讀寫；v2 只有 zustand，重新整理永遠回 tab1。
- **修法**：`URLSearchParams` 初始化＋`history.replaceState`。

### 2.3 【HIGH／部分】ActionModulePool 功能斷崖
- v3 `ActionModulePool.vue`：12 欄表格 — 搜尋、GM/CM 篩選、全選(半選態)、拖曳排序、行內頻率 `input-number`、SIMO switch、Base/Eff TMU＋CT 欄、句子點擊→抽屜、編輯/複製/刪除、編輯中高亮。
- v2 `ActionModuleWorkspace.tsx:548-679`：卡片清單，只有搜尋＋checkbox＋編輯/複製/刪除。**缺**：模型篩選、全選、排序、行內頻率、SIMO、Eff TMU/CT、檢視抽屜。
- **修法**：改為表格（欄位鏡射 `MiCompositionTable`）；頻率/SIMO 走既有 `useUpdateModule`；先確認 motion-module API 是否收列級 frequency。

### 2.4 【HIGH／缺】DetailInspector 抽屜三個 tab 全缺
- v3：`DetailInspector.vue`（mode: action-module / wi-template / process-wi-instance），copy-on-write 編輯＋save/copy/delete/套用回模板，三個 workspace 都接。
- v2：`features/workbench-v3/` 完全沒有 inspector。
- **修法**：做一個共用 `DetailInspector.tsx`（骨架同 1.16），`mode` prop 決定按鈕組；Tab1 接 `useUpdateModule`/`useCloneModule`/`useDeleteModule`。

### 2.5 【MEDIUM／部分】建立器視覺不一致＋缺 Block H
- v3 Tab1 建立器重用 `SequenceSlotBuilder` slot 色塊＋`CalculationSummary`。
- v2 Tab1（:497-515）用行內下拉句型 — 跟 v3 不同、也跟 v2 自家 WiWorkbench 的 slot 色塊不同；無 CalculationSummary；NL 同 1.13 的問題（:282-303 靜默全蓋）。
- **修法**：把 WiWorkbench 的 slot 色塊列抽共用元件後套用；動作下方加統計列（基礎/頻率/有效/CT/SIMO/貢獻）。

### 2.6 【MEDIUM／部分】WIComposer 缺拖曳/複製/自動命名
- v3：`WIComposer.vue:48-69` 拖曳排序；:77-79 子項複製；:37-46 名稱留空自動取首句。
- v2：`WIPoolWorkspace.tsx:234-260` 只有 ↑↓；無複製；無名稱直接報錯（:263）。
- **修法**：composer 列加 DnD；複製鈕 `splice(i+1,0,{...mod})`；`handleSaveWi` 預設名 `composerModules[0]?.name_zh.slice(0,40)`。

### 2.7 【LOW／部分】WI Pool 卡片缺「編輯」
- v3 卡片有編輯（→inspector）＋複製/刪除；v2 只有複製/刪除（:81-96）。
- **修法**：編輯鈕開 2.4 的 DetailInspector。

### 2.8 【LOW／部分】Tab2→Tab3 傳送語義
- v3：pending WI 到達即自動加入流程；v2 只預勾選，要再按一次「加入流程」。
- **修法**：消化 pending 後自動呼叫 `handleAddToProcess()`（守 `activeWs`）。

### 2.9 【HIGH／部分】ProcessWorkspace 大綱扁平＋半殘
- v3 `ProcessOutline.vue`：流程名稱/代碼＋儲存/清空；WI 實例卡片可展開至模組實例；拖曳排序；子項複製；刪除有確認；每實例「套用回模板」；流程級 CalculationSummary。
- v2 `ProcessWorkspace.tsx`：大綱＝扁平 worksheet 列（:499-516）；無 WI 分組/展開；**刪除是 stub — `handleDelete` 只顯示「功能即將推出」（:303-305）**；無複製；無流程名稱/代碼/儲存/清空；排序僅本地、refetch 即丟（:284-301，被 :205-207 的 useEffect 重置）。
- **修法優先序**：(a) 列刪除走 worksheet 批次儲存（`useSaveWorksheet` 已存在）；(b) 排序透過同一儲存持久化；(c) 依 `source_module_id`+`source_module_version` 分組為可折疊 WI 實例卡；(d) 流程 metadata 對映 worksheet/版本命名 — 先與後端定合約再動工。
- **註**：v2 的「套用回模板」反而比 v3 完整（帶版本確認對話框，:34-85）— 保留。

**已確認移植正確（Area 2）**：Tab1→Tab2 跨層傳送與 pending 消化；toasts；pool 搜尋走後端 `q`（優於 v3 的前端過濾）；建立後發布流；實例化時 TMU 漂移警告（v2 特有，屬加分項）。

---

## 3. WI 專案建立（v3 `WISetBuilderPage.vue` → v2 `wi-project/WISetBuilderPage.tsx`）

### 3.1 【MEDIUM／錯誤】Auto 按鈕填錯欄位
- v3：`ProjectMetadataForm.vue:24-34` — `site-bu-process-family-model` 串接結果填入 **Project Name**（Auto 鈕在名稱欄上）。
- v2：（:279-308）同樣的串接卻填入 **project_code**；專案名稱欄沒有 Auto。
- **修法**：Auto 鈕移到專案名稱欄（`onChange({...form, name: autoCode})`）。

### 3.2 【MEDIUM／部分】必填驗證弱於 v3
- v3：儲存/自動建立前要求 name＋site＋bu＋process＋family＋model 全填（`WISetBuilderPage.vue:107-120`）。
- v2：`handleSave`（:1042-1051）只驗 name＋project_code，五個 metadata 靜默可空。
- **修法**：`handleSave` 與 `handleAddModules` 的自動建立路徑補齊五欄驗證。

### 3.3 【MEDIUM／缺】選中專案無 URL 持久化（`?id=`）
- v3 從 `route.query.id` 載入、create/duplicate/reset 皆 `router.replace`。v2 `projectId` 純 useState（:924），重新整理即丟。
- **修法**：mount 讀 `?wiSetId=`；select/create/duplicate/reset 時 `history.replaceState`。

### 3.4 【MEDIUM／部分】庫搜尋範圍不足＋展開子表缺欄／欄位錯位 bug
- v3：後端關鍵字搜尋涵蓋名稱/語句/動作；展開子表有 Action Sentence/Base TMU/Freq/Eff TMU/SIMO。
- v2：前端只過濾 `name_zh`/`id`（:469-475）；`ExpandedRows`（:436-449）只有序號/sub_activity/手/頻率 — 無 TMU、無 SIMO。**Bug**：展開列每列只 render 5 個 `<td>` 對 6 欄表，且 `<td>` 上掛了無效的 Tailwind `col-span-2` class（:441）→ 欄位對不上表頭。
- **修法**：補到 6 個 td（加列級 TMU＋SIMO 欄），移除 `col-span-2`；若後端 `/api/v2/motion-modules` 支援 `q`（workbench-v3 已在用）就改走後端搜尋。

### 3.5 【MEDIUM／錯誤】WI Code 快照塞了 UUID
- v3 快照帶真實 `wi_code`；v2 `handleAddModules` 塞 `wi_code_snapshot: m.id`（:1022）→ Section C 顯示截斷的 UUID。
- **修法**：motion-modules 尚無 code 欄位前送 `null`（欄位已會渲染 `'—'`），或由後端補值。

### 3.6 【HIGH／錯誤】快照數字由前端捏造（違反值權威原則）
- v3：`addItemsToProject(projectId, wiIds)` — **後端計算全部快照**。
- v2：`handleAddModules`（:1017-1027）前端算 `action_count = m.rows.length`、`total_tmu = m.total_tmu ?? 0`（list 沒給就靜默塞 0）、`total_seconds = tmu * TMU_SEC` — 違反本檔頭自己寫的 DISC-02/07 與全 repo「前端不計算」鐵律。且因 0.1 的合約問題，`m.rows` 根本不存在 → `rows.length` 會 throw 或恆 0。
- **修法**：add-item 只送 `wi_template_id`，快照由 `wi_set.py` 後端解析回填 — 確認新寫的後端是否支援 template-id-only 建立，不支援就請 ddm-backend 補。

### 3.7 【MEDIUM／錯誤】備註欄永不持久化
- v2 備註輸入只寫 `localNotes`（:837-846），從不送 PATCH，重載即丟 — **看起來可編輯實際會遺失資料**。
- **修法**：`onBlur` → 後端更新 item notes（`WiSetItemOut` 已有 `notes` 欄，缺的是 item 級 PATCH 端點 — 請 ddm-backend 補 `PATCH /items/{item_id}`），或先拔掉輸入框。

### 3.8 【LOW】其他偏差
- Section C 整列可拖曳（:792）vs v3 只有把手可拖 — 整列拖曳會搶備註輸入框的文字選取；`draggable` 限縮到 ⠿ 儲存格。
- 合計 TMU `toFixed(1)`（:897）vs v3 `toFixed(3)`。
- v2 只允許刪 draft 專案 vs v3 任何狀態確認後可刪 — 若為 v2 後端規則則保留，屬記錄在案的偏差。
- Section B 對 viewer 整段隱藏（:1171-1173）vs v3 唯讀可瀏覽 — 建議改唯讀渲染（checkbox disabled）。

**已確認移植正確（Area 3）**：Section A~E 結構；專案選單＋新增專案；加入時自動建專案流；複製/刪除；DnD＋↑↓＋批次移除（含插入線指示，與 v3 對齊良好）；5 格彙總含分鐘；debounce 搜尋；flash 訊息。

---

## 4. 橫切面（全站性問題）

### 4.1 【MEDIUM】角色權限只擋 sidebar 可見性，render 層不設防
- v3：router 全域 guard — 未登入→login、角色不符→dashboard；users/dictionaries 需 admin。
- v2：`Sidebar.tsx:107-111` 只是藏按鈕，`App.tsx:32-51` 對任何 tab id 無條件渲染 — `ddm:switch-tab` CustomEvent 可讓 viewer 開 `UsersPanel`。另有 gate 不一致：v3 字典管理需 **admin**，v2 sidebar 用 `canEdit`（analyst 即可）。後端仍有擋，屬縱深防禦缺失而非安全洞。
- **修法**：`App.tsx` 加 `TAB_MIN_ROLE` 對照表守 `renderContent`（fallback「無權限」面板）；字典管理門檻對齊 `docs/architecture/rbac-spec.md` 的裁定。

### 4.2 【MEDIUM】全站無 URL/路由持久化
- v3 全路由（深連結、重新整理安全）。v2 無 router：作用中 tab、workbench-v3 子 tab、WI-set 專案選取，重新整理全部歸零。
- **修法**：最小 — `?tab=`（＋2.2/3.3 的功能參數）用 `URLSearchParams`＋`history.replaceState`；完整 — 後續重構導入 react-router。

### 4.3 【MEDIUM】workbench-v3 內部無權限 gating
- v3 每個 workspace 都收 `canEdit` 並 disable 全部變更控制。
- v2 `features/workbench-v3/*` **從未 import `useMe`/`canEdit`** — viewer 看到可點的新增/刪除/發布按鈕，按下去吃 403 raw error。WiWorkbench 的 slot 色塊/下拉對 viewer 也仍可互動（只有加入/儲存被擋）。
- **修法**：各 workspace 開頭 `const editable = canEdit(useMe().data)`，變更類按鈕與建立器輸入統一 disable。

### 4.4 【LOW】儀表板是死 tab
- `Sidebar.tsx:9` 有 `dashboard`，`App.tsx` 無對應 case → 顯示「功能開發中」佔位。v3 儀表板有：啟用字典版本卡、案件狀態統計、近期案件表。
- **修法**：擇一 — 做最小儀表板（案件統計卡可直接用 `GET /api/v2/cases` 聚合）或先從 sidebar 拔掉。

### 4.5 【CRITICAL，見 0.1】全站無 Error Boundary
- 已列 0.1 修法 1。另建議 per-tab boundary（切 tab 可自救，不用重新整理）。

---

## 5. Playwright 實測對照摘要

| 頁面 | v3 (:5173) | v2 (:8877) | 對照結論 |
|---|---|---|---|
| 登入 | 獨立登入頁（email/密碼） | 無（gateway header 注入） | 架構差異，v2 走 LB 整合，可接受 |
| 儀表板 | 字典版本卡＋案件統計＋近期案件 | 「功能開發中」佔位 | 缺（4.4） |
| MOST 工作台 | 完整摘要列＋交錯 slot 流＋顯示於MI | 分離的下拉列＋slot 列 | 見 §1 |
| WI 組裝 tab1 | 常駐徽章 3/2/2＋建立器＋Pool 表格 | **白屏崩潰** | P0（0.1） |
| WI 組裝 tab2/3 | WI 組成器＋Pool／流程大綱含儲存/複製/套用回模板 | 崩潰後無法抵達 | P0＋§2 |
| WI 專案建立 | Section A~E＋必填星號＋Auto 填名稱 | 結構已對齊（本輪已重寫） | 見 §3 細項 |
| Level System | 「Coming Soon」佔位（v3 也未做） | 有完整 R1-R9 功能 | **v2 超前 v3**，保留 |
| 分析案件 | 列表＋篩選＋新增案件 | 雙欄清單＋簽核＋報表下載 | v2 結構不同但功能較完整，可接受 |
| 字典管理 | 版本管理（啟用/匯出/編輯/匯入） | 詞彙庫＋範本管理 | **語義不同**：v3 管字典「版本」，v2 管詞彙「內容」。v2 缺版本管理概念（ADR-014 的字典重匯流程目前只有 CLI 腳本） |
| 使用者管理 | email/姓名/多角色/啟停用 | 員編/角色 | 架構差異（LB 整合），可接受 |

---

## 6. 修復優先序與派工計畫

### P0 — 立即（阻斷生產）
| # | 項目 | 派工 | 預估 |
|---|---|---|---|
| 0.1 | ErrorBoundary＋`rows?.[0]` 修正＋list/detail 型別拆分 | ddm-frontend | 半天 |
| 0.2 | 測試資料汙染隔離＋清理腳本 | ddm-testing＋ddm-backend | 半天 |
| 3.6 | 快照改後端計算（值權威） | ddm-backend＋ddm-frontend | 半天 |

### P1 — 核心工作流（本週）
| # | 項目 | 派工 |
|---|---|---|
| 1.7＋1.8 | 列編輯/複製迴路（`payloadToState` 已在，~60 行） | ddm-frontend |
| 1.14＋1.15＋1.16 | WI 群組持久化＋快照語義＋Inspector（需先開後端 MI statement API） | ddm-backend → ddm-frontend |
| 1.13＋2.5 | NL 覆蓋/填空對話框＋結果面板（兩處共用） | ddm-frontend |
| 2.9 | ProcessWorkspace：刪除實作（現為 stub）、排序持久化、WI 分組 | ddm-frontend＋ddm-backend |
| 共用抽取 | slot 編輯區塊（aBlock…iBlock）抽共用元件（目前複製兩份，Inspector 要第三份） | ddm-frontend |

### P2 — UX 對齊（下週）
1.1／1.2／1.5（交錯 slot 流＋顯示於MI＋摘要列）、2.3＋2.4（Pool 表格化＋DetailInspector）、2.1（徽章語義）、3.1（Auto 填名稱）、3.2（驗證）、3.4（展開子表修欄）、3.7（備註持久化或拔除）

### P3 — 打磨
1.3／1.4／1.9／1.10／1.11／1.12／1.17／1.18、2.2／2.6／2.7／2.8、3.3／3.5／3.8、4.1／4.2／4.3／4.4

### 待補審查
- **核心邏輯對比** — ✅ 已完成，見 §7。**新增 P0 裁決項：SIMO 貢獻語義（7.1，v2 內部三處總數互不一致）＋捨入模式（7.2）**。
- **後端 API 對等性** — ✅ 已完成，見 §9。**新增 P0：F-01 儲存動作模組必定 422 失敗（rule-set code vs UUID）**。

---

## 7. 核心邏輯對比審查（已完成 2026-07-12）

> **稽核方法**：逐行比對 v3 權威引擎（`ddm-v3/apps/api/app/services/calculation_v2.py` 為現行認證版）與 v2 引擎（`most_engine/calculate.py`、`rule_set_data.py`、`narrative.py`、`level.py`、`schemas/v2/most.py`）；值表以 v3 字典對 v2 生成 seed **全區塊核對**；實跑 v2 seed 自我驗證（黃金錨全數通過，GM=28、CM=29）。
>
> **總結論**：值表與七格計算演算法（A/B/G/P/M/X/I 的 max 規則、加總、秒轉換、repeat 語義）**移植正確**。實質分歧僅一組 CRITICAL（SIMO），加一項 HIGH（捨入模式）。

### 7.1 【CRITICAL】SIMO 貢獻語義與 v3 認證引擎不同（✅ 已裁決 2026-07-13：對齊 v3，見 ADR-020）
- **v3**：boolean `is_simo` — 被標記列**貢獻 0**（`calculation_v2.py:261-266`、`:286`；route 層 `most_workbench_v3.py:460-461` 同）。時間由未標記的主列吸收。
- **v2**：`simo_group_id` 群組 — 群組取 **max 另外計入**總計（`calculate.py:280-298`；`worksheet_service.py:173-203` 同語義）。
- **分歧實例**：(a) 單獨一列帶 `simo_group_id` 無同組夥伴 → v2 全額計入、v3 語義應為 0；(b) 主列不在群組而平行列成組 → v2＝主列＋群組max（重複計），v3＝主列。
- **加重**：`cases_service.py:31` 清單聚合 `SUM(total_tmu × frequency)` 連 SIMO 都不處理 — **v2 自己內部三處總數就不一致**（engine / worksheet_service / cases_service）。
- **修法**：IE/架構裁決採用哪一契約並寫 ADR；若對齊 v3：`compute_table` 改「SIMO 標記列貢獻 0」，同步修 worksheet_service 與 cases_service，補 SIMO 黃金測試。
- **註**：v3 舊層 `most_workbench.py:179-184` 曾用 statement 級 max — v2 的群組 max 更像 v3 的**舊**語義而非現行認證版。

### 7.2 【HIGH】捨入模式不一致：v3 全程 Decimal ROUND_HALF_UP，v2 總計/秒數用 Python `round()`（half-even）
- v3：`calculation_v2.py:15-19,256-259,289-290`（TMU 3 位、秒 4 位，Decimal 全程 HALF_UP）。
- v2：`calculate.py:275-277,297-298` 用 `round()`（banker's rounding＋二進位浮點誤差）。v2 的 `seconds_to_tmu`（`rule_set_data.py:102-107`）本身已正確 Decimal HALF_UP，**只有總計/秒數兩處未對齊**。
- **修法**：兩處改 Decimal `quantize(HALF_UP)`（沿 ADR-014 E2 口徑），跑黃金測試確認 GM=28/CM=29 不動。

### 7.3 【MEDIUM】A 分量 twist 超 180° 時 v2 靜默夾最大檔
- v3 字典 hand_degree 僅四檔（≤30/60/120/180），使用者選不出 >180°；v2 `band_index()`（`rule_set_data.py:55-63`）超界靜默回最大 index。對照 v2 自己的 M 手度超 180° 會擲 `M_HAND_RANGE` — 同一物理量兩種行為。
- **修法**：`band_index` 無 overflow 帶且超界回 None → `_a_tmu` 擲 `A_RANGE` 422；或 IE 裁決允許夾檔並記 ADR。

### 7.4 【MEDIUM】repeat_count 上限：v2 封 1..99，v3 無上限
- v3 接受任意大 repeat（非法值靜默回退 1）；v2 超界擲 `REPEAT_INVALID`（`calculate.py:47-57`，檔內已註記「待 IE 拍板」）。
- **修法**：99 上限提交 IE 裁決；v2「擲錯而非靜默回退」的作法優於 v3，建議保留。

### 7.5 【MEDIUM】MI 句子生成結構性漂移
- v3 `_compose_sentence`（`most_workbench_v3.py:154-196`）：無標點直串，GM 語序「P→至{to}」；v2 `narrative.py:55-105`：標點散文體＋「伸手約N公分」「隨後」等 v3 沒有的片語，GM 語序相反（「到{to}→以P放置」）。
- **一致處**：P 可見詞演算法完全對齊；×N 後綴一致；B 不入句；x_none/i_none 略過。
- **v2 優於 v3**：「A_move 含手度→句中須現『翻轉+目標物』」是 v3 規格明文（`MiniMOST_system_data_spec.md:116`）但 v3 程式未實作；v2 `narrative.py:78-79` 有實作 — 屬補齊規格。
- **修法**：需與 v3 產出互驗時提供「v3 相容模式」；若散文體是產品決策，記 ADR。

### 7.6 【LOW】三項次要
- **V1 遺留 gating 死碼**：`calculate.py:112-114`（G modifier gating）、`:138-140`（P `needs_precision` 未勾時**靜默少算**）— V2 seed 全 False 不觸發，但屬地雷；V1 退役後刪除，期間加測試斷言。
- **有效 TMU 不量化**：v3 逐級 quantize 3 位，v2 浮點直乘只在總計 round — 小數頻率極端情況差 0.001；隨 7.2 改 Decimal 管線自然對齊。
- **manual_override 為 v2 擴充**（ADR-014 E7 治理增強，v3 無）— 非錯誤；確保覆寫值不進「與 v3 對驗」管線。

### 7.7 【INFO】v3 自身文件債（不需 v2 動作）
- v3 規格寫 P modifier 為「階梯升檔」，字典 JSON 與 v3 程式實作為固定 +8/+16 flat — ADR-014 已裁定字典為值權威，v2 跟隨字典**正確**。

### 7.8 已確認一致（Parity Confirmed，12 項）
1. 序列結構 GM=A B G A B P A、CM=A B G M X I A；CM 回程格更名 A3（僅計 reach）雙邊一致
2. A 格 modal max（A1/A2 = max(reach,手度,腳步)；A3 reach only）
3. M 格 modal max 與 repeat 語義（rep 只乘動詞，不乘手度/腳步）；v2 超值域擲錯優於套檔
4. P 規則（base 必選、modifier ≤2、插入⊥卡合互斥、base+Σmodifier）
5. X 規則（秒/0.036，Decimal HALF_UP 3 位；0.216s→6 TMU、10s→277.778 實測通過）
6. B/G/I 單選×repeat
7. TMU→秒＝0.036
8. frequency float >0
9. **值表全區塊核對一致**（A reach/手度/腳步、B、G 11 項、P base+modifier、M ladder/腳步/旋轉/手度、X 九檔、I 八檔；multiplier=1）
10. **黃金錨實跑通過**：GM=28、CM=29＋8 項邊界，seed 自我驗證全綠
11. Level System：v3 全庫**無**對應實作 — v2 `level.py` 是對 1205.xlsx 規格的獨立實作，無移植偏差問題
12. GM↔CM 欄位互斥：v2 比 v3 嚴（v3 無互斥檢查），合法資料下等價

## 8. 後端 API 對等性審查（已完成 2026-07-12）

> **稽核方法**：完整盤點 v3 三個 MOST 路由（`most.py` 18 端點、`most_workbench_v3.py` 23 端點、`wi_set_builder.py` 10 端點）＋ auth/users/dictionaries/analysis/reports，逐一對照 v2 路由、schema、service 與資料模型（含 alembic/migration 雙邊比對）。

### 8.1 【CRITICAL】F-01：儲存動作模組**必定失敗** — 前端送 rule-set code，後端要 UUID
- 前端：`workbench-v3/ActionModuleWorkspace.tsx:345-348` publish 時送 `rule_set_id: opts.code`（值是 `"MINIMOST_FACTORY_V1"` 字串）；`GET /rule-sets/{code}/options` 回應**沒有 id 欄位**（`rule_set_service.py:49`）。
- 後端：`schemas/v2/motion_module.py` `PublishRequest.rule_set_id: uuid.UUID` → **每次 publish 都 Pydantic 422**。create 成功但 publish 失敗 → 留下空 draft；且 `MotionModuleCreate` 靜默丟棄前端送的 `rows/status/source` 欄位。
- v3 對照：一個 POST 帶 slot_selections，**伺服器自己解析 active dictionary**，不收 client 的版本 id（`most_workbench_v3.py:320-367`）。
- **修法（建議後者）**：(a) options 回應加 `id`；(b) `PublishRequest` 改收 `rule_set_code` 伺服器解析（貼近 v3 模式）。另 `MotionModuleCreate` 加 `extra="forbid"` 讓靜默丟棄變成大聲報錯（no-error-bypass 鐵律）。

### 8.2 【CRITICAL】F-02：wi_set 快照全零寫入＋status 過濾被靜默忽略＋list/detail 合約錯位（白屏根因的後端面）
- **合約實證**：v2 list `GET /motion-modules` 回 `current_version_detail=None`（`motion_module_service.py:254,264`）；detail 才有巢狀的 rows/total_tmu（`:199-208`）。**兩者都沒有 top-level rows** — 前端型別宣告錯了兩層。
- **status=standard 被忽略**：route 只收 `q/scope/category`（`motion_module.py:45-53`），WI pool 因此混入 draft/retired。
- **後果**：F-04 頁面經此建立的每筆 `wi_set_items` 都是 `action_count=0, total_tmu=0, total_seconds=0`，`wi_code_snapshot`＝UUID — **持久化了錯誤資料**。
- **修法（對齊 v3 伺服器端快照鐵律）**：`POST /wi-set-projects/{pid}/items` 改收 `{wi_template_id}` 由 service 載入模組現版自行回填快照（v3 `add_items_to_project` 同款，`wi_set_builder.py:383-451`）；`list_modules` 加 status 參數；前端型別改讀 `current_version_detail`。

### 8.3 【HIGH】F-03：workbench-v3 的 NL 端點打到不存在的路徑
- 前端呼叫 `POST /api/v2/minimost/nl-draft`（`ActionModuleWorkspace.tsx:287`）— **此路由不存在**，實際只有 `/api/v2/worksheets/nl-draft` 且必填 `rule_set_code` → 永遠 404，被 catch 顯示「NL 解析功能尚未啟用」— 靜默功能喪失。且該處把回應直接餵 `payloadToState()`，格式也不對（正確格式見 WiWorkbench 的 NlDraftRes）。
- **修法**：改打 `/api/v2/worksheets/nl-draft` 帶 `rule_set_code`，寫 NLDraftResult→CycleState 的正確轉接器。

### 8.4 【HIGH】F-04：wi_set 欄位缺口 vs v3
- `wi_set_projects` 缺 **total_wi_count / total_action_count / total_tmu / total_seconds**（v3 每次增刪 item 即重算，`wi_set_builder.py:171-178`）— v2 清單無法以 SQL 聚合查詢總量。
- `wi_set_items` 缺 **wi_sentence_snapshot / wi_snapshot_json**（v3 含子動作的完整深快照）— 來源模組變更/退役後 **v2 無法重現 WI 內容**，快照設計意圖（v2 自己 model docstring 寫的）落空一半。
- 更名對照需記錄：`project_name→name`、`note→notes`、`order_index(0-based)→seq_no(1-based)`、`source_wi_id→wi_template_id`；必填性反轉（v3 五維必填/code 可空，v2 相反）。
- **修法**：migration 補 `wi_sentence_snapshot Text`＋`wi_snapshot_json JSONB`（隨 8.2 的 service 改造一起回填）；totals 四欄擇一（實欄＋service 重算 or `WiSetProjectOut` 計算欄位）。

### 8.5 【HIGH】F-05：v3 L2/L3 快照表在 v2 無對應
- v3 有 `action_module_templates / wi_templates / wi_template_items / process_routes / process_route_items`（含 `module_instances_json` 深快照＋逐項編輯＋套用回模板）。v2 把 L1+L2 折進 `motion_modules(+versions)`，只靠前端 `category='wi-template'` 慣例區分；L3 折進 `wi_set_projects`（淺快照）。
- **缺失端點**：WI template 逐項編輯（v3 #32）、逐項 reorder（#33）、wi-set 路徑的套用回模板（#41）。
- **修法**：要嘛補表，要嘛寫 ADR 明定「motion-module 版本制取代 v3 快照表」（版本不可變涵蓋快照性，但**不涵蓋逐項編輯**）— 這是產品決策，先裁決再動工。

### 8.6 【MEDIUM】其餘發現
- **F-06 reorder 是 no-op stub**：`PUT /motion-modules/reorder` 回 `{ok:true}` 什麼都沒做（`motion_module.py:88-96`），`motion_modules` 無 seq_no 欄 — 排序重載即丟。修法：加欄＋migration＋依 owner 範圍持久化。
- **F-07 人工句編輯/稽核欄全缺**：v3 的 `user_edited_sentence_zh / is_manual_edited / manual_edit_note / show_hand_in_sentence` 在 v2 `wi_rows`/`most_cycles` 皆無 — 「IE 手調語句留痕」UX 若在範圍內需補欄。v3 自由文字 context 對 v2 vocab FK：治理較佳，但 `component`/`where_location` 無 v2 vocab 槽位。
- **F-08 NL 情境抽取能力退化**：v2 backend↔frontend 合約內部一致（已驗證），但 v2 `context` 只會填 `reach_cm`（`nlp/rule_based.py:66-70`），v3 抽 hand/from/to/object/component/where＋missing_fields＋warnings。要達 v3 品質需擴充 RuleBasedParser。
- **F-09 業務規則差異**（多數 v2 較嚴＝可接受）：duplicate 未加「(副本)」名稱後綴（同名並列）；delete 限 draft（v3 任意）→ 前端要處理 409；reorder 要求全集 422（v3 靜默部分）；create 不收 status。
- **F-10 RBAC 模型差異**：v3 exact-set（approver **不能**動 workbench），v2 階層制（approver ≥ analyst **可以**動）；v2 無 reviewer 角色。需在 rbac-spec 裁決 approver-can-edit 是否符合意圖。所有權：v3 workbench 資源 owner-or-admin，v2 motion-modules 用 scope 隔離（含 404-not-403 IDOR 防護，等優或更好）；wi-set 兩邊都無所有權檢查（平手）。
- **F-11 案件簽核鏈缺**：v3 有 submit/review/request-changes/approve/archive＋per-case audit；v2 只有唯讀 cases＋worksheet publish/retire。若 worksheet 生命週期取代之，記 ADR（promote 端點已是 501 佔位等 ADR-018）。
- **F-12 SIMO 配對欄形狀不同**：v3 `simo_with_row_id` vs v2 `simo_group_id`/`simo_pair_index` — 能力等價，記錄對映即可。

### 8.7 已確認一致（8 項）
1. wi-set 9 條路由全存在且 method/path 對齊（含 reorder 先於 `/{item_id}` 的路由順序修正，雙邊同款）
2. 快照不可變意圖：soft-ref＋快照欄設計對齊 v3
3. wi-set RBAC 讀 viewer+/寫 analyst+ 對齊
4. nl-draft 的 v2 後端↔v2 WiWorkbench 前端合約**完全吻合**（含 404 on unknown rule_set）
5. 單一引擎權威：兩邊都是伺服器端重算 TMU（唯一違例＝8.2 的 wi_set 快照，修掉即全綠）
6. wi-set 錯誤語義 v2＝v3 或更嚴
7. users/admin、reports/export：v2 覆蓋 v3 且 export 是超集（LB 整合）
8. v2 migration v2_0019 ↔ model 雙邊逐欄一致（constraint 名/預設值/CASCADE/unique）

### 8.8 資料模型欄位缺口總表（v3 有 / v2 無）
| v3 表 | v2 缺的欄位 | v2 對應位置 |
|---|---|---|
| wi_set_projects | total_wi_count, total_action_count, total_tmu, total_seconds | wi_set_projects（8.4） |
| wi_set_project_items | wi_sentence_snapshot, wi_snapshot_json | wi_set_items（8.4） |
| most_sequence_items | user_edited_sentence_zh, is_manual_edited, manual_edit_note, simo_with_row_id | wi_rows/most_cycles（8.6 F-07/F-12） |
| most_mi_statement_items | 整表無對應 | 無（8.5） |
| action_module_templates | context_fields_json, generated_sentence_zh, source, order_index, is_simo | motion_modules versions JSONB（8.6 F-06） |
| wi_templates / wi_template_items | tags_json, wi_code, module_count, 逐項快照 | motion_modules category 慣例（8.5） |
| process_routes / process_route_items | module_instances_json 深快照 | wi_set_projects 淺快照（8.5） |

## 9. 附錄

- 截圖存放：session scratchpad `shots/`（v3 十頁全數成功、v2 崩潰前三張）
- 走查腳本：`walkthrough.mjs`（可改造為 regression e2e：「點遍所有 tab 不得白屏」）
- 白屏重現腳本：`crash-check.mjs`
- 本文件由審查總召（主對話）彙整；前端 34 項發現由前端審查 agent 回報，P0 兩項由 Playwright 實測發現。
