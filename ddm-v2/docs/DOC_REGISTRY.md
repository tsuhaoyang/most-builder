# 文件索引（Document Registry）

> **版本：alpha** — MOST（MiniMOST）工時量測平台 v2 文件。
> 依用途分類：核心邏輯 / 架構 / 決策 / 路線圖 / 使用者規格 / 參考 / UI。

## 目錄結構

```
docs/
├── core-logic/      核心邏輯（權威）：MOST 計算、Level System、驗證
├── architecture/    系統架構、資料模型、前端資料流、RBAC
├── decisions/       決策記錄（OQ / ADR）
├── roadmap/         路線圖草案（phase2）
├── user-spec/       使用者提供的規格草案
├── reference/       維運/參考筆記
├── sample_excel/    權威來源資料（1205 / 1128）
└── html_con/        前端原型（preview_server 提供）
```

## 狀態說明

| 符號 | 意義 |
|------|------|
| ✅ 完成 | 可作為實作依據 |
| 🔄 進行中 | 仍在撰寫/待更新 |
| 📌 參考 | 唯讀參考，不應修改 |

---

## core-logic/（核心邏輯 — 權威）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [minimost-sequence-model-core-logic-spec.md](core-logic/minimost-sequence-model-core-logic-spec.md) | MiniMOST Sequence Model（GM/CM 七格、A/B/G/P/M/X/I 查表、TMU 口徑、敘事、SIMO） | ✅ v1.0 |
| [level-system-core-logic-spec.md](core-logic/level-system-core-logic-spec.md) | Level System（main/sub/cub/nb、變動主序 `~`/`/`、R1–R9、巢狀 sub⊃cub、對 LB 輸出合約） | ✅ v1.x |
| [core-logic-validation-test-catalog.md](core-logic/core-logic-validation-test-catalog.md) | 核心邏輯驗證測試目錄（黃金集＋反例＋edge case） | ✅ v1.0 |
| [MOST-core-algorithm-spec.md](core-logic/MOST-core-algorithm-spec.md) | MOST 核心算法規格（核心參考） | 📌 參考 |

## architecture/（架構）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [system-architecture-v2-spec.md](architecture/system-architecture-v2-spec.md) | 目標系統架構 v2（定點重建）：單一權威引擎、rule-set 版本化、SPA、LB 輸出合約 | 🔄 v0.x |
| [data-model-and-storage-spec.md](architecture/data-model-and-storage-spec.md) | 資料模型與儲存（廠區→產品→SKU→version→工序單→level、儲存策略、生命週期） | 🔄 v0.x |
| [frontend-data-flow-spec.md](architecture/frontend-data-flow-spec.md) | 前端資料流（DTO/狀態、cycle 編輯迴圈、Level 同步、錯誤碼→UI） | 🔄 v0.x |
| [rbac-spec.md](architecture/rbac-spec.md) | RBAC（聯邦認證 Traefik ForwardAuth + 本地角色 IE/manager/admin） | ✅ v1.0（已實作） |

## decisions/（決策記錄）

OQ-001~006、ADR-010~013：見 [decisions/README.md](decisions/README.md)。（ADR-012 3D 渲染架構、ADR-013 Excel 匯入架構）

## roadmap/（路線圖草案）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [phase2-ui-ia-rbac-masterdata-architecture.md](roadmap/phase2-ui-ia-rbac-masterdata-architecture.md) | IA／topology／群組／手勢（部分已決） | 🔄 草案 |
| [phase2-cross-system-data-alignment-spec.md](roadmap/phase2-cross-system-data-alignment-spec.md) | 跨系統數據對齊 | 🔄 草案 |
| [phase5-i18n-full-bilingual-spec.md](roadmap/phase5-i18n-full-bilingual-spec.md) | Phase 5：全面多語系（中/英） | 🔄 草案 |

## user-spec/（使用者規格草案）

| 文件 | 主旨 | 狀態 |
|------|------|------|
| [minimost-database-schema-design.md](user-spec/minimost-database-schema-design.md) | MiniMOST 主數據與循環 ER／表結構草案 | 🔄 草案 |
| [minimost-operational-flow-and-examples.md](user-spec/minimost-operational-flow-and-examples.md) | MiniMOST 操作流程、選項、GM/CM 教學範例 | 🔄 草案 |
| [backstage_spec.md](user-spec/backstage_spec.md) | 後台規格 | 🔄 草案 |

## reference/ + 資料 + UI

| 項目 | 主旨 |
|------|------|
| [reference/docker-data-persistence.zh-TW.md](reference/docker-data-persistence.zh-TW.md) | Docker 映像 vs volume 資料持久化 |
| [sample_excel/](sample_excel/) | 權威來源（1205.xlsx＝Level System、1128＝WI 範本） |
| [html_con/v2-workbench.html](html_con/v2-workbench.html) | 現役單頁多分頁 workbench（preview_server `/`） |
| [html_con/v2-wi-preview.html](html_con/v2-wi-preview.html) | 單列聚焦版（preview_server `/single`） |

---

*最後更新：2026-06-21（alpha：docs 結構化分類）*
