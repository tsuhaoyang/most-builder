# 領域索引：wi-workbench — WI 工時表（worksheet／cycle／SIMO 配對／clone／revision）

## 一句話
實際案件的工時表編輯與持久化：wi_rows＋most_cycles（1:1）、SIMO 貢獻語義、clone／另存、樂觀鎖 revision。

## 權威文件
- [`data-model-and-storage-spec.md`](../architecture/data-model-and-storage-spec.md)
- [ADR-020](../decisions/ADR-020-simo-contribution-semantics.md)（SIMO 貢獻 0）

## 決策（相關 ADR）
- [ADR-020](../decisions/ADR-020-simo-contribution-semantics.md) — SIMO 標記列貢獻 0（對齊 v3 認證版）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/worksheet_service.py`、`worksheet_revision.py`、`process_version_service.py`、`catalog_service.py`、`cases_service.py`、`src/ddm_v2/api/routes/v2/{worksheet,cases,catalog}.py`、`src/ddm_v2/models/v2/worksheet.py`、`src/ddm_v2/schemas/v2/{worksheet,cases}.py`、`src/frontend/src/features/{wi-workbench,workbench-v3,cases,catalog}/**`
- graphify 錨點：`save_worksheet`、`read_worksheet`、`clone_worksheet`、`compute_rows_for_save`、`worksheet_revision`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- `Site→Product→SKU→ProcessVersion→MostWorksheet→WiRow`；`MostCycle` 以 per-cycle `rule_set_id` 釘版回放。
- WiRow：`sub_activity`、`key_parts`、`hand`、`frequency`、`simo_group_id`、`wi_group`（作業名，ADR-035 D10）、`object/from/to/tool_vocab_id`、`source_module_id`／`version`。
- 儲存：`compute_rows_for_save`（純函式）；`version_no` 配號 per-SKU advisory lock；revision 樂觀鎖（`WORKSHEET_REVISION_CONFLICT`）。
- 前端存檔 body：`buildSaveBody`（帶 9 lb_tags＋wi_group＋tool_vocab_id＋sub_activity＋key_parts）。

## 不變量
見 `docs/agent-team/domains.yaml` domain `wi-workbench` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_worksheet*.py`、`test_export.py`、`tests/unit/test_*simo*`、`scripts/core_logic/run_all.py`（SIMO 黃金）。
- 缺口：無單一缺口（data-model spec + ADR-020 覆蓋核心）。
