# MOST ↔ ai_service 整合與舊 LLM 清理：實作計畫

**文件類型：** Roadmap / 執行分期（非核心規則權威）
**版本：** 0.2 — 計畫草案（納入 2026-11-14 第二輪審查與裁決）
**建立日期：** 2026-11-14
**決策邊界：** [ADR-037](../decisions/ADR-037-ai-service-integration.md)（accepted 2026-11-14）
**既有行為：** [ADR-025](../decisions/ADR-025-import-template-matching-p2.md)、[ADR-026](../decisions/ADR-026-wi-ai-parser-pipeline-boundary.md)、[ADR-033](../decisions/ADR-033-llm-planner-scope-narrowing.md)

## 狀態

🔄 執行中（ADR-037 於 2026-11-14 核可）。S0 文件回寫、S1 舊 LLM 路徑移除、S2 adapter／fake／契約測試已完成；S3 進行中：PR #8（guard）、#9（migration v2_0050）、#10（plan adapter）、#11（`wi_ai_service` 接線）、#12（路由）已合併；**路由合併後外部路徑即可達，`DDM_AI_SERVICE_ENABLED` 預設關是唯一防線，見「路由開放前置條件」。**與 ADR-037 衝突時以 ADR-037 為準。

**2026-11-23，ADR-038 追記**：S3 前端、S4、S5 依 [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md) 重新規劃：單句與整份共用工作區編輯區，審核佇列即編輯區（D2、D3）。前端拆分待另行提出。

**2026-11-23 修訂，Howard 裁決（ADR-038 D7）**：12 月底範圍含自動算距離（區域設定、DSX 座標同步、物件歸區、依區域座標算距離）。PR 順序：W2、W3，然後 W7（區域與距離後端）與 W4（工作區畫面）平行，再 W5（整份上傳整合）、W8（距離畫面），W6（移除舊畫面）最後。

**2026-11-23，W1，Howard 核可（W1 進度）**：W1（編輯區資料表 `wi_draft_rows` 與 6 個 API）已在 `feat/w1-wi-draft-rows` 分支實作。**W3 待辦**：外部 AI 草稿寫入前的 engine_gate 檢查（目前寫入時 Fail-Fast 拒絕 `ai_service` 草稿）、其餘 stale 條件與列內容雜湊（W1 只做「非草稿版本」與「revision 不符 409」）。

**2026-11-24，W3，依審查建議，Howard 授權（W3 進度）**：上段 W3 待辦（engine_gate 檢查、stale 條件）已在 W3 實作，單句與整份上傳寫進編輯區；批次外部 AI（S5 的 batch lane）與 Excel 數量權威拆到 W3b。狀態與驗收見 [adr-038-delivery-plan.md](adr-038-delivery-plan.md)。

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
| S3 | ADR-033 P3；單句路徑接上（工時表編輯情境，開關後）。**前端依 ADR-038 重新規劃（2026-11-23）** | 是 | 是（已實作的 `structured-completion`） |
| S4 | 審核佇列、逐項審核、最小編輯、經編輯器落盤到 worksheet。**依 ADR-038 重新規劃（2026-11-23）：審核佇列即工作區編輯區** | 是 | 否 |
| S5 | Excel 批量（併入既有 parse-jobs）。**依 ADR-038 重新規劃（2026-11-23）：與單句共用編輯區** | 是 | 是（逐句；flow 落地後換 adapter） |
| 延後 | motion_module 落盤（含工作台 AI）、回饋通道、flow／job adapter、拆分／合併編輯 | — | 部分 |

## 2. S1：移除舊 LLM 路徑

舊路徑由 `DDM_WI_AI_ENABLED` 控制，正式環境預設關閉、compose 沒有傳 `DDM_LLM_*`。移除後 `nl-draft` 的行為與正式環境現況相同（`rule_based`）。

**先搬家（同一個 PR 內完成，S2 才有防腐層可用）**

| 元件 | 現址 | 新址（建議） |
|---|---|---|
| `_parse_sanitize_validate`、`_sequence_orders_contiguous` | `nlp/llm_planner.py` | `nlp/inbound_guard.py` |
| `PlannerRequest`（索取契約）與其守衛 | `nlp/prompts/plan_v2_schema.py` | `nlp/plan_request.py`（S2 再決定是否移入 `ai_integration/`） |
| `PlannerError` | `nlp/planner_ports.py` | 原地保留（`planner_eval.py` 引用） |
| `TestEnglishParsingIntegration`（測 `rule_plan_adapter._detect_language`） | ~~`tests/unit/test_english_parsing.py`~~ | `tests/unit/test_rule_plan_language.py` |

`docs/CI_GATES.md` 的靜態掃描「定義站」放行清單隨新檔名同步。

**刪除**

- `nlp/llm_client.py`、`nlp/prompts/*`（`plan_v2_schema.py` 已先搬走）
- `nlp/planner_ports.py` 的 `LLMClientPort`／`LLMRawResponse`；`nlp/llm_planner.py` 的 `LLMPlannerAdapter`（防腐函式已搬走後整檔刪除）
- `wi_ai_service.py` 內的舊路徑：`_build_llm_client`、`_try_llm_plan`、`_plan_from_planner_output`、
  `from ddm_v2.nlp.prompts import plan_v1` 與 `plan_v1.PROMPT_VERSION`
- `settings.py` 的 `llm_*`；`wi_ai_enabled` 刪除（S3 新增 `ai_service_enabled`，env 名 `DDM_AI_SERVICE_ENABLED`）
- ~~`scripts/test_english_most_parsing.py`~~；`scripts/wi_ai_eval.py` 的 `--planner llm`、`OpenAICompatClient` 與 `settings.llm_*` 用法（含檔頭說明與 `secrets` tuple）

**必須保留的讀取路徑**：`wi_ai_service` 的 provenance 與快取重播中的 `prompt_version`、`llm_raw_response`、`response_format_mode`、`usage`。
DB 欄位不動；寫入端不再產生 `kind='llm'`，但**舊 `kind='llm'` 列必須仍可讀取與重播**，以 integration 測試釘住。

**保留不動**：`most_compiler/*`、`policies.resolve_multiplier`、`engine_gate`、`nlp/{linking,lexicon,quantities,normalization,routing,rule_based,rule_plan_adapter,gold_eval,contracts}`、
`planner_eval` 的脫敏函式（`_redact_urls`、`_redact_secrets`、`_sanitize_rejected_raw`、`sanitize_stripped_value`）與 `planner_preannotation_origin`、
`parse_job`／worker、`ai_parse_runs`、`ai_review_events`、outbox。`nlp/prompts/language_aware.detect_language` 只被舊路徑使用，可刪。

**測試**

| 處置 | 檔案 |
|---|---|
| 刪除 | ~~`tests/unit/test_llm_planner.py`~~、`test_prompt_few_shots.py`（few-shot 內容先轉成 gold 資產或移交 ai_service；它也是 `docs/CI_GATES.md` 第 188 行附近「對外列舉契約凍結」的守衛之一，刪檔前先確認 `test_contract_enum_freeze.py` 已涵蓋 `FROZEN_DEPENDENCY_TYPE`、`FROZEN_ROLE_KEYS`，未涵蓋就搬過去，並更新 CI_GATES 的檔案欄）、`test_english_parsing.py`（rule_based 部分已搬走） |
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

### S2 落地紀錄（2026-11-14）

- 落地檔案：`src/ddm_v2/ai_integration/{config,client,mapper,ports,adapter,fake,schema,errors}.py`、
  `schemas/wi-motion-parse.schema.json`（ai_service `df399fc` 的複本，sha256 釘在 `schema.py`）；
  測試 `tests/unit/ai_integration/`、`tests/contract/ai_service/`（新 pytest marker `contract`，CI 另一段執行）、
  假服務 `tests/fakes/ai_service_app.py`。
- **與計畫的差異 1（身分 header）**：ai_service 的 `structured-completion` 以 `require_acting_user` 要求四個使用者
  header，缺任一回 401。依 ADR-037 D7「不送員工編號」，四個 header 一律填**部署設定的固定服務身分**
  （`DDM_AI_SERVICE_SERVICE_USER`、`DDM_AI_SERVICE_PLANT_CODE`），不取自入站請求。
- **與計畫的差異 2（錯誤碼）**：S2 沒有路由對外報錯，所以失敗分類先留在 MOST 內部
  （`ai_integration.errors.AiServiceErrorKind`），**未**登記進 `errors/registry.py`、未加 i18n 訊息；
  S3 接上 nl-draft 時，降級原因以 routing reason／provenance 呈現，真的需要對外錯誤碼時再登記並補 zh-TW／en。
- **與計畫的差異 3（mapper 輸出）**：mapper 輸出 MOST 端型別 `MotionSuggestion`（已過 allow-list 與上限檢查），
  **尚未**轉成 `WorkInstructionPlan`／候選欄位——那需要以加法擴充 `nlp/contracts`，放在 S3 一起做。
- **golden 不是真服務錄製**：content 取自 ai_service pack 的 IE 核凍 few-shot；S3 進入條件的 30 句量測時補錄真回應。
- **已知限制**：DNS 重新綁定檢查在每次請求前做，仍有檢查到連線之間的 TOCTOU 空窗（https 憑證驗證可擋大部分；
  `DDM_AI_SERVICE_ALLOW_PLAINTEXT` 模式沒有這層，上線前要嘛釘 IP、要嘛只允許 loopback）；熔斷為單程序計數。
- ✅ **MOST 端守門已落地**（2026-11-20，`ai_integration/guard.py`；規則本體見 ADR-037 D8，本處不重述）：
  並行上限、每人每分鐘與每日預算、single-flight。`AiServiceWiParser.parse` 本身仍逐句串行，守門由 `GuardedWiParser` 包住。
- **S3 進入前必須補**：S3 的 `wi_ai_service` 要在外層接住 `ValueError` 與 `RuntimeError`，轉成降級並記 ERROR log。
  `ValueError` 包含 `context` 白名單違規，以及 `actor`／`scope` 缺漏（ADR-037 D2、D8）；`RuntimeError` 是 schema hash 不符。
  另外，`QUOTA_EXCEEDED` 接到路由而需要對外報錯時，必須登記 ADR-034 信封碼並補 zh-TW／en 對稱文案（ADR-032），目前前端還沒有。
  S3 落盤 `ai_parse_runs` 要能處理「無 `run_id`、有 `shared_run_id`」（ADR-037 D7）。

## 4. S3：ADR-033 P3＋單句路徑（開關後）

> 2026-11-23，ADR-038 追記：S3 前端部分依 ADR-038 重新規劃（單句與整份共用工作區編輯區）。以下 PR-A／PR-B 為後端，不受影響。

**拆分（2026-11-22）**：S3 分兩個 PR。
- **PR-A（已落地）**：純函式與契約加法。`ai_integration/plan_adapter.py`（`MotionSuggestion` → `WorkInstructionPlan`＋候選；`chosen` 恆為 None，`preview_drafts` 用候選複本算預覽）、`CandidateSource` 加 `ai_service`、六個 routing reason、契約凍結表（`test_contract_enum_freeze`）。
- **PR-B（已落地於本分支，2026-11-22；Howard 核可設計 Q1–Q6「照建議」）**：`wi_ai_service` 接線。實際行為：
  - `parse_interactive` 新增可選參數 `external`（`ExternalAi`：`port`、`service_bundle_code`（部署設定的 ai_service bundle）、`actor`、`scope`、`known_hand`）。`None` 時行為與先前完全相同（rule_based）。只支援單句 interactive，批量維持 rule_based（S5）。
  - 順序：讀完要讀的 → `session.commit()`（釋放連線，ADR-037 D8）→ 呼叫 port → 算完 → 最後才寫 run（run 是最後一個副作用）。
  - 快取鍵含佔位 bundle、設定的 service bundle code、`known_hand`、worksheet revision（另含正規化語句、context、rule-set）。命中時不呼叫 ai_service、不扣額度。呼叫後比對回應的 `bundle_code` 與設定是否一致，不一致即降級。
  - 一律 `compute_routing(auto_enabled=False)`，不受 `wi_ai_auto_enabled` 影響。
  - 降級：port 回 failed、guard 的 `ValueError`／`RuntimeError`、任何例外、空結果、佔位 bundle 缺、bundle 不符、plan 建不起來、provenance 不合 allow-list，一律降級為 rule_based，不拋給呼叫端。完整原因寫進該 rule run 的 `error`（`{"ai_service": {error_kind, upstream_code}}`）；回應的 `provenance.ai_error` 是粗粒度版：維運類分類（`misconfigured`、`auth`、`deployment`、`request_rejected`、`contract_mismatch`、`internal_error`、`bundle_not_runnable`）不帶 `upstream_code`。降級的 run 不當 external run 快取，下一次請求會再試 AI。
  - legacy GM 形狀 slots 仍由 MOST 的 rule parser 產生（出處 `rule_based_v1`）；重播時從存檔候選還原（`slots_parser=ai_candidates`、`chosen` 空）。
  - provenance 鍵 allow-list 在 `ai_integration/provenance.py`：ai_service 的 13 個鍵，加 MOST 自己的 `motion_labels`、`dropped`。值只收識別字元、限長、有限數值；寫入前 `validate_provenance` 再驗一次。
  - **前端未做**（見下方前置條件）。
- **路由 PR（分支 `feat/s3-nl-draft-ai-route`，2026-11-22；Howard 核可「照建議」）**：
  - 路由接線與角色檢查已完成：`nl_draft` 在 analyst 以上且整合可用時傳 `external`；viewer 與整合不可用時一律 rule_based。`ai.status` 三值：`ai_service`／`degraded`／`rule_based`。請求新增 `hand` 欄位（MOST 已知手別，對應 `known_hand`）。`scope`＝worksheet 所屬站點，沒有則 `'none'`，只用於隔離合併，不是存取檢查。新增 `GET /wi-ai/status`（登入即可，只回 `enabled`／`available`）。
  - 行程級單例 `ai_integration/runtime.py`：啟動時在執行緒預熱；請求路徑不在 event loop 上做 DNS；暫時性 DNS 失敗 60 秒後重試；任何建構錯誤都收成「啟用但不可用」。
  - compose 傳 `DDM_AI_SERVICE_*`；金鑰正式做法是 docker secrets 檔案（`DDM_AI_SERVICE_KEY_FILE`）。
  - 稽核「外送」事件依 ADR-037 D7 修訂（2026-11-22）改為 v1 以 `ai_parse_runs` 代替；失敗外送的 `request_id` 寫進該 run 的 `error`（`_Degraded.request_id`）。
  - 開放前必須先滿足下方「路由開放前置條件」。

### 路由開放前置條件

下列各項是 PR-B 審查發現的，狀態以 2026-11-22 路由 PR 為準。路由 PR 合併後外部路徑已接上，**未完成項在打開 `DDM_AI_SERVICE_ENABLED` 前必須完成**。

- **前端不得直接採用預覽 draft（❌ 未完成；打開開關的硬性前置）**：**2026-11-23，ADR-038 追記：由 ADR-038 D3 的編輯區取代（尚未實作）。**以下為原文：路由合併後開關預設關是唯一防線，前端修正與 `ai_error` 文案落地前，不得在任何環境開啟 `DDM_AI_SERVICE_ENABLED`。`AiDraftPanel.tsx`、`ActionModuleWorkspace.tsx` 的 adopt 只檢查 `draft.cycle` 是否存在，會把帶 `ai_candidate_preview` 的 cycle 載入編輯器（`source='ai'`）。需停用，或導向 S4 審核流程（ADR-037 D3 澄清）。
- **稽核與角色（D7）（✅ 已完成；稽核改為 v1 過渡）**：稽核依 ADR-037 D7 修訂（2026-11-22）不做外送事件，v1 以 `ai_parse_runs` 代替，失敗外送的 `request_id` 寫進 run 的 `error`（涵蓋 ai_service 回 failed 與已回應但 MOST 端降級）。角色檢查在路由（analyst 以上才傳 `external`），有 `tests/integration/test_nl_draft_ai_route.py` 鎖定。
- **`worksheet_id` 存取權驗證（已裁決不做）**：Howard 2026-11-22：權限由未來的統一平台重新設計，MOST 不發明站點權限模型；`scope` 只用於隔離合併。重播回 `cached`／`cached_run_id` 的探測風險記於 [BL-ENG-19](../BACKLOG.md#bl-eng-19--worksheet-路由沒有站點層級的存取控制延後)。
- **`known_hand`／`scope` 的來源（✅ 已完成）**：`hand` 由請求欄位帶入，`scope` 取 worksheet 所屬站點，否則 `'none'`。`known_hand` 是整句一個值，逐 motion 比對會對左右手不同的句子誤報（保守方向）。無手別來源時不標，手別提示存在 `motion_labels`。
- **`ai_error` 文案與信封碼（❌ 未完成）**：補 zh-TW／en 對稱文案與 ADR-034 信封碼，與 `QUOTA_EXCEEDED` 一併登記。
- **legacy slots 在 fresh 與重播不一致（✅ 已由 ADR-038 D3 關閉，2026-11-23：AI 結果不使用 legacy 相容欄位）**：原文保留：fresh 是 rule parser 的建議值，重播是空的 `chosen`，前端相容欄位的顯示前後不同。路由開放前須決定：(i) 重播也用 rule parser 重算（會隨當下 synonym 漂移），或 (ii) fresh 也輸出空的 `chosen`（AI 路徑不預填；審查者傾向此案）。
- **快取 TTL（未決定，待 Howard）**：ai_service 在同一 bundle code 底下更新 model 或 prompt 時，快取不會 miss（`prompt_version`、`model_served` 要呼叫後才知道）。ADR-037 D8 沒有明文處理這個缺口。是否加 TTL，或把 `prompt_version` 變動視為 miss，尚未決定。

### 12 月開 AI 前的清單

全部完成前，不得在任何環境開啟 `DDM_AI_SERVICE_ENABLED`。

- [ ] 前端 adopt 停用，或導向 S4 審核流程（2026-11-23，ADR-038：由 D3 的編輯區取代，尚未實作）。
- [ ] `ai_error`／`QUOTA_EXCEEDED` 的 zh-TW／en 文案與 ADR-034 信封碼。
- [x] legacy slots：已由 ADR-038 D3 關閉（2026-11-23；AI 結果不使用 legacy 相容欄位，原二選一不再需要）。
- [x] 每日額度：已決定 10,000 次（Howard 2026-11-23，ADR-038 D7；原 ADR-037 D8 為 2000）。程式預設值另以小 PR 更新。
- [ ] 快取 TTL 決定。
- [ ] 進入條件：30 句延遲量測；`most` 金鑰最小權限已確認。
- [ ] 部署：verify 模式（見 [lb-most-auth](../architecture/lb-most-auth.md)）；金鑰用檔案。

**進入條件**：ADR-037 accepted；已對真 ai_service 量測 30 句延遲分布（poc003 須已轉 shadow），並據此定逾時與並行參數；`most` 金鑰最小權限已確認。

1. ✅ **ADR-033 P3 前兩項**（2026-11-14 完成）（獨立 PR 先行）：刪 `compile.py` 的 `_role_distance_cm` 與 `x_seconds` 讀值；在 `nlp/contracts` 以加法新增帶出處的距離／秒數欄位與 compile 的讀取（`a6`／CM `a0` 不在本階段，`return` 一律審核）；
   落地：`nlp/contracts.Measurement`（鍵 `from_location`／`distance`／`process_seconds`，來源 `human`／`dsx`／`excel`／`ai_estimate_confirmed`，有限且有上限）；空的時候不序列化，既有 plan JSON 逐位元不變；`wi_ai_eval` 報告與 P3 前相同（compile 55/55）。linker 的 X 秒數來源判斷同步改讀 measurements。`ai_estimate_confirmed` 來源必須帶確認者與時間。**數量仍讀 `quantity` 角色的 `role.value`**，出處欄位（`quantity_source=excel`）留到 S5。
   帶出處的人工數值不觸發 `*_unevidenced_review`。必過 `run_all.py`（GM=28／CM=29）與 compiler 單元測試。
2. **單句路徑**：
   - `wi_ai_service` 改用 `WiParserPort`；呼叫期間不占 DB session；single-flight（key 含 bundle 與 site）。
   - 入口在工時表編輯情境（`nl-draft` 帶 worksheet），不含 MOST 工作台（motion_module，延後）。
   - `nl-draft` 維持同步 200；AI 路徑要求 analyst，viewer 只走 `rule_based`；`ai` 區塊以加法新增 `status`、`provenance`。
   - ✅ migration（加法；v2_0050，2026-11-20 已落地）：
     - `ai_deployment_bundles.kind` 的 CHECK 加 `'external'`。（原寫「`ai_parse_runs.kind`」有誤：`ai_parse_runs` 沒有 kind 欄，一筆 run 的種類由 `bundle_id`（NOT NULL）指向的 bundle 決定。）
     - `ai_parse_runs` 新增 `provenance JSONB NULL`（ai_service 去敏出處）與 `upstream_run_id TEXT NULL`（加索引，供 ADR-037 D7 對帳；合併的等待者沒有自己的外送，此欄為 NULL，`shared_run_id` 只在 provenance）。
     - 佔位 bundle `external-ai-service`：kind=external、status=active、config={}。所有外部 run 都指向它。
     - downgrade：有 `ai_parse_runs` 或 `ai_parse_jobs` 指向 external bundle，或存在佔位以外的 external bundle，就 `RuntimeError` 拒絕、不刪資料（`ai_review_events` 會跟 run CASCADE，直接刪等於悄悄清掉稽核資料）。
   - ✅ 已落地的保護：`wi_ai_service._get_active_bundle` 與 `parse_job_service.create_parse_job` 查 active bundle 時加了 `kind != 'external'`，佔位 bundle 不會被 analyst 的 `bundle_code` 或環境設定選為 rule_based／llm 路徑的 bundle（有測試）。
   - **後續 `wi_ai_service` PR 必須處理**（已決定留給後續 PR，目前只記錄）：
     - 快取鍵：外部 run 全部指向同一個佔位 bundle，現有 `UNIQUE(input_hash, bundle_id)` 對外部 run 實際上只剩 `input_hash`。落盤前必須把 `provenance.bundle_code`（實際 ai_service bundle 代碼）納入 `input_hash`，並決定唯一約束衝突時的行為（重播或覆蓋）；否則 ai_service 換 bundle 或 prompt 後會命中舊結果。
     - 讀取路徑：`wi_ai_service._result_from_run` 以 `run.fallback` 與 `llm_raw_response` 判定 planner 與 model；外部 run 沒有 `llm_raw_response`，重播會被誤標為 rule_based。需改讀 provenance（`model_served`、`prompt_version`、`bundle_code`）。
     - 寫入端對 provenance 做鍵 allow-list（只允許 adapter／guard 實際輸出的鍵），並以測試斷言不含金鑰、員工編號、原文（ADR-037 D7）；DB 欄位本身無 schema 約束。
   - ✅ 新 routing reason 名稱已定案（2026-11-22，PR-A）：`ai_source_no_evidence`、`ai_unknown_code`、`ai_return_a_position`、`ai_hand_hint_mismatch`、`ai_addon_truncated`、`ai_candidate_preview`，全部在 `routing._eligible_auto` 的 blocked，並已同步 `test_contract_enum_freeze`（名稱與理由見 ADR-037 D4）。
     「code 與 linker 分歧」「AI 已展開成 N 個 motion」「數量待指定」三個 reason 延後到 S4，與 linker 比對一起做（ADR-037 D3、D4）。
   - `GET /api/v2/wi-ai/status`（不含金鑰與內部 URL）；前端顯示 AI 狀態與降級訊息。
   - 稽核：外送事件（不記原文）。
3. 測試：integration 以 fake server 驗成功與各種降級；viewer 不外送；既有 `e2e/workbench-nl-*.spec.ts` 不改仍綠。
4. 完成定義：開關開＋fake 時工時表情境可見 AI 草稿；開關關或 fake 掛掉時行為與現況一致；黃金值綠。

## 5. S4：審核佇列、逐項審核、最小編輯

> 2026-11-23，ADR-038 追記：依 ADR-038 重新規劃，審核佇列即工作區編輯區（D3），不另做獨立頁面。

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
- 設計約束（2026-11-22）：「採用」端點不得以 `run_id`／`created_by` 作授權依據。重播會讓多位使用者共用同一個 `run_id`，而 `ai_review.py` 目前只驗 run 存在、不驗擁有者。授權要以呼叫者對該 worksheet 的權限判斷。
- 採用前重驗（ADR-037 D3 澄清，2026-11-22）：S3 的預覽 draft 不是依據。採用時由人寫入 `chosen`，再重跑 compile 與引擎（含 engine_gate）。
- 與 S3 延後項合併：linker 比對，以及「code 與 linker 分歧」「AI 已展開成 N 個 motion」「數量待指定」三個 reason（ADR-037 D3、D4）。
- 前端：新 feature module `features/wi-ai-review/`，經 `shared/api/client.ts`；並排顯示原文、AI 建議（標「語意未經驗證」）、引擎結果、差異與套用依據；AI 文字以純文字渲染。
- 測試：
  - unit：狀態機、stale 五條件、RBAC 矩陣、`set_slot` 不合法擋接受、出處欄位、provenance 不接受前端直傳。
  - integration：accept 後 TMU 與手建一致、409 但 stale 條件不成立時重送成功、一般存檔不觸發 stale、引用列被改觸發 stale、未存檔離開時審核項維持 pending、再次存檔後 provenance 維持、viewer 看不到原文。
  - e2e：工時表單句 → 審核 → 落盤。
- 稽核：accept、commit、重設。

## 6. S5：Excel 批量

> 2026-11-23，ADR-038 追記：依 ADR-038 重新規劃，整份上傳的結果進同一個編輯區（D2）。

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
