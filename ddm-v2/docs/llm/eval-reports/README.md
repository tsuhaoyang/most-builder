# WI AI Eval Reports

`scripts/wi_ai_eval.py` 輸出目錄。

規格出處一律寫**全檔名**（兩份 spec 的 §14.4/§19 是不同章節，簡寫會指錯）：
本目錄引用的 §14.4「指標與上線門檻」與 §19「分階段交付」都在
`docs/architecture/wi-ai-parser-system-spec.md`；
`docs/llm/wi-ai-parser-implementation-spec.md` 的 §14.4 是 Playwright e2e、§19 是未決事項。

- 檔名：`wi-gold-<UTC timestamp>.json`
- 最新一次亦寫 `wi-gold-latest.json`（方便 diff；可入版控）
- 本目錄以 `.gitkeep` 與 `wi-gold-latest.json` 為起點；歷史報告可選擇性 commit。

## 報告格式（`report_schema_version: wi-gold-report-v3`）

兩段並列、分開呈現：

| 區塊 | 量什麼 | 輸入 |
|------|--------|------|
| 頂層 `summary` / `cases` | **compile 段**：gold plan → SlotLinker → compile → engine_gate → routing（驗 compiler+engine） | gold 檔內 `plan` |
| `planner_eval` | **planner 段**：gold 原文 → planner → 與 gold plan 比對（驗 text→plan） | gold 檔 `source_text` |
| `gold_load_errors` | 載入層即無效的 gold 檔（`gold_case_invalid`：malformed JSON、缺 `plan`、plan schema 不合），點名檔名 | gold 檔本身 |

版本相容性：

- v1 → v2 為加法演進：新增 `report_schema_version`、`dataset_note`、
  `compile_eval_note`、`planner_eval`；頂層 `summary`/`cases`（compile 段）形狀不變。
- v2 → v3（2026-08-15）：頂層 compile 段形狀仍不變；新增 `gold_load_errors`；
  `dataset_note` 改為依 n 與 `approved_by` 動態生成。`planner_eval` 內有
  **breaking rename／語意修正**（讀 v2 報告的工具需更新）：
  - `summary.boundary` → `summary.boundary_span`（並新增 `scored_cases`、
    `trivially_empty_cases`）；
  - `summary.spec_targets.boundary_f1` → `boundary_span_f1`；
  - 新增 `summary.dependency_f1`（恆 `null`，附 `dependency_f1_note` 說明未實作原因）
    與 `summary.degenerate_planner_note`（rule planner 時點明分數退化）；
  - `cases[*].boundary_f1` → `cases[*].boundary_span_f1`，新增
    `cases[*].boundary_trivially_empty`；
  - 語意修正：兩邊皆無 span 的案例從「f1=1.0」改為「f1=null、
    `boundary_trivially_empty=true`、排除於 micro 聚合」——舊算法會讓
    「全面 abstain、不給 evidence」的 planner 拿滿分（指標獎勵棄權）。
    現行 seed gold 三筆都有 evidence，此修正**不影響**現行 micro 數字。

### planner 段指標（操作型定義）

`wi-ai-parser-system-spec.md` §14.4 只給指標名與門檻（Plan 層：action-count exact
match ≥0.95、**boundary/dependency F1** ≥0.90，即 §19 P2 退出條件），計算細節採
以下定義（同 `src/ddm_v2/nlp/planner_eval.py` docstring）：

- **action_count_accuracy**：`len(pred.actions) == len(gold.plan.actions)` 的案例比例。
- **boundary_span_f1**：以 `plan.actions[*].evidence` 的 `(start, end)` 半開區間
  （normalized_text 字元 offset）為邊界標註；嚴格 (start, end) 相等才算 TP；
  micro 聚合（總 TP/FP/FN），另附 per-case F1。`composite_unknown` 可合法無
  evidence；其他 action 缺 evidence → 該案列入 `unannotated_cases` 並排除於聚合；
  兩邊皆無 span → `trivially_empty_cases`、不給分（缺什麼在報告點名，不硬湊）。
- **dependency_f1：未實作，恆為 `null`**。§14.4 該列是「boundary/dependency F1」
  合為一項，`boundary_span_f1` 只涵蓋前半——**不得以 boundary_span_f1 ≥0.90 單獨
  宣告該列（或 P2 退出條件）達標**。未實作原因（記在報告 `dependency_f1_note`，
  不靠人記得）：action counts 不齊時 pred↔gold 的 action 對齊無定義，dependency
  端點無從對應；且 rule planner 永遠回空 dependencies（gold g02 有
  `tool_held_for`，真的算恆為 0）。

planner 段預設 `rule_based_v1`（**無 DB、無 LLM**；synonym 用 gold 檔內
`synthetic_synonyms`）。`--planner llm` 僅限手動顯式使用，CI 與預設絕不打真模型。

### 退出碼（`--help` epilog 同步此定義）

- `0` ＝ compile 段全過 **且** planner 段完整執行（n>0、gold 標註無缺損）且無載入錯誤。
- `1` ＝ **eval 跑完但發現問題**：compile 段有 FAIL，或 gold 標註缺損
  （offset 越界、slice 不符、缺 evidence…）。
- `2` ＝ **gold 輸入不可用**：任何 `gold_case_invalid` 載入錯誤（malformed JSON、
  缺 `plan`、plan schema 不合），或 n=0。有載入錯誤時其餘有效案例仍會評測並
  產出報告（見 `gold_load_errors`），但退出碼以 2 為準。

planner 分數低於 spec 門檻**不影響**退出碼（P2 門檻是上線 gate，不是本腳本成敗）；
但 planner 段量不到東西（恆空）視為失敗。

### 現況（誠實基線）

gold set 現為 **n=3、全部 seed（`approved_by=seed`）**，未達
`wi-ai-parser-system-spec.md` §19 P0 的「IE 核准至少 50 筆」前置；
分數統計上無意義，管道存在才是交付物。

`rule_based_v1` 基線（2026-08-15）：action_count_accuracy=0.6667、
boundary_span_f1(micro)=0.5714。**這兩個數字是退化的**：rule planner 恆輸出單一
action、evidence 恆為整句 `[0, len(normalized_text))`、dependencies 恆空——分數
量的是 gold 集形狀（單 action 且整句標註的案例佔比），不是 planner 的切分能力，
不得引用為 P2 進度（報告內 `degenerate_planner_note` 同此聲明）。
