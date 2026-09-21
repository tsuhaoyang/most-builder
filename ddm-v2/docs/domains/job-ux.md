# 領域索引：job-ux — 作業版（Level System job-oriented UX，反投影）

## 一句話
把 IE 詞彙的 Level System 包成只講「作業／步驟／順序」的 UI；作業視圖是 store 的純函式反投影，不接 LLM。

## 權威文件
- [`LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`](../lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md)
- [ADR-035 D10](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md)（D10 作業版兩層視圖、同一 store）

## 決策（相關 ADR）
- [ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md) — D10 修訂：作業版（預設）＋進階檢視（IE），反投影形式定義

## 程式入口
- 路徑：`src/frontend/src/features/level-system/**`（`LevelSystem.tsx`、`JobsShell.tsx`、`JobsFlow.tsx`、`JobDrawer.tsx`、`Notices.tsx`、`notices.ts`、`LineView.tsx`、`WritebackPanel.tsx`（LB 回寫實際結果區塊，ADR-036 F2）、`DevGrid.tsx`、`AdvancedView.tsx`、`jobs.ts`、`jobsActions.ts`、`jobsModel.ts`、`layers.ts`、`store.ts`、`logic.ts`、`api.ts`）
- graphify 錨點：`jobsFromStore`、`JobsShell`、`derive`、`buildNotices`、`applyBaseline`、`useLbPreview`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- store（`useLevelStore`）：`levelMap`（每列 `LevelCell`：coefficient/level/countersignature/workerCub/offline/segment/stationPin/isGeneral/generalRole/mergeLock/actionType/machineUnattended）、`groupMeta`、`workerCubMeta`。
- 反投影模型：`Job {steps, generalSteps, discrete, sameStation, samePerson, offline, pin, cub/sub/wcubLabel}`、`layers`。
- 預覽：`POST …/export/lb-report/preview`（dry-run）；四個是非題＝同站／同人一口氣／離線先做／固定站。
- 不變量狀態：hydrate/baseline 完成前不發預覽（避免 `E_LEVEL_INVALID` 閃錯）；`buildSaveBody` 保留 derive 的 null 層級。

## 不變量
見 `docs/agent-team/domains.yaml` domain `job-ux` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：e2e `level-jobs-logic.spec.ts`（純邏輯 19）、`level-jobs-golden.spec.ts`（DoD-1 兩路徑）、`level-jobs-ui.spec.ts`、`level-jobs-f7.spec.ts`、`level-jobs-plaindiag.spec.ts`、`level-hydrate-tags.spec.ts`、`writeback-line-view.spec.ts`（回寫區塊顯示＋套用離線）、`level-jobs-screenshot.spec.ts`（設計截圖；預設寫 `test-results/`，`UPDATE_SCREENSHOTS=1` 才覆寫 `docs/lb-integration/screenshots/`）。
- 缺口：~~無（剛落地，文件齊備）。~~ 回寫區塊（ADR-036 F2）：UI 尚未顯示件數不符／無法比對的警告，且 `GET latest` 的任何讀取錯誤都顯示「尚無結果」引導文案——清單見 [LB 回寫消費實作書](../lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md) §7。
