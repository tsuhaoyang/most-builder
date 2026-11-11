# 衝線批覆核材料 — P0 44→50 的最後 6+ 筆（**IE 已答 2026-08-17；D3-028 已落地，取而無放歸宿由 D3-029 改判**）

**文件類型：** IE 覆核材料（快答題；答案落地後由工程端執行並留痕）
**答覆狀態：** ✅ IE 已答（2026-08-17，IEC141289）——逐題答案與落地結果見
下方「§七 IE 答案與落地結果（D3-028）」；本文件 §一~§五 是**提問當時的盤點**，
保留原文不改寫（提問內容本身是軌跡）。實際結果 **P0 44 → 52**（10 題候選中
8 筆轉正、2 筆依 IE 指示不登記同義詞而留草稿）。
**後續改判（D3-029，2026-08-17）：** Q5 兩筆的「取而無放」歸宿由
`place_in_next_row`（工程推定）改判為 **`consumed_by_later_action`**——IE 否決
單一 token、改裁四類歸宿；兩筆不撤回（P0 維持 52/50）。見 §七 Q5 後續列與
「兩個提問時未預見的工程結果」第 2 點的後記。
**產生輪次：** 第九輪準備（D3-027 之後；草稿池＝第八輪 harvest 後的 47 筆）
**基線：** 正式 gold 47（3 seed＋44 轉正）＝P0 **44/50**；草稿池 47 筆；unit 842 綠
**盤點方法：** 唯讀逐筆跑 `scripts/gold_harvest.py` 的 `promotion_blockers`
（轉正資格唯一出處；本文件不動草稿、不動 review-state、不寫 DB、不動 src）

---

## 一、47 筆草稿的資格差距盤點（按缺口數排序）

「缺口」＝IE 可用快答補上的確認/裁決；標【工程】者是程式修復票，IE 答了也解不了，
誠實排除在衝線候選之外。

### A. 只缺一項（5 筆）——切分確認即可轉正

D3-024 點名的「entry 僅它面向」5 筆：state entry 只帶判型/TMU 面向（D3-019 第 5 點
「切分維度 IE 未答，不冒填」），切分維度懸置至今。5 筆皆無切分爭點旗標
（無配對旗、無 likely_multi）——符合 D3-021 無爭點批次確認的適用前提。

| # | sha8 | 句子 | 判型 | TMU | 缺什麼 |
|---|---|---|---|---|---|
| d008 | `1dd7c1d5` | 按壓功能測試治具 | CM 已確認 | **3.0 真值**（`A0 B0 G0 M3 X0 I0 A0`） | 切分確認 |
| d011 | `6be614c5` | 按壓 DIMM 卡扣到定位 | CM 已確認 | **3.0 真值**（同上） | 切分確認 |
| d035 | `2e7b2e5a` | 按壓/按鈕 | CM 已確認 | **3.0 真值**（同上） | 切分確認 |
| d004 | `51518399` | 貼附Label到主板規定位置處 | CM 已確認 | 0.0 非真值——**已裁** `distance_unstated`（D3-019） | 切分確認（轉正後＝誠實 incomplete） |
| d029 | `7f085e02` | 撕除螢幕保護膜 | CM 已確認 | 0.0 非真值——**未裁**（distance-rulings C11 懸案） | 切分確認＋TMU=0 距離裁決（缺兩項，列此因裁決已排隊） |

### B. 切分已確認、缺實質內容（12 筆）——差同義詞/判型答案或工程票

全部已有 state entry（批次確認或 ie_ruling），唯一 blocker＝空殼守門
（無 complete 帶 TMU>0 的 cycle、也無顯式 `expected_incomplete_reason`）。卡點逐類：

| # | sha8 | 句子 | 卡點 | IE 可快答？ |
|---|---|---|---|---|
| d005 | `28f9ed7e` | 拿取螺絲 x1 | 單 G 動詞不足以定型（G 存在於 GM/CM 兩序列） | ✅ 判型答案（預設 acquire）→ 工程照答案 edit＋recompile（g30-a1 前例：acquire＝g_pick_sel 10.0 真 TMU） |
| d010 | `37fbd2a6` | 放置散熱片於 CPU 上 | 單 P 動詞不足（放置已登記） | ✅ 判型答案（預設 move_place）＋P 方向數確認 |
| d012 | `0461f75d` | 拿取 M.2 SSD | 同 d005 | ✅ 同 d005 |
| d013 | `ac155900` | 拿取 DIMM 記憶體模組 | 同 d005 | ✅ 同 d005 |
| d014 | `b2618d31` | 小範圍拿取(≤50cm) | 同 d005；另句面帶距離上界（≤50cm 可否當 A 距離＝IE 裁） | ✅（範本標籤句，優先度較低） |
| d015 | `0e83128f` | 下壓 CPU 拉桿鎖定 | 「下壓」未登記（synonym-candidates 既列 `m_press` **?**） | ✅ 同義詞裁決＋判型旗確認 |
| d007 | `35372a96` | 拿取排線並對準接頭 | 「對準」未登記（`i_align1` **?** vs P addon `a_align` 分工未裁） | ⚠️ 可答但開放度高（兩條建模路線） |
| d003 | `633b52bb` | 雙手掰開DIMM卡槽的卡扣 | 「掰開」無貼合選項——可能 rule-set 覆蓋缺口 | ⚠️ 開放題（裁不出＝記錄缺口，不硬湊） |
| d009 | `4eb2b2e6` | 功能測試(治具) | GM 判型來自名詞觸發、missing_core_p；句子是設備製程標籤 | ⚠️ 建模開放（process？P code？） |
| d002 | `6678c378` | 左手抓握DIMM壓合治具的把手放×16至對應的點位 | 「放×16至」被數量記號插斷、M/P 面漏配——**F 票**（D3-026 記票，lexicon 穩健性） | ❌【工程】修 F 票後再覆核（distance/頻率屆時一併） |
| d006 | `8dfafd2e` | 摺合上蓋扣合 | 句面無動詞面命中 | ❌ 非同義詞可解；需 IE 補建模/改 plan |
| d016 | `995f5d45` | 貼標籤 | 句面無動詞面命中 | ❌ 同上 |

### C. 標題句 fail-closed（1 筆）——IE 已裁不轉正

| # | sha8 | 句子 | 狀態 |
|---|---|---|---|
| d001 | `d0350279` | 拿取風槍清潔放置DIMM材料盒的DIMM | `title_sentence_no_resegmentation`（D3-022 裁、D3-024 重確認）——留草稿當多動作辨識參考，**永不列衝線** |

### D. 無 review-state entry（29 筆）——缺切分確認＋實質內容

轉正需要：切分確認（無爭點批次機制可用）＋判型/同義詞答案＋（部分）TMU 裁決。
按解鎖路徑分三類：

- **D1 單動詞已登記（15 筆）**——判型答案（acquire／move_place）＋批次切分即可解，
  路徑同 d005/d010：
  `d018` 自料盒拿取主機板、`d024` 放置擋板至機殼後方、`d025` 放置成品入緩衝棧板、
  `d026` 放置主機板入機殼、`d027` 放置、`d032` 插入/組裝、`d037` 拿取風扇模組、
  `d038` 拿取顯示卡、`d039` 拿取電源供應器、`d040` 拿取防靜電袋、`d041` 拿取出貨外箱、
  `d042` 拿取側板、`d043` 拿取保護泡棉、`d044` 拿取、
  **`d046` 左手從螺絲料盒拿取螺絲（本類結構證據最強——見候選 #9）**
- **D2 未登記 `?` 動詞（11 筆）**——需同義詞裁決（部分另需 TMU=0 裁決）：
  `d017` 貼上序號標籤（貼上→`m_attach`？＋零 TMU）、`d019` 精密對準裝配（對準？）、
  `d021` 熱壓導熱膠固化（熱壓？機製程 X？）、`d022` 旋緊天線接頭（旋緊？**手動**旋緊
  與 D3-024「鎖附一律電動」的邊界）、`d023` 整理機殼內線材（整理？）、
  `d028` 擦拭外殼指紋（擦拭？「清潔」的擦拭情境 IE 尚未裁——synonym-candidates 記
  `m_wipe`？屆時另裁）、`d030` 撕開/移除（撕開→`m_tearopen`＋零 TMU）、
  `d033` 掃描條碼建檔／`d034` 掃描/檢查（掃描？）、
  **`d036` 按下電源測試按鈕（按下→`m_btn`？——本類證據最強，見候選 #10）**、
  `d047` 壓合卡扣（壓合→`m_press`？`x_press`？）
- **D3 句面無動詞面（3 筆）**——非同義詞可解：`d020` 移動/走步、`d031` 插接線材、
  `d045` 拆箱取件

---

## 二、衝線候選 10 筆（總表）

挑選原則：缺口最少優先；已知 5 筆切分未確認全數納入；無 entry 池補結構證據最強的
2 筆。10 筆＝留餘裕（達 50 只需其中 6 筆過關）。

| 候選 | sha8 | 句子 | 缺口（IE 快答數） | 預設答案 | 轉正後型態 |
|---|---|---|---|---|---|
| 1 | `1dd7c1d5` | 按壓功能測試治具 | 1：切分確認 | 併入無爭點批次（single_cycle） | **帶工時 3.0**（g13/g14 同口徑） |
| 2 | `6be614c5` | 按壓 DIMM 卡扣到定位 | 1：切分確認 | 同上 | **帶工時 3.0** |
| 3 | `2e7b2e5a` | 按壓/按鈕 | 1：切分確認 | 同上（範本標籤句；g48 前例） | **帶工時 3.0** |
| 4 | `51518399` | 貼附Label到主板規定位置處 | 1：切分確認 | 同上 | **誠實 incomplete**（`distance_unstated` 已裁；g20 同句型前例）——除非距離裁決表 B10 改判補距離 |
| 5 | `7f085e02` | 撕除螢幕保護膜 | 2：切分確認＋距離裁決（distance-rulings C11） | 切分批次；距離**不預填** | 補距離→帶工時／維持→**誠實 incomplete** `distance_unstated` |
| 6 | `28f9ed7e` | 拿取螺絲 x1 | 2：判型答案＋數量順答（切分已批次確認） | acquire（g30-a1 前例）；x1→frequency 1 | **帶工時 10.0**（g_pick_sel；A 未述＝A0 口徑）；`ie_modified: true` |
| 7 | `0e83128f` | 下壓 CPU 拉桿鎖定 | 2：同義詞裁決＋判型旗確認（切分已批次確認） | 下壓→`m_press`（候選表既案） | **帶工時 3.0**（同按壓口徑） |
| 8 | `37fbd2a6` | 放置散熱片於 CPU 上 | 2–3：判型答案＋P 方向數確認（切分已批次確認） | move_place；CPU 座＝機構件→`p_place_single`（方向數一種） | **帶工時**（P 值；引擎算）；`ie_modified: true` |
| 9 | `8ef772ab` | 左手從螺絲料盒拿取螺絲 | 3：批次切分＋判型答案（＋edit 落地） | single_cycle；acquire | **帶工時 10.0**；`ie_modified: true`。無 entry 池結構證據最強：v3 module `1c0e39ae`（category=action）＋version `9569aeaf` rows[0]（g08/g46 同一 wi-template 的成分列） |
| 10 | `00104439` | 按下電源測試按鈕 | 3：批次切分＋同義詞裁決＋判型旗確認 | single_cycle；按下(按鈕賓語)→`m_btn`（備選 `m_press`） | **帶工時 3.0**（g13/g15 的 m_btn 同口徑） |

**備位（本輪不出快答題，IE 否決候選時遞補）**：`35372a96` 拿取排線並對準接頭
（切分已裁 single_cycle，但「對準」的 I 參數 vs P addon 分工是開放裁決）、
`1a9be08f` 壓合卡扣（壓合→`m_press` vs `x_press` 開放）、`cc6c7d56` 貼上序號標籤
（貼上→`m_attach` 低風險但另需零 TMU 裁決）、`633b52bb` 掰開（可能 rule-set 覆蓋缺口）。

---

## 三、逐筆快答題

格式同覆核表：原文／結構證據／預設答案／具體問題。**預設答案是預設不是判決**，
IE 可推翻；推翻＝該筆退回池中，不影響其他筆。

### 候選 1 — d008_1dd7c1d5「按壓功能測試治具」

- **原文**：按壓功能測試治具（`wi_rows/bd1da7bc…` sub_activity）
- **現況**：判型 CM 已確認（IEC141289，2026-08-17）；TMU=3.0 真值
  （`A0 B0 G0 M3 X0 I0 A0`）；唯一缺口＝切分維度未確認。
- **結構證據**：單動詞單句、無切分爭點旗標；plan＝1 action。與已轉正
  g13/g14 同 tech line 口徑（A 段距離未述＝A0、G 未掛＝G0，M3 為 m_press 真值）。
- **預設答案**：併入無爭點批次切分確認（single_cycle）。
- **IE 請回答**：本句是否併入無爭點批次確認（1 action＝1 cycle）？
  是→本筆即符合全部轉正資格。

### 候選 2 — d011_6be614c5「按壓 DIMM 卡扣到定位」

- **原文**：按壓 DIMM 卡扣到定位（`wi_rows/0c5b0f92…` sub_activity）
- **現況**：判型 CM 已確認；TMU=3.0 真值；唯一缺口＝切分確認。
- **結構證據**：同候選 1；與 g07/g14（按壓卡扣型）同動作族。
- **預設答案**：併入無爭點批次切分確認（single_cycle）。
- **IE 請回答**：同候選 1。

### 候選 3 — d035_2e7b2e5a「按壓/按鈕」

- **原文**：按壓/按鈕（`motion_templates/f378444b…` name_zh——範本標籤句）
- **現況**：判型 CM 已確認；TMU=3.0 真值；唯一缺口＝切分確認。
- **結構證據**：範本名稱句（斜線標籤型）；g48「電動鎖附(多顆)」已有標籤句
  轉正前例。單動作、無爭點旗標。
- **預設答案**：併入無爭點批次切分確認（single_cycle）。
- **IE 請回答**：①同候選 1；②標籤句身分是否影響本筆當 gold（不影響＝照 g48 前例）？

### 候選 4 — d004_51518399「貼附Label到主板規定位置處」

- **原文**：貼附Label到主板規定位置處（`motion_modules/9f61331e…` name_zh，wi-template）
- **現況**：判型 CM 已確認；TMU=0.0 已裁 `distance_unstated`（D3-019）、草稿已記
  `expected_incomplete_reason`；唯一缺口＝切分確認。
- **結構證據**：與已轉正 g20「右手從DIMM材料盒拿取Label貼附至主板」同動作族——
  g20 即以 `distance_unstated` 誠實 incomplete 轉正（同 tech line `A0 B0 G0 M0 X0 I0 A0`）。
- **預設答案**：併入無爭點批次切分確認（single_cycle）。
- **⚠️ 誠實預告**：轉正後本筆是 **incomplete 型**（reason＝`distance_unstated`）——
  不帶工時，是「誠實記錄資訊不足」不是帶 TMU 的案例；距離裁決表 B10 若改判補距離
  則走 ie_edited＋recompile 轉帶工時。
- **IE 請回答**：①同候選 1；②（順答，distance-rulings B10）貼附動作補典型距離幾 cm，
  或維持資訊不足？

### 候選 5 — d029_7f085e02「撕除螢幕保護膜」

- **原文**：撕除螢幕保護膜（`wi_rows/e58b4ad3…` sub_activity）
- **現況**：判型 CM 已確認（撕除→`m_teartape`）；TMU=0.0 **未裁**
  （distance-rulings C11——D3-023 起懸至今、README 快答清單第 1 條）；切分未確認。
- **結構證據**：與已轉正 g23「右手抓握假DIMM的包裝袋撕除」同動詞同 option
  （g23 以 `distance_unstated` 轉正）。
- **預設答案**：切分＝併入無爭點批次；距離**不預填**（典型距離是 IE 工程判斷，
  預填即發明資料——distance-rulings 誠實邊界）。
- **⚠️ 誠實預告**：若 IE 答「維持資訊不足」，轉正後是 **incomplete 型**
  （reason＝`distance_unstated`）；若補距離則 ie_edited＋recompile 後帶真 TMU。
- **IE 請回答**：①切分是否併入批次確認？②撕膜動作補典型距離幾 cm，或維持資訊不足？

### 候選 6 — d005_28f9ed7e「拿取螺絲 x1」

- **原文**：拿取螺絲 x1（`wi_rows/34ea3fe5…` sub_activity）
- **現況**：切分已批次確認（2026-08-17）；判型未定——「拿取」已登記
  `g_pick_sel`，但單一 G 動詞不足以定 GM/CM（G 兩序列都有，classify_seq 設計如此）。
- **結構證據**：g30-a1 前例——IE 重切後的 acquire action（g_pick_sel）編譯
  complete 10.0 TMU；g28「右手從料架拿取主板保持住」同取料族。
- **預設答案**：判型＝**acquire**（單純取料、放在後續列）；x1→frequency=1。
  工程端照答案 edit plan（action_type→acquire、`review_status: ie_edited`）→
  `--recompile` → entry 宣告 `ie_modified: true` → `--promote`（D3-022 工作流）。
- **誠實預告**：轉正後**帶工時 10.0**（g_pick_sel），但 A 段距離未述＝A0——與
  g30-a1 同口徑；本筆 `ie_modified: true` 會**計入** Plan 層指標（action 數與
  span 與 planner 輸出一致，指標分母 +1）。
- **IE 請回答**：①本句動作類型＝acquire，對嗎（不對請給 move_place/CM 等並述建模）？
  ②x1 掛 frequency=1，對嗎？

### 候選 7 — d015_0e83128f「下壓 CPU 拉桿鎖定」

- **原文**：下壓 CPU 拉桿鎖定（`wi_rows/c4104cb6…` sub_activity）
- **現況**：切分已批次確認；判型未定——「下壓」未登記
  （synonym-candidates 既列 `m_press` **?**：「下壓≈按壓？CPU 拉桿是槓桿控制移動」）。
- **結構證據**：按壓→`m_press` 已登記且 3 筆同型（d008/d011/d035）判型 CM 已確認。
- **預設答案**：下壓→`m_press`（priority 0 登記）。登記後 harvest 重跑，本筆判型
  null→CM、TMU 3.0；新出的判型旗**同輪確認**（D3-021/023 前例）。
- **IE 請回答**：①「下壓」對應 `m_press` 嗎？若拉桿應建其他 M 動詞（如拉）請指明；
  ②登記後的判型修正（null→CM）照預設確認嗎？

### 候選 8 — d010_37fbd2a6「放置散熱片於 CPU 上」

- **原文**：放置散熱片於 CPU 上（`wi_rows/30da4026…` sub_activity）
- **現況**：切分已批次確認；判型未定——「放置」已登記（single/none 兩變體），
  但單一 P 動詞不足以定型（設計如此；G 端無動詞面）。
- **結構證據**：g19/g26（抓握…放至）同放置族；P 情境規則（D3-017）：機構件→
  `p_place_single`。
- **預設答案**：判型＝**move_place**；CPU 座屬機構件→`p_place_single`（方向數
  預設一種）。工程端照答案 edit（action_type→move_place）→ recompile →
  `ie_modified: true` 轉正。
- **誠實預告**：帶工時（P 值由引擎算；A 段未述＝A0 口徑）；計入 Plan 層指標。
- **IE 請回答**：①動作類型＝move_place，對嗎？②散熱片放上 CPU＝機構件對準
  （`p_place_single`、方向數一種），對嗎？不對請改（盤面→none／方向數多種）。

### 候選 9 — d046_8ef772ab「左手從螺絲料盒拿取螺絲」

- **原文**：左手從螺絲料盒拿取螺絲（來源三筆：`motion_module_versions/587d379b…`
  rows[0]、`motion_module_versions/9569aeaf…` rows[0]、`motion_modules/1c0e39ae…`
  name_zh（category=action））
- **現況**：無 state entry（切分未答）；判型未定（單 G 動詞，同 d005）。
- **結構證據**：**無 entry 池最強**——v3 遷移 module（IE 驗證過並提供，D3-014
  裁決 3）＋version rows[0]（一列＝一 cycle）；`9569aeaf` 即 g08/g46 所屬
  wi-template『拿取電動起子，依圖示鎖附兩顆螺絲』的版本，本句是其成分列
  （左手取螺絲、右手持起子的 SIMO 對手列）。
- **預設答案**：切分＝single_cycle（v3 一列＝一 cycle）併入批次確認；判型＝acquire
  （同候選 6 路徑，`ie_modified: true`）。
- **誠實預告**：帶工時 10.0（g_pick_sel；A 未述＝A0）；計入 Plan 層指標。
- **IE 請回答**：①切分 single_cycle 併入批次確認，對嗎？②動作類型＝acquire，對嗎？
  ③SIMO 註記：本列與右手持起子列並行——是否需在 notes 標 SIMO（現行 plan 契約
  未表達 SIMO，照 g22 前例記 notes 即可）？

### 候選 10 — d036_00104439「按下電源測試按鈕」

- **原文**：按下電源測試按鈕（`wi_rows/8712630a…` sub_activity）
- **現況**：無 state entry；判型未定——「按下」未登記。
- **結構證據**：賓語是按鈕——「按動按鈕」→`m_btn` 已登記（g13/g15 以
  `A0 B0 G0 M3 X0 I0 A0`＝3.0 轉正）；「按壓」→`m_press` 亦已登記。
- **預設答案**：按下→**`m_btn`**（按鈕賓語，語意最貼；備選 `m_press`）。
  切分＝single_cycle 併入批次確認；登記後新判型旗同輪確認。
- **IE 請回答**：①「按下」（按鈕情境）對應 `m_btn` 還是 `m_press`？
  ②切分併入批次確認、判型旗照預設確認，對嗎？

---

## 四、誠實 incomplete 預標（任務要求逐筆預告）

轉正後**不帶工時**、以 `expected_incomplete_reason` 誠實記錄的候選：

| 候選 | reason（轉正時寫入） | 依據 |
|---|---|---|
| 4（d004 貼附Label） | `distance_unstated`（已裁，D3-019） | M 距離句面未述；g20 同型前例 |
| 5（d029 撕除保護膜） | `distance_unstated`（**若** IE 維持資訊不足；補距離則轉帶工時） | distance-rulings C11；g23 同型前例 |

其餘 8 筆轉正後皆帶引擎真 TMU（3.0／10.0／P 值），但一律附口徑註記：
**A 段（伸手）距離句面未述＝A0**——與 g13/g14/g30-a1 既有轉正口徑一致，非本輪新放寬。
候選 6/8/9 的 TMU 以 `--recompile` 重算為準（TMU 唯一出處＝most_engine，本文件
引用的數字是既有草稿/前例值，不是手算）。

---

## 五、答完預計 P0 到幾（誠實預估）

現況 **44/50**。

| 情境 | 過關筆數 | P0 |
|---|---|---|
| 只過「僅缺切分」4 筆（候選 1–4；預設答案全是既有機制套用，否決風險最低） | +4 | **48/50** |
| 上行＋d029 距離裁決落地（候選 5） | +5 | **49/50** |
| 上行＋判型/同義詞類再過 1 筆（候選 6–10 任一） | +6 | **50/50 達標** |
| 10 筆全過 | +10 | **54/50**（餘裕 4，吸收個別否決） |

- **達標最低組合＝候選 1–5 全過＋候選 6–10 任一過**；候選 6–10 的否決風險
  集中在判型/同義詞裁決（IE 可能給不同建模），這正是留 5 筆餘裕的原因。
- 誠實邊界一：達標批次裡預計含 **1–2 筆 incomplete 型**（候選 4、可能候選 5）——
  它們是「IE 裁決過的資訊不足記錄」，不是帶工時案例；P0 的 50 筆計數對此不區分
  （g42–g49 前例），但報告引用時應分開陳述帶工時/誠實 incomplete 的構成。
- 誠實邊界二：候選 6/8/9（`ie_modified: true`）轉正後 **Plan 層指標會動**
  （plan_metrics_n 6→最多 9；單 action、span 同 planner 輸出→accuracy 預期
  0.3333→約 0.55）——這是真 ground truth 進分母的合法變動，不是自我指涉假象；
  釘值測試（`_seed_gold_baseline.py`／`test_planner_eval.py`）需同批更新並在
  worklog 記數字。
- 誠實邊界三：若 IE 否決超過 4 筆，本池衝不到 50——剩餘草稿的卡點是工程票
  （d002 F 票）、無動詞面（5 筆）與開放建模題，都不是快答可解；屆時缺額回到
  harvest-summary 的既有結論：需 IE 提供真實工單補件，不湊數。

---

## 六、答案落地流程（工程端，全程留痕）

1. 切分批次確認 → `review-state.json` 增補/新增 entry
   （`segmentation_source: no_contention_batch_confirmed`；既有 entry 只加切分
   面向，不動已確認面向）→ harvest 合併。
2. 同義詞（下壓/按下）→ `POST /api/v2/rule-sets/MINIMOST_FACTORY_V2/synonyms`
   登記（IEC141289、priority 0）→ harvest `--force` 重跑 → 新判型旗依 IE 同輪
   答案落 typing 面向。
3. 判型答案（acquire/move_place）→ 照 D3-022 工作流：edit plan
   （`review_status: ie_edited`）→ `--recompile` → entry 宣告 `ie_modified: true`。
4. d029 距離裁決 → distance-rulings.md C11 落地（補距離走 ie_edited＋recompile；
   維持資訊不足走 `zero_tmu_ruling`＋`expected_incomplete_reason`）。
5. 整批 `--promote`（資格＝`promotion_blockers` 唯一出處；一筆不合格＝一筆都不寫）
   → 釘值更新（`PROMOTED_GOLD_N`、COMPLETE_TMU、plan 指標）→ 全套測試綠才回報。

---

## 七、IE 答案與落地結果（D3-028，2026-08-17，IEC141289）

### 逐題答案

| 快答題 | 候選 | IE 答案 | 落地 |
|---|---|---|---|
| **Q1** | 1／2／3（`1dd7c1d5`／`6be614c5`／`2e7b2e5a`） | **OK**：三筆併入無爭點批次切分確認 | 轉正 → `g50_press_function_test_fixture`／`g51_press_dimm_latch_to_position`／`g52_press_button_template`，各帶真 TMU **3.0**（`A0 B0 G0 M3 X0 I0 A0`，m_press） |
| **Q2** | 4（`51518399` 貼附Label到主板規定位置處） | **OK**：切分批次確認 | 轉正 → `g53_attach_label_to_board_position`，**誠實 incomplete**（`distance_unstated`，D3-019 已裁，本輪只補切分面向） |
| **Q3** | 5（`7f085e02` 撕除螢幕保護膜） | **維持**——IE 原話「**維持不考慮要撕多遠**」 | 距離裁決落地為 `zero_tmu_ruling: distance_unstated`（**不是補距離**）＋切分批次確認 → 轉正 `g54_tear_screen_film`，誠實 incomplete。`distance-rulings.md` C11 標「已裁：維持」，該表待裁筆數 11→0 |
| **Q4** | 7（`0e83128f` 下壓 CPU 拉桿鎖定）、10（`00104439` 按下電源測試按鈕） | **不登記同義詞** | 兩筆**留草稿**，卡點記為「**動詞不在字典標籤內、無 IE 裁決**」。本輪據此立同義詞登記準則＋機械守門（見下） |
| **Q5** | 6（`28f9ed7e`）、9（`8ef772ab`）、8（`37fbd2a6`） | **OK**：`28f9ed7e`→acquire、`8ef772ab`→acquire、`37fbd2a6`→move_place＋機構件 `p_place_single` | 三筆 `review_status: ie_edited` → `--recompile` → entry 宣告 `ie_modified: true` → 轉正 `g55_pick_screw_x1`（10.0）／`g57_lh_pick_screw_from_box`（10.0）／`g56_place_heatsink_on_cpu`（16.0，`A0 B0 G0 A0 B0 P16 A0`） |
| **Q5 後續**（取而無放歸宿） | 6（`28f9ed7e`）、9（`8ef772ab`） | **D3-029 改判**：IE 否決工程推定的單一 token（原話「**不一定都會是下一步才有放，要看是什麼物件也要看是什麼動作**」），改裁**四類歸宿**；兩筆螺絲句＝`consumed_by_later_action` | `g55`／`g57` 的 `acquire_lint_ruling`：`place_in_next_row` → **`consumed_by_later_action`**（IEC141289，2026-08-17）；notes 補 v3 三列結構證據；推定與撤回過程記在 review-state 的 `ruling_history`（`superseded_rulings` 型）。兩筆**不撤回**，P0 維持 52/50 |

**未出題的備位候選**（`35372a96` 對準、`1a9be08f` 壓合、`cc6c7d56` 貼上、
`633b52bb` 掰開）本輪未動——衝線目標已達（52 > 50），不為湊數擴大提問面。

### 對 §五「誠實預估」的對帳

| §五情境 | 預估 | 實際 |
|---|---|---|
| 候選 1–4 過 | 48/50 | ✅ 全過 |
| ＋候選 5（距離裁決） | 49/50 | ✅ 過（答案是「維持」不是「補距離」，仍解鎖轉正） |
| ＋候選 6–10 任一 | 50/50 達標 | ✅ 候選 6/8/9 **三筆全過** |
| 候選 7、10 | （預估可過） | ❌ **未過**——IE 不登記同義詞（§三預設答案「下壓→`m_press`」「按下→`m_btn`」被推翻） |
| **合計** | 最多 54/50 | **52/50** |

§五「誠實邊界一」兌現：達標批次含 **2 筆 incomplete 型**（g53／g54），
另 6 筆帶引擎真 TMU（3.0×3、10.0×2、16.0×1）——引用時分開陳述。

### 兩個提問時未預見的工程結果（誠實補記）

1. **候選 7／10 的預設答案被推翻的理由，比「這兩個詞不對」更重要**：IE 反問
   「動詞應該要按照 most 字典庫去查吧？」——查證 22 條既有登記，**21 條的詞
   本身就與該 option 的標籤/句面文字有子串關係**，唯一例外「插入」有明確 IE
   裁決（D3-021）。「下壓≈按壓」「按下≈按動按鈕」字典查無，屬工程端相似性
   判斷。據此立準則（**同義詞登記的合法來源只有：標籤衍生 或 IE 裁決；工程端
   不得以相似性自行判定**）＋機械守門，寫進 ADR-023 §3.3 規則 1 補節二。
   v3 認證字典**無 alias 欄位**可匯入（欄位名已逐一查證）。
2. **候選 6／9 判成 acquire 之後，`acquire_without_place` 旗標必然出現**——
   該旗標自 D3-014 起就是「未解決的覆核提問」（README 轉正資格明列它是
   blocker），但**先前沒有記錄答案的地方**，答了也照擋。本輪補上
   `acquire_lint_ruling`（當時定為唯一合法值 `place_in_next_row`＝「『放』在
   下一句/下一列」，g01 前例）。**誠實揭露**：這個答案不是 IE 在本輪被單獨
   問到的，而是取自候選 6 預設答案的字面「單純取料、**放在後續列**」與候選 9
   的結構證據（wi-template 版本的 rows[0]，後續列在同一版本內），IE 對兩題都
   答 OK。

   > **後記（D3-029，2026-08-17）：上面這段「誠實揭露」的風險兌現了。**
   > IE 看過後**否決**單一 token——「不一定都會是下一步才有放，要看是什麼
   > 物件也要看是什麼動作」——改裁四類歸宿（`placed`／
   > `consumed_by_later_action`／`tool_held`／`genuinely_missing`）。
   > 兩筆螺絲句正確答案是 **`consumed_by_later_action`**：螺絲**沒有獨立的
   > 「放」**，它的「放」被後續的鎖附動作消耗。反證其實一直在同一份 v3
   > 證據裡（rows[1] 右手起子 `p_hold` 保持住＝根本不放，rows[2] 鎖附消耗
   > 螺絲），D3-026 查 D 型接續配對時就看過，上輪卻沒拿它檢驗自己的 token。
   > **`place_in_next_row` 已撤回**（只在 `ruling_history` 裡合法），兩筆
   > 改判、不撤回轉正。詳見 README「取而無放的四類歸宿」節與 worklog D3-029。

### Plan 層指標的逐筆變因（§五「誠實邊界二」兌現）

`ie_modified: true` 的三筆（g55／g56／g57）**進分母**，plan_metrics_n **6 → 9**：

| 案例 | action 數（gold/planner） | action_count 命中 | boundary span F1 |
|---|---|---|---|
| `g55_pick_screw_x1` | 1 / 1 | ✅ | 1.0（span `[0,7)` 未改） |
| `g56_place_heatsink_on_cpu` | 1 / 1 | ✅ | 1.0（span `[0,12)` 未改） |
| `g57_lh_pick_screw_from_box` | 1 / 1 | ✅ | 1.0（span `[0,11)` 未改） |

→ action_count accuracy **0.3333 (2/6) → 0.5556 (5/9)**；boundary micro
**(tp2,fp4,fn9) → (tp5,fp4,fn9)**、F1 **0.2353 (4/17) → 0.4348 (10/23)**。

**這是真 ground truth 進分母的合法上移，但證據力要說清楚**：IE 在這三筆改的是
`action_type`（判型），**action 數與 evidence span 維持 planner 輸出未動**——
所以那 3 分 boundary 是「planner 自己的 span 經 IE 覆核未改」，弱於 D3-022 重切
族（IE 真的重畫了邊界，且 rule planner 必然拿 0）。橡皮圖章回歸
（`test_rubber_stamp_promotion_does_not_move_plan_metrics`）仍綠——未修改者
（本輪 5 筆 `ie_modified: false`）照樣排除，46 筆自我指涉排除。
