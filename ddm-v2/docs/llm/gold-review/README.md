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
     「**判型已由動詞字典修正，請確認**」（第三輪 24 筆；第六輪起訊號源
     含 X/I，見 D3-023 節）。
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

## IE 第三輪答案與首批轉正（D3-019，2026-08-17；User/IE 親答）

1. **「拿取」→ 預設「選取」`g_pick_sel`**（G，priority 0）已登記（詞典
   15→16 條）。只登這條——small/collect 變體 IE 未授權都掛，維持候選
   （`synonym-candidates.md`）。
2. **24 筆判型修正：全部照預設（確認）**。落地：state entry 記
   `typing_confirmed_by/date`＋`typing_change_at_review`（確認當時的舊/新值＝
   stale 判定基準——新一輪判型又變即 `typing_change_changed`，不靜默沿用）。
3. **6 筆放置方向數：照預設**（single/none 如旗標）。落地：
   `p_direction_confirmed_by/date`＋`p_direction_caveat_at_review`。
4. **9 筆 TMU=0.0：照預設**——協調者解讀為「判定句子資訊不足」，記
   `zero_tmu_ruling: "distance_unstated"`（**此解讀已向 User 揭示待確認**）；
   harvest 合併時草稿記 `expected_incomplete_reason: "distance_unstated"`
   （走 D3-018 M1 空殼守門的誠實記錄路徑，不發明距離）。
5. 三筆不在首輪 41 筆內的草稿（d033/d042/d049）新增 entry **只帶判型/TMU
   面向**——切分維度 IE 未答，不冒填（它們因此仍不可轉正）。
6. **首批轉正 21 筆**（`--promote`；approved_by=IEC141289、approved_date=
   2026-08-17、split=test、`ie_modified: false` 全數維持——原樣核准對 planner
   段零證據力，Plan 層指標釘在 seed 基線 0.6667/0.5714 不動）。資格與被擋
   清單見 worklog D3-019；轉正後 state entry 標 `promoted_to`/`promoted_date`
   （軌跡保留不刪），harvest 合併跳過 promoted entry。

## IE 第四輪答案與第二批轉正（D3-021，2026-08-17；User/IE 親答）

1. **6 條同義詞登記**（同一 API，登記人 IEC141289，priority 0；詞典 16→22 條）：
   確認→`i_confirm`（範圍內）、鎖附→`x_screw_fix`（電動起子情境）、
   組至/組於/插入→`p_asm_single`（照放置邏輯，方向數逐筆確認）、
   清潔→`x_blow_clean`（**僅吹風情境**）。細節與情境條件見
   `synonym-candidates.md`；「插入」的 base＋addon 雙段計時裁決同見該檔。
2. **清潔情境守門**：同義詞映射是全域的，IE 的裁決是情境的——harvest 對
   「lexicon 配出清潔→x_blow_clean 但句面無風槍/吹風脈絡」的草稿掛
   `x_clean_context_unverified` 旗標（仿 p_direction 情境規則模式），
   **不無條件套用**；旗標無確認機制，轉正 fail-closed。本輪語料 2 筆「清潔」
   全在風槍脈絡 → 0 旗標。
3. **4 筆新旗標照預設確認**（第四輪 d015/d016/d029/d039＝句子
   a062c017/d0350279/650ee42f/0423b4e8）：判型 4 筆＋其中 2 筆 P 方向數。
4. **16 筆無爭點案例批次切分確認**：`segmentation_source:
   "no_contention_batch_confirmed"`（第三個來源值）——與逐筆確認**可區分**
   （批次未逐筆核 v3 結構證據；entry 的 hint_at_review 必須 null、不得帶
   ie_ruling；草稿長出切分旗標 ⇒ `segmentation_contention_appeared` stale）。
   16 筆全數仍卡實質內容守門（incomplete、無 TMU）——批次確認≠轉正。
5. **第五輪 harvest**：60 entry 全存活（stale 0）；草稿集換血——已轉正 21 句
   移出、21 筆新候選補位；動詞解鎖讓組至/組於/插入 7 筆轉 complete 帶 TMU
   （但判型旗標新出現、未確認）。**新出現 TMU=0.0 恰 1 筆**
   （`7f085e02`「撕除螢幕保護膜」）——**不自動套「資訊不足」**（上輪 9 筆的
   解讀仍待 User 明示確認，不擴大適用），標旗列清單、本輪不轉正、交 IE 下輪。
6. **第二批轉正 3 筆**（g27–g29；approved_by=IEC141289、2026-08-17、
   split=test、`ie_modified: false`）：a062c017→g27_pick_dimm_box_to_bench、
   650ee42f→g28_pick_board_hold、0423b4e8→g29_pick_dummy_dimm_hold_to_line
   ——即 D3-019 被擋類別「新 typed 判型/方向未確認」3 筆，本輪確認後解鎖。
   任務預期的「B 的 16 筆」全數卡實質內容（誠實統計見 worklog D3-021）；
   6 筆 multi_cycle（重切建議稿 IE 未答）維持被擋不動。累計 IE 核准
   **24/50**；planner 指標維持 0.6667/0.5714（24 筆全數自我指涉排除）。

## IE 重切裁決落地（D3-022，2026-08-17；User/IE 親答）

D3-020 重切建議稿（`resegmentation-proposals.md`）的 6 筆裁決：
**d008 照切、d016 不硬切、其餘（d001/d005/d012/d030）照建議稿**——含其中的
取捨點結論（F3 距離未述不發明、F4 acquire 單獨子句照 g01 先例、span 字面
優先於 v3 option 差異，差異一律留痕）。

1. **d008（72dc0511）→ g30**：照切 2 action（逗號 span、與 module 2 列 1:1）
   ——a1 acquire（g_pick_sel，10.0）＋a2 CM（m_remove@0cm，TMU 0.0 記
   `distance_unstated`）。**`ie_modified: true`**（IE 改過 plan＝真 ground
   truth，計入 planner 段 Plan 層指標）。
2. **d001（6fa45cdb）→ g31**、**d005（5cb719bb）→ g32**：**部分重切**——可切
   的誠實 span 切（d001＝2 段、d005＝3 段），**span 不可得的 v3 列不塞進
   plan**（該列已是獨立 gold：d001 的 rows[2]＝g21、d005 的 rows[2]＝g24），
   涵蓋對應與建模差異記進案例 notes；切分記錄以 `ie_ruling`
   （multi_cycle_2／multi_cycle_3）更正、首輪確認值保留在 `ruling_history`
   （`superseded_source: v3_structure_confirmed`）。`ie_modified: true`。
3. **d012（fe5391c6）→ g33**、**d030（fe1f3a90，留草稿）**：hint 解讀更正
   （multi_cycle_2 的結構證據指 module 而非本句；第二列是獨立句＝g10／g25）
   ——照 d026 前例走 `ruling_history` 留痕更正為 `single_cycle`，plan 不動、
   `ie_modified` 維持 false（d012 轉正後仍屬自我指涉排除）。**d030 不轉正**：
   第五輪新判型旗（null→GM）IE 未確認，資格檢查照擋（不越權）。
4. **d016（d0350279）不硬切、不轉正**：`resegmentation_ruling:
   "title_sentence_no_resegmentation"`（`ie_ruling` 欄是 single/multi_cycle
   硬 regex，語意另立欄位留痕——同 D3-019 zero_tmu_ruling 的 scope 前例）。
   本句是五步驟製程的壓縮標題（d026 型，5 列 span 全不可得），內容已由
   5 列獨立 gold 全數覆蓋（g27/g26/g18/g22/g15）；留在草稿當多動作辨識參考，
   轉正端 fail-closed（`promotion_blockers` 一律擋，mutation 守門在
   `test_gold_promotion.py`）。

**Plan 層指標的誠實變化**：`ie_modified: true` 的 g30–g32 **計入**指標——
plan_metrics_n 3→6，accuracy 0.6667→**0.3333**（2/6）、boundary span F1
0.5714→**0.2353**（4/17）。rule planner 恆單 action，對多 action gold 必然
拿 0：**分數下降是預期且誠實的**（真 ground truth 進了分母），不是迴歸；
指標若回跳基線＝ie_modified 案例被錯誤排除（釘值守門在
`test_planner_eval.py`）。累計 IE 核准 **28/50**。

## IE 第六輪答案：X/I 參與判型＋第三批轉正（D3-023，2026-08-17；User/IE 親答）

1. **X/I 參與判型（核可開票）**：X 與 I 只存在 CM 序列
   （`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2）——
   已登記的 X/I 動詞面（鎖附/清潔/確認）命中＝結構性 CM 訊號，與 M 同級；
   X/I＋G 不是混合（CM 自有 G 格，g13 型）、X/I＋P＝跨模型混合照 M+P 前例
   棄權。衝突矩陣與逐格理由：`src/ddm_v2/nlp/rule_based.py` classify_seq。
   效果：9 筆鎖附/確認/清潔草稿判型解鎖（null→CM，**新旗標未經 IE 確認
   照擋**，名單見 `harvest-summary.md`）；1 筆誠實降級——
   「拿取風槍清潔放置DIMM材料盒的DIMM」（d0350279，IE 已裁標題句）命中
   G＋X＋P 混合 → 判型棄權，原 GM complete 是誤判，其 entry 隨之 stale
   （`typing_change_changed`，待 IE 重看）。
2. **判型新旗標（含 d030）照預設確認**：第五輪的 9 筆未確認判型旗
   （7c6eb8af/b6ee694d/af172fd9/1c27dc35/fe1f3a90/e945e29e/9c1a987f 的
   null→GM＋7f085e02/2e7b2e5a 的 null→CM）全數落 state entry 判型面向
   （IEC141289，2026-08-17；7f085e02/2e7b2e5a 不在首輪 41 筆內，entry 僅帶
   判型面向、切分不冒填）。
3. **第三批轉正 7 筆（g34–g40）**：判型旗確認後解鎖的取放/取組配對 GM
   （TMU 16–24），資格檢查全套通過；**d030（fe1f3a90）→ g38 本輪過**
   （D3-022 被擋原因＝判型旗，已確認）。累計 IE 核准 **35/50**。
4. **TMU=0.0 不做一刀切**：IE 答「看狀況、逐筆判」——本輪產
   **距離裁決表** `distance-rulings.md`（11 筆：9 已轉正＋1 已裁草稿＋
   1 未裁草稿），逐筆問「補典型距離幾 cm，或維持資訊不足」，不預填答案；
   7f085e02 的 TMU=0 未裁、不轉正。

## IE 第七輪答案：三項裁決落地＋linker 掛 X/I 格（D3-024，2026-08-17；User 親答）

D3-023 快答清單第 1–3 題的答案落地（第 4 題未裁，見下節）：

1. **「鎖附」一律當電動（X/CM），無條件**——IE 確認**產線無手動鎖附**，
   D3-021 答②的「手動鎖附遇到再議」條件解除。語料 4 筆句面無電動起子
   脈絡的「鎖附螺絲」型句（bc473698/3791550c/7ff8b879/323b04c1）自此在
   裁決字面內。**不建情境旗標**（User 明選無條件裁決而非情境守門；取捨
   與風險註記——未來若出現手動鎖附工位需回頭補情境守門——記 worklog
   D3-024）。`rule_based.py` classify_seq ※1 的情境限縮註記已更新為
   無條件裁決。
2. **d0350279（標題句）stale 重看＝維持「不硬切、不轉正」**（重確認
   2026-08-17）。判型與 P 方向兩面向的依據隨判型棄權消失（旗標不再存在、
   無從「確認照預設」），依規則退場入 entry 的 `ruling_history`
   （**superseded_aspects 型條目**，D3-024 新定義：退場面向原值全文保留、
   不無痕刪除；驗證 fail-closed——切分面向不得走退場型）。entry 恢復
   可套用，已知 stale 名單清空（`test_gold_harvest_review_state.py`）。
3. **9 筆 X/I 新判型旗照預設確認**（null→CM）：b49a90ee/ee5c168e/
   51077fd1/bc473698/3791550c/7ff8b879/2f0cb396/130bb1ad/323b04c1
   ——typing 面向落 state entry（IEC141289，2026-08-17）。
4. **linker 掛 X/I 格（生產變更）**：`src/ddm_v2/nlp/linking.py`——CM 系
   action（controlled_move/process/inspect）的 X/I 面命中掛進對應格
   （x4.x_code／i5.i_code，與 G/M/P 同模式、面命中才掛不加噪音；GM 序列
   無 X/I 格不掛）。清潔情境守門語意保留：`x_clean_context_unverified`
   情境下**掛值照掛但 needs_review**（判定單一出處自 harvest 搬進
   linking.py，兩邊 import 同一份）。**完整性語意不變**：9 筆 X/I 句掛值
   後仍 incomplete `missing_core_m`——「X 承載做工時 M 可為零」是 IE 域
   判準，未裁不硬通（列下節快答）。**第四批轉正 0 筆**（誠實回報：X/I
   掛值解的是「登記映射閒置」，解不了 substance 守門——9 筆全卡
   incomplete 無 TMU；被擋 56 筆逐類見 worklog D3-024）。

## 下輪快答清單（IE 待答；D3-024 收尾）

答案落地後逐條清掉並更新對應 state entry／文件：

1. **7f085e02 的 TMU=0.0 距離裁決**（`distance-rulings.md` 唯一未裁筆；
   自 D3-023 懸至今）。
2. **「X 承載做工時 M 可為零」是否成立？**（D3-024 新題）9 筆 X/I 判型
   確認的 CM 句（鎖附/確認/清潔型）在 X/I 掛值後仍 incomplete
   `missing_core_m`——句面無移動動詞、M 格空。若 IE 裁定「X/I 承載做工
   的 CM cycle 可以 M=0（或 M 空）視為 complete」，這 9 筆才有 TMU 可談；
   未裁前完整性判準不放寬（`missing_core_m` 照擋，紅線釘在
   `test_linking.py::test_xi_mounted_cycle_still_incomplete_without_core_m`）。

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
  `--force`（D3-022 實務：重切草稿在同一輪內完成 edit → `--recompile` →
  `--promote`，轉正後 entry 標 promoted、合併跳過，不留 stale）。

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

**D3-019 起有工具路徑**：IE 各面向答案已入 `review-state.json` 且 harvest
合併後，走 `--promote`（資格檢查＝`promotion_blockers` 唯一出處；整批先驗再
動手，compile／planner 段預檢全綠才落筆；正式 gold 落檔、草稿檔移除、state
entry 標 `promoted_to`——守門在 `tests/unit/test_gold_promotion.py`）：

```bash
PYTHONPATH=src .venv/bin/python scripts/gold_harvest.py \
  --promote tests/gold/wi_plans_draft/dXXX_XXXXXXXX.json ... \
  --approved-by IEC141289 --approved-date YYYY-MM-DD --split test \
  --slugs slug_a,slug_b,...
```

轉正資格（全部滿足才轉；任一不合格＝整批拒絕）：切分已確認（state entry 的
切分面向）、確認結構與 plan 一致（multi_cycle_n 確認但 plan 未重切＝擋）、
判型/P 方向/TMU=0 等旗標全部有對應確認或裁決、cycle complete 帶 **TMU>0**
或帶 `expected_incomplete_reason`、無未解決旗標（acquire_without_place／
engine_rejected_cycle）、S 檢（provenance 一致）綠。

**D3-022 起 `ie_modified: true`（IE 重切）也走工具路徑**：宣告的唯一出處＝
state entry 的 `ie_modified`；草稿必須是 `review_status: "ie_edited"`（兩者
不一致雙向都擋——編輯過的 plan 不得以未修改身分轉正，反之亦然）；payload 的
`ie_modified` 以 entry 為準（true＝計入 Plan 層指標）。帶
`resegmentation_ruling`（標題句不硬切，d016 型）的 entry 一律擋轉正。

手動步驟（工具路徑不適用時的後備）：

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
4. 更新釘值測試：`tests/unit/_seed_gold_baseline.py`（基線釘值唯一出處；
   `test_planner_eval.py`／`test_gold_harvest_recompile.py`／
   `test_gold_promotion.py` 共用）——`SEED_GOLD_N` 是 seed 基線**不動**；
   轉正改 `PROMOTED_GOLD_N`（`GOLD_TOTAL_N` 隨算）。**分數解讀**：
   `ie_modified: false` 的案例不進 Plan 層指標——本批全數原樣核准，Plan 層
   指標必須停在 seed 基線（0.6667/0.5714）；指標若在轉正後大幅上跳，
   先檢查是不是自我指涉假象。
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
