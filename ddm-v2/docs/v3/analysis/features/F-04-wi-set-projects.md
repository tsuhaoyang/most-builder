# F-04：WI Set 專案——WI 收集與度量（可執行功能規格）

> 分類：功能 ｜ 相依：CL-04、F-03 ｜ 證據：api-inventory-workbench §wi_set_builder、frontend-usage-flows §B5
> ⚠️ 收斂註記（DISC-01）：一代收集器。其使用邏輯（元數據＋搜庫＋收集＋排序＋度量）在 v2 由 **ProcessVersion＋worksheet（F-03 L3）** 承載；本文件保留行為規格與元數據欄位需求。

## 1. 使用邏輯（保真）

IE 建專案（project_code/name/site/BU/process/family/model/description/status）→ 在 WI 庫以關鍵字搜尋（搜名稱與句子全文，含子動作句）→ 多選加入（**快照複製**，含名稱/句子/動作數/TMU/秒與完整內容 JSON）→ 拖拉排序、逐項備註 → 看 Summary（總 WI 數/總動作數/總 TMU/總秒）。

> **⚠️ 程式碼查證補充（C-13/C-15/C-16，2026-07-08）**
>
> **WI 庫的來源只有 MiStatement，不含 WITemplate。** `wi_set_builder.py list_wi_library()` 的查詢是：
>
> ```python
> """List old MOST workbench MI Statements (WI 大綱) as the WI Pool source."""
> query = db.query(MostMiStatement)
> ```
>
> WITemplate（三層二代）**不在 WI 庫內**。WISetProject 收集的是一代 MiStatement；ProcessRoute 收集的是二代 WITemplate——兩者是完全平行、互不相關的收集系統。
>
> `WISetProjectItem.source_wi_id` 雖然 model 注釋寫「Reference back to WITemplate」，實際儲存的是 `MostMiStatement.id`（見 `AddItemsRequest` 注釋："MostMiStatement IDs from old MOST workbench"）。
>
> **IE 生產 DB 實況**：minimost.db 中 13 筆 MiStatement 為真實伺服器組裝工序（DIMM、主板等）；13 筆 WISetProjectItem 全部對應這些 MiStatement。WITemplate 2 筆、ProcessRoute 1 筆均為測試資料。IE 真實工作流完全走一代路徑。

## 2. 行為規則

1. 加入＝快照；來源 WI 之後刪改不影響專案（provenance 僅供追溯）。
2. **Totals 一律由列快照按 CL-04 聚合**——(v3 實況：直接加總快照 totals **漏排 SIMO**，已確認為 bug（DISC-03），不移植；v2 實體化為 worksheet 列後由 compute_table 聚合，結構上免疫)。
3. 搜尋走檢索基建（ADR-016：L1 精確→L2 trgm→L3 語意），必分頁（DISC-10）。
4. 專案元數據欄位（site/BU/process/family/model）對映 v2 的 Site→Product→SKU 階層＋ProcessVersion 欄位；缺口（BU/family）以 SKU/Product 屬性欄補（migration 時併入 impl-04 範圍評估）。
5. duplicate 專案＝深拷貝全部項與元數據。

## 3. API 合約（v2 落地）

搜尋：`GET /api/v2/search?types=motion_module&q=`；收集/排序/移除/備註：即 worksheet 列操作（`rows/from-module`、seq_no、列 note 欄）；Summary：worksheet 讀取回應的 totals（normal/standard）。

## 4. 驗收條件

- Given 關鍵字「壓合」，Then 命中名稱或任一子句含「壓合」的 WI（分頁、含 TMU 預覽）。
- Given 加入含 SIMO 配對的 WI，Then 專案合計按 group-max（v3 bug 的回歸測試）。
- Given 來源 WI 刪除，Then 專案項完整、標示來源已失聯。
- Given duplicate 專案，Then 兩專案互不影響、totals 相等。
