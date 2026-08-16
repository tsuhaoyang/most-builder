# Harvest 摘要 — gold set 擴充候選採集

<!-- 本檔由 scripts/gold_harvest.py 產生（決定性輸出，不含 timestamp） -->

## 來源（唯讀 DB）

| 來源 | 撈得筆數 |
|---|---|
| motion_modules | 42 |
| motion_module_versions.rows[] | 58 |
| wi_rows | 30 |
| motion_templates | 16 |

正規化去重後 unique 候選：**91**；本次選出：**60**（上限 60，多樣性 greedy max-coverage，非取前 N）。

**取樣性質**：coverage-optimized（挑戰維度過採樣），**不是**分佈代表性樣本——在本集合上量到的分數不可外推為生產分佈的表現；分佈代表性指標需另抽隨機樣本。

另有 **1 筆**與正式 gold（tests/gold/wi_plans/）既有案例同句，已排除不重複進草稿：「拿取電動起子，依圖示鎖附兩顆螺絲」。

詞典（rule_option_synonyms @ MINIMOST_FACTORY_V2）：**15 條**。

Cycle 完成度：**27／60 筆**至少一個 cycle complete 帶 TMU（TMU 唯一出處＝most_engine）；其餘 33 筆全部 incomplete（缺 slot 候選或判型未定——逐筆原因見草稿 `expected_cycles[].issues_contain`）。

**誠實旗標**：complete 之中 **9 筆 TMU＝0.0**（`d008_72dc0511`、`d011_7e40706c`、`d019_d9190952`、`d020_a00f4953`、`d027_f721bbfc`、`d033_51518399`、`d035_e55d16c7`、`d037_6ae5a84f`、`d040_4765e5f2`）——引擎口徑下距離未述＝0cm（M 階梯 0→0）且核心參數以外的 slot（如 CM 的 G、GM 的 G）未由 linker 掛值（per-action linking 只掛 core 參數）。complete≠可信 TMU：TMU=0.0 非真值——每筆已掛 `zero_tmu_distance_unstated` 旗標，覆核表逐筆問「補距離或判定句子資訊不足」；原樣轉正會撞空殼守門（total_tmu > 0 或顯式 expected_incomplete_reason）。

## 挑戰維度覆蓋（spec §14.3 的 16 維度）

| 維度 | 規則式可判？ | 全候選命中 | 已選命中 |
|---|---|---|---|
| 繁簡（簡體字/大陸用語）（`zh_simplified_variant`） | 可判 | 16 | 16 |
| 全形字元（`fullwidth_chars`） | 可判 | 3 | 3 |
| 錯字（`typo`） | **判不動（每筆標 unknown）** | — | — |
| 同音別字（`homophone`） | **判不動（每筆標 unknown）** | — | — |
| 中英混合（`mixed_zh_en`） | 可判 | 42 | 42 |
| 純英文（`english_only`） | 可判 | 0 | 0 |
| 語序顛倒（`inverted_word_order`） | **判不動（每筆標 unknown）** | — | — |
| 口語（`colloquial`） | **判不動（每筆標 unknown）** | — | — |
| 多 action（`multi_action`） | 可判 | 22 | 22 |
| 數量（`quantity`） | 可判 | 11 | 11 |
| 工具持有（`tool_handling`） | 可判 | 17 | 17 |
| SIMO／雙手（`simo_both_hands`） | 可判 | 15 | 15 |
| 缺資訊（`missing_info`） | **判不動（每筆標 unknown）** | — | — |
| 歧義（`ambiguity`） | **判不動（每筆標 unknown）** | — | — |
| 依圖示但無圖片（`diagram_reference_no_image`） | 可判 | 0 | 0 |
| 不同 site 用語與匯入髒資料（`site_jargon_dirty_import`） | **判不動（每筆標 unknown）** | — | — |

全形字元細分——全形**英數**：全候選 0／已選 0；全形**標點/空白**：全候選 3／已選 3。

## 覆蓋缺口（需 IE 補寫合成案例或提供真實工單，不硬湊）

- 錯字（`typo`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 同音別字（`homophone`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 純英文（`english_only`）：真實資料中 0 筆命中
- 語序顛倒（`inverted_word_order`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 口語（`colloquial`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 缺資訊（`missing_info`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 歧義（`ambiguity`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 依圖示但無圖片（`diagram_reference_no_image`）：真實資料中 0 筆命中
- 不同 site 用語與匯入髒資料（`site_jargon_dirty_import`）：規則式判不動，覆核時 IE 可順手標，或需合成案例
- 全形英數（`fullwidth_chars` 細分）：0 筆命中——現有 fullwidth 命中全是標點，全形英數（ＡＢＣ／０１２）視為未覆蓋

## 預測 action type 分佈（rule planner 預標註，非 ground truth）

| action_type | 筆數 |
|---|---|
| composite_unknown | 31 |
| controlled_move | 16 |
| move_place | 13 |

## 第三輪判型（D3-017：動詞字典參與 GM/CM 判型）

判型自本輪起吃動詞字典（M 命中＝CM 訊號、G+P 組合＝GM 訊號；衝突矩陣與棄權路徑見 `src/ddm_v2/nlp/rule_based.py` classify_seq）。「舊」欄＝僅名詞觸發詞的第二輪行為（同一函式傳空詞典重算，非手抄數字）：

| 判型 | 舊（僅名詞） | 新（動詞字典參與） |
|---|---|---|
| GM（move_place） | 10 | 13 |
| CM（controlled_move） | 0 | 16 |
| 未定（composite_unknown） | 50 | 31 |

判型變更 **24 筆**（草稿帶 `typing_changed_by_verb_lexicon`＋`typing_change` 舊/新值；覆核表逐筆標「第三輪判型已修正，請確認」）：

- `d001_6fa45cdb`：GM（一般移動） → CM（控制移動）——「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」
- `d003_0acd56df`：未定（composite_unknown） → CM（控制移動）——「雙手接觸×16DIMM卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置」
- `d007_3ba13f82`：未定（composite_unknown） → GM（一般移動）——「右手抓握电动起子保持住至機箱」
- `d008_72dc0511`：未定（composite_unknown） → CM（控制移動）——「從料架上拿取假DIMM，去除其包裝袋」
- `d010_30d9b858`：未定（composite_unknown） → GM（一般移動）——「雙手抓握主板保持住至流水線」
- `d011_7e40706c`：GM（一般移動） → CM（控制移動）——「雙手接觸DIMM壓合治具推至規定位置」
- `d019_d9190952`：GM（一般移動） → CM（控制移動）——「雙手接觸DIMM壓合治具拉至規定位置」
- `d020_a00f4953`：未定（composite_unknown） → CM（控制移動）——「雙手接觸DIMM卡槽的左右卡扣推至規定位置並確認到位」
- `d021_3eab7c3e`：未定（composite_unknown） → CM（控制移動）——「右手抓握風槍按動按鈕並吹風清潔DIMM卡槽」
- `d022_9f3d6515`：未定（composite_unknown） → CM（控制移動）——「雙手接觸DIMM卡槽的左右卡扣按壓並確認卡扣按壓規定位置」
- `d023_f8b21a01`：未定（composite_unknown） → CM（控制移動）——「右手抓握風槍按動按鈕並吹風清潔DIMM」
- `d024_813bca06`：未定（composite_unknown） → GM（一般移動）——「雙手重新抓握主板放至潔淨棚的工作台」
- `d027_f721bbfc`：未定（composite_unknown） → CM（控制移動）——「左手抓握主板的包装袋去除」
- `d031_c6add069`：未定（composite_unknown） → GM（一般移動）——「右手抓握風槍保持住至規定位置處」
- `d033_51518399`：未定（composite_unknown） → CM（控制移動）——「貼附Label到主板規定位置處」
- `d035_e55d16c7`：未定（composite_unknown） → CM（控制移動）——「右手從DIMM材料盒拿取Label貼附至主板」
- `d037_6ae5a84f`：GM（一般移動） → CM（控制移動）——「右手接觸DIMM壓合治具的底板拉至對應的點位」
- `d038_aa72871a`：未定（composite_unknown） → GM（一般移動）——「左手抓握DIMM材料盒保持住」
- `d040_4765e5f2`：未定（composite_unknown） → CM（控制移動）——「右手抓握假DIMM的包裝袋撕除」
- `d042_1dd7c1d5`：GM（一般移動） → CM（控制移動）——「按壓功能測試治具」
- `d043_5cd079e8`：未定（composite_unknown） → GM（一般移動）——「左手重新抓握主板的包装袋放至料架」
- `d049_6be614c5`：未定（composite_unknown） → CM（控制移動）——「按壓 DIMM 卡扣到定位」
- `d052_d58a53a7`：未定（composite_unknown） → GM（一般移動）——「左手抓握假DIMM的包裝袋丟至垃圾桶」
- `d053_631c3ece`：未定（composite_unknown） → GM（一般移動）——「左手抓握DIMM材料盒放至規定位置處」

### 判型仍未定的 31 筆——卡點逐類

- **動詞跨模型混合（M＋P 同句）→ 棄權（多 cycle 證據，設計如此）**：1 筆
  - `d005_5cb719bb`：「拿取主板，去除包裝袋，將主板放置工作台」
- **句面動詞（部分）未登記——卡 `?` 動詞，IE 裁決後可解**：27 筆
  - `d004_7c6eb8af`（未登記：拿取、插入）：「雙手從DIMM材料盒拿取×16DIMM插入×16至主板」
  - `d006_b49a90ee`（未登記：確認）：「雙手接觸DIMM卡槽的左右卡扣推×16至規定位置並確認到位」
  - `d009_ee5c168e`（未登記：鎖附）：「電動起子鎖附 CPU 散熱片螺絲 x4」
  - `d013_b6ee694d`（未登記：拿取、組於）：「雙手拿取DIMM組於DIMM卡槽 (依據配置要求-16個DIMM)」
  - `d015_a062c017`（未登記：拿取）：「雙手從料架拿取DIMM材料盒放至潔淨棚的工作台」
  - `d016_d0350279`（未登記：拿取、清潔）：「拿取風槍清潔放置DIMM材料盒的DIMM」
  - `d017_af172fd9`（未登記：拿取、組至）：「雙手從DIMM材料盒拿取DIMM組至主板」
  - `d018_51077fd1`（未登記：拿取、清潔）：「拿取風槍清潔DIMM卡槽」
  - `d025_bc473698`（未登記：鎖附）：「鎖附主機板固定螺絲 x6」
  - `d026_1c27dc35`（未登記：組至）：「雙手抓握主板組至機箱」
  - `d028_28f9ed7e`（未登記：拿取）：「拿取螺絲 x1」
  - `d029_650ee42f`（未登記：拿取）：「右手從料架拿取主板保持住」
  - `d030_fe1f3a90`（未登記：拿取、組於）：「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」
  - `d032_e945e29e`（未登記：拿取、插入）：「右手拿取×16假DIMM插入×16至DIMM卡槽」
  - `d036_633b52bb`（未登記：掰開）：「雙手掰開DIMM卡槽的卡扣」
  - `d039_0423b4e8`（未登記：拿取）：「左手從料架拿取假DIMM保持住至流水線」
  - `d045_35372a96`（未登記：對準、拿取）：「拿取排線並對準接頭」
  - `d046_3791550c`（未登記：確認、鎖附）：「右手並鎖附固定並確認螺絲到位」
  - `d047_7ff8b879`（未登記：確認、鎖附）：「並鎖附固定並確認螺絲到位」
  - `d050_0461f75d`（未登記：拿取）：「拿取 M.2 SSD」
  - `d051_ac155900`（未登記：拿取）：「拿取 DIMM 記憶體模組」
  - `d054_b2618d31`（未登記：拿取）：「小範圍拿取(≤50cm)」
  - `d055_9c1a987f`（未登記：拿取、組至）：「右手拿取假DIMM組至DIMM卡槽」
  - `d056_2f0cb396`（未登記：確認）：「並確認DIMM點位」
  - `d057_0e83128f`（未登記：下壓）：「下壓 CPU 拉桿鎖定」
  - `d058_130bb1ad`（未登記：鎖附）：「電動鎖附(多顆)」
  - `d059_323b04c1`（未登記：鎖附）：「鎖附螺絲」
- **已登記動詞僅 G 或 P 單獨——單一動詞不足以定型**：1 筆
  - `d048_37fbd2a6`：「放置散熱片於 CPU 上」
- **句面無動詞面命中——需 IE 改 plan／補描述（非同義詞可解）**：2 筆
  - `d041_8dfafd2e`：「折合上蓋扣合」
  - `d060_995f5d45`：「貼標籤」

### P 方向數（IE 情境規則：機構件→對準 single／盤面→無方向 none；名詞分類單一出處＝`src/ddm_v2/nlp/linking.py`）

- 機構件→`p_place_single`（方向數預設一種，不對請改）：3 筆
- 盤面→`p_place_none`（已套用，請確認）：2 筆
- 判不出→預設 single＋交 IE 裁決：1 筆

## Split 分組（傳遞閉包已算好；同 component 必同 split）

多筆同組（分 split 時必須綁在一起，草稿的 `split_component` 已標）：

- `module:03ceef7d-5939-4ccc-a57c-da17e06e94de`：d001_6fa45cdb、d014_6678c378、d037_6ae5a84f、d056_2f0cb396
- `module:0c944bee-3c4f-4e72-a071-2b45c118a6af`：d015_a062c017、d016_d0350279、d023_f8b21a01、d031_c6add069、d038_aa72871a、d053_631c3ece
- `module:12ce967e-4c91-4b5d-b2a7-a41a317a1dc1`：d004_7c6eb8af、d013_b6ee694d
- `module:2b73646b-bfb4-43aa-a610-9c21f6543776`：d008_72dc0511、d039_0423b4e8、d040_4765e5f2
- `module:2ea27e92-e4e5-4a67-91c5-a1b1359c96b9`：d007_3ba13f82、d046_3791550c
- `module:310981d5-6069-4303-9c05-38dc618e0b74`：d002_6017ab5e、d011_7e40706c、d012_fe5391c6
- `module:32a29bba-fabe-4332-baee-9785d4c2525d`：d010_30d9b858、d019_d9190952、d026_1c27dc35
- `module:39a7b9db-6453-4898-b1a3-9df0b3bacaac`：d018_51077fd1、d021_3eab7c3e
- `module:45915347-cc29-4ee1-a4c7-e696d05cdd7a`：d003_0acd56df、d022_9f3d6515
- `module:6366f744-6791-4e84-a3ac-5305d4f07679`：d030_fe1f3a90、d032_e945e29e、d052_d58a53a7
- `module:8436a0d0-da56-4eee-818a-b1c9bff29f44`：d005_5cb719bb、d024_813bca06、d027_f721bbfc、d029_650ee42f、d043_5cd079e8
- `module:945b0420-3367-42e9-90d0-00993cf80ff5`：d006_b49a90ee、d036_633b52bb
- `module:9f61331e-fe42-430a-8311-63960bda302f`：d033_51518399、d035_e55d16c7
- `worksheet:55555555-5555-5555-5555-555555555555`：d009_ee5c168e、d025_bc473698、d028_28f9ed7e、d041_8dfafd2e、d042_1dd7c1d5、d045_35372a96、d048_37fbd2a6、d049_6be614c5、d050_0461f75d、d051_ac155900、d057_0e83128f

其餘 10 個 component 各只含 1 筆草稿。

## v3 結構回填（D3-014：v3 結構＝IE 的切分裁決；hint 是證據不是判決）

帶切分旗標（配對／likely_multi）的草稿逐筆對回 v3 遷移資料的結構（module/cycle 邊界）；有結構答案的配對題已改為**確認題**（預設依 v3 結構，IE 可推翻），缺失/矛盾者維持開放題：

| 旗標 | 筆數 | single_cycle | multi_cycle_n | ambiguous |
|---|---|---|---|---|
| 取＋放配對（GM） | 16 | 13 | 2 | 1 |
| 取/觸＋推/拉配對（CM） | 3 | 3 | 0 | 0 |
| likely_multi | 22 | 17 | 4 | 1 |

ambiguous 逐筆（維持開放題；矛盾/缺失證據已列在草稿與覆核表）：

- `d026_1c27dc35`（conflicting_v3_structures）：「雙手抓握主板組至機箱」
- `d045_35372a96`（no_v3_structure_signal）：「拿取排線並對準接頭」

likely_multi 中 **17 筆**因 v3 結構顯示單一 cycle，「幾乎必然低估」警語已對該筆**降級**（覆核表逐筆標示）。

「取必有放」lint（D3-014 裁決 2）：**0 筆**命中 `acquire_without_place`（plan 有 acquire 而同 plan 內其後無收尾；WARN 標給 IE，非 BLOCK）。

## IE 覆核狀態合併（review-state.json；--force 重產後存活）

套用 **41 筆**（草稿帶 `ie_review` 區塊；配對鍵＝normalized_text sha256 前 8 碼，與流水號無關）：`d001_6fa45cdb`、`d002_6017ab5e`、`d003_0acd56df`、`d004_7c6eb8af`、`d005_5cb719bb`、`d006_b49a90ee`、`d007_3ba13f82`、`d008_72dc0511`、`d010_30d9b858`、`d011_7e40706c`、`d012_fe5391c6`、`d013_b6ee694d`、`d015_a062c017`、`d016_d0350279`、`d017_af172fd9`、`d018_51077fd1`、`d019_d9190952`、`d020_a00f4953`、`d021_3eab7c3e`、`d022_9f3d6515`、`d023_f8b21a01`、`d024_813bca06`、`d026_1c27dc35`、`d027_f721bbfc`、`d029_650ee42f`、`d030_fe1f3a90`、`d031_c6add069`、`d032_e945e29e`、`d034_314f0644`、`d035_e55d16c7`、`d037_6ae5a84f`、`d038_aa72871a`、`d039_0423b4e8`、`d040_4765e5f2`、`d043_5cd079e8`、`d045_35372a96`、`d046_3791550c`、`d047_7ff8b879`、`d052_d58a53a7`、`d053_631c3ece`、`d055_9c1a987f`

stale：0 筆（所有覆核狀態都配對到內容未變的草稿）。

## 未入選候選（31 筆；多樣性選擇額度用罄，非品質淘汰）

coverage-optimized 取樣會把同維度重複的候選排到額度外——以下清單供 IE 檢視是否有應優先的真實案例（用 `--limit` 放寬或手動指定補進下一輪）：

- 「壓合卡扣」（命中：無）
- 「左手從螺絲料盒拿取螺絲」（命中：無）
- 「拆箱取件」（命中：無）
- 「拿取」（命中：無）
- 「拿取保護泡棉」（命中：無）
- 「拿取側板」（命中：無）
- 「拿取出貨外箱」（命中：無）
- 「拿取防靜電袋」（命中：無）
- 「拿取電源供應器」（命中：無）
- 「拿取顯示卡」（命中：無）
- 「拿取風扇模組」（命中：無）
- 「按下電源測試按鈕」（命中：無）
- 「按壓/按鈕」（命中：無）
- 「掃描/檢查」（命中：無）
- 「掃描條碼建檔」（命中：無）
- 「插入/組裝」（命中：無）
- 「插接線材」（命中：無）
- 「撕開/移除」（命中：無）
- 「撕除螢幕保護膜」（命中：無）
- 「擦拭外殼指紋」（命中：無）
- 「放置」（命中：無）
- 「放置主機板入機殼」（命中：無）
- 「放置成品入緩衝棧板」（命中：無）
- 「放置擋板至機殼後方」（命中：無）
- 「整理機殼內線材」（命中：無）
- 「旋緊天線接頭」（命中：無）
- 「熱壓導熱膠固化」（命中：無）
- 「移動/走步」（命中：無）
- 「精密對準裝配」（命中：無）
- 「自料盒拿取主機板」（命中：無）
- 「貼上序號標籤」（命中：無）

## 已知系統性偏差（也逐筆寫在草稿的 preannotation_caveat）

- rule planner 永遠單 action：22 筆多動作候選的預測切分幾乎必然低估（`likely_multi_action_undercounted`）。
- 另 16 筆是「取＋放」配對（`take_place_pair_may_be_single_gm`）：MiniMOST 的 GM 本來就是 G＋P 同一 cycle，**不預設低估**——IE 逐筆裁決建單一 GM 或兩個 action。
- 另 3 筆是「取/觸＋推/拉」配對（`take_move_pair_may_be_single_cm`）：CM 序列的 G 與 M 本來就在同一 cycle（`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2），**不預設低估**——IE 逐筆裁決建單一 CM 或兩個 action。
- `challenge_tags` 的 9 個可判維度：`false` 也是啟發式輸出（`heuristic_tags_unverified` 點名的 quantity/tool_handling/simo_both_hands 已有實證漏標），覆核時 true/false 都要確認。
- 時間戳注意：v3 遷移資料的 DB 時間是**遷移執行時間**（同一天），不是原著作時間——temporal_holdout 不能用現有 created_at 定義，提案見 docs/llm/gold-review/README.md。
