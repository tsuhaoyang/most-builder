# IE 覆核表 — gold set 擴充預標註草稿

<!-- 本檔由 scripts/gold_harvest.py 產生；重跑 harvest 會整檔重寫，IE 批註請寫在草稿 JSON 或另開檔案 -->

草稿位置：`tests/gold/wi_plans_draft/`。**這些不是 gold**（`approved_by: null`、`review_status: pending_ie`），評測不會撿到。核准／轉正流程見 `docs/llm/gold-review/README.md`。

**先讀這個——預標註的系統性偏差**：現行 rule planner 對任何輸入都只會產生**1 個 action、evidence=整句**。所以「預測 action 數=1」不是模型判斷，是結構限制；帶 `likely_multi_action_undercounted` 的每一筆都請假設切分是錯的，逐動詞重切（**例外**：該筆若有 `v3_structure_hint: single_cycle`，警語降級——v3 結構顯示 IE 當初建為單一 cycle，預設依此）。帶 `take_place_pair_may_be_single_gm` 的是「取＋放」配對——GM 本來就是 G＋P 同 cycle，**不預設低估**，請用該筆的「取放建模」題裁決單一 GM 或兩個 action。帶 `take_move_pair_may_be_single_cm` 的是「取/觸＋推/拉」配對——CM 的 G 與 M 同一 cycle，同樣**不預設低估**，請用該筆的「取移建模」題裁決單一 CM 或兩個 action。配對題與切分題已用 **v3 結構回填**（D3-014 裁決 3：v3 遷移資料是 IE 驗證過並提供的，結構＝IE 的切分裁決）：有結構答案的是**確認題**（預設依 v3 結構，不同意再改），缺失/矛盾的維持開放題——hint 是證據不是判決，IE 可推翻。帶 `acquire_without_place` 的是「取而無放」（裁決 2：取最後一定有放）——請回答該筆的「放」在哪（WARN 不 BLOCK；單句 acquire 可能合法）。另外：`challenge_tags` 裡 9 個可判維度的 `false` 也是啟發式輸出（`heuristic_tags_unverified` 點名的維度已有實證漏標），true/false 請一併確認。

共 60 筆，其中 25 筆帶 ⚠️ 旗標。

其中 **39 筆**已由 `review-state.json` 合併 IE 覆核狀態（各節「IE 覆核狀態」行）。注意：那是**切分維度**的確認/裁決，**不是整筆 gold 核准**——cycle 仍 incomplete 的照樣要覆核 option code，轉正另有流程（`docs/llm/gold-review/README.md`）。

---

## d001_6fa45cdb

**原文**：確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)
**正規化**：確認dimm點位,並按壓dimm壓合治具的把手 (依據配置要求-16個dimm)
**來源**：`motion_modules/d630108e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：全形字元、中英混合、多 action、數量、工具持有
**v3 結構**：`multi_cycle_3`——`motion_modules/d630108e…`（name_zh (category=wi-template)；3 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝GM（一般移動），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【確認dimm點位,並按壓dimm壓合治具的把手 (依據配置要求-16個dimm)】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 M3 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **3 個 cycle**（證據：`motion_modules/d630108e…`（name_zh (category=wi-template)；3 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：GM（一般移動） → CM（控制移動），請確認】
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d002_7c6eb8af

**原文**：雙手從DIMM材料盒拿取×16DIMM插入×16至主板
**正規化**：雙手從dimm材料盒拿取×16dimm插入×16至主機板
**來源**：`motion_module_versions/255beb05…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、數量、SIMO／雙手
**v3 結構**：`single_cycle`——`motion_module_versions/255beb05…`（rows[0].sub_activity；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手從dimm材料盒拿取×16dimm插入×16至主機板】

**預測 TMU / tech line**：
- `a1`：TMU=24.0，tech line=`A0 B0 G0 A0 B0 P24 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/255beb05…`（rows[0].sub_activity；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/255beb05…`（rows[0].sub_activity；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d003_b49a90ee

**原文**：雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位
**正規化**：雙手接觸dimm卡槽的左右卡扣推×16至規定位置並確認到位
**來源**：`motion_module_versions/2b40d576…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：中英混合、多 action、數量、SIMO／雙手
**v3 結構**：`single_cycle`——`motion_module_versions/2b40d576…`（rows[0].sub_activity；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手接觸dimm卡槽的左右卡扣推×16至規定位置並確認到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/2b40d576…`（rows[0].sub_activity；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d004_5cb719bb

**原文**：拿取主板，去除包裝袋，將主板放置工作台
**正規化**：拿取主機板,去除包裝袋,將主機板放置工作臺
**來源**：`motion_modules/8436a0d0…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、全形字元、多 action
**v3 結構**：`multi_cycle_4`——`motion_modules/8436a0d0…`（name_zh (category=wi-template)；4 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取主機板,去除包裝袋,將主機板放置工作臺】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **4 個 cycle**（證據：`motion_modules/8436a0d0…`（name_zh (category=wi-template)；4 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d005_fe5391c6

**原文**：拿取主板放置於DIMM壓合治具
**正規化**：拿取主機板放置於dimm壓合治具
**來源**：`motion_modules/b5666b80…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、工具持有
**v3 結構**：`multi_cycle_2`——`motion_modules/b5666b80…`（name_zh (category=wi-template)；2 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（P 方向數）**：方向數變體已確認照預設（IEC141289，2026-08-17）。
**⚠️ p_direction_single_default**：P 方向數（IE 情境規則 D3-017）：賓語屬**機構件類**（治具/卡槽/機箱/接頭/點位）→ 必對準，已預設 `p_place_single`。**方向數預設一種，不對請改**（p_place_multi 多種方向／p_place_none 無方向）
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【拿取主機板放置於dimm壓合治具】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **2 個 cycle**（證據：`motion_modules/b5666b80…`（name_zh (category=wi-template)；2 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）
3. P 方向數：P 方向數（IE 情境規則 D3-017）：賓語屬**機構件類**（治具/卡槽/機箱/接頭/點位）→ 必對準，已預設 `p_place_single`。**方向數預設一種，不對請改**（p_place_multi 多種方向／p_place_none 無方向）
4. 取放建模（確認題）：v3 結構顯示 IE 當初把這句切成 **2 個 cycle**（證據：`motion_modules/b5666b80…`（name_zh (category=wi-template)；2 cycle；v3））——**預設依此切成 2 個 action/cycle**；不同意再改（hint 是證據不是判決，可推翻）。
5. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
6. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d006_ee5c168e

**原文**：電動起子鎖附 CPU 散熱片螺絲 x4
**正規化**：電動起子鎖附 cpu 散熱片螺絲 x4
**來源**：`wi_rows/30e06fae…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量、工具持有
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【電動起子鎖附 cpu 散熱片螺絲 x4】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d007_a062c017

**原文**：雙手從料架拿取DIMM材料盒放至潔淨棚的工作台
**正規化**：雙手從料架拿取dimm材料盒放至潔淨棚的工作臺
**來源**：`motion_module_versions/687ed233…`（rows[0].sub_activity）; `motion_module_versions/f799f56e…`（rows[0].sub_activity）; `motion_modules/b09813d6…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、SIMO／雙手
**v3 結構**：`single_cycle`——`motion_module_versions/687ed233…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/f799f56e…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/b09813d6…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**✅ IE 覆核狀態（P 方向數）**：方向數變體已確認照預設（IEC141289，2026-08-17）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ p_direction_none_by_context**：P 方向數（IE 情境規則 D3-017）：賓語屬**盤面類**（流水線/工作台/垃圾桶/料盒/材料盒/料架）→ 無方向，已套用 `p_place_none`。請確認
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手從料架拿取dimm材料盒放至潔淨棚的工作臺】

**預測 TMU / tech line**：
- `a1`：TMU=6.0，tech line=`A0 B0 G0 A0 B0 P6 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/687ed233…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/f799f56e…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/b09813d6…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. P 方向數：P 方向數（IE 情境規則 D3-017）：賓語屬**盤面類**（流水線/工作台/垃圾桶/料盒/材料盒/料架）→ 無方向，已套用 `p_place_none`。請確認
4. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/687ed233…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/f799f56e…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/b09813d6…`（name_zh (category=action)；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d008_72dc0511

**原文**：從料架上拿取假DIMM，去除其包裝袋
**正規化**：從料架上拿取假dimm,去除其包裝袋
**來源**：`motion_modules/d9203ed2…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：全形字元、中英混合、多 action
**v3 結構**：`multi_cycle_2`——`motion_modules/d9203ed2…`（name_zh (category=wi-template)；2 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**✅ IE 裁決（TMU=0.0）**：`distance_unstated`——句子未述距離、判定資訊不足（IEC141289，2026-08-17）；草稿已記 `expected_incomplete_reason`（轉正走誠實記錄路徑，不發明距離）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查
**⚠️ zero_tmu_distance_unstated**：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【從料架上拿取假dimm,去除其包裝袋】

**預測 TMU / tech line**：
- `a1`：TMU=0.0，tech line=`A0 B0 G0 M0 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **2 個 cycle**（證據：`motion_modules/d9203ed2…`（name_zh (category=wi-template)；2 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → CM（控制移動），請確認】
3. TMU=0.0：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）。
4. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d009_b6ee694d

**原文**：雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)
**正規化**：雙手拿取dimm組於dimm卡槽 (依據配置要求-16個dimm)
**來源**：`motion_modules/12ce967e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、數量、SIMO／雙手
**v3 結構**：`single_cycle`——`motion_modules/12ce967e…`（name_zh (category=wi-template)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手拿取dimm組於dimm卡槽 (依據配置要求-16個dimm)】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_modules/12ce967e…`（name_zh (category=wi-template)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_modules/12ce967e…`（name_zh (category=wi-template)；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
6. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d010_d0350279

**原文**：拿取風槍清潔放置DIMM材料盒的DIMM
**正規化**：拿取風槍清潔放置dimm材料盒的dimm
**來源**：`motion_modules/8451efa7…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**v3 結構**：`multi_cycle_5`——`motion_modules/8451efa7…`（name_zh (category=wi-template)；5 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**✅ IE 覆核狀態（P 方向數）**：方向數變體已確認照預設（IEC141289，2026-08-17）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ p_direction_none_by_context**：P 方向數（IE 情境規則 D3-017）：賓語屬**盤面類**（流水線/工作台/垃圾桶/料盒/材料盒/料架）→ 無方向，已套用 `p_place_none`。請確認
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【拿取風槍清潔放置dimm材料盒的dimm】

**預測 TMU / tech line**：
- `a1`：TMU=6.0，tech line=`A0 B0 G0 A0 B0 P6 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **5 個 cycle**（證據：`motion_modules/8451efa7…`（name_zh (category=wi-template)；5 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. P 方向數：P 方向數（IE 情境規則 D3-017）：賓語屬**盤面類**（流水線/工作台/垃圾桶/料盒/材料盒/料架）→ 無方向，已套用 `p_place_none`。請確認
4. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d011_af172fd9

**原文**：雙手從DIMM材料盒拿取DIMM組至主板
**正規化**：雙手從dimm材料盒拿取dimm組至主機板
**來源**：`motion_module_versions/77097e44…`（rows[0].sub_activity）; `motion_modules/61f49bcc…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合、SIMO／雙手
**v3 結構**：`single_cycle`——`motion_module_versions/77097e44…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/61f49bcc…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手從dimm材料盒拿取dimm組至主機板】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/77097e44…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/61f49bcc…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/77097e44…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/61f49bcc…`（name_zh (category=action)；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d012_51077fd1

**原文**：拿取風槍清潔DIMM卡槽
**正規化**：拿取風槍清潔dimm卡槽
**來源**：`motion_modules/83a0868f…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、多 action、工具持有
**v3 結構**：`single_cycle`——`motion_modules/83a0868f…`（name_zh (category=wi-template)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取風槍清潔dimm卡槽】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_modules/83a0868f…`（name_zh (category=wi-template)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d013_6678c378

**原文**：左手抓握DIMM壓合治具的把手放×16至對應的點位
**正規化**：左手抓握dimm壓合治具的把手放×16至對應的點位
**來源**：`motion_module_versions/40bb7624…`（rows[1].sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量、工具持有
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

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

## d014_1c27dc35

**原文**：雙手抓握主板組至機箱
**正規化**：雙手抓握主機板組至機箱
**來源**：`motion_modules/dcbb30a8…`（name_zh (category=wi-template)）; `motion_module_versions/34b10cd8…`（rows[0].sub_activity）; `motion_module_versions/b91e9fca…`（rows[2].sub_activity）；另 1 個來源見草稿 JSON
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、SIMO／雙手
**v3 結構**：`ambiguous`——`motion_modules/dcbb30a8…`（name_zh (category=wi-template)；3 cycle；v3）；`motion_module_versions/34b10cd8…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/b91e9fca…`（rows[2].sub_activity；1 cycle；v3）；`motion_modules/32a29bba…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 裁決（切分維度）**：`single_cycle`（IEC141289，2026-08-16）——裁決取代本節 v3 結構的 ambiguous/開放題。僅裁決切分，不是整筆 gold 核准。
  - 裁決註記：IE 裁決（第二輪更正，2026-08-16 釐清並獲 User 確認）：本句本身＝1 列（單一 cycle）。首輪「3 列」的答案是對整個三步驟製程（wi-template motion_modules/dcbb30a8-44f0-4218-aafb-b6882a66aca0）說的——提問時把範本結構誤述為句子切分，已釐清更正（先前裁決全文與更正理由見 ruling_history，不無痕覆寫）。結構證據與更正後裁決一致：本句在該 wi-template v1 中就是 rows[2] 一列＝一個 cycle（motion_module_versions/b91e9fca-a311-496a-bbdb-db6f76f460c2），單列 action module（motion_modules/32a29bba-fabe-4332-baee-9785d4c2525d）亦為 1 cycle——首輪對它的否定一併撤回。被否定的是「wi-template 名稱句對應發布版 3 列＝本句切 3 個 cycle」的推論（motion_modules/dcbb30a8 的 name_zh 來源，標 ie_ruling_rejected 證據保留）：範本名稱是三步驟製程的標題，其 3 列是各自獨立的完整子句，不是本句的切分。
  - IE 裁決否定的結構（證據保留不刪）：`motion_modules/dcbb30a8…`（name_zh (category=wi-template)；3 cycle）
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【雙手抓握主機板組至機箱】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】結構訊號缺失或矛盾（conflicting_v3_structures；證據：`motion_modules/dcbb30a8…`（name_zh (category=wi-template)；3 cycle；v3）；`motion_module_versions/34b10cd8…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/b91e9fca…`（rows[2].sub_activity；1 cycle；v3）；`motion_modules/32a29bba…`（name_zh (category=action)；1 cycle；v3））——維持開放題，請逐動詞裁決。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模：此句是「取＋放」動詞配對——應建成**一個 GM cycle（G 與 P 各取值）**，還是 acquire + move_place **兩個 action**？（裁決 1：看動作逐案裁決，不預設方向）【v3 結構訊號缺失或矛盾（conflicting_v3_structures）：`motion_modules/dcbb30a8…`（name_zh (category=wi-template)；3 cycle；v3）；`motion_module_versions/34b10cd8…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/b91e9fca…`（rows[2].sub_activity；1 cycle；v3）；`motion_modules/32a29bba…`（name_zh (category=action)；1 cycle；v3）】
4. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d015_650ee42f

**原文**：右手從料架拿取主板保持住
**正規化**：右手從料架拿取主機板保持住
**來源**：`motion_module_versions/334b6d42…`（rows[0].sub_activity）; `motion_module_versions/fb1bde71…`（rows[0].sub_activity）; `motion_modules/979b51cb…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、多 action
**v3 結構**：`single_cycle`——`motion_module_versions/334b6d42…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/fb1bde71…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/979b51cb…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【右手從料架拿取主機板保持住】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 A0 B0 P3 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/334b6d42…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/fb1bde71…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/979b51cb…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d016_633b52bb

**原文**：雙手掰開DIMM卡槽的卡扣
**正規化**：雙手掰開dimm卡槽的卡扣
**來源**：`motion_modules/945b0420…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、SIMO／雙手
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【雙手掰開dimm卡槽的卡扣】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. SIMO/雙手：左右手是否同時動作？是否需標 hand 與 SIMO 群組？（現行 plan 契約未表達 SIMO——若需要請註記）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d017_bc473698

**原文**：鎖附主機板固定螺絲 x6
**來源**：`wi_rows/2e52933c…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【鎖附主機板固定螺絲 x6】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d018_51518399

**原文**：貼附Label到主板規定位置處
**正規化**：貼附label到主機板規定位置處
**來源**：`motion_modules/9f61331e…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）、中英混合
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**✅ IE 裁決（TMU=0.0）**：`distance_unstated`——句子未述距離、判定資訊不足（IEC141289，2026-08-17）；草稿已記 `expected_incomplete_reason`（轉正走誠實記錄路徑，不發明距離）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答
**⚠️ zero_tmu_distance_unstated**：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【貼附label到主機板規定位置處】

**預測 TMU / tech line**：
- `a1`：TMU=0.0，tech line=`A0 B0 G0 M0 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → CM（控制移動），請確認】
3. TMU=0.0：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）。
4. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d019_28f9ed7e

**原文**：拿取螺絲 x1
**來源**：`wi_rows/34ea3fe5…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取螺絲 x1】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
4. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d020_0423b4e8

**原文**：左手從料架拿取假DIMM保持住至流水線
**正規化**：左手從料架拿取假dimm保持住至流水線
**來源**：`motion_module_versions/7fc58b77…`（rows[0].sub_activity）; `motion_module_versions/93b2939c…`（rows[0].sub_activity）; `motion_modules/ac3ce9bb…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合、多 action
**v3 結構**：`single_cycle`——`motion_module_versions/7fc58b77…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/93b2939c…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/ac3ce9bb…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【左手從料架拿取假dimm保持住至流水線】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 A0 B0 P3 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/7fc58b77…`（rows[0].sub_activity；1 cycle；v3）；`motion_module_versions/93b2939c…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/ac3ce9bb…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d021_fe1f3a90

**原文**：拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)
**正規化**：拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm)
**來源**：`motion_modules/6366f744…`（name_zh (category=wi-template)）
**挑戰維度（規則式判定）**：中英混合、數量
**v3 結構**：`multi_cycle_2`——`motion_modules/6366f744…`（name_zh (category=wi-template)；2 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm)】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句切成 **2 個 cycle**（證據：`motion_modules/6366f744…`（name_zh (category=wi-template)；2 cycle；v3）），預設依此切分；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句切成 **2 個 cycle**（證據：`motion_modules/6366f744…`（name_zh (category=wi-template)；2 cycle；v3））——**預設依此切成 2 個 action/cycle**；不同意再改（hint 是證據不是判決，可推翻）。
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d022_e945e29e

**原文**：右手拿取×16假DIMM插入×16至DIMM卡槽
**正規化**：右手拿取×16假dimm插入×16至dimm卡槽
**來源**：`motion_module_versions/0be9daab…`（rows[0].sub_activity）
**挑戰維度（規則式判定）**：中英混合、數量
**v3 結構**：`single_cycle`——`motion_module_versions/0be9daab…`（rows[0].sub_activity；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【右手拿取×16假dimm插入×16至dimm卡槽】

**預測 TMU / tech line**：
- `a1`：TMU=24.0，tech line=`A0 B0 G0 A0 B0 P24 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/0be9daab…`（rows[0].sub_activity；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/0be9daab…`（rows[0].sub_activity；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
4. 數量：句中的數量應掛在哪個 action？frequency=N 還是 repeat？（現行 QuantityPolicyV1 保守處理並標 quantity_policy_review）
5. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d023_1dd7c1d5

**原文**：按壓功能測試治具
**來源**：`wi_rows/bd1da7bc…`（sub_activity）
**挑戰維度（規則式判定）**：工具持有
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝GM（一般移動），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【按壓功能測試治具】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 M3 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：GM（一般移動） → CM（控制移動），請確認】
3. 工具持有：工具是否跨動作持有？若是，後續動作 G 應留空並在 dependencies 標 tool_held_for。
4. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d024_4eb2b2e6

**原文**：功能測試(治具)
**來源**：`motion_templates/5f477fd6…`（name_zh）
**挑戰維度（規則式判定）**：工具持有
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

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

## d025_8dfafd2e

**原文**：折合上蓋扣合
**正規化**：摺合上蓋扣合
**來源**：`wi_rows/a2e1730a…`（sub_activity）
**挑戰維度（規則式判定）**：繁簡（簡體字/大陸用語）
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【摺合上蓋扣合】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d026_35372a96

**原文**：拿取排線並對準接頭
**來源**：`wi_rows/26d9037d…`（sub_activity）
**挑戰維度（規則式判定）**：多 action
**v3 結構**：`ambiguous`——`wi_rows/26d9037d…`（sub_activity；1 cycle；非 v3，不餵 hint）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 裁決（切分維度）**：`single_cycle`（IEC141289，2026-08-16）——裁決取代本節 v3 結構的 ambiguous/開放題。僅裁決切分，不是整筆 gold 核准。
  - 裁決註記：IE 裁決（首輪覆核）：「拿取排線並對準接頭」為 1 列（單一 cycle）；plan 已是 1 action，內容不動（ie_modified: false）。
**⚠️ likely_multi_action_undercounted**：rule planner 結構上永遠只出 1 個 action；本句含多動詞/連接詞，**切分幾乎必然低估**——請務必逐動詞檢查

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取排線並對準接頭】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】結構訊號缺失或矛盾（no_v3_structure_signal；證據：`wi_rows/26d9037d…`（sub_activity；1 cycle；非 v3，不餵 hint））——維持開放題，請逐動詞裁決。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d027_3791550c

**原文**：右手並鎖附固定並確認螺絲到位
**來源**：`motion_module_versions/9569aeaf…`（rows[2].sub_activity）
**挑戰維度（規則式判定）**：多 action
**v3 結構**：`single_cycle`——`motion_module_versions/9569aeaf…`（rows[2].sub_activity；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【右手並鎖附固定並確認螺絲到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/9569aeaf…`（rows[2].sub_activity；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d028_7ff8b879

**原文**：並鎖附固定並確認螺絲到位
**來源**：`motion_module_versions/a4b7f7b7…`（rows[0].sub_activity）; `motion_modules/c7c55293…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：多 action
**v3 結構**：`single_cycle`——`motion_module_versions/a4b7f7b7…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/c7c55293…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ likely_multi_action_undercounted**：本句含多動詞/連接詞，rule planner 只出 1 個 action——但 **v3 結構顯示 IE 當初把這句建為單一 cycle**（證據見本節「v3 結構」與草稿 `v3_structure_evidence`），「幾乎必然低估」對本筆**降級**：預設依 v3 結構（單一 cycle），除非你認定 v3 的切分本身有誤（hint 是證據不是判決，可推翻）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【並鎖附固定並確認螺絲到位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/a4b7f7b7…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/c7c55293…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d029_37fbd2a6

**原文**：放置散熱片於 CPU 上
**正規化**：放置散熱片於 cpu 上
**來源**：`wi_rows/30da4026…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置散熱片於 cpu 上】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d030_6be614c5

**原文**：按壓 DIMM 卡扣到定位
**正規化**：按壓 dimm 卡扣到定位
**來源**：`wi_rows/0c5b0f92…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（判型）**：第三輪判型修正已確認照預設（IEC141289，2026-08-17）。確認≠修改，`ie_modified` 維持 false。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【按壓 dimm 卡扣到定位】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 M3 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → CM（控制移動），請確認】
3. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d031_0461f75d

**原文**：拿取 M.2 SSD
**正規化**：拿取 m.2 ssd
**來源**：`wi_rows/b112297e…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取 m.2 ssd】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d032_ac155900

**原文**：拿取 DIMM 記憶體模組
**正規化**：拿取 dimm 記憶體模組
**來源**：`wi_rows/717dcc8f…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取 dimm 記憶體模組】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d033_b2618d31

**原文**：小範圍拿取(≤50cm)
**來源**：`motion_templates/e6261ef9…`（name_zh）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【小範圍拿取(≤50cm)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d034_9c1a987f

**原文**：右手拿取假DIMM組至DIMM卡槽
**正規化**：右手拿取假dimm組至dimm卡槽
**來源**：`motion_module_versions/94ca55fd…`（rows[0].sub_activity）; `motion_modules/f7f178a1…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**v3 結構**：`single_cycle`——`motion_module_versions/94ca55fd…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/f7f178a1…`（name_zh (category=action)；1 cycle；v3）（hint 是證據不是判決；預設依 v3 結構，IE 可推翻）
**✅ IE 覆核狀態（切分維度）**：已確認照 v3 結構預設（IEC141289，2026-08-16）。僅確認切分，不是整筆 gold 核准；`ie_modified: false`（確認≠修改——本筆不計入 planner 段 Plan 層證據力）。
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝GM（一般移動）。不同意新判型請在本筆「判型」題回答
**⚠️ take_place_pair_may_be_single_gm**：本句是「取＋放」動詞配對（無連接詞）——MiniMOST 的 GM 序列本來就是 G＋P 同一 cycle，單 action 不必然是低估。請裁決：建成**單一 GM cycle**（G 與 P 各取值）還是 acquire＋move_place **兩個 action**（見下方「取放建模」題；不預設方向）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` move_place：【右手拿取假dimm組至dimm卡槽】

**預測 TMU / tech line**：
- `a1`：TMU=16.0，tech line=`A0 B0 G0 A0 B0 P16 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。【v3 結構】IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/94ca55fd…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/f7f178a1…`（name_zh (category=action)；1 cycle；v3）），預設依此；不同意再改。
2. 判型（a1）：預測為 move_place，對嗎？若對，core 參數 P（放置） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → GM（一般移動），請確認】
3. 取放建模（確認題）：v3 結構顯示 IE 當初把這句建為**單一 cycle**（證據：`motion_module_versions/94ca55fd…`（rows[0].sub_activity；1 cycle；v3）；`motion_modules/f7f178a1…`（name_zh (category=action)；1 cycle；v3））——**預設建成單一 GM cycle（G 與 P 各取值）**；不同意再改成 acquire + move_place 兩個 action（hint 是證據不是判決，可推翻）。
4. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d035_2f0cb396

**原文**：並確認DIMM點位
**正規化**：並確認dimm點位
**來源**：`motion_module_versions/40bb7624…`（rows[0].sub_activity）; `motion_module_versions/61a9b8da…`（rows[0].sub_activity）; `motion_modules/03ceef7d…`（name_zh (category=action)）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【並確認dimm點位】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d036_0e83128f

**原文**：下壓 CPU 拉桿鎖定
**正規化**：下壓 cpu 拉桿鎖定
**來源**：`wi_rows/c4104cb6…`（sub_activity）
**挑戰維度（規則式判定）**：中英混合
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【下壓 cpu 拉桿鎖定】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d037_130bb1ad

**原文**：電動鎖附(多顆)
**來源**：`motion_templates/8b1753a1…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【電動鎖附(多顆)】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d038_323b04c1

**原文**：鎖附螺絲
**來源**：`motion_templates/5d6bb4c7…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【鎖附螺絲】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d039_995f5d45

**原文**：貼標籤
**來源**：`motion_templates/03fcc018…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**✅ IE 覆核狀態（切分維度・批次確認）**：無切分爭點案例，IE 整批確認現行切分（單 action＝single_cycle；IEC141289，2026-08-17）。與逐筆確認可區分（`segmentation_source: no_contention_batch_confirmed`——未逐筆核 v3 結構證據）；僅確認切分，不是整筆 gold 核准。

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【貼標籤】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d040_cc6c7d56

**原文**：貼上序號標籤
**來源**：`wi_rows/6adbba57…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【貼上序號標籤】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d041_86a61399

**原文**：自料盒拿取主機板
**來源**：`wi_rows/56c0ad5d…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【自料盒拿取主機板】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d042_c82940ca

**原文**：精密對準裝配
**來源**：`motion_templates/25da0fff…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【精密對準裝配】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d043_850cc7ef

**原文**：移動/走步
**來源**：`motion_templates/9be91373…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【移動/走步】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d044_1e0d9e15

**原文**：熱壓導熱膠固化
**來源**：`wi_rows/2d428ddc…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【熱壓導熱膠固化】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d045_e552df5e

**原文**：旋緊天線接頭
**來源**：`wi_rows/22a278d0…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【旋緊天線接頭】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d046_fe5df381

**原文**：整理機殼內線材
**來源**：`wi_rows/27f942d5…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【整理機殼內線材】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d047_e55c3e1c

**原文**：放置擋板至機殼後方
**來源**：`wi_rows/3c953e62…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置擋板至機殼後方】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d048_9b7bc11d

**原文**：放置成品入緩衝棧板
**來源**：`wi_rows/a320207b…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置成品入緩衝棧板】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d049_e0c7f95c

**原文**：放置主機板入機殼
**來源**：`wi_rows/443ccae7…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置主機板入機殼】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d050_901d1623

**原文**：放置
**來源**：`motion_templates/12f6f6b9…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【放置】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d051_8b6e6aab

**原文**：擦拭外殼指紋
**來源**：`wi_rows/7dbf5621…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【擦拭外殼指紋】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d052_7f085e02

**原文**：撕除螢幕保護膜
**來源**：`wi_rows/e58b4ad3…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答
**⚠️ zero_tmu_distance_unstated**：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【撕除螢幕保護膜】

**預測 TMU / tech line**：
- `a1`：TMU=0.0，tech line=`A0 B0 G0 M0 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → CM（控制移動），請確認】
3. TMU=0.0：此句未述距離，**TMU=0.0 非真值**（引擎口徑：距離未述＝0cm、M 階梯 0→0；linker 只掛 core 參數，伴隨 slot 未填）——complete 是結構完成度不是 TMU 可信度。**請補距離（改 plan/cycle 後 `--recompile` 重算）或判定句子資訊不足**（轉正時顯式寫 expected_incomplete_reason；空殼守門要求 total_tmu > 0，原樣轉正會被擋）。
4. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d053_553bb598

**原文**：撕開/移除
**來源**：`motion_templates/8bd71661…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【撕開/移除】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d054_21ccfce2

**原文**：插接線材
**來源**：`motion_templates/25b51820…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【插接線材】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d055_60223e3d

**原文**：插入/組裝
**來源**：`motion_templates/ada85770…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【插入/組裝】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d056_debe277a

**原文**：掃描條碼建檔
**來源**：`wi_rows/7fc33f3a…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【掃描條碼建檔】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d057_ff7166e0

**原文**：掃描/檢查
**來源**：`motion_templates/3e9ea047…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【掃描/檢查】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d058_2e7b2e5a

**原文**：按壓/按鈕
**來源**：`motion_templates/f378444b…`（name_zh）
**挑戰維度（規則式判定）**：（無命中）
**⚠️ typing_changed_by_verb_lexicon**：**第三輪判型已修正，請確認**：動詞字典自本輪參與 GM/CM 判型（D3-017，衝突矩陣見 nlp/rule_based.py classify_seq）——舊判型（僅名詞觸發）＝未定（composite_unknown），新判型（動詞字典參與）＝CM（控制移動）。不同意新判型請在本筆「判型」題回答

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` controlled_move：【按壓/按鈕】

**預測 TMU / tech line**：
- `a1`：TMU=3.0，tech line=`A0 B0 G0 M3 X0 I0 A0`
**預測 routing**：`review`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 controlled_move，對嗎？若對，core 參數 M（控制移動） 的 option code 是什麼？（預標註無候選時請直接填）【第三輪判型已修正：未定（composite_unknown） → CM（控制移動），請確認】
3. routing：預測 routing_status = review（理由：無）。核准後應維持這個值嗎？

---

## d059_00104439

**原文**：按下電源測試按鈕
**來源**：`wi_rows/8712630a…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【按下電源測試按鈕】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

---

## d060_df2af257

**原文**：拿取風扇模組
**來源**：`wi_rows/dd6bc54d…`（sub_activity）
**挑戰維度（規則式判定）**：（無命中）

**預測 action 數**：1
**預測切分（evidence 以【】標在正規化原文上）**：
- `a1` composite_unknown：【拿取風扇模組】

**預測 TMU / tech line**：
- `a1`：未編譯（composite_unknown）
**預測 routing**：`abstain`

**IE 請回答**：
1. 切分：預測 action 數 = 1。本句實際應拆成幾個 action？若不同，請在 plan.actions 增列並各給 evidence（原文子字串與 offset）。
2. 判型（a1）：預測為 composite_unknown（第三輪起動詞字典已參與判型——仍未定＝動詞未登記/單一動詞不足/訊號衝突棄權，逐類統計見 harvest-summary）。實際動作類型是哪個：acquire / move_place / controlled_move / process / inspect？
3. routing：預測 routing_status = abstain（理由：composite_unknown）。核准後應維持這個值嗎？

