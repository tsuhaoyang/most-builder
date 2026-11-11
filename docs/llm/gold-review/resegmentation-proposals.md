# 重切建議稿 — 6 筆 IE 已確認 multi_cycle 但 plan 未重切（第五輪覆核材料，D3-020 準備中）

**日期**：2026-08-17
**對象**：D3-019 轉正被擋類別「multi_cycle 確認但 plan 未重切」的 6 筆——
`d001_6fa45cdb`／`d005_5cb719bb`／`d008_72dc0511`／`d012_fe5391c6`／
`d016_d0350279`／`d030_fe1f3a90`（以 `tests/gold/wi_plans_draft/review-state.json`
標 multi_cycle 且未 `promoted_to` 者逐筆核對，兩邊一致）。

**本文件的性質**：**建議稿，不是裁決**。產出過程**唯讀**——未動任何草稿 JSON、
未動 `review-state.json`、未寫 DB、未動 `src/`。IE 對各節是非題的答案由後續輪次
落地（`ie_edited` → `--recompile` → `--promote` 資格檢查）。

## 產生方式（可重現，全部唯讀）

1. **v3 結構證據**：唯讀查 dev DB（`ddm_v2_most`）的
   `motion_modules`／`motion_module_versions`——每筆 provenance 指到的 module
   之 `current_version` 發布版 `rows[]`（一列＝一個 cycle，per D3-014 裁決 3）。
2. **每列 TMU**：以單一引擎重放——列內存的 cycle 值走
   `CycleIn → cycle_in_to_engine → most_engine.compute_cycle`
   （rule-set＝`build_from_seed_v2()` 的 `MINIMOST_FACTORY_V2`），**不手算**。
   逐 module 以「Σ(列 TMU×freq)＝版本 `total_tmu`」交叉驗證；帶
   `simo_pair_index` 的列（與配對列同時進行）**不計入版本合計**——d001 rows[2]
   與 d016 rows[3] 即此類，合計驗證通過。
3. **子句管道預測**：對每個建議 span 的子句文字（與 span 不可得列的 v3 列文字）
   跑現行 pipeline（與 `scripts/gold_harvest.py` `run_pipeline` 同路徑：
   `rule_based_v1 → plan_from_rule_result → SlotLinker(no-db) → compile_plan →
   engine_gate(most_engine) → compute_routing(auto=off)`；詞典＝DB
   `rule_option_synonyms` @ `MINIMOST_FACTORY_V2` **16 條**，D3-019 後現況）。
   唯讀演算、不落檔。
4. span 位置一律指 **normalized_text 的半開區間**（evidence 契約同草稿）。

## 跨筆共通事實（先讀，各節不重複展開）

- **F1（誠實 span 原則）**：只在原句能切出連續子字串時給 span；v3 列是獨立句
  非原句子字串者，明說「span 不可得」——選項為「以 v3 列文字重構該 action 並在
  evidence 記缺失原因（`v3_row_text_not_in_source` 之類的誠實標記）」，**不編造
  span**（d026 教訓）。注意：`source_provenance` 不可改，schema 守門要求
  `plan.normalized_text` 與 provenance `raw_text` 正規化一致——重構的是
  `plan.actions`，母句本身不換。
- **F2（成分列已各自成案）**：這 6 筆的 **19 個 v3 列，列文字全部已是獨立草稿或
  已轉正 gold**（各節逐列標注；11 列已是 g06–g26 的轉正 gold、8 列是在案草稿）。
  重切時每段的建模答案可直接對表，不必重新發明。
- **F3（距離未述）**：子句多數未述移動距離，現行管道 TMU 帶 0.0——沿
  D3-018 M1／D3-019 ④ 的誠實記錄路徑（`expected_incomplete_reason:
  "distance_unstated"`），**不發明距離**。v3 列 cycle 存有當初 IE 的距離值
  （reach 35cm、b_stand 等）——是否把 v3 列值回填進重切後的 cycle，屬 IE 裁決
  （見各節是非題）。
- **F4（acquire 單獨子句）**：「拿取×」單獨成段時現行管道判不了型
  （`composite_unknown` 棄權）——plan 層合法建模是 acquire action（g01
  「拿起DIMM」先例：單 acquire、不補步驟、routing review）；v3 對應列多建為
  GM＋`p_hold`（「保持住」），但「保持住」**不在子句文字裡**——兩種建法都列為
  取捨點。
- **F5（已確認面向會 stale）**：這 6 筆已有的判型／P 方向／TMU=0 確認
  （review-state 面向）是對**現行 1-action plan** 說的；重切後逐段判型會變，
  stale 機制（`typing_change_changed` 等）會逐筆抓出重問，不靜默沿用。重切屬
  plan 內容編輯（`ie_modified: true`）——state 檔保覆核詮釋資料、保不了 plan
  內容，重切後對草稿目錄 `--force` 前先轉正或另行備份（README「覆核狀態怎麼在
  重產後存活」）。

---

## d001_6fa45cdb（multi_cycle_3）

### 1. 原句與 v3 結構證據

原句：「確認DIMM點位，並按壓DIMM壓合治具的把手 (依據配置要求-16個DIMM)」
normalized：`確認dimm點位,並按壓dimm壓合治具的把手 (依據配置要求-16個dimm)`（len 40）

Provenance module：`motion_modules/d630108e-643e-4717-94e0-c0c922200076`
（category=wi-template，keywords=[v3-import]，status=standard）；發布版 v1
（`motion_module_versions/40bb7624-b631-49ed-b35c-d395fc10cf0b`，
rule_set=MINIMOST_FACTORY_V2，published_by=IEC141289）共 **3 列**，
`total_tmu=442.0`（＝rows[0]＋rows[1]；rows[2] 帶 `simo_pair_index=1` 與
rows[1] 併行不計入合計；引擎重放逐列 26＋416＋54 驗證相符）。

| 列 | 手 | 列文字（sub_activity） | cycle 摘要（引擎重放） | 該列文字的獨立案件 |
|---|---|---|---|---|
| rows[0] | RH | 並確認DIMM點位 | CM：B1=b_eye、I5=i_confirm_out → `A0 B10 G0 M0 X0 I16 A0`＝**26.0** | 草稿 `d056_2f0cb396`（無 review-state entry） |
| rows[1] | LH | 左手抓握DIMM壓合治具的把手放×16至對應的點位 | GM：A0(reach20)、B1=b_stand、G2=g_grasp、B4=b_eye、P5=p_place_none×16＋addon a_press → `A6 B42 G6 A0 B10 P352 A0`＝**416.0** | 草稿 `d014_6678c378`（無 entry） |
| rows[2] | RH | 右手接觸DIMM壓合治具的底板拉至對應的點位 | CM：A0(reach10)、B1=b_stand、G2=g_touch、M3=m_pull@2.5cm → `A3 B42 G3 M3 X0 I0 A3`＝**54.0**；**SIMO 併行 rows[1]，不計合計** | **已轉正 g21_pull_fixture_base** |

### 2. 建議切分

原句唯一標點切點＝逗號（norm index 8）。誠實 span 只切得出 **2 段**：

| action | span | span 文字 | 對應 v3 列 |
|---|---|---|---|
| a1 | `[0,8)` | 確認dimm點位 | rows[0] |
| a2 | `[9,40)` | 並按壓dimm壓合治具的把手 (依據配置要求-16個dimm) | rows[1]（×16 的證據在括註內，故 span 含括註） |
| a3 | **span 不可得** | —— | rows[2]：列文字（接觸底板拉至點位）完全不在原句內。建議以 v3 列文字重構並記 evidence 缺失原因；該列已是獨立 gold g21，建模答案可直接對表 |

### 3. 判型／slot／TMU（v3 期望 vs 現行管道對子句的唯讀演算）

- **a1**（確認dimm點位）：v3＝CM（I5=i_confirm_out，26 TMU）。現行管道：
  `composite_unknown`、**abstain**——「確認」的 I 面**未登記**（synonym-candidates
  列 `確認→i_confirm?`，且範圍內 i_confirm vs 範圍外 i_confirm_out 待 IE 裁；
  v3 此列用的是**範圍外** i_confirm_out）。
- **a2**（並按壓…把手 (…16個dimm)）：v3＝**GM**（把手「放×16」＋P addon
  a_press，416 TMU）。現行管道：**CM**、m_press@0cm、complete、
  `A0 B0 G0 M3 X0 I0 A0`＝**3.0 TMU**、routing review——與 v3 建模**判型相反**，
  且 ×16 數量未被抽取（管道 frequency=1）。本筆 2026-08-17 的判型確認
  （noun_only GM→lexicon CM）是對**整句 1-action plan** 的確認，重切後 a2 的
  GM/CM 需重新裁（F5）。
- **a3**（重構自 rows[2] 文字）：v3＝CM（m_pull@2.5cm，54 TMU）。現行管道對該
  列文字：CM、m_pull@0cm、TMU 0.0（距離未述，F3）；gold g21 已以
  `expected_incomplete_reason: distance_unstated` 轉正。

### 4. 給 IE 的是非題

**切成 3 段：a1=[0,8) 確認點位（CM-I）、a2=[9,40) 按壓把手（建模照 v3
rows[1]：GM 放×16＋a_press）、a3=span 不可得——以 v3 rows[2] 文字重構（CM
拉至點位）並記 evidence 缺失原因——對嗎？**

取捨點（請一併回答）：
1. a1 的「確認」I 面未登記——要登記 `i_confirm`（範圍內）還是 `i_confirm_out`
   （範圍外，v3 此列所用）？
2. a2 判型：照 v3 建 GM（放×16＋a_press addon，416）還是照現行詞典判 CM
   （m_press，3）？×16 是否作為 a2 的 repeat_count 寫入？
3. a3 是 SIMO 併行列（v3 不計入合計）——重切後的 plan 要不要建第 3 個 action？
   若建，SIMO/手別資訊原句不可得，是否照 v3 列值補記（並記缺失原因）？
   若不建（只切 2 段），與已確認的 multi_cycle_3 結構的對應差異需留痕。

---

## d005_5cb719bb（multi_cycle_4）

### 1. 原句與 v3 結構證據

原句：「拿取主板，去除包裝袋，將主板放置工作台」
normalized：`拿取主機板,去除包裝袋,將主機板放置工作臺`（len 21）

Provenance module：`motion_modules/8436a0d0-da56-4eee-818a-b1c9bff29f44`
（wi-template，v3-import，standard）；v1
（`motion_module_versions/fb1bde71-16d0-4988-ab3d-adeb4f1da929`）共 **4 列**，
`total_tmu=324.0`（逐列 85＋71＋84＋84 重放相符，無 SIMO 列）。

| 列 | 手 | 列文字 | cycle 摘要（引擎重放） | 獨立案件 |
|---|---|---|---|---|
| rows[0] | RH | 右手從料架拿取主板保持住 | GM：A0(reach35)、b_stand、G2=g_pick_sel、B4=b_eye、P5=p_hold → `A10 B42 G10 A0 B10 P3 A10`＝**85.0** | 草稿 `d029_650ee42f`（切分已確認、判型未確認、未轉正） |
| rows[1] | LH | 左手抓握主板的包装袋去除 | CM：A0(reach35)、b_stand、G2=g_grasp、M3=m_remove@2.5cm → `A10 B42 G6 M3 X0 I0 A10`＝**71.0** | **已轉正 g17_remove_board_bag** |
| rows[2] | LH | 左手重新抓握主板的包装袋放至料架 | GM：A0(reach35)、b_stand、G2=g_regrasp、B4=b_eye、P5=p_place_none → `A10 B42 G6 A0 B10 P6 A10`＝**84.0** | **已轉正 g24_board_bag_to_rack** |
| rows[3] | BH | 雙手重新抓握主板放至潔淨棚的工作台 | GM：同上形狀 → `A10 B42 G6 A0 B10 P6 A10`＝**84.0** | **已轉正 g16_regrasp_board_to_bench** |

### 2. 建議切分

兩個逗號給出 **3 段誠實 span**；第 4 列（rows[2]，包裝袋放至料架）原句完全沒提：

| action | span | span 文字 | 對應 v3 列 |
|---|---|---|---|
| a1 | `[0,5)` | 拿取主機板 | rows[0] |
| a2 | `[6,11)` | 去除包裝袋 | rows[1] |
| a3 | **span 不可得** | —— | rows[2]：原句無「包裝袋放料架」任何字面。建議以 v3 列文字重構並記 evidence 缺失原因；建模答案＝gold g24 |
| a4 | `[12,21)` | 將主機板放置工作臺 | rows[3] |

（action 順序照 v3 製程序 rows[0..3]；有 span 的三段在原句內單調不重疊。）

### 3. 判型／slot／TMU

- **a1**（拿取主機板）：v3＝GM（g_pick_sel＋p_hold，85）。現行管道：
  `composite_unknown` abstain——acquire 單獨子句判不了型（F4）；「保持住」不在
  span 文字內，p_hold 借不到誠實字面。取捨：建 acquire action（g01 先例）vs
  照 v3 建 GM＋p_hold（值有據、字面缺失需留痕）。
- **a2**（去除包裝袋）：v3＝CM（m_remove@2.5cm，71）。現行管道：CM、
  m_remove@0cm、complete、TMU **0.0**（距離未述，F3）、routing review——判型
  與 v3 一致，差距離與 A/B/G 準備值。
- **a3**（重構自 rows[2] 文字）：v3＝GM（g_regrasp＋p_place_none，84）。現行
  管道對該列文字：GM、p_place_none、TMU 6.0（`A0 B0 G0 A0 B0 P6 A0`）；
  gold g24 已轉正。
- **a4**（將主機板放置工作臺）：v3＝GM（g_regrasp＋p_place_none，84）。現行
  管道：`composite_unknown` abstain——子句只有 P 動詞（放置）無 G 動詞，
  現行 `classify_seq` 的 GM 訊號需 G＋P 組合。取捨：判型卡點是管道限制，
  IE 可直接裁 GM（工作台＝盤面類→p_place_none，與 D3-017 情境規則一致）。

### 4. 給 IE 的是非題

**切成 4 段：a1=[0,5) 拿取（照 v3＝GM＋p_hold 或 acquire）、a2=[6,11) 去袋
（CM m_remove）、a3=span 不可得——以 v3 rows[2] 文字重構（GM 袋至料架）並記
evidence 缺失原因、a4=[12,21) 主板放工作台（GM p_place_none）——對嗎？**

取捨點：
1. a1 建 acquire 還是 GM＋p_hold（「保持住」字面不在 span 內）？
2. a2／a4 距離未述：TMU 留 0.0 記 `distance_unstated`（本筆 zero_tmu 裁決已
   照此），還是回填 v3 列的距離值（reach 35cm 等）？
3. a3 不在原句字面——照 v3 重構（4 action）還是只建 3 action 並留結構差異註記？

---

## d008_72dc0511（multi_cycle_2）

### 1. 原句與 v3 結構證據

原句：「從料架上拿取假DIMM，去除其包裝袋」
normalized：`從料架上拿取假dimm,去除其包裝袋`（len 18）

Provenance module：`motion_modules/d9203ed2-8138-4d2a-8ab6-480ff29daafb`
（wi-template，v3-import，standard）；v1
（`motion_module_versions/7fc58b77-1e55-4ef3-a4ff-6cf6aaad7cf8`）共 **2 列**，
`total_tmu=136.0`（75＋61 重放相符）。

| 列 | 手 | 列文字 | cycle 摘要（引擎重放） | 獨立案件 |
|---|---|---|---|---|
| rows[0] | LH | 左手從料架拿取假DIMM保持住至流水線 | GM：A0(reach35)、b_stand、G2=g_pick_sel、B4=b_eye、P5=p_hold → `A10 B42 G10 A0 B10 P3 A0`＝**75.0** | 草稿 `d039_0423b4e8`（切分已確認、未轉正） |
| rows[1] | RH | 右手抓握假DIMM的包裝袋撕除 | CM：A0(reach35)、b_stand、G2=g_grasp、M3=m_teartape@2.5cm → `A10 B42 G6 M3 X0 I0 A0`＝**61.0** | **已轉正 g23_tear_dummy_dimm_bag** |

### 2. 建議切分

逗號切點，**2 段誠實 span、與 v3 兩列 1:1 乾淨對應**（本組唯一無缺列案例）：

| action | span | span 文字 | 對應 v3 列 |
|---|---|---|---|
| a1 | `[0,11)` | 從料架上拿取假dimm | rows[0] |
| a2 | `[12,18)` | 去除其包裝袋 | rows[1] |

### 3. 判型／slot／TMU

- **a1**：v3＝GM（g_pick_sel＋p_hold，75）。現行管道：`composite_unknown`
  abstain（F4——「保持住至流水線」不在 span 文字內）。取捨同 d005 a1。
- **a2**：v3＝CM（**m_teartape** 撕除@2.5cm，61）。現行管道：CM、
  **m_remove**@0cm、TMU **0.0**（距離未述；本筆 zero_tmu_ruling 已裁
  distance_unstated）。動詞面差異：span 字面「去除」→ 已登記 m_remove；
  v3 列用「撕除」→ m_teartape——兩者在 2.5cm 同為 M3，TMU 無差，但 option
  code 不同，gold 對答案時要選一個。

### 4. 給 IE 的是非題

**切成 2 段：a1=[0,11) 拿取假DIMM（照 v3＝GM＋p_hold 或 acquire）、
a2=[12,18) 去袋（CM）——對嗎？**

取捨點：
1. a1 建 acquire 還是 GM＋p_hold？
2. a2 的 M 動詞：照 span 字面掛 `m_remove`，還是照 v3 列（＝g23 gold）掛
   `m_teartape`？
3. 距離未述：TMU 0.0 記 `distance_unstated`（現況）還是回填 v3 距離值？

---

## d012_fe5391c6（multi_cycle_2）

### 1. 原句與 v3 結構證據

原句：「拿取主板放置於DIMM壓合治具」
normalized：`拿取主機板放置於dimm壓合治具`（len 16）

Provenance module：`motion_modules/b5666b80-fd4e-4157-840f-ee61ac3cecc3`
（wi-template，v3-import，standard）；v1
（`motion_module_versions/62d5bebb-5897-4d46-aaee-aad4d1c742ca`）共 **2 列**，
`total_tmu=178.0`（110＋68 重放相符）。

| 列 | 手 | 列文字 | cycle 摘要（引擎重放） | 獨立案件 |
|---|---|---|---|---|
| rows[0] | BH | 雙手抓握主板放至DIMM壓合治具 | GM：A0(reach35)、b_stand、G2=g_grasp、**A3(foot45)**、B4=b_eye、P5=p_place_single → `A10 B42 G6 A16 B10 P16 A10`＝**110.0** | **已轉正 g06_board_to_press_fixture** |
| rows[1] | BH | 雙手接觸DIMM壓合治具推至規定位置 | CM：A0(reach35)、b_stand、G2=g_touch、M3=m_push@2.5cm → `A10 B42 G3 M3 X0 I0 A10`＝**68.0** | **已轉正 g10_push_press_fixture** |

### 2. 建議切分

原句無標點切點；「取＋放」配對＝v3 rows[0] 的**單一 GM cycle**（D3-014 裁決 1
的單 cycle 方向，本筆 `take_place_pair_may_be_single_gm` 旗標的解答）。第 2 列
（推至規定位置）原句隻字未提：

| action | span | span 文字 | 對應 v3 列 |
|---|---|---|---|
| a1 | `[0,16)`（全句） | 拿取主機板放置於dimm壓合治具 | rows[0]（取放＝同一 GM cycle） |
| a2 | **span 不可得** | —— | rows[1]：列文字（接觸治具推至規定位置）完全不在原句內。建議以 v3 列文字重構並記 evidence 缺失原因；建模答案＝gold g10 |

### 3. 判型／slot／TMU

- **a1**：v3＝GM（g_grasp＋A3 腳步 45cm＋p_place_single，110）。現行管道
  （＝現行草稿）：GM、p_place_single（P 方向 single 已於 2026-08-17 確認）、
  complete、`A0 B0 G0 A0 B0 P16 A0`＝**16.0**、routing review——G slot 未取值
  （g_code null）且距離/腳步未述是與 v3 110 的差距主因。
- **a2**（重構自 rows[1] 文字）：v3＝CM（m_push@2.5cm，68）。現行管道對該列
  文字：CM、m_push@0cm、TMU 0.0（距離未述）；gold g10 已以
  `distance_unstated` 轉正。

### 4. 給 IE 的是非題

**切法＝a1 維持全句 span 建單一 GM（取放同 cycle），a2=span 不可得——以 v3
rows[1] 文字重構（CM 推至定位）並記 evidence 缺失原因——對嗎？**

取捨點：
1. a1 的 G slot：現行管道 g_code 未取值（G0）——照 v3 掛 g_grasp（或按已登記的
   「拿取→g_pick_sel」）？
2. a2 不在原句字面——照 v3 重構（2 action）還是維持 1 action 並留結構差異註記
   （multi_cycle_2 確認 vs plan 1 action 的落差即現在的轉正阻擋原因）？
3. 距離/腳步（A3 foot45）未述：TMU 留誠實 0/16 還是回填 v3 值？

---

## d016_d0350279（multi_cycle_5）

### 1. 原句與 v3 結構證據

原句：「拿取風槍清潔放置DIMM材料盒的DIMM」
normalized：`拿取風槍清潔放置dimm材料盒的dimm`（len 20）

Provenance module：`motion_modules/8451efa7-7536-48f7-b579-b56d21608c02`
（wi-template，v3-import，standard）；v1
（`motion_module_versions/687ed233-54bd-4b49-ab1c-2f39e39fc9d3`）共 **5 列**，
`total_tmu=377.333`（＝rows[0]＋rows[1]＋rows[2]＋rows[4]；rows[3] 帶
`simo_pair_index=4` 與 rows[4] 併行不計；逐列 88＋74＋61＋71＋154.333 重放
驗證相符）。

| 列 | 手 | 列文字 | cycle 摘要（引擎重放） | 獨立案件 |
|---|---|---|---|---|
| rows[0] | BH | 雙手從料架拿取DIMM材料盒放至潔淨棚的工作台 | GM：g_pick_sel＋p_place_none → `A10 B42 G10 A0 B10 P6 A10`＝**88.0** | 草稿 `d015_a062c017`（切分已確認、判型未確認、未轉正） |
| rows[1] | LH | 左手抓握DIMM材料盒放至規定位置處 | GM：g_grasp＋p_place_none → `A10 B42 G6 A0 B10 P6 A0`＝**74.0** | **已轉正 g26_dimm_box_to_position** |
| rows[2] | RH | 右手抓握風槍保持住至規定位置處 | GM：g_grasp＋p_hold → `A10 B42 G6 A0 B0 P3 A0`＝**61.0** | **已轉正 g18_hold_airgun_to_position** |
| rows[3] | LH | 左手抓握DIMM材料盒保持住 | GM：g_grasp＋p_hold → `A10 B42 G6 A0 B10 P3 A0`＝**71.0**；**SIMO 併行 rows[4]，不計合計** | **已轉正 g22_hold_dimm_box** |
| rows[4] | RH | 右手抓握風槍按動按鈕並吹風清潔DIMM | CM：g_grasp＋M3=m_btn＋**X4=x_blow_clean 3s** → `A10 B42 G6 M3 X83.333 I0 A10`＝**154.333** | **已轉正 g15_airgun_clean_dimm** |

### 2. 建議切分

**span 不可得（d026 型，全 5 列）**：5 列全部是各自獨立的完整子句，無一是原句
的子字串。原句是這段五步驟製程的**壓縮標題**（取風槍、清潔、材料盒、DIMM 的
詞面散落且語序交錯——「拿取風槍」`[0,4)` 與 rows[2]、「清潔」`[4,6)` 與 rows[4]
只有碎片級重疊，切不出 5 段連續、互不重疊、語意對應的誠實 span）。**不編造**。

建議：以 v3 列文字重構 plan（5 個 action，每個 action 的 evidence 記缺失原因
＝v3 列文字非原句子字串），或裁決本句不重切、不轉正（成分 cycle 已由
g15/g18/g22/g26 與 d015 逐筆覆蓋，母句僅存 provenance 對應）。

### 3. 判型／slot／TMU

現行管道對**原句全句**：GM、p_place_none、TMU 6.0、routing review——單 action
誤併（「清潔放置」詞面誤導），不可作為期望值。對各 v3 列文字的現行管道輸出：

| 列 | v3 期望 | 現行管道（對列文字） |
|---|---|---|
| rows[0] | GM 88.0 | GM p_place_none，TMU 6.0（距離未述） |
| rows[1] | GM 74.0 | GM **p_place_single**，TMU 16.0——「規定位置處」被情境規則判機構件方向；v3 建 p_place_none（差異點，g26 以 v3 面向轉正時已覆核） |
| rows[2] | GM 61.0 | GM p_hold，TMU 3.0 |
| rows[3] | GM 71.0 | GM p_hold，TMU 3.0 |
| rows[4] | CM 154.333 | CM m_btn，TMU 3.0——**X（x_blow_clean 3s）未掛**：「清潔」的 X 面未登記（synonym-candidates `清潔→x_blow_clean?` 僅建議風槍語境，待 IE 裁） |

### 4. 給 IE 的是非題

**本句 5 段 span 不可得——以 v3 五列文字重構 plan（5 action，evidence 記缺失
原因；建模照上表 v3 期望）——對嗎？**（若答否：是否改裁「母句不重切、不轉正，
成分 cycle 由既有 gold 覆蓋」？）

取捨點：
1. rows[3] 是 SIMO 併行列——重構時要不要建第 4 個 action？SIMO/手別資訊原句
   不可得（同 d001 取捨點 3）。
2. rows[4] 的「清潔」X 面未登記——要不要按候選（風槍語境→x_blow_clean）登記？
   x_seconds=3s 是 v3 列值，原句不可得。
3. rows[1] 的 P 方向：v3＝none vs 現行情境規則＝single（「規定位置處」）——
   重構時以哪個為準？

---

## d030_fe1f3a90（multi_cycle_2）

### 1. 原句與 v3 結構證據

原句：「拿取假DIMM組於DIMM卡槽 (依據配置要求-16個假DIMM)」
normalized：`拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm)`（len 33）

Provenance module：`motion_modules/6366f744-6791-4e84-a3ac-5305d4f07679`
（wi-template，v3-import，standard）；v1
（`motion_module_versions/0be9daab-eb7b-4158-8ce6-096de65c6ae2`）共 **2 列**，
`total_tmu=669.0`（606＋63 重放相符）。

| 列 | 手 | 列文字 | cycle 摘要（引擎重放） | 獨立案件 |
|---|---|---|---|---|
| rows[0] | RH | 右手拿取×16假DIMM插入×16至DIMM卡槽 | GM：A0(reach35)、b_stand、G2=g_pick_sel**×16**、B4=b_eye、P5=p_asm_single**×16**＋addon a_insert → `A10 B42 G160 A0 B10 P384 A0`＝**606.0** | 草稿 `d032_e945e29e`（切分已確認、未轉正） |
| rows[1] | LH | 左手抓握假DIMM的包裝袋丟至垃圾桶 | GM：A0(reach20)、b_stand、G2=g_grasp、P5=p_toss → `A6 B42 G6 A0 B0 P3 A6`＝**63.0** | **已轉正 g25_toss_dimm_bag** |

### 2. 建議切分

「取＋組於」配對＝v3 rows[0] 的單一 GM cycle（含 ×16 與 a_insert）；第 2 列
（包裝袋丟垃圾桶）原句隻字未提：

| action | span | span 文字 | 對應 v3 列 |
|---|---|---|---|
| a1 | `[0,33)`（全句） | 拿取假dimm組於dimm卡槽 (依據配置要求-16個假dimm) | rows[0]（×16 證據在括註內，span 含括註） |
| a2 | **span 不可得** | —— | rows[1]：原句無「包裝袋」任何字面。建議以 v3 列文字重構並記 evidence 缺失原因；建模答案＝gold g25 |

### 3. 判型／slot／TMU

- **a1**：v3＝GM（g_pick_sel×16＋p_asm_single×16＋a_insert，606）。現行管道：
  `composite_unknown`、**abstain**——「組於」的 P 面**未登記**
  （synonym-candidates `組至/組於→p_asm_*?`：single/multi 方向數待 IE 裁；
  「插入」與 addon `a_insert` 的分工也在同一候選節待裁）。×16 數量現行管道
  未抽取。
- **a2**（重構自 rows[1] 文字）：v3＝GM（g_grasp＋p_toss，63）。現行管道對該列
  文字：GM、p_toss、TMU 3.0（`A0 B0 G0 A0 B0 P3 A0`）；gold g25 已轉正。

### 4. 給 IE 的是非題

**切法＝a1 維持全句 span 建單一 GM（取＋組於同 cycle，×16 照括註），
a2=span 不可得——以 v3 rows[1] 文字重構（GM 丟垃圾桶）並記 evidence 缺失
原因——對嗎？**

取捨點：
1. 「組於」P 面未登記——登 `p_asm_single`（v3 此列所用、DIMM 插卡槽一種方向）
   還是 `p_asm_multi`？「插入」＝base＋addon（p_asm_single＋a_insert）的分工
   照 v3 嗎（避免雙重計價的裁決，synonym-candidates 在案）？
2. ×16 是否作為 a1 的 repeat_count 寫入（G 與 P 皆 ×16，照 v3）？
3. a2 不在原句字面——照 v3 重構（2 action）還是維持 1 action 並留結構差異註記？

---

## 附：切分建議一覽

| 筆 | v3 結構 | 誠實 span | span 不可得（不編造） |
|---|---|---|---|
| d001 | 3 列 | 2 段（逗號切） | 1 列（SIMO 拉底板；＝g21） |
| d005 | 4 列 | 3 段（兩逗號切） | 1 列（袋至料架；＝g24） |
| d008 | 2 列 | **2 段，1:1 乾淨對應** | 無 |
| d012 | 2 列 | 1 段（全句＝單一 GM） | 1 列（推至定位；＝g10） |
| d016 | 5 列 | **0 段（d026 型）** | 全 5 列（4 列已轉正 gold＋d015） |
| d030 | 2 列 | 1 段（全句＝單一 GM） | 1 列（袋丟垃圾桶；＝g25） |
