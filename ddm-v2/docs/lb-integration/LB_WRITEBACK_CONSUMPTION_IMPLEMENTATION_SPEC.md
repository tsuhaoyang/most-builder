# LB 回寫消費實作書（MOST 端，implements ADR-036）

> **語意權威**：回寫契約 `lb-most-writeback-v1` 的欄位定義在 **LB** `docs/dev_docs/MOST_INTEGRATION_INPUT_SPEC.md` §8——本檔**不重述欄位**，衝突時以 LB 該節為準並回報。
> **決策邊界**：[ADR-036](../decisions/ADR-036-lb-writeback-consumption.md)（D1–D7）。ADR 沒涵蓋的設計問題：停下來問 Howard。
> **分支**：`feature/lb-writeback`，自 `chore/agent-docs-shared` 末端分岔（帶著文件重整的檢查機制與領域索引）。**不 push、不合入**。
> **狀態**：Design Accepted（2026-09-17）。未開工。

---

## 0. 範圍與完成定義

### 0.1 做
1. 後端：LB client、快照與逐列放置的資料模型、匯入（fetch／import）端點、差異比對、`offline` 套用端點。
2. 前端：作業版「產線視角」加「實際結果」區塊與離線差異套用流程；i18n zh-TW／en。
3. 測試：解析與聚合的單元測試、端點整合測試（含 LB 不可達）、E2E（顯示＋套用）。
4. 文件：ADR-036 落地追蹤、`docs/domains/lb-projection.md` 加回寫段、DOC_REGISTRY 一列。

### 0.2 不做
- 不碰 Traefik／forward-auth（ADR-036 D1；v1 直連）。
- 不回流 `offline` 以外任何欄位（D2／D3）。
- 不改投影層（`lb_projection/**`）、不改 CSV 契約。
- 不把 LB 的站別／人員寫進 `wi_rows`／`level_entries`（除 `offline` 外）。
- 不改作業版既有的秒數來源（ADR-036 §4 待裁決項：v1 兩者分開顯示）。

### 0.3 DoD
1. 用 LB 端實跑產出的樣本 JSON（§4 fixture）匯入後：`rows` 全數解析、matched／unmatched／missing 三類數字正確、聚合（工具三列、general 多站）符合 D6。
2. 契約版本不符 → 擋並回 ADR-034 信封；LB 不可達 → 502／504 且 log 帶原始錯誤。
3. 離線差異：列出 → 勾選套用 → `level_entries.offline` 更新且**組內傳染生效**、R1–R9 驗證通過；未勾的列不動。
4. 作業版產線視角顯示站別／人／件數與三種差異標記；zh-TW／en 齊全；`i18n-hardcoded-zh` 綠。
5. `PYTHONPATH=src pytest tests/unit tests/integration -q`、`npm run typecheck && npm run build`、`docs_check.py`、`check_agent_config.py` 全綠；`scripts/core_logic/run_all.py` 不受影響。
6. 每個 WP 一個 commit，訊息 `implements ADR-036: <WP> <一句話>`。

---

## 1. 資料模型（加法，ADR-011）

### B1 `lb_writeback_snapshots`（migration `v2_0049`）

| 欄 | 型別 | 說明 |
|---|---|---|
| `id` | uuid PK | |
| `worksheet_id` | uuid FK → `most_worksheets.id` ON DELETE CASCADE | |
| `contract_version` | text NOT NULL | 必須 `lb-most-writeback-v1`（D7） |
| `lb_project_id` / `lb_version_id` / `lb_result_id` | text NOT NULL | 來源座標 |
| `generated_at` | timestamptz NULL | payload 的 `generated_at` |
| `fetched_at` | timestamptz NOT NULL default now() | |
| `unattended_machine_policy` | text NOT NULL | `free`／`busy` |
| `unattended_machine_policy_source` | text NOT NULL | `persisted`／`defaulted` |
| `source_url` | text NULL | 實際呼叫的 URL（import 路徑為 NULL） |
| `payload` | jsonb NOT NULL | **原始回應原樣**（D4：契約升版後仍可解讀） |
| `created_by` | text NOT NULL | |

索引：`(worksheet_id, fetched_at desc)`。保留最近 10 筆／worksheet，超出刪最舊（D4）。

### B2 `lb_row_placements`（同 migration）

| 欄 | 型別 | 說明 |
|---|---|---|
| `id` | uuid PK | |
| `snapshot_id` | uuid FK → snapshots ON DELETE CASCADE | |
| `source_wi_row_id` | uuid NOT NULL | **不設 FK**（可能指向已刪除或別份 worksheet 的列；比對在應用層） |
| `task_id` | int NOT NULL | |
| `line_index` / `station_index` | int NULL | offline 列為 NULL |
| `workers` | jsonb NOT NULL default `'[]'` | LB 的 `workers[]`（字串識別值） |
| `units` | jsonb NULL | Q>1 才有：`[{worker, units}]` |
| `offline_flag` | bool NOT NULL | |

索引：`(snapshot_id)`、`(snapshot_id, source_wi_row_id)`。

---

## 2. 後端工作包

### B3 LB client（`services/v2/lb_client.py`）
- `async def fetch_writeback(*, base_url, project_id, version_id, result_id, timeout_s, auth_header: tuple[str,str] | None = None) -> dict`
- URL：`{base_url}/api/v3/projects/{p}/versions/{v}/results/{r}/writeback`。
- 比照 `dsx_client` 的錯誤分類（**逐字照抄它的例外分層，不要自創**）：`httpx.TransportError`／總時限逾時 → `LbUnreachable`；4xx → `LbRequestFailed(status)`；5xx → `LbUnreachable`。log 帶原始狀態碼。
- 設定（`settings.py`，加法）：`DDM_LB_API_BASE_URL`（None → 端點 503）、`DDM_LB_TIMEOUT_S`（預設 10）、`DDM_LB_AUTH_HEADER_NAME`（選填；設了才帶，值＝當前使用者員編——**為日後掛 gateway 預留，v1 預設不設**）。

### B4 解析與比對（`services/v2/lb_writeback_service.py`，純函式優先）
1. `parse(payload) -> ParsedWriteback`：驗 `contract_version`（不符 → `LbWritebackContractMismatch`）；逐 row 轉 `RowPlacement`；未知欄位忽略（加法相容）。
2. `aggregate(rows) -> dict[wi_row_id, MotionPlacement]`（D6）：`stations: set[int]`、`workers: set[str]`、`units_total: int | None`、`offline_values: set[bool]`、`task_ids: list[int]`、`cross_station: bool`（`len(stations)>1` 且該列非 general）、`offline_conflict: bool`。
   - general 判定用 MOST 自己的 `level_entries.is_general`，**不要**從 LB payload 猜。
3. `diff(worksheet_rows, aggregated) -> WritebackDiff`：
   - `matched` / `unmatched`（LB 有、MOST 沒有）/ `missing`（MOST 有、LB 沒有；SIMO 從屬列與 general 以外的 missing 要能分辨，回傳 reason hint）。
   - `offline_diffs: [{wi_row_id, most_offline, lb_offline}]`。
   - `unit_mismatches`：`units_total` 與該列 `frequency`／repeat 的 N 不符。
4. `persist(session, worksheet_id, payload, parsed, source_url, actor) -> snapshot_id`（含保留策略）。

### B5 端點（`api/routes/v2/lb_writeback.py`，權限比照 ADR-019：讀 viewer+、寫 IE+）
| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v2/worksheets/{id}/lb-writeback/fetch` | body `{lb_project_id, lb_version_id, lb_result_id}` → 呼叫 LB → 存快照 → 回 `{snapshot_id, summary, diff}` |
| POST | `/api/v2/worksheets/{id}/lb-writeback/import` | body ＝ 回寫 payload 原樣（**測試／離線驗證用**，走同一解析路徑） |
| GET | `/api/v2/worksheets/{id}/lb-writeback/latest` | 最新快照 ＋ 聚合 ＋ diff（無快照 → 404） |
| GET | `/api/v2/worksheets/{id}/lb-writeback/snapshots` | 最近 10 筆摘要（供切換檢視） |
| POST | `/api/v2/worksheets/{id}/lb-writeback/apply-offline` | body `{snapshot_id, wi_row_ids: [...]}` → 套用（D2） |

錯誤碼（`errors/registry.py` 加法 ＋ 前端 catalog 同步，ADR-034）：`LB_WRITEBACK_CONTRACT_MISMATCH`、`LB_UNREACHABLE`、`LB_NOT_CONFIGURED`。

### B6 `apply-offline`（D2 的「走正門」）
1. 只接受 `offline_diffs` 裡出現過的 `wi_row_id`（其餘 → 422）。
2. 寫 `level_entries.offline`；**接著跑 MOST 既有的組內傳染**（同 `countersignature` 的 cub、同 `worker_cub`）——重用作業版／既有存檔路徑的傳染實作，不要另寫一份。
3. 跑 `level` 驗證（R1–R9）與投影預覽（`lb_export_report`）；任一 E 碼 → 整批 rollback 並回報（不可只套一半）。
4. 回 `{applied: [...], propagated: [...], report: {...}}`；在 `lb_writeback_snapshots` 記一筆套用紀錄（新欄 `applied_at`／`applied_rows jsonb`，同 migration）。

---

## 3. 前端工作包（作業版產線視角，D5）

### F1 資料與 hook
`features/level-system/api.ts` 加 `useLbWriteback(worksheetId)`（GET latest）、`useFetchWriteback()`、`useApplyOffline()`。型別鏡像後端回應。

### F2 產線視角「實際結果」區塊（`LineView.tsx`）
- 頂部一列：來源座標（project／version／result）、取得時間、機台政策（`busy` 時標「以人力計」）、「重新取得」按鈕（開小表單填三個 id）。
- 每個作業方塊下方顯示：`第 n 站 · k 人`（多站 general → `每站`）、Q>1 顯示件數分配。
- 三種差異標記：`cross_station`（⚠ 同一動作被排到不同站）、`missing`（LB 沒有這一步的結果）、`offline_conflict`。
- 無快照時顯示引導文案與「取得結果」按鈕，不報錯。

### F3 離線差異套用
差異清單（每列：步驟、MOST 現值、LB 值）＋ 勾選 ＋「套用勾選的離線設定」；送出後顯示套用結果與傳染到哪些列；失敗（E 碼）顯示原因且**不套用任何一列**。

### F4 i18n
`levelSystem.jobs.writeback.*`（zh-TW／en），至少：`title`、`source`、`fetchedAt`、`policyBusy`、`refetch`、`noSnapshot`、`station`、`workers`、`unitsPerWorker`、`crossStation`、`missing`、`offlineConflict`、`applyOffline`、`applied`、`applyFailed`、錯誤碼三條。**文案要用使用者語言**（「這一步被排到第 3 站，2 個人做」而不是 `station_index=2`）。

---

## 4. 測試

| 層 | 檔 | 內容 |
|---|---|---|
| 單元 | `tests/unit/test_lb_writeback_parse.py` | 契約版本不符擋；未知欄位忽略；欄位型別 |
| 單元 | `tests/unit/test_lb_writeback_aggregate.py` | 工具三列同站 → 1 站；跨站 → `cross_station`；general 多站不算異常；units 加總；offline 衝突 |
| 單元 | `tests/unit/test_lb_writeback_diff.py` | matched／unmatched／missing 三類；SIMO 從屬列的 missing 有 reason |
| 整合 | `tests/integration/test_lb_writeback_endpoints.py` | import → latest → apply-offline（含傳染與 rollback）；未設定 base URL → 503；LB 不可達（mock httpx）→ 502/504；保留策略只留 10 筆 |
| E2E | `src/frontend/e2e/writeback-line-view.spec.ts` | import 樣本 → 產線視角顯示站別／人／差異 → 套用離線 → 重新載入仍正確 |
| **待真機驗證** | （手動） | **LB 起服務後跑一次 `fetch` 全鏈**：目前 `fetch` 只用 mock／本機慢速 server 驗過（逾時 504、連線拒 502），尚未對真實 LB 端點跑過一次完整取數→解析→存快照。LB 起實例後補跑一次並記錄結果。 |

**fixture**：`docs/lb-integration/fixtures/writeback_sample.json` —— 由 **LB 端實跑**產生（用 LB 的黃金複本結果呼叫 writeback 端點），不得手寫。取得前先確認 LB 分支 `feature/most-integration-phase2` 可跑；取不到就回報，**不要自己捏一份假的**。

---

## 5. 文件同步
1. ADR-036 §5 加落地追蹤（commit）。
2. `docs/domains/lb-projection.md`：加「回寫（消費）」段，列端點、資料表、聚合規則，並指向 LB §8。
3. `DOC_REGISTRY.md` LB 整合表加本實作書一列。
4. `domains.yaml`：`lb-projection` 的 `paths` 加新檔；invariant 加一條「回寫只回流 `offline`，且必走組內傳染與 R1–R9；其餘欄位唯讀」。

---

## 6. 禁止事項
1. **不得在 v1 對外開放**：直連 LB 無認證，只可內網／本機（ADR-036 §4）。端點文件與 `AGENTS.md` 各標一次。
2. 不回流 `offline` 以外欄位；不寫進 `wi_rows`。
3. 不改投影層、不改 CSV 契約、不升 `CONTRACT_VERSION`。
4. 不自己捏 fixture（§4）。
5. 不繞過組內傳染與 R1–R9 直接 UPDATE `level_entries`。
6. LB repo 唯讀。
