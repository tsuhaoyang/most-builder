# ADR-036：LB 回寫消費——唯讀快照 ＋ 屬性回流走正門

## 狀態

🟢 **accepted**（2026-09-18，Howard 核可；三項取捨於 2026-09-17 裁決，見 §2 D1／D2／D5）。D6「件數」一條已於 2026-09-21 由整合架構師修訂（見 §2 D6 件數修訂）。實作見 `docs/lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md`。

- **對應 LB 端**：`lb-most-writeback-v1`，定義於 LB `docs/dev_docs/MOST_INTEGRATION_INPUT_SPEC.md` §8（**該檔是回寫契約的唯一權威**；本 ADR 不重述欄位）、LB ADR-023 D11。LB 落地 commit `adb750b`＋`631e3a5`＋`02dba21`；真機驗證另依賴 LB 兩個修正：`aac992f`（插回的 general 保留 `source_wi_row_id`，回寫不再漏 general）、`c0cb244`（上傳 CSV 標準化保留 MOST 擴充欄，見 §4）（皆在分支 `feature/most-integration-phase2`，未合入 LB master）。
- **關聯**：[ADR-035](ADR-035-lb-projection-layer-and-motion-decomposition.md)（MOST→LB 投影；本 ADR 是反方向）、`docs/lb-integration/MOST_LB_CONTRACT.md` D13（屬性可雙向、結構單向）、[ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進）、[ADR-019](ADR-019-worksheet-access-control.md)（端點權限）、[ADR-034](ADR-034-language-aware-error-contract.md)（錯誤信封）。

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

> **D1 追記（2026-09-18，真機驗證發現）**：本節原寫「v1 直連、預設不帶身分 header」——**前提不成立**。實測（LB Phase 2 以 uvicorn 直跑 `:8090`，不經 Traefik）：LB **應用程式本身**就檢查 gateway 身分 header，最小需求是 **三個都要**——`X-User-Id`、`X-Plant-Code`、`X-Username`，缺任一 → 401（writeback 讀取端點亦然）。故 v1 即須帶 header：MOST client 的 `DDM_LB_AUTH_HEADER_NAME`（單一 header）擴為**可設定一組 header**（名稱→值，值可為固定字串或當前使用者員編）。這仍符合本節的「認證只能是加法」——日後掛 Traefik 時只換 base URL 與 header 值來源，解析／資料模型／UI 不動。證據：`GET …/writeback` 帶三 header → 200、少任一 → 401。header **值**的預設配置（`X-User-Id`／`X-Username` 用 `@me`、固定字串屬例外）見 §4〈身分 header 的限制與預設配置〉，本節不重述。

### D2 屬性回流只有 `offline`，人工確認，走 MOST 正門
（Howard 裁決）匯入後列出「LB 的 `offline_flag` 與 MOST `level_entries.offline` 不一致」的列；IE 勾選後才套用。套用**重用既有存檔路徑的語意**：寫入 `level_entries.offline` 後跑 MOST 自己的組內傳染（同 cub／同 wcub）與 R1–R9 驗證，不得直接 UPDATE 繞過治理。

- 不自動套用的理由：LB 的結果編輯是 what-if 性質；自動覆蓋等於讓 LB 成為 MOST 屬性的第二權威，D13 明文禁止。
- `offline` 以外的欄位（`workers`／`station_index`／`units`／`line_index`）**一律唯讀**，只顯示、不回流。

> **D2 追記（2026-09-21，Howard 裁：維持此行為、本輪不重構投影層；`a85d89d`＋`603b83f`）：正門的「投影 E 關」在跑不起來時被跳過，而不是擋下。**
> 本節的「走正門」原本是無條件的——寫入 → 組內傳染 → R1–R9 → 投影報告（`lb_export_report`）的 E 碼，任一 E 整批 rollback。現況多了一個條件：
> - **被跳過的只有「投影報告的 E 碼」那一關**。寫入 `level_entries.offline`、組內傳染、R1–R9 一律照跑；投影**收集到**的 E 碼也照常整批 rollback ＋ 422。只有投影**拋例外**（逃得出投影的三類，見 §2 D7 追記 2026-09-21 第 5 點）時這一關**無從判定**——不是判定為「沒問題」。
> - **為什麼不 rollback**：那幾類例外反映的是 MOST 端工序此刻投影不出來，與使用者要套用的 `offline` 標記無關；連帶取消離線設定，等於用一個使用者無法自行解決的狀況，擋住一件本來就該做的事。故改採 `fetch` 的 `units_baseline` 同一套降級模式：照常套用，但把「這一關沒跑」在回應與留痕裡**明講**（`report.status="unavailable"` ＋ E 碼；欄位形狀見實作書 §2 B6，本節不重述）。**這是 fail-open**，取捨與翻轉風險見 §2 D7 追記（2026-09-21）第 5 點。
> - **留痕在哪**：`lb_writeback_snapshots.applied_rows`（套用者、報告狀態、E 碼、完整診斷）。這條路徑**沒有任何稽核寫入**，`applied_rows` 是唯一的痕跡；由 `latest`／`snapshots` 帶出。
> - **留痕的保存期限＝該快照的壽命**：依 D4 每 worksheet 只留最近 10 筆（按 `fetched_at` 排序，**不看有沒有套用紀錄**），第 11 次 `fetch` 起最舊的一筆連同它的 `applied_rows` 一併刪除——**該次降級的紀錄就此消失，事後無處可查**。要長期保存得另開稽核，本輪未做。

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
- **件數**：`units` 僅 Q>1 出現，**不可跨 row 加總**（理由見下方修訂追記）。取值：先逐 row 把 `units[]` 的各 worker 值相加（同一 row 可能多人分攤），再依 `qty_scope` 取值——
  - payload 有 `qty_scope`（LB §8 加欄後）→ 取 `qty_scope == "cyclic"` 的 row 值（持工具 motion 的 use 列為 cyclic；若多列皆 cyclic 且值相同，取 max）。標 `units_source=cyclic`＝**確定值**。
  - payload 無 `qty_scope`（舊快照／LB 尚未加欄）→ 取各 row 值的**最大值**（cyclic 列的 Σ＝Q ≥ setup 列的 Σ＝經手人數）。標 `units_source=inferred_max`＝**推算值，UI 必須標示**。
  - 有 `qty_scope` 但無任何 cyclic 列、或無任何 row 帶 `units` → 無件數。
- **件數的比對基準**：與 **MOST 自己投影出的 `quantity` Q**（契約 §3.2 實際送給 LB 的值）對照，**不是** motion 層的 `frequency`／`repeat_count`。基準狀態三選一，寫在 `summary.units_baseline.status`：
  - `ok`＝已用投影 Q 比對；兩邊都有值且不符 → `diff.unit_mismatches`（警告）。
  - `unavailable`＝MOST 此刻投影不出來（投影拋出或帶 E 碼，`reasons` 附 E 碼）→ **不得讀成「一致」**，端點仍回 200。
  - `not_needed`＝投影結果沒有任何 Q>1 的 motion。
  - MOST 投影 Q>1、LB 卻沒給件數（非 offline）→ 列入 `diff.units_uncomparable` 明列，不靜默略過。
  - 判斷一律以 **MOST 投影**為準，不從「LB 沒帶 units」反推不必比（LB 對 Q>1 也可能不帶 units）。
- **offline**：多筆若不一致 → 警告（LB 端本就要求同群組一致）。

> **D6 件數修訂（2026-09-21，整合架構師；裁決 2026-09-18 Howard「C＋退路」，實作 `79d8e4f`）**
> 原文為「逐 worker 加總後與 MOST 的 `frequency`／`repeat_count` 對照」，**有兩處錯**，已改寫於上：
> 1. **跨 row 加總錯**。依 LB 端 `docs/adr/ADR-008`（quantity lot `units[s,w]`）D3，Q>1 lot 的 **setup 列**（acquire／release）`units` 記的是 `used`（0／1，跨 worker 加總＝經手人數），**只有 cyclic 列才是件數**。黃金複本動作 I（`electric_driver`，Q=8）三列回 1／8／1，逐列加總得 **10**，實為 **8**。
> 2. **比對基準錯**。`frequency` 是 motion 層的次數；投影會把持工具 motion 拆成三列，拿 `frequency` 比會對「持工具且 F>1」產生 3F 的假警報。基準應為投影後的 Q。
> 缺陷為 2026-09-18 真機複驗（§4）所暴露；此前未被發現，是因為比對只看 `frequency` 一欄。
> **跨 repo 未結項**：LB `MOST_INTEGRATION_INPUT_SPEC.md` §8 尚未定義 `rows[].qty_scope`（LB 端票 B20）。補上前 MOST 顯示的件數一律是 `inferred_max` 推算值。值域必須釘死為小寫 `setup`／`cyclic`、Q=1 不輸出該欄（null）、不得出現 `auto` 等第三值——否則依 D7 追記（2026-09-18）第 2 點會整份 422。
> 已知限制（UI 覆蓋範圍等）見 [實作書](../lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md) §7，本 ADR 不重述。

### D7 驗證與失敗處理
- `contract_version != "lb-most-writeback-v1"` → **擋**（ADR-034 信封，`code=LB_WRITEBACK_CONTRACT_MISMATCH`）。
- `rows[].source_wi_row_id` 不屬於本 worksheet → **不擋**，記為 `unmatched`（可能是別的 worksheet 的結果）。
- worksheet 有列但回寫沒有 → 記為 `missing`（SIMO 從屬列本就不輸出；offline 列可能不在結果；IE 需要看得到）。
- LB 不可達／逾時 → 502／504 ＋ 原始狀態碼寫 log，不靜默當成空結果。

> **D7 追記（2026-09-18，Howard 裁決）**：以下一律回 **422**（ADR-034 信封，`code=VALIDATION_ERROR`）。
> 1. **LB 座標格式**：`lb_project_id`／`lb_version_id`／`lb_result_id` 必須符合 `^[A-Za-z0-9_-]{1,64}$`，不合 → 422、**不呼叫 LB**。理由：三個座標直接成為 LB URL 的路徑段，`/`、`..`、`%2F`、`?`、`#` 等可把請求改寫成 LB 主機上的任意路徑、且帶著身分 header 發 GET；只做 URL 編碼仍可能打到別的路徑，故擋在驗證。這是對 LB id 格式的**假設**（LB 現行 project＝32 位 hex、version＝`original`／`v_<hex>`、result＝UUID，皆在集合內）；LB 若改 id 格式須先同步本條。client 以同一規則再擋一次（縱深防線）。
> 2. **`rows[].qty_scope` 值域**：只收 `setup`／`cyclic` 或缺欄（null）；其他值（含大小寫不符、空字串、`auto`）→ 整份 422、不存快照。理由：未知值會讓件數取值（D6 件數註記）失真，寧可擋下也不猜。
> 3. **`rows[].source_wi_row_id` 不是 UUID** → 整份 422、不存快照（對應鍵本身壞了，不是「別份 worksheet 的列」）。判準是 `uuid.UUID()` 解析得動：32 位無連字號、`{…}`、`urn:uuid:` 等非正規形式**放行並正規化為小寫連字號形式**再比對。合法 UUID 但不屬本 worksheet 仍照上方記 `unmatched`，不擋。
> 4. **已存快照在現行驗證下讀不回**（驗證收緊前寬鬆匯入的 payload）→ `latest`／`apply-offline` 回 422「請重新取得」，不落 500。與 D4(c) 不衝突：D4(c) 的「契約升版後舊快照仍可解讀」指**原始 payload 留存、事後可解析**，不等於 API 一定讀得回；讀不回就重新取得。
>
> 其餘 row 欄位型別錯（`task_id`／index 非整數、`offline_flag` 非布林、`workers`／`units` 形狀錯）同屬整份 422——這部分是 `79d8e4f` 的審查修正（Howard 核可文件化，非獨立裁決），清單見實作書 §2 B4-1。

> **D7 追記（2026-09-21，Howard 指示「照 fetch 的降級模式、本輪不重構投影層」；`a85d89d`）：`apply-offline` 的兩個 500 收掉——一個改 422，一個降級不擋。**
> 1. **body 的 id 非 UUID → 422**（原本在路由內轉型，落成**無信封 500**）：`snapshot_id`／`wi_row_ids` 改以 UUID 型別收。判準同上方 2026-09-18 追記第 3 點（canonical／32 位無連字號／`{…}`／`urn:uuid:`／大小寫皆放行並正規化），差別是 pydantic 的 parser 比 `uuid.UUID()` **略嚴**——連字號放在怪位置的字串它不收；對正常輸入兩者等價，該邊界以 reject 案例釘住。`wi_row_ids` 另設上限（見實作書 §2 B5）：ADR-034 §D5 的信封會原樣回吐每一筆壞值，無上限時一份壞 payload 會被放大數倍。
> 2. **投影報告拋例外 → 不 5xx、不 rollback，回 200 並明確標示**：投影層有幾類例外是直接拋出、不收進 `ProjectionResult.errors`（根因＝[BL-ENG-2](../BACKLOG.md)），撞上時 E 碼那一關**無從判定**。照 `fetch` 的 `units_baseline` 同一套降級模式：`report.status="unavailable"` ＋ E 碼與完整診斷，**離線設定照常套用**，R1–R9 仍照常擋。被投影**收集**（而非拋出）的 E 碼行為完全不變——仍整批 rollback ＋ 422。**正門語意的變更（跳過的是哪一關、留痕在哪與留多久）記在 §2 D2 追記（2026-09-21），本節不重述**；回應欄位形狀見實作書 §2 B6。
> 3. **這一條不是加法演進（[ADR-011](ADR-011-schema-evolution-and-contract-stability.md) 的明列例外）**：`report.errors` 原本**恆為 `[]`**，現在 `status="unavailable"` 時是 **`null`**（`warnings` 同）。刻意如此——`[]` 等於對消費端斷言「檢查過、沒問題」，但這裡是「沒算出來」；只讀 `errors`、不讀 `status` 的既有消費端**應該炸**，不該把降級讀成一切正常。既有欄位的型別變更必須明記，否則下一個人會當成加法。
> 4. **降級要留痕**：降級若只活在當下的回應，重整後畫面只剩「已套用」，事後查不到。`applied_rows`（jsonb）是這條路徑唯一的痕跡，故一併記下**套用者**（與快照 `created_by`＝取得者未必是同一人）與報告狀態／E 碼／完整診斷，並由 `latest`／`snapshots` 帶出（欄位見實作書 §2 B6）。
> 5. **取捨自覺（fail-open）**：實際逃得到這條路的是三類（`QuantityError`／`ToolResolveError`／`TmuDecompositionError`；`PrecedenceError` 在投影層內就被接住轉成收集型 E），而它們本身都攜帶確定的 E 碼，因此「降級 200」等於**閘門跑不起來時放行**。Howard 2026-09-21 裁定本輪維持降級、不重構投影層；收斂根因時要不要翻成 fail-closed（把 E 碼餵進 `proj_errors` → 整批 rollback ＋ 422 `LB_EXPORT_BLOCKED`）是 [BL-ENG-2](../BACKLOG.md) 的待裁項——屬**使用者可見的行為翻轉**，不得當成重構順手做掉。

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

**身分 header 的限制與預設配置（2026-09-18 資安複核；2026-09-21 Howard 裁：由「建議」改為預設＋例外）**：`DDM_LB_AUTH_HEADERS` 是 MOST **自稱**的身分，LB 不驗（v1 直連、不經 gateway）。值設固定字串時，所有 analyst 在 LB 端共用同一個身分——LB 的紀錄看不出是誰取的（confused deputy）；`@me` 則帶當前使用者員編（來源是 MOST 這端的 gateway-trust 身分）。故配置規則為：

- **預設**：`X-User-Id`／`X-Username` 一律設 `@me`。MOST 這端本來就有當前使用者（actor），用 `@me` 沒有額外成本，LB 的紀錄才對得回真正的操作者。
- **例外**：設固定字串屬例外，**必須在 `.env` 就地以註解註明理由**（為什麼這台／這個用途不能帶操作者）。沒有就地理由的固定身分字串視為設定錯誤。
- `X-Plant-Code` **維持固定值**（廠別是環境屬性，不是個人身分）。

~~建議 `X-Username`／`X-User-Id` 用 `@me`、只有 `X-Plant-Code` 用固定值。~~（2026-09-21 起不再只是建議，見上。）這不是認證，只是讓 LB 的紀錄能對回真正的操作者；真正的認證仍等掛 gateway（D1）。

**真機驗證（2026-09-18，整合架構師實跑）**：LB Phase 2 直跑 `:8090`（不經 Traefik）→ 建專案（上傳黃金 tasks.csv）→ 求解 → `GET …/writeback`。結果：(a) 契約版本與機台政策欄正確；(b) **`rows` 為 0** —— LB 專案建立時的 CSV 標準化（`infrastructure/csv/csv_service.py::process_uploaded_file`）用寫死的 STD_COL 清單，丟掉 `source_wi_row_id`／`role_type`／`general_role`（存下來 22 欄，上傳為 24 欄），對應鍵在儲存層即斷；影響不只回寫，`role_type=machine`（D9）與 `general_role`（D4）走真實上傳路徑同樣失效。~~LB 端修正中。~~ **已修**（LB `c0cb244`；複驗見下段）。(c) MOST `fetch` 對真 LB 回 502 `LB_UNREACHABLE`（HTTP 401），MOST 側管路正確，成因見 D1 追記。

**複驗（2026-09-18，LB 修正後）**：LB `feature/most-integration-phase2` 含 `c0cb244`（上傳標準化保留擴充欄）與 `aac992f`（general 保留 `source_wi_row_id`），直跑 `:8090`。全鏈改為自動化端到端（`src/frontend/e2e/writeback-golden-replica.spec.ts`，`@slow`）：MOST 建黃金複本（隨機 id，不佔 `wi_rows` 全域主鍵）→ 匯出 lb-csv → 上傳 LB 建專案 → 求解 → MOST `fetch` → 刪除該 LB 專案。結果：rows 34、matched 24／missing 0／unmatched 0；general 單列單站；工具五組 acquire／use／release 各聚成單站、無 `cross_station`；Q>1 三個 motion（G、H `frequency=8`；I `repeat_count=8`）`units_total` 皆 8、`unit_mismatches` 空、件數比對基準 `ok`；offline 列無站無人、無 offline 差異；`GET latest` 讀回一致。複驗同時暴露 D6 件數規則的缺陷：同一份黃金快照動作 I 依 D6 逐列加總得 10，依 Howard 裁決改為 8（標推算 `inferred_max`——LB §8 尚未輸出 `qty_scope`），見 D6 件數註記。

**待裁決（不阻擋實作）**：是否讓回寫結果影響作業版的「秒數」顯示（目前秒數來自 MOST 投影預覽，非 LB 實際排程）；建議 v1 不混用，兩者分開顯示。

**跨 repo 未結（不阻擋實作）**：D6「件數」已於 2026-09-21 修訂（見 §2 D6 件數修訂）。仍待 LB：`MOST_INTEGRATION_INPUT_SPEC.md` §8 定義 `rows[].qty_scope`（LB 票 B20）；補上前，MOST 顯示的件數一律是推算值（`inferred_max`）。

---

## 5. 落地追蹤

實作見 [`docs/lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md`](../lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md)。

- **落地（2026-09-17，分支 `feature/lb-writeback`）**：fixture（LB `aac992f` 實跑，含 general）`6e1d139`／`c9a64bf`；
  B1 資料模型 `d01d8f2`；B3 LB client `62bc5fa`；B4 解析/聚合/差異 `dce1415`；B5 五端點＋三錯誤碼 ＋ B6
  apply-offline（走正門）`9e4f636`；F1–F4 作業版產線視角實際結果＋離線套用 `b978994`。**未 push、未合入。**
- **502／504（已裁：維持 502／504，逾時以子類別分出，2026-09-18 Howard；`47bc3bc`）**：§2 D7「LB 不可達／逾時 → 502／504」
  維持。實作以最小改動達成——`lb_client` 加 `LbTimeout(LbUnreachable)`，只在單次操作逾時（`httpx.TimeoutException`）
  與總時限逾時（`asyncio.timeout`）時拋；其餘連線失敗、5xx、非預期狀態仍為 `LbUnreachable`。路由層先判
  `LbTimeout` → **504**（`GatewayTimeoutError`，`LB_TIMEOUT`，訊息「LB 還在回應中或太慢，稍後再試」）、
  再判 `LbUnreachable` → **502**（`BadGatewayError`，`LB_UNREACHABLE`，訊息「連不到 LB，請確認服務與
  `DDM_LB_API_BASE_URL`」）。理由：兩種失敗對 IE 的處置不同（等一下重試 vs 檢查服務／設定），錯誤碼與訊息分開才不誤導；
  `LbTimeout` 為 `LbUnreachable` 子類，既有「不可達即 502」的捕捉語意不破（is-a），只是路由層多一層更精準的判斷。
  新增 `LB_TIMEOUT`（獨立碼，前端 catalog 兩語系齊）而非共用 `LB_UNREACHABLE` 改訊息——獨立碼讓前端可各自在地化、
  日後可對逾時做重試 UI。原始上游狀態碼／逾時秒數仍寫 log。
- **身分 header 一組（2026-09-18，D1 追記落地；`224e143`）**：真機驗證發現 LB 需三個身分 header（見 §2 D1 追記）。
  MOST client 的單一 `DDM_LB_AUTH_HEADER_NAME` 擴為 **`DDM_LB_AUTH_HEADERS`**（一組 header，CSV `名稱=值,…`
  或 JSON；值為固定字串或 `@me`＝當前使用者員編，於呼叫時解析；**哪個 header 該用哪種值見 §4**）。舊 `DDM_LB_AUTH_HEADER_NAME`（單一，值＝@me）
  **保留相容但標為 deprecated**（`settings._parse_lb_headers` 仍讀）——選「保留相容」而非移除：避免既有 .env 靜默失效，
  且遷移成本低（改一行）。LB 回 401／403（缺 header）→ `LbAuthRequired`（`LbRequestFailed` 子類）→ 路由 502 ＋ 碼
  **`LB_AUTH_REQUIRED`** ＋ 訊息「LB 需要身分 header（X-User-Id／X-Plant-Code／X-Username），請設定 DDM_LB_AUTH_HEADERS」
  （兩語系齊）——不靜默送出、不誤導為單純連不到。仍符合 D1「認證只能是加法」：掛 Traefik 時只換 base URL 與 header 值來源。
- **黃金複本不佔固定 id（2026-09-18，Howard 裁；`959f4f1`＋`6b9fa7b`）**：複驗初期沿用 fixture 固定 id 建黃金複本，因 `wi_rows.id` 是全域主鍵而清掉了共用 dev DB 的 worksheet `e9299cab`。Howard 裁定佔用固定 id 是測試設計缺陷：`959f4f1` 記錄把該 worksheet 原樣還原的資料操作；`6b9fa7b` 把複本改為一律隨機 id（離線 `import` 依 seq_no 改寫 fixture 的 `source_wi_row_id`），並把真機全鏈自動化（§4 複驗）。
- **LB 座標格式驗證（2026-09-18，Howard 裁：現在修、不開票；`dcbb9a5`）**：見 §2 D7 追記（2026-09-18）第 1 點。
- **件數語意（2026-09-18，Howard 裁：C＋退路；`79d8e4f`）**：見 §2 D6 件數註記。API 加法欄位 `diff.motions.<wi_row_id>.units_source`、`diff.units_uncomparable`、`summary.units_baseline`（`summary.motions` 是計數，不是這裡的物件；定義見實作書 §2 B4）；同一 commit 收緊 payload 驗證並讓讀不回的舊快照回 422（§2 D7 追記（2026-09-18）第 2–4 點）。已知限制見實作書 §7。
- **`apply-offline` 的兩個 500（2026-09-21，Howard 指示：照 fetch 的降級模式、本輪不重構投影層；`a85d89d`）**：見 §2 D7
  追記（2026-09-21）。body 的 `snapshot_id`／`wi_row_ids` 改收 UUID 型別（非 UUID → 422，另設筆數上限）；投影報告拋例外
  → 200 ＋ `report.status="unavailable"`，`errors`／`warnings` 轉 `null`——**既有欄位的型別變更，不是加法**（追記第 3 點）。
  降級一併留痕於 `applied_rows`（套用者、報告狀態、E 碼、完整診斷），由 `latest`／`snapshots` 帶出，UI 為常駐一行（欄位與
  testid 見實作書 §2 B6／§3 F2）。同一 commit 補齊回寫五支端點的 RBAC 測試（viewer 打寫入端點 → 403；[BL-ENG-4](../BACKLOG.md)
  的主要範圍，權限規則本身不變）。後續 `603b83f` 收掉「留痕本身會 500」的兩條（NaN／inf 的 params、無長度上限的
  `message`）並把絆線測試收緊——**降級路徑的任何一段都不准再丟出無信封 500**，做法見實作書 §2 B6-4。
