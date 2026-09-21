# 領域索引：lb-projection — LB 投影層（motion→task、工具生命週期、匯出契約）

## 一句話
把 MOST worksheet 的 motion 確定性翻成 LB 的 24 欄 task CSV（`most-lb-csv-v1.1`）；工具生命週期拆列、數量乘數、匯出前驗證。

## 權威文件
- [`MOST_LB_DATA_CONTRACT_SPEC.md`](../lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md)（**最高原則**）
- [ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md)（決策邊界）
- [`LB_PROJECTION_IMPLEMENTATION_PLAN.md`](../lb-integration/LB_PROJECTION_IMPLEMENTATION_PLAN.md)（實作書）、[`fixtures/README.md`](../lb-integration/fixtures/README.md)（黃金驗收）

## 決策（相關 ADR）
- [ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md) — 投影層與 motion 分解（拆列、repeat_count、資料模型、過渡守衛、D10 作業版）

## 程式入口
- 路徑：`src/ddm_v2/lb_projection/**`（`project.py`、`adapter.py`、`tools.py`、`quantity.py`、`tmu.py`、`precedence.py`、`mappers.py`、`report.py`、`hints.py`、`validator.py`、`errors.py`、`models.py`）、`src/ddm_v2/services/v2/export_service.py`、`src/ddm_v2/api/routes/v2/export.py`
- graphify 錨點：`project_rows`、`build_report`、`ToolLifecycleResolver`、`decompose_engine`、`rows_from_worksheet`、`to_lb_csv`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- **輸出 CSV 24 欄（順序凍結，Spec §6）**：`task_id, action, part_id, group, atomic_group, duration, predecessors, station_name, action_type, complexity_level, adjustable, fixed_station, offline_flag, tool_id, tool_action, divisible, p2, quantity, segment, qty_scope, duration_basis, source_wi_row_id, role_type, general_role`。
- 恆空：`p2`、`complexity_level`；不輸出：`machine_count`／`manpower`（D16）；`qty_scope` 不輸出 `auto`。
- **輸入 9 個 `lb_tags`**（由 `level_entries` 存、`read_worksheet` 回、adapter 讀）：`worker_cub`、`offline`、`segment`、`station_pin`、`is_general`、`general_role`、`merge_lock`、`action_type`、`machine_unattended`（三態 null/true/false）。
- 報告加法欄位：`rows[]`、`hints[]`、`params`、`tasks[]`（`include_tasks`）；`contract_version`＝`most-lb-csv-v1.1`。
- 過渡守衛狀態：`E_TOOL_ID_SHARED_ACROSS_LOT`（維持 E，見 Spec §7.7）；SIMO 從屬列不輸出（定案）；p2／complexity 恆空（過渡）。

## 回寫（消費，反方向；ADR-036）
LB 求解結果經 `lb-most-writeback-v1` 契約回寫給 MOST（唯讀快照）。契約欄位權威在 **LB `MOST_INTEGRATION_INPUT_SPEC.md` §8**（本 repo 不重述）。
- 資料表：`lb_writeback_snapshots`（原始 payload＋政策＋applied_at/applied_rows）＋`lb_row_placements`（逐 task：source_wi_row_id/task_id/line_index/station_index/workers[]/units/offline_flag）。保留最近 10 筆/worksheet。
- 端點（`api/routes/v2/lb_writeback.py`）：`POST …/lb-writeback/fetch`（呼叫 LB）、`/import`（測試離線）、`GET …/latest`、`/snapshots`、`POST …/apply-offline`。錯誤碼 `LB_WRITEBACK_CONTRACT_MISMATCH`(422)／`LB_UNREACHABLE`(502)／`LB_AUTH_REQUIRED`(502，缺身分 header)／`LB_TIMEOUT`(504)／`LB_NOT_CONFIGURED`(503)；LB 座標不合 `LB_ID_PATTERN`、payload row 格式錯（含 `qty_scope` 值域外、`source_wi_row_id` 非 UUID）、舊快照讀不回 → `VALIDATION_ERROR`(422)，座標錯不呼叫 LB（ADR-036 D7 追記；完整表見實作書 §2 B5）。
- 聚合規則（ADR-036 D6）：同 `source_wi_row_id` → stations 集合、workers 聯集、~~units 加總~~ **件數不跨列加總**（規則見實作書 §2 B4；硬約束見 domains.yaml；~~D6「件數」一條待整合架構師修訂~~ D6 件數修訂已於 2026-09-21 落檔，見 ADR-036 §2）；`cross_station`＝多站且**非 general**（general 判定用 MOST 自己的 `is_general`，不從 payload 猜）。
- 屬性回流只有 `offline`（D2，走 MOST 組內傳染＋R1–R9，投影**收集到**的任一 E 碼整批 rollback）；其餘欄位（workers/station/units/line）唯讀；結構欄不回流（D3）。
- `apply-offline` 的降級（2026-09-21，ADR-036 D7 追記）：body 的 id 非 UUID → 422；投影**拋例外**（BL-ENG-2；逃得出來的三類）→ 仍 200、離線照常套用，`report.status=unavailable`＋E 碼，且 `errors`／`warnings` 轉 `null`（既有欄位型別變更，非加法）；留痕寫進 `applied_rows` 並由 `latest`／`snapshots` 帶出。**欄位形狀見實作書 §2 B6，本索引不重抄。**
- **真機驗證（已驗 2026-09-18；LB 修正後已複驗 2026-09-18）**：LB 直跑 `:8090`（不經 Traefik）`fetch` 全鏈可行；LB 應用本身需三個身分 header（`X-User-Id`／`X-Plant-Code`／`X-Username`），MOST client 以 `DDM_LB_AUTH_HEADERS` 帶一組 header（`X-User-Id`／`X-Username` **預設 `@me`**＝當前使用者員編，固定字串屬例外且須在 `.env` 註明理由；`X-Plant-Code` 固定值——規則見 ADR-036 §4，本索引不重抄）。第一輪 `rows=0` 成因＝LB 上傳 CSV 標準化丟欄（source_wi_row_id/role_type/general_role），**LB 端缺陷、非 MOST**，~~LB 修正中；待修後複驗 rows=34、matched 24~~ LB `c0cb244` 已修。複驗（LB 分支含 `c0cb244`＋`aac992f`；自動化端到端 `src/frontend/e2e/writeback-golden-replica.spec.ts`，`@slow`，開關 `E2E_LB_BASE_URL`＋`E2E_LB_AUTH_HEADERS`）：rows 34、matched 24／missing 0／unmatched 0，Q>1 三個 motion 件數皆 8、無不符。細節見 ADR-036 §4。
- 權威文件：[ADR-036](../decisions/ADR-036-lb-writeback-consumption.md)、[LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md](../lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md)、LB §8。

## 不變量
見 `docs/agent-team/domains.yaml` domain `lb-projection` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/unit/test_lb_projection_*.py`（golden、tmu、tools、quantity、validator、report、hints）、`tests/integration/test_export.py`、`test_export_lb_preview.py`、`test_lb_projection_adapter_equiv.py`；e2e `level-jobs-golden.spec.ts`（DoD-1）。回寫（ADR-036）的測試清單見實作書 §4。
- 缺口：投影——~~無。~~ ~~無（剛落地，文件齊備）。~~ 數類例外直接拋出、不收 E 碼（逃得出投影的是三類；`lb-report`／`lb-csv` 仍會 500）→ [BL-ENG-2](../BACKLOG.md)。回寫（ADR-036）——已知限制（件數基準是現況投影、跨線漂移偵測不到、placements 無 `qty_scope`、UI 未顯示件數警告等）＋ offline 組內傳染兩份實作 → [BL-ENG-1](../BACKLOG.md)；~~D6「件數」一條待整合架構師修訂~~（2026-09-21 已修訂）、LB §8 尚未定義 `rows[].qty_scope`：**清單與細節見實作書 §7**（本索引不重抄）。
