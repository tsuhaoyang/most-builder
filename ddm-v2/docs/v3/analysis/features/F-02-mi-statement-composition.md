# F-02：MI 語句組合（一代；收斂進組件庫——可執行功能規格）

> 分類：功能 ｜ 相依：CL-02、CL-04 ｜ 證據：api-inventory-workbench §mi-statements、frontend-usage-flows §B3
> ⚠️ **收斂註記（DISC-01）**：本功能是三層組裝（F-03）的前身；v2 不建獨立 MiStatement 資料層，其使用邏輯由 `motion_modules`（rows>1 的模組）承載。本文件保留的是**行為規格**（快照/重算/子項編輯），供 F-03 與 impl-04 實作引用。

## 1. 使用邏輯（保真）

IE 在序列清單多選數列 → 命名（未填則以句子串接前 80 字自動命名）→ 存成一句 MI（WI 語句）→ 之後可展開子項逐一微調（slot/frequency/SIMO/context），微調**不回寫**來源序列。

## 2. 行為規則（v3 驗證過的快照機制，照抄為規格）

1. **建立即快照**：組合時把每條來源序列複製成獨立子項（slot_inputs＋context＋計算快照＋句子），記 `source_id` 僅作 provenance；來源之後刪改不影響本 MI。
2. **子項編輯**：改子項任何輸入 → 該子項重算（CL-01）→ 整句 MI 重組（子項句以「；」串接為系統句）→ totals 重聚合（CL-04；v3 一代用 calculate_analysis_total 正確排 SIMO——此行為保留）。標 `is_modified_from_source=true`。
3. **排序**：子項 order 連續 0..n-1；reorder 收 ordered_ids 全量替換；刪除後重排連續。
4. （v3 實況：子項是**延遲 backfill**——首次讀取才建快照。v2 不採延遲：建立當下即快照，行為更可預期。）

## 3. v2 落地對映

| v3 | v2 |
|---|---|
| MostMiStatement＋Items | `motion_modules`（rows = 子項陣列）＋`motion_module_versions`（impl-04） |
| 子項微調後另存 | 模組發新版（版本不可變） |
| 加入 WI Set | 實體化進 worksheet（F-04） |

## 4. 驗收條件

- Given 三條序列組成 MI，When 刪除其中一條來源序列，Then MI 子項與 totals 不變。
- Given 子項 frequency 2→3，Then 僅該子項 effective 變、MI totals 與系統句同步更新、is_modified_from_source=true。
- Given 子項含 SIMO 配對，Then MI totals 按 CL-04 group-max。
- Given reorder [c,a,b]，Then 讀回順序一致且 order 連續。
