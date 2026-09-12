# Level System「作業版」原型（設計參考，2026-09-12）

可直接在瀏覽器開 `index.html`（無需伺服器）。對應實作書：`../../LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`。

| 檔 | 用途 | 正式版對應 |
|---|---|---|
| `index.html` | 作業順序／作業內容抽屜／系統看出來的事／產線視角／開發者表的互動流程與文案 | 實作書 §5 F3–F6、附錄 B |
| `jobs.js` | 作業模型 → 引擎狀態（`toEngineState`）、基線（`baseline`）、黃金對應的 12 個作業（`example`）、使用者語言訊息表（`MSG`／`HIDDEN`） | 附錄 A、§6.3、§7；正式版改為 store 的**反投影**（`jobsFromStore`），不是主狀態 |
| `engine.js` | 投影層的 JS 鏡像（tool 拆列、TMU 分桶、分層 DAG、驗證碼、`suggestions`），對黃金 CSV 逐位元相等 | **只用來理解**；正式版投影只在後端（實作書 §12-2 禁止移植） |
| `data.js` | 黃金 24 列＋風扇作業 3 列的 dummy 資料 | `fixtures/server_node_worksheet.json` |
| `test_jobs.js` | `node test_jobs.js`：驗證 `example()` 經 `toEngineState`＋`engine.project` 與黃金逐位元相等 | 實作書 §8.3 `level-jobs-logic.spec.ts` |

與正式版的刻意差異（不要照抄）：
1. 原型的 general 候選用關鍵字猜（`conveyor|next station|work order`、`part==='General'`）——正式版**禁止**（實作書 §12-1）。
2. 原型句子寫死中文——正式版全部走 i18n（§6）。
3. 原型的 job model 是主狀態、存 localStorage——正式版 store 為唯一真相，作業視圖是反投影，存檔走既有 `PUT /worksheets/{id}`。
4. 原型在前端算投影——正式版打 `POST …/export/lb-report/preview`（dry-run）。
