# ADR-036：LB 回寫消費——唯讀快照 ＋ 屬性回流走正門

## 狀態

🟡 **proposed**（2026-09-17，整合架構師撰寫；三項取捨已由 Howard 2026-09-17 裁決，見 §2 D1／D2／D5）。實作見 `docs/lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md`。

- **對應 LB 端**：`lb-most-writeback-v1`，定義於 LB `docs/dev_docs/MOST_INTEGRATION_INPUT_SPEC.md` §8（**該檔是回寫契約的唯一權威**；本 ADR 不重述欄位）、LB ADR-023 D11。LB 落地 commit `adb750b`＋`631e3a5`＋`02dba21`（分支 `feature/most-integration-phase2`，未合入 LB master）。
- **關聯**：[ADR-035](ADR-035-lb-projection-layer-and-motion-decomposition.md)（MOST→LB 投影；本 ADR 是反方向）、`docs/lb-integration/MOST_LB_CONTRACT.md` D13（屬性可雙向、結構單向）、[ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進）、[ADR-019](ADR-019-rbac-read-write-boundaries.md)（端點權限）、[ADR-034](ADR-034-language-aware-error-contract.md)（錯誤信封）。

---

## 1. 脈絡

MOST 匯出 24 欄 tasks.csv → LB 求解 → **使用者在 LB 端看到的結果，MOST 目前完全看不到**。IE 想知道「我建的這個 motion 最後被排到第幾站、誰做、批量怎麼分」只能兩邊對著看。

LB Phase 2 已提供唯讀端點 `GET /api/v3/projects/{p}/versions/{v}/results/{r}/writeback`：扁平 `rows[]`（每 task 一筆），以 `source_wi_row_id`（＝MOST `wi_rows.id`）為跨系統對應鍵，帶 `task_id`／`offline_flag`／`line_index`／`station_index`／`workers[]`／`units[]`，頂層帶 `unattended_machine_policy` 與 `..._source`。**不含 predecessors／group／duration 等結構欄**（D13：結構單向）。

D13 同時定下屬性回流規則：可回流的只有 `offline` 這類標籤，且**必須走 MOST 正門**（MOST 的驗證與組內傳染），不得直接寫 DB。

---

## 2. 決策

### D1 取得方式：MOST 伺服器端主動呼叫 LB（v1 直連，不經 gateway）
（Howard 2026-09-17 裁決）MOST 後端以 httpx 呼叫 LB 的 writeback 端點，前端只給 `project_id`／`version_id`／`result_id`。v1 **不處理 Traefik／forward-auth**：LB base URL 由設定給定（`DDM_LB_API_BASE_URL`），直連。

- 理由：本輪目標是**確認資料格式與解析正確**；認證整合是獨立工程（兩系統未來會走同一入口）。
- 設計約束：認證只能是**加法**——日後把 MOST 掛到 Traefik 之下時，唯一要改的是 base URL 與「帶上入站身分 header」，解析、資料模型、UI 一律不動。故 client 從一開始就支援可選的身分 header 透傳（`DDM_LB_AUTH_HEADER_NAME`／值取自當前使用者），v1 預設不帶。
- 設定缺失（`DDM_LB_API_BASE_URL` 未設）→ 503 ＋ 明確訊息（比照 `dsx_service` 既有慣例），不靜默失敗。
- 另保留 `import`（直接貼上／上傳 payload）路徑：**測試與離線驗證專用**，走同一套解析與驗證程式碼，避免測試繞過產品路徑。

### D2 屬性回流只有 `offline`，人工確認，走 MOST 正門
（Howard 裁決）匯入後列出「LB 的 `offline_flag` 與 MOST `level_entries.offline` 不一致」的列；IE 勾選後才套用。套用**重用既有存檔路徑的語意**：寫入 `level_entries.offline` 後跑 MOST 自己的組內傳染（同 cub／同 wcub）與 R1–R9 驗證，不得直接 UPDATE 繞過治理。

- 不自動套用的理由：LB 的結果編輯是 what-if 性質；自動覆蓋等於讓 LB 成為 MOST 屬性的第二權威，D13 明文禁止。
- `offline` 以外的欄位（`workers`／`station_index`／`units`／`line_index`）**一律唯讀**，只顯示、不回流。

### D3 結構欄不回流
`predecessors`／`group`／`atomic_group`／`duration` 等結構與工時欄，LB 端本就不輸出；MOST 端也不得從其他來源反推寫回。工序結構與 TMU 的權威永遠在 MOST（D13、ADR-014／028）。

### D4 回寫落地為**快照**，不是即時鏡像
每次取得存成一筆 `lb_writeback_snapshots`（含原始 payload）＋逐列 `lb_row_placements`。理由：(a) IE 看到的「是哪一次求解的結果」必須可追溯；(b) LB 結果會被重新求解或編輯，MOST 不該假裝自己有即時真相；(c) 契約升版時舊快照仍可解讀（原始 payload 留存）。
- 保留策略：同一 worksheet 保留最近 N＝10 筆，超出刪最舊（避免 payload 無限長大）。

### D5 顯示落點：作業版「產線視角」加一區
（Howard 裁決）不另開導覽項。作業版的產線視角本來就是「使用者看順序」的地方，把「實際排到第幾站、誰做」疊上去，並標出差異（離線不一致、同一 motion 跨站、LB 沒有結果的列）。進階檢視不動。

### D6 一個 motion 對多個 task 的聚合規則
投影層會把持工具 motion 拆成 acquire／use／release、general 列每站各插一份，因此同一 `source_wi_row_id` 可能對到多筆 row：
- **站別**：取所有 row 的 `station_index` 集合。集合大小 >1 → 標 `cross_station`（工具 episode 依 LB ADR-023 D3 應同站，跨站代表結果來自舊版或人工編輯）；general 列的多站是**預期**，不標異常。
- **人**：`workers` 取聯集。
- **件數**：`units` 僅 Q>1 出現，逐 worker 加總後與 MOST 的 `frequency`／`repeat_count` 對照，不一致 → 警告。
- **offline**：多筆若不一致 → 警告（LB 端本就要求同群組一致）。

### D7 驗證與失敗處理
- `contract_version != "lb-most-writeback-v1"` → **擋**（ADR-034 信封，`code=LB_WRITEBACK_CONTRACT_MISMATCH`）。
- `rows[].source_wi_row_id` 不屬於本 worksheet → **不擋**，記為 `unmatched`（可能是別的 worksheet 的結果）。
- worksheet 有列但回寫沒有 → 記為 `missing`（SIMO 從屬列本就不輸出；offline 列可能不在結果；IE 需要看得到）。
- LB 不可達／逾時 → 502／504 ＋ 原始狀態碼寫 log，不靜默當成空結果。

---

## 3. 被否決的方案

| 方案 | 否決理由 |
|---|---|
| 前端直接呼叫 LB API | 跨來源、需在瀏覽器持有 LB 憑證；且日後掛 gateway 時前端要改，違反 D1 的「認證只能是加法」 |
| 只存最新一份、覆蓋前一份 | 無法回答「IE 當時看到的是哪一次結果」；契約升版後舊資料不可解讀（D4） |
| 自動套用 LB 的 offline | LB 結果編輯是 what-if；自動覆蓋讓 LB 成為第二權威（D13 禁止） |
| 把站別／人員寫回 `wi_rows` 當屬性 | 那是求解結果不是工序屬性；寫回會讓下一次匯出把結果當輸入（循環） |

---

## 4. 後果

**正面**：IE 在 MOST 就能看到平衡結果並回答「我這步被排到哪」；offline 有了受控的回流路徑；快照可追溯。

**代價／風險**：多一組表與端點；v1 直連 LB 無認證——**只可在內網／本機使用**，掛 gateway 前不得對外開放（實作書列為禁止事項）；LB 分支尚未合入其 master，端點可用性依賴該分支部署。

**待裁決（不阻擋實作）**：是否讓回寫結果影響作業版的「秒數」顯示（目前秒數來自 MOST 投影預覽，非 LB 實際排程）；建議 v1 不混用，兩者分開顯示。
