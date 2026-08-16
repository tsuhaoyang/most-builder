# WI AI Gold 草稿（預標註，**非 gold**）

由 `scripts/gold_harvest.py` 自動產生的**預標註草稿**：真實 WI 描述（唯讀採自 dev DB 的
`wi_rows` / `motion_module_versions.rows[]` / `motion_modules` / `motion_templates`）
跑過現行 rule pipeline 的結果，等 IE 覆核。

**這個目錄不是 gold**：

- 每筆 `approved_by: null`、`review_status: "pending_ie"`、`split: null`。
- **草稿的 `plan` 就是 rule planner 的輸出**（`plan_origin:
  "rule_based_v1_preannotation"`）——原樣核准（轉正時 `ie_modified: false`）的
  案例會被 planner 段 Plan 層指標排除（自我指涉；見
  `docs/llm/gold-review/README.md`「先讀（一）」）。
- 評測（`scripts/wi_ai_eval.py` 與 `nlp/gold_eval.py`）只掃 `tests/gold/wi_plans/*.json`
  （glob 不遞迴，本目錄是 sibling，結構上掃不到）；隔離守門測試在
  `tests/unit/test_gold_draft_isolation.py`。
- `preannotation_caveat` 是每筆的已知系統性偏差（例如
  `likely_multi_action_undercounted`：rule planner 永遠單 action，多動作句的切分
  幾乎必然低估；`take_place_pair_may_be_single_gm`：取＋放配對，GM 本來就是
  G＋P 同 cycle；`take_move_pair_may_be_single_cm`：取/觸＋推/拉配對，CM 的
  G 與 M 同 cycle——兩種配對都**不預設低估**、IE 裁決；
  `acquire_without_place`：D3-014 裁決 2「取最後一定有放」，plan 有 acquire 而
  同 plan 內其後無收尾——WARN 問「放在哪」，非 BLOCK）——**覆核時先看旗標**。
- 帶切分旗標的草稿另有 `v3_structure_hint`＋`v3_structure_evidence`
  （D3-014 裁決 3：v3 遷移資料是 IE 驗證過的，結構＝IE 的切分裁決）——
  覆核表的配對題/切分題預設依 v3 結構；**hint 是證據不是判決**，IE 可推翻。

## 格式

wi-gold-v1 相容（見 `tests/gold/wi_plans/README.md`），外加草稿欄位：

| 欄位 | 說明 |
|---|---|
| `review_status` | `pending_ie`（管線原樣；schema 測試做**整份 plan 相等**重放比對）→ `ie_edited`（IE 改過、未轉正）→ 轉正時 `approved` 並移出本目錄 |
| `plan_origin` / `ie_modified` | plan 出處（rule planner 預標註）；`ie_modified` 轉正時必填 `true|false`——自我指涉排除靠這兩欄，`plan_origin` 不可刪 |
| `split` / `split_groups` / `split_component` | 核准時才填 split；`split_groups` 是防 leakage 的分組鍵；`split_component` 是 harvest 算好的傳遞閉包分組 id（同 component 必同 split，IE 不用手推） |
| `source_provenance` | 來源表/id/欄位/DB 時間戳/原文（同句多來源全列） |
| `challenge_tags` | spec §14.3 的 16 維度；規則式判不動的標 `"unknown"`（不硬湊） |
| `heuristic_tags_unverified` | `false` 也未覆核的維度清單（quantity/tool/simo 有實證漏標）——true/false 都要確認 |
| `preannotation_caveat` | 該筆預標註的已知系統性偏差（清單） |
| `v3_structure_hint` / `v3_structure_evidence` | 僅切分旗標草稿：v3 結構回填（`single_cycle` / `multi_cycle_n` / `ambiguous`＋逐來源證據：哪個表哪筆幾列、是否 v3 遷移）。hint 是證據不是判決，絕不寫進 `expected.*` |
| `preannotation` | pipeline/planner/詞典大小/routing 理由（重現資訊；無 timestamp） |

`expected_cycles` 與 `expected` 是**現行 pipeline 的預測**（TMU 唯一出處＝`most_engine`），
不是驗證過的期望值——IE 修正 `plan` 後用
`PYTHONPATH=src python scripts/gold_harvest.py --recompile <檔案>` 重算。

## 覆核與轉正

覆核表：`docs/llm/gold-review/review-checklist.md`（每筆一節、附具體問題）。
工作流（核准→轉正→重跑 eval）：`docs/llm/gold-review/README.md`。

## Schema 守門

- `tests/unit/test_gold_draft_schema.py`：全部草稿過 wi-plan-v1 契約、evidence offset
  守衛（`0 <= start < end <= len`）、compile/planner 兩段重放自洽、**來源一致**
  （`plan.normalized_text` 必須與至少一筆 `source_provenance[].raw_text` 正規化後
  一致——換 `source_text` 塞虛構句會紅；spec §19 要的是真實案例）。
- `tests/integration/test_gold_harvest.py`：harvest 決定性（同一 DB 跑兩次 byte-identical）。
