# Gold Set 擴充 — IE 覆核工作流

目的：達成 `docs/architecture/wi-ai-parser-system-spec.md` §19 P0 退出條件
「**IE 核准至少 50 筆真實案例**」，並把 IE 的工作從「從零標 50 筆」降到
「覆核 50 筆預標註」。

本目錄檔案：

| 檔案 | 產生方式 | 內容 |
|---|---|---|
| `review-checklist.md` | `scripts/gold_harvest.py` 產生（重跑會整檔重寫） | 每筆草稿一節：原文、預測切分（evidence 以【】標示）、TMU/tech line、routing、⚠️ 旗標、**IE 覆核狀態**（review-state 合併）、IE 要回答的具體問題 |
| `harvest-summary.md` | 同上 | 來源筆數、16 維度覆蓋表（全形英數/標點分列）、覆蓋缺口、預測 action type 分佈、split 分組（傳遞閉包）、**IE 覆核狀態合併結果（含 stale 清單）**、未入選候選清單、已知系統性偏差 |
| `synonym-candidates.md` | 工程端整理（掃 60 句動詞面對照 rule-set 選項與 v3 字典） | 同義詞核可狀態：**同字直配 11 條映射已登記**（2026-08-16 IE 核可，`rule_option_synonyms`）；13 個 `?` 項維持候選待 IE 裁決（ADR-023 字典治理） |
| `README.md`（本檔） | 手寫 | 覆核工作流、覆核狀態保留機制、split 分配原則、temporal_holdout 提案 |

另有 `tests/gold/wi_plans_draft/review-state.json`（**IE 覆核狀態檔**，見下節
「覆核狀態怎麼在重產後存活」）。

草稿位置：`tests/gold/wi_plans_draft/`（**非 gold**；評測掃不到，守門在
`tests/unit/test_gold_draft_isolation.py`）。

## User/IE 三條裁決（D3-014，2026-08-16；User/IE 裁決）

1. **「取＋放」看動作**：單一 cycle 與兩個 action 都可能，**不能全域定死**，
   逐案裁決。落地：配對旗標維持中性（不預設方向），每筆的裁決答案優先用
   裁決 3 的 v3 結構回填（見下）。
2. **不變式「取最後一定有放」**：plan 裡有 acquire 而下游無收尾＝錯。落地：
   `acquire_without_place` lint（見「先讀（二）」第 4 點；WARN 標給 IE，
   非 BLOCK——單句 acquire 可能合法，「放」在下一句/下一列，如 gold g01）。
3. **v3 遷移資料是 IE 驗證過並提供的**：不只文字，**結構（module/cycle 邊界）
   就是 IE 的切分裁決**。落地：帶切分旗標的草稿逐筆回填
   `v3_structure_hint`＋`v3_structure_evidence`，配對題從開放題改成**確認題**
   （預設依 v3 結構；不同意再改）。

**Provenance 證據力定位**（裁決 3 的查證結果，2026-08-16）：

- `motion_modules`／`motion_module_versions`（keywords 帶 `v3-import`）＝
  `scripts/migrate_v3_user_data.py` 從 v3 生產 DB 搬入、**IE 驗證過並提供**的
  資料——結構語意：版本 `rows[]` 一列＝一個 cycle（`rows[*].cycle` 單一
  CycleIn）；module 名稱句對應發布版 rows 列數＝IE 把這段話切成幾個 cycle。
  **這是 hint 的唯一餵入來源。**
- `wi_rows`（本 dev DB 為 `dev_seed_30rows.py` 種入）與 `motion_templates`
  （`dev_seed_templates.py` 種入）：結構語意成立（`wi_rows` 一列＝一個 cycle
  容器，`most_cycles.wi_row_id` UNIQUE；`cycle_template`＝單一 CycleIn），
  但 **v3 搬遷不寫這兩個表**——非 IE 驗證的 v3 資料，**不餵 hint**（證據
  條目標 `v3_migrated: false`）。
- 誠實邊界：**hint 是證據不是判決**——欄位名就叫 hint，覆核表明寫「預設依
  v3 結構，IE 可推翻」；hint 絕不寫進 `expected.*`（守門在
  `tests/unit/test_gold_draft_schema.py`）。

## 先讀（一）：草稿的 plan 就是 rule planner 的輸出——自我指涉警告

每筆草稿標 `plan_origin: "rule_based_v1_preannotation"`：**草稿的 `plan` 不是
獨立標註，是 rule planner 自己的輸出**。因此：

- 轉正時**必填 `ie_modified: true|false`**——`true`＝IE 改過 plan 內容（真實
  ground truth）；`false`＝IE 覆核後原樣核准（同意 planner 的輸出，但對
  planner 指標**零證據力**）。
- planner 段評測（`nlp/planner_eval.py`）會把「`plan_origin` 為受測 planner
  且 `ie_modified` 非 true」的案例**排除出 Plan 層指標**（action-count
  accuracy、boundary span F1），排除名單與理由寫在報告的
  `self_referential_excluded`。compile 段（TMU/engine 重放）不受影響。
- **轉正後 Plan 層指標若往 1.0 跳，那是自我指涉假象**（planner 給自己打分），
  不是能力提升——橡皮圖章實驗（60 筆草稿只改身分欄位轉正）實測會把
  accuracy 從 0.667 吹到 0.98，排除邏輯就是為了殺掉這件事；守門在
  `tests/unit/test_planner_eval.py::test_rubber_stamp_promotion_does_not_move_plan_metrics`。

## 先讀（二）：預標註的已知系統性偏差

這些偏差**逐筆寫在草稿的 `preannotation_caveat`**，不是只寫在這裡：

1. `likely_multi_action_undercounted` — 現行 rule planner 結構上**永遠只出 1 個
   action、evidence=整句**。多動作句（≥3 動詞、或含順序連接詞）的預測切分
   幾乎必然低估。覆核這類草稿時，請把「預測 action 數=1」當作未標註，逐動詞重切。
   動詞偵測已排除**名詞內幽靈命中**（「DIMM壓合治具」的「壓合」不再算動詞——
   先前 8 筆因此誤掛本旗標）。**D3-014 降級例外**：該筆若有
   `v3_structure_hint: single_cycle`（v3 結構顯示 IE 當初建為單一 cycle，
   本輪 22 筆中 17 筆），「幾乎必然低估」對該筆**降級**——預設依 v3 結構，
   除非 IE 認定 v3 切分本身有誤（覆核表逐筆標示降級版警語）。
2. `take_place_pair_may_be_single_gm` — 恰好「取＋放」兩動詞且無連接詞的句子
   **不算 multi_action**：MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單
   action 不必然是低估。請用該筆覆核表的「取放建模」題裁決：建成**單一 GM
   cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**——中性
   旗標，不預設方向（先前把配對也標成「必然低估」會系統性推向過度切分；
   本輪 16 筆）。**D3-014**：有 v3 結構答案的（16 筆中 15 筆），「取放建模」
   題已改成**確認題**（預設依 v3 結構）；矛盾者（1 筆）維持開放題並列證據。
3. `take_move_pair_may_be_single_cm` — 恰好「取/觸＋推/拉」兩動詞且無連接詞
   （如「接觸…推至/拉至」）同理：CM 序列的 G 與 M 本來就在同一 cycle
   （`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：
   A B G M X I A）。請用該筆的「取移建模」題裁決：建成**單一 CM cycle**
   （G 與 M 各取值）還是 acquire＋controlled_move **兩個 action**——中性旗標，
   不預設方向（本輪 3 筆，v3 結構全部顯示單一 cycle → 皆為確認題）。覆核表
   的配對題與旗標**共用同一判定函式**（`take_place_pair`／`take_move_pair`），
   不會再出現「掛必然低估又問要不要建單一 GM」的自相矛盾節。
4. `acquire_without_place` — D3-014 裁決 2「取最後一定有放」：plan 含 acquire
   而其後**同 plan 內**無任何收尾 action（move_place／release_return／
   controlled_move——CM 無 P 參數，M 即閉合，且裁決 1 明言 acquire＋
   controlled_move 是合法建模）。覆核表醒目提問：**這句的「放」在哪？被截斷
   了還是描述缺漏？** WARN 不 BLOCK：只在同 plan 內判——單句 acquire 可能
   合法（「放」在下一句/下一列，如 g01「拿起DIMM」不發明後續步驟）。判定用
   plan 的 action_type 序列，**不用文字啟發式**（R1 教訓：動詞面會被名詞
   擊穿）。本輪 60 筆 0 命中——**結構使然，非 lint 失效**：rule planner 的
   adapter 只產 move_place／controlled_move／composite_unknown，永遠不出
   acquire；lint 的作用點是 IE 改完 plan 之後（`--recompile` 會同步本旗標）。
5. `empty_lexicon_no_slot_candidates` — **第二輪起本旗標已消失**（2026-08-16
   IE 核可 11 條同字直配同義詞後字典非空）。第二輪誠實記錄（歷史）：cycle
   完成度 0/60——當時 GM/CM 判型只認名詞觸發詞、不吃詞典。**第三輪
   （D3-017）判型已吃字典**：typed 10→29 筆（GM 13＋CM 16）、complete 帶 TMU
   0→27 筆（其中 9 筆 TMU=0.0——距離未述＝0cm＋非核心 slot 未掛，
   complete≠可信 TMU，見 `harvest-summary.md`「誠實旗標」）；判型仍未定的
   31 筆卡點逐類見 `harvest-summary.md`「第三輪判型」節（27 筆卡未登記
   `?` 動詞、1 筆跨模型混合棄權、1 筆單動詞不足、2 筆無動詞面）。
   剩餘 11 個 `?` 動詞面維持候選待 IE 裁決：`synonym-candidates.md`。
5b. **第三輪新旗標（D3-017）**：
   - `typing_changed_by_verb_lexicon` — 本筆判型與「僅名詞」舊行為不同
     （草稿 `typing_change` 欄存舊/新值），覆核表標
     「**第三輪判型已修正，請確認**」（本輪 24 筆）。
   - `p_direction_single_default`／`p_direction_none_by_context`／
     `p_direction_unclassified_default_single` — 「放至/放置」的方向數已依
     IE 情境規則預選（機構件→`p_place_single` 一種方向、盤面→`p_place_none`
     無方向、判不出→預設 single 交 IE）；**每筆覆核表都問「方向數預設一種，
     不對請改」**。名詞分類清單單一出處＝`src/ddm_v2/nlp/linking.py`
     （逐項附語料證據；生產 nl-draft、gold_eval 重放、harvest 同一套）。
6. `engine_rejected_cycle` — 引擎拒絕的 complete cycle。期望端寫的是
   `expected_engine_rejected: true`（重放驗「引擎仍拒絕」，草稿不會產出即紅）；
   但**轉正前必須修正 cycle 值**——原樣轉正沒有 TMU，會撞空殼守門
   （除非顯式寫 `expected_incomplete_reason`）。
7. `challenge_tags` 的 9 個可判維度：**`false` 也是啟發式輸出，不是「已確認
   沒有」**——`heuristic_tags_unverified` 點名的 `quantity`／`tool_handling`／
   `simo_both_hands` 已有實證漏標（如「電動鎖附(多顆)」無數字，quantity 誤標
   false）。覆核時 true/false 請一併確認，不要只看 true 的。

**v3 結構回填統計（本輪）**：19 筆配對旗標中 **18 筆**拿到結構答案
（GM：13 single＋2 multi_cycle_2；CM：3 single）、**1 筆 ambiguous**
（d026「雙手抓握主板組至機箱」——同句同時是 3 列 wi-template 名稱與單列
action module，conflicting）；22 筆 likely_multi 中 **21 筆**拿到結構答案
（17 single→警語降級、4 multi_cycle_n）、**1 筆 ambiguous**（d045「拿取排線
並對準接頭」——唯一來源是 dev seed 的 wi_rows，no_v3_structure_signal）。
逐筆明細見 `harvest-summary.md`「v3 結構回填」節。

## IE 首輪覆核結果（D3-015，2026-08-16；User/IE 親答）

1. **39 筆確認題：全部照 v3 結構預設，OK**。落地：`review-state.json` 逐筆記
   `segmentation_confirmed_by: "IEC141289"`＋日期＋
   `segmentation_source: "v3_structure_confirmed"`，harvest 合併回草稿的
   `ie_review` 區塊。**這是切分維度的確認，不是整筆 gold 核准**——cycle 仍
   incomplete（首輪時詞典為空；第二輪登記 11 條後仍 0/60 complete，
   見「先讀（二）」第 5 點），option code 覆核與轉正另有流程；`ie_modified`
   維持 `false`（確認≠修改，依自我指涉設計不計 planner 段證據力）。
2. **d045「拿取排線並對準接頭」＝1 列**（ambiguous → 裁決）。
   `ie_ruling: "single_cycle"`；plan 已是 1 action，內容不動。
3. **d026「雙手抓握主板組至機箱」＝3 列**（ambiguous → 裁決：v3 兩個矛盾結構
   中，3 列 wi-template 是對的；單列 action module 為 IE 裁決否定的結構，
   證據保留並標 `ie_ruling_rejected`）。**plan 未重切（誠實降級）**：查證該
   wi-template v1 的 3 列子句＝「雙手接觸DIMM壓合治具拉至規定位置」／
   「雙手抓握主板保持住至流水線」／「雙手抓握主板組至機箱」——三列是各自
   獨立的完整子句，**不是原句的子字串**，原句切不出 3 段誠實的 evidence
   span（不編造）。記 `ie_ruling: "multi_cycle_3"`＋
   `plan_pending_resegmentation: true`，plan 重切等第二輪（需子句對應）。

   **⚠️ 第二輪更正（2026-08-16 釐清並獲 User 確認）：d026 這句本身＝1 列**。
   首輪「3 列」的答案是對**整個三步驟製程（那個 wi-template）**說的——提問時
   把範本結構誤述為句子切分。更正落地：`ie_ruling: "single_cycle"`、
   `plan_pending_resegmentation` 清除（單 cycle 沒有「等重切」，plan 本來就是
   1 action、內容不動、`ie_modified` 維持 false）；被否定的結構改為
   「wi-template 名稱句對應 3 列＝本句切 3 個 cycle」的推論
   （`motion_modules/dcbb30a8` 的 name_zh 來源標 `ie_ruling_rejected`；範本
   名稱是製程標題，其 3 列是各自獨立子句，本句自己就是其中 rows[2] 一列＝
   一個 cycle）；首輪對單列 action module 的否定隨更正撤回。**更正軌跡保留**
   在 state entry 的 `ruling_history`（先前答案全文＋為何更正）——標準答案集
   的更正不是無痕覆寫。

## 覆核狀態怎麼在重產後存活（D3-015）

問題：`--force` 整批重寫草稿檔，覆核記錄若寫在草稿上會被第二輪
（同義詞登記後必然重跑）洗掉。

機制：覆核狀態放**獨立檔** `tests/gold/wi_plans_draft/review-state.json`
（**IE 的檔案：harvest 只讀不寫、`--force` 不刪**），以 normalized_text 的
sha256 前 8 碼（草稿檔名後綴）為鍵；harvest 重產時逐筆合併回對應草稿的
`ie_review` 區塊。編號位移（d026→d031）不影響配對——鍵跟著句子走。

**stale 不靜默套用**（逐條列入 `harvest-summary.md`）：

- 句子文字變了 ⇒ sha 變 ⇒ 配不到（`no_matching_draft`）；
- v3 結構 hint 變了 ⇒ 當初確認/裁決所依據的證據已不同
  （`v3_structure_hint_changed`）；
- entry 記 `ie_modified: true` ⇒ 本機制只保覆核詮釋資料、保不了 plan 內容
  （`ie_modified_plan_not_preservable`）——要保 plan 編輯就不要對該目錄
  `--force`。

守門：`tests/unit/test_gold_harvest_review_state.py`（合併/stale/驗證的
mutation 逐條）＋`tests/unit/test_gold_draft_schema.py` 5d（草稿 `ie_review`
的唯一出處＝state 檔，兩邊漂移即紅）＋
`tests/integration/test_gold_harvest.py`（--force 存活演練＋決定性）。

## 覆核一筆草稿的步驟

1. 開 `review-checklist.md` 對應小節，逐題回答（切分、判型、option code、
   數量/工具/SIMO、routing）。
2. 直接編輯草稿 JSON（`tests/gold/wi_plans_draft/dXXX_XXXXXXXX.json`）。
   **動手改的第一步：把 `review_status` 從 `"pending_ie"` 改成 `"ie_edited"`**
   （`tests/unit/test_gold_draft_schema.py` 對 pending_ie 草稿做**整份 plan
   相等比對**——改 action_type、換句子、動 evidence 而不改狀態都會紅）。然後：
   - 修 `plan.actions`：正確的 action 數、`action_type`、`sequence_order`、
     `roles`（含 evidence 內的原文子字串）、每個 action 的 `evidence`
     （`start`/`end`/`text`，對 `normalized_text` 的半開區間，
     `0 <= start < end <= len`——planner 段評測會擋越界）。
   - 需要時補 `dependencies`（如 `tool_held_for`）與 `unresolved`。
   - slot 的 option code 走 `synthetic_synonyms`：把「動詞→option code」映射
     加進該筆的 `synthetic_synonyms`（這讓 gold 檔自足、eval 不依賴 DB）。
     同時建議把同一條登記進 DB 字典（見上）。
3. 用單一引擎重算期望值（**不得手算 TMU**）：

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py \
     --recompile tests/gold/wi_plans_draft/dXXX_XXXXXXXX.json
   ```

   這會以檔內 `plan` + `synthetic_synonyms` 重跑 linking → compile →
   `most_engine` → routing，重寫 `expected_cycles` 與 `expected`。
   檢視結果：TMU/tech line 是否符合 IE 判斷；不符就回到步驟 2。

## 核准→轉正（草稿 → 正式 gold）

1. 草稿 JSON 填上：
   - `approved_by`: IE 工號（如 `IEC141289`）；
   - `review_status`: `"approved"`；
   - `ie_modified`: **必填** `true|false`——`true`＝改過 plan 內容；`false`＝
     原樣核准（該筆會被 planner 段 Plan 層指標排除，見「先讀（一）」）。
     `plan_origin` **保留不可刪**（IE 從零手寫的新案例填 `"ie_manual"`）；
   - `split`: 四選一（原則見下）；`split_groups` 與 `split_component` 保留
     （防 leakage 的稽核憑據；`split_component` 是 harvest 算好的傳遞閉包分組）。
2. 實質門檻（`tests/unit/test_gold_draft_isolation.py` 的 tripwire）：非 seed
   案例必須**至少一個 `complete: true` 帶 `total_tmu` 的 cycle**，或顯式
   `expected_incomplete_reason`（資訊不足可以誠實記錄，但要寫出來）——
   空殼填個名字不算核准。**`approved_by` 填 `"seed"` 沒有用**：seed 豁免釘在
   `SEED_GOLD_IDS` 白名單（`src/ddm_v2/nlp/gold_eval.py` 的 3 個 A5 種子檔），
   非白名單的 seed 視同未核准且 tripwire 必紅。
   另：`source_provenance` **不可改**——schema 守門要求 `plan.normalized_text`
   與至少一筆 `raw_text` 正規化後一致（真實案例守門，換句即紅）。
3. 檔案**移入** `tests/gold/wi_plans/`，依既有慣例改名與改 `id`
   （下一個流水號＋語意 slug，如 `g06_dimm_press_fixture.json` / `id: "g06_dimm_press_fixture"`）。
   保留 `source_provenance` 與草稿 id 供追溯（可放 `notes`）。
4. 更新釘值測試：`tests/unit/_seed_gold_baseline.py` 的 `SEED_GOLD_N`（基線釘值
   唯一出處；`test_planner_eval.py` 與 `test_gold_harvest_recompile.py` 共用）
   與對應分數釘值。**分數解讀**：`ie_modified: false` 的案例不進
   Plan 層指標；指標若在轉正後大幅上跳，先檢查是不是自我指涉假象。
5. 重跑驗證，全綠才算轉正完成：

   ```bash
   PYTHONPATH=src pytest tests/unit/test_gold_plans.py tests/unit/test_planner_eval.py \
     tests/unit/test_gold_draft_schema.py tests/unit/test_gold_draft_isolation.py -q
   PYTHONPATH=src .venv/bin/python scripts/wi_ai_eval.py   # 退出碼 0
   ```

6. 已核准的 gold 不可覆蓋（`tests/gold/wi_plans/README.md` 的規則）。
   `--recompile` 對 `tests/gold/wi_plans/` 的檔案**預設拒絕**——引擎或 rule-set
   版本變更需重鎖 TMU 時，顯式走：

   ```bash
   PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py \
     --recompile tests/gold/wi_plans/gXX_*.json \
     --relock-approved --reason "為什麼要重鎖（如 rule-set v2→v3）"
   ```

   reason 會寫進檔案 `notes` 留痕，並在 commit 訊息記錄。「引擎改壞 → gold 紅
   → recompile → 綠」不准零摩擦（No error bypass）。

## Split 分配原則（spec §14.2）

四種 split：`train` / `calibration` / `test` / `temporal_holdout`。

硬規則：

- **同 `split_component` 必同 split**——同一句的改寫、同一 motion module 衍生樣本
  不得跨 split（防 leakage）。草稿的 `split_groups` 是原始分組鍵
  （`module:<id>` / `worksheet:<id>` / `template:<id>`），`split_component` 是
  harvest 用傳遞閉包算好的連通分量 id（同句多來源、跨鍵串連都已合併）——
  **IE 直接看 `split_component` 分組即可，不用手推閉包**；多筆同組清單見
  `harvest-summary.md` 的「Split 分組」節。
- `test` 只收 IE 核准案例、不可用於調參；`calibration` 與 `train` 不可混用。

P0 階段建議（**先讀取樣性質**）：

- 本輪 harvest 是 **coverage-optimized 取樣**（greedy max-coverage 對挑戰維度
  過採樣），**不是分佈代表性樣本**——在這批案例上量到的分數只反映「困難維度
  覆蓋下的表現」，**不可外推**為生產分佈的表現；要分佈代表性指標，需另抽
  隨機樣本（未入選的候選清單在 `harvest-summary.md`，可作為隨機補抽的池）。
- 本輪 IE 核准的案例作為 **P0 退出條件的 50 筆集合**；因上一條，這批案例
  即使放進 `test`，也必須在報告裡明示「challenge-oversampled test set」，
  不得當作母體表現的 test 分數引用。
- `train` / `calibration` 留給後續合成改寫與更大量匯入資料——目前 unique 真實
  描述不足以三分，硬切會讓每個 split 都太小。**不要為了湊 split 而複製案例**。

## temporal_holdout 提案（查證後的結論）

**現有資料無法用 DB 時間戳定義 temporal split**：查證 dev DB——

- v3 遷移資料（`motion_modules` / `motion_module_versions`）的 `created_at` /
  `published_at` 全部是**遷移執行當天**（2026-08-04 同一分鐘內），原始著作時間
  未帶入 v2；
- `wi_rows` 30 筆是 `dev_seed_30rows.py` 的種子（2026-08-11 同批）。

用這些時間戳切 temporal_holdout 只是在量「哪次批次匯入」，不是資料漂移。因此提案：

1. **前向定義**：以「P0 gold 凍結日」為 cutoff；cutoff 之後由使用者在 DDM 實際
   新增的 WI 描述（`wi_rows.created_at > cutoff` 且 `provenance='manual'`，或
   之後的 Excel 匯入批次）才進 `temporal_holdout`。現有 harvest 的案例一律不進。
2. （備選）若需要歷史 temporal split，得回 `ddm-v3/apps/api/minimost.db` 讀原始
   `created_at`（唯讀）再對映——本輪**未做**：v3 DB 是保護資產，且 P0 不需要。

## 覆蓋缺口（誠實清單）

見 `harvest-summary.md` 的「覆蓋缺口」節——重點：真實資料裡**沒有**純英文
（`english_only` 0 筆）、也沒有可規則式判定的錯字/同音/語序顛倒/口語/缺資訊/
歧義/髒資料案例（這 7 維規則式判不動，每筆標 `unknown`）。全形字元已細分
**英數／標點**分開統計——現有命中全是全形標點（逗號），**全形英數（ＡＢＣ／０１２）
視為未覆蓋**，不要被合計數字誤導。這些維度需要 IE：

- 覆核時順手把命中的維度從 `unknown` 改成 `true`/`false`（真實資料裡可能本來就有
  口語或缺資訊案例，只是程式判不出來）；
- 缺的維度（尤其純英文、極端長句、髒資料）**補寫合成案例或提供真實工單**，
  不由工程端生成假案例硬湊。
