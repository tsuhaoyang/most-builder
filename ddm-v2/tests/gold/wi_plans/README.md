# WI AI Gold Plans（`wi-gold-v1`）

IE 核准（或種子）的計畫案例，供 L3+ 迴歸與 `scripts/wi_ai_eval.py` 評測。

## 檔案格式

| 欄位 | 說明 |
|------|------|
| `gold_schema_version` | 固定 `wi-gold-v1` |
| `id` | 穩定案例 ID |
| `approved_by` | `seed`（開發種子）或 IE 工號／核准紀錄 |
| `boundary` | 邊界標籤（如 `acquire_only_no_invented_steps`） |
| `plan` | `wi-plan-v1` WorkInstructionPlan（gold 輸入） |
| `synthetic_synonyms` | 評測用同義詞（unit／無 DB） |
| `expected_cycles` | 與 A5 fixture 同形：complete／TMU／tech_line… |
| `expected.action_count` / `routing_status` | 可選總體斷言 |

評測有**兩段並列**（皆不呼叫 LLM、不需 DB）：

- **compile 段**（`nlp/gold_eval.py`）：檔內 `plan` 為輸入 → linking → compiler → engine
  （TMU 權威仍為 `most_engine`），驗 compiler+engine。
- **planner 段**（`nlp/planner_eval.py`）：`source_text` 為輸入 → rule-based planner →
  與檔內 `plan` 比對，產出 `docs/architecture/wi-ai-parser-system-spec.md` §14.4 的
  plan action-count accuracy 與 boundary **span** F1（boundary 標註＝
  `plan.actions[*].evidence` 的 (start,end) span；非 `composite_unknown` 的 action
  缺 evidence 會被點名並排除於 F1 聚合；§14.4 該列的 dependency F1 未實作，
  報告恆輸出 `dependency_f1: null` 附原因）。引用 spec 請寫全檔名——
  `docs/llm/wi-ai-parser-implementation-spec.md` 的 §14.4 是別的章節。

新增 gold case 時：`plan.actions[*].evidence` 必須齊全（每筆都要有
`start`/`end`/`text`）且 offset 落在 `normalized_text` 範圍內
（`0 <= start < end <= len`）——Python slice 會 clamp，越界靠肉眼看不出來，
planner 段評測會直接報 `gold_evidence_offset_out_of_range`（缺欄位報
`gold_evidence_missing_field`），`wi_ai_eval.py` 退出碼 1。檔案層壞掉
（malformed JSON、缺 `plan`、plan 不合 `wi-plan-v1` schema）則報
`gold_case_invalid` 並以退出碼 2 區分（退出碼定義見
`docs/llm/eval-reports/README.md`）。

## 指令

```bash
# 單位測試
cd ddm-v2 && PYTHONPATH=src pytest tests/unit/test_gold_plans.py tests/unit/test_planner_eval.py -q

# 產生 versioned 報告 → docs/llm/eval-reports/
PYTHONPATH=src python scripts/wi_ai_eval.py
```

## 種子來源

初版由 `tests/integration/fixtures/e2e_plans/`（附錄 A5）複製並加 gold 中繼資料；
正式 IE 核准後將 `approved_by` 改為實際記錄，勿覆蓋已核准內容的 TMU 期望（除非引擎／rule-set 版本變更並重鎖）。
