# ADR-037：WI AI Parser 改接外部 ai_service——MOST 只保留確定性管線與審核

## 狀態

🟡 **proposed**（2026-11-14 起草）。本 ADR 的取捨已於 2026-11-14 由 Howard 在對話中逐項裁決（見 §7），
全文仍待 Howard 核可後改為 accepted。核可前不得依本 ADR 改程式，也不得回寫其他權威文件（影響清單見 §6）。

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
- 新開關命名為 `DDM_AI_SERVICE_ENABLED`，不沿用 `DDM_WI_AI_ENABLED`，避免舊環境的 `true` 在新路徑完成前意外啟用。

### D3 ai_service 選的 slot code 只當候選（修訂 ADR-033 D2）

（Howard 2026-11-14 裁決選 (a)）

**入站形狀**
- mapper 對回應做欄位 allow-list，未知欄位丟棄不透傳；每句 motion 數與自由文字欄位（`object`、`sub_activity`）長度設上限。
- slot code 進 plan 時放在**新增的候選欄位**（帶來源＝`ai_service`），不直接填 `SlotCandidateSet.chosen`，不繞過 linker。
- MOST 仍以確定性 linker 對該句產生自己的候選。兩者一致 → 採用；不一致或 linker 無結果 → 以 ai_service 的 code 為候選，
  新增 routing reason 標審核，**不得自動採用**。未知 code（不在目標 rule-set）一律拒收並標審核。
- ai_service 的回應沒有 evidence span，ADR-033 D3 的字面子字串不變式在此路徑不適用；因此此路徑的 motion 一律經人工採用（D4），
  不存在自動落盤。
- `return` 型 A 位置在 compile 尚無對應分支：mapper 保留語意並標審核，不臆測格位。

**驗證**
- 候選 code 必須通過：存在於**目標 worksheet 的 rule-set**（`default_rule_set_id`，不是「當前 active」）→ compile → engine_gate。
- **可接受的 motion**：plan 完整（`complete=True`）、`compute_cycle` 通過、engine_gate 無 high 級問題。其餘只能人工補齊並重驗後才可接受。

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
  `return` 型 A 位置、AI 已展開成 N 個 motion、數量待指定；名稱於單句階段定案）
  須同步 `test_contract_enum_freeze` 與 `routing._eligible_auto` 的 blocked 清單。`risk_level` 只作衍生顯示。
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
- 一句 N 個 motion → N 列 WiRow＋N 個 cycle（`most_cycle.wi_row_id` 1:1 不變）。審核項的落盤參照存 `wi_row_id` 陣列（cycle id 每次存檔重建，不可作參照）。
- **TMU**：審核預覽與落盤都用 `compute_rows_for_save` 與目標 worksheet 的 rule-set；審核畫面的值標為預覽，以落盤結果為準。
- **stale 條件**：目標 worksheet 的 `default_rule_set_id` 改變；process_version 非 draft；目標被刪除；
  `source_input_hash` 改變；審核項引用的列被改動（內容雜湊不同）或刪除。一般的存檔（revision 遞增但未動到引用列）不觸發 stale。clone 不搬移審核項。
- **wi_group**：同一句拆出的 N 列共用同一 wi_group。來源依序為 Excel 欄、使用者輸入、該句原文；
  超過 `WiRowSaveIn.wi_group` 上限（200 字）時截斷並標示，與現行 `AiDraftPanel` 的預設規則統一。

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

### D7 RBAC、服務間認證與資料外送

**角色**（以程式為準：`viewer < analyst < approver < admin`，`auth/deps.py`）

| 動作 | 最低角色 |
|---|---|
| 觸發 AI 解析（單句、批量） | analyst（viewer 只走 `rule_based`，不外送） |
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
- 每次外送由 MOST 產生 request id 並隨請求送出，與 ai_service 回傳的 `run_id` 一併記錄，供兩邊對帳。
- 稽核事件 append-only（無刪改 API，資料庫角色不授予 UPDATE／DELETE），actor 一律取自 `CurrentUser`：外送（誰、何時、bundle、筆數、request id、`run_id`，不記原文）、
  accept、commit、重設、整合啟用／停用、金鑰輪替。

**輸出安全**
- 前端以純文字渲染 AI 文字欄位。匯出 Excel／CSV 時，以 `=`、`+`、`-`、`@`、Tab、CR 開頭的字串加以轉義，Excel 儲存格設為文字型別，防 formula injection。
- `GET /wi-ai/status` 只回啟用與可用狀態（viewer 可見），不含金鑰、內部 URL 與 bundle 細節。

### D8 並行、逾時、背壓與成本

- 單句用 ai_service 的 `lane=interactive`，批量用 `lane=batch`，兩者各有並行上限，批量不得卡住單句。
- 呼叫 ai_service 期間不占用 DB session／連線。
- 同一 `input_hash` 的併發請求合併為一次（single-flight），key 含 bundle 與 site 範圍。
- 保守預設值先行（暫定，量測後調整）：

  | 項目 | 預設 |
  |---|---|
  | 並行（interactive／batch） | 2／1 |
  | 每人每分鐘請求 | 30 |
  | 每日請求預算（超過即停並降級） | 2000 |
  | 單次匯入列數 | 沿用現行上限 1000 |
  | 每句 motion 數 | 20 |
  | 自由文字欄位長度 | 200 字 |
  | 回應大小 | 256 KB |
  | 重試 | 最多 2 次，指數退避加抖動；熔斷開啟時不重試 |

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
| `docs/agent-team/domains.yaml` | nlp-compiler 的 docs、paths、invariants；wi-workbench 的 provenance invariant；auth-rbac 的角色名改為程式現況 |
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
