# 領域索引：excel-import — Excel／CSV 匯入

## 一句話
兩階段匯入（staging→submit）＋可重用欄位對應（profile）；建列填 wi_group；含 DSX 3D 擺放整合。

## 權威文件
- [ADR-013](../decisions/ADR-013-excel-import-architecture.md)（Excel 匯入架構——**僅骨架，偏薄**）
- ⚠️ **staging→submit 流程細節無完整 spec，現況以程式為準**（見 `docs/BACKLOG.md` **BL-DOC-5**）。

## 決策（相關 ADR）
- [ADR-013](../decisions/ADR-013-excel-import-architecture.md) — Excel 匯入架構（Phase 2a）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/{import_service,dsx_service,dsx_client}.py`、`src/ddm_v2/api/routes/v2/{import_excel,dsx}.py`、`src/ddm_v2/schemas/v2/{import_excel,dsx}.py`、`src/ddm_v2/models/v2/{import_staging,dsx_suggestion}.py`、`src/frontend/src/features/{import,export}/**`
- graphify 錨點：`import_service`、`TARGET_FIELDS`、`map_columns`、`submit_import`、`dsx_service`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- `TARGET_FIELDS`：`description`（必）、`part_no`、`hand`、`seconds`、`quantity`、`element_class`、`notes`、`wi_group`（ADR-035 D10）。
- staging：`excel_imports.staged_rows`、`import_profiles.column_map`（可重用）、`time_unit`。
- 提交：`column_map` 缺 `description` → 擋提交；rule-set 缺庫改用 active **必須在報告上說出來**（不得靜默改版）。

## 不變量
見 `docs/agent-team/domains.yaml` domain `excel-import` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_import.py`、`tests/unit/test_import_excel_wi_group.py`、`tests/integration/test_dsx*.py`。
- **缺口（BL-DOC-5）**：ADR-013 僅骨架，兩階段流程與欄位對應細節以程式為準。補 spec 需另行排程核准。
