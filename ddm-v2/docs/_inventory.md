# docs/_inventory.md — WP-D1 文件盤點（暫存，D3 刪）

> **性質**：階段二 WP-D1 的盤點產物（實作書 §2）。**暫存檔，WP-D3 完成後刪除**。
> **原則**：只讀不改。重複權威取捨、47 份去留、空目錄處置全部**交 Howard 裁決**後才進 WP-D2。
> **產生時間**：2026-09-16，HEAD＝`be5e5a4`。

---

## 0. 圖規模與同步狀態（graphify）

| 項 | 值 |
|---|---|
| 重建前 | 8527 節點，`built_at_commit=5547e8c`（2026-09-02，落後 HEAD **78 個 commit**，整個 ADR-035 不在圖裡） |
| 重建後 | **9323 節點、19328 邊、489/493 社群**，`built_at_commit=be5e5a4`（**＝HEAD，已同步**） |
| 方式 | `graphify . --code-only`（132 份 doc/paper/image 需 LLM key 做語意抽取；本輪只需程式圖，docs 由本盤點手動處理）＋ `graphify cluster-only .` 命名社群 |

備註：`graphify-out/` 為 gitignore（僅 `.kiro/skills/graphify` 與 `graphify.md` 進版控），本次重建產物不 commit。

---

## 1. 總覽

- `docs/**/*.md` 共 **96 份**（另有非 md：3 個 xlsx、2 個 html）。
- `DOC_REGISTRY.md` 索引到 **36** 份（含 md 連結）→ **60 份不在索引**（其中 6 份為本輪新建的 `agent-team/`，由 `AGENTS.md` 指路而非 md 連結，不算漏網）。實質未收錄 ≈ **54 份**。
- 斷鏈（文件↔文件）：**0**（DOC_REGISTRY 的 md 連結全部解析成功）。
- 斷鏈（文件↔程式/測試，反引號路徑不存在）：**11 份文件**（見 §2.1）。
- 潛在孤兒（不在索引且無任何文件連入）：**35 份**（扣掉 agent-team 6 份 → 實質 29 份，見 §2.2）。

（完整 96 份逐檔表：狀態標頭／KB／是否在索引／被引次數／最後更新 commit，見本檔末 §7。）

---

## 2. 四類問題清單

### 2.1 斷鏈（Broken links）

文件↔文件：**無**。

文件↔程式/測試（反引號引用的路徑已不存在——多為改名或未建）：

| 文件 | 失效引用 | 研判 |
|---|---|---|
| `CI_GATES.md` | `tests/integration/test_rule_set_lifecycle.py` | 測試檔名可能已改；需核對現有 rule-set 測試檔名 |
| `agent-team/verification.md` | `src/shared/types/api.d.ts` | 該檔由 `npm run gen:api` 產生、**gitignore 或尚未生成**（不是真斷鏈，是產生檔）——WP-D3 修辭改為「由 OpenAPI 產生」 |
| `architecture/legacy-inventory-and-engine-audit.md` | `src/frontend/src/features/sop/api.ts`、`tests/integration/test_nl_draft_compat.py` | 歷史稽核文件，引用當時路徑；標歷史後可不修 |
| `lb-integration/LB_PROJECTION_IMPLEMENTATION_PLAN.md` | `tests/integration/test_export_lb_csv.py`、`test_worksheet_lb_tags_roundtrip.py` | **實際**落點為 `test_export.py`（repeat 回歸）與 `test_lb_projection_adapter_equiv.py`；計畫書寫的檔名未採用 → WP-D3 校正 |
| `lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md` | `test_motion_module_materialize_wi_group.py`、`test_worksheet_lb_tags_roundtrip.py` | 前者實為 `tests/integration/test_motion_module_materialize_wi_group.py`（存在，但路徑前綴差異）；後者未建 → 校正 |
| `lb-integration/TASK_CSV_INPUT_CONTRACT.md` | `src/optimization/**`、`src/shared/domain/**`（5 條） | **LB 端路徑**（此檔是 LB 提供的輸入契約副本）→ 屬跨 repo 參照，非 MOST 斷鏈；標明來源 |
| `llm/gold-review/README.md` | `tests/gold/wi_plans_draft/dXXX_XXXXXXXX.json` | 佔位樣板（`XXX`），非真實路徑 → 白名單性質 |
| `llm/wi-ai-parser-implementation-spec.md` | `scripts/dev_seed_ai_bundles.py`、`prune_ai_runs.py`、`build_option_embeddings.py` | 需核對 scripts/ 現有檔；可能已改名或未建 |
| `llm/wi-ai-parser-worklog.md` | `scripts/prune_ai_runs.py` | 同上 |
| `v4-integration/02-...md`、`06-...md` | `tests/test_most_workbench.py` 等 | **v4/LB 端測試路徑**（前瞻文件），非 MOST 現況 → 標分類後不修 |

> 研判：真正需 WP-D3 校正的 MOST 斷鏈約 **4 份**（CI_GATES、兩份 lb-integration 實作書、兩份 llm spec 的 scripts 引用）；其餘為產生檔、歷史、或跨 repo 參照。

### 2.2 孤兒（Orphan：不在索引且無文件連入）

實質 29 份（扣掉 agent-team 6 份新建 infra）：

- **root（2）**：`DOC_REGISTRY.md`（本身是索引，不算孤兒）、`ui-english-support-plan.md`（前瞻計畫？需分類）。
- **architecture（2）**：`docs-and-agent-docs-restructure-plan.md`（本重整實作書，剛建）、`dsx-integration-api-contract-draft.md`（草案，狀態⏳）。
- **lb-integration（4）**：`PR_DESCRIPTION.md`、`PR_DESCRIPTION_D10.md`、`TICKET_clone_concurrency_version_no.md`、`TICKET_outbox_claim_pending.md`（PR 描述與工單——性質上是過程產物，可標「過程紀錄」不進索引，或收進索引的「工單／PR」節）。
- **llm（6）**：`gold-review/` 下數份 README／樣板 + worklog 類。
- **v3（1）**：`v3/reference/four-tabs-usage-logic.md` 類（歷史 UX 參照）。
- **v4-integration（14）**：全部（架構師未追蹤的前瞻整合評估）。

> 多數孤兒是「過程紀錄／前瞻計畫／歷史」，非該刪的死檔。逐份去留見 §4，交 Howard。

### 2.3 重複權威（比內容，不比標題）

盤點結論：**MOST 文件的權威紀律良好，幾乎無「兩處都有定義級敘述且皆未標記取代」的真重複。** 逐一查證：

| 概念 | 定義級所在（權威） | 其他出現處 | 研判 |
|---|---|---|---|
| `1 TMU = 0.036 秒` | `core-logic/minimost-sequence-model-core-logic-spec.md`（§ 表＋Q1） | `core-logic-validation-test-catalog.md`（黃金向量頁復述）；`ADR-014`（「保留不變」**引用**，非重定義） | **低度**：測試目錄復述屬合理第二處（golden vector）；ADR-014 為引用。建議 WP-D2 在 catalog 加「定義見 spec」一行即可 |
| CSV 24 欄契約 | `lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`（§6，最高原則） | `level-system-core-logic-spec.md`、`system-architecture-v2-spec.md`、`MOST_LB_CONTRACT.md` | **無問題**：三處皆**已明確標「已被 ADR-035 取代／見 DATA_CONTRACT_SPEC」**（DOC_CONVENTION R2/R3 合規） |
| SIMO 貢獻 0 | `ADR-020` | core-logic spec、`MOST_LB_DATA_CONTRACT_SPEC`、ADR-035 | **無問題**：其餘皆**引用** ADR-020，非重定義 |
| `role_type`／`machine_unattended` | `MOST_LB_DATA_CONTRACT_SPEC.md §6`（＋ADR-035） | frontend-data-flow-spec、實作書 | **無問題**：引用關係清楚 |
| `MOST_LB_CONTRACT.md` 整份 | — | vs `MOST_LB_DATA_CONTRACT_SPEC.md` | **已自我降級**：檔頭明寫「本文件自此為討論紀錄；與 Spec 衝突以 Spec 為準」→ 非競爭權威 |

> 需 Howard 裁決者：僅 `1 TMU=0.036` 的 catalog 復述要不要加「定義見 spec」指引（低度，傾向加）。其餘無真重複。

### 2.4 歷史（History）

明確歷史／存檔性質、應標「不可作為現況依據、agent 預設不讀」：

- `architecture/legacy-inventory-and-engine-audit.md`（56KB，Phase-1 稽核）。
- `docs/v3/`（v3 UX 參照，母版性質但屬歷史畫面）。
- `docs/html_con/`（`v2-workbench.html`、`v2-wi-preview.html`——README 已註「廢止為 UI reference，僅存檔勿刪」）。
- `docs/sample_excel/`（3 個 xlsx：MOST 邏輯原始 Excel，來源素材）。
- `roadmap/phase5-i18n-full-bilingual-spec.md`（狀態標頭已是 ⛔）。
- 多份 `*-worklog.md`（llm/）為開發流水帳，非現況規範。

---

## 3. 用 graphify 社群對照 11 領域：程式有、文件缺口

以 `graphify query` 對每個領域錨點確認程式節點存在，再對照 `domains.yaml` 的 `docs`：

| 領域 | 程式（graphify 確認） | 權威文件現況 | 缺口 |
|---|---|---|---|
| most-engine | ✅ calculate/providers/rule_set_data | core-logic spec + ADR-028/014 齊 | 無 |
| lb-projection | ✅ lb_projection/** | DATA_CONTRACT_SPEC + ADR-035 + 計畫書，**剛做完很齊** | 無 |
| job-ux | ✅ features/level-system/** | JOB_UX 實作書 + ADR-035，**剛做完很齊** | 無 |
| level-system | ✅ level.py + level_validation_service | level-system-core-logic-spec | 無（服務層可補一段） |
| i18n | ✅ i18n_service/errors/locale.py + shared/i18n | ADR-032/034/011 | 無 |
| excel-import | ✅ import_service/import_excel | ADR-013（僅 2KB，很薄） | **偏薄**：ADR-013 只有骨架，暫存→submit 流程細節散在程式；WP-D2 可補 domain md |
| nlp-compiler | ✅ most_compiler/** + nlp/** | ADR-033 | **部分**：`most_compiler`（policies/compile）有 ADR-033，但 `nlp/**`（20 檔：lexicon/linking/routing/rule_based）**無專屬文件** |
| **rule-set** | ✅ rule_set_service/rule_option/synonym/policy | ADR-023（詞彙治理）+ ADR-025 | **缺口**：ADR-023 偏「詞彙治理」，**版本 clone→發布→回放**與 synonym governance 的規範散在程式與 ADR 片段，無單一「rule-set 生命週期」spec |
| **motion-module** | ✅ motion_module_service/template_matching/wi_set | 「對應 ADR」（草案語）＋ ADR-025（比對） | **缺口**：`motion_module`（WI 大綱、實體化、range/reorder）**無專屬權威文件**；wi_set/wi_context 亦然 |
| **auth-rbac** | ✅ auth/** + audit/outbox/search | ADR-019 + rbac-spec | **部分**：RBAC 有 spec，但 `outbox`（R3b 事件）、`search`（bge-m3）**無專屬文件** |

> **有程式、缺文件的區域（WP-D2 補 domain md 時重點）：rule-set 生命週期、motion-module／wi-set、nlp/**（compiler 之外）、outbox／search、excel-import 流程細節。** 與實作書 §2.5 的預判（rule-set、motion-module、auth-rbac）一致。

---

## 4. MOST 專屬三項（建議，交 Howard 裁決）

### 4.1 未收錄約 54 份 → 逐份判「收進索引／標歷史／建議刪」

分類建議（詳見 §7 逐檔）：

- **應收進索引（現行權威／有效參照，約 26 份）**：24 份 ADR（`ADR-011`…`ADR-034`）**不在 DOC_REGISTRY 的直接 md 連結**，但 DOC_REGISTRY 有一行連到 `decisions/README.md`（ADR 主題／狀態索引），故 ADR 是**經一跳可達、非真孤兒**；`agent-team/` 6 份（改由 DOC_REGISTRY 新「dev-team」節收錄）；`lb-integration/PR_DESCRIPTION*`＋`TICKET_*`（收進「過程紀錄」節或標歷史）。
- **標歷史（約 8 份）**：`legacy-inventory-and-engine-audit`、`v3/**`、`roadmap/phase5`（⛔）、各 `*-worklog.md`。
- **建議刪（0～少數，需 Howard 確認）**：`llm/gold-review/` 的純樣板 README（若已無 gold pipeline）；`ui-english-support-plan.md`（若已被 ADR-032 完整取代）。**傾向不刪，改標歷史**。

> ⚠️ **關鍵發現**：DOC_REGISTRY 的 md 直接連結只含 **ADR-035**；其餘 24 份 ADR 靠「連到 `decisions/README.md`」一跳可達（非孤兒，但三層入口應把 `decisions/README.md` 正式列為 ADR 索引層）。真正「未收錄且無入口」的大宗是 **`v4-integration/`（14，前瞻，未追蹤）＋ `llm/` worklog 與 gold-review 樣板（~6）＋ PR/TICKET 過程紀錄（4）＋ 草案（dsx draft、ui-english-support-plan）**——與實作書「約 47 份」同量級。

### 4.2 空目錄 `docs/sample_excel/`、`docs/html_con/` 去留

- 實作書稱「空目錄」，**實測兩者皆非空**：`sample_excel/` 有 3 個 xlsx（MOST 邏輯原始 Excel，663KB＋17KB＋22KB）；`html_con/` 有 2 個 html（v2-workbench、v2-wi-preview，README 已註廢止存檔）。
- **建議**：兩者皆**保留、標歷史/素材**（`sample_excel` 是核心邏輯來源素材，`html_con` 是封存原型）。不是空目錄，無需處置為「刪空目錄」。**交 Howard 確認是否納入索引的「素材／存檔」節。**

### 4.3 `docs/v3/`、`docs/llm/`、`docs/v4-integration/`、`docs/roadmap/` 分類

| 目錄 | 分類 | 建議索引標記 |
|---|---|---|
| `docs/v3/` | **歷史**（v3 UX 母版參照） | 標「歷史／UX 母版參照，不作新實作依據」 |
| `docs/llm/` | **現行**（WI-AI parser 已落地，ADR-026/033）＋部分 worklog 為歷史 | spec 類收現行索引；`*-worklog.md`、`gold-review/` 標歷史 |
| `docs/v4-integration/` | **前瞻計畫**（v4↔MOST 整合評估，架構師未追蹤） | 標「**未排程，實作前需回到本文件補 spec**」；且此為 LB/v4 端內容，多數程式引用指向 LB repo |
| `docs/roadmap/` | **前瞻計畫** | `phase5-i18n`（⛔ 已停）標歷史；`wi-ai-and-batch-modeling-delivery-plan` 標「未排程前瞻」 |

---

## 5. 停損點

以下三項一律**交 Howard 裁決後**才進 WP-D2：
1. 重複權威取捨（§2.3——實質只有 `1 TMU` catalog 復述一項待決，傾向加指引）。
2. 未收錄 ~54 份去留（§4.1——重點：24 份 ADR 是否經 `decisions/README.md` 正式納入三層入口）。
3. 空目錄處置（§4.2——實為非空的素材/存檔目錄，建議保留標記）。

---

## 6. graphify 社群清單（供 WP-D2 對照）

重建後 489 個聚合社群（節點級 493）。社群名多為檔名／符號級（code-only 圖）。與 11 領域對照見 §3。
（完整社群列表在 `graphify-out/GRAPH_REPORT.md`，本檔不複製。）

---

## 7. 逐檔盤點表

> 欄：KB｜索引（Y＝在 DOC_REGISTRY md 連結）｜被引（幾份 doc 連入）｜狀態標頭｜最後更新 commit。
> `docs/llm/` 另有 `gold-review/` 等子目錄檔未全列於此表主幹；完整清單見 `find docs -name '*.md'`。
### docs/

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| CI_GATES.md | 66 | Y | 5 | — | 7b9fed3|2026-09-12 |
| DOC_REGISTRY.md | 10 | N | 0 | — | 3fef07e|2026-09-12 |
| ui-english-support-plan.md | 4 | N | 0 | — | 827994d|2026-09-02 |

### docs/agent-team

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| checkpoint.md | 4 | N | 0 | — | aed28d2|2026-09-16 |
| commit-convention.md | 2 | N | 0 | — | aed28d2|2026-09-16 |
| verification.md | 2 | N | 0 | — | aed28d2|2026-09-16 |

### docs/architecture

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| data-model-and-storage-spec.md | 21 | Y | 7 | — | 7b9fed3|2026-09-12 |
| docs-and-agent-docs-restructure-plan.md | 8 | N | 0 | — | 855c4bb|2026-09-16 |
| domain-evolution-and-ai-readiness-spec.md | 34 | Y | 9 | — | bd99460|2026-08-04 |
| dsx-integration-api-contract-draft.md | 19 | N | 0 | ⏳ 草案——先建 MVP、邊做邊調（User 2 | 67027d2|2026-08-24 |
| frontend-data-flow-spec.md | 9 | Y | 3 | — | 3fef07e|2026-09-12 |
| frontend-ux-spec.md | 17 | Y | 4 | — | 3fef07e|2026-09-12 |
| lb-most-auth.md | 3 | Y | 2 | — | 3b72971|2026-06-24 |
| legacy-inventory-and-engine-audit.md | 56 | Y | 4 | — | bd69a78|2026-08-12 |
| rbac-spec.md | 7 | Y | 3 | — | ec4dbef|2026-07-10 |
| system-architecture-v2-spec.md | 14 | Y | 7 | — | 7b9fed3|2026-09-12 |
| v2-authoritative-model-guide.md | 10 | Y | 3 | — | bd99460|2026-08-04 |
| wi-ai-parser-system-spec.md | 41 | Y | 10 | — | bd99460|2026-08-04 |

### docs/core-logic

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| core-logic-validation-test-catalog.md | 14 | Y | 2 | — | 8015291|2026-08-19 |
| level-system-core-logic-spec.md | 26 | Y | 6 | — | 7b9fed3|2026-09-12 |
| minimost-sequence-model-core-logic-spec.md | 24 | Y | 13 | — | 7b9fed3|2026-09-12 |

### docs/decisions

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| ADR-011-schema-evolution-and-contract-stability.md | 3 | N | 14 | Accepted | 5abcca1|2026-06-21 |
| ADR-012-3d-rendering-architecture.md | 3 | N | 3 | accepted | 192814d|2026-06-22 |
| ADR-013-excel-import-architecture.md | 2 | N | 7 | accepted | bd99460|2026-08-04 |
| ADR-014-v3-dictionary-as-value-authority.md | 4 | N | 14 | accepted（2026-07-05，User | bd99460|2026-08-04 |
| ADR-015-nl-parsing-in-scope.md | 1 | N | 6 | accepted（2026-07-05，User | bd99460|2026-08-04 |
| ADR-016-search-infrastructure.md | 1 | N | 4 | proposed | bd99460|2026-08-04 |
| ADR-017-motion-modules-library.md | 2 | N | 2 | proposed | bd99460|2026-08-04 |
| ADR-018-workflow-and-role-convergence.md | 3 | N | 1 | Accepted（2026-07-10） | bd99460|2026-08-04 |
| ADR-019-worksheet-access-control.md | 12 | N | 1 | Accepted（2026-07-09） | b449243|2026-07-09 |
| ADR-020-simo-contribution-semantics.md | 3 | N | 5 | — | bd99460|2026-08-04 |
| ADR-021-ia-restructure-v3-parity.md | 5 | N | 6 | — | bd99460|2026-08-04 |
| ADR-022-workbench-two-layer-correction.md | 6 | N | 5 | — | afc5a95|2026-08-05 |
| ADR-023-dictionary-governance-unification.md | 22 | N | 12 | — | d2ff730|2026-08-20 |
| ADR-024-master-data-vs-dictionary-boundary.md | 10 | N | 7 | accepted（2026-07-22，User | a6b9faa|2026-07-24 |
| ADR-025-import-template-matching-p2.md | 5 | N | 6 | accepted（2026-07-22，User | 52b4fcc|2026-07-23 |
| ADR-026-wi-ai-parser-pipeline-boundary.md | 6 | N | 10 | accepted（2026-08-10，User | a7cc2d8|2026-08-10 |
| ADR-027-domain-evolution-versioning-and-ai-readiness.md | 6 | N | 9 | accepted（2026-08-10，User | a7cc2d8|2026-08-10 |
| ADR-028-most-engine-boundary-validation-and-single-authority.md | 28 | N | 4 | proposed | 8015291|2026-08-19 |
| ADR-029-python-dependency-locking-and-audit-gate.md | 33 | N | 1 | accepted（2026-08-15，User | eef6392|2026-08-15 |
| ADR-030-in-process-parse-worker-topology.md | 6 | N | 1 | proposed（待 User 核可；核可前本文 | 59518e7|2026-08-15 |
| ADR-031-spatial-layout-and-distance-acquisition.md | 44 | N | 4 | proposed（待 User 核可。核可前本文 | c508369|2026-08-17 |
| ADR-032-bilingual-ui-and-data-label-layer.md | 71 | N | 6 | — | 8e8a690|2026-09-04 |
| ADR-033-llm-planner-scope-narrowing.md | 41 | N | 3 |  | e6ce290|2026-08-23 |
| ADR-034-language-aware-error-contract.md | 19 | N | 3 | — | 8e8a690|2026-09-04 |
| ADR-035-lb-projection-layer-and-motion-decomposition.md | 17 | Y | 5 | — | c9062eb|2026-09-16 |
| README.md | 7 | Y | 1 | — | e6b16ec|2026-09-12 |

### docs/lb-integration

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| AGENT_BRIEF_LB_PROJECTION.md | 3 | Y | 1 | — | abc259a|2026-09-12 |
| AGENT_BRIEF_LEVEL_JOBS_UX.md | 5 | Y | 1 | — | 397b062|2026-09-12 |
| IE_REVIEW_MOST_LB_CONTRACT.md | 5 | Y | 1 | — | abc259a|2026-09-12 |
| LB_PROJECTION_IMPLEMENTATION_PLAN.md | 29 | Y | 3 | — | 3fef07e|2026-09-12 |
| LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md | 80 | Y | 3 | — | bd1796e|2026-09-12 |
| MOST_LB_CONTRACT.md | 46 | Y | 2 | — | f269c47|2026-09-12 |
| MOST_LB_DATA_CONTRACT_SPEC.md | 31 | Y | 5 | — | c9062eb|2026-09-16 |
| PR_DESCRIPTION.md | 6 | N | 0 | — | 2321f5e|2026-09-12 |
| PR_DESCRIPTION_D10.md | 9 | N | 0 | — | e357918|2026-09-14 |
| TASK_CSV_INPUT_CONTRACT.md | 29 | Y | 1 | — | abc259a|2026-09-12 |
| TICKET_clone_concurrency_version_no.md | 2 | N | 0 | — | 335a35d|2026-09-12 |
| TICKET_outbox_claim_pending.md | 1 | N | 0 | — | a022472|2026-09-14 |

### docs/llm

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| i18n-worklog.md | 46 | Y | 1 | — | a75c83a|2026-08-21 |
| wi-ai-parser-implementation-spec.md | 96 | Y | 2 | — | 7b9fed3|2026-09-12 |
| wi-ai-parser-worklog.md | 165 | Y | 3 | — | 93b0327|2026-08-24 |

### docs/reference

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| docker-data-persistence.zh-TW.md | 1 | Y | 1 | — | bd99460|2026-08-04 |
| v3-user-data-source.md | 3 | Y | 1 | 受保護資料來源 | bd99460|2026-08-04 |

### docs/roadmap

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| phase5-i18n-full-bilingual-spec.md | 3 | Y | 2 | ⛔ | da8fd48|2026-08-18 |
| wi-ai-and-batch-modeling-delivery-plan.md | 21 | Y | 3 | — | bd99460|2026-08-04 |

### docs/v4-integration

| 檔 | KB | 索引 | 被引 | 狀態標頭 | 最後更新 |
|---|--:|:--:|:--:|---|---|
| 00-overview.md | 6 | N | 0 | — | untracked |
| 01-feature-matrix.md | 16 | N | 0 | — | untracked |
| 02-most-sequence-comparison.md | 27 | N | 0 | — | untracked |
| 03-data-model-and-dictionary.md | 26 | N | 0 | — | untracked |
| 04-api-comparison.md | 28 | N | 0 | — | untracked |
| 05-integration-assessment.md | 21 | N | 0 | — | untracked |
| 06-line-balance-kpi-logic.md | 18 | N | 0 | — | untracked |
| 07-level-system-ux-gap.md | 25 | N | 0 | — | untracked |
| 08-implementation-spec.md | 20 | N | 0 | — | untracked |
| 09-open-question-A-main-instance.md | 5 | N | 0 | — | untracked |
| 10-open-question-B-datasource.md | 5 | N | 0 | — | untracked |
| 11-open-question-C-dict-db.md | 11 | N | 0 | — | untracked |
| 12-open-question-D-reviewer.md | 12 | N | 0 | — | untracked |
| 13-open-question-E-entities.md | 15 | N | 0 | — | untracked |
