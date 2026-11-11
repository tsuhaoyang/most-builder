# 領域索引：level-system — Level System（R1–R9 巢狀關係與驗證）

## 一句話
標註工序 main/sub/cub/nb 關係與變動主序，供 LB 的完整約束模型用；R1–R9 驗證權威在引擎。

## 權威文件
- [`level-system-core-logic-spec.md`](../core-logic/level-system-core-logic-spec.md)
- [ADR-028](../decisions/ADR-028-most-engine-boundary-validation-and-single-authority.md)

## 決策（相關 ADR）
- [ADR-028](../decisions/ADR-028-most-engine-boundary-validation-and-single-authority.md) — 引擎邊界與單一權威（含 level 驗證）

## 程式入口
- 路徑：`src/ddm_v2/most_engine/level.py`、`src/ddm_v2/services/v2/level_validation_service.py`、`src/ddm_v2/models/v2/level_validation.py`
- graphify 錨點：`validate`、`level_validation_service`、`LevelEntry`、`ascription`、`countersignature`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- `level_entries`：`ascription`（main/null）、`level`、`countersignature`、`parent_countersignature`、`order_in_group`、`number`／`number_count`（nb）、`coefficient`（難度係數）、`second`（GENERATED）。
- 另有 9 個 LB tag 欄（見 lb-projection 領域）——同表 `level_entries` 但語意屬 lb-projection。
- R1–R9：main 內容、sub 巢狀、cub 深度、變動層級（`~`／`/`）、順序約束。

## 不變量
見 `docs/agent-team/domains.yaml` domain `level-system` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`scripts/core_logic/level_system_validator.py`（黃金）、`tests/unit/test_level*.py`、`tests/integration/*level*`。
- 缺口：服務層（`level_validation_service`）與 R1–R9 spec 對應良好；無單一缺口。
