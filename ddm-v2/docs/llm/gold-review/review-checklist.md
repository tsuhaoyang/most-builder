# IE 覆核表 — gold set 擴充預標註草稿

<!-- 本檔由 scripts/gold_harvest.py 產生；重跑 harvest 會整檔重寫，IE 批註請寫在草稿 JSON 或另開檔案 -->

草稿位置：`tests/gold/wi_plans_draft/`。**這些不是 gold**（`approved_by: null`、`review_status: pending_ie`），評測不會撿到。核准／轉正流程見 `docs/llm/gold-review/README.md`。

**先讀這個——預標註的系統性偏差**：現行 rule planner 對任何輸入都只會產生**1 個 action、evidence=整句**。所以「預測 action 數=1」不是模型判斷，是結構限制；帶 `likely_multi_action_undercounted` 的每一筆都請假設切分是錯的，逐動詞重切。帶 `take_place_pair_may_be_single_gm` 的是「取＋放」配對——GM 本來就是 G＋P 同 cycle，**不預設低估**，請用該筆的「取放建模」題裁決單一 GM 或兩個 action。帶 `take_move_pair_may_be_single_cm` 的是「取/觸＋推/拉」配對——CM 的 G 與 M 同一 cycle，同樣**不預設低估**，請用該筆的「取移建模」題裁決單一 CM 或兩個 action。另外：`challenge_tags` 裡 9 個可判維度的 `false` 也是啟發式輸出（`heuristic_tags_unverified` 點名的維度已有實證漏標），true/false 請一併確認。

共 60 筆，其中 60 筆帶 ⚠️ 旗標。

---

## d001_6fa45cdb

**原文**：確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)
**正規化**：確認dimm點位,並按壓dimm壓合治具的把手 (依據配置要求-16個dimm)
**來源**：`motion_modules/d630108e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：全形字元、中英混合、多 action、數量、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【確認dimm點位,並按壓dimm壓合治具的把手 (依據配置要求-16個dimm)】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d002_6017ab5e

**原文**：雙手抓握主板放至DIMM壓合治具
**正規化**：雙手抓握主機板放至dimm壓合治具
**來源**：`motion_module_versions/62d5bebb…`（rows[0].sub_activity）; `motion_module_versions/89add432…`（rows[0].sub_activity）; `motion_modules/310981d5…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、工具持有、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手抓握主機板放至dimm壓合治具】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d003_0acd56df

**原文**：雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置
**正規化**：雙手接觸×16dimm卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置
**來源**：`motion_module_versions/6e6f8d3d…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：中英混合、多 action、數量、SIMO／雙手
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手接觸×16dimm卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d004_7c6eb8af

**原文**：雙手從DIMM材料盒拿取×16DIMM插入×16至主板
**正規化**：雙手從dimm材料盒拿取×16dimm插入×16至主機板
**來源**：`motion_module_versions/255beb05…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、數量、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手從dimm材料盒拿取×16dimm插入×16至主機板】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d005_5cb719bb

**原文**：拿取主板，去除包裝袋，將主板放置工作台
**正規化**：拿取主機板,去除包裝袋,將主機板放置工作臺
**來源**：`motion_modules/8436a0d0…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、全形字元、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取主機板,去除包裝袋,將主機板放置工作臺】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d006_b49a90ee

**原文**：雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位
**正規化**：雙手接觸dimm卡槽的左右卡扣推×16至規定位置並確認到位
**來源**：`motion_module_versions/2b40d576…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：中英混合、多 action、數量、SIMO／雙手
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手接觸dimm卡槽的左右卡扣推×16至規定位置並確認到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d007_3ba13f82

**原文**：右手抓握电动起子保持住至機箱
**正規化**：右手抓握電動起子保持住至機箱
**來源**：`motion_module_versions/9569aeaf…`（rows[1].sub_activity）; `motion_module_versions/b66a74ed…`（rows[0].sub_activity）; `motion_modules/2ea27e92…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手抓握電動起子保持住至機箱】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d008_72dc0511

**原文**：從料架上拿取假DIMM，去除其包裝袋
**正規化**：從料架上拿取假dimm,去除其包裝袋
**來源**：`motion_modules/d9203ed2…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：全形字元、中英混合、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【從料架上拿取假dimm,去除其包裝袋】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d009_ee5c168e

**原文**：電動起子鎖附 CPU 散熱片螺絲 x4
**正規化**：電動起子鎖附 cpu 散熱片螺絲 x4
**來源**：`wi_rows/30e06fae…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量、工具持有
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【電動起子鎖附 cpu 散熱片螺絲 x4】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d010_30d9b858

**原文**：雙手抓握主板保持住至流水線
**正規化**：雙手抓握主機板保持住至流水線
**來源**：`motion_module_versions/55e93ed7…`（rows[0].sub_activity）; `motion_module_versions/b91e9fca…`（rows[1].sub_activity）; `motion_modules/ea8ebe0c…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、多 action、SIMO／雙手
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手抓握主機板保持住至流水線】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d011_7e40706c

**原文**：雙手接觸DIMM壓合治具推至規定位置
**正規化**：雙手接觸dimm壓合治具推至規定位置
**來源**：`motion_module_versions/62d5bebb…`（rows[1].sub_activity）; `motion_module_versions/b7eefdb5…`（rows[0].sub_activity）; `motion_modules/8028b635…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、工具持有、SIMO／雙手
**⚠️ take_move_pair_may_be_single_cm**：本句是「取/觸＋推/拉」動詞配對（無連接詞）——MiniMOST 的 CM 序列本來就是 G 與 M 同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：A B G M X I A），單 action 不必然是低估。請裁決：建成**單一 CM cycle**（G 與 M 各取值）還是 acquire＋controlled_move **兩個 action**（見下方「取移建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手接觸dimm壓合治具推至規定位置】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取移建模：此句是「取/觸＋推/拉」動詞配對——應建成**一個 CM cycle（G 與 M 各取值）**，還是 acquire + controlled_move **兩個 action**？（CM 序列的 G 與 M 本來就在同一 cycle：`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d012_fe5391c6

**原文**：拿取主板放置於DIMM壓合治具
**正規化**：拿取主機板放置於dimm壓合治具
**來源**：`motion_modules/b5666b80…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、工具持有
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【拿取主機板放置於dimm壓合治具】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d013_b6ee694d

**原文**：雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)
**正規化**：雙手拿取dimm組於dimm卡槽 (依據配置要求-16個dimm)
**來源**：`motion_modules/12ce967e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、數量、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手拿取dimm組於dimm卡槽 (依據配置要求-16個dimm)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d014_6678c378

**原文**：左手抓握DIMM壓合治具的把手放×16至對應的點位
**正規化**：左手抓握dimm壓合治具的把手放×16至對應的點位
**來源**：`motion_module_versions/40bb7624…`（rows[1].sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量、工具持有
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【左手抓握dimm壓合治具的把手放×16至對應的點位】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d015_a062c017

**原文**：雙手從料架拿取DIMM材料盒放至潔淨棚的工作台
**正規化**：雙手從料架拿取dimm材料盒放至潔淨棚的工作臺
**來源**：`motion_module_versions/687ed233…`（rows[0].sub_activity）; `motion_module_versions/f799f56e…`（rows[0].sub_activity）; `motion_modules/b09813d6…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手從料架拿取dimm材料盒放至潔淨棚的工作臺】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d016_d0350279

**原文**：拿取風槍清潔放置DIMM材料盒的DIMM
**正規化**：拿取風槍清潔放置dimm材料盒的dimm
**來源**：`motion_modules/8451efa7…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取風槍清潔放置dimm材料盒的dimm】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d017_af172fd9

**原文**：雙手從DIMM材料盒拿取DIMM組至主板
**正規化**：雙手從dimm材料盒拿取dimm組至主機板
**來源**：`motion_module_versions/77097e44…`（rows[0].sub_activity）; `motion_modules/61f49bcc…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手從dimm材料盒拿取dimm組至主機板】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d018_51077fd1

**原文**：拿取風槍清潔DIMM卡槽
**正規化**：拿取風槍清潔dimm卡槽
**來源**：`motion_modules/83a0868f…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取風槍清潔dimm卡槽】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d019_d9190952

**原文**：雙手接觸DIMM壓合治具拉至規定位置
**正規化**：雙手接觸dimm壓合治具拉至規定位置
**來源**：`motion_module_versions/437a60f0…`（rows[0].sub_activity）; `motion_module_versions/b91e9fca…`（rows[0].sub_activity）; `motion_modules/3725c049…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、工具持有、SIMO／雙手
**⚠️ take_move_pair_may_be_single_cm**：本句是「取/觸＋推/拉」動詞配對（無連接詞）——MiniMOST 的 CM 序列本來就是 G 與 M 同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：A B G M X I A），單 action 不必然是低估。請裁決：建成**單一 CM cycle**（G 與 M 各取值）還是 acquire＋controlled_move **兩個 action**（見下方「取移建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手接觸dimm壓合治具拉至規定位置】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取移建模：此句是「取/觸＋推/拉」動詞配對——應建成**一個 CM cycle（G 與 M 各取值）**，還是 acquire + controlled_move **兩個 action**？（CM 序列的 G 與 M 本來就在同一 cycle：`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d020_a00f4953

**原文**：雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位
**正規化**：雙手接觸dimm卡槽的左右卡扣推至規定位置並確認到位
**來源**：`motion_module_versions/ab031277…`（rows[0].sub_activity）; `motion_modules/b55f8099…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action、SIMO／雙手
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手接觸dimm卡槽的左右卡扣推至規定位置並確認到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d021_3eab7c3e

**原文**：右手抓握風槍按動按鈕並吹風清潔DIMM卡槽
**正規化**：右手抓握風槍按動按鈕並吹風清潔dimm卡槽
**來源**：`motion_module_versions/3c2d739e…`（rows[0].sub_activity）; `motion_module_versions/76d8c950…`（rows[0].sub_activity）; `motion_modules/39a7b9db…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手抓握風槍按動按鈕並吹風清潔dimm卡槽】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d022_9f3d6515

**原文**：雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置
**正規化**：雙手接觸dimm卡槽的左右卡扣按壓並確認卡扣按壓規定位置
**來源**：`motion_modules/45915347…`（name_zh (category=wi-template)）; `motion_module_versions/fc8b5371…`（rows[0].sub_activity）; `motion_modules/f495f90c…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action、SIMO／雙手
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手接觸dimm卡槽的左右卡扣按壓並確認卡扣按壓規定位置】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d023_f8b21a01

**原文**：右手抓握風槍按動按鈕並吹風清潔DIMM
**正規化**：右手抓握風槍按動按鈕並吹風清潔dimm
**來源**：`motion_module_versions/687ed233…`（rows[4].sub_activity）; `motion_module_versions/83f8be04…`（rows[0].sub_activity）; `motion_modules/7b395f7d…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手抓握風槍按動按鈕並吹風清潔dimm】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d024_813bca06

**原文**：雙手重新抓握主板放至潔淨棚的工作台
**正規化**：雙手重新抓握主機板放至潔淨棚的工作臺
**來源**：`motion_module_versions/47007c24…`（rows[0].sub_activity）; `motion_module_versions/fb1bde71…`（rows[3].sub_activity）; `motion_modules/d4106090…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手重新抓握主機板放至潔淨棚的工作臺】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d025_bc473698

**原文**：鎖附主機板固定螺絲 x6
**來源**：`wi_rows/2e52933c…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【鎖附主機板固定螺絲 x6】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d026_1c27dc35

**原文**：雙手抓握主板組至機箱
**正規化**：雙手抓握主機板組至機箱
**來源**：`motion_modules/dcbb30a8…`（name_zh (category=wi-template)）; `motion_module_versions/34b10cd8…`（rows[0].sub_activity）; `motion_module_versions/b91e9fca…`（rows[2].sub_activity）；另 1 個來源見草稿 JSON
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、SIMO／雙手
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手抓握主機板組至機箱】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d027_f721bbfc

**原文**：左手抓握主板的包装袋去除
**正規化**：左手抓握主機板的包裝袋去除
**來源**：`motion_module_versions/549e17e8…`（rows[0].sub_activity）; `motion_module_versions/fb1bde71…`（rows[1].sub_activity）; `motion_modules/8a2348c0…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手抓握主機板的包裝袋去除】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d028_28f9ed7e

**原文**：拿取螺絲 x1
**來源**：`wi_rows/34ea3fe5…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取螺絲 x1】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d029_650ee42f

**原文**：右手從料架拿取主板保持住
**正規化**：右手從料架拿取主機板保持住
**來源**：`motion_module_versions/334b6d42…`（rows[0].sub_activity）; `motion_module_versions/fb1bde71…`（rows[0].sub_activity）; `motion_modules/979b51cb…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手從料架拿取主機板保持住】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d030_fe1f3a90

**原文**：拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)
**正規化**：拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm)
**來源**：`motion_modules/6366f744…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、數量
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d031_c6add069

**原文**：右手抓握風槍保持住至規定位置處
**來源**：`motion_module_versions/1ec11b2a…`（rows[0].sub_activity）; `motion_module_versions/687ed233…`（rows[2].sub_activity）; `motion_modules/0c944bee…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：多 action、工具持有
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手抓握風槍保持住至規定位置處】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d032_e945e29e

**原文**：右手拿取×16假DIMM插入×16至DIMM卡槽
**正規化**：右手拿取×16假dimm插入×16至dimm卡槽
**來源**：`motion_module_versions/0be9daab…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手拿取×16假dimm插入×16至dimm卡槽】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d033_51518399

**原文**：貼附Label到主板規定位置處
**正規化**：貼附label到主機板規定位置處
**來源**：`motion_modules/9f61331e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【貼附label到主機板規定位置處】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d034_314f0644

**原文**：左手抓握DIMM壓合治具的把手放至對應的點位
**正規化**：左手抓握dimm壓合治具的把手放至對應的點位
**來源**：`motion_module_versions/61b92e7e…`（rows[0].sub_activity）; `motion_modules/a6e06c10…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、工具持有
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【左手抓握dimm壓合治具的把手放至對應的點位】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d035_e55d16c7

**原文**：右手從DIMM材料盒拿取Label貼附至主板
**正規化**：右手從dimm材料盒拿取label貼附至主機板
**來源**：`motion_module_versions/2a1ba08c…`（rows[0].sub_activity）; `motion_module_versions/4495bd92…`（rows[0].sub_activity）; `motion_modules/d8232ea2…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手從dimm材料盒拿取label貼附至主機板】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d036_633b52bb

**原文**：雙手掰開DIMM卡槽的卡扣
**正規化**：雙手掰開dimm卡槽的卡扣
**來源**：`motion_modules/945b0420…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、SIMO／雙手
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手掰開dimm卡槽的卡扣】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d037_6ae5a84f

**原文**：右手接觸DIMM壓合治具的底板拉至對應的點位
**正規化**：右手接觸dimm壓合治具的底板拉至對應的點位
**來源**：`motion_module_versions/40bb7624…`（rows[2].sub_activity）; `motion_module_versions/739d25e9…`（rows[0].sub_activity）; `motion_modules/9af1d144…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、工具持有
**⚠️ take_move_pair_may_be_single_cm**：本句是「取/觸＋推/拉」動詞配對（無連接詞）——MiniMOST 的 CM 序列本來就是 G 與 M 同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2：A B G M X I A），單 action 不必然是低估。請裁決：建成**單一 CM cycle**（G 與 M 各取值）還是 acquire＋controlled_move **兩個 action**（見下方「取移建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【右手接觸dimm壓合治具的底板拉至對應的點位】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 取移建模：此句是「取/觸＋推/拉」動詞配對——應建成**一個 CM cycle（G 與 M 各取值）**，還是 acquire + controlled_move **兩個 action**？（CM 序列的 G 與 M 本來就在同一 cycle：`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d038_aa72871a

**原文**：左手抓握DIMM材料盒保持住
**正規化**：左手抓握dimm材料盒保持住
**來源**：`motion_module_versions/687ed233…`（rows[3].sub_activity）; `motion_module_versions/87f0fddc…`（rows[0].sub_activity）; `motion_modules/ef3a2924…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手抓握dimm材料盒保持住】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d039_0423b4e8

**原文**：左手從料架拿取假DIMM保持住至流水線
**正規化**：左手從料架拿取假dimm保持住至流水線
**來源**：`motion_module_versions/7fc58b77…`（rows[0].sub_activity）; `motion_module_versions/93b2939c…`（rows[0].sub_activity）; `motion_modules/ac3ce9bb…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手從料架拿取假dimm保持住至流水線】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d040_4765e5f2

**原文**：右手抓握假DIMM的包裝袋撕除
**正規化**：右手抓握假dimm的包裝袋撕除
**來源**：`motion_module_versions/7fc58b77…`（rows[1].sub_activity）; `motion_module_versions/b8e3690d…`（rows[0].sub_activity）; `motion_modules/2b73646b…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手抓握假dimm的包裝袋撕除】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d041_8dfafd2e

**原文**：折合上蓋扣合
**正規化**：摺合上蓋扣合
**來源**：`wi_rows/a2e1730a…`（sub_activity）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【摺合上蓋扣合】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d042_1dd7c1d5

**原文**：按壓功能測試治具
**來源**：`wi_rows/bd1da7bc…`（sub_activity）
**挑戰維度（規則式判定）**：工具持有
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【按壓功能測試治具】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d043_5cd079e8

**原文**：左手重新抓握主板的包装袋放至料架
**正規化**：左手重新抓握主機板的包裝袋放至料架
**來源**：`motion_module_versions/37b5e479…`（rows[0].sub_activity）; `motion_module_versions/fb1bde71…`（rows[2].sub_activity）; `motion_modules/909142f5…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手重新抓握主機板的包裝袋放至料架】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d044_4eb2b2e6

**原文**：功能測試(治具)
**來源**：`motion_templates/5f477fd6…`（name_zh）
**挑戰維度（規則式判定）**：工具持有
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【功能測試(治具)】

**預測 TMU / tech line**：
- `a1`：未編譯（missing_core_p）
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = review（理由：no_candidate_p、missing_core_p）。核准後應維持這個值嗎？

---

## d045_35372a96

**原文**：拿取排線並對準接頭
**來源**：`wi_rows/26d9037d…`（sub_activity）
**挑戰維度（規則式判定）**：多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取排線並對準接頭】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d046_3791550c

**原文**：右手並鎖附固定並確認螺絲到位
**來源**：`motion_module_versions/9569aeaf…`（rows[2].sub_activity）
**挑戰維度（規則式判定）**：多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手並鎖附固定並確認螺絲到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d047_7ff8b879

**原文**：並鎖附固定並確認螺絲到位
**來源**：`motion_module_versions/a4b7f7b7…`（rows[0].sub_activity）; `motion_modules/c7c55293…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：多 action
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【並鎖附固定並確認螺絲到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d048_37fbd2a6

**原文**：放置散熱片於 CPU 上
**正規化**：放置散熱片於 cpu 上
**來源**：`wi_rows/30da4026…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置散熱片於 cpu 上】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d049_6be614c5

**原文**：按壓 DIMM 卡扣到定位
**正規化**：按壓 dimm 卡扣到定位
**來源**：`wi_rows/0c5b0f92…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【按壓 dimm 卡扣到定位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d050_0461f75d

**原文**：拿取 M.2 SSD
**正規化**：拿取 m.2 ssd
**來源**：`wi_rows/b112297e…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取 m.2 ssd】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d051_ac155900

**原文**：拿取 DIMM 記憶體模組
**正規化**：拿取 dimm 記憶體模組
**來源**：`wi_rows/717dcc8f…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取 dimm 記憶體模組】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d052_d58a53a7

**原文**：左手抓握假DIMM的包裝袋丟至垃圾桶
**正規化**：左手抓握假dimm的包裝袋丟至垃圾桶
**來源**：`motion_module_versions/0be9daab…`（rows[1].sub_activity）; `motion_module_versions/9a0c3806…`（rows[0].sub_activity）; `motion_modules/c8728419…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手抓握假dimm的包裝袋丟至垃圾桶】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d053_631c3ece

**原文**：左手抓握DIMM材料盒放至規定位置處
**正規化**：左手抓握dimm材料盒放至規定位置處
**來源**：`motion_module_versions/687ed233…`（rows[1].sub_activity）; `motion_module_versions/b7ba9e33…`（rows[0].sub_activity）; `motion_modules/c1fde19a…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【左手抓握dimm材料盒放至規定位置處】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d054_b2618d31

**原文**：小範圍拿取(≤50cm)
**來源**：`motion_templates/e6261ef9…`（name_zh）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【小範圍拿取(≤50cm)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d055_9c1a987f

**原文**：右手拿取假DIMM組至DIMM卡槽
**正規化**：右手拿取假dimm組至dimm卡槽
**來源**：`motion_module_versions/94ca55fd…`（rows[0].sub_activity）; `motion_modules/f7f178a1…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手拿取假dimm組至dimm卡槽】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（v3 對此句型多半建單一 GM cycle）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d056_2f0cb396

**原文**：並確認DIMM點位
**正規化**：並確認dimm點位
**來源**：`motion_module_versions/40bb7624…`（rows[0].sub_activity）; `motion_module_versions/61a9b8da…`（rows[0].sub_activity）; `motion_modules/03ceef7d…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【並確認dimm點位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d057_0e83128f

**原文**：下壓 CPU 拉桿鎖定
**正規化**：下壓 cpu 拉桿鎖定
**來源**：`wi_rows/c4104cb6…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【下壓 cpu 拉桿鎖定】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d058_130bb1ad

**原文**：電動鎖附(多顆)
**來源**：`motion_templates/8b1753a1…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【電動鎖附(多顆)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d059_323b04c1

**原文**：鎖附螺絲
**來源**：`motion_templates/5d6bb4c7…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【鎖附螺絲】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d060_995f5d45

**原文**：貼標籤
**來源**：`motion_templates/03fcc018…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**⚠️ empty_lexicon_no_slot_candidates**：dev DB 的 rule_option_synonyms 目前是空的：所有 slot 都沒有候選，option code 需 IE 自填（並考慮順手登記同義詞）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【貼標籤】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（判型詞典僅認「治具/機台/壓合」類詞）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

