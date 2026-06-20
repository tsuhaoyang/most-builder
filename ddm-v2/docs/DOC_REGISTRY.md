# 文件登錄表（Document Registry）

> 追蹤現役文件、狀態與主旨。
> （2026-06-21：已移除 phase1/phase1a 全部 legacy 規格與審查報告、legacy_specs/、舊 system-architecture-spec、html_con 舊原型。）

---

## 狀態說明

| 符號 | 意義 |
|------|------|
| ✅ 完成 | 文件已完成，可作為參考 |
| 🔄 進行中 | 文件仍在撰寫或待更新 |
| 📌 參考 | 唯讀參考文件，不應修改 |

---

## 核心邏輯 / 架構（docs/specs/）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [minimost-sequence-model-core-logic-spec.md](specs/minimost-sequence-model-core-logic-spec.md) | MiniMOST Sequence Model 核心邏輯（GM/CM 七格、A/B/G/P/M/X/I 查表、TMU 口徑、敘事、SIMO） | ✅ v1.0 |
| [level-system-core-logic-spec.md](specs/level-system-core-logic-spec.md) | Level System 核心邏輯（main/sub/cub/nb、深度階層、變動層級 `~`/`/`、R1–R9、巢狀 sub⊃cub、對 LB 輸出合約） | ✅ v1.x |
| [core-logic-validation-test-catalog.md](specs/core-logic-validation-test-catalog.md) | 核心邏輯驗證測試目錄（黃金集＋反例＋edge case） | ✅ v1.0 |
| [MOST-core-algorithm-spec.md](specs/MOST-core-algorithm-spec.md) | MOST 核心算法規格（核心參考） | 📌 參考 |
| [system-architecture-v2-spec.md](specs/system-architecture-v2-spec.md) | 目標系統架構 v2（定點重建）：架構決策、單一權威引擎、rule-set 版本化、SPA、LB 輸出合約 | 🔄 v0.x |
| [data-model-and-storage-spec.md](specs/data-model-and-storage-spec.md) | 資料模型與儲存設計（廠區→產品→SKU→version→工序單→level、儲存策略、生命週期） | 🔄 v0.x |
| [frontend-data-flow-spec.md](specs/frontend-data-flow-spec.md) | 前端資料流（DTO/狀態、cycle 編輯迴圈、Level 同步、錯誤碼→UI） | 🔄 v0.x |
| [rbac-spec.md](specs/rbac-spec.md) | RBAC（聯邦認證 Traefik ForwardAuth + 本地角色 IE/manager/admin、員工編號為鍵） | ✅ v1.0（已實作） |
| [phase2-ui-ia-rbac-masterdata-architecture.md](specs/phase2-ui-ia-rbac-masterdata-architecture.md) | Phase 2：IA／topology／群組／手勢（部分已決） | 🔄 草案 |
| [phase2-cross-system-data-alignment-spec.md](specs/phase2-cross-system-data-alignment-spec.md) | Phase 2：跨系統數據對齊 | 🔄 草案 |

---

## 決策記錄（docs/decisions/）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [OQ-001-most-system-selection.md](decisions/OQ-001-most-system-selection.md) | MOST 系統選型（MiniMOST 優先） | ✅ |
| [OQ-002-allowance-and-standard-time.md](decisions/OQ-002-allowance-and-standard-time.md) | Allowance 與 standard time | ✅ |
| [OQ-003-database-migration.md](decisions/OQ-003-database-migration.md) | DB 遷移策略（Alembic + PostgreSQL） | ✅ |
| [OQ-004-concurrent-access.md](decisions/OQ-004-concurrent-access.md) | 並發存取與鎖定 | ✅ |
| [OQ-005-custom-tool-elements.md](decisions/OQ-005-custom-tool-elements.md) | 自定義工具元素 | ✅ |
| [OQ-006-phase1-implementation-open-questions.md](decisions/OQ-006-phase1-implementation-open-questions.md) | 實作開放問題 | ✅ |
| [ADR-010-nl-to-most-backlog.md](decisions/ADR-010-nl-to-most-backlog.md) | 自然語言 → MOST：暫不實作 | ✅ |
| [ADR-011-schema-evolution-and-contract-stability.md](decisions/ADR-011-schema-evolution-and-contract-stability.md) | Schema 演進與合約穩定政策 | ✅ |
| [README.md](decisions/README.md) | 決策記錄目錄說明 | ✅ |

---

## 使用者規格（docs/user_spec/）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [minimost-database-schema-design.md](user_spec/minimost-database-schema-design.md) | MiniMOST sequence model 主數據與循環 ER／表結構草案 | 🔄 草案 |
| [minimost-operational-flow-and-examples.md](user_spec/minimost-operational-flow-and-examples.md) | MiniMOST 操作流程、G/P/M/X/I 選項、GM/CM 教學範例 | 🔄 草案 |
| [backstage_spec.md](user_spec/backstage_spec.md) | 後台規格 | 🔄 草案 |

---

## 其他

| 文件/目錄 | 主旨 |
|------|------|
| [docs/html_con/v2-workbench.html](html_con/v2-workbench.html) | 現役單頁多分頁 workbench（preview_server `/`） |
| [docs/html_con/v2-wi-preview.html](html_con/v2-wi-preview.html) | 單列聚焦版（preview_server `/single`） |
| [docs/sample_excel/](sample_excel/) | 權威來源資料（1205.xlsx＝Level System、1128＝WI 範本） |
| [docs/docker-data-persistence.zh-TW.md](docker-data-persistence.zh-TW.md) | Docker 映像 vs volume 資料持久化 |

---

*最後更新：2026-06-21 | 清理 legacy 文件*
