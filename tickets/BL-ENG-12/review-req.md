---
類別: "PROCESS-RECORD"
狀態: "獨立REQ審查原文（R1 BLOCK；R2 PASS）"
票: "BL-ENG-12"
---

# bleng12-req-reviewer

以下保留獨立 context 原始回覆；主 context 未代其執行測試。

## R1（2026-10-28，審 Draft requirements.md）

### type ／ 範圍
- review_type: `req`　領域: 不適用　diff 範圍: `tickets/BL-ENG-12/requirements.md`（Draft、未追蹤；交審紀錄見 `state.yaml` log，2026-10-28）

### 阻擋級
- `requirements.md`:REQ-2／REQ-4 — 禁止外來提示與保留既有降級提示互相衝突 — 當 `diff.unmatched` 為空、但 `unattached_units_degraded > 0` 時，既有畫面仍提示資料警告對不上此工序表；刪除該提示違反 REQ-4，保留則與 REQ-2 的絕對禁止衝突。
- `requirements.md`:REQ-3 — 驗收意圖要求「兩語系 key 對稱」，把 i18n 實作結構寫入需求，違反 `doc-taxonomy.md` §1.8 — 英文複數可能需要 zh-TW 不需的 `_one` key；即使兩語系畫面語意正確，也可能被此內部結構要求誤判失敗。
- `requirements.md`:來源 — `docs/BACKLOG.md#BL-ENG-12` 的錨點不存在 — 讀者依引用定位時無法到達條目；`BACKLOG.md:281` 的標題包含完整中文標題，且未定義 `BL-ENG-12` 錨點。

### 建議
- `requirements.md`:REQ-1 — 保留可觀察的區分與數量判準；design／ACC 可進一步明確列出混合、全 unmatched 與空集合情境。
- `requirements.md`:REQ-2 — 澄清禁止的是本票新增的 unmatched 提示，還是所有語意相近的既有警告。

### 移交
- `state.yaml`:open_questions[0] — 交 architect/design：決定呈現方式與可攜的畫面行為驗證入口。
- `state.yaml`:open_questions[1] — 交 human/orchestrator：後續 git 寫入及實作須另取精確授權。

### 誤報（附證據）
- 「unmatched 是 motion 上的布林欄位」— 並非如此：`api.ts` 的 `WbDiff.unmatched` 是 `string[]`；後端以聚合結果 ID 減去 MOST ID 計算，與 REQ 所述「LB 有、MOST 沒有」一致。
- 「所有對不上工序表的警告都屬 unmatched 結果」— 不是；`unattached_units_degraded` 是另一個既有警告計數，F2 有獨立顯示語意。

### 測試結果
- 未跑測試；僅唯讀檢視文件、相關欄位與工作樹狀態。

**BLOCK** — REQ-2／REQ-4 存在衝突，REQ-3 含實作決定，且來源錨點懸空。

## R2（2026-10-28，窄複核；獨立 context、與 R1 不同 reviewer 實例）

### type／範圍
- `req`；BL-ENG-12 需求文件的 R2 窄範圍複審。

### 阻擋級
- 無。R1 三項阻擋均已解除：
  1. REQ-2 限制的是本票**新增**提示，既有 `unattached_units_degraded` 提示由 REQ-4 保護，不再衝突。
  2. REQ-3 改為驗證雙語可見語意，不再要求 i18n key 對稱。
  3. 來源改為具名條目；`docs/BACKLOG.md:281` 有對應標題。
- 未發現新的需求衝突或實作決定；REQ-1～REQ-4 均有可觀察、可測試的驗收意圖。

### 建議
- 後續 ACC 可具體列出混合、全 unmatched、全部正常、無結果，以及既有降級警告並存的情境。

### 誤報
- 無。

### 測試結果
- 未跑測試；僅唯讀檢視指定文件與 BACKLOG 標題。

**PASS**
