# F-03：三層組裝——動作模組 → WI 範本 → 製程途程（可執行功能規格）

> 分類：功能 ｜ 相依：CL-01/02/04、[impl-04](../../impl/impl-04-motion-modules.md)（v2 資料載體） ｜ 證據：api-inventory-workbench §most_workbench_v3、frontend-usage-flows §B4
> **這是 v3 二代、canonical 的使用邏輯（DISC-01 ✅ 已定案，2026-07-05 User 裁決；詳解見 00 §2.1）**。⚠️ 用詞：三層是「組裝層級」，與 v2 Level System（main/sub/cub）無關（DISC-13）。
> 使用者故事：IE 把常用動作存成模組（L1），把模組組成 WI 範本（L2），再把 WI 排成製程途程（L3）；跨層皆「傳送→快照→可微調→顯式回寫」。

## 1. 三層語意與 v2 載體

| 層 | v3 概念 | 語意 | v2 載體 |
|---|---|---|---|
| L1 | Action Module | 單一動作（一條 cycle）的可重用範本 | `motion_modules`（rows 長度 1） |
| L2 | WI Template | 多模組組成的一句 WI（含子項快照） | `motion_modules`（rows 長度 n） |
| L3 | Process Route | WI 依工序排列的途程（**建立即快照**每個 WI 的完整內容） | `ProcessVersion`＋`MostWorksheet`（實體化列） |

## 2. 行為規則

1. **L1 模組**：由 F-01 編輯器「儲存為模組」建立；池支援搜尋、clone、刪除、拖拉排序（order 全量替換）；多選「傳送至 L2」。
2. **L2 組成**：Composer 收模組清單（可重複同一模組）→ 命名＋敘述 → 建立時**逐模組複製為子項快照**；totals 由子項按 CL-04 聚合。子項可 inspector 微調（重算該子項→重聚合）；clone 整個 WI。
3. **L3 途程**：收 WI 清單 → **建立即快照**每個 WI 的全部子項（含各模組內容）為途程項；途程項可排序/複製/刪除/微調；clone 整個途程。
4. **apply-back（顯式回寫）**：途程項改好後，IE 可把它回寫到來源 WI 範本——v2 語意＝**對該模組發布新版本**（owner/approver 限定；版本不可變，見 impl-04 §3；v3 實況為破壞性覆寫——DISC-09 不移植）。
5. **跨層傳送 UX**：多選→「傳送至下一層」→ 自動切換分頁並帶入待組清單（pending list）。
6. **快照不同步**：上層改動不回流下層、下層更新僅提示（provenance＋「模組已更新」badge），一律不自動同步。

## 3. API 合約（v2 落地）

| Method | Path | 目的 |
|---|---|---|
| POST/GET/PUT/DELETE | /api/v2/motion-modules（＋/{id}） | L1/L2 統一 CRUD（rows 1..n） |
| POST | /api/v2/motion-modules/{id}/publish、/clone、/versions/from-rows | 發版、複製、回寫發新版（=apply-back） |
| POST | /api/v2/worksheets/{wid}/rows/from-module | L3 實體化（批次建列＋tmu_drift 警示） |
| PUT | /api/v2/worksheets/{wid}（列 reorder 走既有 seq_no） | 途程排列 |

（v3 實況對照：/most/action-modules、/most/wi-templates、/most/process-routes 三組共 24 個 endpoints——完整清單見證據底稿。）

## 4. 驗證與錯誤

publish 空 rows→422；實體化 retired 模組→409；apply-back 非 owner→403、來源模組已刪→404；快照後來源刪除不影響既有途程（斷 provenance 僅提示）。

## 5. 驗收條件

- Given L1 模組 A（28 TMU），When 組成含 A×2 的 L2 WI，Then WI totals=56 且兩子項獨立可微調。
- Given L2 WI 加入 L3 後修改 WI 範本，Then 途程項不變、顯示「來源已更新」提示。
- Given 途程項微調後 apply-back，Then 來源模組 current_version+1、舊版本仍可讀。
- Given 非 owner apply-back，Then 403。
- Given clone 途程，Then 全部途程項深拷貝、totals 相等、與原途程互不影響。
