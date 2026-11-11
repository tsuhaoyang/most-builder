# 領域索引：most-engine — MiniMOST 序列模型與 TMU 單一權威引擎

## 一句話
七格 GM/CM motion 的 TMU 計算與敘事產生的**唯一權威**；前端不自算，值一律經 API。

## 權威文件
- [`minimost-sequence-model-core-logic-spec.md`](../core-logic/minimost-sequence-model-core-logic-spec.md)（序列模型、TMU 與合計規則、單位換算定義處）
- [`core-logic-validation-test-catalog.md`](../core-logic/core-logic-validation-test-catalog.md)（黃金向量目錄）
- [ADR-028](../decisions/ADR-028-most-engine-boundary-validation-and-single-authority.md)、[ADR-014](../decisions/ADR-014-v3-dictionary-as-value-authority.md)

## 決策（相關 ADR）
- [ADR-028](../decisions/ADR-028-most-engine-boundary-validation-and-single-authority.md) — 引擎邊界驗證與單一權威
- [ADR-014](../decisions/ADR-014-v3-dictionary-as-value-authority.md) — v3 字典為值權威

## 程式入口
- 路徑：`src/ddm_v2/most_engine/**`（`calculate.py`、`providers.py`、`rule_set_data.py`、`narrative.py`、`narrative_en.py`）、`src/ddm_v2/api/routes/v2/calculate.py`、`src/ddm_v2/schemas/v2/most.py`
- graphify 錨點：`compute_cycle`、`compute_table`、`_a_tmu`、`_m_tmu`、`build_from_seed_v2`、`resolve_multiplier`
- `graphify explain "<anchor>"` 展開；`domain_guard.py map <檔>` 確認歸屬。

## 吃哪些欄位／狀態
- 輸入：七格 slot（A0/B1/G2/A3/B4/P5/A6 或 CM 的 M3/X4/I5）、`rule_set_code`（釘版）、`frequency`、`repeat_count`、`x_seconds`。
- 輸出：`total_tmu`、`slot_tmus`（breakdown）、`tech_line`、`narrative_zh`／`narrative_en`。
- 單位：`1 TMU = 0.036 秒`（定義見 sequence spec §3）；合計不乘 10、`×system_tmu_multiplier`。
- 黃金錨點：**GM=28**（A6 B0 G6 A10 B0 P6 A0）、**CM=29**（A10 B0 G3 M16 X0 I0 A0 @45cm push）。

## 不變量
見 `docs/agent-team/domains.yaml` domain `most-engine` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`PYTHONPATH=src python scripts/core_logic/run_all.py`（黃金值）、`tests/unit/test_most_engine*.py`、`tests/unit/test_calculate*.py`。
- 缺口：無（核心邏輯 spec 齊備）。
