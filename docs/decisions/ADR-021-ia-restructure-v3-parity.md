# ADR-021：資訊架構重構 — 以 v3 IA 為母版

- **狀態**：Accepted（使用者/IE 裁決於 2026-07-13）
- **決策者**：Howard（IE）＋ 審查總召
- **關聯**：[Frontend UX Spec](../architecture/frontend-ux-spec.md)、ADR-014（值權威）、ADR-022（後續工作台修正）
- **本文件是所有前端派工的必讀母版。任何前端 agent 動工前必須讀完本文件。**

## 背景：移植為什麼走偏了

v3 → v2 移植過去以「功能清單」方式執行：每個 F-XX 規格由獨立 agent 實作成**新增的 tab**，而非**取代** v2 既有架構。結果 v2 側欄膨脹到 11 項、出現兩套平行的建模工作台（worksheet 模式的「MOST 工作台」vs module 模式的「WI 組裝」）、v2 遺留的「目錄／匯出」佔據頂層、WorksheetBar 強制出現在每一頁。使用者實測後裁定：**v3 的資訊架構是驗證過的 UX 權威，v2 必須收斂到 v3 的形狀**。

根因（防止再犯）：
1. CLAUDE.md 曾把 `docs/html_con/v2-workbench.html`（v2 舊原型）當 UI reference——**已廢止，UI 母版改為 v3 畫面與本 ADR**。
2. 垂直切片派工無 IA 所有者——此後 IA 變更一律以本 ADR 為準，協調者為 IA 所有者。
3. UX 無驗收關卡——此後前端派工必附 **Playwright 截圖對照 v3 對應頁**，由協調者親自核圖。
4. `[SPEC GAP]` 型測試（斷言缺口存在而通過）——一律翻轉為正向斷言。

## 決策：目標資訊架構

### 側欄（一般使用者 7 項＋admin 2 項，順序固定）

| # | 項目 | 內容 | 對應現有程式 |
|---|---|---|---|
| 1 | 儀表板 | 啟用 rule-set 卡＋案件狀態統計＋近期案件（v3 DashboardPage 的最小對等） | 新建 `features/dashboard/` |
| 2 | MOST 工作台 | **三層組裝工作台**（動作模組工作區／WI 組成工作區／製程途程工作區） | `features/workbench-v3/`（改 nav id 與標題，去掉「WI 組裝」名稱） |
| 3 | WI 專案建立 | WI Set 專案組裝 | `features/wi-project/`（不動） |
| 4 | Level System | R1–R9（v2 超前 v3，保留） | `features/level-system/`（不動） |
| 5 | 分析案件 | 案件清單＋**案件編輯情境**（吸收 worksheet 編輯器＋匯出） | `features/cases/`＋`features/wi-workbench/`（見下） |
| 6 | 字典管理 | 詞彙庫＋範本 | `features/dictionaries/`（不動） |
| 7 | 使用者管理 | admin | `features/users/`（不動） |
| 8 | Rule-set（admin） | rule-set 檢視 | `features/rule-set/`（不動） |
| 9 | 字典管理權限依 rbac-spec 裁定（現為 analyst+） | | |

### 移除的頂層項目與去向

| 移除 | 去向 |
|---|---|
| 「WI 組裝」名稱 | 改名為「MOST 工作台」（元件不動，語意取代） |
| 舊「MOST 工作台」（WiWorkbench worksheet 編輯器） | 移入「分析案件 → 開啟案件 → 工時表編輯」情境頁；**不再是頂層 tab** |
| 目錄（CatalogPanel） | 頂層移除；案件建立時的階層選擇（產品/SKU/工序表）收進分析案件的「新建案件」流程 |
| 匯出（ExportPanel） | 頂層移除；匯出動作（wi-preview/excel/lb-csv/lb-api/report.xlsx）併入分析案件詳情的操作區 |
| 匯入 Excel（header 按鈕） | 保留 header（全域工具），不動 |

### WorksheetBar 去全域化

`App.tsx` 不再全域渲染 `<WorksheetBar/>`。工序表情境（產品/SKU/工序表選擇＋新建）只存在於「分析案件」的編輯情境內。MOST 工作台、WI 專案建立等頁**不得**出現 WorksheetBar。

### 「MOST 工作台」Tab1 的目標形態（v3 MostWorkbenchPage 單頁流）

由上而下（參照 v3 截圖 `/home/howard/workspace/most-builder/v3-most-workbench-full.png`）：
1. **AI 快速建模列**：NL 輸入＋「AI 預填」；編輯器有內容時詢問「覆蓋／只填空白」
2. **摘要列**（常駐）：動作類型｜使用手｜基礎 TMU｜頻率｜有效 TMU｜CT(秒)｜SIMO｜納入總時間｜MI 語句（即時更新）
3. **交錯句型列**：`使用手(紫)｜從哪裡(米黃)｜A1｜B1｜G｜目標物｜元件｜A2｜B2｜P｜到哪裡｜A3`（GM）；CM 為 `…｜M｜到哪裡｜X｜I｜哪裡｜A3`。情境欄位嵌在格位之間，同一 flex-wrap 流
4. **WI 語句覆寫輸入**＋「新增動作／清空」
5. **動作清單**：搜尋框＋筆數＋合計；12 欄表格（既有 MiCompositionTable 樣式）；列操作 ✏️編輯（載回建立器）／📋複製／✕刪除（確認）
6. **模組 Pool**（可搜尋，即「搜尋 pooling 動作」）與 **WI 組成器**維持在同一工作區內可達
7. Tab2（WI 組成）／Tab3（製程途程）維持三層組裝語意

### 分析案件的目標形態

- 清單（現有 CasesPage 左欄）→ 點擊案件 → 詳情含：狀態流（簽核/退役）、**「編輯工時表」進入 WiWorkbench**（帶該案件的 worksheet 上下文）、匯出操作區、稽核歷程
- 「新建案件」= 選產品/SKU → 建工序表（原 WorksheetBar 的 +新建工序表 流程）

## 驗收協定（每個 Phase 硬性要求）

1. agent 交付必附 Playwright 全頁截圖（v2 結果），協調者親自與 v3 對應頁比對後才算通過
2. `npm run typecheck`＋`npm run build` 綠
3. code-reviewer 過 → 才 commit
4. 既有功能不得回歸：11→7 收斂後，被移走的功能必須在新位置可用（匯出四種格式、階層瀏覽、worksheet 編輯全流程）

## 實施順序

- Phase 1：側欄收斂＋最小儀表板＋目錄/匯出收納（不動工作台內部）
- Phase 2：MOST 工作台 Tab1 升級 v3 單頁流
- Phase 3：分析案件吸收 worksheet 編輯器；WorksheetBar 去全域化
- 每 Phase 獨立 commit，可獨立回退
