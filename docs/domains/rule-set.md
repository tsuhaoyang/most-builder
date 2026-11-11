# 領域索引：rule-set — Rule-set 版本治理與回放

## 一句話
TMU 計算規則為版本化資料（DB）；clone→改→發布→retired，舊 worksheet 以釘版 `rule_set_id` 回放；含 synonym 治理。

## 權威文件
- [ADR-023](../decisions/ADR-023-dictionary-governance-unification.md)（詞彙治理統一——偏 synonym／governance）
- [ADR-025](../decisions/ADR-025-import-template-matching-p2.md)（範本比對）
- ⚠️ **無單一「rule-set 生命週期」權威規格；現況以程式為準**（見 `docs/BACKLOG.md` **BL-DOC-1**，最高優先）。

## 決策（相關 ADR）
- [ADR-023](../decisions/ADR-023-dictionary-governance-unification.md) — 詞彙治理統一（含 D7b preview 安全）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/rule_set_service.py`、`rule_set_diff.py`、`rule_option_service.py`、`synonym_service.py`、`policy_service.py`、`src/ddm_v2/api/routes/v2/{rule_set,synonyms}.py`、`src/ddm_v2/models/v2/{rule_set,rule_set_tables,synonym,policy}.py`、`src/ddm_v2/schemas/v2/rule_set_options.py`、`src/ddm_v2/seed/v2/{rule_set_seed,rule_set_seed_v2,policy_seed}.py`
- graphify 錨點：`rule_set_service`、`clone_draft`、`next_version_no`、`rule_option_service`、`rule_set_diff`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- 版本狀態：draft / published / certified（`MINIMOST_FACTORY_V2`）/ retired；`version_no`（per-SKU advisory lock 配號）。
- 回放：`MostCycle.rule_set_id` 釘版（**回放鐵則**——目前只在程式，無 spec，見 BL-DOC-1）。
- synonym：正規化＋唯一性（`EN_LABEL_NOT_UNIQUE`）；retired 閘門（`RULE_SET_FROZEN`）。

## 不變量
見 `docs/agent-team/domains.yaml` domain `rule-set` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_rule_set*.py`、`test_synonym*.py`、`test_process_version_concurrency.py`。
- **缺口（BL-DOC-1，最高）**：無單一 rule-set 生命週期 spec；版本狀態機、回放語義、synonym 唯一性目前**以程式為準**。補 spec 需另行排程核准。
