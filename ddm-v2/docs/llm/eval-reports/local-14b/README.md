# 本機 14B planner 量測報告（非正式）

`scripts/wi_ai_eval.py --planner llm` 的輸出，但**模型不是設定的那一顆**。

## 為什麼分一個目錄

上層 `docs/llm/eval-reports/` 是**設定模型**（`DDM_LLM_MODEL` 預設
`qwen2.5:32b-instruct`）的正式報告區。本目錄是 **qwen2.5:14b** 的量測——
32B 在開發機上不存在（LLM 呼叫必失敗 → fallback 到結構性退化的 rule parser，
那正是 planner 段長期量不到東西的原因，見 commit b12575d）。

兩者混在同一個目錄會讓「報告的模型欄」失真：同樣叫 `wi-gold-*.json`、
同樣的 schema，讀的人無從分辨哪一份是設定模型跑的。**不要把本目錄的數字
拿去對 `docs/architecture/wi-ai-parser-system-spec.md` §14.4 的上線門檻**——
那條門檻是對設定模型講的。

## 檔名

`plan-<prompt version>[-<變體>]-<UTC timestamp>.json`

刻意不沿用 `wi-gold-<stamp>.json`：這批報告的**自變數是 prompt 版本**，
時戳排序看不出哪一版；且與上層正式報告同名會誘發誤讀。
時戳保留，對得回 `generated_at` 與 session scratchpad 的原始輸出。

| 檔名 | prompt | 備註 |
|------|--------|------|
| `plan-v1.0-pre-offset-repair-*` | plan-v1 | evidence offset 修復**之前**的基線 |
| `plan-v1.0-offset-repair-*` | plan-v1 | ＝ commit b12575d 的水準 |
| `plan-v1.1-timeout-tainted-*` | plan-v1.1 | **作廢**：21 次 ReadTimeout（timeout 過短），僅留存不作結論 |
| `plan-v1.1-*` | plan-v1.1 | 放寬 timeout 後重跑 |
| `plan-v1.2-*` | plan-v1.2 | |
| `plan-v1.3-run1-*` / `run2-*` | plan-v1.3 | 同條件兩輪，用來量變異 |

## 量測條件（全批一致）

gold n=55、`--llm-timeout-s 300`、地端 ollama、`DDM_LLM_MODEL=qwen2.5:14b`。
數字對照表與結論見 `docs/llm/wi-ai-parser-worklog.md` §8——**本目錄只放原始報告，
不重複寫結論**（兩邊各寫一份必然漂移）。

重跑方式（**兩步**：腳本產的是 `wi-gold-<stamp>.json`，本目錄的檔名是人工改的）：

```bash
cd ddm-v2
DDM_LLM_MODEL=qwen2.5:14b PYTHONPATH=src .venv/bin/python scripts/wi_ai_eval.py \
  --planner llm --llm-timeout-s 300 --out <輸出目錄>

# 腳本不會照本目錄的慣例命名——改名這一步是人工的：
mv <輸出目錄>/wi-gold-<stamp>.json docs/llm/eval-reports/local-14b/plan-<版本>-<stamp>.json
```

⚠️ 腳本另會寫一份 `wi-gold-latest.json`（同內容），本目錄不收——留著會與上層正式
報告的 `latest` 混淆。

**改名只為目錄可讀性，不再是版本歸屬的依據**：`wi-gold-report-v7`
（2026-08-22）起報告自帶 `planner_run.model_requested`／`model_served`
（後者是伺服器回報值，證據力較強）與 `planner_run.prompt_version`，
版本歸屬以**報告內容**為準。⚠️ 本目錄現存七份是 v7 之前跑的，**內容不記模型與
prompt 版本**（`grep -c qwen` 全為 0）——那七份的版本歸屬仍只有檔名與下表可依。

rule planner 的對照組（`--planner rule`）不收在這裡：它不需要 LLM、幾秒可重現，
且其基線已釘成測試常數（`PLAN_ACCURACY=5/9`、`BOUNDARY_F1=10/23`）。
