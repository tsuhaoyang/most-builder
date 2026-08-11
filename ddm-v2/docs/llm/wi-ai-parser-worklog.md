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
