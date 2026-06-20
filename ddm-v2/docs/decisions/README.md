# 決策紀錄與討論索引

此目錄用於保存 DDM v2 專案的架構決策、待解問題與討論過程。

## 目的

- 保存「為什麼這樣做」而不只是「做了什麼」
- 記錄曾評估過的方案、取捨理由與否決原因
- 持續追蹤待解問題與其解決狀態
- 為後續開發者與 AI agent 提供可追溯的上下文

## 文件索引

| 文件 | 主題 | 狀態 |
|------|------|------|
| [OQ-001-most-system-selection.md](OQ-001-most-system-selection.md) | MOST 系統範圍：MiniMOST / MaxiMOST 的階段性策略，以及產品、SKU、廠區的建模粒度 | 🟡 討論中 |
| [OQ-002-allowance-and-standard-time.md](OQ-002-allowance-and-standard-time.md) | Normal Time / Standard Time 的定義、allowance 決策與舊資料匯入語義 | 🟡 討論中 |
| [OQ-003-database-migration.md](OQ-003-database-migration.md) | PostgreSQL、multi-site、未來微服務邊界與 Phase 1 架構策略 | 🟡 討論中 |
| [OQ-004-concurrent-access.md](OQ-004-concurrent-access.md) | 使用者工作區、後台發布、跨廠區產品版本與共享資料一致性 | 🟡 討論中 |
| [OQ-005-custom-tool-elements.md](OQ-005-custom-tool-elements.md) | 非標準 MOST 元件、自定義工具元素與其治理方式 | 🟡 討論中 |
| [OQ-006-phase1-implementation-open-questions.md](OQ-006-phase1-implementation-open-questions.md) | 從決策推進到 Phase 1 實作後浮現的細節問題 | 🟢 已定案 |
| [ADR-010-nl-to-most-backlog.md](ADR-010-nl-to-most-backlog.md) | 自然語言 → MOST：暫不實作與後續條件 | 🟢 已定案 |
| [ADR-011-schema-evolution-and-contract-stability.md](ADR-011-schema-evolution-and-contract-stability.md) | v2 實作期變更政策：契約穩定 + schema 加法演進（避免整合問題） | 🟢 已定案 |

## 主題歸屬

為避免同一問題在多份文件中重複追問，後續討論請以以下文件作為主歸屬，其餘文件只保留摘要與引用：

| 主題 | 主文件 | 說明 |
|------|--------|------|
| MOST 系統範圍、Product / SKU / Site 粒度 | `OQ-001-most-system-selection.md` | 包含 MiniMOST Phase 1 與跨 site 標準粒度 |
| Normal Time / Standard Time / allowance / 舊資料時間語義 | `OQ-002-allowance-and-standard-time.md` | 包含 historical standard time 與 line-balance 輸入語義 |
| PostgreSQL、site 資料隔離、history、auth 整合 | `OQ-003-database-migration.md` | 包含資料庫與 Phase 1 架構主決策 |
| workspace、draft、published、並發編輯規則 | `OQ-004-concurrent-access.md` | 包含使用者工作流與版本治理 |
| custom element 類型、建模、審核與版本化 | `OQ-005-custom-tool-elements.md` | 不重複討論 site / version 主體規則，必要時引用 OQ-003/OQ-004 |
| Phase 1 規格落地後的新細節問題 | `OQ-006-phase1-implementation-open-questions.md` | 承接規格化過程中新增的實作細節問題 |

## 狀態說明

| 符號 | 意義 |
|------|------|
| 🔴 尚未定案 | 問題已提出，但尚未形成可執行決策 |
| 🟡 討論中 | 已有初步方向，仍需補充規則或確認邊界 |
| 🟢 已定案 | 已形成可落地的決策，可據此實作 |
| ⚫ 已取消 | 議題不再適用或已被其他方案取代 |

## 已產出規格文件

以下規格文件已從決策討論中衍生，可直接作為實作依據：

| 文件 | 說明 | 依賴決策 |
|------|------|----------|
| [`docs/specs/MOST-core-algorithm-spec.md`](../specs/MOST-core-algorithm-spec.md) | 不可變動的 MOST 核心算法規格、驗證與測試案例 | — |
| [`docs/specs/system-architecture-v2-spec.md`](../specs/system-architecture-v2-spec.md) | 目標系統架構 v2（定點重建） | — |
| [`docs/specs/minimost-sequence-model-core-logic-spec.md`](../specs/minimost-sequence-model-core-logic-spec.md) | MiniMOST Sequence Model 核心邏輯 | OQ-001 |
| [`docs/specs/level-system-core-logic-spec.md`](../specs/level-system-core-logic-spec.md) | Level System 核心邏輯（含對 LB 輸出合約） | OQ-001 |

> 註：phase1/phase1a 規格已隨 legacy 移除（2026-06-21）。

---

## 使用方式

當某個議題有新結論時，請在對應文件中更新：

1. `Status`
2. `Discussion Notes`
3. `Open Questions`
4. `Resolution`

若某項結論已可直接影響實作，請在 commit message、PR 描述或程式註解中引用對應編號。

示例：`implements OQ-001: Phase 1 採 MiniMOST、保留 MaxiMOST 擴充點`
