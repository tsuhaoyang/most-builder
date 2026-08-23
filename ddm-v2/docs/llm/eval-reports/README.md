# WI AI Eval Reports

`scripts/wi_ai_eval.py` 輸出目錄。

規格出處一律寫**全檔名**（兩份 spec 的 §14.4/§19 是不同章節，簡寫會指錯）：
本目錄引用的 §14.4「指標與上線門檻」與 §19「分階段交付」都在
`docs/architecture/wi-ai-parser-system-spec.md`；
`docs/llm/wi-ai-parser-implementation-spec.md` 的 §14.4 是 Playwright e2e、§19 是未決事項。

- 檔名：`wi-gold-<UTC timestamp>.json`
- 最新一次亦寫 `wi-gold-latest.json`（方便 diff；可入版控）
- **降級守門**：gold_dir 含任何未核准案例（`approved_by` 空、或 `review_status`
  非 approved）時，檔名改為 `wi-draft-<stamp>.json`／`wi-draft-latest.json`，
  **拒寫** `wi-gold-*`——覆核期間不得污染官方報告（報告內 `unapproved_cases` 點名）。
- 本目錄以 `.gitkeep` 與 `wi-gold-latest.json` 為起點；歷史報告可選擇性 commit。

## 報告格式（`report_schema_version: wi-gold-report-v7`）

兩段並列、分開呈現：

| 區塊 | 量什麼 | 輸入 |
|------|--------|------|
| 頂層 `summary` / `cases` | **compile 段**：gold plan → SlotLinker → compile → engine_gate → routing（驗 compiler+engine） | gold 檔內 `plan` |
| `planner_eval` | **planner 段**：gold 原文 → planner → 與 gold plan 比對（驗 text→plan） | gold 檔 `source_text` |
| `gold_load_errors` | 載入層即無效的 gold 檔（`gold_case_invalid`：malformed JSON、缺 `plan`、plan schema 不合），點名檔名 | gold 檔本身 |
| `planner_run` | **執行來源自述**（v7）：這趟是哪個 planner／哪顆模型（請求 vs 伺服器回報）／哪一版 prompt／`--llm-timeout-s` 多少 | CLI 參數＋settings＋`plan_v1.PROMPT_VERSION`＋`LLMRawResponse.model` |

`planner_run` 的取值與邊界：

- `planner`：`rule_based_v1` / `llm`（與 `planner_eval.summary.planner` 同值）。
- `model_requested`：`--planner llm` 時＝建構 client 用的 `DDM_LLM_MODEL`（**送出去的**）；
  rule planner 為 `null`。
- `model_served`：**伺服器回報**的模型名（`LLMRawResponse.model`）——證據力較強，
  ollama 的 tag 解析（要求 `qwen2.5:14b`、實際服務 `qwen2.5:14b-instruct-q4_K_M`）、
  伺服器端別名、endpoint 被指到別顆模型時，兩者會分岔。同一個問題，
  `wi_ai_service` 用的也是這個來源（`llm_raw_response.model`），兩個子系統一致。
  ⚠️ 伺服器若沒回 `model` 欄，`llm_client` 會退回請求值——此時 served 等於
  requested 但**並非真的被證實**。
  值域：恰好一種回報值 → 該字串；**沒有任何成功呼叫**（例如全案 401/timeout）→ `null`
  （此時 `model_requested` 仍在，失敗時「送出去的是哪顆」正是要查的）；
  回報值分岐 → `null`，實況見下一欄。
- `model_served_variants`：所有出現過的伺服器回報值（排序、去重）。正常是單元素；
  分岐時列出全部——**不靜默挑一個代表**，那會讓分岐消失於無形。rule planner 為 `[]`。
  ⚠️ 以上兩個 served 欄位是**遠端可控字串**（LLM 伺服器回應的 `model` 欄，
  `llm_client` 只做 `str()`、httpx 未設 response size limit）。寫入前一律剝除
  C0/C1 控制字元並截斷至 200 字元，截過的值帶 `…[truncated from N chars]`
  （截斷留痕，不讓它看起來像完整值）。修的主要是**終端機**那個 sink——腳本的
  `print` 未經逸出，ESC 序列可以清屏、改視窗標題並覆寫先前印出的其他評測數字；
  報告 JSON 那邊 `json.dumps` 本來就會逸出 ESC，剩下的問題是長度無界。
  刻意**不用字元白名單**：合法 tag 本來就含 `:` `/` `.` `-`，未來也可能有非 ASCII，
  誤殺真值的後果是「報告說不出自己跑了哪顆模型」。
- `prompt_version`：`--planner llm` 時＝`nlp/prompts/plan_v1.PROMPT_VERSION`；rule planner 為 `null`。
- `llm_timeout_s`：`--planner llm` 時的單案 timeout（量測條件——timeout 過短會整批
  ReadTimeout，`local-14b/plan-v1.1-timeout-tainted-*` 即因此作廢）；rule planner 為 `null`。
- **刻意不記** `llm_base_url` 與 `llm_api_key`：報告要入版控，base_url 有夾帶憑證的
  可能；重現方式寫在 `local-14b/README.md` 的指令裡，不靠報告帶 endpoint。
  ⚠️ 這是**整份報告**的性質，不只本區塊：另一個入口是 `planner_eval.cases[*].planner_error`
  ——httpx 的 `HTTPStatusError` 訊息內嵌完整 request URL **連同 userinfo**
  （401/404/429/5xx 都會踩到），故例外訊息在寫入報告前一律把 URL 遮成
  `<redacted-url>`（`nlp/planner_eval._redact_urls`）。狀態碼、原因短語與 Pydantic
  的 `input_value=…` 等診斷細節照留，被換掉的只有 URL。
- `gold_dir` 記**相對於 `ddm-v2/`** 的路徑（v7 起；此前是含 OS 使用者名的本機絕對路徑）。

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
- v3 → v4（2026-08-16）：頂層 compile 段形狀仍不變；新增頂層 `unapproved_cases`
  （非空時報告檔名降級 `wi-draft-*`）。`planner_eval` 內**語意修正——自我指涉
  排除**：gold 檔標 `plan_origin=<planner>_preannotation` 且 `ie_modified` 非
  true（＝該 gold plan 就是受測 planner 的預標註輸出、IE 原樣核准）者，排除出
  Plan 層指標（`action_count_accuracy` 與 `boundary_span` 聚合的分母都不含）；
  `summary` 新增 `plan_metrics_n` 與 `self_referential_excluded`
  （count/cases/reason），`cases[*]` 新增 `plan_origin`／`ie_modified`。
  動機：橡皮圖章實驗（60 筆草稿只改身分欄位轉正）會把 accuracy 從 0.667 吹到
  0.98——那是 planner 給自己打分，不是能力。現行 seed gold 三筆無
  `plan_origin`，此修正**不影響**現行數字。
- v4 → v5（2026-08-17）：加法。planner 個案失敗改為**逐案隔離**（單案例外不再中止整批）
  → `planner_eval.cases[*]` 新增 `planner_failed`／`planner_error`／`planner_error_codes`／
  `planner_elapsed_ms`，`summary` 新增 `planner_failures`（count/rate/cases/error_codes）
  與 `planner_latency_ms`。失敗案例在 Plan 層指標中**記為漏**（不是排除），且
  **不改變退出碼**——例外是 n>0 且全案皆失敗（＝管道壞掉）時 exit 1。
- v5 → v6（2026-08-22）：加法。新增 `planner_eval.sanitize_reasons`
  （`by_code`／`by_phase`／`by_case`＋note）＝`contracts.sanitize_planner_output()`
  的 reasons（含 evidence offset 修復次數）。純觀測，不影響分數與退出碼；
  rule planner 不經 sanitize，三個統計恆為空。
- v6 → v7（2026-08-22）：加法＋兩個既有欄位的值域收斂。新增頂層 `planner_run`
  （見上表；模型記 `model_requested` 與 `model_served` **兩個**——請求值與伺服器
  回報值會分岔，後者證據力較強）——此前報告**不記自己是哪顆模型、哪一版 prompt
  跑的**，版本歸屬只能靠人工命名的檔名（`local-14b/` 那批即是事後手改名）；
  同版 `gold_dir` 由本機絕對路徑
  改為相對於 `ddm-v2/`，`planner_eval.cases[*].planner_error`／`errors` 內的 URL 改為
  `<redacted-url>`（防 endpoint 憑證隨報告入版控）。頂層 compile 段與 `planner_eval`
  的**形狀**皆不變（只有上述欄位的字串內容變）。

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

gold set 現為 **n=55（seed 3 ＋ IE 核准 52）**，已達
`wi-ai-parser-system-spec.md` §19 P0 的「IE 核准至少 50 筆」前置。

⚠️ 但 **Plan 層指標的有效樣本只有 `plan_metrics_n=9`**：其餘 46 筆是
`plan_origin=<planner>_preannotation` 且 `ie_modified≠true` 的預標註，
被**自我指涉排除**（planner 不得給自己打分，見 `nlp/planner_eval.py` 的
`SELF_REFERENTIAL_EXCLUSION_REASON`）。所以「n=55」是語料規模，不是評分樣本數。

`rule_based_v1` 基線（2026-08-22 重量）：action_count_accuracy=**0.5556**（5/9）、
boundary_span_f1(micro)=**0.4348**（10/23）。這兩個值同時是測試常數
（`PLAN_ACCURACY`／`BOUNDARY_F1`），rule 路徑有迴歸就會紅。

**這兩個數字仍然是退化的**：rule planner 恆輸出單一 action、evidence 恆為整句
`[0, len(normalized_text))`、dependencies 恆空——分數量的是 gold 集形狀（單 action
且整句標註的案例佔比），不是 planner 的切分能力，不得引用為 P2 進度
（報告內 `degenerate_planner_note` 同此聲明）。

> 前一版本節寫「n=3、全部 seed」與 2026-08-15 的 0.6667／0.5714，在 gold 擴充到 55 筆
> 之後未同步——一個叫「誠實基線」的段落自己過期了。**改動 gold set 或 rule 基線時，
> 這一節必須一起更新**；數字請取 `wi_ai_eval.py` 當次輸出，不要憑記憶抄。
>
> ⚠️ LLM planner 的分數**不在這裡**：那是 `docs/llm/wi-ai-parser-worklog.md` §8，
> 且目前只有非設定模型（qwen2.5:14b）的量測，不得對 §14.4 上線門檻。
