# DDM v2 文件索引

> **版本：** 2026-08-12
> **範圍：** 僅列目前 ddm-v2 的核心邏輯、系統設計、功能決策、有效 roadmap 與必要參考資產。

## 權威順序

發生衝突時依序採用：

1. **Accepted ADR**：已核可的邊界與取捨。
2. **核心邏輯規格**：MiniMOST、Level System 與黃金驗證。
3. **Canonical architecture spec**：系統、資料、前端與 AI 的目標設計。
4. **現行 API/schema/tests**：已落地行為的可執行證據。
5. **Roadmap / reference / archive**：不得覆蓋前四層。

MOST→LB 匯出的語意以 [MOST_LB_DATA_CONTRACT_SPEC.md](lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md) 為最高原則（位階同 Accepted ADR；ADR-035 為其決策紀錄）。

若 accepted ADR 與核心規格出現衝突，必須先完成新決策與 regression tests，不可自行擇一。

## 狀態

| 符號 | 意義 |
|------|------|
| ✅ | 已核可或可作現行實作依據 |
| 🔄 | 現行文件，仍隨程式更新 |
| ⏳ | 完整提案，仍依賴 proposed ADR / User 核可 |
| 📌 | 必要參考或封存資產，不是新實作權威 |

## 三層入口（怎麼用這份索引）

**改什麼功能 → 領域索引 → 權威規格**。三步：

1. **改什麼功能**：先想這次動的是哪個業務領域（TMU 引擎？投影？作業版？rule-set？…）。
2. **領域索引**：查下表 → 進 `docs/domains/<id>.md`（七段：一句話／權威文件／決策 ADR／程式入口／吃哪些欄位狀態／不變量／測試與缺口）。不變量的單一真相在 `docs/agent-team/domains.yaml`。
3. **權威規格**：領域索引指向的 core-logic spec／ADR／lb-integration 契約，才是要改／要比對的權威。

> **ADR 索引層（重要，一跳可達）**：本索引**不**逐一列 24 份 ADR 的連結；ADR 的主題／狀態索引集中在 [decisions/README.md](decisions/README.md)。路徑為 **DOC_REGISTRY.md → decisions/README.md → 各 ADR**（三層入口的 ADR 索引層）。ADR 非孤兒，經此一跳可達。

### 領域索引（11 個業務領域）

| 領域 | 索引 | 一句話 | 缺口票 |
|---|---|---|---|
| most-engine | [domains/most-engine.md](domains/most-engine.md) | TMU 單一權威引擎 | — |
| level-system | [domains/level-system.md](domains/level-system.md) | R1–R9 巢狀關係與驗證 | — |
| wi-workbench | [domains/wi-workbench.md](domains/wi-workbench.md) | 工時表／SIMO／clone／revision | — |
| motion-module | [domains/motion-module.md](domains/motion-module.md) | 動作範本庫／WI 大綱 | BL-DOC-3 |
| nlp-compiler | [domains/nlp-compiler.md](domains/nlp-compiler.md) | NL→MOST 編譯與 LLM planner | BL-DOC-2 |
| rule-set | [domains/rule-set.md](domains/rule-set.md) | 版本治理與回放 | **BL-DOC-1** |
| lb-projection | [domains/lb-projection.md](domains/lb-projection.md) | motion→task 投影與匯出契約 | BL-ENG-1／BL-ENG-2 |
| job-ux | [domains/job-ux.md](domains/job-ux.md) | 作業版（反投影，無 LLM） | BL-ENG-3 |
| i18n | [domains/i18n.md](domains/i18n.md) | 雙語標籤與錯誤信封 | — |
| excel-import | [domains/excel-import.md](domains/excel-import.md) | Excel／CSV 匯入 | BL-DOC-5 |
| auth-rbac | [domains/auth-rbac.md](domains/auth-rbac.md) | 認證／RBAC／稽核／搜尋 | BL-DOC-4 |

[BACKLOG.md](BACKLOG.md) 收**兩類票**（2026-09-21 起，分類定義見該檔檔頭）：**BL-DOC-1…5**＝有程式、缺單一權威規格的區域（對應領域索引誠實標「現況以程式為準」，不現場編規格）；**BL-ENG-1…3**＝程式／UI 的已知缺陷或待統一項（讓文件裡的「另案」有編號可追）。優先序見該檔。

## 核心邏輯

| 文件 | 用途 | 狀態 |
|------|------|------|
| [MiniMOST Sequence Model](core-logic/minimost-sequence-model-core-logic-spec.md) | GM/CM 七格、A/B/G/P/M/X/I、TMU、SIMO、敘事 | ✅ |
| [Level System](core-logic/level-system-core-logic-spec.md) | R1–R9、main/sub/cub/nb、變動層級與 LB output | ✅ |
| [核心驗證目錄](core-logic/core-logic-validation-test-catalog.md) | 黃金值、反例與 edge cases | ✅ |

值資料的唯一權威是 [v3 IE 認證字典 DB](v3/reference/minimost_ai_dictionary_v1.json)；生成檔 `rule_set_seed_v2.py` 不得手改。

## 系統架構

| 文件 | 用途 | 狀態 |
|------|------|------|
| [System Architecture v2](architecture/system-architecture-v2-spec.md) | 系統總覽、唯一引擎、rule-set、API 與 LB 邊界 | 🔄 |
| [Data Model and Storage](architecture/data-model-and-storage-spec.md) | v2 聚合、JSONB/關聯式分工、回放與生命週期 | 🔄 |
| [Domain Evolution and AI Readiness](architecture/domain-evolution-and-ai-readiness-spec.md) | Revision、policy manifests、method context、outbox、AI/batch 資料地基 | 🔄 ADR-027 accepted；分批落地 |
| [Frontend Data Flow](architecture/frontend-data-flow-spec.md) | DTO、server/client state、calculate/Level 資料流 | 🔄 |
| [Frontend UX Spec](architecture/frontend-ux-spec.md) | 現行 v2 導覽、工作台與互動 UX 約束 | ✅ ADR-021/022/024 |
| [RBAC](architecture/rbac-spec.md) | Gateway 身分、本地角色與端點權限 | ✅ |
| [LB / MOST Auth](architecture/lb-most-auth.md) | 與 LB 共用登入的部署與驗證邊界 | 🔄 |
| [v2 權威模型與反 Legacy 守則](architecture/v2-authoritative-model-guide.md) | 版本語意、兩層工作台、rule-set 回放與禁止模式 | ✅ |
| [WI AI Parser](architecture/wi-ai-parser-system-spec.md) | 互動/批次 WI 解析、compiler、審核與 learning loop | 🔄 ADR-026 accepted |
| [DSX 整合 API 契約（草案）](architecture/dsx-integration-api-contract-draft.md) | DSX 3D 擺放整合的 API 契約草案 | ⏳ 草案——先建 MVP、邊做邊調 |
| [WI AI Parser 實作規格](llm/wi-ai-parser-implementation-spec.md) | 實作層：契約、模組、DB、prompt、測試與 L0–L4 分期 | 🔄 |
| [WI AI Parser 交付追蹤](llm/wi-ai-parser-worklog.md) | Phase 狀態、卡點、D3 決策、checkpoint 與驗收紀錄 | 🔄 交付期間持續更新 |
| [WI AI Eval Reports](llm/eval-reports/README.md) | gold plan 評測輸出（`wi_ai_eval.py`） | 🔄 L3+ |
| [本機 14B planner 量測報告](llm/eval-reports/local-14b/README.md) | 非設定模型（qwen2.5:14b）的 prompt 迭代原始報告；**不得對 §14.4 門檻** | 🔄 數字與結論見 worklog §8 |
| [WI Gold Set 擴充覆核工作流](llm/gold-review/README.md) | 預標註草稿的 IE 覆核／轉正流程、自我指涉排除、split 原則（`gold_harvest.py`） | 🔄 P0 覆核中 |
| [i18n（雙語 UI）交付追蹤](llm/i18n-worklog.md) | ADR-032 Phase A／B／C 交付紀錄、複審修復、**§11 交接：做完了什麼／沒做什麼** | ✅ 三個 Phase 皆完成（2026-08-21）；剩餘缺口見 §11 |

## LB 整合（MOST → Line Balance）

| 文件 | 用途 | 狀態 |
|------|------|------|
| [MOST↔LB 資料契約 Spec](lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md) | **最高原則**：`most-lb-csv-v1.1` 24 欄、motion→task 粒度、兩個乘數矩陣、工具生命週期狀態機、分層 DAG、不變量、E/W 碼 | ✅ 2026-09-11 |
| [ADR-035](decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md) | 投影層決策與邊界（拆列、repeat_count、compiler 目的地、資料模型、過渡守衛、UI） | 🟢 accepted（2026-09-12，Howard） |
| [LB 投影層實作書](lb-integration/LB_PROJECTION_IMPLEMENTATION_PLAN.md) | WP0–WP12、檔案變更總表、關卡、禁止事項 | ✅ 已落地（feature/lb-projection，abc259a..d73467f；WP0–12 全綠） |
| [Agent Brief](lb-integration/AGENT_BRIEF_LB_PROJECTION.md) | 執行 agent 的工作方式與交付格式 | 🔄 |
| [Level System 作業版實作書](lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md) | ADR-035 D10 修訂：使用者語言的作業／排／四個是非題 UI；`wi_group`；dry-run 預覽端點；確定性提示（無 LLM）；反投影形式定義；zh-TW／en i18n 全目錄 | ✅ 已落地（feature/lb-projection，`08f59e7`..`49d02c1`；B1–F9 全綠，DoD-1 22 欄逐欄相等） |
| [Agent Brief：作業版](lb-integration/AGENT_BRIEF_LEVEL_JOBS_UX.md) | 執行作業版實作書的 agent prompt | 📝 |
| [作業版原型](lb-integration/prototypes/level-jobs/README.md) | 可跑的 HTML 設計原型（engine.js 為投影 JS 鏡像，僅供理解，不得移植） | 📌 設計參考 |
| [黃金 fixture](lb-integration/fixtures/README.md) | server node 24 motions → 34 tasks；LB 端實跑通過 | ✅ |
| [MOST↔LB 整合契約（討論紀錄）](lb-integration/MOST_LB_CONTRACT.md) | D1–D18 逐題裁決史；已由 Spec 正式化 | 📌 討論紀錄 |
| [LB Task CSV 輸入契約（LB 端提供）](lb-integration/TASK_CSV_INPUT_CONTRACT.md) | LB 讀什麼（以 LB 程式碼為準） | 📌 對接參考 |
| [IE 審查](lb-integration/IE_REVIEW_MOST_LB_CONTRACT.md) | H1–H6 缺口審查；H2/H3/H6 已解 | 📌 |
| [ADR-036](decisions/ADR-036-lb-writeback-consumption.md) | LB 回寫消費：唯讀快照＋屬性回流走正門（只回流 offline） | 🟢 accepted（2026-09-18；三取捨 2026-09-17 裁決；D6「件數」一條待整合架構師修訂） |
| [LB 回寫消費實作書](lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md) | 消費 `lb-most-writeback-v1`：資料模型、LB client、解析/聚合/差異、五端點、apply-offline、作業版產線視角 | ✅ 已落地（feature/lb-writeback，`6e1d139`..`79d8e4f`；B1–B6＋F1–F4，fixture 由 LB `aac992f` 實跑；真機端到端複驗、座標格式驗證、件數語意見 ADR-036 §5） |

## 架構決策

完整狀態與主題索引見 [decisions/README.md](decisions/README.md)。

- **Accepted：** ADR-011～015、ADR-018～027、ADR-029。
- **Proposed：** ADR-016、ADR-017、ADR-028、ADR-030、ADR-031（ADR-031＝空間佈局與距離取得：座標→引擎距離輸入的建議層，待 User 核可；臂展閾值與產線實體粒度尚未定值）。
- **ADR-032**＝雙語（中／英）UI 外殼與資料標籤層，**2026-08-18 accepted**（其 D4 修訂 ADR-023 規則 1 矩陣，須回寫 ADR-023；本表〈Roadmap〉的「全面中英雙語」草案隨之被取代）。實作分三階段（Phase A 前端框架＋locale／Phase B 標籤機器翻譯＋審核追蹤／Phase C 引擎敘事英文樣板），依序進行中。
- ADR-026/027 已於 2026-08-10 accepted；實作仍依 roadmap 分批（L4 jobs 先於 worksheet revision／outbox）。
- ADR-028（most_engine 邊界驗證與單一權威）**仍 proposed**，且**不應在正式環境掃描之前簽署**——
  §7 的執行順序把 User 核可放在「正式環境掃描報告」之後（第 2 步），先簽等於在缺證據時授權加嚴。
  掃描工具已於 2026-08-15 交付（`scripts/audit_slot_inputs.py`），本機零命中不構成放行證據（斷言 #34）。
  另有一項待裁決：§4 的留痕機制不可用（見該 ADR〈不由本 ADR 決定〉第 9 項）。
- ADR-029（Python 依賴鎖版與阻斷式 pip-audit）**2026-08-15 accepted**，18 條驗收斷言全綠。
  殘留決策：3.11/3.12 收斂、nightly 合併後的首次觸發、docker smoke 是否升為 PR 關卡、pytest 9 升級、
  starlette testclient deprecation。

## Roadmap

| 文件 | 用途 | 狀態 |
|------|------|------|
| [WI AI 與批次建模交付計畫](roadmap/wi-ai-and-batch-modeling-delivery-plan.md) | Core、Domain Readiness、AI Quality、Batch/Deployment 分期 | ⏳ |
| [全面中英雙語](roadmap/phase5-i18n-full-bilingual-spec.md) | UI、敘事、資料標籤、匯出與錯誤 i18n | ⛔ 已被 ADR-032 取代（見上方〈架構決策〉:62），僅存檔供追溯 |

Roadmap 只定義時程與退出條件，不定義資料真相。

## 品質與維運

| 文件 | 用途 | 狀態 |
|------|------|------|
| [CI Gates](CI_GATES.md) | 核心、DB、API、前端、隔離與回放的合併門檻；含〈依賴鎖版與安全稽核〉 | ✅ ADR-029 |
| [Legacy 分類清冊與引擎稽核](architecture/legacy-inventory-and-engine-audit.md) | **提出「清掉 legacy」之前必讀**：六類 legacy 的保留／移除判定依據、most_engine 純度稽核、靜默 fallback 實測；§12 為 ADR-029 的事實基礎 | ✅ |
| [Docker 資料持久化](reference/docker-data-persistence.zh-TW.md) | PostgreSQL volume 與安全操作 | 📌 |
| [v3 使用者資料來源](reference/v3-user-data-source.md) | v3 SQLite WI/WI 大綱來源、保護規則、checksum 與搬遷驗證 | ✅ |

## 必要資料與封存資產

| 路徑 | 定位 |
|------|------|
| [v3/reference/minimost_ai_dictionary_v1.json](v3/reference/minimost_ai_dictionary_v1.json) | **保留的 v3 IE 認證字典 DB**；ADR-014 值權威、converter 唯一輸入，禁止刪除 |
| [外部 v3 使用者 SQLite DB](../../ddm-v3/apps/api/minimost.db) | **保護資產、gitignored**；含 13 筆 WI 大綱、29 筆 actions、2 份 WI templates、1 個 WI Set 專案。只允許 `migrate_v3_user_data.py` 以 read-only mode 讀取，禁止清理或寫入 |
| [sample_excel/](sample_excel/) | 1205 Level/敘事來源、1128 WI 範本與詳解參考 |
| [html_con/](html_con/) | 已退役 UI prototype；依 repo 守則只封存、不作新實作依據 |

## 文件規範

MOST 目前**無獨立 `DOC_CONVENTION.md`**（跨 repo 複製全文會變成第二份權威）。文件撰寫與更新遵循以下**三條硬規則的精神**（權威全文見 LB 版本 [`line-balance_stream-weaver_v2/docs/DOC_CONVENTION.md`](../../../line-balance_stream-weaver_v2/docs/DOC_CONVENTION.md)，**只連結、不複製**）：

- **R1（正文只寫現況）**：正文描述當前有效狀態；過時內容不留在正文當現況。
- **R2（被取代內容標記後保留）**：被取代／已刪除的敘述用刪線 `~~…~~` 或「已廢止／訂正」標註後保留，不直接刪（可追溯）。`docs_check.py` 對 R2 刪線內的引用不算斷鏈。
- **R3（單一權威、其他指過去）**：每個概念只有一處定義級敘述，其他地方指過去、不重抄（本 repo 的落點：領域不變量單一真相在 `agent-team/domains.yaml`；領域索引與 ADR 只引用不重定義）。

改任何 `docs/` 後必跑 `python3 scripts/docs_check.py`（見 `agent-team/checkpoint.md` 步驟 6）；`most-doc-sync` 動手前後照此自檢。

## dev-team（agent 團隊設定）

正本在 `docs/agent-team/`，工具中立；`.kiro/`、`.claude/` 只留薄轉接；repo 根 `AGENTS.md`／`CLAUDE.md` 為薄入口。

| 文件 | 用途 |
|---|---|
| [agent-team/domains.yaml](agent-team/domains.yaml) | 領域登記表（11 領域 paths／anchors／invariants；領域索引與缺口守衛的單一真相） |
| [agent-team/checkpoint.md](agent-team/checkpoint.md) | 品質關卡（commit 前必跑；派 most-code-reviewer／most-logic-reviewer／most-doc-sync） |
| [agent-team/commit-convention.md](agent-team/commit-convention.md) | commit 慣例（`implements ADR-NNN: <WP> …`／`docs: …`） |
| [agent-team/verification.md](agent-team/verification.md) | 驗證規範（UI Playwright、unit/integration 分開跑、core-logic 黃金） |
| [agent-team/agents/](agent-team/agents/most-code-reviewer.md) | 三個 agent 角色正本 |
| [agent-team/decisions.log](agent-team/decisions.log) | 決策追蹤（只由主 context 追加） |
| [architecture/docs-and-agent-docs-restructure-plan.md](architecture/docs-and-agent-docs-restructure-plan.md) | 本次文件與 agent 設定重整實作書（階段一＋二落地追蹤） |

## 前瞻計畫（未排程）

> 標記：**未排程；實作前需回到本文件補 spec 並經核准**。不得覆蓋前四層權威。

| 文件 | 定位 |
|---|---|
| [roadmap/wi-ai-and-batch-modeling-delivery-plan.md](roadmap/wi-ai-and-batch-modeling-delivery-plan.md) | 前瞻交付計畫（未排程） |
| [v4-integration/](v4-integration/00-overview.md)（14 份） | v4↔MOST 整合評估；**內容多指向 LB repo，屬跨 repo 參考**；未排程，實作前需補 spec 並核准 |

## 過程紀錄（歷史過程，非現況規範）

> 這些是開發過程的流水帳／PR 描述／工單，**非現況規範**；收編於此後不再算孤兒。

| 文件 | 定位 |
|---|---|
| [lb-integration/PR_DESCRIPTION.md](lb-integration/PR_DESCRIPTION.md)、[PR_DESCRIPTION_D10.md](lb-integration/PR_DESCRIPTION_D10.md) | LB 投影／作業版 PR 描述 |
| [lb-integration/TICKET_clone_concurrency_version_no.md](lb-integration/TICKET_clone_concurrency_version_no.md)、[TICKET_outbox_claim_pending.md](lb-integration/TICKET_outbox_claim_pending.md) | 工單（並發、outbox） |
| [llm/wi-ai-parser-worklog.md](llm/wi-ai-parser-worklog.md)、[llm/i18n-worklog.md](llm/i18n-worklog.md) | 交付流水帳（已標歷史檔頭） |
| [llm/gold-review/](llm/gold-review/README.md) | gold set 覆核過程紀錄 |

## 歷史（不可作為現況依據，agent 預設不讀）

> 下列文件檔頭已標「歷史文件」；**agent 預設不讀**，現況以領域索引指向的權威文件為準。

| 文件 | 定位 |
|---|---|
| [architecture/legacy-inventory-and-engine-audit.md](architecture/legacy-inventory-and-engine-audit.md) | Phase-1 legacy 分類與引擎稽核（歷史） |
| [v3/reference/most-workbench-ui-ux.md](v3/reference/most-workbench-ui-ux.md)、[four-tabs-usage-logic.md](v3/reference/four-tabs-usage-logic.md) | v3 UX 母版參照（歷史畫面） |
| [roadmap/phase5-i18n-full-bilingual-spec.md](roadmap/phase5-i18n-full-bilingual-spec.md) | 已被 ADR-032 取代（⛔） |
| [ui-english-support-plan.md](ui-english-support-plan.md) | 早期英文支援計畫，已被 ADR-032 取代 |

## 已清理內容

2026-08-04 已從工作文件移除：Phase 1 舊規格/手冊、早期 dev/user drafts、教科書算法副本、OQ 討論稿、已取代的 NL backlog ADR、舊 Phase2 roadmap，以及已由 v2 ADR/spec/tests 吸收的歷史 migration/analysis/impl 研究樹。需要追溯時使用 Git 歷史，不在 active docs 維護第二份真相。
