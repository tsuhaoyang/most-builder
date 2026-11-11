# ADR-017: 組件庫 motion_modules — 合併範本與 v3 MI 語句概念

**狀態：** proposed
**日期：** 2026-07-04
**關聯：** [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)、[ADR-016](ADR-016-search-infrastructure.md)、[ADR-022](ADR-022-workbench-two-layer-correction.md)

## 脈絡

v3 的核心使用邏輯（IE 認證）：做好 MI 語句（多 cycle）存庫 → 關鍵字搜 → 組裝工序表（加入時快照、留 provenance、不回寫）。v2 既有 `motion_templates` 是單 cycle 範本。兩者概念重疊，直接並存會形成「兩套範本體系」——違反單一真相／反漂移原則。

## 決策

合併為單一組件庫：`motion_modules`（主檔，scope personal/site/global）＋ `motion_module_versions`（不可變發布版本，rows=有序 CycleIn 陣列，1 列＝舊範本、n 列＝MI 語句）；加入工序表＝**實體化複製**成 WiRow＋MostCycle 並記 provenance 兩欄；既有 `motion_templates` 以 migration 轉入後分步退役。

## 考慮過的選項

- **A. 照搬 v3 三表（MiStatement/StatementSequence/StatementItem）** — 與 motion_templates 平行重疊、v3 需自維護 `_recalculate_project_totals` 平行合計邏輯；否決。
- **B. 只做工序表列複製、不建庫** — IE 已養成的存庫/搜庫工作流退化；否決。
- **C. 統一組件庫（選定）** — registry 模式（發布不可變版本＋使用端快照）與 rule-set 快照哲學同構；實體化後即普通 WiRow，工時（含 SIMO 引擎 max）、Level 標註、LB 輸出、匯出**全走既有機制，零平行邏輯**。

## 後果

- 好處：一個庫、一套治理（draft/standard、promote 審核）；檢索統一走 ADR-016 基建。
- 代價：motion_templates 轉移 migration 與一個 phase 的唯讀退役期（舊 API 410）；「模組更新 vs 已實體化列」僅提示不同步（刻意——工時文件必須快照）。
- 邊界：publish 時引擎驗算，total/narrative 不接受呼叫端提供；實體化以 worksheet 當前 rule-set 重算並回 `tmu_drift` 警示。
