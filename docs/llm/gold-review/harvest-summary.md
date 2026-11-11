# Harvest 摘要 — gold set 擴充候選採集

<!-- 本檔由 scripts/gold_harvest.py 產生（決定性輸出，不含 timestamp） -->

## 來源（唯讀 DB）

| 來源 | 撈得筆數 |
|---|---|
| motion_modules | 42 |
| motion_module_versions.rows[] | 58 |
| wi_rows | 30 |
| motion_templates | 16 |

正規化去重後 unique 候選：**39**；本次選出：**39**（上限 60，多樣性 greedy max-coverage，非取前 N）。

**取樣性質**：coverage-optimized（挑戰維度過採樣），**不是**分佈代表性樣本——在本集合上量到的分數不可外推為生產分佈的表現；分佈代表性指標需另抽隨機樣本。

另有 **53 筆**與正式 gold（tests/gold/wi_plans/）既有案例同句，已排除不重複進草稿：「並確認DIMM點位」、「並鎖附固定並確認螺絲到位」、「右手並鎖附固定並確認螺絲到位」、「右手從DIMM材料盒拿取Label貼附至主板」、「右手從料架拿取主板保持住」、「右手抓握假DIMM的包裝袋撕除」、「右手抓握电动起子保持住至機箱」、「右手抓握風槍保持住至規定位置處」、「右手抓握風槍按動按鈕並吹風清潔DIMM」、「右手抓握風槍按動按鈕並吹風清潔DIMM卡槽」、「右手拿取×16假DIMM插入×16至DIMM卡槽」、「右手拿取假DIMM組至DIMM卡槽」、「右手接觸DIMM壓合治具的底板拉至對應的點位」、「左手從料架拿取假DIMM保持住至流水線」、「左手從螺絲料盒拿取螺絲」、「左手抓握DIMM壓合治具的把手放至對應的點位」、「左手抓握DIMM材料盒保持住」、「左手抓握DIMM材料盒放至規定位置處」、「左手抓握主板的包装袋去除」、「左手抓握假DIMM的包裝袋丟至垃圾桶」、「左手重新抓握主板的包装袋放至料架」、「從料架上拿取假DIMM，去除其包裝袋」、「拿取主板，去除包裝袋，將主板放置工作台」、「拿取主板放置於DIMM壓合治具」、「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」、「拿取螺絲 x1」、「拿取電動起子，依圖示鎖附兩顆螺絲」、「拿取風槍清潔DIMM卡槽」、「按壓 DIMM 卡扣到定位」、「按壓/按鈕」、「按壓功能測試治具」、「撕除螢幕保護膜」、「放置散熱片於 CPU 上」、「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」、「貼附Label到主板規定位置處」、「鎖附主機板固定螺絲 x6」、「鎖附螺絲」、「雙手從DIMM材料盒拿取DIMM組至主板」、「雙手從DIMM材料盒拿取×16DIMM插入×16至主板」、「雙手從料架拿取DIMM材料盒放至潔淨棚的工作台」、「雙手抓握主板保持住至流水線」、「雙手抓握主板放至DIMM壓合治具」、「雙手抓握主板組至機箱」、「雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)」、「雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置」、「雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位」、「雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位」、「雙手接觸DIMM壓合治具拉至規定位置」、「雙手接觸DIMM壓合治具推至規定位置」、「雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置」、「雙手重新抓握主板放至潔淨棚的工作台」、「電動起子鎖附 CPU 散熱片螺絲 x4」、「電動鎖附(多顆)」。

**⚠️ 未達 50 筆**：實際只有 39 筆 unique 真實描述，缺額 11 筆需要 IE 提供真實工單（不得複製貼上湊數、不得生成假案例）。

詞典（rule_option_synonyms @ MINIMOST_FACTORY_V2）：**22 條**。

Cycle 完成度：**0／39 筆**至少一個 cycle complete 帶 TMU（TMU 唯一出處＝most_engine）；其餘 39 筆全部 incomplete（缺 slot 候選或判型未定——逐筆原因見草稿 `expected_cycles[].issues_contain`）。

## 挑戰維度覆蓋（spec §14.3 的 16 維度）

| 維度 | 規則式可判？ | 全候選命中 | 已選命中 |
|---|---|---|---|
| 繁簡（簡體字/大陸用語）（`zh_simplified_variant`） | 可判 | 1 | 1 |
| 全形字元（`fullwidth_chars`） | 可判 | 0 | 0 |
| 錯字（`typo`） | **判不動（每筆標 unknown）** | — | — |
| 同音別字（`homophone`） | **判不動（每筆標 unknown）** | — | — |
| 中英混合（`mixed_zh_en`） | 可判 | 7 | 7 |
| 純英文（`english_only`） | 可判 | 0 | 0 |
| 語序顛倒（`inverted_word_order`） | **判不動（每筆標 unknown）** | — | — |
| 口語（`colloquial`） | **判不動（每筆標 unknown）** | — | — |
| 多 action（`multi_action`） | 可判 | 2 | 2 |
| 數量（`quantity`） | 可判 | 1 | 1 |
| 工具持有（`tool_handling`） | 可判 | 3 | 3 |
| SIMO／雙手（`simo_both_hands`） | 可判 | 1 | 1 |
| 缺資訊（`missing_info`） | **判不動（每筆標 unknown）** | — | — |
| 歧義（`ambiguity`） | **判不動（每筆標 unknown）** | — | — |
| 依圖示但無圖片（`diagram_reference_no_image`） | 可判 | 0 | 0 |
| 不同 site 用語與匯入髒資料（`site_jargon_dirty_import`） | **判不動（每筆標 unknown）** | — | — |

全形字元細分——全形**英數**：全候選 0／已選 0；全形**標點/空白**：全候選 0／已選 0。

## 覆蓋缺口（需 IE 補寫合成案例或提供真實工單，不硬湊）

- 全形字元（`fullwidth_chars`）：真實資料中 0 筆命中
- 錯字（`typo`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 同音別字（`homophone`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 純英文（`english_only`）：真實資料中 0 筆命中
- 語序顛倒（`inverted_word_order`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 口語（`colloquial`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 缺資訊（`missing_info`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 歧義（`ambiguity`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 依圖示但無圖片（`diagram_reference_no_image`）：真實資料中 0 筆命中
- 不同 site 用語與匯入髒資料（`site_jargon_dirty_import`）：規則式判不動，覆核時 IE 可順手標，或需合成案例

## 預測 action type 分佈（rule planner 預標註，非 ground truth）

| action_type | 筆數 |
|---|---|
| composite_unknown | 37 |
| move_place | 2 |

## 判型（D3-017 動詞字典參與＋D3-023 X/I 參與 GM/CM 判型）

判型吃動詞字典（第三輪 D3-017：M 命中＝CM 訊號、G+P 組合＝GM 訊號；第六輪 D3-023：X/I 命中同為 CM 訊號——X/I 只存在 CM 序列，與 M 同級；衝突矩陣與棄權路徑見 `src/ddm_v2/nlp/rule_based.py` classify_seq）。「舊」欄＝僅名詞觸發詞的第二輪行為（同一函式傳空詞典重算，非手抄數字）：

| 判型 | 舊（僅名詞） | 新（動詞字典參與） |
|---|---|---|
| GM（move_place） | 2 | 2 |
| CM（controlled_move） | 0 | 0 |
| 未定（composite_unknown） | 37 | 37 |

判型變更 **0 筆**（草稿帶 `typing_changed_by_verb_lexicon`＋`typing_change` 舊/新值；覆核表逐筆標「判型已由動詞字典修正，請確認」）：


### 判型仍未定的 37 筆——卡點逐類

- **動詞跨模型混合（M/X/I＋P 同句）→ 棄權（多 cycle 證據，設計如此）**：1 筆
  - `d001_d0350279`：「拿取風槍清潔放置DIMM材料盒的DIMM」
- **句面動詞（部分）未登記——卡 `?` 動詞，IE 裁決後可解**：14 筆
  - `d003_633b52bb`（未登記：掰開）：「雙手掰開DIMM卡槽的卡扣」
  - `d005_35372a96`（未登記：對準）：「拿取排線並對準接頭」
  - `d010_0e83128f`（未登記：下壓）：「下壓 CPU 拉桿鎖定」
  - `d012_cc6c7d56`（未登記：貼上）：「貼上序號標籤」
  - `d014_c82940ca`（未登記：對準）：「精密對準裝配」
  - `d016_1e0d9e15`（未登記：熱壓）：「熱壓導熱膠固化」
  - `d017_e552df5e`（未登記：旋緊）：「旋緊天線接頭」
  - `d018_fe5df381`（未登記：整理）：「整理機殼內線材」
  - `d023_8b6e6aab`（未登記：擦拭）：「擦拭外殼指紋」
  - `d024_553bb598`（未登記：撕開）：「撕開/移除」
  - `d027_debe277a`（未登記：掃描）：「掃描條碼建檔」
  - `d028_ff7166e0`（未登記：掃描）：「掃描/檢查」
  - `d029_00104439`（未登記：按下）：「按下電源測試按鈕」
  - `d039_1a9be08f`（未登記：壓合）：「壓合卡扣」
- **已登記動詞僅 G 或 P 單獨——單一動詞不足以定型**：17 筆
  - `d007_0461f75d`：「拿取 M.2 SSD」
  - `d008_ac155900`：「拿取 DIMM 記憶體模組」
  - `d009_b2618d31`：「小範圍拿取(≤50cm)」
  - `d013_86a61399`：「自料盒拿取主機板」
  - `d019_e55c3e1c`：「放置擋板至機殼後方」
  - `d020_9b7bc11d`：「放置成品入緩衝棧板」
  - `d021_e0c7f95c`：「放置主機板入機殼」
  - `d022_901d1623`：「放置」
  - `d026_60223e3d`：「插入/組裝」
  - `d030_df2af257`：「拿取風扇模組」
  - `d031_3d3c5d8f`：「拿取顯示卡」
  - `d032_b3fe9873`：「拿取電源供應器」
  - `d033_0bc1c188`：「拿取防靜電袋」
  - `d034_bbd33b62`：「拿取出貨外箱」
  - `d035_76590adb`：「拿取側板」
  - `d036_e9064034`：「拿取保護泡棉」
  - `d037_e2d59bc4`：「拿取」
- **句面無動詞面命中——需 IE 改 plan／補描述（非同義詞可解）**：5 筆
  - `d004_8dfafd2e`：「折合上蓋扣合」
  - `d011_995f5d45`：「貼標籤」
  - `d015_850cc7ef`：「移動/走步」
  - `d025_21ccfce2`：「插接線材」
  - `d038_bac1cab6`：「拆箱取件」

### P 方向數（IE 情境規則：機構件→對準 single／盤面→無方向 none；名詞分類單一出處＝`src/ddm_v2/nlp/linking.py`）

- 機構件→`p_place_single`（方向數預設一種，不對請改）：0 筆
- 盤面→`p_place_none`（已套用，請確認）：0 筆
- 判不出→預設 single＋交 IE 裁決：0 筆

## Split 分組（傳遞閉包已算好；同 component 必同 split）

多筆同組（分 split 時必須綁在一起，草稿的 `split_component` 已標）：

- `worksheet:55555555-5555-5555-5555-555555555555`：d004_8dfafd2e、d005_35372a96、d007_0461f75d、d008_ac155900、d010_0e83128f、d012_cc6c7d56、d013_86a61399、d016_1e0d9e15、d017_e552df5e、d018_fe5df381、d019_e55c3e1c、d020_9b7bc11d、d021_e0c7f95c、d023_8b6e6aab、d027_debe277a、d029_00104439、d030_df2af257、d031_3d3c5d8f、d032_b3fe9873、d033_0bc1c188、d034_bbd33b62、d035_76590adb、d036_e9064034

其餘 16 個 component 各只含 1 筆草稿。

## v3 結構回填（D3-014：v3 結構＝IE 的切分裁決；hint 是證據不是判決）

帶切分旗標（配對／likely_multi）的草稿逐筆對回 v3 遷移資料的結構（module/cycle 邊界）；有結構答案的配對題已改為**確認題**（預設依 v3 結構，IE 可推翻），缺失/矛盾者維持開放題：

| 旗標 | 筆數 | single_cycle | multi_cycle_n | ambiguous |
|---|---|---|---|---|
| 取＋放配對（GM） | 0 | 0 | 0 | 0 |
| 取/觸＋推/拉配對（CM） | 0 | 0 | 0 | 0 |
| likely_multi | 2 | 0 | 1 | 1 |

ambiguous 逐筆（維持開放題；矛盾/缺失證據已列在草稿與覆核表）：

- `d005_35372a96`（no_v3_structure_signal）：「拿取排線並對準接頭」

likely_multi 中 **0 筆**因 v3 結構顯示單一 cycle，「幾乎必然低估」警語已對該筆**降級**（覆核表逐筆標示）。

「取必有放」lint（D3-014 裁決 2）：**0 筆**命中 `acquire_without_place`（plan 有 acquire 而同 plan 內其後無收尾；WARN 標給 IE，非 BLOCK——但轉正端要求該筆帶 IE 裁決 `acquire_lint_ruling` ∈ ('placed', 'consumed_by_later_action', 'tool_held', 'genuinely_missing')，其中 `genuinely_missing`（建模錯誤）**不解除**阻擋；plan 已標 `tool_held_for` 者自動推得 `tool_held`，D3-029）。

## IE 覆核狀態合併（review-state.json；--force 重產後存活）

套用 **11 筆**（草稿帶 `ie_review` 區塊；配對鍵＝normalized_text sha256 前 8 碼，與流水號無關）：`d001_d0350279`、`d002_6678c378`、`d003_633b52bb`、`d004_8dfafd2e`、`d005_35372a96`、`d006_4eb2b2e6`、`d007_0461f75d`、`d008_ac155900`、`d009_b2618d31`、`d010_0e83128f`、`d011_995f5d45`

stale：0 筆（所有覆核狀態都配對到內容未變的草稿）。

已轉正（promoted）entry：**52 筆**——跳過合併（句子已在 tests/gold/wi_plans/，不再產草稿；entry 保留為轉正軌跡）：

- `0423b4e8` → `g29_pick_dummy_dimm_hold_to_line`：「左手從料架拿取假DIMM保持住至流水線」
- `0acd56df` → `g07_dimm_latch_press_x16`：「雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置」
- `130bb1ad` → `g48_screw_fix_multi`：「電動鎖附(多顆)」
- `1c27dc35` → `g37_board_to_chassis`：「雙手抓握主板組至機箱」
- `1dd7c1d5` → `g50_press_function_test_fixture`：「按壓功能測試治具」
- `28f9ed7e` → `g55_pick_screw_x1`：「拿取螺絲 x1」
- `2e7b2e5a` → `g52_press_button_template`：「按壓/按鈕」
- `2f0cb396` → `g41_confirm_dimm_points`：「並確認DIMM點位」
- `30d9b858` → `g09_hold_board_to_line`：「雙手抓握主板保持住至流水線」
- `314f0644` → `g19_fixture_handle_to_point`：「左手抓握DIMM壓合治具的把手放至對應的點位」
- `323b04c1` → `g44_screw_fix_single`：「鎖附螺絲」
- `3791550c` → `g46_rh_screw_fix_confirm`：「右手並鎖附固定並確認螺絲到位」
- `37fbd2a6` → `g56_place_heatsink_on_cpu`：「放置散熱片於 CPU 上」
- `3ba13f82` → `g08_hold_driver_to_chassis`：「右手抓握电动起子保持住至機箱」
- `3eab7c3e` → `g13_airgun_clean_slot`：「右手抓握風槍按動按鈕並吹風清潔DIMM卡槽」
- `4765e5f2` → `g23_tear_dummy_dimm_bag`：「右手抓握假DIMM的包裝袋撕除」
- `51077fd1` → `g45_pick_airgun_clean_slot`：「拿取風槍清潔DIMM卡槽」
- `51518399` → `g53_attach_label_to_board_position`：「貼附Label到主板規定位置處」
- `5cb719bb` → `g32_pick_board_debag_place_bench`：「拿取主板，去除包裝袋，將主板放置工作台」
- `5cd079e8` → `g24_board_bag_to_rack`：「左手重新抓握主板的包装袋放至料架」
- `6017ab5e` → `g06_board_to_press_fixture`：「雙手抓握主板放至DIMM壓合治具」
- `631c3ece` → `g26_dimm_box_to_position`：「左手抓握DIMM材料盒放至規定位置處」
- `650ee42f` → `g28_pick_board_hold`：「右手從料架拿取主板保持住」
- `6ae5a84f` → `g21_pull_fixture_base`：「右手接觸DIMM壓合治具的底板拉至對應的點位」
- `6be614c5` → `g51_press_dimm_latch_to_position`：「按壓 DIMM 卡扣到定位」
- `6fa45cdb` → `g31_confirm_points_press_handle`：「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」
- `72dc0511` → `g30_pick_dummy_dimm_debag`：「從料架上拿取假DIMM，去除其包裝袋」
- `7c6eb8af` → `g34_dimm_x16_insert_to_board`：「雙手從DIMM材料盒拿取×16DIMM插入×16至主板」
- `7e40706c` → `g10_push_press_fixture`：「雙手接觸DIMM壓合治具推至規定位置」
- `7f085e02` → `g54_tear_screen_film`：「撕除螢幕保護膜」
- `7ff8b879` → `g47_screw_fix_confirm`：「並鎖附固定並確認螺絲到位」
- `813bca06` → `g16_regrasp_board_to_bench`：「雙手重新抓握主板放至潔淨棚的工作台」
- `8ef772ab` → `g57_lh_pick_screw_from_box`：「左手從螺絲料盒拿取螺絲」
- `9c1a987f` → `g40_dummy_dimm_to_slot_r`：「右手拿取假DIMM組至DIMM卡槽」
- `9f3d6515` → `g14_dimm_latch_press_confirm`：「雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置」
- `a00f4953` → `g12_push_dimm_latches_confirm`：「雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位」
- `a062c017` → `g27_pick_dimm_box_to_bench`：「雙手從料架拿取DIMM材料盒放至潔淨棚的工作台」
- `aa72871a` → `g22_hold_dimm_box`：「左手抓握DIMM材料盒保持住」
- `af172fd9` → `g35_dimm_from_box_to_board`：「雙手從DIMM材料盒拿取DIMM組至主板」
- `b49a90ee` → `g49_dimm_latch_push_x16_confirm`：「雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位」
- `b6ee694d` → `g36_dimm_to_dimm_slot`：「雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)」
- `bc473698` → `g43_screw_board_fix_x6`：「鎖附主機板固定螺絲 x6」
- `c6add069` → `g18_hold_airgun_to_position`：「右手抓握風槍保持住至規定位置處」
- `d58a53a7` → `g25_toss_dimm_bag`：「左手抓握假DIMM的包裝袋丟至垃圾桶」
- `d9190952` → `g11_pull_press_fixture`：「雙手接觸DIMM壓合治具拉至規定位置」
- `e55d16c7` → `g20_attach_label_to_board`：「右手從DIMM材料盒拿取Label貼附至主板」
- `e945e29e` → `g39_dummy_dimm_x16_insert_to_slot`：「右手拿取×16假DIMM插入×16至DIMM卡槽」
- `ee5c168e` → `g42_screw_cpu_heatsink_x4`：「電動起子鎖附 CPU 散熱片螺絲 x4」
- `f721bbfc` → `g17_remove_board_bag`：「左手抓握主板的包装袋去除」
- `f8b21a01` → `g15_airgun_clean_dimm`：「右手抓握風槍按動按鈕並吹風清潔DIMM」
- `fe1f3a90` → `g38_dummy_dimm_to_dimm_slot`：「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」
- `fe5391c6` → `g33_take_board_place_press_fixture`：「拿取主板放置於DIMM壓合治具」

## 未入選候選（0 筆；多樣性選擇額度用罄，非品質淘汰）

coverage-optimized 取樣會把同維度重複的候選排到額度外——以下清單供 IE 檢視是否有應優先的真實案例（用 `--limit` 放寬或手動指定補進下一輪）：


## 已知系統性偏差（也逐筆寫在草稿的 preannotation_caveat）

- rule planner 永遠單 action：2 筆多動作候選的預測切分幾乎必然低估（`likely_multi_action_undercounted`）。
- 另 0 筆是「取＋放」配對（`take_place_pair_may_be_single_gm`）：MiniMOST 的 GM 本來就是 G＋P 同一 cycle，**不預設低估**——IE 逐筆裁決建單一 GM 或兩個 action。
- 另 0 筆是「取/觸＋推/拉」配對（`take_move_pair_may_be_single_cm`）：CM 序列的 G 與 M 本來就在同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2），**不預設低估**——IE 逐筆裁決建單一 CM 或兩個 action。
- `challenge_tags` 的 9 個可判維度：`false` 也是啟發式輸出（`heuristic_tags_unverified` 點名的 quantity/tool_handling/simo_both_hands 已有實證漏標），覆核時 true/false 都要確認。
- 時間戳注意：v3 遷移資料的 DB 時間是**遷移執行時間**（同一天），不是原著作時間——temporal_holdout 不能用現有 created_at 定義，提案見 docs/llm/gold-review/README.md。
