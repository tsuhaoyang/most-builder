# 領域索引：nlp-compiler — NL→MOST 編譯器與 LLM planner

## 一句話
自然語言 → MOST cycle 的編譯（數量政策對 TMU 中性）＋受限 LLM planner；LLM 不是規則權威。

## 權威文件
- [ADR-037](../decisions/ADR-037-ai-service-integration.md)（2026-11-14 accepted：LLM 改接外部 ai_service，修訂 ADR-033 D2；**規劃中，尚未實作**，現況仍是 MOST 內的 `llm_planner`，預設關閉）
- [ADR-033](../decisions/ADR-033-llm-planner-scope-narrowing.md)（LLM planner 範圍收斂；被 ADR-037 部分修訂）
- ⚠️ `most_compiler`（policies/compile）有 ADR-033；但 **`nlp/**` 的 lexicon／linking／routing／rule_based 無單一權威規格，現況以程式為準**（見 `docs/BACKLOG.md` **BL-DOC-2**）。

## 決策（相關 ADR）
- [ADR-033](../decisions/ADR-033-llm-planner-scope-narrowing.md) — LLM planner 範圍收斂、QuantityPolicyV2（被 ADR-037 部分修訂）
- [ADR-037](../decisions/ADR-037-ai-service-integration.md) — 外部 ai_service 整合：port／adapter、逐項採用、RBAC 與外送範圍（規劃中）

## 程式入口
- 路徑：`src/ddm_v2/most_compiler/**`（`compile.py`、`policies.py`、`engine_gate.py`、`intermediate.py`）、`src/ddm_v2/nlp/**`（`lexicon.py`、`linking.py`、`routing.py`、`rule_based.py`、`normalization.py`、`quantities.py`、`llm_planner.py`、`contracts.py`…20 檔）、`src/ddm_v2/services/v2/{wi_ai_service,ai_review_service,parse_job_service,parse_job_worker}.py`、`src/ddm_v2/api/routes/v2/{nl_draft,parse_jobs,ai_review}.py`、`src/ddm_v2/models/v2/ai_ops.py`
- graphify 錨點：`compile`、`resolve_multiplier`、`QuantityPolicyV2`、`llm_planner`、`rule_based`、`engine_gate`
- `graphify explain "<anchor>"` 展開。

## 吃哪些欄位／狀態
- 編譯輸出：中繼 `PlannedAction` → CycleIn；`QuantityPolicyV2` 回 `(frequency, repeat_count, reasons)`（對 TMU 中性）。
- LLM：受限 planner（`llm_planner.py`）；`engine_gate` 擋不合法序列；`rule_based.py` 為非 LLM 路徑。
- nlp 內部（**無 spec，以程式為準**）：lexicon 來源、linking、routing（rule_based vs llm）門檻、normalization、quantities 解析。

## 不變量
見 `docs/agent-team/domains.yaml` domain `nlp-compiler` 的 `invariants`（單一權威，本索引不重抄）。

## 測試與已知缺口
- 測試：`tests/unit/test_compile*.py`、`test_engine_path*.py`、`test_english_parsing.py`、`tests/integration/test_nl_draft*.py`、`test_parse_job*.py`；`scripts/gold_eval` 類。
- **缺口（BL-DOC-2）**：`nlp/**`（lexicon/linking/routing）行為只在程式，AI 路徑無文件。補 spec 需另行排程核准。
