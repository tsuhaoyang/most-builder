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
- 端點（`api/routes/v2/lb_writeback.py`）：`POST …/lb-writeback/fetch`（呼叫 LB）、`/import`（測試離線）、`GET …/latest`、`/snapshots`、`POST …/apply-offline`。錯誤碼 `LB_WRITEBACK_CONTRACT_MISMATCH`(422)／`LB_UNREACHABLE`(502)／`LB_NOT_CONFIGURED`(503)。
- 聚合規則（ADR-036 D6）：同 `source_wi_row_id` → stations 集合、workers 聯集、units 加總；`cross_station`＝多站且**非 general**（general 判定用 MOST 自己的 `is_general`，不從 payload 猜）。
- 屬性回流只有 `offline`（D2，走 MOST 組內傳染＋R1–R9，任一 E 整批 rollback）；其餘欄位（workers/station/units/line）唯讀；結構欄不回流（D3）。
- **真機驗證（已驗 2026-09-18）**：LB 直跑 `:8090`（不經 Traefik）`fetch` 全鏈可行；LB 應用本身需三個身分 header（`X-User-Id`／`X-Plant-Code`／`X-Username`），MOST client 以 `DDM_LB_AUTH_HEADERS` 帶一組 header（值可為固定字串或 `@me`＝當前使用者員編）。當時 `rows=0` 成因＝LB 上傳 CSV 標準化丟欄（source_wi_row_id/role_type/general_role），**LB 端缺陷、非 MOST**，LB 修正中；待修後複驗 rows=34、matched 24。
- 權威文件：[ADR-036](../decisions/ADR-036-lb-writeback-consumption.md)、[LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md](../lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md)、LB §8。

## 不變量
見 `docs/agent-team/domains.yaml` domain `lb-projection` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/unit/test_lb_projection_*.py`（golden、tmu、tools、quantity、validator、report、hints）、`tests/integration/test_export.py`、`test_export_lb_preview.py`、`test_lb_projection_adapter_equiv.py`；e2e `level-jobs-golden.spec.ts`（DoD-1）。
- 缺口：無（剛落地，文件齊備）。
