# WI AI Parser 交付追蹤（Worklog）

**文件類型：** 交付追蹤紀錄（單一追蹤入口；不定義規格）
**規格：** [wi-ai-parser-implementation-spec.md](wi-ai-parser-implementation-spec.md)（§20 定義本文件的填寫規則）
**建立日期：** 2026-08-07

> 填寫規則摘要（完整版見 spec §20）：
> - Phase 狀態、checklist 勾選、checkpoint 結果 → 本文件。
> - 卡點（規格沒寫／規格與現實衝突）→ Blocker Log，**先記再解**；不刪列、不改寫歷史。
> - 決策分級：D1 架構級 → 開 ADR；D2 規格級 → 修 spec＋升版本；D3 實作級 → 本文件 Decision Log。
> - 不確定分級時從嚴（往上一級記）。

---

## 1. Phase 狀態總覽

| Phase | 內容 | 狀態 | 開工 | 完成 | Checkpoint |
|-------|------|------|------|------|------------|
| L0 | 契約 + AI 表 migration + rule parser 包進新契約 + run 落庫 | `completed` | 2026-08-07 | 2026-08-07 | code-review APPROVE_WITH_NITS |
| L1 | LLM planner adapter（structured output、cache、fallback） | `completed` | 2026-08-07 | 2026-08-07 | code-review APPROVE |
| L2 | Slot linking + deterministic compiler + engine gate | `completed` | 2026-08-07 | 2026-08-07 | code-review APPROVE_WITH_NITS |
| L3 | 審核 UI + review events + feedback candidates | `completed` | 2026-08-07 | 2026-08-10 | impl checkpoint；§0.1 現場 demo 待人 |
| L4 | 批次 parse job（**需 ADR-026/027 accepted**） | `completed` | 2026-08-10 | 2026-08-10 | code-review APPROVE |
| R1 | Worksheet revision 樂觀鎖（ADR-027 §2） | `completed` | 2026-08-11 | 2026-08-11 | code-review APPROVE_WITH_NITS |
| R2a | Policy manifests（modeling／Level）+ worksheet FK（ADR-027 §3） | `completed` | 2026-08-11 | 2026-08-11 | code-review APPROVE_WITH_NITS |
| R2b | Level validation runs + publish gate（ADR-027 §9） | `completed` | 2026-08-11 | 2026-08-11 | code-review APPROVE_WITH_NITS |
| R3b | Transactional outbox（review／save 同交易）（ADR-027 §5） | `completed` | 2026-08-11 | 2026-08-11 | code-review APPROVE_WITH_NITS |
| R3a | Method context `wi_row_contexts`（ADR-027 §4） | `completed` | 2026-08-11 | 2026-08-11 | code-review APPROVE_WITH_NITS |

狀態值：`not_started / in_progress / blocked / completed / blocked_on_adr`

## 2. Checklist 進度（對照 spec §18）

### L0
- [x] L0-1 `contracts.py` + 單元測試
- [x] L0-2 `normalize_with_map` + `quantities.py` + 測試
- [x] L0-3 `models/v2/ai_ops.py` + Alembic migration（AI-1 / v2_0026）+ bundle seed；`alembic upgrade head` 已套用
- [x] L0-4 `rule_plan_adapter.py` + `wi_ai_service.parse()`（rule 路徑）+ run 落庫 + 冪等
- [x] L0-5 `nl_draft.py` 加法擴充 + integration 相容／冪等測試（9 passed）
- [x] L0 checkpoint（code review；資安依 user 指示延後）
  - 驗證：unit + `test_nlp_api` 綠；migration v2_0026/v2_0027；review [L0 WI AI code review](b4377189-48be-4e40-9f68-42988e7b3bb4) → REQUEST_CHANGES 後修畢 → APPROVE_WITH_NITS。
  - 資安完整席位：延後（功能優先）。

### L1
- [x] L1-1 `llm_client.py` + settings 欄位 + `prompts/plan_v1.py`
- [x] L1-2 `llm_planner.py` + `validate_planner_output` + fallback 接線（`wi_ai_enabled`）
- [x] L1-3 injection / dimm / fallback 測試 + FakeLLMClient（minimal：無真模型）
- [x] L1 checkpoint
  - 驗證：unit + L1 FakeLLM/unreachable integration 綠；review → REQUEST_CHANGES 後修 P0/P1 → **APPROVE**（[L1 re-check](38db58c0-df15-4693-8e3d-5105d37d3618)）。
  - 備註：minimal 骨架；prompt few-shot 可後調；drafts 仍空（L2）；security 延後。

### L2
- [x] L2-0 端到端 fixture 5 筆（spec 附錄 A5）
- [x] L2-1 `linking.py`（L0/L1/L2 層；embedding 可後補）
- [x] L2-2 `most_compiler/` + 決策表矩陣測試
- [x] L2-3 engine gate + routing + multi_action 整合測試 + golden 全跑
- [x] L2 checkpoint
  - 驗證：A5 fixtures + engine_gate unit；integration NLP/fallback/L2 13 passed；golden 全綠；review → REQUEST_CHANGES 後修 P1 → **APPROVE_WITH_NITS**（[L2 re-check](8b77587a-1da0-46e8-9b51-62c6f70d4ccf)）。
  - 備註：L3 embedding 未做；A5 其餘 reject code 可後補；security 延後。

### L3
- [x] L3-1 `ai_review.py` + `ai_review_service`（events + candidates）+ 測試
- [x] L3-2 前端 `AiDraftPanel` 等 + typecheck/build（Playwright e2e 可後補）
- [x] L3-3 gold plans 目錄與 eval script 骨架
- [x] L3 checkpoint（實作出口；§0.1 現場五條待人確認）
  - 驗證：L3-1 review API；L3-2 typecheck/build＋APPROVE；L3-3 `test_gold_plans` 4 passed、`wi_ai_eval` 3/3、core_logic golden 全綠。
  - 缺口：Playwright e2e／A6 band／正式 IE gold 核准／資安席位／OpenAPI gen:api。
  - L3-2 備註：minimal — drafts／採用／accept_plan／stale／multi_action。
  - L3-3 備註：`tests/gold/wi_plans/` seed + `scripts/wi_ai_eval.py` + `docs/llm/eval-reports/`。

### L4（D3-007 jobs-first）
- [x] L4-0 ADR-026／027 → accepted；worklog／registry
- [x] L4-1 `ImportRow` + `AiParseJob`／`AiParseJobItem` + migration `v2_0028`
- [x] L4-2 `parse_job_service`（materialize／create／claim SKIP LOCKED／tick／cancel）+ `parse_interactive(source_kind=import_row)`
- [x] L4-3 API：`POST/GET .../parse-jobs`、`.../tick`、`.../cancel`（analyst+；不改 map/submit）
- [x] L4-4 unit：`test_parse_job_service`；integration：`test_parse_jobs_api`
- [x] L4-5 `alembic upgrade head` + integration 綠 + checkpoint review
  - 驗證：`v2_0027→v2_0028`；unit+integration **9 passed**；review [L4 WI AI code review](77df24e2-19a1-47cb-836a-6b1c174d2f79) → REQUEST_CHANGES 後修 P1 → **APPROVE**。
  - R1 revision／policy／outbox 另工（D3-007）；資安延後。
  - agent shell 無 host docker/network（BLK-003 resolved via 使用者終端）。

### R1（worksheet revision）
- [x] R1-1 migration `v2_0029`：`revision_no`／`content_hash`／`last_edited_*`；`ai_parse_runs.source_revision`
- [x] R1-2 `worksheet_revision.bump` CAS + save／from-module／submit 接線；clone／create 重置為 1；publish 不 bump
- [x] R1-3 FE：store revision、save `base_revision`、409 UX；AI adopt 擋 stale source_revision
- [x] R1-4 `alembic upgrade` + integration + typecheck + checkpoint
  - 驗證：`v2_0028→v2_0029`；unit+revision_api+worksheet **16 passed**；typecheck 綠。
  - ORM expire fix：bump 後必須清 session 快取，避免舊 revision 被 flush 蓋回。
    - ⚠️ **2026-08-12 更正並修復（P0）**：當時採用的 `session.expire_all()` 會失效
      **整個 session** 的 ORM 物件，導致 async 下呼叫端的下一次屬性存取變成
      `MissingGreenlet`。實際線上影響三處：WI Set 專案含 ≥2 筆 WI、
      `from-module` 帶 `base_revision`、`imports/submit` 帶 `base_revision`（前端實際就這樣送）
      全部 500。四個呼叫點只有 `save_worksheet` 因為之後多做了一次 `session.get`
      而僥倖能用——而那正是唯一有 CAS 測試的那一個。
    - 另更正失效機制：「舊 revision 被 flush 蓋回」實測在 SQLAlchemy 2.0 下**不成立**
      （ORM UPDATE 只寫有 history 差異的欄位）。真正可觸發的是 **stale read**——
      `read_worksheet()` 直接讀 identity map 那顆物件，回舊 revision 給 client，
      client 拿它當下次 `base_revision` → 永遠 409。
    - 修法：`session.refresh(ws, attribute_names=[...])` 只重讀被 Core UPDATE 改過的欄位。
      補 7 條迴歸測試（含 mutation 驗證）。詳見
      [引擎與 legacy 稽核 §11](../architecture/legacy-inventory-and-engine-audit.md)。
  - P0/P1 後修：AI cache key 含 ws:rev；Import/from-module `base_revision`；legacy adopt stale gate；`source_revision` BigInteger。
  - checkpoint：[R1 review](ca934a12-62e5-4670-a022-29c7602c86a7) → **APPROVE_WITH_NITS**（nit：legacy null revision；import/CAS／cache bust 測試可後補）。資安延後。

### R2a（policy manifests）
- [x] R2a-1 migration `v2_0030`：`modeling_policy_versions`／`level_policy_versions`；worksheet nullable FKs；seed＋backfill factory V1；`ai_parse_jobs` FK
- [x] R2a-2 resolver：`(MODELING_FACTORY|LEVEL_FACTORY, version_no=1, published)`；缺則 `NoDefaultPolicy`；create／clone／read 接線
- [x] R2a-3 unit `test_policy_manifest`＋integration `test_policy_manifest_api`
- [x] R2a-4 `alembic upgrade` + pytest + checkpoint（待使用者終端）
  - 驗證：`v2_0029→v2_0030`；unit+policy_api+worksheet **17 passed**。
  - checkpoint：[R2a review](52d1b490-4ada-41e8-815d-691c7fd124ed) → **APPROVE_WITH_NITS**（ORM index 已補；fail-closed 測試可後補）。資安延後。
  - **非本切片**：R2b `level_validation_runs`／publish gate／Level validate 讀 policy。

### R2b（level validation runs）
- [x] R2b-1 migration `v2_0031`：`level_validation_runs` + unique (ws, rev, policy, input_hash)
- [x] R2b-2 `level_validation_service`：validate_and_persist／assert_publishable；save／clone 寫 run；publish gate
- [x] R2b-3 `POST .../level/validate`；409/422 `LEVEL_VALIDATION_*`
- [x] R2b-4 alembic + pytest + checkpoint（待使用者終端）
  - 驗證：`v2_0030→v2_0031`；unit+level_validation_api+worksheet+revision+policy **23 passed**。
  - checkpoint：[R2b review](9b4a4c82-95cd-4bc1-a864-e1f74a03010a) → **APPROVE_WITH_NITS**（nit：policy mismatch／舊 rev 測試可後補）。資安延後。

### R3b（outbox）
- [x] R3b-1 migration `v2_0032`：`outbox_events`（pending/published/failed/dead_letter）
- [x] R3b-2 `outbox_service.enqueue_*` + claim／mark；`record_reviews`／`save_worksheet` 同交易寫入
- [x] R3b-3 unit + integration `test_outbox*`
- [x] R3b-4 alembic + pytest + checkpoint（待使用者終端）
  - 驗證：`v2_0031→v2_0033`；outbox+ai_review **8 passed**（含 UNIQUE migration）。
  - checkpoint：[R3b review](19d777d6-6a9a-49d5-bfc9-5b19dc078d20) → P1 UNIQUE 已補 → **APPROVE_WITH_NITS**。資安延後。
  - **非本切片**：R3a `wi_row_contexts`；publisher worker／AI DB role／完整 R0 retry policy。

### R3a（wi_row_contexts）
- [x] R3a-1 migration `v2_0034`：`wi_row_contexts`（UNIQUE wi_row_id CASCADE）
- [x] R3a-2 `wi-context-v1` Pydantic 校驗＋hash；GET/PUT/DELETE `/wi-rows/{id}/context`
- [x] R3a-3 unit + integration
- [x] R3a-4 alembic + pytest + checkpoint（待使用者終端）
  - 驗證：`v2_0033→v2_0034`；unit+integration **8 passed**（含 publish freeze）。
  - checkpoint：[R3a review](3325fa79-8b6a-4f87-9e0b-0b7386f6a27c) → P1 凍結測試已補 → **APPROVE_WITH_NITS**。資安延後。
  - **非本切片**：FE 編輯 UI；與 worksheet save 嵌套寫入；AI parse context 升正式欄。

## 3. Blocker Log（卡點紀錄）

> 格式：現象寫「發生了什麼」，處置寫「為什麼這樣解」。重開同一問題＝新編號＋引用舊編號。

| 編號 | 日期 | Phase | 現象 | 影響範圍 | 分級 | 處置與理由 | 狀態 |
|------|------|-------|------|----------|------|------------|------|
| BLK-001 | 2026-08-07 | L0 | 本機 Docker daemon 未啟動，無法跑 `alembic upgrade`／integration（需 DATABASE_URL） | L0 退出條件中的 migration/integration 驗收 | D3 | 啟動 docker compose db 後：`alembic upgrade head`（v2_0025→v2_0026）成功；`pytest tests/integration/test_nlp_api.py` → 9 passed。 | resolved |
| BLK-002 | 2026-08-10 | L4 | ADR-026／027 仍為 **proposed**；L4 硬條件含 accepted＋worksheet revision（R1）＋`import_rows`／`ai_parse_jobs` proposed schema | 不得開 L4 migration／worker／改 ADR-025 submit | D1 | 2026-08-10 User 核可兩 ADR → accepted。R1 revision／policy manifest／outbox 仍分批；L4 先 jobs 最小切片（D3-007）。 | resolved |
| BLK-003 | 2026-08-10 | L4 | Docker／DB：agent shell 無 sock／連不到 5432；使用者一般 WSL 可連 | L4-5 曾無法在 agent 內驗收 | D3 | 使用者終端：`alembic upgrade` v2_0028 + pytest 7 passed。agent 與 host 網路隔離保留為環境限制。 | resolved |

## 4. Decision Log（D3 實作級決策）

> D1 → `docs/decisions/ADR-*`；D2 → 修 spec＋§20.5 修訂紀錄。本表只收 D3。

| 編號 | 日期 | Phase | 背景 | 選項 | 選擇與理由 |
|------|------|-------|------|------|------------|
| D3-001 | 2026-08-07 | 規劃 | spec v1.0 七個軟點 | 邊做邊猜 vs 先查證定案 | 先查證定案，寫入附錄 A（升 v1.1） |
| D3-002 | 2026-08-07 | L0 | input_hash 用 bundle.code 或 bundle.id | code（穩定字串） vs UUID | 採用 code，與 settings/bundle seed 對齊；記於 wi_ai_service 註解 |
| D3-003 | 2026-08-07 | L0 | cache hit 時 legacy slots 重算或還原 | 重算（會與 synonym 漂移） vs 自 run 還原 | 自 run 的 slot_candidates 還原（legacy_from_run_snapshot），保證 ai.* 與 legacy 一致 |
| D3-004 | 2026-08-07 | L3 | OpenAPI nl-draft 200 為任意物件 | 等後端補 schema 再 gen:api vs 前端 `aiTypes.ts` 對齊 contracts | 採 aiTypes.ts；升 OpenAPI 後再 gen:api 並改 import |
| D3-005 | 2026-08-07 | L3 | A6 信心三檔缺後端 band 欄 | 前端重算 vs 暫不顯示 | 暫顯示「可採用／待審」；A6 band 等後端輸出後再接 |
| D3-006 | 2026-08-10 | L3 | gold 案例尚無 IE 正式核准 | 空目錄等 IE vs A5 fixture 作 `approved_by=seed` | 先 seed 3 筆跑通 eval；IE 核准後改標籤不改 TMU 鎖點（除非 rule-set 變更） |
| D3-007 | 2026-08-10 | L4 | L4 全量含 R1 revision／policy／outbox | 一次做完 vs jobs-first | User 選 jobs-first：`import_rows`+`ai_parse_jobs/items`+API+tick worker；`modeling_policy_version_id` 可 NULL；不改 ADR-025 submit；R1 另工 |
| D3-008 | 2026-08-15 | L4 | jobs 只能靠 API 手動 tick，批次 job 建了不會自己跑 | 手動 tick 維持 vs lifespan 背景 worker | lifespan asyncio task 週期驅動（`services/v2/parse_job_worker.py`；`DDM_PARSE_WORKER_ENABLED/_INTERVAL_S/_BATCH`，**預設開**——compose 不另設就會跑）；per-job 錯誤隔離＋poison 標 failed；多實例沿用 CLAIM_SQL SKIP LOCKED＋lease；API tick 保留供手動/測試。**部署拓撲面已升級 D1 → ADR-030（proposed）** |
| D3-009 | 2026-08-15 | 硬化 | 毒 job（病理長輸入）可卡死 event loop 分鐘級且重啟不復原（checkpoint security F1） | 只加 timeout vs 三層防禦 | 三層：①長度上限 `MAX_PARSE_TEXT_CHARS=2000`（=NLDraftIn 既有契約；病理最壞實測 800c≈0.18s/1600c≈1.4s，2000 鎖在 2–3s；超過標 review 不進 parser）②同步 CPU 段（normalize/rule parse）丟 executor＋`wait_for(PARSE_CPU_TIMEOUT_S=10)`（=最壞 2–3s 的 3 倍餘裕；單加 wait_for 無效——同步阻塞下 timeout 無作用點）③CLAIM_SQL 加 `attempt_count < MAX_ATTEMPTS`＋`_reap_exhausted_items` 收屍，毒 item 有終點 |
| D3-010 | 2026-08-15 | 硬化 | `_mark_job_failed` 把 pool 逾時/斷線等暫時性失敗判死刑，且繞過 `_finalize_job_status` 留下「終態 job＋active items」（code-reviewer #1） | 全部判死 vs 失敗分類 | 結構性（JobNotFound/RuleSetNotFound/RuntimeError=bundle 缺失）立即判死；其他視為 infra，log 後下輪重試、**連續** 5 次才判死（`MAX_CONSECUTIVE_JOB_FAILURES`）。判死一律走 `svc.fail_job`（收尾 items＋import_rows＋`_finalize_job_status`），狀態機單一路徑 |
| D3-011 | 2026-08-15 | 硬化 | 撤權不中止在途 job（security F4） | 完整物件級授權 vs 最小集 | 本輪最小集：`_runnable_jobs` 跳過 `app_users.is_active=False` 的 requester。**已知缺口（後續票）**：imported_by/site scope 的完整物件級授權（誰能 create/tick/cancel 誰的 import）未做 |
| D3-012 | 2026-08-15 | 硬化 | tick 交易在首個計數 UPDATE 後抱著 ai_parse_jobs 列鎖跨 LLM 呼叫，Cancel 被卡（code-reviewer #3） | job 挑選 SKIP LOCKED／LLM 移出交易 vs 縮鎖窗＋誠實文件 | 選後者：計數改交易尾端一次性遞增（鎖窗縮到 LLM 之後；殘餘＝首次 tick 的 queued→running，上限 ≈ batch×llm_timeout=32s，LLM 預設關閉時毫秒級）；worker docstring 撤回「job 挑選層免鎖」的錯誤宣稱。LLM 移出交易＝重構 parse_interactive 的交易邊界，收益只在 LLM 開啟時存在 → 併入 ADR-030 觸發條件 2（dedicated worker 抽離時做正解） |
| D3-013 | 2026-08-16 | P0 gold | gold 預標註管線（`scripts/gold_harvest.py`）：草稿 plan＝rule planner 輸出，IE 原樣轉正會讓 planner 給自己打分（審查實測 accuracy 0.667→0.98 假跳） | 指標照算＋文件警告 vs 結構性排除 | 結構性排除：草稿標 `plan_origin=rule_based_v1_preannotation`、轉正必填 `ie_modified: true\|false`；`summarize_planner_results` 把「plan_origin=受測 planner 且 ie_modified≠true」排除出 Plan 層指標（報告 `self_referential_excluded` 列名單與理由；report schema 升 v4）。橡皮圖章回歸測試釘死「未修改轉正 → 指標不動」。配套：pending_ie 守門改整份 plan 相等比對；`--recompile` 對正式 gold 預設拒絕（`--relock-approved --reason` 留痕）；「取＋放」配對不再誤標 multi_action（13/42 筆改發中性旗標 `take_place_pair_may_be_single_gm`）；非 seed 核准案例須有實質 cycle 或 `expected_incomplete_reason`；未核准案例混入 gold_dir 時報告降級 `wi-draft-latest.json` |
| D3-014 | 2026-08-16 | P0 gold | User/IE 三條裁決：①「取＋放」看動作（單一 cycle 與兩個 action 都可能，逐案裁決）②不變式「取最後一定有放」③v3 遷移資料是 IE 驗證過並提供的——結構（module/cycle 邊界）就是 IE 的切分裁決 | 全域定死配對方向 vs 逐案回填 v3 結構答案；文字啟發式 lint vs action_type 序列 lint | ①＋③：查證 cycle 容器語意（`motion_module_versions.rows[]` 一列＝一 cycle、`motion_modules.name_zh`＝發布版列數、`wi_rows` 一列＝一 cycle 容器但 v3 搬遷不寫此表、`motion_templates` 同）→ 帶切分旗標草稿回填 `v3_structure_hint`＋逐來源證據，只採 v3-import 訊號；配對題有答案改**確認題**（預設依 v3 結構，IE 可推翻——hint 是證據不是判決，絕不寫進 expected.*）。統計：19 配對筆 18 答案＋1 ambiguous（d026 同句跨結構矛盾）；22 likely_multi 筆 21 答案（17 single→「幾乎必然低估」警語降級）＋1 ambiguous（d045 唯一來源＝dev seed wi_rows）。②`acquire_without_place` lint：acquire 其後同 plan 內無 move_place/release_return/controlled_move（CM 無 P、M 即閉合，收 controlled_move 以免跟裁決①打架）→ WARN 旗標＋覆核表問「放在哪」；本輪 0 命中＝結構使然（rule adapter 永不出 acquire），`--recompile` 同步旗標供 IE 改後生效。mutation 7 條逐一紅；正式 gold 3 筆 byte 不動 |
| D3-015 | 2026-08-16 | P0 gold | IE 首輪覆核結果（User 親答）：①39 筆確認題全照 v3 結構預設 OK ②d045「拿取排線並對準接頭」＝1 列 ③d026「雙手抓握主板組至機箱」＝3 列（矛盾結構中 3 列 wi-template 是對的）。致命前提：`--force` 整批重寫草稿，覆核記錄寫在草稿上會被第二輪（同義詞登記後必重跑）洗掉 | 覆核狀態寫草稿（重產即失）vs 獨立 state 檔＋重產合併 | 獨立檔 `tests/gold/wi_plans_draft/review-state.json`（IE 的檔案：harvest 只讀不寫、`--force` 不刪），鍵＝normalized_text sha256 前 8 碼（跟句子不跟流水號）；harvest 重產時合併回草稿 `ie_review` 區塊。stale 不靜默套用（文字變＝配不到、v3 hint 變＝證據已不同、entry ie_modified=true＝plan 內容保不了→逐條列入摘要）；sha8 同但全 sha 不同＝完整性失敗大聲擋。套用結果：39 筆記 `segmentation_confirmed_by=IEC141289`＋`v3_structure_confirmed`（切分維度確認≠整筆核准；`ie_modified: false` 確認≠修改）；d045 記 `ie_ruling: single_cycle`（plan 不動）；d026 記 `ie_ruling: multi_cycle_3`＋**誠實降級** `plan_pending_resegmentation: true`——查證 3 列 wi-template（dcbb30a8）子句＝「雙手接觸DIMM壓合治具拉至規定位置／雙手抓握主板保持住至流水線／雙手抓握主板組至機箱」，非原句子字串，切不出 3 段誠實 evidence span（不編造），plan 重切等第二輪；被否定的單列 action module（32a29bba）標 `ie_ruling_rejected` 證據保留。配套：同義詞候選清單 `docs/llm/gold-review/synonym-candidates.md`（23 動詞面：10 同字直配＋13 標 `?` 待 IE 裁決；**候選未寫 DB**，ADR-023 治理）。驗證：--force 重跑 41 筆覆核記錄 byte-identical 存活；unit 656／integration 446＋1 skip／golden 全綠／eval 仍 n=3；正式 gold 3 筆不動 |
| D3-016 | 2026-08-16 | P0 gold | IE 第二輪指示（User 親答）：①d026「雙手抓握主板組至機箱」**這句本身＝1 列**——首輪「3 列」是對整個三步驟製程（wi-template）的回答，提問誤述範本結構為句子切分，釐清後更正 ②10 個同字直配同義詞核可先登記（含推至/拉至共 11 條映射），13 個 `?` 不登等具體句子情境 | 更正無痕覆寫 vs 保留軌跡；同義詞走 API vs 直寫 DB | ①`review-state.json` d026 entry 改 `ie_ruling: single_cycle`、清 `plan_pending_resegmentation`；**更正軌跡**存 entry `ruling_history`（先前 multi_cycle_3 全文＋supersede_reason；`load_review_state` 加軌跡形狀硬驗證——空殼軌跡擋下）；被否定結構改為 dcbb30a8 name_zh 的「名稱句→3 列」推論（本句自己是該範本 rows[2] 一列＝一 cycle），首輪對 32a29bba 的否定撤回 ②走正常 API `POST /api/v2/rule-sets/MINIMOST_FACTORY_V2/synonyms`（analyst+；登記人 IEC141289；priority 0）＝11 條，唯讀查表確證恰 11 列 ③第二輪 harvest `--force`：41 筆覆核狀態全存活（stale 0）、決定性二跑 byte-identical、正式 gold 3 筆不動。**誠實回報：cycle 完成度 0/60**——11 條同義詞讓 32/60 筆拿到 slot 命中（`empty_lexicon_no_slot_candidates` 60→0），但 rule_based_v1 的 GM/CM 判型只認名詞觸發詞（治具/機台）不吃詞典：50 筆卡 `composite_unknown`（39 筆句含 `?` 動詞、11 筆句面動詞全已登記＝判型是唯一卡點）；10 筆 typed GM 全 `missing_core_p`（3 筆卡未裁決的 `?` P 動詞「放至/放置」——實驗證實登記即轉 complete；7 筆句面無 P 動詞，需 IE 改 plan 非同義詞可解）。判型吃詞典與否＝rule parser 設計決策，未動核心（另票）。守門：slot 命中基線 superset 釘＋complete 集合等值釘（`test_gold_draft_schema.py`）、`ruling_history` 驗證 mutation 測試 |

## 5. Checkpoint 紀錄

| 日期 | Phase | 席位/審查者 | 發現 | 處置 |
|------|-------|-------------|------|------|
| 2026-08-07 | L0 | code-reviewer agent | P1：`error` 欄誤用；P2：缺 UNIQUE／abstain／active bundle／legacy 漂移／§7.5 | 全部必修項已修；**APPROVE_WITH_NITS**（optional 測試檔可後補）。資安延後。 |
| 2026-08-07 | L1 | code-reviewer agent | P1：malformed envelope／sanitize 硬失敗／cache provenance／缺 unreachable test | 全修；**APPROVE**。資安延後。 |
| 2026-08-07 | L2 | code-reviewer agent | P1：L0 stub／auto 忽略 quantity_policy／缺 engine_gate 覆蓋 | 全修；**APPROVE_WITH_NITS**。資安延後。 |
| 2026-08-07 | L3-2 | code-reviewer agent | P0 stale 被 setResponse 清掉；P1 前端假 A6 檔位 | 全修；**APPROVE**。 |
| 2026-08-10 | L3 | coordinator | L3-1～L3-3 實作出口彙整 | **impl checkpoint**：自動化證據齊；§0.1 現場 demo／Playwright／資安仍 open。 |
| 2026-08-10 | L4 | code-reviewer agent | P1：bundle pin 未用於 tick／計數非原子／缺 lease reclaim | 全修；**APPROVE**（[L4 review](77df24e2-19a1-47cb-836a-6b1c174d2f79)）。資安延後。 |
| 2026-08-11 | R1 | code-reviewer agent | P0 AI cache 未含 revision；P1 Import/from-module 無 CAS／legacy bypass／Integer vs BigInt | 全修；**APPROVE_WITH_NITS**（[R1 review](ca934a12-62e5-4670-a022-29c7602c86a7)）。資安延後。 |
| 2026-08-11 | R2a | code-reviewer agent | P2：ORM index／fail-closed 測試／CreateOut nullable | ORM index 已補；**APPROVE_WITH_NITS**（[R2a review](52d1b490-4ada-41e8-815d-691c7fd124ed)）。 |
| 2026-08-11 | R2b | code-reviewer agent | P2：policy mismatch／舊 rev 測試缺口；issues JSON string | **APPROVE_WITH_NITS**（[R2b review](9b4a4c82-95cd-4bc1-a864-e1f74a03010a)）。 |
| 2026-08-11 | R3b | code-reviewer agent | P1：缺 UNIQUE(aggregate,event_no)；P2 測試薄 | UNIQUE 以 v2_0033 補；**APPROVE_WITH_NITS**（[R3b review](19d777d6-6a9a-49d5-bfc9-5b19dc078d20)）。 |
| 2026-08-11 | R3a | code-reviewer agent | P1：缺 publish freeze IT；P2 ORM index／standalone revision | freeze IT＋index 已補；**APPROVE_WITH_NITS**（[R3a review](3325fa79-8b6a-4f87-9e0b-0b7386f6a27c)）。 |
| 2026-08-15 | L4 硬化 | checkpoint 三席（security＋code-reviewer×2） | Blocker：F1 毒 job 卡死 loop 且重啟不復原；#1 `_mark_job_failed` 暫時性失敗判死＋狀態機旁路；#2/F6 worker 先死→shutdown 炸/dispose 跳過/死亡靜默。必修：F3 idempotency 未範圍化、F5 `str(exc)` 落 DB、#6 cleanup 漏 search_documents、F2 上傳/配額無上限、F4 撤權不中止、#3 tick 鎖窗 | 全部修復（D3-009～D3-012；migration v2_0037；ADR-030 proposed）。已知缺口：F4 完整物件級授權（D3-011）；LLM 移出交易（D3-012→ADR-030 觸發條件） |
| 2026-08-16 | P0 gold 預標註管線 | code-reviewer agent | P0-1 自我指涉評測（草稿 plan＝planner 輸出，橡皮圖章轉正把指標吹到 0.98）；P0-2 pending_ie 守門只查 action 數（改 action_type/整句換掉都綠）；P1-3「IE 核准」無實質門檻；P1-4 `--recompile` 可零摩擦改寫正式 gold；P1-5 取放配對誤標 multi_action 且 caveat 方向反了（13/42 筆）；P2-6～P2-9 取樣/啟發式/全形/報告污染誠實性；P3 十項小修 | 全部修復（D3-013）。驗證：橡皮圖章實驗排除 60 筆、Plan 層指標釘在基線 2/3 與 4/7 不動；5 條 mutation 逐一紅→綠；unit 583／integration 445＋1 skip／golden 全綠；正式 gold 3 筆 byte-identical |

## 6. 驗收紀錄（spec §0.1）

| # | 判準 | 演示日期 | 結果 | 備註 |
|---|------|----------|------|------|
| 1 | 多 action 拆解＋top-K＋TMU 來自引擎 | 2026-08-10 | partial | 自動：gold g02＋L2 multi_action（TMU 引擎）；top-K UI 延後 |
| 2 | 「拿起 DIMM」不補步驟、missing、review | 2026-08-10 | pass* | 自動：gold g01 boundary＋routing review（*缺現場 UI 演示） |
| 3 | replace_candidate review event 可查 | 2026-08-10 | pass* | 自動：`test_ai_review_api` synonym candidate（*缺現場 UI） |
| 4 | LLM 關機 fallback 無損核心 | 2026-08-07 | pass | integration unreachable／disabled |
| 5 | 黃金錨點全綠（GM=28、CM=29） | 2026-08-10 | pass | `scripts/core_logic/run_all.py` 全綠 |

## 7. 待決事項狀態（鏡射 spec §19，裁決後更新）

| # | 事項 | 分級 | 狀態 |
|---|------|------|------|
| 1 | quantity 展開 policy | D2（IE 裁決） | open |
| 2 | inspect 併入前 cycle | D2（modeling policy） | open |
| 3 | 手別/SIMO 自動分配 | D2（IE 裁決） | open |
| 4 | 雲端 LLM | **D1（需 ADR）** | open |
| 5 | auto-accept 開啟 | **D1（需 ADR）** | open |
| 6 | `ai_*` 獨立 PostgreSQL schema | **D1（需 ADR）** | open |
| 7 | worksheet revision 綁定 | D2（R1 後加法） | open |
