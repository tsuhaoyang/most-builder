# Harvest 摘要 — gold set 擴充候選採集

<!-- 本檔由 scripts/gold_harvest.py 產生（決定性輸出，不含 timestamp） -->

## 來源（唯讀 DB）

| 來源 | 撈得筆數 |
|---|---|
| motion_modules | 42 |
| motion_module_versions.rows[] | 58 |
| wi_rows | 30 |
| motion_templates | 16 |

正規化去重後 unique 候選：**56**；本次選出：**56**（上限 60，多樣性 greedy max-coverage，非取前 N）。

**取樣性質**：coverage-optimized（挑戰維度過採樣），**不是**分佈代表性樣本——在本集合上量到的分數不可外推為生產分佈的表現；分佈代表性指標需另抽隨機樣本。

另有 **36 筆**與正式 gold（tests/gold/wi_plans/）既有案例同句，已排除不重複進草稿：「右手從DIMM材料盒拿取Label貼附至主板」、「右手從料架拿取主板保持住」、「右手抓握假DIMM的包裝袋撕除」、「右手抓握电动起子保持住至機箱」、「右手抓握風槍保持住至規定位置處」、「右手抓握風槍按動按鈕並吹風清潔DIMM」、「右手抓握風槍按動按鈕並吹風清潔DIMM卡槽」、「右手拿取×16假DIMM插入×16至DIMM卡槽」、「右手拿取假DIMM組至DIMM卡槽」、「右手接觸DIMM壓合治具的底板拉至對應的點位」、「左手從料架拿取假DIMM保持住至流水線」、「左手抓握DIMM壓合治具的把手放至對應的點位」、「左手抓握DIMM材料盒保持住」、「左手抓握DIMM材料盒放至規定位置處」、「左手抓握主板的包装袋去除」、「左手抓握假DIMM的包裝袋丟至垃圾桶」、「左手重新抓握主板的包装袋放至料架」、「從料架上拿取假DIMM，去除其包裝袋」、「拿取主板，去除包裝袋，將主板放置工作台」、「拿取主板放置於DIMM壓合治具」、「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」、「拿取電動起子，依圖示鎖附兩顆螺絲」、「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」、「雙手從DIMM材料盒拿取DIMM組至主板」、「雙手從DIMM材料盒拿取×16DIMM插入×16至主板」、「雙手從料架拿取DIMM材料盒放至潔淨棚的工作台」、「雙手抓握主板保持住至流水線」、「雙手抓握主板放至DIMM壓合治具」、「雙手抓握主板組至機箱」、「雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)」、「雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置」、「雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位」、「雙手接觸DIMM壓合治具拉至規定位置」、「雙手接觸DIMM壓合治具推至規定位置」、「雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置」、「雙手重新抓握主板放至潔淨棚的工作台」。

詞典（rule_option_synonyms @ MINIMOST_FACTORY_V2）：**22 條**。

Cycle 完成度：**5／56 筆**至少一個 cycle complete 帶 TMU（TMU 唯一出處＝most_engine）；其餘 51 筆全部 incomplete（缺 slot 候選或判型未定——逐筆原因見草稿 `expected_cycles[].issues_contain`）。

**誠實旗標**：complete 之中 **2 筆 TMU＝0.0**（`d003_51518399`、`d038_7f085e02`）——引擎口徑下距離未述＝0cm（M 階梯 0→0）且核心參數以外的 slot（如 CM 的 G、GM 的 G）未由 linker 掛值（per-action linking 只掛 core 參數）。complete≠可信 TMU：TMU=0.0 非真值——每筆已掛 `zero_tmu_distance_unstated` 旗標，覆核表逐筆問「補距離或判定句子資訊不足」；原樣轉正會撞空殼守門（total_tmu > 0 或顯式 expected_incomplete_reason）。

## 挑戰維度覆蓋（spec §14.3 的 16 維度）

| 維度 | 規則式可判？ | 全候選命中 | 已選命中 |
|---|---|---|---|
| 繁簡（簡體字/大陸用語）（`zh_simplified_variant`） | 可判 | 2 | 2 |
| 全形字元（`fullwidth_chars`） | 可判 | 0 | 0 |
| 錯字（`typo`） | **判不動（每筆標 unknown）** | — | — |
| 同音別字（`homophone`） | **判不動（每筆標 unknown）** | — | — |
| 中英混合（`mixed_zh_en`） | 可判 | 16 | 16 |
| 純英文（`english_only`） | 可判 | 0 | 0 |
| 語序顛倒（`inverted_word_order`） | **判不動（每筆標 unknown）** | — | — |
| 口語（`colloquial`） | **判不動（每筆標 unknown）** | — | — |
| 多 action（`multi_action`） | 可判 | 6 | 6 |
| 數量（`quantity`） | 可判 | 5 | 5 |
| 工具持有（`tool_handling`） | 可判 | 6 | 6 |
| SIMO／雙手（`simo_both_hands`） | 可判 | 2 | 2 |
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
| composite_unknown | 40 |
| controlled_move | 14 |
| move_place | 2 |

## 判型（D3-017 動詞字典參與＋D3-023 X/I 參與 GM/CM 判型）

判型吃動詞字典（第三輪 D3-017：M 命中＝CM 訊號、G+P 組合＝GM 訊號；第六輪 D3-023：X/I 命中同為 CM 訊號——X/I 只存在 CM 序列，與 M 同級；衝突矩陣與棄權路徑見 `src/ddm_v2/nlp/rule_based.py` classify_seq）。「舊」欄＝僅名詞觸發詞的第二輪行為（同一函式傳空詞典重算，非手抄數字）：

| 判型 | 舊（僅名詞） | 新（動詞字典參與） |
|---|---|---|
| GM（move_place） | 3 | 2 |
| CM（controlled_move） | 0 | 14 |
| 未定（composite_unknown） | 53 | 40 |

判型變更 **14 筆**（草稿帶 `typing_changed_by_verb_lexicon`＋`typing_change` 舊/新值；覆核表逐筆標「判型已由動詞字典修正，請確認」）：

- `d001_b49a90ee`：未定（composite_unknown） → CM（控制移動）——「雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位」
- `d002_ee5c168e`：未定（composite_unknown） → CM（控制移動）——「電動起子鎖附 CPU 散熱片螺絲 x4」
- `d003_51518399`：未定（composite_unknown） → CM（控制移動）——「貼附Label到主板規定位置處」
- `d005_51077fd1`：未定（composite_unknown） → CM（控制移動）——「拿取風槍清潔DIMM卡槽」
- `d009_bc473698`：未定（composite_unknown） → CM（控制移動）——「鎖附主機板固定螺絲 x6」
- `d012_1dd7c1d5`：GM（一般移動） → CM（控制移動）——「按壓功能測試治具」
- `d013_3791550c`：未定（composite_unknown） → CM（控制移動）——「右手並鎖附固定並確認螺絲到位」
- `d015_7ff8b879`：未定（composite_unknown） → CM（控制移動）——「並鎖附固定並確認螺絲到位」
- `d017_6be614c5`：未定（composite_unknown） → CM（控制移動）——「按壓 DIMM 卡扣到定位」
- `d021_2f0cb396`：未定（composite_unknown） → CM（控制移動）——「並確認DIMM點位」
- `d023_130bb1ad`：未定（composite_unknown） → CM（控制移動）——「電動鎖附(多顆)」
- `d024_323b04c1`：未定（composite_unknown） → CM（控制移動）——「鎖附螺絲」
- `d038_7f085e02`：未定（composite_unknown） → CM（控制移動）——「撕除螢幕保護膜」
- `d044_2e7b2e5a`：未定（composite_unknown） → CM（控制移動）——「按壓/按鈕」

### 判型仍未定的 40 筆——卡點逐類

- **動詞跨模型混合（M/X/I＋P 同句）→ 棄權（多 cycle 證據，設計如此）**：1 筆
  - `d004_d0350279`：「拿取風槍清潔放置DIMM材料盒的DIMM」
- **句面動詞（部分）未登記——卡 `?` 動詞，IE 裁決後可解**：14 筆
  - `d007_633b52bb`（未登記：掰開）：「雙手掰開DIMM卡槽的卡扣」
  - `d011_35372a96`（未登記：對準）：「拿取排線並對準接頭」
  - `d022_0e83128f`（未登記：下壓）：「下壓 CPU 拉桿鎖定」
  - `d026_cc6c7d56`（未登記：貼上）：「貼上序號標籤」
  - `d028_c82940ca`（未登記：對準）：「精密對準裝配」
  - `d030_1e0d9e15`（未登記：熱壓）：「熱壓導熱膠固化」
  - `d031_e552df5e`（未登記：旋緊）：「旋緊天線接頭」
  - `d032_fe5df381`（未登記：整理）：「整理機殼內線材」
  - `d037_8b6e6aab`（未登記：擦拭）：「擦拭外殼指紋」
  - `d039_553bb598`（未登記：撕開）：「撕開/移除」
  - `d042_debe277a`（未登記：掃描）：「掃描條碼建檔」
  - `d043_ff7166e0`（未登記：掃描）：「掃描/檢查」
  - `d045_00104439`（未登記：按下）：「按下電源測試按鈕」
  - `d056_1a9be08f`（未登記：壓合）：「壓合卡扣」
- **已登記動詞僅 G 或 P 單獨——單一動詞不足以定型**：20 筆
  - `d010_28f9ed7e`：「拿取螺絲 x1」
  - `d016_37fbd2a6`：「放置散熱片於 CPU 上」
  - `d018_0461f75d`：「拿取 M.2 SSD」
  - `d019_ac155900`：「拿取 DIMM 記憶體模組」
  - `d020_b2618d31`：「小範圍拿取(≤50cm)」
  - `d027_86a61399`：「自料盒拿取主機板」
  - `d033_e55c3e1c`：「放置擋板至機殼後方」
  - `d034_9b7bc11d`：「放置成品入緩衝棧板」
  - `d035_e0c7f95c`：「放置主機板入機殼」
  - `d036_901d1623`：「放置」
  - `d041_60223e3d`：「插入/組裝」
  - `d046_df2af257`：「拿取風扇模組」
  - `d047_3d3c5d8f`：「拿取顯示卡」
  - `d048_b3fe9873`：「拿取電源供應器」
  - `d049_0bc1c188`：「拿取防靜電袋」
  - `d050_bbd33b62`：「拿取出貨外箱」
  - `d051_76590adb`：「拿取側板」
  - `d052_e9064034`：「拿取保護泡棉」
  - `d053_e2d59bc4`：「拿取」
  - `d055_8ef772ab`：「左手從螺絲料盒拿取螺絲」
- **句面無動詞面命中——需 IE 改 plan／補描述（非同義詞可解）**：5 筆
  - `d008_8dfafd2e`：「折合上蓋扣合」
  - `d025_995f5d45`：「貼標籤」
  - `d029_850cc7ef`：「移動/走步」
  - `d040_21ccfce2`：「插接線材」
  - `d054_bac1cab6`：「拆箱取件」

### P 方向數（IE 情境規則：機構件→對準 single／盤面→無方向 none；名詞分類單一出處＝`src/ddm_v2/nlp/linking.py`）

- 機構件→`p_place_single`（方向數預設一種，不對請改）：0 筆
- 盤面→`p_place_none`（已套用，請確認）：0 筆
- 判不出→預設 single＋交 IE 裁決：0 筆

## Split 分組（傳遞閉包已算好；同 component 必同 split）

多筆同組（分 split 時必須綁在一起，草稿的 `split_component` 已標）：

- `module:03ceef7d-5939-4ccc-a57c-da17e06e94de`：d006_6678c378、d021_2f0cb396
- `module:1c0e39ae-abd0-42db-a277-c6490b1c8f78`：d013_3791550c、d055_8ef772ab
- `module:945b0420-3367-42e9-90d0-00993cf80ff5`：d001_b49a90ee、d007_633b52bb
- `worksheet:55555555-5555-5555-5555-555555555555`：d002_ee5c168e、d008_8dfafd2e、d009_bc473698、d010_28f9ed7e、d011_35372a96、d012_1dd7c1d5、d016_37fbd2a6、d017_6be614c5、d018_0461f75d、d019_ac155900、d022_0e83128f、d026_cc6c7d56、d027_86a61399、d030_1e0d9e15、d031_e552df5e、d032_fe5df381、d033_e55c3e1c、d034_9b7bc11d、d035_e0c7f95c、d037_8b6e6aab、d038_7f085e02、d042_debe277a、d045_00104439、d046_df2af257、d047_3d3c5d8f、d048_b3fe9873、d049_0bc1c188、d050_bbd33b62、d051_76590adb、d052_e9064034

其餘 20 個 component 各只含 1 筆草稿。

## v3 結構回填（D3-014：v3 結構＝IE 的切分裁決；hint 是證據不是判決）

帶切分旗標（配對／likely_multi）的草稿逐筆對回 v3 遷移資料的結構（module/cycle 邊界）；有結構答案的配對題已改為**確認題**（預設依 v3 結構，IE 可推翻），缺失/矛盾者維持開放題：

| 旗標 | 筆數 | single_cycle | multi_cycle_n | ambiguous |
|---|---|---|---|---|
| 取＋放配對（GM） | 0 | 0 | 0 | 0 |
| 取/觸＋推/拉配對（CM） | 0 | 0 | 0 | 0 |
| likely_multi | 6 | 4 | 1 | 1 |

ambiguous 逐筆（維持開放題；矛盾/缺失證據已列在草稿與覆核表）：

- `d011_35372a96`（no_v3_structure_signal）：「拿取排線並對準接頭」

likely_multi 中 **4 筆**因 v3 結構顯示單一 cycle，「幾乎必然低估」警語已對該筆**降級**（覆核表逐筆標示）。

「取必有放」lint（D3-014 裁決 2）：**0 筆**命中 `acquire_without_place`（plan 有 acquire 而同 plan 內其後無收尾；WARN 標給 IE，非 BLOCK）。

## IE 覆核狀態合併（review-state.json；--force 重產後存活）

套用 **26 筆**（草稿帶 `ie_review` 區塊；配對鍵＝normalized_text sha256 前 8 碼，與流水號無關）：`d001_b49a90ee`、`d002_ee5c168e`、`d003_51518399`、`d005_51077fd1`、`d006_6678c378`、`d007_633b52bb`、`d008_8dfafd2e`、`d009_bc473698`、`d010_28f9ed7e`、`d011_35372a96`、`d012_1dd7c1d5`、`d013_3791550c`、`d014_4eb2b2e6`、`d015_7ff8b879`、`d016_37fbd2a6`、`d017_6be614c5`、`d018_0461f75d`、`d019_ac155900`、`d020_b2618d31`、`d021_2f0cb396`、`d022_0e83128f`、`d023_130bb1ad`、`d024_323b04c1`、`d025_995f5d45`、`d038_7f085e02`、`d044_2e7b2e5a`

**⚠️ stale 1 筆——未套用**（狀態所依據的內容已變，不靜默沿用；IE 需重看後更新 state 檔）：

- `d0350279`（typing_change_changed）：「拿取風槍清潔放置DIMM材料盒的DIMM」

已轉正（promoted）entry：**35 筆**——跳過合併（句子已在 tests/gold/wi_plans/，不再產草稿；entry 保留為轉正軌跡）：

- `0423b4e8` → `g29_pick_dummy_dimm_hold_to_line`：「左手從料架拿取假DIMM保持住至流水線」
- `0acd56df` → `g07_dimm_latch_press_x16`：「雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置」
- `1c27dc35` → `g37_board_to_chassis`：「雙手抓握主板組至機箱」
- `30d9b858` → `g09_hold_board_to_line`：「雙手抓握主板保持住至流水線」
- `314f0644` → `g19_fixture_handle_to_point`：「左手抓握DIMM壓合治具的把手放至對應的點位」
- `3ba13f82` → `g08_hold_driver_to_chassis`：「右手抓握电动起子保持住至機箱」
- `3eab7c3e` → `g13_airgun_clean_slot`：「右手抓握風槍按動按鈕並吹風清潔DIMM卡槽」
- `4765e5f2` → `g23_tear_dummy_dimm_bag`：「右手抓握假DIMM的包裝袋撕除」
- `5cb719bb` → `g32_pick_board_debag_place_bench`：「拿取主板，去除包裝袋，將主板放置工作台」
- `5cd079e8` → `g24_board_bag_to_rack`：「左手重新抓握主板的包装袋放至料架」
- `6017ab5e` → `g06_board_to_press_fixture`：「雙手抓握主板放至DIMM壓合治具」
- `631c3ece` → `g26_dimm_box_to_position`：「左手抓握DIMM材料盒放至規定位置處」
- `650ee42f` → `g28_pick_board_hold`：「右手從料架拿取主板保持住」
- `6ae5a84f` → `g21_pull_fixture_base`：「右手接觸DIMM壓合治具的底板拉至對應的點位」
- `6fa45cdb` → `g31_confirm_points_press_handle`：「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」
- `72dc0511` → `g30_pick_dummy_dimm_debag`：「從料架上拿取假DIMM，去除其包裝袋」
- `7c6eb8af` → `g34_dimm_x16_insert_to_board`：「雙手從DIMM材料盒拿取×16DIMM插入×16至主板」
- `7e40706c` → `g10_push_press_fixture`：「雙手接觸DIMM壓合治具推至規定位置」
- `813bca06` → `g16_regrasp_board_to_bench`：「雙手重新抓握主板放至潔淨棚的工作台」
- `9c1a987f` → `g40_dummy_dimm_to_slot_r`：「右手拿取假DIMM組至DIMM卡槽」
- `9f3d6515` → `g14_dimm_latch_press_confirm`：「雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置」
- `a00f4953` → `g12_push_dimm_latches_confirm`：「雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位」
- `a062c017` → `g27_pick_dimm_box_to_bench`：「雙手從料架拿取DIMM材料盒放至潔淨棚的工作台」
- `aa72871a` → `g22_hold_dimm_box`：「左手抓握DIMM材料盒保持住」
- `af172fd9` → `g35_dimm_from_box_to_board`：「雙手從DIMM材料盒拿取DIMM組至主板」
- `b6ee694d` → `g36_dimm_to_dimm_slot`：「雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)」
- `c6add069` → `g18_hold_airgun_to_position`：「右手抓握風槍保持住至規定位置處」
- `d58a53a7` → `g25_toss_dimm_bag`：「左手抓握假DIMM的包裝袋丟至垃圾桶」
- `d9190952` → `g11_pull_press_fixture`：「雙手接觸DIMM壓合治具拉至規定位置」
- `e55d16c7` → `g20_attach_label_to_board`：「右手從DIMM材料盒拿取Label貼附至主板」
- `e945e29e` → `g39_dummy_dimm_x16_insert_to_slot`：「右手拿取×16假DIMM插入×16至DIMM卡槽」
- `f721bbfc` → `g17_remove_board_bag`：「左手抓握主板的包装袋去除」
- `f8b21a01` → `g15_airgun_clean_dimm`：「右手抓握風槍按動按鈕並吹風清潔DIMM」
- `fe1f3a90` → `g38_dummy_dimm_to_dimm_slot`：「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」
- `fe5391c6` → `g33_take_board_place_press_fixture`：「拿取主板放置於DIMM壓合治具」

## 未入選候選（0 筆；多樣性選擇額度用罄，非品質淘汰）

coverage-optimized 取樣會把同維度重複的候選排到額度外——以下清單供 IE 檢視是否有應優先的真實案例（用 `--limit` 放寬或手動指定補進下一輪）：


## 已知系統性偏差（也逐筆寫在草稿的 preannotation_caveat）

- rule planner 永遠單 action：6 筆多動作候選的預測切分幾乎必然低估（`likely_multi_action_undercounted`）。
- 另 0 筆是「取＋放」配對（`take_place_pair_may_be_single_gm`）：MiniMOST 的 GM 本來就是 G＋P 同一 cycle，**不預設低估**——IE 逐筆裁決建單一 GM 或兩個 action。
- 另 0 筆是「取/觸＋推/拉」配對（`take_move_pair_may_be_single_cm`）：CM 序列的 G 與 M 本來就在同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2），**不預設低估**——IE 逐筆裁決建單一 CM 或兩個 action。
- `challenge_tags` 的 9 個可判維度：`false` 也是啟發式輸出（`heuristic_tags_unverified` 點名的 quantity/tool_handling/simo_both_hands 已有實證漏標），覆核時 true/false 都要確認。
- 時間戳注意：v3 遷移資料的 DB 時間是**遷移執行時間**（同一天），不是原著作時間——temporal_holdout 不能用現有 created_at 定義，提案見 docs/llm/gold-review/README.md。
