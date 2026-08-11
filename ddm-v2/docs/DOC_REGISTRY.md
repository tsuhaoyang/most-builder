# DDM v2 文件索引

> **版本：** 2026-08-04
> **範圍：** 僅列目前 ddm-v2 的核心邏輯、系統設計、功能決策、有效 roadmap 與必要參考資產。

## 權威順序

發生衝突時依序採用：

1. **Accepted ADR**：已核可的邊界與取捨。
2. **核心邏輯規格**：MiniMOST、Level System 與黃金驗證。
3. **Canonical architecture spec**：系統、資料、前端與 AI 的目標設計。
4. **現行 API/schema/tests**：已落地行為的可執行證據。
5. **Roadmap / reference / archive**：不得覆蓋前四層。

若 accepted ADR 與核心規格出現衝突，必須先完成新決策與 regression tests，不可自行擇一。

## 狀態

| 符號 | 意義 |
|------|------|
| ✅ | 已核可或可作現行實作依據 |
| 🔄 | 現行文件，仍隨程式更新 |
| ⏳ | 完整提案，仍依賴 proposed ADR / User 核可 |
| 📌 | 必要參考或封存資產，不是新實作權威 |

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
| [WI AI Parser 實作規格](llm/wi-ai-parser-implementation-spec.md) | 實作層：契約、模組、DB、prompt、測試與 L0–L4 分期 | 🔄 |
| [WI AI Parser 交付追蹤](llm/wi-ai-parser-worklog.md) | Phase 狀態、卡點、D3 決策、checkpoint 與驗收紀錄 | 🔄 交付期間持續更新 |
| [WI AI Eval Reports](llm/eval-reports/README.md) | gold plan 評測輸出（`wi_ai_eval.py`） | 🔄 L3+ |

## 架構決策

完整狀態與主題索引見 [decisions/README.md](decisions/README.md)。

- **Accepted：** ADR-011～015、ADR-018～027。
- **Proposed：** ADR-016、ADR-017、ADR-028。
- ADR-026/027 已於 2026-08-10 accepted；實作仍依 roadmap 分批（L4 jobs 先於 worksheet revision／outbox）。
- ADR-028（most_engine 邊界驗證與單一權威）proposed，待 User 核可；前置條件為正式環境 `slot_inputs` 掃描。

## Roadmap

| 文件 | 用途 | 狀態 |
|------|------|------|
| [WI AI 與批次建模交付計畫](roadmap/wi-ai-and-batch-modeling-delivery-plan.md) | Core、Domain Readiness、AI Quality、Batch/Deployment 分期 | ⏳ |
| [全面中英雙語](roadmap/phase5-i18n-full-bilingual-spec.md) | UI、敘事、資料標籤、匯出與錯誤 i18n | 🔄 |

Roadmap 只定義時程與退出條件，不定義資料真相。

## 品質與維運

| 文件 | 用途 | 狀態 |
|------|------|------|
| [CI Gates](CI_GATES.md) | 核心、DB、API、前端、隔離與回放的合併門檻 | ✅ |
| [Legacy 分類清冊與引擎稽核](architecture/legacy-inventory-and-engine-audit.md) | **提出「清掉 legacy」之前必讀**：六類 legacy 的保留／移除判定依據、most_engine 純度稽核、靜默 fallback 實測 | ✅ |
| [Docker 資料持久化](reference/docker-data-persistence.zh-TW.md) | PostgreSQL volume 與安全操作 | 📌 |
| [v3 使用者資料來源](reference/v3-user-data-source.md) | v3 SQLite WI/WI 大綱來源、保護規則、checksum 與搬遷驗證 | ✅ |

## 必要資料與封存資產

| 路徑 | 定位 |
|------|------|
| [v3/reference/minimost_ai_dictionary_v1.json](v3/reference/minimost_ai_dictionary_v1.json) | **保留的 v3 IE 認證字典 DB**；ADR-014 值權威、converter 唯一輸入，禁止刪除 |
| [外部 v3 使用者 SQLite DB](../../ddm-v3/apps/api/minimost.db) | **保護資產、gitignored**；含 13 筆 WI 大綱、29 筆 actions、2 份 WI templates、1 個 WI Set 專案。只允許 `migrate_v3_user_data.py` 以 read-only mode 讀取，禁止清理或寫入 |
| [sample_excel/](sample_excel/) | 1205 Level/敘事來源、1128 WI 範本與詳解參考 |
| [html_con/](html_con/) | 已退役 UI prototype；依 repo 守則只封存、不作新實作依據 |

## 已清理內容

2026-08-04 已從工作文件移除：Phase 1 舊規格/手冊、早期 dev/user drafts、教科書算法副本、OQ 討論稿、已取代的 NL backlog ADR、舊 Phase2 roadmap，以及已由 v2 ADR/spec/tests 吸收的歷史 migration/analysis/impl 研究樹。需要追溯時使用 Git 歷史，不在 active docs 維護第二份真相。
