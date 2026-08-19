# MiniMOST Sequence Model — 核心邏輯規格（Core Logic Spec）

> ## ⚖️ V2 修訂（ADR-014，2026-07-05 起生效——本節為權威，與下文衝突時以本節為準）
>
> **值權威**＝`docs/v3/reference/minimost_ai_dictionary_v1.json`（IE 認證字典）；rule-set **`MINIMOST_FACTORY_V2`**（由 `scripts/import_v3_dictionary.py` 程式轉換產生，禁手抄）。V1 僅供既有 cycle 快照回放。已實作並由黃金測試鎖定（pytest 57／validators 82+26+54 全綠）。與下文 V1 敘述的差異：
>
> | # | 變更 | V1（下文舊敘述） | **V2（現行權威）** |
> |---|---|---|---|
> | C1 | M 距離階梯單位 | ≤1/4/10/18/30「cm」→3/6/10/16/24、>30→42 | 門檻是吋，cm 正確值 **≤2.5/10/25/45/75**→3/6/10/16/24；**無 overflow，>75 → 422 M_DISTANCE_RANGE**。黃金 CM=29 的「推 18」＝18 吋＝45cm |
> | C2 | M 腳步 | 同 M 階梯（§4.5 舊文「同 A 腳步帶」為筆誤） | **獨立帶** ≤25/40/55/75→10/16/24/32、>75→42（`rule_m_foot_bands`） |
> | E2 | X 捨入 | `ceil(sec/0.036)`（舊 Q3 裁決，superseded） | **half-up 3 位**（10s→277.778；0.216s→6.000） |
> | C6 | G 修飾 gating | 未勾修飾→0 | **移除**（選項即完整語意；V2 資料 requires_modifier=false，引擎邏輯保留讀資料） |
> | — | P 對準精度 | 勾「精度<4mm」才 +8 | 選項自含精度語意，**直接 +8**；新增 **插入⊥卡合 → P_ADDON_CONFLICT**、**有附加無 base → P_ADDON_NO_BASE** |
> | E1 | A3 返回格 | 三分量取 max | **僅計伸手**；twist/foot 非零 → 422 A_RETURN_COMPONENT |
> | C5 | I 檔位 | 4 檔（0/6/10/16） | **八檔＋i_none**：檢查/確認×正常 6、對準到點 10、對齊兩點 16、視線外 16/16/24/32（`vision_scope`） |
> | C5 | X 檔位 | 4 檔 | **九檔＋x_none**（壓合/卡合&壓合/熱熔/點膠/鎖附 0.216→6/鐳雕/刷PPID/刷工單/刷條形碼） |
> | — | 旋轉/手度 | >12.5 無上限、3 圈檔 | 直徑≤50 封頂、大直徑無 3 圈檔（→422 M_ROTATION_RANGE）；手度 ≤180 封頂（→422 M_HAND_RANGE） |
> | — | 手度/腳步的地位 | 與動詞同列，可單獨成格 | 字典的 `M.controls` 是三個平行控制群，`verb` **required=true**：手度/腳步是**伴隨維度**，必須與動詞併用（單獨成格 → 422 **M_COMPANION_WITHOUT_VERB**；併用照常取 max），且**不入敘事句**（字典的 hand_degree/foot_step 選項全無句面）。詳見 [ADR-028 §2 A8](../decisions/ADR-028-most-engine-boundary-validation-and-single-authority.md) 與 [ADR-032 D7.6](../decisions/ADR-032-bilingual-ui-and-data-label-layer.md) |
> | E4 | slot repeat | 無 | G/P/X/I 整格 ×repeat（1..99）；**M 僅乘動詞分量再 max**；A/B 禁用 |
> | E7 | 人工覆寫 | 無 | slot `manual_override{tmu,reason,by}`：值取代＋留痕＋tech_line 標 `*` |
> | E5 | SIMO 輸入 | 顯式 simo_group_id | ＋`simo_with_row_id` 配對輸入（僅從屬列標記，主列不標記）；**ADR-020：標記列貢獻 0**（舊「群組取 max」廢止） |
> | — | 寬放 | 無 | worksheet 級 `allowance_percent`（standard=normal×(1+%/100)；見 data-model §2.5） |
>
> 實作權威＝本規格＋[ADR-014](../decisions/ADR-014-v3-dictionary-as-value-authority.md)＋IE 認證字典；可執行規格＝`src/ddm_v2/most_engine/`、`tests/unit/test_most_engine.py` 與 `scripts/core_logic/minimost_sequence_validator.py`。


**文件類型：** 核心邏輯規格（Core Logic / Function Spec）
**版本：** **1.0 — 已確認核心**（低風險項採建議預設；待 IE 確認項見 [Level spec §14 統一清單](./level-system-core-logic-spec.md#14--需找人ie確認清單user-尚未回答須對外確認)）
**建立日期：** 2026-06-16　**升版：** 2026-06-16（v0.1→v1.0）
**範圍：** **MiniMOST only**（GM 一般移動、CM 控制移動兩種 sequence model）
**目的：** 在開始任何系統設計／開發之前，把「這個專案實際採用的 MiniMOST sequence model 計算邏輯」**逐格、逐表、嚴格**整理出來，並對齊三份來源資料的差異，作為後續核心邏輯驗證 script/skill 的依據。

> **✅ 已確認決策（2026-06-16，User）：**
> - **Q1：合計口徑＝工廠 Excel（`(Σindex) × system_tmu_multiplier`，**不乘 10**）；`1 TMU = 0.036 秒`。** 教科書 `×10` 僅參考。
> - **Q2：B 身體動作採 1205 的值（眼部 10／起身彎腰坐 32／站 42，加 B0＝0），且 B 必須真正計入**（補掉 JS 寫死 0 的 gap）。SEED 的 0/3/6/18 廢棄。
> - **Q5：1128（MiniMOST1128.xlsx）視為「工作指導書 WI 範本」，純參考，不是邏輯定義來源。** SIMO 不從 1128 的 Y/N 推導。

---

## 0. 來源資料與權威層級（必讀）

本規格交叉整理自三類來源。**它們彼此並不完全一致**，差異彙整於 [§8](#8-三來源差異對照待嚴格確認)。

| 代號 | 來源 | 角色 | 路徑 |
|------|------|------|------|
| **引擎** | `most_engine/` | **v2 權威計算引擎**（讀 rule-set 資料，非硬編） | [src/ddm_v2/most_engine/](../../src/ddm_v2/most_engine/) |
| **SEED** | `rule_set_seed_v2.py` | **由 IE 認證字典產生的 rule-set 種子值** | [src/ddm_v2/seed/v2/rule_set_seed_v2.py](../../src/ddm_v2/seed/v2/rule_set_seed_v2.py) |
| **1205** | `MOST系統邏輯1205.xlsx` → 工作表「MOST 系统逻辑」 | **完整 IE 主表**（最詳盡的階梯、進階放置、處理時間、詞彙庫、長敘事範例） | [docs/sample_excel/](../sample_excel/) |
| **詳解版** | `MOST邏輯詳解版.xlsx` | **WI 顯示導向的精簡教學表**（G/P/M/X/I 選項與顯示字樣規則） | [docs/sample_excel/](../sample_excel/) |
| **1128** | `MiniMOST1128.xlsx` → 工作表「1126」 | **WI 表（工時表）範例**：一列＝一個方法步，含 SUB/Key Parts/HAND/METHOD/SEQUENCE/Freq/SIMO/TMU 欄 | [docs/sample_excel/](../sample_excel/) |

> ⚠️ **與標準教科書 MOST 的關係：** 本專案的 MiniMOST 是工廠客製化表，其 G/P/I 等索引值與教科書 MiniMOST 不同（見 [§8.1](#81-本專案-minimost-vs-教科書-minimost重大)）。依 ADR-014，本規格與 IE 認證字典是本系統權威；教科書只作歷史比較，不可覆蓋工廠值。

**事實基準：** 以 ADR-014 的 IE 認證字典、`MINIMOST_FACTORY_V2` 與唯一引擎為準；1205/詳解版/1128 是驗證與敘事參考。歷史差異保留於 §8 供查核。

---

## 1. 三個層次與本規格範圍

| 層 | 名稱 | 說明 |
|----|------|------|
| A | 方法論層 MOST | IE 的動作分解語言，以 TMU 量化。 |
| **B** | **Sequence Model** | **一次動作循環的固定字母序列。本專案＝GM 與 CM 兩種。本規格描述此層。** |
| C | ddm-v2 產品 | 實作 B 層的軟體（API/DB/UI）。本規格**不**描述產品實作，只描述其應遵循的邏輯。 |

**範圍界定：**
- 僅 **MiniMOST**；僅 **GM（一般移動）** 與 **CM（控制移動）** 兩種 sequence model。
- 不含 BasicMOST Tool Use / Equipment Use、MaxiMOST。
- 「一條 cycle」＝整段動作以**一組** GM 或 CM 的七格填完（與 1128 WI 表「一列＝一方法步」是不同層次；WI 表是多列，每列各自一條 cycle）。

---

## 2. 七格模型與字母順序（不可變）

每個 sequence model 固定 **7 個 slot**（index 0…6），字母順序**不可更改**。使用者選 GM 或 CM 後，slot 3／4／5 的語意不同。

| slot | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|------|---|---|---|---|---|---|---|
| **GM** | A | B | G | A | B | P | A |
| **CM** | A | B | G | M | X | I | A |

- **GM 取得段**＝slot 0–2（A B G）；**放置段**＝slot 3–5（A B P）；**返回**＝slot 6（A）。
- **CM 取得段**＝slot 0–2（A B G）；**控制段**＝slot 3–5（M X I）；**返回**＝slot 6（A）。
- CM 序列中**不出現 P**；GM 序列中**不出現 M/X/I**。

> SEED 對應：`minimost_sequence_kinds`（`sequence_code IN ('GM','CM')`）＋ `minimost_sequence_slots`（`slot_index`, `letter IN ('A','B','G','P','M','X','I')`, `ui_step_group`）。

---

## 3. TMU 與合計規則

| 換算 | 值 |
|------|----|
| 1 TMU | = 0.036 秒 |
| 1 秒 | ≈ 27.8 TMU |

**單格貢獻：** 每個 slot 依其字母規則（[§4](#4-各參數-slot-計算規則)）算出一個 **index/TMU 值**。

**一條 cycle 合計：**
```
cycle_total_tmu = ( slot0 + slot1 + slot2 + slot3 + slot4 + slot5 + slot6 ) × system_tmu_multiplier
cycle_total_seconds = cycle_total_tmu × 0.036
```
- `system_tmu_multiplier`：來自 rule set，教學範例＝**1**（SEED：`minimost_rule_sets.system_tmu_multiplier = 1`）。
- **多列 WI（1128）整表合計：** `Σ ( cycle_total_tmu × frequency )`（僅計未帶 SIMO 標記的列；SIMO 標記列貢獻 0，見 [§6](#6-simo-與-frequency)／ADR-020）。

> ⚠️ **與教科書差異：** 標準教科書通式常以 `(Σ index) × 10` 表達。本專案依 ADR-014 **不乘 10**，改乘版本化 `system_tmu_multiplier`（目前＝1），且各格值本身即為 TMU 貢獻。此裁決已由黃金測試鎖定。

---

## 4. 各參數 slot 計算規則

> 以下「現況數值」以 **JS + SEED** 為準；「完整表」欄標註 **1205** 的更完整內容；差異彙整於 [§8](#8-三來源差異對照待嚴格確認)。

### 4.1 A — Action Distance（伸手／手度／腳步，取 max）

A 格由三個**分量**組成，各自查表得 index，**取最大者**為該格貢獻（1205：「单选取较大值」）。

```
A_index = max( reach_index, twist_index, foot_index )
```

**伸手 reach（距離 cm）— JS `A_REACH_BANDS`：**

| 上界 cm | ≤2.5 | ≤5 | ≤10 | ≤20 | ≤35 | ≤60 | >60 |
|---------|------|----|----|----|----|----|----|
| index | 0 | 1 | 3 | 6 | 10 | 16 | 24 |

**手度 twist（角度°）— JS `A_TWIST_BANDS`：**

| 上界° | ≤30 | ≤60 | ≤120 | ≤180 |
|-------|-----|-----|------|------|
| index | 0 | 1 | 3 | 6 |

**腳步 foot（距離 cm）— JS `A_FOOT_BANDS`：**

| 上界 cm | ≤20 | ≤30（一步） | ≤45 | ≤65 | >65（兩步） |
|---------|-----|------------|-----|------|------------|
| index | 6 | 10 | 16 | 24 | 32 |

- 值 `≤0` 的分量視為不存在（不貢獻）。三分量皆無 → A0（0）。
- **CM 專屬：** 1205 註記「有選手度則一定要有『翻轉』＋『目標物』」（JS 以 `flip` + `flip_target` 實作；屬敘事必填，不影響 TMU）。

> ⚠️ **SEED 與 JS 的 A 帶不一致**（待對齊，見 [§8.2](#82-seed-vs-js-的數值落差)）：SEED `a_rows` 為 `≤0→0, ≤3→1, ≤8→3, ≤20→6, ≤28→10, ≤45→16, ≤60→24, ≤80→32`，與 JS 的 cm 門檻不同（且 SEED 為單一距離帶，未顯式分 reach/twist/foot）。

### 4.2 B — Body Motion（身體動作，單選）✅ 已定（採 1205）

**權威值（1205，已確認）：**

| 選項 | index（TMU） |
|------|:--:|
| 無身體動作（B0） | 0 |
| 眼部動作 | 10 |
| 起身或彎腰／坐 | 32 |
| 站立 | 42 |

**計算規則：** B 為單選，取所選選項的 index 作為該格（slot1／slot4）貢獻；預設 B0＝0。

> ✅ **已確認（2026-06-16）：** 採 **1205 的值（0／10／32／42）**，且 **B 必須真正計入計算**——目前 JS 把 slot1/slot4 寫死 0 是 **bug 等級的 gap，須修正**；SEED 的 0/3/6/18 **廢棄**。
> ⏳ **仍待 User 補充：** ①除上述四項外是否還有其他 B 選項？②「何時選哪一級」的判定規則（例：彎腰取料→32）。
> 敘事規範：B 非 0 時必須轉成具體身體語，不可只寫「B32」。

### 4.3 G — Gain Control（取得控制，單選；部分需勾修飾）

JS `G_OPTIONS` / SEED `g_rows`（兩者一致）：

| 動詞 | 修飾（modifier） | 需勾修飾才計入 | base TMU |
|------|------------------|:--:|:--:|
| 輕按 / 接觸 / 輕拍 | 接觸 contact | ✓ | 3 |
| 抓握 / 抓取 / 重新抓握 | —（無修飾） | | 6 |
| 換手 | 轉移 transfer | ✓ | 10 |
| 拿取（選取） | 選取 select | ✓ | 10 |
| 拿取（選取-小） | 選取（小） select_small | ✓ | 16 |
| 拔出 | 分離 separate | ✓ | 16 |
| 拿取（收集） | 收集 collect | ✓ | 24 |

**計算規則（JS `slotTmus` slot2）：**
```
若 未選 G 動詞                          → 0
若 該動詞 requires_modifier 但未勾修飾  → 0   （計為未完成，不計分）
否則                                    → base_tmu
```

> ⚠️ **與教科書差異（重大）：** 教科書 MiniMOST 的 G 索引為 `0,1,3,6`；本專案為 `3,6,10,16,24`，語意分類（接觸/抓握/轉移·選取/選取小·分離/收集）也不同。詳見 [§8.1](#81-本專案-minimost-vs-教科書-minimost重大)。

### 4.4 P — Placement（放置，**僅 GM**；單選 base ＋ 附加 ≤2）

**Base（JS `P_BASES` / SEED `p_base`，一致）：**

| 動作 | 方向 | base TMU |
|------|------|:--:|
| 丟 | — | 3 |
| 保持住 | — | 3 |
| 放 | 無方向 | 6 |
| 放 | 多種方向 | 10 |
| 放 | 一種方向 | 16 |
| 組 | 多種方向 | 10 |
| 組 | 一種方向 | 16 |

**附加 add-on（JS `P_ADDONS` / SEED `p_addons`，一致；最多選 2）：**

| 附加 | Δ TMU | 條件 |
|------|:--:|------|
| 對準 | +8 | **需勾「精度 <4mm」才 +8**，否則不加（JS `needsPrecision`） |
| 插入 | +8 | — |
| 較難處理 | +8 | — |
| 卡合 | +16 | — |
| 施加壓力 | +16 | — |

**計算規則（JS `slotTmus` GM slot5）：**
```
P = base_tmu
  + Σ( addon.delta )  for each selected addon (≤2)
     其中 對準(needsPrecision) 僅在 precision=true 時才加
```
WI 顯示字樣規則（詳解版）：對準會顯示「對準＋Verb.」（如「對準組」）；插入/卡合顯示字樣；較難處理/施加壓力**不**顯示字樣。

> ⚠️ **P base 與 1205 不一致：** 1205 的 base 為 `丟0、保持住3、放6/10/16、組24/32、複選42、對準54、66…` 並另有「精確放置」升級索引模型；JS/SEED 採用的是**詳解版的精簡值**（丟3、組10/16）。見 [§8.3](#83-p-放置三來源差異)。

### 4.5 M — Controlled Move（控制移動，**僅 CM**；可多分量，取 max）

一個 M 格可含多個分量（verb ＋ 距離/角度/圈數…），各自算 partial TMU，**取最大者**（1205：「单选取较大值」）。
```
M = max( partialM(component) for component with verb )   ；無分量 → 0
```

**M 動詞與計價方式（JS `M_VERBS` / SEED）：**

| 動詞 | 計價 kind | 規則 |
|------|-----------|------|
| 按動按鈕 | 固定 | 3 |
| 滑出螺絲 | 固定 | 3 |
| 理 / 穿 / 推 / 拉 / 貼附（+1205：去除/撕除/折/擦拭/撕开） | 距離階梯 | 見下「距離階梯」 |
| 旋轉 | 旋轉 | 直徑≤12.5cm：1圈16 / 2圈32 / 3圈42；直徑≤50cm：1圈24 / 2圈42 |
| 手度 | 角度 | ≤90°→6；>90°（≤180°）→10。⚠️ **伴隨維度，不可單獨成格**（頂部修訂表） |
| 腳步 | 距離階梯（腳） | ⚠️ V1 文（筆誤）；V2＝獨立腳步帶（頂部修訂表 C2）。同為**伴隨維度** |

**距離階梯：⚠️ 本表為 V1 舊值（把吋數誤存為 cm）——V2 權威值見頂部修訂表 C1（≤2.5/10/25/45/75 cm，無 overflow）。**

| 上界 cm（V1 舊） | ≤1 | ≤4 | ≤10 | ≤18 | ≤30 | >30 |
|---------|----|----|----|----|----|----|
| TMU | 3 | 6 | 10 | 16 | 24 | 42 |

> 旋轉圈數 JS 夾在 1–3 圈；1205 另有更多圈數與直徑組合。

### 4.6 X — Process Time（處理時間，**僅 CM**）

JS `X_OPTIONS`：

| 選項 | 模式 | TMU |
|------|------|-----|
| 無機台等待 | zero | 0 |
| 並壓合機台 / 並熱熔機台 | 輸入秒數 | `ceil(seconds / 0.036)` |
| 刷條碼（固定 0.216s 類） | fixed | `ceil(0.216 / 0.036)` = **6** |

```
secToTmu(sec) = (sec<=0) ? 0 : ceil(sec / 0.036)
```
1205 對 X 另有一張**離散 index 階梯**（並压合/卡合/热熔/点胶/锁附/镭雕/刷PPID/刷工单/刷条形码…），以及 (0.216S) 固定類。JS 採**連續 ceil 換算**，未用離散階梯。

> ⚠️ **與教科書差異：** 教科書 X 表是「找出秒數 ≥ 觀測時間的最小 index」的離散查表；本專案 JS 直接連續 `ceil(sec/0.036)`。見 [§10 Q3](#10-待確認問題-open-questions)。

### 4.7 I — Alignment（對齊，**僅 CM**，單選）

JS `I_OPTIONS`：

| 選項 | TMU |
|------|-----|
| 不額外對齊 | 0 |
| 並檢查（正常視線） | 6 |
| 並對準（正常視線·到點） | 10 |
| 並對齊（正常視線·到兩點） | 16 |

1205 更完整：檢查/確認/對準/對齊 × 正常視線範圍內外 × 到點/到兩點 → 6 / 10 / 16 / 24 / 32。

> ⚠️ **與教科書差異：** 教科書 I 為 `0,1,3,6`。見 [§8.1](#81-本專案-minimost-vs-教科書-minimost重大)。

---

## 5. 敘事（Narrative）規則

### 5.1 敘事公式（1205）

```
GM：  從 + "從哪裡" + (A+B) + G + 對象/目標物 + (A+B) + P + A + "到哪裡"
CM：  從 + "從哪裡" + (A+B) + G + 對象/目標物 + M + X + I + A + "到哪裡"
```

### 5.2 敘事主數據（嵌在流程，非 slot 字母）

| 角色 | kind | 必填性 | 出現位置 |
|------|------|--------|----------|
| 作業物件 object | object | **必填** | 取得段第一格之前 |
| 自 / 來源 from | target | 選填 | 取得段第一格之前 |
| 手勢 hand | hand | 選填 | 取得段第一格之前 |
| 至 / 目的地 to | destination | 選填 | GM：放置前；CM：移動啟動前 |

### 5.3 敘事撰寫規範（Action Narrative Protocol）

- **嚴禁**碎片化單字拼貼；須組成可朗讀的完整語句。
- A 轉化為「伸／移約 X 公分」，不直接唸內部 index。
- B 非 0 時必須寫出具體身體語，不得只寫「B3」。
- G／P 以自然語帶出取得方式／放置方式（必要時含精度語意）。

| 判定 | 例句 |
|------|------|
| **NG** | 取得 30cm，抓取，放置 10cm，丟。 |
| **Good** | 用右手從工具箱伸手約 30 公分，以接觸方式取螺絲起子，隨後移動約 10 公分，在回收桶邊以「丟入」方式完成放置。 |

> 1205 第 96–117 列有大量**完整 WI 長敘事範例**（含 `(伸手60cm)`、`[…](*n)` 重複記號），可作為敘事產生器的黃金測試集。

---

## 6. SIMO 與 Frequency

- **Frequency（Freq.）：** 1128 WI 表每列有 `Freq.` 欄；該方法步 TMU 乘以次數。教學 1128 多為 1，亦見 11、3。
- **SIMO（ADR-020，2026-07-13，對齊 v3 認證語義）：** 帶 SIMO 標記（`simo_group_id` 非空）的列**貢獻 0**——其時間由未標記的主列吸收；主列不得標記，僅從屬列標記（`simo_group_id` 的意義＝「SIMO 標記＋配對資訊」，非群組配對鍵）。
  ```
  total = Σ(未標記列 tmu × freq)    ← SIMO 標記列一律計 0
  ```
  舊語義「同一 SIMO 群組取群組內最大 TMU」已由 ADR-020 廢止（該語義對應 v3 舊層實作，非現行認證版）。
- 配對輸入 `simo_with_row_id`（E5）由 service 正規化：僅宣告配對的從屬列標記 `simo_group_id`，被指向的主列不標記。

---

## 7. 完整教學範例（驗收基準）

來自理解快照（與 JS 一致），`system_tmu_multiplier = 1`：

| slot | GM 範例 | 值 | CM 範例 | 值 |
|------|---------|:--:|---------|:--:|
| 0 A | 伸手 20cm | 6 | 伸手 25cm | 10 |
| 1 B | B0 | 0 | B0 | 0 |
| 2 G | 抓握類 | 6 | 接觸 G3 | 3 |
| 3 | A 25cm | 10 | **M** 推 30cm | 16 |
| 4 | B0 | 0 | **X** 無機台 | 0 |
| 5 | **P** 隨手放 | 6 | **I** 不對齊 | 0 |
| 6 A | 返回 A0 | 0 | 返回 A0 | 0 |
| **合計** | | **28 TMU** | | **29 TMU** |

> 技術列字串示例：GM `A6 B0 G6 A10 B0 P6 A0`；CM `A10 B0 G3 M16 X0 I0 A0`。
> ⚠️ **來源筆誤（驗證器發現）：** 理解文件把 CM 的 `M16` 標為「推 **30cm**」，但 §4.5 M 階梯 **30cm → 24**（≤18cm 才 →16）。故黃金 29 TMU 對應的是「推 **≤18cm**」；驗證 script 已用 18cm 還原 29，並另測 30cm→24。
> ⚠️ 注意 CM「伸手 25cm → 10」與 [§4.1](#41-a--action-distance伸手手度腳步取-max) JS 帶（≤35→10）一致，但與 SEED（≤28→10）也一致；GM「伸手 20cm → 6」JS（≤20→6）一致、SEED（≤20→6）一致。此範例可同時驗 JS 與 SEED A 帶（門檻差異落在 20–35 區間，需獨立測例覆蓋）。

---

## 8. 三來源差異對照（待嚴格確認）

### 8.1 本專案 MiniMOST vs. 教科書 MiniMOST（重大）

| 參數 | 標準教科書 MOST（歷史比較） | 本專案（IE 認證字典／V2 引擎） |
|------|------|------|
| 合計式 | `(Σ index) × 10` | `(Σ index) × system_tmu_multiplier`（＝1），**不乘 10** |
| G | 0, 1, 3, 6 | 3, 6, 10, 16, 24 |
| P | 0,1,3,6（+精密 10,16,24） | 3,6,10,16（+附加 +8/+16） |
| I | 0, 1, 3, 6 | 0, 6, 10, 16 |
| B | 0, 3, 6, 18 | JS 未計入；SEED 0/3/6/18；1205 為 10/32/42 |

→ **本專案 MiniMOST 是工廠客製表，與教科書 MiniMOST 不同。** 需 User 裁示：核心邏輯以工廠 Excel 為準（建議），教科書僅作參考。

### 8.2 SEED vs JS 的數值落差

| 項目 | JS | SEED |
|------|----|----|
| A 距離帶 | reach/twist/foot 三帶分開，門檻 2.5/5/10/20/35/60 | 單一距離帶，門檻 3/8/20/28/45/60/80 |
| B | 寫死 0 | 0/3/6/18 四選項 |
| G、P base、P addon、M 階梯 | 一致 ✓ | 一致 ✓ |

→ A 帶與 B 需對齊一個權威版本。

### 8.3 P 放置三來源差異

| 來源 | 丟 | 保持 | 放(無/多/一) | 組(多/一) | 進階 |
|------|----|----|----|----|----|
| JS/SEED/詳解版 | 3 | 3 | 6/10/16 | 10/16 | 附加 +8/+16（≤2） |
| 1205 | 0 | 3 | 6/10/16 | 24/32 | 複選42、對準54、66… + 精確放置升級索引 |

### 8.4 同一參數在不同 sequence 的占位

1128 WI 表中常見 `A0 B0 G0 …` 全 0 占位列（模板列），代表「該方法步尚未填值」，非真實 0 動作。驗證時需區分「模板占位」與「真實 A0」。

---

## 9. 現有程式碼對齊現況

| 元件 | 檔案 | 狀態 |
|------|------|------|
| 資料模型 | [models/v2/rule_set_tables.py](../../src/ddm_v2/models/v2/rule_set_tables.py) | rule set + A 帶 / B 選項 / G / P base / P addon / M 階梯 / M 動詞 / X / I 子表 |
| 種子 | [seed/v2/rule_set_seed.py](../../src/ddm_v2/seed/v2/rule_set_seed.py) | rule-set 種子值（值見 §4） |
| 引擎 | [most_engine/calculate.py](../../src/ddm_v2/most_engine/calculate.py) | 單一權威計算引擎（讀 rule-set 資料實作 §4 規則） |
| 遷移 | `migrations/versions/0015~0017` | MiniMOST catalog + cycles + 敘事 FK |

> 本規格**不**要求現在改程式；僅標出「規格 vs 現況」供後續驗證 script 使用。

---

## 10. 待確認問題（Open Questions）

| # | 問題 | 影響 | 狀態／決議 |
|---|------|------|----------|
| **Q1** | 合計式口徑 | 全部 TMU 數值口徑 | ✅ **已定：工廠 Excel（×multiplier，不乘 10）；1 TMU=0.036 秒** |
| **Q2** | B 身體動作索引值與是否計入 | B 格 TMU | ✅ **已定：採 1205 值（0/10/32/42）且必須計入**；⏳ 待補完整選項清單與選用規則 |
| **Q3** | X 處理時間：連續 ceil vs 1205 離散階梯 | X 格 TMU | ✅ **採連續 `ceil(sec/0.036)`＋固定 0.216→6**；1205 離散階梯列 Phase 2 選用 |
| **Q4** | A 距離帶：JS 三帶 vs SEED 單帶 | A 格 TMU | ✅ **採 JS 三帶（伸手/手度/腳步取 max）**；SEED 單帶須修正對齊 |
| **Q5** | SIMO 分組來源 | 整表合計 | ✅ **已定：1128 純參考，不作邏輯來源；SIMO 用顯式 `simo_group_id`**；⏳ 現場配對 UX→清單 C5 |
| **Q6** | P / G / I 是否先做 JS/詳解版子集 | 可選項範圍 | ✅ **Phase 1 先做子集**；1205 完整表（複選/精確放置/視線外）Phase 2 |
| **Q7** | 「>2.5cm 用 CM穿／≤2.5 用 GM組」選 model 規則是否入規格 | model 選擇 | ✅ **列為軟提示（warning），非硬性驗證** |
| **Q8** | 文件放置與登錄 | 文件治理 | ✅ **specs/ ＋ 登錄 DOC_REGISTRY** |

---

*本文件為草案，等待 User 對 §10 逐項確認後升版為 1.0。確認後即可據此撰寫「核心邏輯驗證 script/skill」的測試案例（§7 範例 + 1205 第 96–117 列長敘事為黃金集）。*
