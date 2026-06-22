# ADR-013: Excel 匯入架構（資料驅動 + 暫存 + 預覽）

**狀態：** accepted
**日期：** 2026-06-21
**關聯：** [../roadmap/phase2-cross-system-data-alignment-spec.md](../roadmap/phase2-cross-system-data-alignment-spec.md)、[ADR-011-schema-evolution-and-contract-stability.md](ADR-011-schema-evolution-and-contract-stability.md)、[integration-lb-import skill]

## 脈絡

Phase 2 要從外部 Excel（如 Touchtime）匯入工序。難點：**來源格式不固定**（不同廠/檔欄位與版面不同、表頭不在第一列、多分頁、重複欄），而且**業務邏輯尚未定**（匯入列如何變成工時表、量測工時與 MOST 的關係還沒拍板）。直接寫死某格式的 parser，或直接灌進核心工時表，都會脆弱且污染核心。

## 決策

採 **資料驅動(profile) + 暫存(staging) + 預覽確認** 的匯入管線，且**增量**實作：

- **格式邏輯放成資料**：欄位對應是 runtime 的 **mapping profile**（可存可重用），不寫死欄位位置。新格式＝加一筆 profile，不改程式（呼應「規則是資料」）。
- **暫存緩衝**：上傳資料先落 staging（`excel_imports.raw_payload` JSONB，仿既有 `bom_imports`），**不直接進 worksheet**。轉換規則可隨業務邏輯演進而不污染核心。
- **人工預覽確認**：使用者選分頁/表頭列、配欄位、預覽正規化結果後才下一步。
- **容錯**：壞列跳過/標記，不整批失敗；缺欄留空。
- **增量**：
  - **2a（本次）**：ingest → staging（上傳/分頁表頭/欄位對應/profile/預覽）。格式無關。
  - **2b（之後，待業務邏輯明確）**：enrich（關鍵字→MOST 草稿，用既有 `/match`）+ 提交政策（staged → worksheet 列、量測工時 vs MOST 權威）。

## 考慮過的選項

- **A. 寫死各格式 parser** — 脆弱，新格式就改碼。否決。
- **B. 直接灌進 worksheet** — 簡單但髒資料污染核心、業務邏輯未定時難回退。否決。
- **C. profile + staging + 預覽（選定）** — 彈性、隔離、可演進；代價是多一層 staging 與對應 UI。

## 後果

- **資料模型（加法）**：新增 `excel_imports`(staging：raw_payload/sheet/header_row/column_map/staged_rows/status) 與 `import_profiles`(可重用欄位對應)；worksheet `provenance` CHECK 加 `'imported'`（為 2b 預留）。migration v2_0008，符合 ADR-011。
- **MOST 權威不變**：2a 只進 staging；worksheet 仍單一真相，提交政策留 2b 再定。
- **彈性**：每種來源樣式一個 profile；新樣式不改碼。
- **與既有契合**：仿 `bom_imports` staging；enrich 用既有範本庫 `/match`（[[integration-lb-import]]）。
- **風險/待 2b**：staged 列如何變 worksheet 列、量測工時的去留、profile 自動辨識（signature）——皆 2b 處理。

## 待後續決（2b）

匯入列→worksheet 的提交政策、量測工時 vs MOST 權威的呈現、profile 自動辨識、BOM→工序 cookbook 對接。
