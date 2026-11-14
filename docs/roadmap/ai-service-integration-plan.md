# MOST ↔ ai_service 整合與舊 LLM 清理：實作計畫

**文件類型：** Roadmap / 執行分期（非核心規則權威）
**版本：** 0.2 — 計畫草案（納入 2026-11-14 第二輪審查與裁決）
**建立日期：** 2026-11-14
**決策邊界：** [ADR-037](../decisions/ADR-037-ai-service-integration.md)（accepted 2026-11-14）
**既有行為：** [ADR-025](../decisions/ADR-025-import-template-matching-p2.md)、[ADR-026](../decisions/ADR-026-wi-ai-parser-pipeline-boundary.md)、[ADR-033](../decisions/ADR-033-llm-planner-scope-narrowing.md)

## 狀態

✅ 已核可、待啟動（ADR-037 於 2026-11-14 核可；S0 文件回寫已完成）。與 ADR-037 衝突時以 ADR-037 為準。

> 來源：MOST 與 ai_service 兩邊的唯讀盤點、架構規劃，以及兩輪審查（架構、資安、code、nlp-compiler、wi-workbench、excel-import、auth-rbac）。
> 本文件中「ADR-033 P3」指 ADR-033 遷移路徑的第 3 階段；本計畫自己的階段寫作 S0–S5，避免撞名。

## 1. 階段總覽

每個階段都可以單獨 merge 和回滾，預設開關關閉，且都要過 [checkpoint](../agent-team/checkpoint.md)。
動到 `most_compiler`／rule-set／level 時前後都跑 `scripts/core_logic/run_all.py`；unit 與 integration 分開跑；
動到 agent 設定跑 `scripts/agent_team/check_agent_config.py`；改 docs 跑 `scripts/docs_check.py`；改程式跑 `graphify update .`。

| 階段 | 內容 | 使用者可見 | 依賴 ai_service |
|---|---|---|---|
| S0 | ADR-037 核可；回寫 ADR-033／026／027／025／035、domains.yaml、rbac-spec、data-model spec | 否 | 否 |
| S1 | 移除 MOST 內舊 LLM 路徑；確定性元件搬家 | 否（正式環境本來就關） | 否 |
| S2 | `WiParserPort`、`AiServiceClient`、mapper、fake server、契約測試 | 否 | 否（只用 fake） |
| S3 | ADR-033 P3；單句路徑接上（工時表編輯情境，開關後） | 是 | 是（已實作的 `structured-completion`） |
| S4 | 審核佇列、逐項審核、最小編輯、經編輯器落盤到 worksheet | 是 | 否 |
| S5 | Excel 批量（併入既有 parse-jobs） | 是 | 是（逐句；flow 落地後換 adapter） |
| 延後 | motion_module 落盤（含工作台 AI）、回饋通道、flow／job adapter、拆分／合併編輯 | — | 部分 |

## 2. S1：移除舊 LLM 路徑

舊路徑由 `DDM_WI_AI_ENABLED` 控制，正式環境預設關閉、compose 沒有傳 `DDM_LLM_*`。移除後 `nl-draft` 的行為與正式環境現況相同（`rule_based`）。

**先搬家（同一個 PR 內完成，S2 才有防腐層可用）**

| 元件 | 現址 | 新址（建議） |
|---|---|---|
| `_parse_sanitize_validate`、`_sequence_orders_contiguous` | `nlp/llm_planner.py` | `nlp/inbound_guard.py` |
| `PlannerRequest`（索取契約）與其守衛 | `nlp/prompts/plan_v2_schema.py` | `nlp/plan_request.py`（S2 再決定是否移入 `ai_integration/`） |
| `PlannerError` | `nlp/planner_ports.py` | 原地保留（`planner_eval.py` 引用） |
| `TestEnglishParsingIntegration`（測 `rule_plan_adapter._detect_language`） | `tests/unit/test_english_parsing.py` | tests/unit 下的新測試檔（例：test_rule_plan_language） |

`docs/CI_GATES.md` 的靜態掃描「定義站」放行清單隨新檔名同步。

**刪除**

- `nlp/llm_client.py`、`nlp/prompts/*`（`plan_v2_schema.py` 已先搬走）
- `nlp/planner_ports.py` 的 `LLMClientPort`／`LLMRawResponse`；`nlp/llm_planner.py` 的 `LLMPlannerAdapter`（防腐函式已搬走後整檔刪除）
- `wi_ai_service.py` 內的舊路徑：`_build_llm_client`、`_try_llm_plan`、`_plan_from_planner_output`、
  `from ddm_v2.nlp.prompts import plan_v1` 與 `plan_v1.PROMPT_VERSION`
- `settings.py` 的 `llm_*`；`wi_ai_enabled` 刪除（S3 新增 `ai_service_enabled`，env 名 `DDM_AI_SERVICE_ENABLED`）
- `scripts/test_english_most_parsing.py`；`scripts/wi_ai_eval.py` 的 `--planner llm`、`OpenAICompatClient` 與 `settings.llm_*` 用法（含檔頭說明與 `secrets` tuple）

**必須保留的讀取路徑**：`wi_ai_service` 的 provenance 與快取重播中的 `prompt_version`、`llm_raw_response`、`response_format_mode`、`usage`。
DB 欄位不動；寫入端不再產生 `kind='llm'`，但**舊 `kind='llm'` 列必須仍可讀取與重播**，以 integration 測試釘住。

**保留不動**：`most_compiler/*`、`policies.resolve_multiplier`、`engine_gate`、`nlp/{linking,lexicon,quantities,normalization,routing,rule_based,rule_plan_adapter,gold_eval,contracts}`、
`planner_eval` 的脫敏函式（`_redact_urls`、`_redact_secrets`、`_sanitize_rejected_raw`、`sanitize_stripped_value`）與 `planner_preannotation_origin`、
`parse_job`／worker、`ai_parse_runs`、`ai_review_events`、outbox。`nlp/prompts/language_aware.detect_language` 只被舊路徑使用，可刪。

**測試**

| 處置 | 檔案 |
|---|---|
| 刪除 | `tests/unit/test_llm_planner.py`、`test_prompt_few_shots.py`（few-shot 內容先轉成 gold 資產或移交 ai_service；它也是 `docs/CI_GATES.md` 第 188 行附近「對外列舉契約凍結」的守衛之一，刪檔前先確認 `test_contract_enum_freeze.py` 已涵蓋 `FROZEN_DEPENDENCY_TYPE`、`FROZEN_ROLE_KEYS`，未涵蓋就搬過去，並更新 CI_GATES 的檔案欄）、`test_english_parsing.py`（rule_based 部分已搬走） |
| 改寫（不可刪） | `test_planner_request_schema.py`（隨 `PlannerRequest` 搬家）、`test_production_no_sanitize_observer.py`、`test_planner_eval.py`（含第 1473 行附近的 `llm_api_key` 斷言）、`test_gold_draft_isolation.py`、`test_gold_draft_schema.py`、`test_rule_plan_adapter.py`、`tests/integration/test_gold_harvest.py`、`test_wi_ai_fallback.py`（第 164、179 行的 `prompt_version` 斷言；第 188–277 行的兩個重播測試改成直接寫入舊 `kind='llm'` 列，作為「舊列可重播」的釘樁）、`test_wi_ai_l2.py` |
| 確認仍綠 | `test_gold_promotion.py`、`test_gold_harvest_recompile.py`（依賴 `plan_metrics_n` 釘值）、`test_contract_enum_freeze.py`（凍結列舉在 `tests/unit/_contract_freeze_v1.py`，**不得收窄**）、`test_wi_ai_cpu_guards.py`、`test_route_mounting.py`、`test_dsx_a3_distance_api.py` |

**文件與註解**
- `docs/CI_GATES.md`：`llm_planner`／`on_sanitize` 條目；「評測旁通道不得進生產」關卡的行為守衛 (a) 原本依賴 `_try_llm_plan`，要重新定義。
- `docs/domains/nlp-compiler.md`；`tests/unit/test_i18n_en_field_isolation.py` 第 58 行對 `prompts/` 的註解；`tests/unit/_contract_freeze_v1.py` 對 `llm_client.ResponseFormatMode` 的註解；
  `nlp/contracts.py:14,232`、`nlp/planner_eval.py:372` 的註解；前端 `features/wi-workbench/detectLanguage.ts` 對後端 `detect_language` 的鏡射說明。
- `docs/architecture/wi-ai-parser-system-spec.md` §11.2 的舊契約草案：標為被 ADR-037 取代。
- `docs/llm/**`、`docs/lb-integration/PR_DESCRIPTION.md`：屬歷史紀錄，不改內容，只在檔頭標註被 ADR-037 取代。

**完成定義**
- `grep -rE --include='*.py' "llm_client|OpenAICompatClient|LLMClientPort|nlp\.prompts|DDM_LLM_|chat/completions" src scripts tests` 無結果（`--include` 排除 `egg-info` 與 `__pycache__`）。
- CI 綠；`nl-draft` 在 `rule_based` 下的 integration 測試綠；舊 `kind='llm'` 列的讀取測試綠。
- 本機 `.env` 移除 `DDM_LLM_*`（`.env.example` 本來就沒有）。

## 3. S2：Adapter、契約、fake（無使用者面）

- 新目錄 `src/ddm_v2/ai_integration/`：
  - `ports.py`：`WiParserPort`。
  - `client.py`：httpx；逾時、重試（指數退避加抖動、限總次數）、熔斷；header 遮蔽；錯誤映射；不跟隨 redirect。
  - `mapper.py`：ADR-037 D3 的 allow-list、motion 數與文字長度上限、未知欄位丟棄、code 放候選欄位、`hand`／`seq_kind` 不採信、SIMO 欄位置 null、magnitude 只作提示且不寫 `role.value`。
  - `errors.py`、`fake.py`、`config.py`（base URL 啟動驗證：scheme、host allow-list、DNS 解析後私網檢查）。
- 設定（全部預設關）：`ai_service_enabled`、base URL（部署層固定）、金鑰（遮蔽型別，支援新舊兩把）、bundle code、`json_schema` 複本 hash、lane、
  並行與預算上限（ADR-037 D8 的保守預設）、context 白名單。
- 測試：
  - `tests/unit/ai_integration/*`：mapper 全分支、錯誤映射、熔斷狀態機、base URL 驗證（metadata 位址、redirect、非 http(s)）、金鑰遮蔽（故意失敗後斷言錯誤信封與 log 不含金鑰）。
  - fake ai_service server（放 `tests/` 下）：成功、多 motion、未知 code、未知欄位、超長文字、magnitude null、429、5xx、純文字 500、契約不符、bundle 不可跑、逾時；斷言請求 body 只含白名單 keys。
  - `tests/contract/ai_service/`：openapi.json 快照＋真服務錄製的 golden。新增 pytest marker `contract`（`pyproject.toml` 目前只註冊 unit／integration），在 `docs/CI_GATES.md` 寫明獨立執行方式，不與 unit 混跑、不連真服務。
  - 評估把 `ai_integration/mapper.py` 納入 `test_i18n_en_field_isolation.py` 的 `_en` 欄位守衛範圍。
- 錯誤碼與 zh-TW／en 訊息；`domains.yaml` nlp-compiler 的 paths 加 `ai_integration/**`、`tests/unit/ai_integration/**`、`tests/contract/ai_service/**`。
- 完成定義：adapter 對 fake 全綠；沒有任何現有路由改動；CI 綠。

## 4. S3：ADR-033 P3＋單句路徑（開關後）

**進入條件**：ADR-037 accepted；已對真 ai_service 量測 30 句延遲分布（poc003 須已轉 shadow），並據此定逾時與並行參數；`most` 金鑰最小權限已確認。

1. **ADR-033 P3 前兩項**（獨立 PR 先行）：刪 `compile.py` 的 `_role_distance_cm` 與 `x_seconds` 讀值；在 `nlp/contracts` 以加法新增帶出處的距離／數量欄位與 compile 的讀取（`a6`／CM `a0` 不在本階段，`return` 一律審核）；
   帶出處的人工數值不觸發 `*_unevidenced_review`。必過 `run_all.py`（GM=28／CM=29）與 compiler 單元測試。
2. **單句路徑**：
   - `wi_ai_service` 改用 `WiParserPort`；呼叫期間不占 DB session；single-flight（key 含 bundle 與 site）。
   - 入口在工時表編輯情境（`nl-draft` 帶 worksheet），不含 MOST 工作台（motion_module，延後）。
   - `nl-draft` 維持同步 200；AI 路徑要求 analyst，viewer 只走 `rule_based`；`ai` 區塊以加法新增 `status`、`provenance`。
   - migration（加法）：`ai_parse_runs.kind` 的 CHECK 加 `external`、新欄、`external-ai-service` 佔位 bundle（`bundle_id` NOT NULL）。downgrade 處理已存在的新值列。
   - 新 routing reason 名稱定案（AI 來源無 evidence、code 與 linker 分歧、hand 分歧、未知 code、`return` 型 A 位置、AI 已展開成 N 個 motion、數量待指定），全部列入 `routing._eligible_auto` 的 blocked，並同步 `test_contract_enum_freeze`。
   - `GET /api/v2/wi-ai/status`（不含金鑰與內部 URL）；前端顯示 AI 狀態與降級訊息。
   - 稽核：外送事件（不記原文）。
3. 測試：integration 以 fake server 驗成功與各種降級；viewer 不外送；既有 `e2e/workbench-nl-*.spec.ts` 不改仍綠。
4. 完成定義：開關開＋fake 時工時表情境可見 AI 草稿；開關關或 fake 掛掉時行為與現況一致；黃金值綠。

## 5. S4：審核佇列、逐項審核、最小編輯

- 表（加法）：
  - `ai_review_items`：`worksheet_id`、`source_revision`、`source_input_hash`、site／owner、`committed_wi_row_ids`（陣列）與各列內容雜湊、狀態、AI 建議與引擎結果快照。
  - `ai_review_revisions`：plan 層編輯歷史。
  - `wi_rows.provenance` 的 CHECK 加 `ai_external`；downgrade 處理已有新值的列。
  - 事件型別只增不減，同步 `test_contract_enum_freeze`。
- 狀態：`pending → accepted | rejected | stale`；`stale` 依 ADR-037 D5 的五個條件，由採用端點判定。
- 端點（草案）：`GET /api/v2/wi-ai/review-items`、`GET …/{id}`、`POST …/{id}/revise`（`set_slot`、`set_distance`、`set_quantity`）、
  `POST …/{id}/decision`。列表與詳情依 `site_ids` 與 owner 過濾；viewer 只拿彙總計數。
- 採用：審核服務先做 stale 檢查 → 前端把 N 列追加到表尾（level 欄留空）→ `save_worksheet` 帶 `base_revision`；
  `WiRowSaveIn` 加可選 `review_item_id`，伺服器驗證後設 `provenance='ai_external'`，並在同一交易內把審核項設為 accepted、寫入 `committed_wi_row_ids` 與列雜湊。
  409 時重跑 stale 條件：成立轉 `stale`；不成立則重新載入並重送，審核項維持 pending。之後的存檔依列雜湊維持 `ai_external`。
- 可接受條件：plan 完整、`compute_cycle` 通過、engine_gate 無 high 級問題。預覽與落盤都用 `compute_rows_for_save` 與目標 worksheet 的 rule-set。
- 前端：新 feature module `features/wi-ai-review/`，經 `shared/api/client.ts`；並排顯示原文、AI 建議（標「語意未經驗證」）、引擎結果、差異與套用依據；AI 文字以純文字渲染。
- 測試：
  - unit：狀態機、stale 五條件、RBAC 矩陣、`set_slot` 不合法擋接受、出處欄位、provenance 不接受前端直傳。
  - integration：accept 後 TMU 與手建一致、409 但 stale 條件不成立時重送成功、一般存檔不觸發 stale、引用列被改觸發 stale、未存檔離開時審核項維持 pending、再次存檔後 provenance 維持、viewer 看不到原文。
  - e2e：工時表單句 → 審核 → 落盤。
- 稽核：accept、commit、重設。

## 6. S5：Excel 批量

- 併入既有 `/imports/{id}/parse-jobs` 與 job 表；明訂 `ImportRow.status` 與 `ai_review_items.status` 的對應。
- 只送 `description`；超過 `MAX_PARSE_TEXT_CHARS` 不外送；超過單批上限自動切批；單次匯入列數上限；`lane=batch`。
- 數量依 ADR-037 D6 四條規則（`quantity_source=excel`）；wi_group、觀測工時依 D5／D6；每項顯示套用依據。
- stale 另加 column_map 變動（`/map` 重跑會覆寫 `staged_rows`）。
- `submit` 以加法新增 `ai_adoptions[{row_index, review_item_id}]`，submit 內由後端重新 link／compile／gate 並重算 TMU（ADR-025 補 D11）。
- 另開 ADR：parse job 執行模型（呼叫移出鎖、lease 心跳、退避、idempotency、worker 出站前從 DB 重查提交者），核可或取代 ADR-030。
- 匯出 Excel／CSV 時的 formula injection 轉義（含 Tab、CR；儲存格設文字型別；若現行匯出未做，一併補上）。
- 測試：部分失敗、取消、重試、重複提交、429 退避、worker 崩潰後 lease 回收、提交者降級後 job 取消；fake 延遲 2–10 秒下的並行上限；e2e 批量進度。

## 7. 向 ai_service 提出的需求

1. 批量 flow `wi_motion_parse`（job、逐筆結果、`output` 欄、逐筆失敗隔離）。
2. code 清單與 MOST rule-set 的同步機制（bundle 宣告引用的 rule-set 版本，或提供可拉取的 enum）。
3. bundle 改用內建 schema，免除 MOST 持有 `json_schema` 複本；或提供 schema hash 查詢。
4. 每個 motion 的歧義或替代候選訊號；若可行，回傳 evidence span。
5. 錯誤信封一致（flow 錯誤用 `FLOW_RUNTIME_ERROR`；不回純文字 500）。
6. 准入行為（排隊或建議並行數）、結果保留期、in-flight 配額、body 與單句字數上限的定案值。
7. `most` 金鑰的最小權限（不得轉換 bundle 狀態）；金鑰新舊並存以便輪替。（上線前置，見 ADR-037 D9）
8. 以服務金鑰為唯一授權依據；在身分模型落地前不依 header 授權。MOST 不送員工編號，job／idempotency 範圍要能以服務身分運作。
9. 說明 LLM provider 是否出內網、是否保存請求內容。（上線前置，見 ADR-037 D9）
10. poc003 轉 shadow／active 的時程與 eval 基準；回饋接收接口（延後項）。

## 8. 實作前要驗證的假設

- ai_service main 是否已含本計畫依賴的 `structured-completion` 行為（盤點時在其分支 `docs/s074-adr-011-flow-async-motion` 上看到的與 main 一致）。
- 舊 `wi-workbench` 面板是否仍在使用。
- 現行 Excel／CSV 匯出是否已防 formula injection。
