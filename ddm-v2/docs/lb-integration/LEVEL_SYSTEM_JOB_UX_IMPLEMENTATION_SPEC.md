# Level System「作業版」實作書（implements ADR-035 D10 修訂 2026-09-12）

> 位階：實作書（與 `LB_PROJECTION_IMPLEMENTATION_PLAN.md` 同級）。語意權威仍是 `MOST_LB_DATA_CONTRACT_SPEC.md`（下稱 Spec）與 ADR-035；本檔只規定「怎麼把同一份語意做成一般使用者看得懂的 UI」。與 Spec／ADR 衝突時以 Spec／ADR 為準，並回報 User。
> 讀者：執行 agent（MOST／ddm-v2）。工作範圍**只在** `/home/howard/workspace/most-builder/ddm-v2`。LB repo 唯讀。
> 設計來源：`docs/lb-integration/prototypes/level-jobs/`（可跑的 HTML 原型；**只當設計參考，程式碼不得移植**，見附錄 C）。

---

## 0. 範圍、不做、完成定義

### 0.1 一句話
把現在的 Level System（sub／cub／wcub／offline／segment／pin／general／merge_lock 的 IE 詞彙）包成一個**只講「作業、步驟、順序」**的畫面：使用者把作業排好先後、對每個作業回答最多四個是非題、對「系統看出來的事」按是／否，產線平衡需要的 24 欄就自動準備好。**這一層不接 LLM**；所有句子都是確定性規則＋模板（§7）。

### 0.2 範圍（做）
1. 後端：`wi_rows.wi_group`（作業名稱，四條輸入路徑都填）、**未存檔投影預覽端點**（dry-run，與存檔後 `lb-report` 同一條投影路徑）、報告加法欄位 `rows[]`／`hints[]`／`params`、`level_entries.machine_unattended`（第 9 個 LB 標記，三態；§3.4、B7；2026-09-12 Howard 裁決）。
2. 前端：`level-system` 新增「作業版」視圖（預設）；既有 WP12 視圖保留為「進階檢視」；`hydrate` 還原 `lb_tags`（現況缺失，§5 F1）；四條輸入路徑帶 `wi_group`；完整 zh-TW／en i18n；E2E 與純邏輯測試。
3. 文件：ADR-035 D10 追記（已由架構師寫入）、Spec §8.2 報告加法欄位追記、`frontend-data-flow-spec.md` §7 追記、DOC_REGISTRY。

### 0.3 不做
- 不改投影邏輯（`lb_projection/{tmu,tools,precedence,quantity,mappers,validator,emit}.py` 的語意與輸出）；不改 CSV 24 欄；不升 `CONTRACT_VERSION`。
- 不改 Level System 引擎（`most_engine/level.py` R1–R9）與 `derive()` 的輸出語意。
- 不接 LLM、不做關鍵字猜測（含「conveyor／next station／work order」這類 general 猜測——原型有，正式版**禁止**）。
- 不刪既有進階檢視、nb、離散層級（`1/3`）、難度係數；作業版只是不把它們放在主畫面。
- 不動 LB repo；不寫 `.kiro/`。
- **不新增 `splittable`／`divisible` 的 DB 欄與 UI**：LB 端審計已判 `divisible` 與 quantity 是「兩機制一概念」，ADR-023 §4 明列「MOST 不輸出 `divisible`；收斂到 quantity 另立 ADR」。產品路徑恆輸出 0（§3.2）。

### 0.4 完成定義（DoD）
1. 黃金 fixture 對應的作業編排（附錄 A.5，11 個作業）在作業版 UI 操作後存檔 → `GET .../export/lb-report` 的 `errors=[]`、`tasks_out=34`；`GET .../export/lb-csv` 與 `server_node_tasks.expected.csv` **除 `duration`、`divisible` 兩欄外逐欄相等**（csv 解析後逐欄比，見 §8.3）。
   - **修訂（2026-09-12）**：黃金 fixture 走投影層靜態路徑、**沒有 `slot_inputs`**，無法原樣經 API 重放；E2E 改用「黃金複本」——以真實 `CycleIn`（同 rule-set、同 vocab kind／`name_en`、同 tool、同 frequency、同 repeat 格位、同 `x_seconds`、同 level／lb_tags）經 API 建 24 列。複本的 TMU 與黃金不同，故 `duration` 欄排除；`duration` 的正確性由投影層黃金（fixture 路徑，`test_lb_projection_golden`）保證。`divisible` 排除理由見 §3.2（task 31 1→0）。其餘 22 欄（含 predecessors／group／atomic_group／quantity／qty_scope／tool_id／tool_action／segment／fixed_station／offline_flag／role_type／general_role）逐欄相等——這才是作業版要證明的事：UI 操作產生正確的結構。
2. `POST .../export/lb-report/preview`（未存檔）與存檔後 `GET .../export/lb-report` 對同一份 rows 回傳相同的 `errors／warnings／tasks_out／groups／atomic_groups／hints`（§8.2 整合測試）。
3. 所有新 UI 字串走 i18n（zh-TW／en 兩份齊全），`e2e/i18n-hardcoded-zh.spec.ts` 綠；34 個 E／W 碼＋4 種提示各有一句使用者語言（§6.3、§6.4）。
4. `npm run typecheck && npm run build` 綠；`PYTHONPATH=src pytest tests/unit -q` 綠；`ruff check` 我方檔案乾淨；`scripts/core_logic/run_all.py` 全綠（不該動引擎）。
5. 既有 `e2e/wp12-lb-tags.spec.ts` 仍綠（進階檢視與 store 介面不破壞）。
6. 每個 WP 一個 commit，訊息 `implements ADR-035 D10: <WP> <一句話>`。

---

## 1. 使用者模型與名詞

### 1.1 使用者只需要懂的三個詞
| 使用者詞 | 定義 | 內部對應（使用者永遠看不到） |
|---|---|---|
| **步驟** | 工時表的一列（一個 MOST motion）。顯示為「第 n 步「敘述」」，n＝工時表列序（1-based）。 | `wi_rows` 一列；`Row` |
| **作業** | 幾個接著做的步驟，有一個名字（例：「裝 HDD」）。名字來自 `wi_rows.wi_group`。 | 一條 **top-level chain**：sub 群組、cub 群組或單一未分組列（Spec §5.3） |
| **排** | 作業順序畫面裡的一橫排。上下＝先後；**同一排＝可以同時做（誰先都行）**；下一排要等上一排全部做完。 | `level_entries.level` 的主層（Spec §5.4、§5.5） |

### 1.2 每個作業最多四個是非題（作業內容抽屜）
| 問題（使用者語言） | 內部對應 |
|---|---|
| 要在**同一個工站**做完（有治具、機台或料架綁在一個位置時勾。中間可以換人。） | 作業＝`cub` 群組（同站不可拆） |
| 要**同一個人一口氣做完**，中途不能去做別的（用工具或做很多次的步驟不適用） | 作業所有步驟同一 `worker_cub` |
| 在**離線區先做好**，不佔線上的時間 | 作業所有步驟 `offline=true` |
| **固定在某一站**做（只有設備焊死在某站時才需要） | 作業所有步驟 `station_pin=n` |

勾選可套用到「整個作業」或「勾選的幾步」（§5 F4）。什麼都不勾＝可移動的作業（`sub`，或單步時未分組）。

### 1.3 步驟層級的少數設定（只在勾選單一步驟時出現）
| 設定 | 內部對應 |
|---|---|
| 這一步是**每台都做一次的通用動作**？（不是／線頭：第一站開頭／每站開頭／每站結尾） | `is_general` + `general_role`（take_unit／scanner／transport，Spec §5.7） |
| 進階（很少用）：工具用完必須放回原位，不可為了省時間跟別的步驟共用一次取放 | `merge_lock` |
| 進階：難度係數 | `coefficient`（既有） |

### 1.4 「系統看出來的事」
畫面下方一個清單，四種類型，依序排列：**要你回答**（是／否）→ **要處理**（E 碼，擋交出）→ **提醒**（W 碼）→ **說明**（資訊）。每一條的句子都由 §7 規則表產生，**沒有 LLM**。

---

## 2. 目標架構

```
                     ┌──────────────── 前端 features/level-system ────────────────┐
 useWiStore.rows ───▶│ useLevelStore（唯一真相：levelMap／groupMeta／wcub／nb）      │
 (Row.wiGroup 新增)   │        ▲                         │                            │
                     │        │ 作業動作（jobsActions.ts）│ derive()（不變）           │
                     │        │                         ▼                            │
                     │  jobsFromStore()  ──▶ JobModel ──▶ 作業版 UI（預設）          │
                     │  （反投影，純函式）                進階檢視（既有 WP12 UI）      │
                     └───────────────┬──────────────────────────────────────────────┘
                                     │ debounce 400ms
                                     ▼
              POST /api/v2/worksheets/{id}/export/lb-report/preview   （未存檔 dry-run）
              GET  /api/v2/worksheets/{id}/export/lb-report            （已存檔）
                                     │  同一條路徑：rows → ProjectionRow → project_rows() → build_report()
                                     ▼
              {contract_version, tasks_out, groups, atomic_groups, errors[], warnings[],
               rows[]（每列摘要）, hints[]（確定性提示）, tasks?[]（開發者表）}
```

原則：
1. **store 仍是唯一真相**。作業版不是第二份狀態，而是 `useLevelStore`＋`useWiStore` 的**反投影**（附錄 A.1）加上一組**只產生「作業形狀」狀態的動作**（附錄 A.2）。兩個視圖同時對同一 store 工作，`derive()`、存檔 payload、既有 E2E 都不變。
2. **後端才是投影權威**（`frontend-ux-spec.md` §8 規則 1；`level-system/api.ts` 註解）。前端不重做 tool 拆列、TMU 分桶、分層 DAG——原型的 `engine.js` 是驗證用鏡像，**不得移植**。
3. **確定性**：hints 由後端投影資料推出（§7），前端只負責把 code＋params 套模板成句子（i18n）。
4. **加法演進**（ADR-011）：新欄位皆 nullable／預設值；報告新欄位不影響 CSV，`CONTRACT_VERSION` 不變。

---

## 3. 資料模型變更

### 3.1 B1 `wi_rows.wi_group`（作業名稱）
- 型別 `Text NULL`；空字串一律正規化為 NULL；`strip()`；長度 ≤ 200（pydantic `max_length=200`）。
- 語意：同一 worksheet 內，**同名＝同一個作業的候選成員**；實際作業邊界由群組決定（附錄 A.1 步驟 3）。名字可重複（兩條 chain 同名時 UI 顯示「名稱 (2)」，資料不改）。
- 落點在 `wi_rows` 而非 `level_entries`：它是 WI 編寫概念，四條輸入路徑在**建列時**就填（§4 B1.3），Level System 只是顯示與改名。與 ADR-035 §3 F（LB 標記放 `level_entries`）不衝突。
- migration：`migrations/versions_v2/v2_0047_wi_rows_wi_group.py`（`op.add_column` / downgrade `op.drop_column`）。
- 進 `content_hash`（`worksheet_revision.content_hash_from_read` 的 `slim.rows[]` 加 `wi_group`）。

### 3.2 `divisible`／`splittable`：**不做**（裁決紀錄）
- 現況事實：投影層 `ProjectionTags.splittable` 與 adapter `_tag("splittable")` 存在，黃金 fixture 的 O 列帶 `lb_tags.splittable: true`（expected CSV task 31 `divisible=1`）——那是為了讓黃金 CSV 覆蓋全部 24 欄。DB（`level_entries`）**沒有**此欄，產品路徑永遠輸出 `divisible=0`。
- 裁決：**維持現況，不加 DB 欄、不加 UI**。理由：LB 端欄位審計判定 `divisible`（結果頁 what-if 拆分許可位，ADR-002）與 `quantity` 是「兩機制表達一概念」（`divisible ⊥ Q>1` 的互斥即證據），ADR-023 §4 明列「MOST 不輸出 `divisible`；收斂到 quantity 另立 ADR」。在 LB 那份 ADR 出來前，MOST 端不投資這個欄。
- 影響：DoD-1 的黃金比對排除 `divisible` 欄（§0.4）；`E_SPLITTABLE_CONFLICT` 在產品路徑不會觸發，其使用者語言句（§6.3）僅為 34 碼目錄完整性保留；契約 Spec §6 `divisible` 列已追記此事。

### 3.3 不變
`level_entries` 其餘欄、`most_cycles`、投影層輸入型別 `ProjectionRow`（`extra="forbid"`，adapter 明列鍵，因此 `wi_group` 不需進投影層）。

---

### 3.4 B7 `level_entries.machine_unattended`（第 9 個 LB 標記，2026-09-12 Howard 裁決）
- `Boolean NULL`，**三態**：`null`＝未回答、`false`＝人要顧、`true`＝人不用顧。`LevelFieldsIn.machine_unattended: bool | None = None`；`read_worksheet().rows[].lb_tags.machine_unattended`；`ProjectionTags.machine_unattended: bool | None = None`；adapter `_tag("machine_unattended")`。
- 語意：契約 Spec §6 `role_type` 修訂——`machine` ⇔ CM ∧ `x_seconds ≥ 1` ∧ `machine_unattended == true`；其餘 `human`。`mappers.role_type` 依此改。**事實在 MOST、政策在 LB**（LB 求解參數 `unattended_machine_policy`，ADR-023 D9 追記）。
- 與 §3.2 被否決的 `splittable` 不同：本欄是 solver 消費的物理事實，沒有別的欄能表達。
- migration：`v2_0048_level_entries_machine_unattended.py`。
- 黃金 fixture 必須跟著改（契約驗收物，兩 repo 各有副本）：L2（seq 15）、P2（seq 23）加 `lb_tags.machine_unattended: true`；N2（seq 19，「握著擋板」）加 `false`。expected CSV **只有 task 29 `role_type` machine→human**，其餘逐位元不變。hints 快照：`H_MACHINE_TIME` 三條全部消失（三列都已回答）→ 快照剩 3 條 `H_TOOL_DECOMPOSED`。LB 端副本由 LB agent 在 WP-L9 同步。

## 4. 後端工作包

### B1 `wi_group` 全路徑
1. `models/v2/worksheet.py::WiRow.wi_group`；migration v2_0047。
2. `schemas/v2/worksheet.py::WiRowSaveIn.wi_group: str | None = Field(None, max_length=200)`；validator：`strip()`，空→None。
3. 四條輸入路徑寫入（**全部**）：
   | 路徑 | 檔案 | 值 |
   |---|---|---|
   | 手動／工時表存檔 | `worksheet_service.save_worksheet`（`session.add(WiRow(...))` 處） | `r.wi_group` |
   | AI 草稿（nl-draft） | 前端（§5 F7）——後端無需改：採用草稿時前端把 `plan.source_text` 帶進列的 `wiGroup`，存檔走上一列 | — |
   | Excel 匯入 | `schemas/v2/import_excel.py::TARGET_FIELDS` 加 `"wi_group"`（非必填）；`import_service`（`WiRow(` 建立處）`wi_group=(row.get("wi_group") or None)`；`apply_mapping` 把該欄當純文字帶過 | 對應欄文字 |
   | 動作模組實體化 | `motion_module_service`（`session.add(WiRow(` 於 materialize） | `module.name_zh`（該次實體化的所有列同名） |
4. `read_worksheet`：rows[] 加 `"wi_group": wr.wi_group`。`clone_worksheet`：複製。`content_hash_from_read`：加入。`worksheet_revision` 快照列（有 `sub_activity` 的那個 dict）：加入。
5. 前端型別 `WsReadRow.wi_group: string | null`（§5 F1）；`npm run gen:api` 若 `openapi.json` 由後端重生則重生 `api.d.ts`（現況 `gen:api` 讀 repo 內 `openapi.json`；照 WP12 慣例處理）。
6. 測試：`tests/integration/test_wi_group_roundtrip.py`（存→讀→clone 相等；content_hash 隨 wi_group 變）；`tests/unit/test_import_excel_wi_group.py`（mapping 帶 `wi_group` → 建列有值；未對應 → None）；`tests/unit/test_motion_module_materialize_wi_group.py`（實體化列 `wi_group == name_zh`）。

### B2（取消）
原規劃第 9 標記 `splittable`；依 §3.2 裁決不做。編號保留避免其他章節錯位。

### B3 未存檔投影預覽端點（dry-run）
- 路由：`POST /api/v2/worksheets/{worksheet_id}/export/lb-report/preview?include_tasks=0|1`（`api/routes/v2/export.py`，權限同 `lb-report`：viewer+，ADR-019 Option A）。
- Body：`WorksheetSaveIn`（與 `PUT /worksheets/{id}` 同型；`base_revision` 忽略）。
- 行為：**不寫 DB**。`export_service.lb_preview_report(session, ws_id, payload, include_tasks)`：
  1. worksheet 不存在 → 404（同其他匯出端點）。
  2. 逐列以 `save_worksheet` 同一套 helper 計算（`resolve_cycle_rule_set` → `cycle_in_to_engine` → `compute_cycle`；`build_narrative_en`）。**抽出共用函式** `worksheet_service.compute_rows_for_save(session, ws, payload) -> list[ComputedRow]`（含 `result.slot_tmus/letters/total_tmu/total_seconds`、`narrative_zh/en`、vocab 名），`save_worksheet` 改呼叫它（行為不變，既有測試須綠）。engine 例外 → 與存檔相同的 422 錯誤碼（`RowSequenceError` 等）。
  3. 組 `ProjectionRow`：直接由 `ComputedRow` 建（不經 DB）：`cycle.slot_tmus=result.slot_tmus`、`total_tmu`、`narrative_en`、`slot_inputs=r.cycle.model_dump(mode="json")`、`rule_set_code`；`level`／`lb_tags` 來自 `r.level`；`wi_row_id=str(r.id)`；`tool_vocab=str(r.tool_vocab_id)`；vocab 表用 `_load_vocab`。實作為 `lb_projection/adapter.py::rows_from_save_payload(payload, computed, vocab)`，與 `rows_from_worksheet` 並列（同一份對映規則，抽共用 `_build_projection_row(...)` 避免兩份）。
  4. `project_rows(...)` → `build_report(...)`（B4）。
- 回應：與 `lb-report` **同一個 builder** 的同一形狀（B4），另含 `"worksheet_id"`、`"preview": true`。
- 效能：≤ 200 列 < 300 ms 為目標；不快取。
- 測試：`tests/integration/test_export_lb_preview.py`：同一份 rows「preview」與「PUT 後 GET lb-report」的 `errors／warnings／tasks_out／groups／atomic_groups／hints／rows` 逐鍵相等；preview 後 DB 無變化（row count、content_hash 不變）；`include_tasks=1` 回 24 欄 dicts 且鍵序＝`emit.COLUMNS`。

### B4 報告 builder、每列摘要、確定性提示
1. `lb_projection/project.py::ProjectionResult` **加法**欄位：`plans: list[MotionPlan] = field(default_factory=list)`、`chains: list[Chain] = field(default_factory=list)`（既有建構呼叫不變）。
2. 新檔 `lb_projection/report.py`：
   ```python
   def build_report(result: ProjectionResult, rows: list[ProjectionRow], *, include_tasks: bool = False) -> dict[str, Any]
   ```
   回傳（`lb_export_report` 與 `lb_preview_report` 都改呼叫它；既有鍵與值**不變**）：
   ```
   contract_version, worksheet_id（呼叫端補）, tasks_out, groups, atomic_groups, tool_episodes（維持 []）,
   errors[{code, wi_row_id, message, params}], warnings[同],
   rows[{wi_row_id, task_ids[], tool_id, parts[], repeat_n, frequency, quantity, qty_scope,
         x_seconds, is_general, general_role, duration_ms_total}],
   hints[{kind, key, wi_row_ids[], params}],
   tasks?[24 欄 dict]（include_tasks 時）
   ```
   - `parts`：`plan.parts` 的字串子集（`acquire/use/release`）；非工具列＝`["use"]`。
   - `repeat_n`：工具列且 `plan.decomposed` 非 None 時＝`plan.decomposed.n`（`tmu.Decomposed.n`；R 空時為 1），否則 `null`。
   - `quantity／qty_scope`：取該列 `use` task（單列＝該 task）。
   - `x_seconds`：`row.cycle.x_seconds`。
   - `duration_ms_total`：Σ 該列 tasks 的 `duration × (quantity if qty_scope=='cyclic' else 1)`。
3. 新檔 `lb_projection/hints.py`：`def hints(result, rows) -> list[Hint]`（純函式；規則見 §7.2；**只用投影資料**，不看敘述文字）。
4. `lb_projection/errors.py::ProjectionError` 加 `params: dict[str, Any] | None = None`（frozen dataclass 預設欄，加法）。填值處（最小集合，§7.3 模板需要的）：
   | 碼 | params |
   |---|---|
   | `E_TOOL_NOT_RELEASED`、`E_TOOL_CROSS_CHAIN`、`E_TOOL_ACQUIRE_DURATION_MISMATCH`、`E_TOOL_RELEASE_DURATION_MISMATCH`、`E_TOOL_ID_SHARED_ACROSS_LOT`、`W_TOOL_NAME_EN_MISSING`、`W_GENERAL_WITH_TOOL` | `{"tool_id": ...}` |
   | `W_TOOL_FREQ_ALL_CYCLIC`、`W_FRACTIONAL_FREQUENCY_BAKED`、`E_TOOL_FRACTIONAL_FREQUENCY` | `{"frequency": ...}` |
   | `E_REPEAT_MIXED`、`E_REPEAT_NONCONTIGUOUS` | `{"counts": {...}}`（可缺） |
   其餘 `None`。既有 `message` 文字**不改**（既有測試斷言 message）。
5. 測試：`tests/unit/test_lb_projection_report.py`（黃金 fixture：`rows` 長度 24；general 列 `is_general`；電動起子列 `parts==["acquire","use","release"]` 且 `repeat_n==8`；`tasks_out==34`；`include_tasks` 鍵序）；`tests/unit/test_lb_projection_hints.py`（§7.2 每條規則各一個合成正例＋一個反例；黃金 fixture 的 hints 快照 `docs/lb-integration/fixtures/server_node_hints.expected.json`——首次由 agent 產出，**列在回報中請 User 過目**後才鎖）；`tests/unit/test_lb_projection_errors_params.py`（上表每碼反例帶 params）。

### B5 `lb-report`（已存檔）同步升級
- `export_service.lb_export_report` 改為 `_project` → `build_report(...)`；回應鍵超集，既有 E2E（`wp12-lb-tags.spec.ts` 讀 `tasks_out／atomic_groups`）不變。
- `include_tasks` 查詢參數同樣支援。

---

### B7 `machine_unattended` 全路徑（§3.4）
1. model／schema／read／save／clone 五處對稱加欄（比照 WP1 八欄，型別 `bool | None`）；migration v2_0048。
2. `lb_projection/models.py::ProjectionTags.machine_unattended`、`adapter.py` 兩條路徑（`rows_from_worksheet`／`rows_from_save_payload`）帶入。
3. `mappers.role_type`：`"machine" if seq_kind=="CM" and x_seconds>=1 and lb_tags.machine_unattended is True else "human"`。
4. `hints.py` `H_MACHINE_TIME`：改為 **ask**，條件加 `lb_tags.machine_unattended is None`（§7.2）；params 加 `{"x_seconds": …}`。
5. 黃金：fixture 三列加 tag（§3.4）；重跑投影更新 `server_node_tasks.expected.csv`（差異必須只有 task 29 `role_type`——用 csv 逐欄 diff 證明，貼在回報）；`server_node_hints.expected.json` 更新為 3 條；`fixtures/README.md` 註記。
6. 測試：`tests/integration/test_worksheet_lb_tags_roundtrip.py` 加三態 roundtrip（null／false／true 各一）；`tests/unit/test_lb_projection_mappers.py` 加 role_type 三案（x≥1 ∧ true → machine；x≥1 ∧ null → human；x≥1 ∧ false → human）；hints 測試加「已回答不再問」；golden 測試更新後全綠。

## 5. 前端工作包

> 目錄：`src/frontend/src/features/level-system/`。新檔以 `jobs*.ts(x)` 命名；既有 `LevelSystem.tsx` 的內容搬到 `AdvancedView.tsx`（進階檢視），`LevelSystem.tsx` 變成外殼（視圖切換）。`store.ts`／`logic.ts`／`derive()` 的既有介面不變（只加）。

### F1 基礎修復與共用抽出（先做，獨立可交付）
1. **`hydrate` 還原 `lb_tags`**（現況 bug：`useWorksheetWorkspace.ts` 把 8 個標記全設預設值，註解「WsReadRow.level 目前未回傳這些欄」已過時——後端 `read_worksheet` 早已回 `lb_tags`）。改為：
   ```ts
   const tags = row.lb_tags
   workerCub: tags?.worker_cub ?? '', offline: tags?.offline ?? false, segment: tags?.segment ?? '',
   stationPin: tags?.station_pin ?? '', isGeneral: tags?.is_general ?? false, generalRole: tags?.general_role ?? '',
   mergeLock: tags?.merge_lock ?? false, actionType: tags?.action_type ?? '',
   ```
   並重建 `workerCubMeta／wseq`（依出現順序；`hydrate(levelMap, groupMeta, gseq, workerCubMeta, wseq)` 加法簽名，舊呼叫相容）。`WsReadRow` 加 `lb_tags: {...} | null`、`wi_group: string | null`；`level` 加 `order: number | null`。
2. **同 chain 的 `level` 字串統一**：hydrate 後，對每條 top-level chain，把第一成員（rows 序）的 `level` 字串複製到所有成員（附錄 A.3 不變量 I-1；後端對非首列回 `null`，前端補 `String(index+1)` 會讓反投影讀錯）。
3. `Row.wiGroup: string | null`（`wi-workbench/store.ts`），`setRows` 帶入；新增 `updateRows(patch: (r: Row) => Row)`。
4. （原 `splittable` 欄位——取消，見 §3.2。）
5. **存檔 payload 抽出**：`features/wi-workbench/savePayload.ts::buildSaveBody(rows, levelPayload, baseRevision)`（內容＝現 `doSave` 的 body 物件，每列加 `wi_group: r.wiGroup ?? null`）；`useSaveWorkspace()` hook（mutation＋`setRevisionMeta`＋三個 `invalidateQueries`）。`WiWorkbench.doSave` 與作業版共用。
6. 關卡：`wp12-lb-tags.spec.ts` 綠；新增 `e2e/level-hydrate-tags.spec.ts`（API 存 3 列帶 offline／worker_cub／segment → 重新載入 → `__ddmTest.levelStore` 的 `levelMap` 帶回相同值）。

### F2 `jobs.ts`：作業模型、反投影、動作（純邏輯，可離線測）
- `jobsModel.ts`：型別
  ```ts
  export interface Job { id: string; name: string | null; steps: string[]; generalSteps: string[]
    row: number; rowHi: number | null; discrete: string | null
    sameStation: boolean; samePerson: boolean; offline: boolean; pin: number | null
    cubLabel: string | null; subLabel: string | null; wcubLabel: string | null }
  export interface StepTag { cub?: string; wcub?: string; offline?: boolean; pin?: number; segment?: string
    generalRole?: string; mergeLock?: boolean; actionType?: string; coefficient?: number }
  export interface JobModel { jobs: Job[]; stepTags: Record<string, StepTag>; layers: number[] }
  ```
- `jobsFromStore(rows, levelMap, groupMeta): JobModel`——附錄 A.1 的演算法，純函式、無副作用、對相同輸入回相同輸出（job 順序、id 穩定）。
- `jobsActions.ts`：附錄 A.2 表列動作，每個動作＝對 `useLevelStore.getState()`／`useWiStore.getState()` 的一組呼叫，**結束前一律** `restampLayers()`（A.3 I-1、I-2）。`store.createGroup` 改為回傳新 label（加法；現況回 void）。
- `layers.ts`：`parseLevel('2')→{lo:2,hi:2}`、`'2~3'→{lo:2,hi:3}`、`'1/3'→{discrete:'1/3'}`；`fmtLevel(lo,hi)`；`normalizeLayers(jobs)`。
- `proposeBaseline(rows, levelMap): Action[] | null`（附錄 A.4；F3 使用）。
- 測試：`e2e/level-jobs-logic.spec.ts`——**純 node 測試（不用 `page`／`request` fixture，不需伺服器）**，用 `@playwright/test` 的 `test()` 直接 import `../src/features/level-system/{jobs,jobsActions,layers}`（`tsconfig.e2e.json` 需能解析 `src/`；若不行，加 `paths`）。案例見 §8.3。

### F3 作業順序畫面（`JobsFlow.tsx`）
- 由 `layers` 逐排渲染 `band`：排號、提示（「這 N 個作業可以同時做，誰先都行；都要等上一排全部做完」／「這一排只有一個作業」）、作業卡。
- 作業卡：名稱（`name ?? rowNarr(firstStep)`；同名第 k 條加「 (k)」）、「k 步 · 約 s 秒」（s＝Σ report.rows[wi_row_id].duration_ms_total/1000，report 未到前顯示 `Σ seconds×freq`）、chips（🏭 同一工站／部分同站、👤 同一個人／部分同人、⏸ 離線先做、📍 第 n 站、⭐ 通用×k、同一批人、🔧 工具名、要處理 k）、按鈕「◀ 跟上一排一起做」（`mergeUp`）、「▶ 自己一排」（同排 >1 時；`ownRow`）。
- 拖放：卡拖到另一張卡＝同排（`joinLayerOf`）；拖到兩排之間的 gap＝接著做（`placeBetween`）。用 HTML5 DnD（既有 workbench 已用 `dragIdx` 慣例）。鍵盤替代：上述兩個按鈕。
- 點卡片＝開右側抽屜（F4）。`data-testid`：`job-card-<jobId>`、`layer-band-<n>`、`job-merge-up`、`job-own-row`。
- 首次進入：若 `proposeBaseline` 非 null → 套用並顯示通知條「已依作業名稱整理成 N 個作業（尚未儲存）［還原］」（❓§13-1）。

### F4 作業內容抽屜（`JobDrawer.tsx`）
- 標題＝作業名稱（可改名：inline input → `rename`；空白不可）。
- 範圍列：「以下設定套用到**整個作業（k 步）**；要只設其中幾步，先在下面勾步驟」／「套用到**勾選的 m 步**（取消勾選＝整個作業）」。
- 四個是非題（§1.2）；狀態由 `Job` 或勾選子集的 `stepTags` 推得；規則：
  - 同一工站：整個作業 → `setSameStation`；子集 → 巢狀 cub（`setSameStation(job,on,subset)`；作業已是 cub 時勾選框顯示為勾選且 disabled，提示「整個作業已是同一工站」）。作業內有「部分同站」而勾整個作業時，先確認「作業內原本 N 個部分同站設定會被整個作業的同站取代」。
  - 同一個人：目標步驟有 `!canAssignWcub`（freq>1 或工具持握）→ 勾選框 disabled，說明「有 k 步用工具或做很多次，不能加同一人。可只勾其他步驟」。
  - 離線：作業為同一工站時只能整個作業；子集離線只允許「不與巢狀 cub／wcub 部分重疊」，否則提示並整組套用（避免 `E_OFFLINE_INCONSISTENT`）。
  - 固定站：數字輸入（≥1，空白＝不固定），整個作業。
  - 進階（收合）：「最晚可以排到第 N 排」（`rowHi`，≥row）；離散層級存在時顯示「這個作業用了進階層級 {{discrete}}，產線平衡不支援 ［改成第 N 排］」。
- 步驟清單（照做的順序）：勾選框、序號、敘述（`useRowNarr`，隨語言）、chips（⭐ 通用、部分同站、部分同人、離線、同一批人、🔧 拆 k 步、做 n 次、拿一次做 N 次、機台 x 秒——來自 report.rows）、上下移（`reorderStep`）。
- 勾選 ≥1 步：「拆成新作業」（`splitSteps`，名字 prompt 預設第一步敘述）、「移到別的作業…」下拉（`moveStepsTo`）。
- 勾選恰 1 步：通用動作下拉（不是／線頭（第一站開頭）／每站開頭／每站結尾）→ `setGeneral`；「進階（很少用）」：merge_lock、難度係數、action_type（IE 標籤，選填）。
- `data-testid`：`drawer-q-station`、`drawer-q-person`、`drawer-q-offline`、`drawer-pin-input`、`drawer-step-<rowId>`、`drawer-split`、`drawer-move-select`、`drawer-general-select`。

### F5 「系統看出來的事」（`Notices.tsx` + `notices.ts`）
- 資料來源：預覽報告（F6 hook）的 `hints[]`、`errors[]`、`warnings[]`＋`useValidateLevel` 的 R1–R9 issues（作業版動作應使其恆為空；若出現，型別 err、原文顯示）。
- 排序：ask → err → warn → info。每條：句子、按鈕（ask：是／否；有列的：去看＝開該作業抽屜並勾該步；warn／info：知道了）。已回答／知道了的 key 進 `dismissed`（session 記憶，切 worksheet 清空；❓§13-7）。
- 句子產生：§7.3／§7.4 模板，`t('levelSystem.plain.<CODE>', {step, steps, tool, freq, n})`；缺模板 → 後端 `message`。`HIDDEN_W = ['W_AUTO_GROUP_FOR_LOT','W_ACTION_TYPE_FALLBACK','W_NB_UNSUPPORTED','W_SIMO_COLLAPSED','W_TOOL_NAME_EN_MISSING']`（不顯示；進階檢視仍列）。
- 「是」的動作（§7.2 第 4 欄）呼叫 `jobsActions`。`H_MACHINE_TIME` 是唯一「否」也要寫回的提示：是＝`setMachineUnattended(id, true)`、否＝`setMachineUnattended(id, false)`；兩者都會讓該提示消失（三態變非 null），不走 `dismissed`。
- **F10（併入本 WP）**：`LevelCell.machineUnattended: boolean | null`（`blankCell` 為 `null`）；`derive()` 輸出 `machine_unattended`；hydrate 還原；`store.setMachineUnattended(id, v)`；抽屜步驟 chip 三態文案（§6.1 `chip.machineUnknown／machineAttended／machineUnattended`）；步驟進階區可改答案（下拉：未回答／要顧／不用顧）。
- `data-testid`：`notice-<key>`、`notice-yes`、`notice-no`、`notice-goto`。

### F6 預覽 hook、產線視角、開發者表、交出
- `useLbPreview(worksheetId, rows, levelPayload, enabled)`：`useMutation` POST preview；由 `JobsShell` 以 `useEffect` 監看 `rows／levelMap／groupMeta`，debounce 400 ms，取消前一個未完成請求（`AbortController`）；回應存於元件 state（不進 store）。422 → 通知條「第 n 步的 MOST 內容有問題，請回工時表修正：{{message}}」。
- 頂列 pills：「待回答 n」「要處理 n」「可以交出」；按鈕「儲存」（`useSaveWorkspace`）、「儲存並交給產線平衡」（存檔成功 → `window.location.href = /api/v2/worksheets/{id}/export/lb-csv`；有 E 碼時 disabled）。既有 `ExportPanel` 的「須先存檔才能預覽」限制在作業版**移除**（預覽走 dry-run）；進階檢視維持原樣。
- 產線視角（`LineView.tsx`）：⭐ 線頭 marker（take_unit）→ 每排的作業方塊（名稱、k 步、秒、📍、🏭、⏸ 樣式）→ ⭐ 每站開頭／每站結尾 marker；頁尾「產線平衡會收到 **N** 個工作項（用工具的步驟已自動拆成拿起／使用／放回）· 一個人從頭做到尾約 **s** 秒 · 還有 k 件要處理才能交出／可以交出」。
- 開發者表（勾「開發者」才顯示）：`include_tasks=1` 的 24 欄表格（`overflow-x:auto`）。
- 視圖切換：「作業順序｜產線視角」；右上「進階檢視（IE）」切到 `AdvancedView`（同一 store，來回切換不丟狀態）。

### F7 四條輸入路徑帶 `wiGroup`
1. 工時表編輯器（`WiWorkbench.tsx`）：新增「作業」欄（`<input list>` datalist＝現有 `wiGroup` 去重、依出現順序），存在 `cur.wiGroup`；`add()` 寫入 `wiGroup: cur.wiGroup?.trim() || null`；加列後**保留**輸入值（連續加列同作業）。
2. AI 草稿：`AiDraftPanel.onAdoptCycle(cycle, meta: { sourceText: string; runId: string })`（加法參數）；`WiWorkbench` 在 `cur.wiGroup` 為空時設為 `sourceText` 正規化（合併空白、去頭尾、≤ 80 字，❓§13-5）。
3. 既有「WI Outline」（`wiGroups` in-memory state，E-2）改為**由 rows 的 `wiGroup` 推得**（依首次出現排序）；「加入 WI」＝`updateRows` 設 `wiGroup`；「刪除」＝清成 null。既有 i18n key（`workbench.wiEditor.outlineTitle` 等）沿用。
4. Excel 匯入：`ImportModal` 的欄位對應自動多一格 `wi_group`（後端 `target_fields`）；`fieldLabel` 加 i18n（`importWizard.field.wi_group`：作業／Job）。
5. 模組實體化：後端 B1 已填；前端 `useWorksheet` 重載即可。

### F8 i18n
- 全部新字串在 `shared/i18n/resources/zh-TW.ts`／`en.ts` 的 `levelSystem.jobs.*`、`levelSystem.plain.*`、`levelSystem.hints.*`、`importWizard.field.wi_group`、`workbench.wiEditor.jobLabel／jobPlaceholder`（§6 完整清單）。兩檔 key 集合必須相同（既有 Widen 對稱機制會在 typecheck 抓）。
- 敘述一律經 `useRowNarr`（不把 `t()` 產物存進 state）；複數用 i18next `_one` 形式（en）。
- 關卡：`e2e/i18n-hardcoded-zh.spec.ts`、`e2e/i18n-review.spec.ts` 綠；`e2e/level-jobs-ui.spec.ts` 含切 en 的斷言（§8.3）。

### F9 E2E 與截圖
- `e2e/level-jobs-ui.spec.ts`（§8.3）、`e2e/level-jobs-screenshot.spec.ts` → `docs/lb-integration/screenshots/level-jobs-flow.png`、`level-jobs-drawer.png`、`level-jobs-line.png`（zh-TW）＋ `level-jobs-flow.en.png`。

---

## 6. i18n 目錄（zh-TW／en 文案；key 為準，agent 逐字建立）

> 命名：`levelSystem.jobs.*` UI；`levelSystem.plain.<E/W 碼>` 使用者語言的診斷；`levelSystem.hints.<KIND>.{text,yes}`；`levelSystem.roles.*` 通用角色。插值：`{{step}}`＝「第 n 步「敘述」」、`{{steps}}`＝多個 step 以 `listSeparator` 串、`{{tool}}`＝tool_id 去底線、`{{freq}}`、`{{n}}`、`{{count}}`。

### 6.1 `levelSystem.jobs`（UI）
| key | zh-TW | en |
|---|---|---|
| title | 工序整理 | Process layout |
| subtitle | 把作業排好順序、回答幾個問題，產線平衡需要的資料就準備好了。 | Order the jobs, answer a few questions, and the line-balancing input is ready. |
| view.flow | 作業順序 | Job order |
| view.line | 產線視角 | Line view |
| view.advanced | 進階檢視（IE） | Advanced view (IE) |
| pill.ask | 待回答 {{count}} | {{count}} to answer |
| pill.err | 要處理 {{count}} | {{count}} to fix |
| pill.ok | 可以交出 | Ready to hand over |
| save | 儲存 | Save |
| saveAndExport | 儲存並交給產線平衡 | Save and hand over to line balancing |
| dev | 開發者 | Developer |
| flow.hint | 上下＝先後；**同一排＝可以同時做（誰先都行）**。拖作業卡到另一張卡上＝一起做；拖到兩排之間＝接著做。 | Top to bottom = order; **same row = can be done at the same time (either first)**. Drop a card on another card = together; drop between rows = after. |
| flow.bandParallel | 這 {{count}} 個作業可以同時做，誰先都行 | These {{count}} jobs can be done at the same time, in any order |
| flow.bandSingle | 這一排只有一個作業 | Only one job in this row |
| flow.bandWait | ；都要等上一排全部做完 | ; all wait for the previous row to finish |
| flow.gapFirst | 放到這裡 → 最先做 | Drop here → do first |
| flow.gapAfter | 放到這裡 → 接著做 | Drop here → do next |
| card.meta | {{steps}} 步 · 約 {{seconds}} 秒 | {{steps}} steps · about {{seconds}} s |
| card.meta_one（en） | — | {{steps}} step · about {{seconds}} s |
| card.mergeUp | ◀ 跟上一排一起做 | ◀ Do together with the previous row |
| card.ownRow | ▶ 自己一排 | ▶ Own row |
| card.dupSuffix | {{name}} ({{k}}) | {{name}} ({{k}}) |
| chip.station | 🏭 同一工站 | 🏭 Same station |
| chip.stationPart | 🏭 部分同站 | 🏭 Partly same station |
| chip.person | 👤 同一個人 | 👤 Same person |
| chip.personPart | 👤 部分同人 | 👤 Partly same person |
| chip.offline | ⏸ 離線先做 | ⏸ Done offline first |
| chip.pin | 📍 第 {{n}} 站 | 📍 Station {{n}} |
| chip.general | ⭐ 通用×{{count}} | ⭐ General ×{{count}} |
| chip.batch | 同一批人 | Same crew |
| chip.tool | 🔧 {{tool}} | 🔧 {{tool}} |
| chip.toFix | 要處理 {{count}} | {{count}} to fix |
| chip.splitParts | 🔧 {{tool}}：拿起／使用／放回（拆 {{count}} 步） | 🔧 {{tool}}: pick up / use / put down (split into {{count}}) |
| chip.repeatN | 拿一次做 {{n}} 次 | Pick once, do {{n}} times |
| chip.freq | 做 {{n}} 次 | Done {{n}} times |
| chip.machineUnknown | 機台 {{seconds}} 秒（還沒回答人要不要顧） | Machine {{seconds}} s (attendance not answered) |
| chip.machineAttended | 機台 {{seconds}} 秒，人要顧 | Machine {{seconds}} s, operator stays |
| chip.machineUnattended | 機台 {{seconds}} 秒，人不用顧 | Machine {{seconds}} s, no operator needed |
| adv.machineAttendance | 機台跑的時候人要在旁邊嗎？ | Must the operator stay during the machine time? |
| adv.machineUnknown | 未回答 | Not answered |
| adv.machineAttendedOpt | 要顧 | Stays |
| adv.machineUnattendedOpt | 不用顧 | Can leave |
| chip.discrete | 進階層級 {{level}} | Advanced level {{level}} |
| drawer.empty | 點左邊的作業卡，回答幾個問題。大多數作業什麼都不用勾。 | Click a job card on the left and answer a few questions. Most jobs need nothing ticked. |
| drawer.rename | 改名 | Rename |
| drawer.nameEmpty | 作業名稱不可空白 | Job name cannot be empty |
| drawer.scopeAll | 以下設定套用到<b>整個作業（{{count}} 步）</b>；要只設其中幾步，先在下面勾步驟 | Settings below apply to the <b>whole job ({{count}} steps)</b>; tick steps below to apply to some only |
| drawer.scopeSel | 以下設定套用到<b>選取的 {{count}} 步</b>（取消勾選＝整個作業） | Settings below apply to the <b>{{count}} selected steps</b> (untick = whole job) |
| q.station | 要在<b>同一個工站</b>做完 | Must be finished at the <b>same station</b> |
| q.stationHint | 有治具、機台或料架綁在一個位置時勾。中間可以換人。 | Tick when a fixture, machine or rack is bound to one place. Operators may change. |
| q.stationAlready | 整個作業已是同一工站 | The whole job is already same-station |
| q.stationReplace | 作業內原本 {{count}} 個「部分同站」設定會被整個作業的同站取代，繼續？ | {{count}} partial same-station settings in this job will be replaced by the whole job. Continue? |
| q.person | 要<b>同一個人一口氣做完</b>，中途不能去做別的 | Must be done by <b>one person in one go</b>, without switching to other work |
| q.personHint | 例如拿起 HDD 後不能放下去鎖螺絲。用工具或做很多次的步驟不適用。 | e.g. once the HDD is picked up it cannot be put down to drive screws. Not for tool steps or repeated steps. |
| q.personBlocked | 有 {{count}} 步用工具或做很多次，不能加同一人。可只勾其他步驟。 | {{count}} steps use a tool or repeat, so they cannot join. Tick the other steps only. |
| q.offline | 在<b>離線區先做好</b>，不佔線上的時間 | <b>Done offline first</b>, taking no line time |
| q.offlineHint | 預先備料、預裝之類。 | Pre-kitting, pre-assembly and the like. |
| q.offlineWhole | 同一工站的作業要整個一起離線 | A same-station job goes offline as a whole |
| q.pin | <b>固定在某一站</b>做 | <b>Fixed to one station</b> |
| q.pinHint | 只有設備焊死在某站時才需要。 | Only when equipment is hard-wired to a station. |
| q.pinNone | （未固定） | (not fixed) |
| q.pinAt | ：第 {{n}} 站 | : station {{n}} |
| q.pinPrompt | 固定在第幾站？（空白＝不固定） | Which station? (blank = not fixed) |
| adv.title | 進階（很少用） | Advanced (rarely used) |
| adv.late | 最晚可以排到第 {{n}} 排 | May be as late as row {{n}} |
| adv.lateNone | 不延後 | No delay |
| adv.discrete | 這個作業用了進階層級 {{level}}，產線平衡不支援。 | This job uses advanced level {{level}}, which line balancing does not support. |
| adv.discreteFix | 改成第 {{n}} 排 | Change to row {{n}} |
| steps.title | 步驟（照做的順序） | Steps (in working order) |
| steps.select | 選取第 {{n}} 步 | Select step {{n}} |
| steps.up | 上移 | Move up |
| steps.down | 下移 | Move down |
| sel.count | 選取的 {{count}} 步： | {{count}} selected steps: |
| sel.split | 拆成新作業 | Split into a new job |
| sel.splitName | 新作業的名稱 | Name of the new job |
| sel.moveTo | 移到別的作業… | Move to another job… |
| general.q | 這一步是<b>每台都做一次的通用動作</b>？ | Is this step a <b>general action done once per unit</b>? |
| general.hint | 不屬於特定零件，例如把機箱放上線、掃工單、推到下一站。 | Not tied to a part, e.g. putting the chassis on the line, scanning the work order, pushing to the next station. |
| general.no | 不是 | No |
| adv.mergeLock | 這一步的工具用完必須放回原位，不可為了省時間跟別的步驟共用一次取放 | The tool must be put back after this step; do not share one pick-up/put-down with other steps to save time |
| adv.coefficient | 難度係數 | Difficulty factor |
| adv.actionType | 動作類型標籤（選填，給 IE） | Action-type label (optional, for IE) |
| notices.title | 系統看出來的事 | What the system noticed |
| notices.hint | 需要你回答的先列在前面 | Things that need your answer come first |
| notices.yes | 是 | Yes |
| notices.no | 否 | No |
| notices.goto | 去看 | Show me |
| notices.ok | 知道了 | Got it |
| notices.none | 沒有要處理的事。 | Nothing to handle. |
| baseline.applied | 已依作業名稱整理成 {{count}} 個作業（尚未儲存） | Grouped into {{count}} jobs by job name (not saved yet) |
| baseline.undo | 還原 | Undo |
| preview.updating | 更新中… | Updating… |
| preview.rowError | 第 {{n}} 步的 MOST 內容有問題，請回工時表修正：{{message}} | Step {{n}} has a MOST problem; fix it in the worksheet: {{message}} |
| preview.failed | 預覽失敗：{{message}} | Preview failed: {{message}} |
| line.hint | 產線平衡系統會看到的順序與可同時做的作業 | The order and parallel jobs the line-balancing system will see |
| line.head | ⭐ 線頭：{{text}}（每台一次） | ⭐ Line head: {{text}} (once per unit) |
| line.stationStart | ⭐ 每站開頭：{{text}} | ⭐ Start of every station: {{text}} |
| line.stationEnd | ⭐ 每站結尾：{{text}} | ⭐ End of every station: {{text}} |
| line.foot | 產線平衡會收到 <b>{{tasks}}</b> 個工作項（用工具的步驟已自動拆成拿起／使用／放回）· 一個人從頭做到尾約 <b>{{seconds}}</b> 秒 · | Line balancing will receive <b>{{tasks}}</b> work items (tool steps auto-split into pick up / use / put down) · one person end-to-end about <b>{{seconds}}</b> s · |
| line.footBlocked | 還有 {{count}} 件要處理才能交出 | {{count}} things to fix before handing over |
| line.footOk | 可以交出 | Ready to hand over |
| stepLabel | 第 {{n}} 步「{{text}}」 | Step {{n}} “{{text}}” |
| stepShort | 第 {{n}} 步 | Step {{n}} |
| unnamed | （未命名作業） | (unnamed job) |

### 6.2 `levelSystem.roles`（通用角色，使用者語言）
| key | zh-TW | en |
|---|---|---|
| take_unit | 線頭（第一站開頭，把機台放上線） | Line head (start of the first station) |
| scanner | 每站開頭 | Start of every station |
| transport | 每站結尾（推到下一站） | End of every station (push to the next) |

### 6.3 `levelSystem.plain.<CODE>`（E／W 碼的使用者語言；34 碼全列，缺一 typecheck 應紅——用 `satisfies Record<ProjectionCode,string>` 鎖）
| code | zh-TW | en |
|---|---|---|
| E_LEVEL_INVALID | {{step}}：作業之間的先後有問題（{{message}}） | {{step}}: the job order is inconsistent ({{message}}) |
| E_LEVEL_DISCRETE_UNSUPPORTED | {{step}}：用了進階層級（例如 1/3），產線平衡不支援。請在作業內容改成一個排數。 | {{step}}: uses an advanced level (e.g. 1/3) that line balancing does not support. Set a single row in the job panel. |
| E_TOOL_NOT_RELEASED | {{step}}：拿了 {{tool}}，後面沒有放回。請在同一個作業裡加一步「放回」，或確認最後那一步就是放回。 | {{step}}: {{tool}} is picked up but never put down. Add a “put down” step in the same job, or make sure the last step is the put-down. |
| E_TOOL_CROSS_CHAIN | {{step}}：{{tool}} 在別的作業放回。拿與放要在同一個作業裡。 | {{step}}: {{tool}} is put down in a different job. Pick-up and put-down must be in the same job. |
| E_TOOL_TWO_TOOLS | {{step}}：一步同時用兩把工具，請拆成兩步。 | {{step}}: two tools in one step; split it into two steps. |
| E_TOOL_FREQ_AND_REPEAT | {{step}}：這一步「整個動作重複」又「拿一次做多次」同時設了，二選一。 | {{step}}: both “repeat the whole motion” and “pick once, do many” are set; choose one. |
| E_TOOL_FRACTIONAL_FREQUENCY | {{step}}：用工具的步驟，重複次數必須是整數（目前 {{freq}}）。 | {{step}}: a tool step must repeat a whole number of times (now {{freq}}). |
| E_TOOL_ACQUIRE_REPEAT | {{step}}：拿工具只做一次，重複次數請標在使用那一格。 | {{step}}: the pick-up happens once; put the repeat count on the “use” slot. |
| E_REPEAT_MIXED | {{step}}：使用段各格的重複次數不一樣，請統一。 | {{step}}: the use-slots have different repeat counts; make them equal. |
| E_REPEAT_NONCONTIGUOUS | {{step}}：重複的動作中間夾了不重複的動作，請把中間那個拆成獨立一步。 | {{step}}: a non-repeated motion sits between repeated ones; split it into its own step. |
| E_REPEAT_NONLINEAR | {{step}}：這一步的重複無法換算成「一次的時間 × 次數」，請檢查 MOST 內容。 | {{step}}: the repeat cannot be expressed as “time once × count”; check the MOST content. |
| E_TMU_DECOMPOSITION | {{step}}：拆成拿起／使用／放回後時間對不上，請檢查 MOST 內容。 | {{step}}: time does not add up after splitting into pick up / use / put down; check the MOST content. |
| E_TOOL_ACQUIRE_DURATION_MISMATCH | 同一把 {{tool}} 在不同地方拿的時間不一樣。如果是不同放置位置，請把工具取不同名字。 | {{tool}} takes different time to pick up in different places. If these are different locations, give the tools different names. |
| E_TOOL_RELEASE_DURATION_MISMATCH | 同一把 {{tool}} 放回的時間不一樣。如果是不同放置位置，請把工具取不同名字。 | {{tool}} takes different time to put down. If these are different locations, give the tools different names. |
| E_TOOL_ID_SHARED_ACROSS_LOT | {{tool}} 同時用在「做很多次」和「做一次」的步驟上，請把批量用的那把另取名字（暫行規則）。 | {{tool}} is used both in repeated and single steps; give the batch one a different name (interim rule). |
| E_NARRATIVE_EN_MISSING | {{step}}：缺英文敘述。請回工時表重新存檔（系統會補上）。 | {{step}}: English narrative is missing. Re-save the worksheet (the system fills it in). |
| E_SEGMENT_CROSS_GROUP | 「同一批人接著做」的步驟必須在同一個「同一工站」作業裡。 | “Same crew” steps must be inside one same-station job. |
| E_SPLITTABLE_CONFLICT（產品路徑不會觸發，§3.2） | {{step}}：用工具或做很多次的步驟不能標「可拆分」，請取消這一步的設定。 | {{step}}: a tool step or a repeated step cannot be marked “divisible”; untick it. |
| E_ATOMIC_ON_TOOL_MOTION | {{step}}：用工具的步驟不用設「同一個人一口氣做完」——工具動作系統會自動綁同一人。請取消這一步的設定。 | {{step}}: tool steps do not need “one person in one go” — the system binds tool motions to one person. Untick this step. |
| E_ATOMIC_QUANTITY | {{step}}：做很多次的步驟不能設「同一個人一口氣做完」，請改用「同一批人接著做」。 | {{step}}: a repeated step cannot be “one person in one go”; use “same crew” instead. |
| E_ATOMIC_CROSS_GROUP | {{step}}：「同一個人一口氣做完」的步驟跨了兩個「同一工站」的作業。 | {{step}}: “one person in one go” spans two same-station jobs. |
| E_OFFLINE_INCONSISTENT | {{step}}：同一組裡有的設離線、有的沒有。整組要一致。 | {{step}}: some steps in the group are offline and some are not. The whole group must match. |
| E_GENERAL_IN_GROUP | {{step}}：通用動作不能同時在「同一工站／同一個人」的作業裡。 | {{step}}: a general action cannot be inside a same-station / same-person job. |
| E_GENERAL_ROLE_MISSING | {{step}}：通用動作要選一種（線頭／每站開頭／每站結尾）。 | {{step}}: choose a kind for the general action (line head / start of station / end of station). |
| E_GENERAL_ROLE_ACTION_MISMATCH | {{step}}：通用動作的種類和動作類型標籤不符，請改其中一個。 | {{step}}: the general kind and the action-type label disagree; change one. |
| W_TOOL_FREQ_ALL_CYCLIC | {{step}}：整個動作（含拿放工具）重複 {{freq}} 次。如果其實是「拿一次、做很多次」，請把次數標在使用那一格。 | {{step}}: the whole motion (including pick-up/put-down) repeats {{freq}} times. If it is really “pick once, do many”, put the count on the “use” slot. |
| W_FRACTIONAL_FREQUENCY_BAKED | {{step}}：重複次數 {{freq}} 不是整數，已換算成平均時間。 | {{step}}: repeat count {{freq}} is not a whole number; converted to an average time. |
| W_AUTO_GROUP_FOR_LOT | （隱藏） | (hidden) |
| W_NB_UNSUPPORTED | （隱藏） | (hidden) |
| W_FLOATING_TASK | {{step}}：這一步跟其他作業沒有任何先後關係，確定嗎？ | {{step}}: this step has no order relation to any other job. Is that right? |
| W_TOOL_NAME_EN_MISSING | （隱藏） | (hidden) |
| W_GENERAL_WITH_TOOL | {{step}}：通用動作裡用了 {{tool}}，會當成單一步驟輸出。 | {{step}}: the general action uses {{tool}}; it will be output as a single step. |
| W_SIMO_COLLAPSED | （隱藏） | (hidden) |
| W_ACTION_TYPE_FALLBACK | （隱藏） | (hidden) |

### 6.4 `levelSystem.hints.<KIND>`
| kind | text（zh-TW） | text（en） | yes（zh-TW／en） |
|---|---|---|---|
| H_TOOL_EPISODE_SAME_STATION | {{steps}} 是拿起、使用、放回同一把工具（{{tool}}）——這通常在同一個地方做。要標成「同一工站」嗎？ | {{steps}} pick up, use and put down the same tool ({{tool}}) — usually done in one place. Mark them “same station”? | 標成同一工站／Mark same station |
| H_LOT_RUN_SEGMENT | {{steps}} 都做 {{freq}} 次——是同一批人接著做嗎（每人做幾個就扣幾個）？ | {{steps}} are all done {{freq}} times — is it the same crew, one after another (each person's count is deducted)? | 是同一批人／Same crew |
| H_TOOL_DECOMPOSED | {{steps}} 用到 {{tool}}：系統會自動當成「拿起 → 使用 → 放回」三個動作交給產線平衡，你不用另外拆。 | {{steps}} use {{tool}}: the system hands them to line balancing as “pick up → use → put down”; no need to split them yourself. | —（info） |
| H_MACHINE_TIME（ask，2026-09-12 改） | {{step}} 有 {{seconds}} 秒機台時間——機台跑的時候，人要在旁邊顧著嗎？（要顧＝這段時間算人力；不用顧＝人可以去做別的，只算節拍） | {{step}} has {{seconds}} s of machine time — must the operator stay while it runs? (Stays = counts as manpower; can leave = counts toward takt only) | yes＝「不用顧」→ `machine_unattended=true`；no＝「要顧」→ `false`（按鈕文案用 `hints.H_MACHINE_TIME.yes`＝不用顧／Can leave、`.no`＝要顧／Stays，不用通用的是／否） |

### 6.5 其他
| key | zh-TW | en |
|---|---|---|
| workbench.wiEditor.jobLabel | 作業 | Job |
| workbench.wiEditor.jobPlaceholder | 這一列屬於哪個作業（例：裝 HDD） | Which job this row belongs to (e.g. Install HDD) |
| importWizard.field.wi_group | 作業 | Job |

---

## 7. 「系統看出來的事」——確定性規則表（無 LLM）

### 7.1 資料流
```
投影資料（後端 project_rows 的 plans／chains／tasks／errors／warnings）
   → hints.py 規則（只看結構：parts、tool_id、frequency、segment、countersignature、x_seconds）
   → {kind, key, wi_row_ids, params}
前端：code/kind + params → i18n 模板 → 句子；「是」→ jobsActions
```
判斷不看敘述文字、不看零件名、不猜語意；看不出來的事就不提示（寧可少問）。

### 7.2 hints 規則（後端 `lb_projection/hints.py`）
| kind | 訊號（全部由投影資料取得） | params | 前端「是」的動作 |
|---|---|---|---|
| H_TOOL_EPISODE_SAME_STATION | 同一 chain 內，Pattern A 的一個工具 episode（`acquire` 列 → 0..n 個 `use` 列 → `release` 列，同 `tool_id`）跨 **≥2 個不同列**，且這些列**不全在同一個 cub**（`countersignature` 相同且為 cub） | `{tool_id}` | 這些列若＝作業全部非通用步驟 → `setSameStation(job,true)`；否則 `setSameStation(job,true,subset)`（巢狀 cub） |
| H_LOT_RUN_SEGMENT | 同一 chain 內，chain 順序上**連續**的列，`frequency>1`、整數、彼此相等，長度 ≥2，且至少一列 `segment` 為空 | `{frequency}` | 若不全在同一 cub → 先 `setSameStation(job,true,subset)`；再 `setSegment(ids, 'batch'+k)`（k＝現有 segment 名數＋1） |
| H_TOOL_DECOMPOSED（info） | `plan.parts` 長度 >1 的列，依 `tool_id` 分組 | `{tool_id}` | — |
| H_MACHINE_TIME（**ask**） | `seq_kind=='CM'` ∧ `x_seconds ≥ 1` ∧ `lb_tags.machine_unattended is None`（已回答者不再問） | `{x_seconds}` | 「不用顧」→ `setMachineUnattended(id,true)`；「要顧」→ `setMachineUnattended(id,false)`。未回答＝契約送 `human`（保守） |

`key = f"{kind}:{','.join(sorted(wi_row_ids))}"`。同一 key 只出一條。順序：依第一個列的 seq_no。

### 7.3 診斷句（E／W）
- 後端 `errors[]／warnings[]` 每條帶 `code, wi_row_id, message, params`。
- 前端 `plainDiag(d)`：`t('levelSystem.plain.'+d.code, { step: stepLabel(d.wi_row_id), tool: humanTool(d.params?.tool_id), freq: d.params?.frequency, message: d.message })`；`stepLabel(id)`＝`t('levelSystem.jobs.stepLabel', {n: rowIndex+1, text: rowNarr(row)})`；`wi_row_id` 為 null 時 `{{step}}` 插空字串並去掉開頭「：」（模板以 `{{step}}` 開頭者，前端在 step 為空時用 `stepless` 變體：實作為 `t(key, …).replace(/^：|^: /, '')`）。
- HIDDEN_W 五碼不顯示（§5 F5）。
- R1–R9（`/level/validate`）issue：作業版動作應使其恆空；出現時以 `type='err'` 顯示 `message` 原文（不另建模板）。

### 7.4 UI 自產的說明（前端規則，不經後端）
| 情境 | 句子 key |
|---|---|
| 首次進入且套用了 baseline | `baseline.applied` |
| 預覽 422 | `preview.rowError` |
| 作業有離散層級 | `adv.discrete`（抽屜內，不進清單） |

---

## 8. 測試總表

### 8.1 後端 unit（`PYTHONPATH=src pytest tests/unit -q`）
| 檔 | 內容 |
|---|---|
| `test_lb_projection_report.py` | 黃金：`rows` 24 筆、`tasks_out` 34、general 列旗標、電動起子列 parts／repeat_n、`include_tasks` 鍵序＝`COLUMNS`、既有鍵值與舊 `lb_export_report` 相同（回歸） |
| `test_lb_projection_hints.py` | 每規則正／反例（合成 3–5 列 fixture）；黃金 hints 快照 `fixtures/server_node_hints.expected.json`（首次產出需 User 過目） |
| `test_lb_projection_errors_params.py` | §4 B4-4 表每碼反例 `params` 非空且鍵正確 |
| `test_import_excel_wi_group.py` | B1 |
| `test_lb_projection_mappers.py`（追加）、hints「已回答不再問」、golden 更新（task 29 human；hints 3 條） | B7 |
| `test_lb_projection_adapter.py`（追加） | `rows_from_save_payload` 與 `rows_from_worksheet` 對同一份資料產出相等的 `ProjectionRow`（用黃金 worksheet 轉成 save payload） |

### 8.2 後端 integration（有 DB）
| 檔 | 內容 |
|---|---|
| `test_export_lb_preview.py` | preview vs 存檔後 report 逐鍵相等；preview 不寫 DB；422 傳遞；404 |
| `test_wi_group_roundtrip.py` | save→read→clone；content_hash 隨 wi_group 變 |
| `test_motion_module_materialize_wi_group.py` | 實體化列 `wi_group == name_zh`（需 DB；B1 執行時自 unit 移入，2026-09-12） |

### 8.3 前端
| 檔 | 內容 |
|---|---|
| `e2e/level-jobs-logic.spec.ts`（純 node） | (1) 黃金形狀 store fixture（由 `fixtures/server_node_worksheet.json` 的 `rows[].level/lb_tags` 轉成 levelMap/groupMeta）→ `jobsFromStore` 得 **11 個作業**，名稱／排／sameStation／samePerson／stepTags 與附錄 A.5 表逐項相等；(2) 對 (1) 的結果做「無操作」→ `derive()` 輸出與原 fixture 的 level 六欄＋lb_tags 逐列相等（反投影不失真）；(3) 每個 A.2 動作各一案例（前後 `jobsFromStore` 的差異恰為預期；I-1／I-2 不變量成立）；(4) `normalizeLayers`：`[1,1,3,5]→[1,1,2,3]`、含 rowHi；(5) `proposeBaseline`：無群組＋wiGroup 連續同名 → 成 sub、各自一排；已有群組 → null；(6) `plainDiag` 對 34 碼各能產句（zh-TW／en 都不含 `levelSystem.plain` 字樣） |
| `e2e/level-hydrate-tags.spec.ts` | F1 |
| `e2e/level-jobs-ui.spec.ts`（preview_server） | clone demo ws → API PUT 6 列（`wi_group`「裝 HDD」×3、「鎖螺絲」×3，皆 freq 1，第 4–6 列 object＝OBJ）→ 開 level tab → 兩張作業卡、兩排（baseline）→ 點「◀ 跟上一排一起做」→ 同一排 → 開「裝 HDD」抽屜 → 勾「同一個工站」→ 等預覽（`preview.updating` 消失）→ 「儲存並交給產線平衡」→ `GET lb-report` 的 `groups` 有 1 組含 3 個 task；`errors=[]`。反例：勾「同一個人」於含 freq>1 的作業 → 勾選框 disabled 且顯示 `q.personBlocked`。i18n：`PATCH /me/locale` 攔截為 en（沿用 `locale-switcher.spec.ts` 手法）→ 卡片按鈕文字為英文、通知句為英文。 |
| `e2e/level-jobs-golden.spec.ts` | **黃金複本**（§0.4 修訂）：`e2e/support/goldenReplica.ts` 以真實 `CycleIn` 建 24 列（vocab 經 API 建立或重用：object 類＋ tool 類 `scanner`／`electric_driver`／`torque_driver` 帶 `name_en`；GM／CM 依 fixture `seq_kind`；I 列 use 格 `repeat_count=8`；G／H `frequency=8`；L2／N2／P2 `x_seconds` 3／2／20；tool 列帶 `tool_vocab_id`；level／lb_tags／`wi_group` 照附錄 A.5）→ PUT → UI 開啟 → `jobsFromStore` 11 作業（透過 `__ddmTest`）→ 「儲存並交給產線平衡」→ `lb-csv` 與 expected **除 `duration`、`divisible` 外逐欄相等**（csv 解析後逐欄，不用字串 replace；`divisible` 差異只允許 task 31）。另斷言 `tasks_out==34`、`errors==[]`（**DoD-1**） |
| `e2e/level-jobs-screenshot.spec.ts` | 三張 zh-TW＋一張 en |

---

## 9. 執行順序與關卡

| 序 | WP | 前置 | 關卡 |
|---|---|---|---|
| 1 | B1 | — | migration up/down；四路徑測試綠；roundtrip 綠 |
| 2 | F1 | B1 | typecheck/build；`wp12-lb-tags` 綠；`level-hydrate-tags` 綠 |
| 3 | B4 | — | report／hints／params unit 綠；黃金 hints 快照交 User |
| 4 | B3 + B5 | B4 | preview 整合測試綠；舊 `lb-report` 回歸綠 |
| 5 | （B2 取消，§3.2） | — | — |
| 6 | F2 | F1 | `level-jobs-logic` 全綠（含 11 作業、反投影不失真） |
| 6b | B7 | B3 | migration up/down；三態 roundtrip；role_type 三案；黃金 csv diff 只有 task 29；hints 快照 3 條（貼給 Howard） |
| 7 | F3–F6 | F2, B3 | 手動走通黃金 11 作業；`level-jobs-ui` 綠 |
| 8 | F7 | F1 | 四路徑 UI 帶 wiGroup；AI 草稿 sourceText |
| 9 | F8 | 全程 | `i18n-hardcoded-zh`／`i18n-review` 綠；en 截圖 |
| 10 | F9 | 7 | `level-jobs-golden` 綠（DoD-1）；截圖入 docs |
| 11 | 文件（§11） | 全部 | DOC_REGISTRY 狀態更新 |

**F2 的 11 作業測試不綠不得進 F3**（避免把錯的反投影做成 UI）。

---

## 10. 檔案變更總表

| 路徑 | 動作 | WP |
|---|---|---|
| `migrations/versions_v2/v2_0047_wi_rows_wi_group.py` | 新增 | B1 |
| `migrations/versions_v2/v2_0048_level_entries_machine_unattended.py` | 新增 | B7 |
| `src/ddm_v2/lb_projection/{models,adapter,mappers,hints}.py`、`models/v2/worksheet.py`、`schemas/v2/worksheet.py`、`services/v2/worksheet_service.py`（第 9 標記五處） | 改 | B7 |
| `docs/lb-integration/fixtures/{server_node_worksheet.json,server_node_tasks.expected.csv,server_node_hints.expected.json,README.md}` | 改：三列 tag、task 29 human、hints 3 條 | B7 |
| `src/ddm_v2/models/v2/worksheet.py` | 改：`WiRow.wi_group` | B1 |
| `src/ddm_v2/schemas/v2/worksheet.py` | 改：`WiRowSaveIn.wi_group` | B1 |
| `src/ddm_v2/schemas/v2/import_excel.py` | 改：`TARGET_FIELDS` + `wi_group` | B1 |
| `src/ddm_v2/services/v2/worksheet_service.py` | 改：抽 `compute_rows_for_save`；save/read/clone 帶 `wi_group` | B1, B3 |
| `src/ddm_v2/services/v2/worksheet_revision.py` | 改：hash／快照含 `wi_group` | B1 |
| `src/ddm_v2/services/v2/import_service.py`、`motion_module_service.py` | 改：建列填 `wi_group` | B1 |
| `src/ddm_v2/services/v2/export_service.py` | 改：`lb_export_report` 走 `build_report`；新 `lb_preview_report` | B3, B5 |
| `src/ddm_v2/api/routes/v2/export.py` | 改：新 `POST …/lb-report/preview`；`include_tasks` | B3, B5 |
| `src/ddm_v2/lb_projection/{report,hints}.py` | 新增 | B4 |
| `src/ddm_v2/lb_projection/{project,errors,adapter}.py` | 改（加法）：`ProjectionResult.plans/chains`、`ProjectionError.params`、`rows_from_save_payload` | B3, B4 |
| `src/ddm_v2/lb_projection/{tools,quantity,validator,tmu}.py` | 改（僅填 `params`，語意不變） | B4 |
| `tests/unit/test_lb_projection_{report,hints,errors_params}.py`、`test_import_excel_wi_group.py`、`test_motion_module_materialize_wi_group.py` | 新增 | B1, B4 |
| `tests/integration/test_export_lb_preview.py`、`test_wi_group_roundtrip.py` | 新增 | B1, B3 |
| `docs/lb-integration/fixtures/server_node_hints.expected.json` | 新增 | B4 |
| `src/frontend/src/features/level-system/{jobsModel,jobs,jobsActions,layers,notices}.ts`、`{JobsShell,JobsFlow,JobDrawer,Notices,LineView,DevGrid}.tsx`、`AdvancedView.tsx`（原 LevelSystem 內容） | 新增／搬移 | F2–F6 |
| `src/frontend/src/features/level-system/{LevelSystem.tsx,store.ts,logic.ts,api.ts}` | 改 | F1–F6 |
| `src/frontend/src/features/wi-workbench/{store.ts,api.ts,useWorksheetWorkspace.ts,savePayload.ts(新),useSaveWorkspace.ts(新),WiWorkbench.tsx,AiDraftPanel.tsx}` | 改／新增 | F1, F7 |
| `src/frontend/src/features/import/ImportModal.tsx` | 改：欄位標籤 | F7 |
| `src/frontend/src/shared/i18n/resources/{zh-TW,en}.ts` | 改：§6 | F8 |
| `src/frontend/e2e/level-{jobs-logic,hydrate-tags,jobs-ui,jobs-golden,jobs-screenshot}.spec.ts` | 新增 | F1, F2, F9 |
| `docs/lb-integration/screenshots/level-jobs-*.png` | 新增 | F9 |
| `docs/…`（§11） | 改 | 11 |

---

## 11. 文件同步（逐條）
1. `MOST_LB_DATA_CONTRACT_SPEC.md` §8.2 末尾追記：「報告加法欄位（2026-09-12，實作書 LEVEL_SYSTEM_JOB_UX）：`errors[]／warnings[]` 各項可帶 `params`；新增 `rows[]`（每列摘要）、`hints[]`（確定性提示，種類見實作書 §7.2）、`tasks[]`（`include_tasks` 時）。CSV 與版本不變。」（§6 `divisible` 列的追記已由架構師加，不重寫。）
2. `ADR-035` D10 已由架構師追記（不重寫）。§5 落地追蹤加一列。
3. `frontend-data-flow-spec.md` §7 追記：「作業版：store 為唯一真相，作業視圖為反投影（實作書附錄 A）；`lb_tags` 與 `wi_group` 在 hydrate 還原；預覽走 dry-run 端點。」§8 表加 `LB_EXPORT_BLOCKED` 與 preview 422 對應。
4. `frontend-ux-spec.md` §8 追記規則 11：「Level System 作業版不接 LLM、不做關鍵字猜測；提示只由投影資料規則產生（實作書 §7）。」
5. `DOC_REGISTRY.md` LB 整合表：本檔一列（架構師已加）→ agent 更新狀態欄為落地 commit 範圍。
6. `fixtures/README.md`：加 `server_node_hints.expected.json` 說明。
7. `LB_PROJECTION_IMPLEMENTATION_PLAN.md` WP12 末尾一行：「後續：作業版 UI 見 LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md」。

---

## 12. 禁止事項（違反即退回）
1. 不接 LLM、不做任何敘述文字／零件名的關鍵字猜測（原型的 `conveyor|next station|work order` 與 `part==='General'` 規則**不得**出現在正式碼）。
2. 前端不得移植 `prototypes/level-jobs/engine.js`（投影邏輯只在後端）；前端只能消費 preview／report。
3. 不改 CSV 24 欄、不升 `CONTRACT_VERSION`、不改 expected CSV／黃金 fixture 讓測試變綠；黃金 hints 快照首次產出後不得為了測試改動。
4. 不改 `derive()`、`most_engine/level.py`、投影層各模組的語意；只允許 §4 列出的加法。
5. 不刪進階檢視、nb、離散層級、難度係數；作業版與進階檢視共用同一 store。
6. 不把 `t()`／`useRowNarr` 的產物存進 store（ADR-032；`useRowNarr.ts` 註解）。
7. 新元件零硬編碼中文／英文 UI 字串；`data-testid` 不算字串。
8. 不寫 `.kiro/`；`.claude/`、`.kiro/` 不 commit；不動 LB repo。
9. Spec／ADR／本檔沒說清楚的：回報「❓需 User 裁決」＋預設選項，先做可獨立的部分。

---

## 13. ❓ 待 User 裁決（不阻擋；預設值如下）
| # | 問題 | 預設 |
|---|---|---|
| 1 | 首次進入時 baseline（依 `wi_group` 自動成組、各自一排）**自動套用＋一鍵還原**，還是只顯示「整理」按鈕？ | 自動套用＋還原 |
| 2 | ~~是否新增第 9 標記 `splittable`~~ | **已裁：不做**（§3.2；ADR-023 §4） |
| 3 | 作業版為 Level tab 預設視圖，進階檢視為切換？ | 是 |
| 4 | preview 端點權限 | 同 `lb-report`（viewer+） |
| 5 | AI 草稿的作業名＝`source_text` 正規化長度上限 | 80 字 |
| 6 | Excel 未對應 `wi_group` 時是否有 fallback（例如用 `element_class`）？ | 無（留 NULL） |
| 7 | 「知道了／否」的紀錄是否持久化 | 否（session 內） |
| 8 | 模組實體化的作業名用 `name_zh`（en 使用者亦同） | `name_zh` |
| 9 | 機台時間人力歸屬 | **已裁（2026-09-12 Howard）**：事實在 MOST（`machine_unattended` 三態，未回答＝要顧→human）、政策在 LB（`unattended_machine_policy`）；§3.4／B7／F10 |

---

## 附錄 A：作業模型 ↔ Level 欄位（形式定義）

### A.1 反投影 `jobsFromStore(rows, lm, gm) → JobModel`
記 `cs(id)`＝`lm[id].countersignature` trimmed，`gm[label].{type,parent}`。
1. `topOf(id)`：`c=cs(id)`；若 `c==''` → `null`；若 `gm[c].parent` 非空且 `rowsIn(parent)` 非空 → `parent`；否則 `c`。（巢狀 cub 的成員屬於外層 sub 這條 chain，Spec §5.3）
2. 非通用列（`!lm[id].isGeneral`）：`chainKey = topOf(id) ?? 'row:'+id`。
3. 通用列：不進 chain。若 `row.wiGroup` 非空且**恰有一條** chain 的第一成員 `wiGroup` 相同 → 附掛到該作業 `generalSteps`；否則自成作業 `key='gen:'+id`（`steps=[]`, `generalSteps=[id]`）。
4. 每個 chainKey 一個 Job：`steps`＝成員依 rows 序；`first=steps[0]`。
   - `id=chainKey`；`name=rows[first].wiGroup ?? null`（顯示時 `?? rowNarr(first)`）。
   - `subLabel／cubLabel`：`gm[chainKey].type` 為 sub／cub 時＝chainKey。
   - 層：`parseLevel(lm[first].level)`；空 → `{lo: index(first)+1}`（與 derive 預設一致）。`row=lo`, `rowHi=hi>lo?hi:null`, `discrete`。
   - `sameStation = gm[chainKey]?.type==='cub'`。
   - `samePerson`：`steps` 非空且全部 `workerCub` 相同非空 `W`，且 `rowsInWcub(W) ⊆ steps`。`wcubLabel=W`。
   - `offline`：`steps` 非空且全部 `offline`。
   - `pin`：全部 `stationPin` 相同非空 → 該值；否則 `null`。
   - `stepTags[id]`（每個成員；只放與作業層級**不同**的資訊）：`cub`＝`cs(id)!==chainKey && gm[cs(id)]?.type==='cub' ? cs(id)`；`wcub`＝`!samePerson ? workerCub||undefined`；`offline`＝`!job.offline ? lm.offline||undefined`；`pin`＝`job.pin==null ? stationPin||undefined`；`segment`、`mergeLock`、`actionType`、`coefficient(≠1)` 照抄；通用列另有 `generalRole`。
5. `layers`：所有 Job 的 `row`（不含 discrete）去重排序；**顯示時**重新編號 1..k（`rowHi` 同表對映，取 `max(映射, row)`）。
6. Job 排序：同排內依 `index(first)`；整體依 (`row`, `index(first)`)。id 穩定（chainKey 不隨渲染改變）。

### A.2 動作 → store 變更（每個動作末尾 `restampLayers()`）
| 動作 | 前置 | store 變更 |
|---|---|---|
| `setLayer(job,row,rowHi?)` | — | 對 `steps ∪ generalSteps` 每列 `patchCell(id,{level: fmtLevel(row,rowHi)})`；再 `normalizeLayers` 對全部 Job 重新編號並 patch |
| `mergeUp(job)` | `row>1` | `setLayer(job, prevLayer(row))` |
| `ownRow(job)` | 同排 >1 | `setLayer(job, row+0.5)`（正規化後成獨立排） |
| `joinLayerOf(job,target)` | `job≠target` | `setLayer(job, target.row)`（捨棄 job 的 rowHi） |
| `placeBetween(job, afterLayer)` | — | `setLayer(job, afterLayer+0.5)` |
| `rename(job,name)` | `name.trim()` 非空 | `updateRows(r ∈ steps∪generalSteps → {...r, wiGroup:name})` |
| `setSameStation(job,true)` | steps ≥1 | 單列未分組：`L=createGroup('cub','')`；`moveTo(id,L)`。sub：`L=createGroup('cub','')`；依 steps 序 `moveTo(id,L)`（巢狀 cub 成員亦搬入）；`dissolveGroup` 舊 sub 與其巢狀 cub |
| `setSameStation(job,false)` | job 為 cub | steps>1：`L=createGroup('sub','')`＋逐列 `moveTo`；steps==1：`moveTo(id,'')`；`dissolveGroup(cub)` |
| `setSameStation(job,on,subset)` | job 為 sub；`subset ⊊ steps` | on：`L=createGroup('cub', subLabel)`；`moveTo(id,L)`。off：`moveTo(id, subLabel)`；空的巢狀 cub `dissolveGroup` |
| `setSamePerson(job,on,subset?)` | 目標每列 `canAssignWcub` | on：`W = job.wcubLabel ?? createWcub()`；`assignWcub(id,W)`。off：`patchCell(id,{workerCub:''})`；空 wcub 移除 meta |
| `setOffline(job,on,subset?)` | 見 F4 規則 | `patchCell(id,{offline:on})`（**不用** `toggleOffline` 的 confirm；作業版自己決定範圍） |
| `setPin(job,n\|null)` | `n≥1` | `setStationPin(id, n ?? '')` 每列 |
| `setLate(job,rowHi\|null)` | `rowHi≥row` | `setLayer(job,row,rowHi)` |
| `splitSteps(job,ids,name)` | `0<|ids|<|steps|` | `moveTo(id,'')` 每列；`|ids|>1` → `L=createGroup('sub','')`＋`moveTo`；`rename(new,name)`；`setLayer(new, job.row+0.5)`；來源剩 1 個非通用步驟且為 sub → 拆成單列（`moveTo(id,'')`＋dissolve）；剩 0 → dissolve |
| `moveStepsTo(job,target,ids)` | `target≠job` | target 單列未分組 → `L=createGroup('sub','')`＋`moveTo(target.first,L)`；`moveTo(id, target.cubLabel ?? target.subLabel)`；`updateRows(wiGroup=target.name)`；來源清理同上 |
| `reorderStep(job,id,dir)` | 鄰步在同 job | `useWiStore.setRows` 交換兩列（列序＝seq_no）；`sync()` |
| `setGeneral(id,role\|null)` | — | role：`moveTo(id,'')`；`patchCell(id,{workerCub:''})`；`isGeneral` 為 false 時 `toggleGeneral(id)`；`setGeneralRole(id,role)`。null：`toggleGeneral(id)`（變成單列作業） |
| `setSegment(ids,name)` | ids 同一 cub | `setSegment(id,name)` 每列 |
| `toggleMergeLock／setCoefficient／setActionType` | — | 既有／新增 `patchCell` |

### A.3 不變量（作業版動作後恆成立；`level-jobs-logic` 逐案斷言）
- **I-1** 同一 top-level chain 的所有成員 `level` 字串相同。
- **I-2** 所有非 discrete Job 的 `row` 為 1..k 連續整數；`rowHi≥row`。
- **I-3** 通用列 `countersignature==''` 且 `workerCub==''`。
- **I-4** `jobsFromStore(derive⁻¹(derive(state)))` 與 `jobsFromStore(state)` 相等（反投影對 derive 輸出不失真；用 fixture 轉換驗證）。
- **I-5** cub 內無 cub；wcub 成員 `canAssignWcub`。

### A.4 `proposeBaseline(rows, lm)`（2026-09-12 修訂：分「全新」與「部分」兩種）
- **候選段**：依 rows 序掃描，「連續、`wiGroup` 相同非空、皆非通用、皆未分組（`cs==''`）」的極大段，長度 ≥2。沒有任何候選段 → `null`。
- **全新（pristine）**：所有列 `cs==''`。動作：每個候選段 `createGroup('sub','')`＋`moveTo`；然後**每個 Job（含單列）依出現順序 `setLayer(job, k)`**（k 遞增，各自一排）。
- **部分（partial）**：已有任何群組（IE 在進階檢視排過、或載入舊資料）。動作：只把候選段成 sub，**不重排任何 layer**（新 sub 的 level＝其第一列現有 level），已分組的列與其 level 一律不碰。
- 回傳可還原的動作清單（還原＝`dissolveGroup` 新建的群組＋ level 回原值）。**F3 必須在 hydrate 後呼叫並套用**，通知條 `baseline.applied`＋`baseline.undo`（§5 F3、§13-1）；未套用＝缺陷（同名連續列會顯示成「名稱 (1)(2)(3)」）。

### A.5 黃金 fixture 的作業編排（`server_node_worksheet.json`，24 列 A…P，11 個作業；F2 測試的期望表）
| 作業 id（chainKey） | 名稱（wiGroup） | 排 | steps | sameStation | samePerson | offline | pin | stepTags |
|---|---|---|---|---|---|---|---|---|
| gen:A | 把機箱放上輸送帶 | 1 | — / general A | — | — | — | — | A: generalRole take_unit |
| row:B | 預備 8 顆螺絲（離線） | 1 | B | ✗ | ✗ | ✓ | — | — |
| row:C | 放主板進機箱 | 1 | C | ✗ | ✗ | ✗ | — | — |
| row:D | 掃主板序號 | 2 | D | ✗ | ✗ | ✗ | — | — |
| sub(E–H) | 裝 CPU 與 DIMM | 2 | E,F,G,H | ✗ | ✗ | ✗ | — | G,H: cub cub30 + segment dimm |
| cub40 | 鎖主板 8 顆螺絲 | 2 | I | ✓ | ✗ | ✗ | — | I: segment screw |
| sub(J1–K) | 裝 HDD | 2 | J1,J2,J3,K | ✗ | ✗ | ✗ | — | J1–J3: wcub wcub20；K: mergeLock |
| cub10 | 背板壓合 | 2 | L1,L2,L3,M | ✓ | ✗ | ✗ | — | L2: machineUnattended true；M: mergeLock |
| cub11 | I/O 擋板熱熔 | 2 | N1,N2,N3 | ✓ | ✓（wcub21） | ✗ | — | N2: machineUnattended false（握著擋板，人要顧） |
| row:O | 外觀目檢 | 3 | O | ✗ | ✗ | ✗ | — | —（fixture 的 `lb_tags.splittable` 忽略，§3.2） |
| sub(P1–P3) | ICT 測試 | 4 | P1,P2,P3 | ✗ | ✗ | ✗ | 6 | P2: machineUnattended true |
（Q1–Q3「鎖風扇支架」不在 24 列黃金內；`prototypes/level-jobs/jobs.js::example()` 有第 12 個作業供 UI 手測。）
sub 的實際 label 以 fixture 內 `countersignature` 為準（測試從 fixture 讀，不寫死）。`wiGroup` 名稱：fixture 目前無 `wi_group` 欄 → 測試以 `jobs.js::example()` 的名稱建立 store（或 agent 在 fixture 加 `wi_group`——**加欄需回報**，因 fixture 是契約驗收物；建議測試端自行注入，不動 fixture）。

---

## 附錄 B：畫面線框（ASCII）

```
┌ 工序整理  把作業排好順序、回答幾個問題，產線平衡需要的資料就準備好了。          [作業順序|產線視角] ┐
│ 待回答 2 · 要處理 0 · 可以交出      [儲存] [儲存並交給產線平衡]  □開發者   進階檢視（IE）        │
├───────────────────────────────────────────────┬───────────────────────────────────────────────┤
│ 作業順序  上下＝先後；同一排＝可以同時做（誰先都行）│ 作業內容                                      │
│ ── 放到這裡 → 最先做 ──                          │ 裝 HDD                                [改名]  │
│ ① 這 3 個作業可以同時做，誰先都行                 │ 以下設定套用到整個作業（4 步）…                │
│  ┌⠿ 把機箱放上輸送帶┐┌⠿ 預備 8 顆螺絲 ┐┌⠿ 放主板…┐ │ □ 要在同一個工站做完   有治具、機台…            │
│  │1 步·約 3.2 秒     ││1 步·約 4.0 秒  ││1 步…     │ │ ☑ 要同一個人一口氣做完 例如拿起 HDD…            │
│  │⭐通用×1           ││⏸ 離線先做      ││          │ │ □ 在離線區先做好                              │
│  └──────────────────┘└[▶ 自己一排]────┘└─────────┘ │ 固定在某一站做（未固定）              [設定]   │
│ ── 放到這裡 → 接著做 ──                          │ ▸ 進階（很少用）                              │
│ ② 這 6 個作業可以同時做…；都要等上一排全部做完     │ 步驟（照做的順序）                            │
│  ┌⠿ 掃主板序號┐┌⠿ 裝 CPU 與 DIMM┐┌⠿ 鎖主板 8 顆螺絲┐ │ □ 10 從料架拿起 HDD        👤同人   ▲▼        │
│  │…          ││4 步·約 25 秒   ││1 步·約 18 秒     │ │ □ 11 對位滑入 HDD 槽       👤同人   ▲▼        │
│  │           ││同一批人 🔧     ││🏭同一工站 同一批人│ │ □ 12 把 HDD 壓到底         👤同人   ▲▼        │
│  └[◀跟上一排一起做]┘…                             │ ☑ 13 用扭力起子鎖 HDD 螺絲 🔧拆3步 做4次 ▲▼     │
│  ┌⠿ 裝 HDD  ┐┌⠿ 背板壓合┐┌⠿ I/O 擋板熱熔┐          │ 選取的 1 步： [拆成新作業] [移到別的作業…▾]     │
│  …                                              │ 這一步是每台都做一次的通用動作？ [不是 ▾]       │
│ ── 放到這裡 → 接著做 ──                          │ ▸ 進階（很少用） □工具用完必須放回原位 □可拆…    │
│ ③ 這一排只有一個作業；都要等上一排全部做完         │                                               │
│  ┌⠿ 外觀目檢┐                                    │                                               │
│ ④ ┌⠿ ICT 測試 📍第 6 站┐                          │                                               │
├───────────────────────────────────────────────┤                                               │
│ 系統看出來的事   需要你回答的先列在前面            │                                               │
│ ？ 第 10 步、第 13 步 是拿起、使用、放回同一把工具   │                                               │
│    （torque driver）——要標成「同一工站」嗎？ [是][否]│                                               │
│ ？ 第 7 步「插 DIMM」和 第 8 步「扣 DIMM 卡榫」都做 8 │                                               │
│    次——是同一批人接著做嗎？            [是][否]     │                                               │
│ ⓘ 第 9 步 用到 electric screwdriver：系統會自動當成 │                                               │
│    「拿起 → 使用 → 放回」…              [知道了]    │                                               │
└───────────────────────────────────────────────┴───────────────────────────────────────────────┘
產線視角：
 ⭐ 線頭：把機箱放上輸送帶（每台一次）
 ① [預備 8 顆螺絲 ⏸][放主板進機箱]
 ② [掃主板序號][裝 CPU 與 DIMM][鎖主板 8 顆螺絲 🏭][裝 HDD][背板壓合 🏭][I/O 擋板熱熔 🏭👤]
 ③ [外觀目檢]
 ④ [ICT 測試 📍6]
 產線平衡會收到 34 個工作項 · 一個人從頭做到尾約 165.3 秒 · 可以交出
```

---

## 附錄 C：原型（`docs/lb-integration/prototypes/level-jobs/`）
- `index.html`／`jobs.js`／`data.js`／`engine.js`／`test_jobs.js`：2026-09-12 的可跑原型（開 `index.html` 即可）。`jobs.js::toEngineState／baseline／MSG` 是本檔 §6.3、§7、附錄 A 的來源；`engine.js` 是投影層的 JS 鏡像（對黃金逐位元相等），**只用來理解，不得移植到前端**（§12-2）。
- 原型與正式版的差異（刻意）：原型的 general 關鍵字猜測（§12-1）不做；原型的 job model 是主狀態，正式版是 store 的反投影（§2）；原型句子寫死中文，正式版走 i18n。
