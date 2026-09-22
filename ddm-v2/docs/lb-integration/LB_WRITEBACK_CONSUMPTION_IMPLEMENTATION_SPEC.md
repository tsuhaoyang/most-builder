# LB 回寫消費實作書（MOST 端，implements ADR-036）

> **語意權威**：回寫契約 `lb-most-writeback-v1` 的欄位定義在 **LB** `docs/dev_docs/MOST_INTEGRATION_INPUT_SPEC.md` §8——本檔**不重述欄位**，衝突時以 LB 該節為準並回報。
> **決策邊界**：[ADR-036](../decisions/ADR-036-lb-writeback-consumption.md)（D1–D7）。ADR 沒涵蓋的設計問題：停下來問 Howard。
> **分支**：`feature/lb-writeback`，自 `chore/agent-docs-shared` 末端分岔（帶著文件重整的檢查機制與領域索引）。**不 push、不合入**。
> **狀態**：✅ 已落地（2026-09-18；B1–B6＋F1–F4 與後續修正，分支 `feature/lb-writeback`，未 push、未合入；commit 清單見 ADR-036 §5）。件數規則依 Howard 2026-09-18 裁決（§2 B4），ADR-036 D6「件數」一條已於 2026-09-21 修訂。`apply-offline` 的兩個 500 於 2026-09-21 收掉（`a85d89d`，§2 B5／B6）。LB `export_warnings` 自 2026-09-22 起消費（`707d0c0`，Howard 給消費規則；§2 B4-6），同日真機第三輪驗收（§4）。已知限制見 §7。~~Design Accepted（2026-09-17）。未開工。~~

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

> **注意（2026-09-18）**：`lb_row_placements` **沒有 `qty_scope` 欄**（建表時 LB 回寫尚無此欄）。所有重算——`latest` 的聚合／diff、`apply-offline` 的 offline 差異清單——一律對快照 `payload` 重新 `parse`，**不讀 placements**；placements 只是逐列落地的查詢便利，不是重算來源。要讓 placements 帶 `qty_scope` 需加法 migration（另案，見 §7 (c)）。**追記（2026-09-21）**：LB 自 `64e4abd` 起確實輸出 `qty_scope`，payload 與 placements 的落差已是**實際存在**而非假設——這條「不讀 placements」更要守。

---

## 2. 後端工作包

### B3 LB client（`services/v2/lb_client.py`）
- `async def fetch_writeback(*, base_url, project_id, version_id, result_id, timeout_s, headers: dict[str, str] | None = None) -> dict`（~~`auth_header: tuple[str,str] | None = None`~~——2026-09-18 改為一組 header，ADR-036 D1 追記）
- 座標驗證：三個座標先以 `LB_ID_PATTERN`（`^[A-Za-z0-9_-]{1,64}$`，定義於 `src/ddm_v2/services/v2/lb_client.py`，路由共用同一常數）`fullmatch`；不合 → `ValueError`、**不發任何請求**。這是縱深防線——路由層應已先回 422（B5；ADR-036 D7 追記 2026-09-18 第 1 點）。⚠️ 只能用 pydantic `pattern` 或 `re.fullmatch`：Python `re.match`／`search` 的 `$` 會放過結尾換行。
- URL：`{base_url}/api/v3/projects/{p}/versions/{v}/results/{r}/writeback`。
- 例外分層（分層原則比照 `dsx_client`：型別分離、單次操作逾時＋`asyncio.timeout` 總時限雙層）；log 帶原始狀態碼：

  | 情況 | 例外 | 端點結果（B5） |
  |---|---|---|
  | 單次操作逾時（`httpx.TimeoutException`）／總時限逾時（`asyncio.timeout`） | `LbTimeout`（`LbUnreachable` 子類） | 504 `LB_TIMEOUT` |
  | 連線失敗（其餘 `httpx.TransportError`）、5xx、3xx 等非預期狀態 | `LbUnreachable` | 502 `LB_UNREACHABLE` |
  | 401／403（缺身分 header） | `LbAuthRequired`（`LbRequestFailed` 子類） | 502 `LB_AUTH_REQUIRED` |
  | 其他 4xx（如座標在 LB 不存在） | `LbRequestFailed(status)` | 502 `LB_UNREACHABLE`（訊息帶 HTTP 狀態） |

  ~~比照 `dsx_client` 的錯誤分類（逐字照抄它的例外分層，不要自創）：`httpx.TransportError`／總時限逾時 → `LbUnreachable`；4xx → `LbRequestFailed(status)`；5xx → `LbUnreachable`。~~（逾時分出 `LbTimeout`、401／403 分出 `LbAuthRequired`，ADR-036 §5。）
- 設定（`settings.py`，加法）：`DDM_LB_API_BASE_URL`（None → 端點 503）、`DDM_LB_TIMEOUT_S`（預設 10）、`DDM_LB_AUTH_HEADERS`（一組身分 header：CSV `名稱=值,…` 或 JSON；值為固定字串或 `@me`＝當前使用者員編，呼叫時解析；LB 最小需 `X-User-Id`＋`X-Plant-Code`＋`X-Username`，ADR-036 D1 追記；**哪個 header 該用哪種值＝ADR-036 §4**——`X-User-Id`／`X-Username` 預設 `@me`、固定字串屬例外，本書不重抄）。~~`DDM_LB_AUTH_HEADER_NAME`（選填；設了才帶，值＝當前使用者員編——為日後掛 gateway 預留，v1 預設不設）~~——deprecated，仍相容讀取（單一 header、值＝`@me`；ADR-036 §5）。

### B4 解析與比對（`services/v2/lb_writeback_service.py`，純函式優先）
1. `parse(payload) -> ParsedWriteback`：驗 `contract_version`（不符 → `LbWritebackContractMismatch`）；逐 row 轉 `RowPlacement`；未知欄位忽略（加法相容）。
   row 驗證（任一不合 → `LbWritebackMalformed` → 整份 422 `VALIDATION_ERROR`、不存快照；ADR-036 D7 追記 2026-09-18 第 2／3 點）：
   - 缺必要欄位（`source_wi_row_id`／`task_id`／`offline_flag`）→ 整份 422（其餘欄位缺欄視同 null／預設）。
   - `source_wi_row_id`：`uuid.UUID()` 解析得動即放行（32 位無連字號、`{…}`、`urn:uuid:` 會正規化為小寫連字號形式）；解析不動 → 422。合法 UUID 但不屬本 worksheet → `unmatched`，不擋。
   - `task_id` 整數（必填）；`line_index`／`station_index` 整數，或 null／缺欄（offline 列即為 null）——bool、小數、字串一律不收（不截斷、不轉型）。
   - `offline_flag`：只收 JSON `true`／`false`（`"false"` 字串會被 `bool()` 變成 True）。
   - `workers`：字串陣列，**元素不可為空字串、但可以是空陣列**（LB §8 的 offline 列與 policy free 的機台列就是 `[]`）；null／缺欄 → `[]`。`units`：null 或 `[{worker: 非空字串, units: 非負整數}]`。
   - `qty_scope`（選填；LB §8 **已定義並輸出**，`64e4abd`）：缺欄**或顯式 `null`**（兩者一視同仁，都成為 `None`），或 `setup`／`cyclic`（大小寫須相符）；其他值（含 `auto`、空字串）→ 422。Q=1 為何兩種表示法都合法、各由哪支測試覆蓋——見 ADR-036 §2「D6 件數修訂」，此處不重述。
   - 頂層 `export_warnings`（選填；LB §8，`bb0d340`）：缺 key／有 key 時的結構要求與 `reason` 值域見 B4-6——**未知 `reason` 不 422**，與上一條 `qty_scope` 刻意相反。
2. `aggregate(rows) -> dict[wi_row_id, MotionPlacement]`（D6）：`stations: set[int]`、`workers: set[str]`、`units_total: int | None`、`units_source: "cyclic" | "inferred_max" | None`、`offline_values: set[bool]`、`task_ids: list[int]`、`cross_station: bool`（`len(stations)>1` 且該列非 general）、`offline_conflict: bool`。
   - general 判定用 MOST 自己的 `level_entries.is_general`，**不要**從 LB payload 猜。
   - **件數**（Howard 2026-09-18 裁決「C＋退路」；規則正本＝ADR-036 §2 D6 ＋ ~~待整合架構師修訂~~「D6 件數修訂」，該修訂已於 2026-09-21 落檔）：每列先逐 worker 加總，**不跨列加總**——LB 的 setup 列 `units` 是 `used`（0／1，經手次數，LB ADR-008 D3），不是件數。
     - **該 motion 中帶 `units` 的列**任一列有 `qty_scope` → 取 `qty_scope=="cyclic"` 那列的值（持工具 F>1 的三列皆 cyclic、值相同，取最大）→ `units_source="cyclic"`；有 `qty_scope` 卻沒有 cyclic 列 → `(None, None)`。
     - 該 motion 帶 `units` 的列都沒有 `qty_scope`（**舊快照**——LB `64e4abd` 加欄前存下的 payload）→ 退回各列取最大值（cyclic 列 Σ＝Q ≥ setup 列 Σ＝經手人數）→ `units_source="inferred_max"`（推算值，UI 必須標示，F2）。
     - Q＝1 的 motion LB 不帶 `units` → `units_total=None`、`units_source=None`。
     - ~~逐 worker、逐列加總~~（舊做法把工具 1／8／1 加成 10）。
3. `diff(worksheet_rows, aggregated) -> WritebackDiff`：
   - `matched` / `unmatched`（LB 有、MOST 沒有）/ `missing`（MOST 有、LB 沒有；SIMO 從屬列與 general 以外的 missing 要能分辨，回傳 reason hint）。LB 自述丟列時，非 SIMO 從屬的缺口另加旗標 `lb_dropped_possible: true`（reason 不改，B4-6）。
   - `offline_diffs: [{wi_row_id, most_offline, lb_offline}]`。
   - `unit_mismatches: [{wi_row_id, expected_n, units_total, units_source}]`：`units_total` 與 **MOST 投影出的 quantity Q**（`expected_n`；`export_service.projected_quantities`，只含 Q>1，同一 motion 拆出的各列 Q 相同取最大）不符。~~`units_total` 與該列 `frequency`／repeat 的 N 不符~~——不用 `frequency`：持工具 F>1、repeat 列的 Q 由投影矩陣決定（契約 §3.2），`frequency` 對不上。
   - `units_uncomparable: [{wi_row_id, expected_n, reason}]`：MOST 投影 Q>1、但沒有可比的件數——沒得比，明列出來，不可讀成一致。~~`reason` 目前恆為 `no_units`~~（2026-09-22 起兩值）：
     - `no_units`：聚合後沒有件數、且該 motion **在 LB 回寫裡不是 offline**（用 LB 的 `offline_flag` 判斷，不是 MOST 的 offline）。「LB 完全沒帶 units」與「有 `qty_scope` 但沒有 cyclic 列」落在同一桶，日後要分辨需再加 reason 值（加法）。
     - `lb_degraded`（2026-09-22 加法）：LB 在 `export_warnings.units_degraded` 自述降級了這一步的件數（缺陷指示，與 `no_units` 分開）；判準見 B4-6。
4. **件數比對基準** `summary.units_baseline = {status, reasons}`（`_units_baseline`）：一律以 MOST 投影判斷，不從 LB 缺值推論。
   - `ok`：已用投影 Q 比對；`not_needed`：MOST 投影沒有任何 Q>1 的 motion。
   - `unavailable`：投影拋出（逃得出來的三類，見 §7 (g)）或收集到 E 碼→ `reasons` 帶 E 碼、件數不比；**回寫端點本身不因此失敗**（不 500），快照照存。`unavailable` 不等於「一致」。（這是**呼叫端的防守**，不是投影層的規則——根因與待修見 §7 (g)／[BL-ENG-2](../BACKLOG.md)。）
   - `import`／`fetch` 先存快照再算基準；`apply-offline` 重算 diff 只取 `offline_diffs`，不比件數。
5. `persist(session, worksheet_id, payload, parsed, source_url, actor) -> snapshot_id`（含保留策略）。placements 不存 `qty_scope`（見 B2 注意）。
6. **LB `export_warnings`（LB §8；Howard 2026-09-22 給消費規則，`707d0c0`）——本項為 MOST 端消費規則的單一權威**；決策與理由見 ADR-036 §2 D7 追記（2026-09-22），欄位定義見 LB §8（本書不重述）。
   - **有沒有這個 key**：缺 key＝舊 LB／舊快照 → `present=false`，回應三欄為 `null`（＝不知道）；有 key 就必須是物件且 `units_degraded`／`dropped_rows`／`truncated` 三欄齊全——`{}`、缺任一欄、顯式 `null`、型別錯、負值 → 整份 422、不存快照（同 B4-1）。`{}` 不得讀成「三欄皆空」：那等於替 LB 宣稱沒有降級、沒有丟列。
   - **`reason` 值域——與 B4-1 的 `qty_scope` 刻意相反**：未知 `reason` → `reason="unknown"` ＋ `reason_raw`（LB 原值，截至 64 字），**照常存快照、不得 422**；未知 reason 時 `units_sum`／`quantity` 可為 `null`（已知 reason 兩欄必填）。`reason` 不是字串仍屬型別錯 → 422。對照：`qty_scope` 未知值 422，因為它決定件數取哪一列、猜錯就顯示錯的件數；`reason` 只是警告的說明——值域封閉是擋壞資料，不是在 LB 加第三個 reason 時炸掉整次 fetch。
   - **降級掛到步驟**：`units_degraded[].source_wi_row_id` 以與 `rows[]` **同一個** `str(UUID(...))` 正規化後，才與聚合結果對應（LB 原樣輸出非正規拼法，直接字串比對會靜默對不上；解析不動 → 422）。對上的掛在 `diff.motions[wi].units_degraded[]`；對不上任何步驟的計入 `diff.export_warnings.unattached_units_degraded`，不靜默消失。
   - **件數沒得比的新歸因** `units_uncomparable.reason="lb_degraded"`（B4-3）：(i) 該步驟聚合後無件數、且在 `units_degraded` 裡；(ii) 該步驟走推算退路（`inferred_max`，無 `qty_scope`）且帶非 `setup_not_one` 的降級——此時剩下的最大值是 setup 列的 used、不是件數，**不報** `unit_mismatches`。(ii) 只有手工 `import` 造得出：LB 輸出 `export_warnings`（`bb0d340`）的版本早已輸出 `qty_scope`（`64e4abd`）。
   - **丟列**：`missing[].reason` **不改**；`dropped_rows` 非空時，非 `simo_subordinate` 的缺口加旗標 `lb_dropped_possible: true`（丟掉的列對應不回是哪一步，這一步只是**可能**其中之一）。`dropped_rows[].task_id` 是 LB 端 id：只顯示給人回 LB 找列，**不**與 MOST 投影的 `task_id` 對應、**不**反推 `wi_row_id`。
   - **MOST 自己的上限**：兩張清單各 50 筆（`EXPORT_WARNING_LIMIT`；回應帶 `limit`，前端不寫死）；任一超過 → 截斷並標 `truncated=true`，不 422（超出的項目不解析）。不信任 LB 自稱的上限：快照解析出的清單之後每一次 `latest` 都會回吐。上限作用在解析與回應；快照 `payload` 仍依 D4 原樣保存。
   - **錯誤訊息限長**：整數／布林欄的錯誤訊息只帶截至 64 字元的值（`_brief`；`rows[]` 的 `task_id`／index／`offline_flag` 與本項各整數欄共用）。**未涵蓋**：`qty_scope`、`units[].units`、`contract_version` 的錯誤訊息仍原樣帶入輸入值（2026-09-22 實測 100 KB 輸入 → 約 100 KB 訊息）→ [BL-ENG-6](../BACKLOG.md)。
   - **回應形狀**（`fetch`／`import`／`latest` 的 `diff`；皆為加法，ADR-011）：`diff.export_warnings = {present, units_degraded, dropped_rows, truncated, limit, unattached_units_degraded}`（最後一欄僅 `present=true` 時有；此處 `units_degraded[]` 帶正規化後的 `source_wi_row_id`，`dropped_rows[]` 為 `{task_id, reason, reason_raw?}`）；`diff.motions[wi].units_degraded = [{task_id, units_sum, quantity, reason, reason_raw?}]`（無則 `[]`）；`diff.missing[].lb_dropped_possible`；`units_uncomparable.reason` 新值 `lb_degraded`。`missing[].reason` 值域不變。舊快照（無此 key）行為與加欄前相同。

### B5 端點（`api/routes/v2/lb_writeback.py`，權限比照 ADR-019：讀 viewer+、寫 IE+）
| 方法 | 路徑 | 用途 |
|---|---|---|
| POST | `/api/v2/worksheets/{id}/lb-writeback/fetch` | body `{lb_project_id, lb_version_id, lb_result_id}` → 呼叫 LB → 存快照 → 回 `{snapshot_id, summary, diff}` |
| POST | `/api/v2/worksheets/{id}/lb-writeback/import` | body ＝ 回寫 payload 原樣（**測試／離線驗證用**，走同一解析路徑） |
| GET | `/api/v2/worksheets/{id}/lb-writeback/latest` | 最新快照 ＋ 聚合 ＋ diff（無快照 → 404） |
| GET | `/api/v2/worksheets/{id}/lb-writeback/snapshots` | 最近 10 筆摘要（供切換檢視） |
| POST | `/api/v2/worksheets/{id}/lb-writeback/apply-offline` | body `{snapshot_id, wi_row_ids: [...]}` → 套用（D2） |

**座標格式**：`FetchIn` 三欄 `Field(pattern=LB_ID_PATTERN)`（`^[A-Za-z0-9_-]{1,64}$`，與 B3 同一常數）；不合 → 422 `VALIDATION_ERROR`，**不呼叫 LB**（ADR-036 D7 追記 2026-09-18 第 1 點）。`import` 的 body 不組 URL，不受此限。

**`apply-offline` 的 body 型別**（`ApplyOfflineIn`，2026-09-21 `a85d89d`；ADR-036 D7 追記 2026-09-21 第 1 點）：`snapshot_id: UUID`、`wi_row_ids: list[UUID]`（`min_length=1`、`max_length=1000`）。非 UUID／空清單／超過 1000 筆 → 422 `VALIDATION_ERROR`（原本在路由內 `uuid.UUID()` 轉型，落成**無信封 500**）。接受形式與 B4-1 的 `source_wi_row_id` 同（canonical／32 位無連字號／`{…}`／`urn:uuid:`／大小寫，並正規化為小寫連字號形式），唯 pydantic 的 parser **略嚴**——`uuid.UUID()` 收、它不收連字號位置怪異的字串（如 `cb43da2198fd-4fad-…`）；對正常輸入兩者等價，該邊界以 reject 案例釘住（§4）。上限 1000 的理由：ADR-034 §D5 的信封原樣回吐 `exc.errors()`，pydantic 對 list 逐項收集錯誤且每筆回吐輸入值，無上限時回應被放大約 6.7×（實測 5000 筆壞值 → 1.47 MB），設限後 ≈ 1:1；壓掉的是**放大倍率**，不是絕對大小（全域沒有 body 大小上限）。

錯誤碼（`errors/registry.py` 加法 ＋ 前端 catalog 同步，ADR-034）：

| 碼 | HTTP | 情況 |
|---|---|---|
| `LB_WRITEBACK_CONTRACT_MISMATCH` | 422 | `contract_version` 不是 `lb-most-writeback-v1`（D7） |
| `VALIDATION_ERROR` | 422 | 座標格式不合（不呼叫 LB）；payload row 格式錯（B4-1，不存快照）；`latest`／`apply-offline` 讀到不符現行驗證的舊快照（請重新取得）；`apply-offline` 的 body id 非 UUID／空清單／超過 1000 筆（見上）；`apply-offline` 的列不在 `offline_diffs`（B6） |
| `LB_UNREACHABLE` | 502 | 連線失敗、LB 5xx／3xx、其他 4xx（訊息帶 HTTP 狀態） |
| `LB_AUTH_REQUIRED` | 502 | LB 回 401／403（缺身分 header；提示設定 `DDM_LB_AUTH_HEADERS`） |
| `LB_TIMEOUT` | 504 | 單次操作或總時限逾時 |
| `LB_NOT_CONFIGURED` | 503 | `DDM_LB_API_BASE_URL` 未設 |
| `LEVEL_VALIDATION_FAILED`／`LB_EXPORT_BLOCKED` | 422 | `apply-offline` 套用後 R1–R9 或投影出 E 碼 → 整批 rollback（B6-3） |
| `NOT_FOUND` | 404 | worksheet 不存在；`latest` 無快照；`apply-offline` 找不到該 worksheet 的快照 |

（`LB_*` 原規劃三條；`LB_TIMEOUT`、`LB_AUTH_REQUIRED` 於 2026-09-18 加法新增，ADR-036 §5。表中其餘為既有共用碼，非本實作新增。）

### B6 `apply-offline`（D2 的「走正門」）
1. 只接受 `offline_diffs` 裡出現過的 `wi_row_id`（其餘 → 422）。
2. 寫 `level_entries.offline=True`；**接著跑組內傳染**（同 `countersignature` cub 或同 `worker_cub` wcub 視為同組，一起翻）。現況：傳染在 `lb_writeback_service._group_members` **自成一份**（規則對齊前端 `store.toggleOffline`，後端為權威）；~~重用作業版／既有存檔路徑的傳染實作，不要另寫一份~~——兩份規則各寫一次有漂移風險，**統一為共用函式**：已開票 [BL-ENG-1](../BACKLOG.md)（原記「另案」，2026-09-21 給票號；做法與影響見該票，本節不重抄）。
3. 跑 `level` 驗證（R1–R9）與投影預覽（`lb_export_report`）；投影**收集到**的任一 E 碼 → 整批 rollback 並回報（不可只套一半）。
   - **投影預覽拋例外**（§7 (g)；清單的單一來源＝`lb_writeback_service._projection_raises()`，有絆線測試盯著投影層新增的例外類別，§4）→ **不 rollback、不 5xx**：端點仍 200、離線設定照常套用，R1–R9 仍照常擋，報告標 `unavailable`（下一點）。**正門的哪一關被跳過、為什麼不 rollback、留痕留多久＝ADR-036 §2 D2 追記（2026-09-21）**；HTTP／回應契約面見同檔 D7 追記（2026-09-21）；根因見 §7 (g)／[BL-ENG-2](../BACKLOG.md)。
4. 回 `{applied: [...], propagated: [...], report: {...}}`。`report` 的形狀（**本節為單一權威**，2026-09-21 `a85d89d`）：

   | 欄 | `status="ok"` | `status="unavailable"` |
   |---|---|---|
   | `reasons` | `[]` | `[E 碼]`（裸碼，相容只讀碼的既有讀取端） |
   | `reason_details` | `[]` | `[{code, wi_row_id, message, params}]`＝完整 `ProjectionError`，經 `_jsonable_err()` 壓成可寫 jsonb 的形狀（下方「留痕本身不准失敗」） |
   | `errors` | `[]`（非空早已 rollback） | **`null`**＝沒算出來 |
   | `warnings` | 投影報告的 `warnings` | **`null`** |

   `errors`／`warnings` 由**恆為 list** 改為可能是 `null`，是既有欄位的型別變更、**不是加法**（ADR-011 的明列例外）——理由見 ADR-036 §2 D7 追記（2026-09-21）第 3 點。只讀 `errors` 不讀 `status` 的消費端會炸，這是刻意的。
   `reasons` 與 `reason_details` 是建構上的恆等式（`reasons == [d["code"] for d in reason_details]`），兩份副本以斷言釘住，不得漂移。

   **留痕本身不准失敗**（`_jsonable_err()`，2026-09-21 `603b83f`）——這條路徑存在的理由就是「投影出問題時不准 500」，壓平動作自己更不能炸：
   - `json.dumps(..., allow_nan=False, default=str)`：`NaN`／`inf` 穿得過 `default=str`，但 PostgreSQL 的 jsonb **直接拒收**，會在 commit 時炸；這條路徑真實可達（`frequency` 是 `Numeric`，而 `'NaN'::numeric > 0` 為 true，`CHECK (frequency > 0)` 擋不住）。`Decimal`／`date` 之類壓成字串。
   - 壓不平（不可序列化／NaN／inf）→ **整個捨棄 `params`**（留 `code`／`message` 仍足以診斷），寫 log，**絕不把例外往外丟**。
   - `message` 截斷至 500 字（`_ERR_MESSAGE_MAX`）：它直接吃工序表欄位（level 原字串在 schema 上無長度上限），不截斷會原樣進 jsonb，並在之後**每一次** `latest` 回應裡回吐。
5. 在 `lb_writeback_snapshots` 記一筆套用紀錄（`applied_at`／`applied_rows jsonb`，同 migration）。`applied_rows` 除 `applied`／`propagated` 外另記（2026-09-21）：
   - `applied_by`：**套用者**員編（`require_role("analyst")` 解出的 `CurrentUser.employee_no`）——與快照 `created_by`（**取得者**，B1）未必是同一人；**只存不回吐**，五支端點都不帶出。
   - `report_status`／`report_reasons`／`report_errors`＝上表的 `status`／`reasons`／`reason_details`（同值）。降級若只活在當下回應，重整後畫面只剩「已套用」，事後查不到。

   讀取端帶出：`GET …/latest` → `applied_report_status`／`applied_report_reasons`／`applied_report_errors`；`GET …/snapshots` 每筆 → 前兩者（下一次 fetch 會產生新快照、`latest` 只回最新那筆；歷史清單不帶狀態的話，舊那筆的降級紀錄整個 API 都讀不到——本 service 沒有其他稽核寫入）。套用前或舊快照無這些鍵 → `null`／`[]`，不誤報。
   **留痕的保存期限＝該快照的壽命**：B1 的保留策略只留最近 10 筆（按 `fetched_at`，不看有沒有套用紀錄），被淘汰的快照連同 `applied_rows` 一併刪，且本路徑**沒有其他稽核寫入**——後果見 ADR-036 §2 D2 追記（2026-09-21）。

---

## 3. 前端工作包（作業版產線視角，D5）

### F1 資料與 hook
`features/level-system/api.ts` 加 `useLbWriteback(worksheetId)`（GET latest）、`useFetchWriteback()`、`useApplyOffline()`。型別鏡像後端回應。

### F2 產線視角「實際結果」區塊（~~`LineView.tsx`~~ → `WritebackPanel.tsx`，由 `JobsShell.tsx` 在產線視角的 `LineView` 上方渲染）
- 頂部一列：來源座標（project／version／result）、取得時間、機台政策（`busy` 時標「以人力計」）、「重新取得」按鈕（開小表單填三個 id）。
- **逐步驟（motion）一列**顯示（~~每個作業方塊下方~~——現況是產線視角上方的獨立區塊，不掛在作業方塊下）：`第 n 站 · k 人`（多站 general → `每站`）、Q>1 顯示總件數：`units_source=cyclic` →「共 n 件」；其餘（`inferred_max`、日後新增的來源）一律「共 n 件（推算）」＋說明 tooltip——出錯時落在保守的一邊。~~Q>1 顯示件數分配~~（逐 worker 分配未實作，只顯示總數）。
- `summary.units_baseline.status=unavailable` → 區塊頂部提示「件數沒有比對」（先處理「要處理」的項目）。
- **套用報告降級提示**（2026-09-21）：`applied_report_status` 非 `ok`（含日後新增的狀態值）→ 區塊底部**常駐**一行琥珀提示（`data-testid="writeback-apply-report-unavailable"`，文案 `levelSystem.jobs.writeback.applyReportUnavailable`）。讀的是快照上的留痕（B6-5），**重整後仍在**，不是只出現一次的 toast；舊快照無此欄（`undefined`）不誤報。**E 碼本身仍未顯示**——`reason_details` 的形狀已與 `plainDiag` 吃的 `LbReportDiag` 逐欄相同，只差接線 → [BL-ENG-3](../BACKLOG.md)。
- **LB 自述的降級／丟列**（`diff.export_warnings`，2026-09-22；判準見 B4-6，本節只寫顯示語意）：
  - 件數被降級的步驟：該步驟列掛琥珀標記（`data-testid="writeback-units-degraded-<wi_row_id>"`，獨佔一行——擠在同一行會把步驟名稱壓到只剩一個字）並帶 LB 工作項編號（`task_id`，讓人回 LB 找列）。依 `reason`：`conservation` 可並排兩數（「算出 X 件、數量是 Y，所以沒給件數」）；`setup_not_one` 講「**件數不受影響**」——cyclic 列的件數仍可信，同一行照常顯示「共 n 件」，**不得**講成「對件數沒有把握」，也不並排兩數（`units_sum` 是 Σused，本來就不該等於 `quantity`）；`unknown` 講「原因無法辨識」，不替它編原因。
  - 丟列（`writeback-lb-dropped`）：區塊頂端講「有 N 列沒送回來」並列 LB 工作項編號，「下面沒有結果的步驟中**至多 N 步**可能是這個原因，其餘照原本說明」——N＝**全部**丟列（不分原因，與後端加旗標的條件一致）；只有丟列清單本身滿到上限（`truncated` 且筆數 ≥ `limit`）才改講「**至少** N 列」、不給「至多」。已知原因另一行講對應資料損壞、請到 LB 檢查；未知原因講「原因無法辨識」。帶 `lb_dropped_possible` 的缺口**保留原本的說明**，後面補一句「也可能是沒送回來的那幾列之一」。
  - `unattached_units_degraded > 0` → 一行「另有 N 筆警告對不上這份工序表的任何步驟」；`truncated` → 一行「只列出前 `limit` 筆」（`limit` 由後端給）。
  - `present=false`（舊 LB／舊快照）不顯示任何 LB 自述警告。
- **尚未顯示**：`diff.unit_mismatches`／`diff.units_uncomparable` 的警告（ADR-036 D6 要求警告；§7 (d)）。`units_uncomparable` 中 `lb_degraded` 那一類的**原因**改由步驟上的降級標記講出（上一條），清單本身仍未渲染。
- 三種差異標記：`cross_station`（⚠ 同一動作被排到不同站）、`missing`（LB 沒有這一步的結果）、`offline_conflict`。
- 無快照時顯示引導文案（`noSnapshot`）與「取得結果」按鈕，不報錯。**現況**：`GET latest` 的**任何**讀取錯誤（404 無快照、5xx、舊快照 422）都走同一個分支，因此失敗原因不會顯示在此區塊——取得／套用的失敗訊息才會顯示（`fetchFailed`／`applyFailed`）。

### F3 離線差異套用
差異清單（每列：步驟、MOST 現值、LB 值）＋ 勾選 ＋「套用勾選的離線設定」；送出後顯示套用結果與傳染到哪些列；失敗（E 碼）顯示原因且**不套用任何一列**。

### F4 i18n
`levelSystem.jobs.writeback.*`（zh-TW／en 對稱）現行 key：`title`、`source`、`fetchedAt`、`policyBusy`、`fetch`、`refetch`、`noSnapshot`、`field.{lb_project_id,lb_version_id,lb_result_id}`、`station`、`stationsMulti`、`units`、`unitsInferred`、`unitsInferredHint`、`unitsBaselineUnavailable`、`crossStation`、`offlineConflict`、`missing.{general_not_written_back,simo_subordinate,no_result}`、`missingDroppedTag`、`lbDropped`、`lbDroppedAtLeast`、`lbDroppedKeyDamaged`、`lbDroppedUnknown`、`lbDegradedUnattached`、`lbWarningsTruncated`、`unitsDegraded.{conservation,setup_not_one,unknown}`（後八組 2026-09-22 加；en 另有複數形 `_one`：`lbDropped`／`lbDroppedAtLeast`／`lbDroppedKeyDamaged`／`lbDroppedUnknown`／`lbDegradedUnattached`）、`offlineTitle`、`offlineVals`、`applyOffline`、`applied`、`propagated`、`appliedAt`、`applyReportUnavailable`、`applyFailed`、`fetchFailed`、`stepLabel`。`LB_*` 錯誤碼五條（B5 表其餘列是既有的共用碼：`VALIDATION_ERROR`／`NOT_FOUND`／`LEVEL_VALIDATION_FAILED`／`LB_EXPORT_BLOCKED`）在錯誤 catalog：`src/frontend/src/shared/i18n/resources/errors.zh-TW.ts`／`errors.en.ts`，清單 `src/frontend/src/shared/i18n/errorCodes.ts`。原規劃清單中的 ~~`workers`~~ 併入 `station`／`stationsMulti` 的 `{{workers}}` 參數；~~`unitsPerWorker`~~ **從未實作**（畫面只顯示總件數）。**文案要用使用者語言**（「這一步被排到第 3 站，2 個人做」而不是 `station_index=2`）。

---

## 4. 測試

| 層 | 檔 | 內容 |
|---|---|---|
| 單元 | `tests/unit/test_lb_writeback_service.py` | parse：契約版本不符擋、未知欄位忽略、缺必要欄位、型別收緊（bool／小數／字串）、`source_wi_row_id` 非 UUID、`units` 形狀、`qty_scope` 值域外 → Malformed；aggregate：工具三列同站 → 1 站、跨站 → `cross_station`、general 多站不算異常、workers 聯集、件數（cyclic 列／`inferred_max`／持工具 F>1 三列 cyclic 不乘 3／有 `qty_scope` 無 cyclic → None）、offline 衝突；diff：三類與 missing reason、fixture matched 24／missing 0／unmatched 0、offline 差異、以投影 Q 比出 `unit_mismatches`、`units_uncomparable`；`expected_n` 取投影 Q 不取 frequency；`export_warnings`（B4-6）：缺 key 與空物件不同、`source_wi_row_id` 四種非正規拼法正規化後掛上、conservation 降級不歸因 offline、setup_not_one 件數仍確定、推算退路＋降級 → `lb_degraded` 而非不符、丟列只加旗標不改 reason（無丟列不加）、`truncated` 帶出、未知 reason（兩張清單）降級為 `unknown` 且 `reason_raw` 限長、未知 reason 可缺數字、結構錯 → Malformed、MOST 端上限 50、對不上的降級計數、錯誤訊息不回吐巨量輸入（整數／布林欄） |
| 單元 | `tests/unit/test_lb_client.py` | 起本機 HTTP server（不 mock httpx）：成功與 URL、header 透傳、401 → `LbAuthRequired`、其他 4xx → `LbRequestFailed`、5xx／3xx／連線拒絕 → `LbUnreachable`、逾時 → `LbTimeout` |
| 單元 | `tests/unit/test_lb_writeback_fetch_ids.py` | 座標格式：LB 現行格式放行；路徑改寫字元（`../`、`%2F`、`?`、`#`、空白、控制字元、結尾換行、全形、零寬、超長…）→ 422；非字串 JSON 不轉型；client 防線零請求。`ApplyOfflineIn`：UUID 五種形式放行並正規化、非 UUID／空清單／1001 筆 → 拒（含 pydantic 比 `uuid.UUID()` 嚴的那個邊界）。**絆線** `test_projection_raises_covers_every_projection_exception`：`lb_projection` 各模組**直接定義**的 `Exception` 子類都必須在 `_projection_raises()` 清單內（否則降級漏接、回到 500），且每個都要有 `err` 參數（處理器會讀 `exc.err.*`，沒有 `err` 會在 except 區塊丟 `AttributeError`＝更難追的 500）；**不涵蓋**投影過程中由別處拋出的例外（如 `most_engine` 的 `SequenceError`——那條路今天不活）。`_jsonable_err`：NaN／inf／不可序列化 params 與超長 message 都不得讓它拋例外 |
| 整合 | `tests/integration/test_lb_writeback_endpoints.py` | import → latest → snapshots；契約不符 422；apply-offline（組內傳染、不在差異清單 422、投影 E 碼整批 rollback）；未設定 base URL → 503；不可達 → 502；逾時 → 504；缺 header → 502 `LB_AUTH_REQUIRED`；三 header 帶齊可達；保留只留 10 筆；惡意座標 → 422 且假 LB 零請求；apply-offline body 非 UUID／空清單 → 422 信封、非正規 UUID 放行；RBAC（ADR-019）：viewer 打 `fetch`／`import`／`apply-offline` → 403、讀 `latest`／`snapshots` → 不得 403（[BL-ENG-4](../BACKLOG.md) 主要範圍；viewer 以「沒出現過的員編」讓 `current_user` JIT 出 `roles=[]`，不新增 fixture）；`export_warnings`：正常（三欄空）與缺欄、降級掛到 motion（conservation／setup_not_one）、丟列加旗標、`truncated` 帶出、未知 reason 存快照不 422、結構錯 422 且不存快照 |
| 整合 | `tests/integration/test_lb_writeback_units.py` | 件數語意：投影 Q 為基準、持工具 F>1 無假警報、以投影 Q 比出不符、repeat 列比投影 Q 不比 frequency、投影失敗 → `units_baseline=unavailable` 不 500、payload 無 units → `units_uncomparable`、未知 `qty_scope` → 422、全 Q=1 → `not_needed`、舊快照 `latest` → 422；apply-offline 投影拋例外（持工具 F=3 且 N=3）→ 200 ＋ `report.status=unavailable`＋E 碼、`errors`／`warnings` 為 `null`、離線照常套用，且 `latest` 讀回 `applied_report_status`／`reasons`／`errors`（與回應的 `reason_details` 逐欄相同） |
| 整合 | `tests/integration/test_lb_writeback_model.py` | B1 資料模型 roundtrip、FK cascade |
| E2E | `src/frontend/e2e/writeback-line-view.spec.ts` | import 樣本 → 產線視角顯示站別／人／差異（含「共 8 件（推算）」）→ 套用離線 → 重新載入仍正確；路徑三（2026-09-22）：注入 `export_warnings`（非正規拼法、setup_not_one／conservation／未知 reason、對不上的降級、丟列、`truncated`）→ UI 文案逐條斷言，並量步驟名稱渲染寬度（標記不得把它擠掉） |
| **真機驗證（已驗 2026-09-18；LB 修正後全鏈複驗通過 2026-09-18；~~units 語意一項未決~~ units 語意已裁 2026-09-18；第三輪 2026-09-22，`export_warnings` 消費後）** | `src/frontend/e2e/writeback-golden-replica.spec.ts`：①離線 `import`——複本用隨機 id，fixture 的 `source_wi_row_id` 依 seq_no 改寫成複本 id 後餵入；②真機端到端（`@slow`，約 1 分鐘）——MOST 建複本 → 匯出 lb-csv → 上傳 LB 建專案 → 求解 → MOST `fetch` → 刪除該 LB 專案（清理失敗即測試失敗）。未設 `E2E_LB_BASE_URL` 即 skip；設了卻缺 `E2E_LB_AUTH_HEADERS` 的三個身分 header（或只設了後者）直接失敗。兩條跑同一組斷言，並以 `GET latest` 讀回再驗 | **第一輪（管路）**：LB 直跑 `:8090`（不經 Traefik）跑 `fetch` 全鏈可行。發現：LB **應用本身**檢查身分 header，最小需 `X-User-Id`＋`X-Plant-Code`＋`X-Username` 三個（缺任一 401）——MOST client 已改帶一組 header（`DDM_LB_AUTH_HEADERS`）。當時 `rows=0` 的成因＝**LB 上傳 CSV 標準化丟欄**（`source_wi_row_id`／`role_type`／`general_role`，STD_COL 寫死 22 欄），LB 端缺陷、非 MOST 問題。**複驗（LB `feature/most-integration-phase2` 含修正 `c0cb244` 後）**：先以沿用 fixture 固定 id 的複本對既有 result 呼叫 `fetch` 驗過；該做法讓測試佔用 `wi_rows` 全域主鍵，撞到 dev DB 既有列，已改為上述不佔 id 的設計（Howard 裁，2026-09-18）。端到端實跑結果：rows 34、matched 24／missing 0／unmatched 0；general（seq1 take_unit）已回寫、單列單站；工具五組 acquire／use／release 各聚成單站、無 `cross_station`；~~`frequency=8` 的兩列 `units_total=8`（`unit_mismatches` 為空，但目前只比 frequency 列）~~ Q>1 三個 motion（G、H `frequency=8`；I `repeat_count=8`）`units_total` 皆 8，以 MOST 投影 Q 比對：`unit_mismatches` 空、`units_uncomparable` 空、`summary.units_baseline` 為 `ok`；offline 列無站無人、無 offline 差異；`GET latest` 讀回一致。離線 `import` 路徑同組斷言通過。~~**未決（待裁決）**：repeat 列（seq9，`repeat_count=8`）在 fixture（LB 實跑）中 LB 回 units 1/8/1——setup 列帶的是 `used`（0／1，跨 worker 加總＝經手人數），不是件數（LB ADR-008 D3）——`aggregate` 加總得 10；`diff` 只比 `frequency`、未比 `repeat_count`（D6 寫「frequency／repeat_count」）。e2e 暫只斷言該列聚成單站。~~ **已裁（Howard 2026-09-18，C＋退路；規則見 B4-2／B4-3）**：同一份黃金快照動作 I（seq9，LB units 1／8／1）`units_total` 舊 10 → 新 8（**當時**為 `inferred_max`——LB §8 那時尚未輸出 `qty_scope`）；e2e 改為逐 motion 比投影 Q，並斷言動作 I＝8。**2026-09-21 re-vendor（`4b89bca`）後**：動作 I 仍是 8，但走 cyclic 主路徑（`units_source="cyclic"`）；推算退路改由「剝掉 `qty_scope` 的同一份 fixture」（單元）與 `lot_scope=None`（整合，兩支比對測試參數化）覆蓋，e2e 兩條路徑在同一份複本內先後各跑一次。**第三輪（2026-09-22，`export_warnings` 消費後；`707d0c0`）**：LB HEAD（`integration/phase2-docs` `1454b05`，另起於獨立資料目錄；其後至 `e032875` 的三個 LB commit 皆未動 `src`）＋ MOST 工作樹建置，跑真機端到端。結果：rows 34、matched 24／missing 0／unmatched 0；動作 I `units_total=8`、`units_source=cyclic`；`summary.units_baseline` `ok`；`export_warnings` `present` 且三欄為空（`units_degraded`／`dropped_rows` 空、`truncated=false`）；工具五組各單站、無 `cross_station`；general 單列單站；offline 列無站無人；LB 專案已刪。e2e 為此多兩條驗收（動作 I 必須 `cyclic`——退回 `inferred_max` 代表 LB 端退化；`export_warnings` 三欄在且為空），並把實際值附成 `real-machine-acceptance.json`（放在斷言**之前**，斷言紅時仍看得到）。**2026-09-18 之後的變更至此才有真機驗證**；真機 e2e 只走 `fetch` 全鏈、不含 `apply-offline`，「有降級／有丟列」的路徑仍只由合成資料覆蓋（上方單元／整合與 `writeback-line-view.spec.ts`）。 |

（原規劃的 ~~`tests/unit/test_lb_writeback_parse.py`~~／~~`tests/unit/test_lb_writeback_aggregate.py`~~／~~`tests/unit/test_lb_writeback_diff.py`~~ 三檔未建立，內容併入 `tests/unit/test_lb_writeback_service.py`。）

**fixture**：`docs/lb-integration/fixtures/writeback_sample.json` —— 由 **LB 端實跑**產生（用 LB 的黃金複本結果呼叫 writeback 端點），逐位元 vendor、不得手寫或編輯。取得前先確認 LB 分支 **`integration/phase2-docs`** 可跑（~~`feature/most-integration-phase2`~~——現行 fixture 的來源 commit `106bf14` 只在前者）；取不到就回報，**不要自己捏一份假的**。來源 commit／sha256／ortools 版本／產法、以及 re-vendor 時的處置＝[`fixtures/README.md`](fixtures/README.md)（唯一權威，本書不重抄）。「不得編輯」這句有機械保證：`tests/unit/test_lb_writeback_service.py::test_vendored_fixture_is_the_pinned_lb_artifact`（驗 sha256 ＋ 34 列 ＋ `qty_scope` 分布）——**它紅了代表有人動過 fixture，正確反應是刻意更新該測試的常數與 README，不是重跑產生器把它弄綠**（理由：LB 的決定性是經驗性的，見 README）。

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
7. **不得在未註明理由的情況下把 `X-User-Id`／`X-Username` 設成固定字串**（預設 `@me`；例外須在 `.env` 就地寫理由——規則與理由見 ADR-036 §4）。

---

## 7. 已知限制（2026-09-18，Howard 裁：寫進文件，不阻擋）

(a) **件數比對基準是 MOST「現在」的投影**，不是匯出當時的：worksheet 在匯出後被改過（frequency／repeat／工具），`unit_mismatches` 反映的是「LB 那次結果 vs MOST 現況」，不是 LB 求解錯誤。

(b) **站別聚合只看 `station_index`、不看 `line_index`**：多線結果時，同一 motion 被排到不同線的同號站不會標 `cross_station`，跨線漂移偵測不到。

(c) **`lb_row_placements` 沒存 `qty_scope`**：重算一律以快照 `payload` 為準（B2 注意）；若日後要從 placements 查件數，需先加法 migration 補欄。LB 自 `64e4abd` 起輸出該欄後，這個落差已是實際存在（payload 有、表沒有），不再只是理論上的。

(d) **UI 尚未顯示 `unit_mismatches`／`units_uncomparable` 的警告**：ADR-036 D6 寫的是「不一致 → 警告」，目前只到 API 回應（F2 只顯示件數與推算標示、基準不可用提示）。→ [BL-ENG-3](../BACKLOG.md)。

(e) **回寫區塊不區分讀取錯誤**：`GET latest` 的任何失敗（404 無快照、5xx、舊快照 422）都顯示「尚無結果」引導文案（F2），失敗原因不會顯示在該區塊。→ [BL-ENG-3](../BACKLOG.md)（與 (d) 同票：同一類「把異常講成正常」的顯示語意；該票另含一處站別文案，本節未列）。

(f) **offline 組內傳染有兩份實作**：後端 `lb_writeback_service._group_members` 與前端 `store.toggleOffline` 各寫一次，規則對齊靠人維持（B6-2）；統一為共用函式見 [BL-ENG-1](../BACKLOG.md)（原記「另案」，2026-09-21 給票號）。

(g) **投影層數類例外直接拋出、不收 E 碼**：`QuantityError`／`ToolResolveError`／`TmuDecompositionError` 會逃到呼叫端（`PrecedenceError` 在 `project_rows` 內就被接住轉成收集型 E，服務端仍列著它只是縱深），由呼叫端各自防守——回寫端點已降級為 `units_baseline=unavailable`／`report.status=unavailable`（B4-4、B6-3），但 `GET /export/lb-report`／`GET /export/lb-csv` 對同一批 worksheet 仍會落成無信封 500。
兩項後果要一起記著：(i) `apply-offline` 的降級是 **fail-open**（逃出來的三類都攜帶確定的 E 碼，閘門跑不起來時仍放行），Howard 2026-09-21 裁定本輪如此；(ii) 收斂根因時若改採 fail-closed，`report.status`／`errors` 的語意會跟著翻轉——屬使用者可見變更，須先裁決並同步 B6-4 與 UI 文案。→ [BL-ENG-2](../BACKLOG.md)（現況、影響與做法見該票；E/W 碼邊界見 ADR-035）。

(h) **LB `export_warnings`：消費後仍存在的已知限制**（2026-09-22 起消費，`707d0c0`；規則見 §2 B4-6，決策見 ADR-036 §2 D7 追記（2026-09-22））：
(i) **清單被截到上限時**（MOST 端 50 筆，B4-6），第 50 筆之後被 LB 降級的步驟不會掛標記——件數被拿掉的（`conservation`）只會講成「LB 沒給件數」（`units_uncomparable.reason="no_units"`）；`truncated` 的提示只說「不只這些」，不說是哪幾步。
(ii) **丟列若只丟掉已對上步驟的其中一列**（例如工具三列只丟了 cyclic 列），該步驟照樣 matched，顯示成沒件數或站數偏少，**且不帶** `lb_dropped_possible`——旗標只加在整步都沒回來的缺口上。→ [BL-ENG-14](../BACKLOG.md)。
~~**LB 的 `export_warnings` 尚未消費**：LB §8 已定義頂層 `export_warnings`（`units_degraded`／`dropped_rows`／`truncated`，宣告「恆存在」）**且 LB 端已實作**（LB `b90c611` 定義、`bb0d340` 實作，皆在 `integration/phase2-docs`）；MOST 的 `parse` 忽略未知頂層欄位（加法相容），因此**既不會壞、也拿不到這些資訊**。後果是兩個「合理但錯誤的故事」：LB 因對應鍵壞掉而丟棄的列，MOST 會算進 `missing`、UI 講成「這一步沒有產線平衡結果」；LB 因違反 ADR-008 D3 不變量而主動把該列 `units` 降級為 `null` 的列，MOST 只讀得出「LB 沒給件數」（`units_uncomparable`／退路推算），看不出那是 LB 自己標記的缺陷指示。黃金 fixture（LB `106bf14`）早於該實作、不帶此欄，故這條路徑目前**零測試覆蓋**。→ [BL-ENG-10](../BACKLOG.md)（本輪不做；消費規則待 LB §8 定稿後才給——現況、影響與做法見該票，本節不重抄）。~~（2026-09-22 已消費：原文的兩個「合理但錯誤的故事」已由 §2 B4-6 分開講；原票 BL-ENG-10 已結。）

另：ADR-036 D6「件數」一條 ~~待整合架構師修訂~~ **已於 2026-09-21 修訂完成**（見 ADR-036 §2「D6 件數修訂」）；~~LB §8 仍未定義 `rows[].qty_scope`，補上前件數一律為推算值（`inferred_max`）~~ **LB §8 已定義並輸出該欄**（LB `64e4abd`，2026-09-21）：件數走 cyclic 主路徑＝確定值，推算退路只留給舊快照。
