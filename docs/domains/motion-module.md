# 領域索引：motion-module — 動作範本庫與 WI 大綱（motion_module／template matching／wi-set）

## 一句話
常用 cycle 範本與 WI 大綱組織（WI⊃motion 兩層）；實體化搬進案件、範本比對加速建表。

## 權威文件
- [ADR-025](../decisions/ADR-025-import-template-matching-p2.md)（匯入範本比對）
- ⚠️ **motion_module／wi-set／wi-context 無專屬權威規格，現況以程式為準**（見 `docs/BACKLOG.md` **BL-DOC-3**）。
- 兩層結構背景：steering `wi-motion-core-structure.md`（WI＝一句語句⊃多個 motion）。

## 決策（相關 ADR）
- [ADR-025](../decisions/ADR-025-import-template-matching-p2.md) — 匯入範本比對 P2
- [ADR-017](../decisions/ADR-017-motion-modules-library.md) — 動作範本庫（proposed）

## 程式入口
- 路徑：`src/ddm_v2/services/v2/{motion_module_service,template_matching,wi_set_service,wi_context_service}.py`、`src/ddm_v2/api/routes/v2/{motion_module,motion_template,wi_set,wi_context,vocab}.py`、`src/ddm_v2/models/v2/{motion_module,motion_template,wi_set,wi_context,vocab}.py`、`src/ddm_v2/schemas/v2/{motion_module,motion_template,wi_set,wi_context,vocab}.py`、`src/frontend/src/features/{wi-project,master-data}/**`
- graphify 錨點：`motion_module_service`、`instantiate`、`template_matching`、`MotionModule`、`wi-template`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- `motion_module`：`category`（`wi-template`／`action`）、`rows[]`（動作快照複本）、版本／`current_version`、`total_tmu`。
- 實體化（from-module）：帶 `wi_group = module.name_zh`；`source_module_id`／`version` 回填 WiRow。
- vocab：object／component／tool／from／to，含 `name_zh`／`name_en`。

## 不變量
見 `docs/agent-team/domains.yaml` domain `motion-module` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/integration/test_motion_module*.py`、`test_motion_module_materialize_wi_group.py`、`test_wi_set.py`、`tests/unit/test_template_matching*`。
- **缺口（BL-DOC-3）**：WI 大綱／實體化／reorder 語義無專屬 spec，以程式為準。補 spec 需另行排程核准。
