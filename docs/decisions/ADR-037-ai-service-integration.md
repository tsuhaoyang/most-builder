# ADR-037：WI AI Parser 改接外部 ai_service——MOST 只保留確定性管線與審核

## 狀態

🟢 **accepted**（2026-11-14，Howard 核可：merge PR #4 後指示繼續）。取捨由 Howard 於 2026-11-14 逐項裁決（見 §7）。
§6 的既有文件回寫隨本次核可一併進行。實作依 [實作計畫](../roadmap/ai-service-integration-plan.md) 分階段推進。

- **關聯**：[ADR-015](ADR-015-nl-parsing-in-scope.md)（NL 解析在範圍內）、
  [ADR-020](ADR-020-simo-contribution-semantics.md)（SIMO 貢獻語意）、
  [ADR-025](ADR-025-import-template-matching-p2.md)（逐列採用）、
  [ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md)（AI bounded context；§3 批次不得繞過逐列採用）、
  [ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md)（§2 revision 樂觀鎖、§5 review event＋outbox、§7 物理拆分條件）、
  [ADR-030](ADR-030-in-process-parse-worker-topology.md)（parse worker 拓撲，proposed）、
  [ADR-031](ADR-031-spatial-layout-and-distance-acquisition.md)（D4 數值出處）、
  [ADR-033](ADR-033-llm-planner-scope-narrowing.md)（LLM 職責收窄；本 ADR 修訂其 D2，見 D3）、
  [ADR-034](ADR-034-language-aware-error-contract.md)（錯誤信封）、[ADR-032](ADR-032-bilingual-ui-and-data-label-layer.md)（i18n 對稱）、
  [ADR-035](ADR-035-lb-projection-layer-and-motion-decomposition.md)（D4 QuantityPolicyV2）。
- **對應 ai_service 端**：`~/workspace/ai_service` 的 ADR-001（服務邊界；D1(e) 要求本 ADR 宣告 ADR-027 §7 觸發成立）、
  ADR-004（身分）、ADR-007（jobs）、ADR-011（flow step 與非同步 flow run，draft）、`docs/specs/e2e-wi-motion-poc.md`（WI→motion 抽取 schema）。
  接口以其 `docs/api/openapi.json` 為權威，本 ADR 不重述欄位。
- **實作計畫**：[roadmap/ai-service-integration-plan.md](../roadmap/ai-service-integration-plan.md)。

---

## 1. 脈絡

MOST 內有一套 in-process 的 LLM planner（`nlp/llm_client.py`、`nlp/prompts/*`、`nlp/llm_planner.py`），
由 `DDM_WI_AI_ENABLED` 控制，正式環境預設關閉。LLM 抽取已另起 repo `ai_service` 實作
（`POST /v1/llm/structured-completion`、bundle registry、provenance、lane 准入），MOST 不應再維護第二套 prompt 與 provider。

ai_service 對一句 WI 回傳 `motions[]`，每個 motion 含 `hand`、`seq_kind`、`sub_activity`、`object`、`slots`。
slot 值是 rule-set 的 **slot code**（例 `g_pick_sel`、`p_hold`），A 位置回語意量 `{kind, magnitude_cm|deg}`。
**不回 index、不回 TMU、不收也不回數量**（ai_service ADR-001 D6／D11；Excel 的 Qty 不在其白名單）。
這與 ADR-033 D2「LLM 只回角色片語，slot 由 MOST 的 `SlotLinker` 對映」不同（見 D3）。

ai_service 仍在開發：批量 flow（`wi_motion_parse`、202＋job）只存在於其 draft ADR-011；bundle 皆為 experimental；
code 清單是 bundle 內的 rule-set 複本，MOST 改 rule-set 不會自動同步；身分模型（ForwardAuth）尚未落地。

## 2. 決策

### D1 宣告 ADR-027 §7 物理拆分條件成立；LLM 歸 ai_service

ADR-027 §7「達條件再物理拆分」的條件已成立：GPU 與大型依賴、release cadence 與 MOST 不同。
ai_service 即 ADR-026 所稱的 `wi-ai-api`。責任切分如下：

| 能力 | 歸屬 |
|---|---|
| prompt、provider、model、bundle 治理、LLM 層 eval | ai_service |
| 把 WI 語句拆成 motion 草稿並給 code 與語意量 | ai_service（**只是建議**） |
| Excel／CSV 解析、批次切分、只送語句 | MOST |
| code 合法性、數量（QuantityPolicyV2）、距離、TMU、index、link／compile／engine_gate／routing | MOST（單一權威引擎） |
| 審核、人工修改、落盤、RBAC、稽核 | MOST |

MOST 內的 LLM 專屬程式移除：`llm_client`、`prompts/*`、`LLMClientPort`／`LLMRawResponse`、`LLMPlannerAdapter`。
確定性元件全部保留，並搬到不依賴 LLM 的位置：`most_compiler/*`、`policies.resolve_multiplier`、`engine_gate`、
`nlp/{linking,lexicon,quantities,normalization,routing,rule_based,rule_plan_adapter,gold_eval,contracts}`、
`llm_planner._parse_sanitize_validate` 與 `_sequence_orders_contiguous`（改作入站防腐層）、`PlannerError`、
`plan_v2_schema.PlannerRequest`（索取契約）、`planner_eval` 的脫敏函式。
舊 `ai_parse_runs`（`kind='llm'`）列必須仍可讀取與重播；凍結列舉不得收窄。逐項清單見實作計畫 §2。

### D2 Port＋adapter 隔離；ai_service 不可用時降級

- MOST 定義 `WiParserPort`：輸入 `{item_id, wi_statement, source_lang, context}`，輸出
  `{item_id, status, motions[], error, provenance}`。第一個 adapter 逐句呼叫 `structured-completion`；
  ai_service 的批量 flow 落地後只換 adapter，port 與下游不動。
- bundle code、`json_schema` 複本、lane 放設定，不寫死在業務邏輯；`json_schema` 複本記 hash 以偵測漂移。
- 測試以 fake ai_service server 為主（依 openapi.json 快照與真服務錄製的 golden 回應），CI 不連真服務。
- ai_service 不可用（逾時、5xx、429、契約不符、bundle 不可跑、熔斷開啟）時，`nl-draft` 照舊回 200 並走 `rule_based`，
  人工建表完全不受影響。`nl-draft` 維持同步，不改成 202。降級訊息不帶內部 URL 與錯誤細節。
- ai_service 的錯誤依 `error.code` 映射到 MOST 錯誤碼，走 ADR-034 信封，zh-TW／en 訊息對稱（ADR-032）。
- 外部失敗降級時（2026-11-22 追記，Howard 核可），回應的 `ai_error` 是粗粒度版：維運類分類（`misconfigured`、`auth`、`deployment`、`request_rejected`、`contract_mismatch`、`internal_error`、`bundle_not_runnable`）不帶 `upstream_code`；完整版只在 `ai_parse_runs.error` 與 log。
- **NO_MOTION 分類與降級原因欄位（2026-11-24，真實量測後，Howard 核可；加法）**：
  - ai_service 回 200 且 `motions` 是空陣列（schema 允許）時，mapper 拋 `AiServiceErrorKind.NO_MOTION`（`upstream_code="NO_MOTION"`），取代舊的 `contract_mismatch`／`motions_empty`。不重試、不計入熔斷失敗次數，降級到 `rule_based`。它不是維運類，所以回應看得到 `upstream_code`（上一條的維運類清單不含它）。降級結果不進快取，同一句重送會再外送。
  - `POST /worksheets/{id}/drafts/from-sentence` 的回應 `ai.reason`（`error_kind`、`upstream_code`；維運類不帶 code）說明降級原因。前端依 `error_kind` 顯示 zh-TW／en 對稱文案，不認得的值（含維運類）顯示通用說明。`ai.reason` 是成功回應內的欄位，不走 ADR-034 錯誤信封碼；`QUOTA_EXCEEDED` 有對應文案。
- 新開關命名為 `DDM_AI_SERVICE_ENABLED`，不沿用 `DDM_WI_AI_ENABLED`，避免舊環境的 `true` 在新路徑完成前意外啟用。
- **D8 守門新增的 port 欄位與錯誤分類（2026-11-20 追記，Howard 核可；加法）**：
  - `WiParseRequest` 新增 `actor`（觸發者）與 `scope`（single-flight 隔離範圍，例：site id）兩欄，只給 MOST 端的配額與合併使用，**絕不外送**（有測試鎖定外送 body 的 keys；與 D7「不送員工編號」一致）。
  - 內部錯誤分類新增 `QUOTA_EXCEEDED`（並行等不到許可、每人每分鐘、每日預算）。不列入可重試，也不計入熔斷失敗次數。
  - `actor`／`scope` 缺漏、`context` 含白名單外的鍵，是呼叫端 bug，守門層拋 `ValueError`（不能讓「沒有身分」變成「不受配額限制」）。
  - mapper 對不預期的回應形狀拋任何例外（`AiServiceError` 以外），adapter 轉成該筆 `failed`，`error_kind=CONTRACT_MISMATCH`、`upstream_code=MAPPER_REJECTED`，不讓例外穿出 port；同時記一筆 WARNING log，讓 mapper bug 對維運可見。log 訊息只帶例外類別名稱，不寫入語句與回應內容。
  - `QUOTA_EXCEEDED` 目前只是 MOST 內部分類。S3 接到路由而需要對外報錯時，必須登記 ADR-034 信封碼並補 zh-TW／en 對稱文案（ADR-032）；目前前端沒有這組文案。
  - **持久快取鍵加版本（2026-11-24，真實量測後，Howard 核可）**：外部 run 的 `ai_parse_runs.input_hash` 另含 ai_service 最近一次外送成功的 run 所回報的 `prompt_version`、`model_served`。實際回應的版本與最近一次不同時，以實際版本記這筆，之後的查詢就對到新版本。不設 TTL。已知限制：版本變更要等任一新句子外送後才發現；上線當次舊快取一次性 miss；多版本交替（canary）時快取會抖動，且可能以 `raced` 重播舊結果；`ai_parse_runs` 日後可加 `(bundle_id, created_at)` 索引。

### D3 ai_service 選的 slot code 只當候選（修訂 ADR-033 D2）

（Howard 2026-11-14 裁決選 (a)）

**入站形狀**
- mapper 對回應做欄位 allow-list，未知欄位丟棄不透傳；每句 motion 數與自由文字欄位（`object`、`sub_activity`）長度設上限。
- slot code 進 plan 時放在**新增的候選欄位**（帶來源＝`ai_service`），不直接填 `SlotCandidateSet.chosen`，不繞過 linker。
- MOST 仍以確定性 linker 對該句產生自己的候選。兩者一致 → 採用；不一致或 linker 無結果 → 以 ai_service 的 code 為候選，
  新增 routing reason 標審核，**不得自動採用**。未知 code（不在目標 rule-set）一律拒收並標審核。
  - **linker 比對第一版延後到 S4**（2026-11-22，Howard 核可）：ai_service 的 motion 切法不一定對得上 MOST 的 action 切法，
    第一版不比對，所有 AI motion 一律標 `ai_source_no_evidence`，一律人工審核（reason 名稱見 D4）。
- ai_service 的回應沒有 evidence span，ADR-033 D3 的字面子字串不變式在此路徑不適用；因此此路徑的 motion 一律經人工採用（D4），
  不存在自動落盤。
- `return` 型 A 位置在 compile 尚無對應分支：mapper 保留語意並標審核，不臆測格位。

**驗證**
- 候選 code 必須通過：存在於**目標 worksheet 的 rule-set**（`default_rule_set_id`，不是「當前 active」）→ compile → engine_gate。
- **可接受的 motion**：plan 完整（`complete=True`）、`compute_cycle` 通過、engine_gate 無 high 級問題。其餘只能人工補齊並重驗後才可接受。
  - **預覽不是依據**（2026-11-22 澄清，不修訂本條）：S3 的預覽 draft 是用 ai_service 候選的複本算的（`chosen` 恆為 None，`preview_drafts`），
    其 `complete` 與引擎結果**不得**作為「可接受的 motion」的依據。人工採用（實作計畫 S4）必須由人寫入 `chosen`，再重跑 compile 與引擎（含 engine_gate），不得沿用預覽。
  > **2026-11-24，W3，依審查建議，Howard 授權（W3 追記，ADR-038 D3）**：在工作區，「人按確認」就是這裡的人工採用（取代「人寫入 `chosen`」的機制；`ai_candidates` 的 `chosen` 仍為 null，只供顯示）。寫入時 `compute_rows_for_save` 以目標工時表規則版本重算，等價 engine_gate（其唯一拒絕條件是 `compute_cycle` 丟 `SequenceError`）。`parse_snapshot.complete` 只是提示：不完整且 cycle 未被人改 → 409 `DRAFT_INCOMPLETE`。預覽 draft 仍不是依據。同一規則也套用在 `rule_based` 草稿。細節見 [ADR-038](ADR-038-unified-wi-workspace-and-two-stage-distance.md) D3 的 W3 追記。

**不採信的欄位**
- `hand`、`seq_kind` 不採信。手別來源依序為 Excel 欄、使用者輸入、MOST 確定性解析；ai_service 的值只作提示，不一致時標審核。
- AI 不產生 SIMO：mapper 一律輸出 `simo_group_id`、`simo_with_row_id` 為 null（ADR-020）；SIMO 只能由人標。

**數值與出處**
- `magnitude_cm|deg` 只作提示，**不得寫入 `role.value`**。人工確認或填寫的距離、數量，以**獨立的出處欄位**進入：
  值、來源（人工／DSX／AI 估計經人確認）、確認者、時間。優先序：人工 > DSX > AI 估計。
- 出處欄位以加法放在 plan 契約（`nlp/contracts`），不改 `tests/unit/_contract_freeze_v1.py` 的既有凍結值；舊 `ai_parse_runs` 重播與 `plan_metrics_n` 釘值不受影響。
- compile **不再讀 `role.value`** 作距離或秒數。句面抽取（`_evidence_distance_cm`）仍在，可能把全句的距離掛到別的 motion，
  由 `distance_unevidenced_review` 擋下，且此路徑本來就一律人工採用。
- 這依賴 ADR-033 P3 的前兩項（刪 `compile.py` 的 `_role_distance_cm` 與 `x_seconds` 讀值），**是單句階段的硬前置**，須過 `run_all.py`（GM=28／CM=29）。
  ADR-033 P3 的第三項（補 `a6`／CM `a0`）不在前置內：首輪 `return` 型 A 位置一律標審核，且不得宣稱 ADR-033 P3 已全部完成。
- 帶出處的人工數值不觸發 `distance_unevidenced_review`／`quantity_unevidenced_review`；AI 估計值未經人確認前不進引擎（ADR-031 D4）。
- ADR-033 D1（LLM 不產數值）、D6（逐項降級）、D7（距離單一來源）維持，改為**入站不變量**。

### D4 單一管線，逐項採用，不設批次接受

四種流程（單句、批量、審核、人工修改）共用同一條管線：

```
Suggest(ai_service) → Map(mapper) → Validate(link/compile/engine_gate/routing) → ReviewItem → Decision → Commit
```

- 差別只在觸發者與同步／非同步。
- 採用一律**逐項**（ADR-025、ADR-026 §3）。不提供「批次接受」（Howard 2026-11-14 裁決移除）；`wi_ai_auto_enabled` 維持硬關。
  審核畫面可一次顯示多項，但每項各自決定。審核畫面顯示原文，並標示「AI 建議，語意未經驗證」。
- 風險判斷沿用既有 `ROUTING_REASONS` 與 `confidence_band`；新增 reason（AI 來源無 evidence、code 與 linker 分歧、hand 分歧、未知 code、
  `return` 型 A 位置、AI 已展開成 N 個 motion、數量待指定）
  須同步 `test_contract_enum_freeze` 與 `routing._eligible_auto` 的 blocked 清單。`risk_level` 只作衍生顯示。
  - **已定案的六個 reason 名稱**（2026-11-22，S3 PR-A；皆在 `routing.ROUTING_REASONS` 與 `_eligible_auto` blocked）：
    `ai_source_no_evidence`（AI 來源無 evidence）、`ai_unknown_code`（未知 code）、`ai_return_a_position`（`return` 型 A 位置）、
    `ai_hand_hint_mismatch`（hand 分歧）、`ai_addon_truncated`（compile 一次只能掛一個 P addon，預覽只用第一個）、
    `ai_candidate_preview`（該 draft 是用候選算的預覽，`chosen` 仍空；經 draft.issues 進 routing reasons）。
  - **延後到 S4**：「code 與 linker 分歧」「AI 已展開成 N 個 motion」「數量待指定」三個 reason，與 D3 的 linker 比對同時做，第一版不新增。
  - **審核落點（2026-11-23，ADR-038 追記）**：審核佇列的落點是 [ADR-038](ADR-038-unified-wi-workspace-and-two-stage-distance.md) 的工作區編輯區（D3）；不再提供「採用到編輯器」捷徑。
  - **legacy slots 待決事項已關閉（2026-11-23，ADR-038 追記）**：實作計畫「路由開放前置條件」中 legacy slots 在首次與重播不一致的待決事項，由 ADR-038 D3 關閉（AI 結果不使用 legacy 相容欄位）。
  - **`ai_candidate_preview` 保留為 routing reason**（Howard 2026-11-22 裁決）：`CycleDraft` 沒有可放旗標的欄位，另加欄位會改到既有 rule 路徑的輸出，所以用 reason 表達「這份是預覽、不是決定」。
- 人工修改在 plan 層操作，改完由 MOST 重跑 link → compile → engine_gate，**不重新呼叫 ai_service**。
  首輪只做最小編輯：`set_slot`、`set_distance`、`set_quantity`（後兩者寫 D3 的出處欄位）。
  `set_slot` 的值不合 rule-set 或引擎範圍時，該項不可接受。拆分、合併等其他編輯延後。

### D5 首輪只落盤到 worksheet；走既有儲存路徑

（Howard 2026-11-14 裁決：採用後帶回編輯器；首輪只做 worksheet）

- **目標**：首輪只支援 worksheet（`wi_rows`／`most_cycles`）。motion_module 沒有 revision 欄位、建新版不比對基準版本，
  樂觀鎖與 stale 判定不成立，延後另開 ADR（屆時以 `current_version` 定義 CAS）。
  因此 MOST 工作台（workbench-v3，建在 motion_module 上）的 AI 單句也延後；首輪的單句入口在工時表編輯情境。
- **採用流程**：
  1. 審核服務在採用當下比對審核項的 `source_revision` 與 worksheet 目前 revision，以及審核項引用的列是否被改動或刪除；
     有變動即轉 `stale`，不允許直接採用。
  2. 前端把 N 個 motion 以 N 列**追加到表尾**（首輪不支援插入中間，避免打斷 level 鏈），level 欄留空，由人事後標註。
  3. 走既有 `save_worksheet` 落盤，帶 `base_revision` 做 compare-and-increment（ADR-027 §2）。
     409 時先重跑下列 stale 條件：成立才轉 `stale`，由人看差異後重新確認；不成立則前端重新載入 worksheet、以新的 `base_revision` 重送，
     審核項維持 pending。**不自動 rebase**。
  4. 審核項的 `accepted` 狀態與 `committed_wi_row_ids` 在 save 成功的**同一交易**內設定；追加後未存檔就離開，審核項維持 pending。
- **provenance**：`WiRowSaveIn` 以加法新增可選的 `review_item_id`。伺服器驗證該審核項屬於此 worksheet 與此使用者後，
  由伺服器設 provenance 為 `ai_external`；前端不得直接傳 provenance。`wi_rows.provenance` 的 CHECK 以加法 migration 擴充，downgrade 處理已有新值的列。
  審核項記錄每個落盤列的內容雜湊；之後的存檔中，`wi_row_id` 在 `committed_wi_row_ids` 內且雜湊未變的列，由伺服器維持 `ai_external`。
  （存檔是整份取代，不能靠 `updated_at` 判斷；同一雜湊也用於下列「引用列被改動」的判定。）
  > **2026-11-23，W1，Howard 核可（W1 追記，ADR-038）**：
  > - **整份存檔保留既有列來源的規則改為列 id 比對**：存檔時列 id 沿用的列，保留原 `provenance`、`source_import_id`、`source_module_id`、`source_module_version`；新 id 的列為 `manual`。**不再以「內容雜湊未變」判斷是否維持 `ai_external`**（上一段後半的雜湊條件由本條取代）。
  >   列是否被人改過（供 stale 判定「引用列被改動」）由 W3 另記內容雜湊處理，不靠 provenance。
  >   後果：人改過內容的 AI 列仍標 `ai_external`（過度標示，方向安全）。
  > - **「採用流程」的落盤入口由 ADR-038 的 `POST /worksheets/{id}/drafts/commit` 取代**（上面第 2、3 步的前端追加＋`save_worksheet`）。該入口仍共用 save 的元件：revision CAS、`compute_rows_for_save`、`persist_computed_rows`、`finalize_content_change`，沒有第二套計算或寫入。
  > - **外部 AI 草稿（`source='ai_service'`）在 W3 補上 engine_gate 檢查前，寫入時 Fail-Fast 拒絕**（409，`field=source`）。
  > **2026-11-24，W3，依審查建議，Howard 授權（W3 追記，ADR-038 D3）**：
  > - **W1 追記的「外部 AI 草稿在 W3 補上 engine_gate 檢查前 Fail-Fast 拒絕」已移除**，由上列 D3 的 W3 追記取代。
  > - **stale 條件在草稿層實作兩個**：工時表 `default_rule_set_id` 改變（`rule_set_changed`）、來源 Excel 列 `input_hash` 改變或被刪（`import_row_changed`）→ 409 `DRAFT_STALE`，整筆寫入作廢，草稿退回 pending 並記 `stale_reason`。「引用列被改動」不適用（草稿追加表尾）。
  > - **provenance**：`ai_service` → `ai_external`；來自 Excel 列的 `rule_based` 草稿 → `imported`（帶 `source_import_id`）；其餘照 W1。
  > - Excel 批量的外部 AI 與 D6 的 Excel 數量權威延後到 W3b（見 [交付計畫](../roadmap/adr-038-delivery-plan.md)）。
- 一句 N 個 motion → N 列 WiRow＋N 個 cycle（`most_cycle.wi_row_id` 1:1 不變）。審核項的落盤參照存 `wi_row_id` 陣列（cycle id 每次存檔重建，不可作參照）。
- **TMU**：審核預覽與落盤都用 `compute_rows_for_save` 與目標 worksheet 的 rule-set；審核畫面的值標為預覽，以落盤結果為準。
- **stale 條件**：目標 worksheet 的 `default_rule_set_id` 改變；process_version 非 draft；目標被刪除；
  `source_input_hash` 改變；審核項引用的列被改動（內容雜湊不同）或刪除。一般的存檔（revision 遞增但未動到引用列）不觸發 stale。clone 不搬移審核項。
- **wi_group**：同一句拆出的 N 列共用同一 wi_group。來源依序為 Excel 欄、使用者輸入、該句原文；
  超過 `WiRowSaveIn.wi_group` 上限（200 字）時截斷並標示，與現行 `AiDraftPanel` 的預設規則統一。
  > 2026-11-24，W4，依審查建議，Howard 授權：`AiDraftPanel` 已於 W4 移除；截斷規則由後端 `from-sentence` 實作（`parse_snapshot.wi_group_truncated`），見 ADR-038 D3 W3／W4 追記。

### D6 Excel 批量：只送語句；數量歸屬規則

- MOST 解析 Excel，只把 `description` 欄送出；超過 `MAX_PARSE_TEXT_CHARS` 的列不外送（沿用現行標 review 規則）。
  批量與既有 `/imports/{id}/parse-jobs` 合併為同一張 job 表；超過單批上限時自動切批，單次匯入另有總列數上限。
- 時間一律由 MOST 引擎由 TMU 換算（TMU × 0.036）。Excel 的觀測工時只留在整句層級作參考（例：「引擎合計 3.2 秒，觀測 3.5 秒」），
  不分配到 motion（現行存檔本來就以引擎秒數覆蓋 `raw_seconds`，`worksheet_service.py`）。
- **數量**：Excel 數量欄為權威，以 `quantity_source=excel` 的出處進入（D3），不觸發 `quantity_unevidenced_review`。
  MOST 依序判斷歸屬並**預填**（仍逐項審核，不存在自動落盤），結果經 QuantityPolicyV2（持工具→`repeat_count`，否則→`frequency`）：
  1. 句中有數量詞且數字與 Excel 一致 → 套到 `object` 對得上被修飾物件的 motion，其餘 motion 為 1。
  2. 句中無數量詞 → 視為整句重複：預填到 `process`、`move_place` 類 motion；其他類型（如抓取）不預填，標審核由 IE 指定，
     審核畫面顯示「其餘 motion 未套用」。
     （`resolve_frequency` 只對這兩類套用整數 N；Howard 2026-11-14 裁決。）
  3. AI 已把數量展開成同物件的多個 motion（個數＝Excel 數量）→ 不自動放行，標審核並註明「AI 已展開成 N 個 motion」，
     由 IE 選擇保留展開或合併成一個 motion 加數量。（兩者 TMU 相同，但 LB task 數不同；Howard 2026-11-14 裁決。）
  4. 其他（對不到、多個候選、句中數字與 Excel 不一致）→ 不猜，標審核，由 IE 指定。

  每項結果都顯示套用依據（例「Excel 數量 2 → motion 2，依據：規則 1」），IE 可改。

  > **2026-11-24，W3b，依審查建議，Howard 授權（D6 數量落地，ADR-038 W3b）**：
  > - 落在草稿層 `apply_excel_quantity`：預填草稿的 `frequency`，`parse_snapshot.quantity` 記 `excel`（Excel 值）、`rule`（1–4）、`applied`、`reason`；草稿仍為 pending，畫面顯示依據，IE 可改。出處記在 `parse_snapshot`，不用 `quantity_source` 欄。
  > - 規則判斷順序與細節：規則 3（同物件且同動作類型的 motion 剛好 N 個）排在規則 1 之前，否則展開成 N 個 motion 後再各乘 N 會變 N²。規則 1 的被修飾物件＝數量詞後 4 字內、遇標點停；「次」與「x N」是重複次數，不綁物件，走規則 4。句中有 `extract_counts` 認不得的「數字＋量詞」（例「三支」「12 pcs」）走規則 4。Excel＝1 但句中數字不是 1 走規則 4。Excel 非正整數或 > 10000 走規則 4。
  > - **決定：持工具時暫不走 `repeat_count`（QuantityPolicyV2），一律預填 `frequency`**。TMU 中性；LB 投影的形狀差異（`repeat_count` 與 `frequency`）留待後續。上方「持工具→`repeat_count`」的路徑在草稿層暫未啟用。
  > - 與 `import_service.submit` 對無效數量的處理不同：submit 把 ≤0 設 1、接受 2.5；草稿層一律標規則 4 交 IE。W5 讓整份上傳改走編輯區後，兩者自然統一。

### D7 RBAC、服務間認證與資料外送

**角色**（以程式為準：`viewer < analyst < approver < admin`，`auth/deps.py`）

| 動作 | 最低角色 |
|---|---|
| 觸發 AI 解析（單句、批量） | analyst（viewer 只走 `rule_based`，不外送）。單句是「依角色分流」（既有 `POST /worksheets/nl-draft`，viewer 得 200＋`rule_based`）；批量是「拒絕」（`require_role("analyst")`，viewer 得 403）（2026-11-22 追記，Howard 核可） |
| 看審核佇列與項目（含原文） | analyst（viewer 只看彙總計數）；列表依 `site_ids` 與 owner 過濾 |
| 逐項接受、人工修改 | analyst；落盤另受既有 service 的守衛 |
| 重設他人已決項目 | approver（須填理由） |
| 啟用／停用整合 | admin |

**服務間認證**
- **服務金鑰是 ai_service 唯一的授權依據**；身分相關 header 只作稽核與範圍標記，ai_service 不得依其授權。
- MOST 不送員工編號（Howard 2026-11-14 裁決）：以服務身分呼叫，使用者歸屬由 MOST 自己的稽核紀錄以 `run_id` 對帳。
- 網路層只允許 MOST 連到 ai_service（防火牆或內部網路），比照 ADR-036 的內網限制。
- `most` 金鑰最小權限（不得轉換 bundle 狀態）是**上線前置條件**。金鑰支援新舊並存以便輪替，輪替事件入稽核。

**base URL 與 SSRF**
- base URL 由部署層環境變數固定，不提供 UI 或 API 修改。
- 啟動時驗證：host 在 allow-list 內；DNS 解析後的 IP 屬預期的私網範圍（擋 link-local 與雲端 metadata 位址）。
  每次連線時再檢查實際連線的 IP（或釘住啟動時解析的 IP），防 DNS 重新綁定。不跟隨 redirect；httpx 設 `trust_env=False`（不吃環境 proxy）。
- 預設要求 TLS；僅限私網位址的明文 http 須在部署設定明確宣告例外。
- 驗證失敗即整合停用並記錄，不影響其他功能。

**金鑰處理**
- 金鑰只放 env／secret，啟動時檢查最小長度，設定物件用遮蔽型別（不出現在 `repr(settings)`）；不入 log、DB、錯誤信封、provenance、`/wi-ai/status`。
- client 統一遮蔽請求 header，並有測試：故意讓請求失敗，斷言錯誤信封與 log 不含金鑰。

**外送範圍**
- 只送 WI 語句與白名單內的 context 欄位。首輪白名單只有 `source_lang`；其他 context（例如可用工具、前一列摘要）要加入須修訂本 ADR。
  fake server 以測試鎖定請求 body 的 keys。不送 Excel 其他欄。
- ai_service 的 `error.message` 不原樣轉給前端，只用映射後的 MOST 錯誤碼與訊息。
- ai_service 轉送的 LLM provider 是否出內網、是否保存請求內容，須由 ai_service 說明（實作計畫 §7）。

**背景 worker 與稽核**
- worker 每次出站前從 DB 重新檢查提交者仍 active 且角色 ≥ analyst，否則該 job 標 cancelled 並記稽核。job 記 acting user id，不快取角色。
  > **2026-11-24，W3b，依審查建議，Howard 授權（D7 批次執行時降權，ADR-038 W3b）**：實作為執行時降級。`tick_job` 判斷是否外送＝整合可用，且 job 建立者目前仍是 active、角色 ≥ analyst；建立者被降權（或停用）後，該 job 剩餘列以 `rule_based` 完成，不外送。建立 job 時角色不足仍是 403。只送 `description`，Excel 手別只用於 MOST 端比對（不外送）。降級原因記在 `item.last_error.ai`（維運類原因不帶 code）。
  > 外部路徑一次只認領一列，所以每列都重新判斷；日後若改成一次認領多列，必須改為逐列判斷。
- 每次外送由 MOST 產生 request id 並隨請求送出，與 ai_service 回傳的 `run_id` 一併記錄，供兩邊對帳。
- **（最終型態；v1 過渡做法見下方「外送稽核的 v1 過渡做法」，2026-11-22 追記）** 稽核事件 append-only（無刪改 API，資料庫角色不授予 UPDATE／DELETE），actor 一律取自 `CurrentUser`：外送（誰、何時、bundle、筆數、request id、`run_id`，不記原文）、
  accept、commit、重設、整合啟用／停用、金鑰輪替。
- **同句合併（D8 single-flight）的稽核（2026-11-20 追記，Howard 核可）**：合併的等待者沒有自己的外送，其 provenance 不帶 `run_id`、`request_id`，改記 `shared_run_id`（指向領頭者那次外送的 `run_id`）。稽核「外送」事件的筆數只計真的外送的請求，等待者不算一次外送。S3 落盤 `ai_parse_runs` 時，必須能處理「無 `run_id`、有 `shared_run_id`」的結果。
- **外送稽核的 v1 過渡做法（2026-11-22 追記，Howard 核可）**：
  - v1 **不做**稽核「外送」事件：不新增 `workflow_audit_log` 事件類型，不加 migration。
  - v1 的外送紀錄就是 `ai_parse_runs`：`created_by`、`created_at`、`provenance` 內的 bundle、`request_id`、`run_id`、`upstream_run_id`。
  - 失敗的外送，MOST 送出的 `request_id` 要寫進該 run 的 `error`（只寫 DB，不回前端），涵蓋兩種情況：ai_service 回 failed；ai_service 已回應但 MOST 端降級（空結果、bundle 不符、plan／provenance 建不起來）。
  - 正式的稽核事件，以及上一條原文的「資料庫角色不授予 UPDATE／DELETE」，留給未來的統一平台（整合 MOST、LB、DES；RBAC／ABAC 將於該平台重新設計）。
  - 已知且接受的後果：(1) `ai_parse_runs` 在 DB 層沒有不可修改保護；(2) 外部呼叫前沒有持久紀錄，程序在呼叫途中崩潰就沒有外送紀錄；(3) 稽核查詢維持 approver 以上（既有 `GET /audit-log`）。
  - 上方「同句合併」那條的「稽核『外送』事件的筆數」，v1 對應為「`ai_parse_runs` 中帶 `run_id` 的 run 數」。
- **provenance 鍵 allow-list（2026-11-22 追記，Howard 核可）**：`ai_parse_runs.provenance` 與回應的 `provenance` 只允許 `ai_integration/provenance.py` 列的鍵（ai_service 出處的 13 個鍵，加 MOST 自己的 `motion_labels`、`dropped`）。每次寫入前都驗證，驗證失敗屬降級（走 rule_based），不寫入。

**輸出安全**
- 前端以純文字渲染 AI 文字欄位。匯出 Excel／CSV 時，以 `=`、`+`、`-`、`@`、Tab、CR 開頭的字串加以轉義，Excel 儲存格設為文字型別，防 formula injection。
- `GET /wi-ai/status` 只回啟用與可用狀態（viewer 可見），不含金鑰、內部 URL 與 bundle 細節。

### D8 並行、逾時、背壓與成本

- 單句用 ai_service 的 `lane=interactive`，批量用 `lane=batch`，兩者各有並行上限，批量不得卡住單句。
- 呼叫 ai_service 期間不占用 DB session／連線。外部路徑（2026-11-22 追記，Howard 核可）在呼叫前 `session.commit()` 以釋放連線；呼叫端須無未提交寫入（起始時檢查，有就 `RuntimeError`）。已 flush 但未提交的寫入無法偵測，靠呼叫端遵守。
- **持久快取鍵（2026-11-22 追記，Howard 核可）**：外部路徑的 `ai_parse_runs` 快取鍵由佔位 bundle、設定的 ai_service bundle code、`known_hand`、worksheet revision、正規化語句、context、rule-set 組成。命中時不呼叫 ai_service、不扣額度。呼叫後回應的 `bundle_code` 須與設定一致，不一致即降級。下方 single-flight 的在途請求合併語意不變。
  > **2026-11-24，W3b，依審查建議，Howard 授權（D8 快取鍵與批次額度，ADR-038 W3b）**：
  > - 快取鍵加入 `source_kind`：單句（`interactive`）與整份上傳（`import_row`）不共用快取。
  > - 已知限制：批次與單句共用建立者的每分鐘額度（30）與全站每日額度；額度用完的列降級為 `rule_based`，不自動重試。guard 的額度是行程內記憶體，API 與 worker 行程各自計算。取消只在每列開頭檢查（外部呼叫中的那一列會做完）。
  > - 整份上傳走路徑 A（`lane=batch`，逐句呼叫）。路徑 B（flow，批次端點）延後，需求見 [實作計畫](../roadmap/ai-service-integration-plan.md) 「路徑 B（延後）」。
- 相同請求的併發合併為一次（single-flight）。語意（2026-11-20 追記，Howard 核可；實作 `ai_integration/guard.py`）：
  - key＝(bundle、scope、語言、lane、sha256(allow-list、context、語句))。這**不是** `ai_parse_runs.input_hash`；持久快取仍歸 S3 的 `ai_parse_runs`。
  - 只合併在途請求，完成後不快取。
  - 領頭者自己的處境不共用：並行等不到許可、配額被拒、被取消、內層例外。等待者自己重來，可能成為新領頭者並實際外送，屆時扣自己的配額。
  - 領頭者真的外送後的上游失敗（含逾時、5xx）仍共用給等待者，避免對壞掉的上游放大請求。
  - 並行等待上限 `acquire_timeout_s`（預設 10 秒）只約束「等並行許可」的時間：從請求進來起算，等待者重來時用剩餘時間；等不到即 `QUOTA_EXCEEDED`。同一個 key 的重試鏈不會把等許可的時間疊加。
  - 等待者等的是領頭者實際外送的時間，不受 `acquire_timeout_s` 約束。這段時間以領頭者的等許可上限（`acquire_timeout_s`）加 client 總時限為界，所以不會無限等待。
  - 合併的等待者不扣自己 actor 的每人／每日配額，因為沒有新的外送。已超過每分鐘上限的使用者，若語句與同 scope 內在途請求完全相同，仍可拿到結果。結果只含同 scope、同語句、同 allow-list 與 context 的內容（都在 key 內），沒有跨使用者的資料洩漏。
  - 超長語句（> `MAX_PARSE_TEXT_CHARS`）不會外送（D6）：由 MOST 端守門自己回 `failed`（`text_too_long_not_sent`），不佔並行許可、不扣配額，也不依賴內層 parser 自己擋。
  - 等待者的 provenance 與稽核處理見 D7。
- **計數口徑與範圍（2026-11-20 追記，Howard 核可）**：
  - 預算與每人配額以「MOST 送進內層 parser 的請求數」計，不含 client 對 429／5xx 的重試，因此對 ai_service 的實際 HTTP 次數最多約 3 倍（1 次加最多 2 次重試）。合併的等待者不計。
  - v1 的「每日」＝UTC 日；日界線只往後重置，牆上時鐘被往回撥不會重置當日預算。每人每分鐘視窗用單調時鐘，不受校時影響。actor 以 `strip` 加 `casefold` 正規化後計，大小寫或前後空白不同不會各拿一份額度。所有計數在 MOST 單程序記憶體內，重啟歸零。多 worker 時預算會乘上 worker 數，共用計數留 S5。
  - 並行 16、每人每分鐘 600、每日 1,000,000 是設定的實作護欄上限（只防設定打錯），不是本 ADR 的決定數字；超出即視為設定不合法。
  - **待辦（已延後，見 [BL-ENG-15](../BACKLOG.md)；Howard 2026-11-20：使用者少，先讓功能打通）**：日界線改按廠區時區（有國外工廠，不能只用 UTC+8 或 UTC）；預算是否也按廠區分開，一併決定。
  - **待辦（已延後，見 [BL-ENG-16](../BACKLOG.md)；Howard 2026-11-20：使用者少，先讓功能打通）**：每日預算是全域一份，每人只有每分鐘上限，單一已認證使用者持續送出即可用光全站當日額度。
- 保守預設值先行（暫定，量測後調整）：

  | 項目 | 預設 |
  |---|---|
  | 並行（interactive／batch） | 2／1 |
  | 每人每分鐘請求 | 30 |
  | 每日請求預算（超過即停並降級） | 2000（2026-11-23 改為 10,000，ADR-038 D7；程式預設值另以小 PR 更新） |
  | 單次匯入列數 | 沿用現行上限 1000 |
  | 每句 motion 數 | 20 |
  | 自由文字欄位長度 | 200 字 |
  | 回應大小 | 256 KB |
  | 重試 | 最多 2 次，指數退避加抖動；只重試 429／5xx；逾時不重試（ai_service 端已有重試，避免重複計費）；熔斷開啟時不重試 |

### D9 啟用順序與前置條件

- `DDM_AI_SERVICE_ENABLED` 預設 False，需 admin 於部署設定開啟。
- 舊 LLM 路徑在正式環境是死碼（預設關閉），清理先於新路徑進行（Howard 2026-11-14 同意提前）。
- 開放給使用者前須滿足：ADR-033 P3 已落地；已對真 ai_service 量測 30 句延遲分布（需 poc003 bundle 已轉 shadow），並據此定逾時與並行參數；
  `most` 金鑰最小權限已確認；ai_service 確認不依身分 header 授權；ai_service 說明 LLM provider 是否出內網、是否保存請求內容。

## 3. 考慮過的選項

- **要求 ai_service 改回只給角色片語（ADR-033 D2 原樣）**：權威最集中，但要等 ai_service 改 schema 並重做 eval；
  而審核與引擎驗證都在 MOST，接受 code 作候選的風險可控。未採用，留作日後選項。
- **審核佇列直接落盤**：少一步操作，但會出現第二條寫 `wi_rows`／`most_cycles` 的路徑，繞過既有守衛與 revision 鎖。未採用。
- **批次接受低風險項目**：省審核時間，但違反 ADR-026 §3，且風險判斷沒有 eval 基準（poc003 slot code 一致率約 0.81 只是診斷值）。未採用。
- **首輪同時支援 motion_module**：工作台可同步受益，但 motion_module 沒有版本比對，需先補樂觀鎖。未採用，延後另案。
- **砍掉 parse_job／outbox／ai_review 重做**：較乾淨，但現有基礎設施已有 lease、input_hash、稽核事件與測試。未採用，改為重用並改造。

## 4. 後果

- 好處：MOST 不再維護 prompt 與 provider；LLM 換模型或改 prompt 不影響 MOST 發版；TMU 權威不變；注入式輸入最壞只能產生需人工審核的合法建議。
- 代價：
  - MOST 依賴另一個服務的可用性與契約穩定（以 port、fake、降級控制）。
  - rule-set 改版後，ai_service bundle 內的 code 清單要另行更新（需 ai_service 提供同步機制）。
  - ADR-033 P3 成為前置，動到 TMU 路徑。
  - MOST 工作台的 AI 單句延後。

## 5. 不由本 ADR 決定

- parse job 執行模型（呼叫移出鎖、lease 心跳、退避、idempotency）：批量階段另開 ADR，核可或取代 ADR-030。
- motion_module 作為落盤目標（含工作台 AI 單句）：另開 ADR。
- 人工修改資料回傳 ai_service（回饋通道）：等 ai_service 提供接收接口與契約再議；首輪只在 MOST 內落地紀錄。
- `ai_parse_runs` 原文保留期限、`ai_feedback_candidates`／`ai_deployment_bundles` 的去留：另案。

## 6. 對既有文件的影響（本 ADR 核可後由 most-doc-sync 回寫）

| 文件 | 影響 |
|---|---|
| ADR-033 | 檔頭加 Amends：D2「slot 由 SlotLinker 對映」改為本 ADR D3；prompt 與 `llm_planner` 呼叫部分作廢；D1／D6／D7 保留為入站不變量；D3–D5 的索取內容改為對 ai_service 的契約需求；寫明 P3 為前置 |
| ADR-026 | 補註：§1 的 `wi-ai-api` 即 ai_service；§3 維持 |
| ADR-027 | 補註：§7 觸發由本 ADR 宣告成立 |
| ADR-025 | 補 D11：AI 建議的逐項採用發生在 submit 之外，經 D5 的既有儲存路徑；批量 submit 的 `ai_adoptions` |
| ADR-035 D4 | 補註：Excel 數量以 `quantity_source=excel` 出處進入 QuantityPolicyV2 |
| ADR-030 | 批量階段的新 ADR 核可或取代 |
| `docs/agent-team/domains.yaml` | nlp-compiler 的 docs、paths、invariants；wi-workbench 的 provenance 與落盤 invariant；excel-import 的批量 AI invariant；auth-rbac 的角色名改為程式現況 |
| `docs/architecture/rbac-spec.md`、`data-model-and-storage-spec.md` | 權限矩陣加 `/wi-ai/*`；`wi_rows.provenance` 值域與 AI 採用路徑 |

## 7. 裁決紀錄（Howard，2026-11-14）

| 題 | 裁決 |
|---|---|
| slot code 的處理 | (a) 接受作候選，MOST 驗證；`hand`／`seq_kind` 不採信 → D3 |
| ADR 取號 037 並宣告 ADR-027 §7 觸發 | 同意 → D1 |
| 批次接受低風險 | 移除 → D4 |
| 落盤方式 | 帶回編輯器，走既有儲存路徑 → D5 |
| 首輪落盤目標 | 只做 worksheet，motion_module 延後 → D5 |
| AI 外送的最低角色 | analyst；viewer 只走 rule_based → D7 |
| 員工編號是否外送 | 不送，改用服務身分 → D7 |
| 首輪範圍 | 縮小：單句、逐項審核、最小編輯、逐句批量、降級 → D4、實作計畫 |
| 舊 LLM 清理提前 | 同意 → D9 |
| Excel 數量、wi_group、觀測工時 | 數量依 D6 四條規則（規則 2 只自動套用 process／move_place；規則 3 標審核由 IE 選）；wi_group Excel 優先；時間由引擎算 → D5、D6 |
| 先量測真服務延遲 | 同意 → D9 |
| 新開關名稱 | `DDM_AI_SERVICE_ENABLED`，不沿用舊名 → D2 |
