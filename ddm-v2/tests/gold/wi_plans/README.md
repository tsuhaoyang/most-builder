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

評測路徑**不呼叫 LLM**：以檔內 `plan` 為準 → linking → compiler → engine（TMU 權威仍為 `most_engine`）。

## 指令

```bash
# 單位測試
cd ddm-v2 && PYTHONPATH=src pytest tests/unit/test_gold_plans.py -q

# 產生 versioned 報告 → docs/llm/eval-reports/
PYTHONPATH=src python scripts/wi_ai_eval.py
```

## 種子來源

初版由 `tests/integration/fixtures/e2e_plans/`（附錄 A5）複製並加 gold 中繼資料；
正式 IE 核准後將 `approved_by` 改為實際記錄，勿覆蓋已核准內容的 TMU 期望（除非引擎／rule-set 版本變更並重鎖）。
