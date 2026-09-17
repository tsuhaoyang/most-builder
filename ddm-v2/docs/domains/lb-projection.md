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

## 不變量
見 `docs/agent-team/domains.yaml` domain `lb-projection` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/unit/test_lb_projection_*.py`（golden、tmu、tools、quantity、validator、report、hints）、`tests/integration/test_export.py`、`test_export_lb_preview.py`、`test_lb_projection_adapter_equiv.py`；e2e `level-jobs-golden.spec.ts`（DoD-1）。
- 缺口：無（剛落地，文件齊備）。
