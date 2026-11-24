# ADR-038：統一 WI 工作區（三種輸入共用編輯區）與距離兩段式

## 狀態

🟢 **accepted**（2026-11-23，Howard 核可）。方向與待定參數 P1–P6 由 Howard 於 2026-11-23 逐項裁決（見 §7）。
欄位與 migration 細節於實作計畫展開；§10 的既有文件回寫隨本次核可一併進行。

- **關聯**：
  [ADR-021](ADR-021-ia-restructure-v3-parity.md)（IA：不得靠加 tab 承載新功能）、
  [ADR-022](ADR-022-workbench-two-layer-correction.md)（工作台動作/WI 兩層模型；**本 ADR 取代其 UI 部分**，見 D4）、
  [ADR-017](ADR-017-motion-modules-library.md)（組件庫，proposed；本 ADR 不採用其 UI）、
  [ADR-024](ADR-024-master-data-vs-dictionary-boundary.md)（主數據／字典分界）、
  [ADR-025](ADR-025-import-template-matching-p2.md)（匯入範本比對；`motion_templates` 保留）、
  [ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md)（revision 樂觀鎖）、
  [ADR-031](ADR-031-spatial-layout-and-distance-acquisition.md)（空間佈局，proposed；**本 ADR 採用其距離治理規則，但不採用其工位模型**，見 D5）、
  [ADR-037](ADR-037-ai-service-integration.md)（ai_service 整合；**本 ADR 定義其 D4 審核的落點**，見 D3）。
- **對應文件**：`docs/architecture/dsx-integration-api-contract-draft.md`（**本 ADR 反轉其距離計算方向**，見 D5.4）、
  DSX 側 `~/workspace/dsx_ai_factory/scenarios/most-single-station/data-service/`（`GET /api/v1/objects`、`GET /api/v1/placements`；2026-11-23 唯讀查證）、
  [實作計畫](../roadmap/ai-service-integration-plan.md)（S3 前端、S4、S5 依本 ADR 重新規劃）。

---

## 1. 脈絡

### 1.1 三種輸入方式（Howard 2026-11-23）

使用者建立一份 WI（MOST 工時表）時有三種輸入方式：

1. **人工逐一輸入**：用句子填空一個 motion 一個 motion 建，TMU 由引擎算。現有功能。
2. **單句 AI 解析**：輸入一句工序描述，AI 拆成多個 motion 與候選格位代碼，使用者修改後存檔。
3. **整份上傳**：上傳 Excel，AI 逐列解析，回傳整份 MOST 草稿，使用者逐列確認、編輯或刪除。

12 月三種都要上線（Howard 2026-11-23：2、3 都要）。

### 1.2 現在的介面不夠直覺

- 三種方式散在不同頁面：工時表編輯器（經「分析案件」進入）、MOST 工作台（`workbench-v3`）、WI 專案頁（`wi-project`），
  Excel 匯入又是另一條流程。
- MOST 工作台建的其實是**可重用的動作範本**（`motion_modules`），不是某個 SKU 的工時表，使用者容易混淆。
- ADR-037 的後端已接上 AI（PR #8–#12），但前端的「採用到編輯器」會把 AI 的預覽草稿直接載入編輯器，
  繞過 ADR-037 D3「人工採用須寫入 `chosen` 並重跑 compile 與引擎」。單句（情境 2）若先做臨時的「載入編輯器」，
  整份（情境 3）上線時又要再改一次。

### 1.3 距離不在句子裡

ADR-031 §1.1 量過：正式 gold 的 35 條 cycle，A 格全是 `A0`；距離是唯一貢獻者的 CM cycle 全部算成 0 TMU。
文字負責「做什麼」，空間佈局負責「在哪裡」。不論人工或 AI，句子都給不出距離，必須由另一個步驟補。

---

## 2. 決策

### D1 每份 WI 一個工作區，分「編輯區」與「工時表」

- 一份 WI 對應一個 **SKU 的工序版本**（`process_version` ⇔ `most_worksheet`，1:1）。使用者從 SKU（或案件）進入它的工作區。
- 工作區分兩塊：
  - **編輯區**：所有新產生的內容（手動、AI 單句、整份上傳）先進這裡當**草稿列**。
  - **工時表**：正式的 `wi_rows`／`most_cycles`，受 revision 樂觀鎖與 SOP 版本狀態管理。
- 只能在**草稿版本**的工序上編輯；已發布版本凍結（沿用既有版本規則）。
- 這是**取代**現有分散的頁面，不是新增一個 tab（ADR-021）。

### D2 三種輸入共用同一個編輯區

- 使用者在工作區內可隨時切換三種輸入方式，產出都落在同一個編輯區。
- 每個草稿列帶兩個標示：
  - **來源**：`manual`（手動）｜`ai_service`（外部 AI）｜`rule_based`（規則解析，含 AI 降級）｜匯入來源（Excel 列號）。
  - **狀態**：`pending`（待確認）｜`missing_distance`（缺距離）｜`confirmed`（已確認）。刪除的列從編輯區移除。
  - > **2026-11-23，W1，Howard 核可**：W1 實作的草稿狀態為 `pending`｜`confirmed`｜`committed`。`committed`＝已寫入工時表的草稿，保留為紀錄，不能修改或刪除（記 `committed_wi_row_id`）。`missing_distance` **不是草稿狀態**，屬 W2 的距離狀態，不存在 `wi_draft_rows.status`。
  - > **2026-11-23，W1，Howard 核可**：`rule_based` 草稿寫入後，`wi_rows.provenance` 為 `manual`（與人工列同等看待）；出處以 `wi_draft_rows.source` 為準。`ai_service` 寫入後標 `ai_external`，`imported` 標 `imported`。
- **審核單位是 motion**（工時表的一列），畫面上依 WI 語句分組（沿用 `wi_rows.wi_group`），並提供「整組確認」（Howard 2026-11-23 同意）。
  一句 WI 通常拆成多個 motion，所以 Excel 的一列進到工時表會變成好幾列。
- 情境 2 就是只有一組的情境 3：**單句與整份走同一套審核畫面**（ADR-037 D4「單一管線」）。
- 手動建的列也進同一個編輯區（來源 `manual`），不需要另外的審核步驟，但一樣經「寫入工時表」才落盤。
  - > **2026-11-24，W4，依審查建議，Howard 授權（W4 追記）**：澄清「不需要另外的審核步驟」。手動列進編輯區後仍要先「確認」才能寫入工時表，與 AI、匯入的草稿一致；這個「確認」就是使用者自己的那一個點擊，沒有另外的審核者，也沒有第二道審核畫面。前端「加入」按鈕改為「加入編輯區」（`POST /worksheets/{id}/drafts`），不再直接加進工時表列。
  - > **2026-11-24，W5，依審查建議，Howard 授權（W5 追記）**：整份上傳進編輯區後，「沒有產生草稿」的 Excel 列（超長、解析失敗、草稿寫不進去）可由使用者按「建空白草稿」補建：後端 `POST /api/v2/worksheets/{id}/drafts/blank-from-import` 建 `source=imported`、帶 `import_row_id` 的列，手別與作業名稱取 Excel 欄、`narrative` 取描述前 2000 字、cycle 是佔位。仍是一般草稿：要補齊格位並確認，才能寫入。

### D3 確認是標記；「寫入工時表」才一次落盤

- 「確認」只改編輯區的狀態，不寫工時表。最後按「寫入工時表」，把已確認的列一次寫入，走**既有儲存路徑**並套用 revision CAS（ADR-037 D5、ADR-027 §2）。
- 編輯區要能保存（中途關掉頁面，已確認的標記與修改不遺失）。
- 「刪除」只刪編輯區的草稿列，不影響工時表。
- > **2026-11-23，W1，Howard 核可（W1 追記）**：
  > - **規則版本**：寫入時一律以工時表的 `default_rule_set`（無則 active）重算，草稿 cycle 內的 `rule_set_code` 被覆蓋。已知風險：既有列若是別的規則版本，之後整份存檔會以第一列的規則版本重算全部列（既有行為，追加路徑讓它更容易發生）。
  > - **stale 條件**：W1 只做兩個：版本非草稿不能寫入；revision 版本鎖不符回 409。其餘 stale 條件與內容雜湊在 W3。版本鎖先於取草稿檢查：兩人同時按寫入，第二個得 409（不是「沒有可寫入的列」）。
  > - **上限**：每份工時表編輯區最多 5000 列（含已寫入的紀錄）；每列內容上限 16KB；拒絕 NaN／±Inf。
  > - **刪除稽核**：刪除尚未寫入的草稿不寫稽核表，只留伺服器 log（誰刪了誰建的哪一列）；寫入工時表經 worksheet revision 留 actor。
  > - **共用編輯區**：任一 analyst 可改、刪、確認、寫入別人建的草稿；`created_by`／`updated_by`／`confirmed_by`／`committed_by` 各自記錄。不做 ownership 與站點限制（BL-ENG-19）。
- > **2026-11-24，W3，依審查建議，Howard 授權（W3 追記）**：W3（單句與整份上傳寫進編輯區，migration `v2_0053`）實作結果。以下修訂 W1 追記中「stale 條件」「provenance」與 ADR-037 D3／D5 的 W1 追記；原文保留。
  > - **可接受的 motion（ADR-037 D3 在工作區的落實）**：依本節「使用者確認時，畫面上的值才成為該列的決定值」，在工作區按「確認」就是 ADR-037 D3 要求的「人工採用」，取代「人寫入 `chosen`」的機制。`ai_parse_runs`／`ai_candidates` 內的 `chosen` 仍為 null，只供畫面顯示哪些格是 AI 填的。寫入時 `compute_rows_for_save` 以工時表的規則版本重算 cycle，等價 engine_gate（engine_gate 唯一的拒絕條件是 `compute_cycle` 丟 `SequenceError`），算不過整筆失敗。`parse_snapshot.complete` 只是「要不要人先補」的提示：解析不完整、而且 cycle 到現在沒被人改過（`cycle_hash` 與建立時相同）→ 確認與寫入都回 409 `DRAFT_INCOMPLETE`；它不是可接受的依據。同一規則也套用在 `rule_based` 草稿。W1 的「外部 AI 草稿寫入時 Fail-Fast」已移除，由本條取代。
  > - **stale**：寫入時，已確認的草稿若 `source_rule_set_id` ≠ 工時表的 `default_rule_set_id`（`rule_set_changed`），或來源 Excel 列的 `input_hash` 與建立時不同、或該列已被刪（`import_row_changed`）→ 409 `DRAFT_STALE`。這次寫入整筆作廢（含 revision 遞增）；另開交易把這些草稿退回 `pending`、記 `stale_reason`。重新確認時以現在的規則版本與 Excel 列為新基準並清除 `stale_reason`。套用於所有草稿。ADR-037 D5 的「引用列被改動」不適用，因為草稿一律追加到表尾、不引用既有列；一般存檔（revision 遞增）不算過期。這關閉 W1 追記「其餘 stale 條件在 W3」。
  > - **provenance（修訂 W1 追記）**：`ai_service` → `ai_external`；來自 Excel 列的草稿（`rule_based`、帶 `import_row_id`）→ `imported`，並帶 `source_import_id`；其餘照 W1（`rule_based`、手動 → `manual`）。
  > - **單句端點** `POST /api/v2/worksheets/{id}/drafts/from-sentence`（analyst+）：body 為 `text`（≤2000 字）、`hand`、`wi_group`（≤200 字）。規則版本取工時表的。先確認工時表可編輯、編輯區還有空位，才呼叫 AI（不白花額度）。外部 AI 分流與 `nl-draft` 同一套（`wi_ai_service.external_for`）；AI 降級或失敗時照樣進編輯區、來源標 `rule_based`。一句一組（共用 `group_key`），`wi_group` 預設為原句截 200 字（截斷記在 `parse_snapshot.wi_group_truncated`）；解析不出 motion 時仍放一列佔位草稿。既有 `nl-draft` 保留。
  > - **整份上傳**：匯入綁了 `worksheet_id` 時，parse job 每列解析後寫進該工時表的編輯區（包在 savepoint 內）；手別與作業名稱（`wi_group`）取 Excel 欄。job 的規則版本與工時表不同、工時表不可寫、編輯區滿 → 該列不寫草稿，原因記在 `item.last_error.drafts`，job 照跑。重新解析同一列：取代沒人動過的 `pending` 草稿；已有人確認、寫入或改過（`updated_by` 有值）的不動，也不追加新的。既有的 submit 保留。
  > - **欄位**（migration `v2_0053`，加法）：`wi_draft_rows.source_rule_set_id`、`parse_snapshot`（JSONB）、`stale_reason`。見 [data-model-and-storage-spec](../architecture/data-model-and-storage-spec.md) §2.6b。
  > - **錯誤碼**：`DRAFT_INCOMPLETE`（detail：`incomplete_count`、`draft_ids` ≤200）、`DRAFT_STALE`（detail：`stale_count`、`drafts[{draft_id, reason}]` ≤200）。
  > - **延後與已知限制**：批次的外部 AI（batch lane）與 ADR-037 D6 的 Excel 數量權威移到 W3b；超長與解析失敗的 Excel 列不產生草稿，畫面處理在 W5。見 [交付計畫](../roadmap/adr-038-delivery-plan.md)。
- > **2026-11-24，W4，依審查建議，Howard 授權（W4 追記）**：W4（工作區畫面，純前端，無 migration）實作結果。原文與前面各次追記保留。
  > - **畫面**：工時表編輯器（`features/wi-workbench/WiWorkbench.tsx`）改為工作區。上方「輸入方式」切換手動／單句／整份上傳；編輯器的加入按鈕改為「加入編輯區」；編輯區列表（`drafts/DraftArea.tsx`）依 `group_key` 分組，顯示來源、狀態、過期、不完整、截斷與解析備註，支援單列與整組確認、編輯、刪除、「寫入工時表」。單句輸入（`drafts/SentenceInput.tsx`）呼叫 `from-sentence`，顯示 `GET /wi-ai/status` 的 AI 狀態與降級文案。
  > - **移除「採用到編輯器」捷徑**：`AiDraftPanel`、`aiDraft.store`、`detectLanguage` 與 `workbench.aiDraft.*` 文案已刪除，滿足本節「不再提供『採用到編輯器』直接載入 cycle 的捷徑」。`workbench-v3` 的 `ActionModuleWorkspace` 還有同類 adopt 路徑，隨 W6 移除（W6 已完成，2026-11-24）。
  > - **編輯草稿**：把草稿載入編輯器，按「更新草稿」送 `PATCH`。**沒改格位就原封保留草稿的 cycle**，避免「打開再存」把 AI 內容改形狀，也避免繞過後端「cycle 沒被人改過」（`cycle_hash`）的 `DRAFT_INCOMPLETE` 判斷。改了任何格位，整個 cycle 換成編輯器的產出，敘述（narrative）清空。草稿含編輯器放不下的內容（多個 M 分量、超過兩個 P 附加）時顯示提示。換工時表時放棄正在進行的編輯。
  > - **寫入工時表**：帶 `base_revision`。表上（含 level、LB 標記）有未存檔修改時前端擋下，要先存檔。409 版本衝突：提示、重新載入，草稿維持 `confirmed`。409 `DRAFT_INCOMPLETE`／`DRAFT_STALE`：在列表上標出是哪幾列。
  > - **整份存檔不帶 `distance_status`**（沿用 W2：未帶＝保留既有值）；存檔後若有 `confirmed` 因 W7b 退回規則變空，畫面提示。
  > - **整份上傳入口**：開既有匯入精靈（與標頭按鈕同權限門檻），文案明講「目前直接寫進工時表、不經編輯區」並先確認。W5 改成進編輯區。**W4～W5 之間**整份上傳不經編輯區，也不開啟距離檢查開關（D6），這是已知且已向使用者說明的過渡狀態。
  > - **既有列仍可直接改**：工時表上既有的列仍可在表上修改、排序、刪除後整份存檔。本節的範圍是「新產生的內容」，不是既有列的編輯方式。
  > - **學習迴圈暫停**：工作區不再送 `nl-draft` 的 review 事件（原 `AiDraftPanel` 採用時送）。後續由後端在 `commit_drafts` 以 `ai_parse_run_id` 與最終 content 產生 review 事件，前端不補送；追蹤見 BL-ENG-20（docs/BACKLOG.md）。
  > - **已知限制**：(1) 編輯草稿時的即時試算用目前 active 的規則版本，寫入時以工時表的規則版本重算，兩者不同時試算可能不準；(2) `PATCH` 沒有版本欄，兩人同時改同一列草稿，後者覆蓋（共用編輯區已接受，見 W1 追記）；(3) `DRAFT_INCOMPLETE` 原本要求「確認前先乾算引擎」，前端以編輯器的即時試算代替；(4) 解析 issues 以原始代碼顯示（診斷資訊，未翻成文案）。
  > - **驗證**：`src/frontend/e2e/workspace-drafts.spec.ts`（9 個，mock API）。e2e 全套在並行時有既有的順序依賴（共用 DB），`workers=1` 時 204 passed、13 skipped。
- > **2026-11-24，W5，依審查建議，Howard 授權（W5 追記）**：W5（工作區整份上傳進編輯區，純前端加兩個後端端點，無 migration）實作結果。取代 W4 追記「整份上傳入口」中「W5 改成進編輯區」的過渡說明；原文保留。
  > - **工作區上傳流程**：上傳時綁工時表（`upload?worksheet_id`）→ 欄位對應 → 建 parse job（規則版本取工時表的，`idempotency_key=workspace:<import_id>`，同一次上傳只建一個）→ 每 3 秒輪詢進度（解析由後端 worker 推進）、每處理一列重讀編輯區 → 結束後列出「沒產生草稿」的列，可建空白草稿。進行中的 job 只把 id 記在 `sessionStorage`，job 不存在（404）時自動清除。工作區上傳**沒有** ADR-025 的範本採用面板（解析器本身仍會參考範本）。
  > - **建 job 先驗目標工時表**：匯入綁了工時表時，`POST /imports/{id}/parse-jobs` 先驗：工時表不存在 404、不可編輯 409、編輯區滿 422、job 規則版本與工時表不同 409（`field=rule_set_code`，`detail.expected` 給工時表的版本）。建立之後狀態才變的，仍走 `item.last_error.drafts`（W3 追記）。
  > - **新端點 `GET /api/v2/imports/{id}/parse-jobs/{job_id}/items`**（analyst）：逐列回 `source_row_no`、描述前 200 字、`status`、`has_drafts`、`reason`（`text_too_long`｜`parse_failed`｜`last_error.drafts` 的原因）、`ai_error_kind`。成功 item 帶 `last_error.drafts` 不當失敗顯示（W3 追記）。
  > - **新端點 `POST /api/v2/worksheets/{id}/drafts/blank-from-import`**（analyst）：只接受綁這份工時表的匯入列（否則 404）；已有草稿的列跳過（重按不重複建）。草稿 `source=imported`、帶 `import_row_id`；`parse_snapshot.complete=false`，所以補齊格位前確認與寫入都回 409 `DRAFT_INCOMPLETE`；帶 `import_input_hash`，納入過期判斷（`import_row_changed`）。
  > - **待 Howard 裁決：標頭的「匯入 Excel」按鈕**。W5 沒有動它，仍是舊流程（ADR-025 範本採用＋直接寫工時表），**這條路仍繞過編輯區與距離檢查開關（D6）**。選項：**A** 標頭按鈕改導到工作區上傳、舊流程從畫面移除，範本採用搬進工作區另開票（審查建議）；**B** 先把範本採用搬進工作區；**C** 維持到 W6。裁決前不得把本 ADR「整份上傳進編輯區」視為涵蓋所有匯入入口。
  > - **2026-11-24，Howard 裁決 A**：標頭「匯入 Excel」改為打開工作區的整份上傳（沒有開啟中的工時表時先提示）；舊的「範本採用＋直接寫工時表」流程從畫面移除（`ImportModal` 的 `submit` 模式、`MatchPanel`、`POST /imports/{id}/submit` 保留程式與端點），D10 的 e2e 一併移除。範本採用搬進工作區排入 [BL-ENG-21](../BACKLOG.md)。自此所有**匯入**入口都經編輯區（非匯入的直接寫入路徑——工時表編輯器的「從 WI 庫插入」、workbench-v3 的實體化——由 W6 移除畫面，D4；W6 已完成）。
  > - **已知限制**：(1) `has_drafts` 是「現在還有草稿」，使用者刪掉某列草稿後該列會再被列出（可再建空白草稿）；(2) items 端點沒有分頁，筆數受匯入列數上限約束；(3) `drafts` 模式的 `/map` 仍計算範本比對但不顯示。
- **本 ADR 定義 ADR-037 D4 審核的落點**：ADR-037 規劃的「審核佇列」就是工作區的編輯區，不另做獨立頁面。
- AI 草稿的處理（滿足 ADR-037 D3 澄清「預覽不是可接受依據」）：
  - AI 的格位代碼在編輯區是**候選**（`chosen` 為空），畫面上可直接看到預填的值，但列狀態為 `pending`。
  - 使用者確認時，畫面上的值才成為該列的決定值；寫入前**重新 compile 與引擎計算**（含 engine_gate），TMU 一律以重算結果為準。
  - 不再提供「採用到編輯器」直接載入 cycle 的捷徑。
- AI 結果（`ai.status=ai_service`）**不使用** nl-draft 回應的 legacy 相容欄位（頂層 `slots`／`suggested_seq`）：
  它們永遠來自 rule_based，且首次與重播內容不一致（實作計畫「路由開放前置條件」的 legacy slots 待決事項，以此關閉）。
- AI 降級或失敗的列照樣進編輯區，來源標 `rule_based`，讓使用者知道要特別檢查。

### D4 移除 MOST 工作台與 WI 專案頁的畫面；不提供跨 SKU 重用

- **從畫面移除**：側欄的「MOST 工作台」（`workbench-v3`）與「WI 專案」（`wi-project`），以及工時表編輯器的「從 WI 庫插入」（ADR-022 E-4）。
- **不提供跨 SKU 重用**（Howard 2026-11-23）：每份 WI 都由使用者重新填寫或交給 AI 解析，不維護範本庫，也不做「從其他 SKU 複製」。理由：流程簡單。
- **後端與資料保留，不刪除**（Howard 2026-11-23 同意）：
  - `motion_modules`（action／wi-template）、`wi_set_projects` 的路由與資料表維持原狀，只是沒有畫面入口。上線後再評估是否刪除，屆時須另開 migration 並先備份。
  - **`motion_templates` 保留且繼續使用**：它是 Excel 匯入範本比對（ADR-025）與規則式解析 L0 範本提示（`nlp/linking.py`）的資料來源，
    拔掉會讓情境 3 的匯入比對與 AI 降級時的規則解析品質下降。
- 本條**取代 ADR-022 的 UI 部分**（工作台兩層 UI、WI 大綱、row inspector）。ADR-022 的資料模型說明（WI ⊃ motion 兩層）仍然成立，改以工作區呈現。
- > **2026-11-24，W6，依審查建議，Howard 授權（W6 完成追記）**：畫面移除已完成。側欄移除工作台與 WI 專案，刪除 `features/workbench-v3/` 與 `WISetBuilderPage`，編輯器移除「從 WI 庫插入」。保留項：後端 `/motion-modules`、`/wi-sets`、`rows/from-module`、`imports/{id}/submit` 與資料（沒有畫面入口）；動作範本（`motion_templates`）管理入口留在主數據管理的「動作模組範本」分頁。DSX 元件搬到 `features/wi-workbench/dsx/`。

### D5 距離兩段式；MOST 是距離資料與計算的權威，DSX 是操作介面

#### D5.1 空間單位：每個 SKU 一個標準工作站（Howard 2026-11-23）

- MOST **沒有工位**這個概念。距離以**單站**計算：一個 SKU 假設每一站都相同，只有一個**標準工作站**。
- 區域、區域座標、物件歸區都**按 SKU** 保存（鍵為 `skus.id`）。不按工序版本：同一 SKU 改 SOP 版本時擺放通常不變，自動沿用。
  不按廠區：不同廠區的 SKU 編號本來就不同（Howard 2026-11-23）。
- 因此 **不採用 ADR-031 的工位模型**：不新增 `stations` 主數據，不加 `wi_rows.station_id`。ADR-031 的距離治理規則（D4 建議帶出處、D5 直線距離、D6 存 3D、I1 引擎唯一時間權威、I5 不得靜默夾擠）照常適用。

#### D5.2 流程（Howard 2026-11-23）

1. **前：設定區域**。使用者為 SKU 的標準工作站建立區域、綁定 DSX 物件，在 DSX 的 3D 介面調整位置，再在 MOST 按「從 DSX 同步區域座標」（D5.4）。
   同一 SKU 只需做一次；之後的工序版本沿用。
2. **中：編輯 WI**。三種輸入方式（D2），此階段不需要距離。
3. **後：物件歸區**。系統把這份 WI 用到的物件與工具**去重列出**，使用者每個物件指定一次所在區域，所有相關列一次算出距離。
   指定結果**按 SKU 記住**，同一 SKU 的下一個工序版本自動帶入。
4. **算距離與 TMU**：MOST 依區域座標算距離（直線，ADR-031 D5），預填對應格位，再由引擎算 TMU（ADR-031 I1）。

#### D5.3 區域：類別固定清單可新增；區域綁 DSX 物件（Howard 2026-11-23）

- **區域類別**：固定清單（工具區、來料區、放料區等），admin 可新增。
- **區域**：屬於某 SKU 的標準工作站，記錄類別、名稱、綁定的 **DSX 物件 id**、中心座標（3D，ADR-031 D6）。
- **綁定方式**：MOST 後端提供代理 API 讀 DSX 的 `GET /api/v1/objects`，前端以下拉列出 DSX 物件讓使用者選。
  瀏覽器不直連 DSX（DSX 沒有認證，與既有 a3 查詢同一做法）。DSX 連不到時明確顯示「DSX 無法連線」，不偽裝成清單是空的。
- **取代 `external_code` 綁定**：現行把 DSX 物件 id 填在 `work_vocab_items.external_code`（由種子腳本灌入，無畫面），
  且因 `external_code` 唯一，「到哪裡」的詞彙項要加 `__to` 後綴（`dsx_service.SYNTHETIC_TO_SUFFIX`）。
  綁定改放在區域上後，「從哪裡」與「到哪裡」指向同一個區域即可，不再需要後綴。既有資料遷移方式在實作計畫定。

#### D5.4 座標交接：MOST 拉取、存快照；使用者按「同步」才更新（Howard 2026-11-23）

- **現行**：MOST 每次要距離就呼叫 DSX 的 `POST /api/v1/distance`，MOST 不存座標。
- **改為**：使用者按「從 DSX 同步區域座標」時，MOST 呼叫 DSX 的 `GET /api/v1/placements`（站內局部座標，公分，原點為作業員站位），
  為該 SKU 存一份**快照**（含 DSX 的 `placement_revision` 與同步時間、同步者）。之後所有距離都用這份快照算。
- **為什麼拉、不讓 DSX 推**：
  - DSX 已有這支 API，v1 不需要 DSX 改程式。
  - 同步是使用者明確、有紀錄的動作；有人在 3D 裡拖動物件，不會讓已算好的距離悄悄改變。
  - 推送需要 MOST 開放寫入 API 並驗證 DSX 身分，DSX 目前沒有認證機制。
- DSX 座標未就緒（DSX 回 409）時，顯示「DSX 座標尚未就緒」，不同步。
- 日後若要即時：DSX 只送「座標有變」通知，MOST 提示使用者重新同步，資料仍由 MOST 拉。
- **DSX 共用一個場景**：DSX 目前只有一個場景，各 SKU 不各建場景。使用者在 DSX 調好後，同步進**當前的 SKU**，MOST 為每個 SKU 各存一份快照。
  代價：在 DSX 調整時，使用者要清楚自己在做哪個 SKU（介面須顯示）。
- 現有的 DSX a3 查詢（`POST /api/v2/dsx/a3-distance`）在新流程落地前繼續可用（D7）。
- > **2026-11-23 修訂，Howard 裁決**：這個案子只改 MOST。DSX 需要配合或確認的事項，整理在一份獨立文件（由主 context 於 W7 撰寫，路徑待定），由 Howard 交給 DSX repo。

> **2026-11-24，W7b，依審查建議，Howard 授權**（上一則「路徑待定」的結果；原文保留）：該文件已寫成 [`docs/architecture/dsx-changes-for-adr-038.md`](../architecture/dsx-changes-for-adr-038.md)，列出 DSX 需確認的假設（`anchor_cm` 是否已含旋轉與人端偏移、站內原點、`placement_revision`、共用場景），由 Howard 轉交 DSX repo。

> **2026-11-24，W7a，依審查建議，Howard 授權**（D5.3–D5.4 的 W7a 實作結果；原文保留）：
>
> - **W7 拆兩個 PR**。W7a：區域類別、按 SKU 的區域、DSX 物件清單代理、同步快照、物件歸區、「這份 WI 用到的物件」。W7b：建模政策門檻與人端偏移、算距離與建議、套用後 `distance_status=confirmed`、DSX 配合事項文件。下列各點只描述 W7a 已落地的部分。
> - **資料**（migration `v2_0054`，欄位以 migration 與 `models/v2/zone.py` 為準；表的說明見 data-model-and-storage-spec §2.6c）：`zone_categories`、`sku_zones`、`sku_placement_snapshots`、`sku_object_zones` 四張表。內建類別 6 個：`work_surface`、`incoming`、`outgoing`、`tool`、`fixture`、`other`（`name_zh`／`name_en`），admin 可新增。同一 SKU 的區域名稱唯一。
> - **端點與角色**：共 11 個，見 `docs/architecture/rbac-spec.md`。讀取 viewer、寫入 analyst、新增類別 admin；`GET /dsx/objects` analyst（整合未開或連不到時回 200＋`available=false`＋原因，不回空清單）。
> - **同步（D5.4）**：區域中心取快照中該物件的 DSX `anchor_cm`（取放錨點後的量測點）；該物件沒有 `anchor_cm` 時退回 `station_local_cm`。每筆在快照裡記 `point_source`（`anchor`｜`station_local`）。快照裡找不到綁定物件的區域，清空中心並在回應中回報；換綁 DSX 物件同樣清空中心。回應附前一份快照，供畫面提示。呼叫 DSX 前先結束資料庫交易，不在等 DSX 時佔著連線。每個 SKU 保留最近 20 份快照。
> - **錯誤碼**：`DSX_DISABLED` 503、`DSX_UNREACHABLE` 502、`DSX_NOT_READY` 409、`ZONE_IN_USE` 409（區域還有物件歸在它底下時不能刪）。
> - **DSX 回應當不可信輸入**：本文 ≤ 2 MB；筆數 ≤ 2000，超過整份拒絕、不截斷；字串 ≤ 200 字；座標絕對值 ≤ 1000 cm 且須為有限數；拒絕重複 id；`station_id` 必填；`placement_revision` 須在 0 到 2^31−1。
> - **鎖順序**：一律先鎖 SKU，再鎖區域。歸區只接受未刪除且啟用的詞彙物件。
> - **不動的部分（D7）**：既有 `external_code`／`__to` 綁定與 a3 查詢（`POST /dsx/a3-distance`）維持原狀。以區域綁定取代它們的遷移留待後續。
> - **migration downgrade**：有任何區域、快照、歸區或非內建類別就拒絕。

#### D5.5 資料面要有物件座標（現在先用區域）

- 現在沒有物件座標，距離一律用**區域中心點**估算（Howard 2026-11-23：精度問題現階段不處理）。
- 但資料模型**現在就要有物件座標欄位**（可為空），之後有物件座標時直接填入，不需重新設計。
- 取用順序：有物件座標用物件座標，否則用所屬區域的中心點。算出的距離記錄來源（`zone_center`｜`object_coordinate`）與快照版本，供審核判斷準確度。
- 座標掛在「擺放」上，不掛在物件身分上（ADR-031 D2：擺放與物件身分分離）。資料形狀方向：
  `SKU →（多個）區域（類別、DSX 物件 id、中心座標）`；`(SKU, 物件) → 區域，＋可選的物件座標`。座標存 3D。

> **2026-11-24，W7a，依審查建議，Howard 授權**（D5.5 的 W7a 實作結果；原文保留）：`sku_object_zones` 以 (SKU, 物件) 為主鍵，帶可空的物件座標三欄（`object_x/y/z`，W7a 不寫入，三欄須同空或同有）；區域以複合外鍵 (`zone_id`, `sku_id`) 保證與歸區同屬一個 SKU，刪除用 RESTRICT。取用順序（物件座標優先、否則區域中心）與距離來源記錄（`zone_center`｜`object_coordinate`）在 W7b 算距離時才落地。

#### D5.6 算出的距離是建議，且不是每一格都算得出來

- 算出的距離是**帶出處的建議**（ADR-031 D4、I4），預填並標「暫定」，使用者確認後才成為該列的值；可整組確認。
- 能算的：**物件到物件的移動**（例：從來料區拿到放料區，a3、M 的位移）。
- 算不出的，須人工填或由 IE 定標準值：
  - **動作本身的行程**（撕包裝袋撕多長、貼標籤走多遠；ADR-031 §1.2）。
  - **手伸向物件的距離**（a0、a6）：需要人端量測基準，ADR-031 P10 尚未定案。**（2026-11-23 修訂：由下方追記取代）**
- 伸手與走動的分界（ADR-031 P1）仍待 IE 定；定案前，距離預填到哪個欄位（`reach_cm`／`foot_cm`）由使用者選。**（2026-11-23 修訂：由下方追記 (b) 取代）**

> **2026-11-23 修訂，Howard 裁決**（修訂上方「不是每一格都算得出來」的範圍；原文保留）：
>
> - **(a) 四種距離都自動算**：a3（從哪裡區到哪裡區）、M（推拉位移）、a0 與 a6（人到物件）。a0／a6 照現行做法從**人的位置**量：起點＝作業員站位加人端偏移（現行 DSX 為肩高 140 cm，見 `dsx_ai_factory/scenarios/most-single-station/data-service/config.yaml` 的 `station.measure_from`）。人端偏移可調整。
> - **(b) 伸手／走動分界**（ADR-031 P1）：距離 ≤ 門檻填 `reach_cm`，> 門檻填 `foot_cm`。門檻**預設 70 cm，可修改**。門檻與人端偏移都放在**建模政策**（`modeling_policy_version`，依 ADR-031 D3）：有版本，工時表記住當時版本，改門檻不會改到既有工時表。
> - **(c) 超出範圍的處理**：M 位置不分伸手／走動；超過 75 cm 是引擎錯誤，不是飽和，標「需 IE 裁決」，不截斷（ADR-031 I5）。A6 不得填 foot（ADR-014 E1、ADR-031 §1.3）；若 a6 超過門檻，不自動改填 reach，也不歸零，標「需 IE 裁決」。
> - **(d) 已知風險**：DSX 實測（`dsx_ai_factory/team_docs/most/03-open-questions.md` P4）從肩量到物件 bbox 中心，8 個物件全落 A24，原因是終點用了幾何中心。本案改用使用者擺到「手會去的地方」的區域中心，預期改善，但**未實測**。每個算出的距離記錄使用的起點、門檻與快照版本。
> - **(e) 動作本身的行程**（撕包裝袋等，ADR-031 §1.2）仍由人填。

> **2026-11-24，W7a，依審查建議，Howard 授權**（W7b 的建模決定，主 context 依建議；原文保留）：算距離時沿用 DSX 現行語句模型（其 schema 註解 `a0`＝人→從哪裡、`a6`＝到哪裡→人）：
>
> - `a0`：人 →「從哪裡」；語句沒有「從」時用「物件」。
> - `a3`、M：「從哪裡」→「到哪裡」。
> - `a6`：「到哪裡」→ 人。
> - 每個結果記 `snapshot_id`、`point_source`、使用的門檻與人端偏移。
> - 「改動作內容後已 `confirmed` 的距離狀態是否退回」（D6 追記 B）在 W7b 決定。
> - `anchor_cm` 是否已含旋轉與人端偏移，需 DSX 確認，列入 `docs/architecture/dsx-changes-for-adr-038.md`（W7b 產出）。

> **2026-11-24，W7b，依審查建議，Howard 授權**（D5.6 的 W7b 實作結果；原文保留，migration `v2_0055`、API 見 `src/ddm_v2/api/routes/v2/distance.py` 檔頭）：
>
> - **建議的儲存**：`wi_row_distance_suggestions`，一列一格（`a0`｜`a3`｜`m3`｜`a6`），`status`＝`suggested`｜`needs_ie`｜`unavailable`，`field`＝`reach_cm`｜`foot_cm`｜`distance_cm`。每格記兩端點出處、`snapshot_id`、使用的門檻、人端偏移與建模政策版本。`wi_row_id` 是軟參考（不設 FK，因為整份存檔會刪除重建 `wi_rows`）；唯一鍵 `(worksheet_id, wi_row_id, slot)`。
> - **端點**：`a0`＝人→從哪裡；GM 的 `a3`、CM 的 `m3`＝從哪裡→到哪裡；`a6`＝到哪裡→人。**決定**：列上沒有「從哪裡」時，`a0` 與 `a3`／`m3` 的起點都用 object。人＝站內原點＋人端偏移。物件位置：歸區有物件座標用它，否則用區域中心。
> - **欄位判定**：用**未取整**的距離比門檻與 75 cm。≤門檻填 `reach_cm`，>門檻填 `foot_cm`；`a6` >門檻 → `needs_ie`；`m3` 只填唯一的 ladder 分量（ladder 判定用存檔時同一個規則版本），>75 cm 或沒有、有多個 ladder 分量 → `needs_ie`。缺端點 → `unavailable`，原因 `endpoint_missing`｜`not_assigned`｜`zone_not_synced`。`needs_ie` 與 `unavailable` 不寫入任何值。套用 A 格時，另一個距離欄位清為 0。
> - **距離設定（D5.6 (b)）**：存在建模政策的 `policy_json["distance"]`（`reach_foot_threshold_cm`、`person_offset_cm`）。版本沒有這段時用 `DEFAULT_DISTANCE_SETTINGS`（70 cm、`[0, 0, 140]`）；這組常數凍結，要換值就發布新版本。admin 以 `POST /api/v2/modeling-policy/distance-settings` 發布新版本（advisory lock 序列化）並把預設指過去；新建工時表的政策版本由新表 `modeling_policy_defaults` **明確指定**（種入 V1），不以 `MAX(version_no)` 隱式選版（R2a）。既有工時表（含 clone）沿用自己的版本，不受影響。
> - **已知限制**：沒有「指回舊版」的路徑；沒有獨立稽核表（版本列記 `created_by`／`published_by`，預設指標記 `set_by`／`set_at`）；既有工時表不能改用新版本。
> - **套用（`apply`）**：請求帶 `base_revision` 與 `computed_at`（使用者看到的那次計算）。**列級套用，不做格位級部分套用**：只有該列全部格位都是 `suggested` 才套用，否則 409 `DISTANCE_NOT_APPLICABLE`，detail 列出各列原因（`no_suggestion`、`marked_not_applicable`、`needs_ie`、`unavailable` 及其原因）。`computed_at` 與存著的不符，或重算結果和存著的不同 → 409 `DISTANCE_SUGGESTION_CHANGED`（要重新算再確認）。各列規則版本不一致 → 409 `CONFLICT`（`field=rule_set_code`）。成功時走整份存檔（從 DB 原樣重組），目標列 `distance_status=confirmed`，TMU 由引擎重算。
> - **權限**：`GET distance-suggestions` 與 `GET distance-settings` viewer；`compute`、`apply` analyst 且工時表須是草稿版本；`POST distance-settings` admin。
> - **新錯誤碼**：`DISTANCE_NOT_APPLICABLE`、`DISTANCE_SUGGESTION_CHANGED`。
> - 同一 migration 順手修正 `v2_0054` 三個 CHECK 約束名（命名慣例已加前綴，原名重複前綴）。

### D6 完成檢查：缺距離的列不得核准或發布（12 月上線；Howard 2026-11-23）

- 工時表要核准或發布時，每一列的距離狀態必須是下列之一，否則擋下：
  - **已確認**：系統算出的建議或 DSX 查詢結果，經使用者確認。
  - **手動值**：使用者自行填的距離。
  - **此動作無距離**：IE 明確標示（例：純目視檢查）。
- **以明確狀態判斷，不以數值判斷**：A0（2.5 公分以內）是合法值，距離為 0 可能是真的、也可能是沒填，所以每列要有距離狀態欄位，檢查只看狀態。
- **只套用到經新工作區建立或編輯的工時表**。既有工時表（開發庫 2026-11-23：252 份、4242 列）沒有距離狀態，不受影響，否則全部無法核准。
- 草稿可以存檔；只擋核准與發布。
- 理由：距離為 0 會讓 TMU 偏低，卻被當成正式工時（ADR-031 I5：不得靜默低估）。

> **2026-11-23，W2 實作狀態（Howard 授權：有建議就照建議做）**：D6 的後端已在 W2 實作（migration `v2_0052`）。
>
> - **欄位**：`wi_rows.distance_status`（可空；`confirmed`｜`manual`｜`not_applicable`；CHECK `ck_wi_rows_distance_status`）、`most_worksheets.distance_check_required`（boolean，預設 false）。既有列與既有工時表維持空與 false，不受檢查。downgrade 在有任何列狀態或任何工時表已開啟檢查時拒絕。
> - **開關**：只在 `POST /worksheets/{id}/drafts/commit` 打開，之後不關。clone 複製開關與每列狀態。
> - **整份存檔（PUT）**：列沒帶 `distance_status` 時保留同 id 既有值；帶 `null` 才清除。編輯區草稿 content 可帶 `distance_status`，寫入工時表時一併帶入。
> - **核准（`POST /worksheets/{id}/publish`）**：先鎖工時表列（`FOR UPDATE`），再做 level gate，再做距離檢查。開關為 true 且有列的狀態為空時回 `409 DISTANCE_STATUS_MISSING`，detail 含 `missing_count` 與 `rows[{wi_row_id, seq_no}]`（依 `seq_no`，最多 200 列）。存檔與編輯區寫入在拿到列鎖後再確認版本仍是 draft，修掉並行核准時寫進已核准版本的競態。
> - **範圍**：已開啟檢查的工時表，經其他路徑（匯入 submit、模組實體化）建立的列沒有狀態，一樣擋核准。檢查只驗證「有沒有標示」，不驗證標示是否正確，核准者仍需判斷。
> - **`content_hash`**：`distance_status` 刻意不入 `content_hash`。下游不得以雜湊相同當作距離狀態沒變。
>
> **W2 審查後的決定（2026-11-23，依審查建議，Howard 授權）**：
>
> - **A 開關何時打開**：目前由 `drafts/commit` 打開。W4 工作區前端上線時，在工作區建立的新工時表一開始就設 true。匯入與模組實體化不打開；匯入改走編輯區後自然涵蓋。
> - **B 改動作內容是否退回已確認狀態**：暫不退回。留待 W7（自動算距離）一併決定。
> - **C 核准檢查順序**：先 level 再距離，維持。

> **2026-11-24，W7b，依審查建議，Howard 授權**（取代上方「B 改動作內容是否退回已確認狀態：暫不退回」；原文保留）：
>
> - **B 的決定：退回。** 整份存檔時，若該列**沒帶** `distance_status`、舊值是 `confirmed`，且 `distance_inputs` 有任何不同 → 退回未標示（空）。`distance_inputs` 包含：GM／CM 種類、object／from／to，a0／a3／a6 的 `reach`／`foot`，m3 各分量的動詞與距離。理由：`confirmed` 代表「使用者確認過這組距離建議」，距離相關內容變了，確認就不再成立。
> - **不退回的情形**：舊值是 `manual` 或 `not_applicable`（人自己負責）；呼叫端明確帶了 `distance_status`（以帶的為準，由呼叫端負責）。
> - **重新同步 DSX 後**區域中心改變，已 `confirmed` 的列**不**自動退回（符合 D5.4：座標只在使用者按同步時更新，已確認的值是當時的決定）。畫面提示留給後續（見交付計畫 W8）。
> - 套用成功時，目標列的 `distance_status` 設為 `confirmed`（見 D5.6 W7b 追記）。
> - **對前端的要求**（W4／W8）：整份存檔開始帶 `distance_status` 時，要「讀回什麼就帶回什麼」，且不得讓上述退回規則失效；建議未改動的列不帶此欄。

### D7 12 月範圍

> **2026-11-23 修訂，Howard 裁決**：自動算距離（區域設定、綁 DSX 物件、DSX 座標同步、物件歸區、依區域座標算距離並預填建議）**提前到 12 月底上線**。下文「12 月」一律指 12 月底。原表保留如下，**由其後的「12 月底範圍」表取代**。

| 12 月上線 | 12 月之後 |
|---|---|
| 統一工作區（D1）、三種輸入（D2）、編輯區逐列與整組審核、寫入工時表（D3） | 區域設定、DSX 座標同步、物件歸區、批次算距離（D5） |
| 移除工作台與 WI 專案頁的畫面（D4） | DSX 契約改版（D5.4） |
| 每列距離狀態與完成檢查（D6） | |
| 距離沿用現行做法：人工填，加上既有的 DSX a3 查詢 | |

**12 月底範圍**（2026-11-23 修訂，Howard 裁決；取代上表）：

| 12 月底上線 | 12 月底之後 |
|---|---|
| 統一工作區（D1）、三種輸入（D2） | 物件級座標（欄位已預留，D5.5） |
| 編輯區逐列與整組審核、寫入工時表（D3） | DSX 推送通知（D5.4 末段的「座標有變」通知） |
| 每列距離狀態與完成檢查（D6） | |
| **區域與自動算距離**：區域設定、綁 DSX 物件、DSX 座標同步、物件歸區、依區域座標算距離並預填建議（D5，四種距離見 D5.6 追記） | |
| 移除工作台與 WI 專案頁的畫面（D4） | |

- AI 每日額度改為 **10,000 次**（Howard 2026-11-23；原 2000）。單次匯入上限 1000 列，約一天 10 份大檔。
  額度在**每個程序內**各自計數，部署 N 個 worker 時實際上限是 N 倍（BL-ENG-15）。程式預設值與 ADR-037 D8 另以小 PR 更新。
- 整份解析為非同步（背景 job 加進度），解析完的列先顯示，不讓使用者等整份完成（沿用既有 parse-jobs，ADR-037 D6）。

---

## 3. 架構不變式（違反即否決）

- **I1 引擎是唯一時間權威**：編輯區、AI、距離計算都不產生 TMU；TMU 一律由 `most_engine` 算。
- **I2 編輯區不是工時表**：未經「寫入工時表」的內容不得出現在正式工時表、匯出、LB 投影或核准流程中。
- **I3 AI 結果須人工確認才成為決定值**：AI 的格位代碼是候選；確認前不得以其預覽結果作為可接受依據（ADR-037 D3）。
- **I4 距離帶出處**：每個由系統算出的距離都記錄 SKU、區域或物件座標、快照版本、計算方式與來源（ADR-031 I4）。
- **I5 不得靜默補 0**：算不出的距離保持「缺」，不填 0；完成檢查只看距離狀態，不看數值（ADR-031 I5、D6）。
- **I6 計算用的座標只有一份正本，是 MOST 的快照**（D5.4）：距離一律用快照算，不即時查 DSX。

---

## 4. 考慮過的選項

- **保留分散的頁面，只修「採用」按鈕**：改動最小，但三種輸入仍在不同地方，單句與整份要做兩套審核。未採用。
- **AI 結果直接寫入工時表、事後再改**：少一步，但工時表會混入未確認內容，核准與匯出分不清哪些可信。未採用（I2）。
- **保留範本庫供跨 SKU 重用**：可省重複輸入，但要維護範本與實體化快照的版本關係（ADR-017／ADR-022 的複雜度）。Howard 裁決不提供。
- **刪除範本庫的資料表**：畫面與後端一併清乾淨，但刪除不可逆，且 `motion_templates` 仍被匯入與規則解析使用。改為只移除畫面（D4）。
- **距離逐列指定**：直覺，但一份 WI 可能 50 個 motion、物件只有十來種，逐列指定重複工作多。改為按物件指定並按 SKU 記住（D5.2）。
- **DSX 為座標正本、MOST 每次即時查**：維持現行契約，但 MOST 算距離要依賴 DSX 在線，且 3D 裡的拖動會悄悄改變已算的距離。改為 MOST 拉快照（D5.4）。
- **DSX 推送座標給 MOST**：即時，但 MOST 要開寫入 API 並驗證 DSX，DSX 沒有認證機制。改為 MOST 拉（D5.4）。
- **新增工位主數據（ADR-031 D1）**：MOST 沒有工位，且一個 SKU 假設每站相同。改為按 SKU 的標準工作站（D5.1）。
- **DSX 每個 SKU 一個場景**：隔離清楚，但 DSX 要改。改為共用場景、按 SKU 分存快照（D5.4）。

---

## 5. 後果

- **好處**：使用者在一個地方完成一份 WI；單句與整份共用審核；AI 草稿不會未經確認進入工時表；距離有固定的補齊步驟，且隨使用累積（物件歸區按 SKU 記住）。
- **代價**：
  - 前端要重做工作區，原本暫停的 S3 前端 PR 依本 ADR 重新規劃，範圍比原計畫大。
  - 需要新的編輯區資料存放（§6 P1）與 migration。
  - DSX 契約要改版並通知 DSX 方（D5.4）；v1 只用 DSX 既有的 API，DSX 不需改程式。
  - 每列要新增距離狀態欄位，完成檢查 12 月就要擋核准與發布（D6）。
  - 移除畫面後，現有 29 筆動作模組、13 筆 WI 範本、1 個 WI 專案（開發庫數字，2026-11-23）沒有入口；正式環境的資料量需在移除前確認。

---

## 6. 待定參數（已於 2026-11-23 裁決，保留紀錄）

| # | 參數 | 裁決 |
|---|---|---|
| **P1** | 編輯區的資料存放 | **新表**（鍵為工時表，引用 `ai_parse_run_id`／`import_row_id` 當出處）。匯入暫存表以一份 Excel 為單位，不涵蓋手動與單句來源 |
| **P2** | 區域的分類 | **固定清單、admin 可新增**；區域綁 DSX 物件，MOST 代理 DSX 物件清單供下拉選擇（D5.3） |
| **P3** | DSX 交接介面 | **MOST 拉取**（`GET /api/v1/placements`）、存快照，使用者按「同步」才更新（D5.4） |
| **P4** | 物件歸區的記憶範圍 | **按 SKU**。MOST 沒有工位，一個 SKU 一個標準工作站；不按工序版本、不按廠區（D5.1） |
| **P5** | AI 每日額度 | **10,000 次**（D7） |
| **P6** | 完成檢查是否提前到 12 月 | **提前**；以每列距離狀態判斷，只套用到新工作區的工時表（D6） |
| **P7**（2026-11-23 修訂） | 自動算距離的上線時間 | **提前到 12 月底**，不再是 12 月之後（D7）；四種距離都自動算（D5.6 (a)） |
| **P8**（2026-11-23 修訂） | 伸手／走動分界（ADR-031 P1） | **暫定**單一門檻，預設 70 cm、可修改；放在建模政策（D5.6 (b)） |
| **P9**（2026-11-23 修訂） | 人端量測基準（ADR-031 P10） | **暫定**沿用 DSX 現行做法：作業員站位加人端偏移（肩高 140 cm），可調整；放在建模政策（D5.6 (a)） |

仍未決、由他處承接：ADR-031 的 P1（伸手／走動分界）、P10（人端量測基準）。**2026-11-23 修訂：P8、P9 為這兩項的暫定值，仍留待 IE 正式定案。**

## 7. 裁決紀錄（Howard，2026-11-23）

| 題目 | 裁決 |
|---|---|
| 三種輸入 12 月是否都上 | 2、3 都要 |
| 輸入方式的介面 | 每份 WI 對應一個 SKU，使用者在同一工作區內彈性切換三種方式（編輯區／工作區概念） |
| 審核單位 | 以 motion 為單位、按 WI 分組 |
| 「編輯區／工時表」的理解 | 確認 |
| MOST 工作台 | 改為不需要；範本庫畫面拔除 |
| 範本庫的資料 | 先隱藏、不刪 |
| 跨 SKU 重用 | 不做；使用者重新填或交給 AI 解析，比較簡單 |
| 3D 距離放在編輯前或後 | 前後都要：先設區域，編輯後物件歸區，最後依區域座標算距離與 TMU |
| 距離資料與計算的權威 | 在 MOST；DSX 是操作介面 |
| 區域精度 | 現階段不處理；但物件資料面要有座標欄位 |
| 區域定義的歸屬 | 一次設定，物件歸區要記住（範圍見 P4：按 SKU） |
| 12 月範圍 | 依 D7 切分 |
| P1 編輯區存放 | 新表 |
| P2 區域分類 | 固定清單、可新增；查清 DSX 綁定方式並讓使用者看 DSX 清單選擇 |
| P3 DSX 交接 | MOST 拉取、存快照（依建議） |
| P4 歸區範圍 | MOST 沒有工位，以標準工作站單站計算，一個 SKU 每站視為相同；按 SKU，因為不同廠區的 SKU 編號也不同 |
| P5 AI 每日額度 | 1 萬 |
| P6 完成檢查 | 提前到 12 月；以明確狀態判斷、只套用新工作區（依建議） |
| 自動算距離上線時間（2026-11-23 修訂） | 提前到 12 月底（修訂 D7）；四種距離（a3、M、a0、a6）都自動算 |
| 伸手／走動分界（2026-11-23 修訂） | 單一門檻，預設 70 cm、可修改；放建模政策，有版本（D5.6 (b)）。暫定，待 IE 定案 |
| 人端量測基準與 DSX 協調（2026-11-23 修訂） | a0／a6 從作業員站位加人端偏移量（現行肩高 140 cm），可調整，暫定；本案只改 MOST，DSX 待辦另立文件由 Howard 交給 DSX repo（D5.4） |

---

## 8. 風險

- **R1 範圍**：工作區重做、三種輸入、距離狀態與完成檢查都在 12 月，時程緊。緩解：D7 把區域、同步、歸區與自動算距離移到 12 月之後。**（2026-11-23 修訂，Howard 裁決：上述緩解撤回。範圍為 12 月底，自動算距離已在範圍內，時程風險更高；緩解改為 PR 順序讓區域與距離後端（W7）和工作區畫面（W4）平行，見實作計畫。）**
- **R2 完成檢查讓使用者無法發布**：12 月距離多為人工填，每列都要給狀態才能核准。緩解：整組確認、「此動作無距離」一鍵標示；只套用新工作區（D6）。
- **R5 在 DSX 調錯 SKU**：DSX 共用一個場景，同步進錯的 SKU 會讓距離錯。緩解：同步畫面明確顯示目標 SKU 與 DSX 的 `placement_revision`；快照可回看。
- **R3 移除畫面後使用者找不到舊資料**：現有動作模組與 WI 範本沒有入口。緩解：移除前確認正式環境資料量，必要時提供唯讀匯出。
- **R4 DSX 協調**：契約反轉需要 DSX 方配合，可能延後距離自動化。12 月不依賴它（D7）。**（2026-11-23 修訂：距離自動化已在 12 月底範圍內，v1 仍只用 DSX 既有 API、DSX 不需改程式；DSX 待確認事項見 D5.4 追記的獨立文件。）**

---

## 9. 不由本 ADR 決定

- 編輯區、區域、擺放的詳細欄位與 migration（實作計畫依 P1–P4 展開）。
- 工作區的版面與互動細節（前端設計稿）。
- `motion_modules`／`wi_set_projects` 資料表的最終去留（上線後評估）。
- ADR-031 的其餘待定參數。

---

## 10. 對既有文件的影響（本 ADR 核可後由 most-doc-sync 回寫）

| 文件 | 影響 |
|---|---|
| `docs/decisions/ADR-022-workbench-two-layer-correction.md` | 狀態註記：UI 部分由 ADR-038 D4 取代；資料模型說明保留 |
| `docs/decisions/ADR-031-spatial-layout-and-distance-acquisition.md` | 註記 ADR-038 D5：工位模型（`stations`、`wi_rows.station_id`）在 MOST 不採用，改為按 SKU 的標準工作站；增加「區域」層、MOST 快照為計算正本、物件座標欄位先預留；距離治理規則照常適用 |
| `docs/decisions/ADR-037-ai-service-integration.md` D8 | 每日預算預設值改為 10,000（另以小 PR 改程式預設） |
| `docs/decisions/ADR-037-ai-service-integration.md` | D4 審核落點＝工作區編輯區；legacy slots 待決事項由 ADR-038 D3 關閉 |
| `docs/architecture/dsx-integration-api-contract-draft.md` | 標註改為 MOST 拉 `GET /api/v1/placements` 存快照、MOST 代理 `GET /api/v1/objects`（D5.3、D5.4）；`external_code` 綁定與 `__to` 後綴由區域綁定取代；通知 DSX 方 |
| `docs/roadmap/ai-service-integration-plan.md` | S3 前端、S4、S5 依本 ADR 重新規劃 |
| `docs/agent-team/domains.yaml` | wi-workbench、motion-module 的路徑與 invariant（工作台畫面移除） |
| `.kiro/steering/wi-motion-core-structure.md` | 以工作台「WI 大綱」說明 WI ⊃ motion 的段落，改以工作區為例（由主 context 在使用者要求下修改） |
| `docs/decisions/README.md`、`docs/DOC_REGISTRY.md` | 索引 |
