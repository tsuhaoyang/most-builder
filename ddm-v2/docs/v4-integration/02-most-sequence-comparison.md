# 02 — MOST Sequence 限制逐格對照（v4 → v2）

> 本審查最重要的文件。目的：把 v4（`minimost_level/minimost/apps/api`）的 MiniMOST 計算引擎
> **逐格**對照 v2（`ddm-v2`）現行單一權威引擎，作為「整合不得污染 v2 黃金值」的依據。
>
> **硬性原則**：所有結論回到實際 code，證據標 `檔案:行號`。這是唯讀審查。
>
> 審查方法：實讀雙方引擎、字典、seed、golden test。v4 文件（docs）與 code 有落差，本文一律以 **code** 為準。

---

## 0. 前置結論：v4 到底用哪套計算？（任務要求 #1）

v4 倉庫裡存在 **三套** 與 TMU 計算相關的程式碼，必須先釐清哪一套是實際生效的：

| 引擎檔 | 模型 | 是否為現役 | 證據 |
|---|---|---|---|
| `app/services/calculation_v2.py` | **AI Dictionary v1**（tmu_value 驅動、七格 A/B/G/P/M/X/I、slot repeat、SIMO=0） | **是（現役）** | `app/api/routes/most.py:21` `from app.services.calculation_v2 import (...)`；`most.py:318` `calculate_slot_tmu(...)`。另 `app/api/routes/most_workbench_v3.py:25` 同樣 import `calculation_v2`。 |
| `app/services/calculation.py` | **index_value + rule_adjustment** 舊模型（`base_index + rule_adjustment`，SIMO 無此概念） | **否（近乎 legacy）** | 全庫只有 `app/api/routes/analysis.py:23` `from app.services.calculation import TMU_TO_SECOND`（只取常數，不呼叫計算函式）＋ `tests/test_calculation.py` 舊測試。無任何 route 呼叫其 `calculate_step()`。 |
| `app/services/most_workbench.py` | **sum(index_value)**、SIMO=`max`（第三套語義，與前兩套都不同！） | **孤兒（無 route 掛載）** | `grep most_workbench\|preview_sequence` 於 `routes/` **無任何匹配**。此 service 的 `preview_sequence`（`most_workbench.py:104`）用 `sum(index_value)`、`preview_mi_statement`（`most_workbench.py:176`）SIMO 用 `max(tmu_values)`。 |

**判定**：v4 現役計算引擎 = **`calculation_v2.py`**。以下逐格對照一律以 `calculation_v2.py` + `minimost_ai_dictionary_v1.json` 為 v4 基準。

> ⚠️ **整合風險（架構層）**：v4 內部就有三套語義互斥的計算路徑，且孤兒 `most_workbench.py` 的 SIMO 語義（`max`）與現役 `calculation_v2.py`（SIMO→0）**完全相反**。整合時只能採信 `calculation_v2.py`，其餘兩套必須明確排除，否則會把矛盾語義帶進 v2。

---

## 1. 資料表徵的根本差異（先講這個，後面每一格都受它影響）

這是兩套系統**最關鍵的結構差異**，決定了整合的難度：

| 面向 | v2 | v4 |
|---|---|---|
| 規則存什麼 | **band 定義**：component→`(max_value, index)` 帶，引擎收「原始量測值」（`reach_cm`/`twist_deg`/`distance_cm`…）後**查表求 index** | **pre-computed tmu_value**：每個 option 直接存 `tmu_value`，使用者**選 option**，引擎直接取值 |
| 引擎輸入 | 物理量（cm/度/圈數/秒） | 已選定的 option（含其 `tmu_value`） |
| 證據 | `rule_set_data.py:76` `band_index()`；`calculate.py:59` `_a_tmu` 讀 `reach_cm` 再 `rs.band_index("reach", ...)`；seed `rule_set_seed_v2.py:19` `A_BANDS = [('reach', 2.5, 0, 0), ('reach', 5.0, 1, 1), ...]` | `calculation_v2.py:75` `_calc_a` 直接 `selections.get("reach_distance").get("tmu_value")`；字典 `minimost_ai_dictionary_v1.json` A.reach_distance.options 每筆帶 `tmu_value` |
| multiplier | rule_set 有 `system_tmu_multiplier`（v2 seed=1，總計 `Σ×multiplier`）(`calculate.py:243`) | **無** multiplier 概念（`calculation_v2.py:236` `calculate_row` 直接 `Σ slot`） |

**整合含義**：v4 的 option `tmu_value` 表其實就是 v2 的 band 表「壓平後查好的結果」。兩者的**數值來源相同**（同一份 MiniMOST 官方值表），但 v2 保留了「原始量測 → band」這一層，v4 把它折進 option。整合時 v4 資料要能對映回 v2 band，或走 v2 的「已知 index」路徑。

---

## 2. 逐格對照（A / B / G / P / M / X / I）

### 序列格式（GM / CM）

| | v2 | v4 |
|---|---|---|
| GM 序列 | `("A","B","G","A","B","P","A")` | `A B G A B P A`，slots `[A1,B1,G,A2,B2,P,A3]` |
| CM 序列 | `("A","B","G","M","X","I","A")` | `A B G M X I A`，slots `[A1,B1,G,M,X,I,A3]` |
| 證據 | `calculate.py:24-25` `GM_LETTERS`/`CM_LETTERS` | `minimost_ai_dictionary_v1.json` sequence_models（GENERAL_MOVE / CONTROLLED_MOVE） |

**【相同】** 七格骨架、GM/CM 兩種模型、第 4 格（A2）與第 7 格（A3/返回）位置皆一致。
**【不同（命名）】** v4 slot key 為 `A1/A2/A3`（第7格叫 A3）；v2 以位置索引 0..6，第 7 格語義為「A_return」（`calculate.py:100` `_a_return_tmu`）。v4 曾有 migration `58a3d1cca6f1` 把 CM 的 `A2→A3` rename——這正是把「CM 第 4 格是 M、第 7 格才是返回 A」對齊；v2 從一開始 CM 第 4 格就是 M（`calculate.py:230`），無此問題。

---

### A 格（距離）

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| A1/A2 聚合 | `max(reach, twist, foot)` 的 band index | `max(reach_tmu, hand_tmu, foot_tmu)` | **相同（語義）** |
| A3/返回 | **僅 reach**，且 twist/foot 非零 → 報錯 `A_RETURN_COMPONENT` | **僅 reach**（`slot_key=="A3"` 直接 return reach_tmu），**不檢查** hand/foot | **不同（驗證強度）** |
| 負值 | `reach_cm<0` → `A_NEGATIVE` | 無負值檢查（tmu_value 由字典給，恆 ≥0） | **v2 有 v4 無** |
| 分量名 | reach / **twist** / foot | reach_distance / **hand_degree** / foot_step | **相同（語義，命名不同）**：v2 的 twist = v4 的 hand_degree（皆為手腕/手掌轉角） |
| 證據 | `calculate.py:59` `_a_tmu`、`calculate.py:100` `_a_return_tmu`（twist/foot 非零即報錯） | `calculation_v2.py:75` `_calc_a`（A3 只回 reach_tmu，其餘 max） | |

**A 值表比對（reach，證明數值同源）**：

| 條件 | v2 index | v4 tmu_value |
|---|---|---|
| ≤2.5cm | 0 (`rule_set_seed_v2.py:20`) | 0 (`A_REACH_LE_1_2_5CM`) |
| ≤5cm | 1 (`:21`) | 1 (`A_REACH_LE_2_5CM`) |
| ≤10cm | 3 (`:22`) | 3 (`A_REACH_LE_4_10CM`) |
| ≤20cm | 6 (`:23`) | 6 (`A_REACH_LE_8_20CM`) |
| ≤35cm | 10 (`:24`) | 10 (`A_REACH_LE_14_35CM`) |
| ≤60cm | 16 (`:25`) | 16 (`A_REACH_LE_24_60CM`) |
| >60cm | 24 (`:26`, overflow) | 24 (`A_REACH_GT_24_60CM`) |

→ **A 值表完全一致**。差異只在 v2 收 cm 查表、v4 收選好的 option。

> **整合風險（A）**：v4 A3 不擋 hand/foot，v2 擋。若 v4 資料直接灌入 v2，遇到「A3 帶了 hand/foot」的歷史列會被 v2 拒收（`A_RETURN_COMPONENT`）。需在遷移時清洗 A3 的伴隨分量，或以 v2 規則重算。這是「v2 較嚴」的正向差異，不會污染黃金值，但會擋下 v4 的髒資料。

---

### B 格（身體動作）

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 聚合 | 單選 → index | 單選 → tmu_value | **相同** |
| 預設 | 有 `b_default`（golden 用 b_none=0） | 無「none」選項，`allow_none:false`（字典 B.selection） | **不同（預設語義）** |
| 未知 code | `B_UNKNOWN` 報錯 | 無（選單驅動） | **v2 有 v4 無** |
| 值 | 站=42（golden `engine_golden_test.py:79`） | 站=42（`B_STAND`）、彎腰/坐=32（`B_BEND_OR_SIT`）、眼部=10（`B_EYE_MOVE`） | **相同（值同源）** |
| 證據 | `calculate.py:129` `_b_tmu` | `calculation_v2.py:88` `_calc_simple_select` | |

**【不同】** v2 B 有 `b_none`（預設 0），GM golden 依賴它（第 2、5 格 B=0）；v4 B 是必選、無 none。這是重要差異：v4 的 GM 一定要選 B（眼部/彎腰/站），而 v2 GM golden 的 B=0。

> **整合風險（B）**：v2 golden GM=28 的成立**依賴 B=0**（見 §4）。v4 若無 0 值 B 選項，直接把 v4 資料當 v2 GM 算會多出 B 的 TMU → **污染黃金值**。整合時必須為 v4 資料補「B=none/0」的對映，或明確標記 v4 的 B 必選語義不套用於 v2 golden 基準列。

---

### G 格（取得控制）

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 聚合 | 單選 → `base_tmu × repeat` | 單選 → `tmu_value × repeat_count` | **相同（含 slot repeat）** |
| gating（需勾修飾） | V2 資料全 `requires_modifier=False`；引擎仍保留 gating 邏輯（V1 相容） | **無 gating** 概念 | **v2 有 v4 無（但 V2 資料已停用）** |
| 未知 code | `G_UNKNOWN` | 無 | **v2 有 v4 無** |
| repeat | 支援（`_repeat`, `calculate.py:151`） | 支援（`get_slot_repeat_count`, `calculation_v2.py:55`） | **相同** |
| 值 | 抓握=6、接觸=3、選取-小=16（golden `:84-86`） | 抓握 `G_GRASP`=6、接觸 `G_TOUCH`=3、選取-小 `G_SELECT_SMALL`=16 | **相同（值同源）** |
| 證據 | `calculate.py:136` `_g_tmu` | `calculation_v2.py:60` (`G` → `_calc_simple_select × repeat`) | |

**【相同】** G 的核心（單選×repeat、值表）一致。**【差異】** v2 保留 gating 骨架但資料停用；v4 無此概念——整合時可忽略 gating（雙方實際都不用）。

---

### P 格（放置）— 最複雜、規則最需逐條核對

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 公式 | `base + Σ addon_delta`（再 ×repeat） | `base_action_tmu + Σ modifier_tmu`（再 ×repeat） | **相同** |
| 最多附加 | `p_addon_max`（seed=2）→ 超過 `P_TOO_MANY_ADDONS` | `>2` → 驗證錯誤「最多 2 個」 | **相同** |
| 插入⊥卡合 | `a_insert`+`a_snap` 同選 → `P_ADDON_CONFLICT` | `P_INSERT`+`P_SNAP_FIT` → 「插入與卡合不可同時選擇」 | **相同** |
| 有 addon 無 base | `P_ADDON_NO_BASE` 報錯 | 「P 有附加條件時必須選擇基礎動作」 | **相同** |
| 空 P | base 空且無 addon → 0 | base 空 → 0（blank P 貢獻 0） | **相同** |
| addon 重複 | `P_DUP_ADDON` 報錯 | **無**去重檢查 | **v2 有 v4 無** |
| precision gating | 引擎**保留** gating 骨架（`calculate.py:180` `if addon.needs_precision and not precision: continue`），但 **V2 資料集全部 addon `needs_precision=False`**（`rule_set_seed_v2.py:74-78`，5 筆第 4 欄皆 False）→ **實際從不觸發**，所有 addon 一律加總 | **無** precision 概念，所有 modifier 一律加總 | **相同（現行資料集下）**：gating 是停用的死碼，效果同 v4 |
| 證據 | `calculate.py:165` `_p_tmu`；資料 `rule_set_seed_v2.py:73-78` | `calculation_v2.py:95` `_calc_p` + `:150` `validate_selections` | |

**P 值表比對**：

| 項目 | v4 tmu | v2 對應 |
|---|---|---|
| 對準<4mm | 8 (`P_ALIGN_LT_4MM`) | `a_align`=8（`rule_set_seed_v2.py:74`；golden `:90` 組一種+對準=24＝16+8）✓ |
| 插入 | 8 (`P_INSERT`) | `a_insert`=8（`:75`） |
| 卡合 | 16 (`P_SNAP_FIT`) | `a_snap`=16（`:77`） |
| 組(一種方向) | 16 (`P_ASSEMBLE_ONE_DIRECTION`) | `p_asm_single`=16（`:69`） |
| 放(無方向) | 6 (`P_PLACE_NO_DIRECTION`) | `p_place_none`=6（`:65`，GM golden 用） |
| 較難處理(隱藏) | 8 (`P_DIFFICULT_HANDLE`) | `a_hard`=8（`:76`，display_rule=hidden） |
| 施加壓力(隱藏) | 16 (`P_APPLY_PRESSURE`) | `a_press`=16（`:78`，display_rule=hidden） |

v4 字典 P.examples：`組一種+對準+較難處理 = 32`（16+8+8），`放一種+對準+插入 = 32`（16+8+8），`放一種+對準+卡合 = 40`（16+8+16）。v2 golden `:90` 組一種+對準=24（16+8）與 v4 一致。

> **整合風險（P）**：
> 1. **precision gating（澄清：現行非風險）**：v2 引擎保留 `needs_precision` gating 骨架（`calculate.py:180-182`），但 **V2 認證資料集的 5 個 P addon 全部 `needs_precision=False`**（`rule_set_seed_v2.py:74-78`），故 gating **實際從不觸發**——所有 addon 一律加總，與 v4 行為**一致**。這是「code 保留、data 停用」的死碼（同 G gating）。**唯一風險**：若未來有人在 v2 rule-set 建立 `needs_precision=True` 的 addon，v2 會開始跳過未標 precision 的 addon，屆時才會與 v4 分歧。整合時應確認不引入這類 addon，或明確在 v4→v2 映射補 `precision` 旗標。
> 2. **addon 去重**：v4 無去重，v2 有（`P_DUP_ADDON`）。v4 的重複 addon 資料進 v2 會被擋——方向安全（v2 較嚴），但需清洗。
> 結論：**P 格在現行資料集下雙方 TMU 等價**（值表同源、gating 皆停用），非污染源；只有「未來新增 needs_precision addon」與「重複 addon 髒資料」兩個邊界要留意。

---

### M 格（控制移動）— CM 專屬，結構差異最大

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 聚合 | `max(動詞類分量×repeat, hand, foot)`；hand/foot **不乘** repeat | `max(verb_tmu×verb_repeat, hand_tmu, foot_tmu)`；hand/foot 不乘 repeat | **相同（語義完全一致）** |
| 動詞值來源 | **依 pricing_kind 查表**：`ladder`（距離→階梯）、`rotate`（直徑×圈數）、`fixed`（固定）、`hand`/`foot`（伴隨維度） | **每個 option 一個 tmu_value**：如 `M_推_LE_4_10CM`=6，直接存 | **不同（表徵）** |
| 距離超界 | `>75cm` 且無 overflow → `M_DISTANCE_RANGE` 報錯 | 選單只到 `<=30(75)`，**無超界概念**（選不到就沒有） | **不同（v2 有值域檢查）** |
| 手度超界 | `>180°` → `M_HAND_RANGE` | 選單只到 `<=180`，無超界 | **v2 有 v4 無** |
| 旋轉超界 | 直徑/圈數超表 → `M_ROTATION_RANGE` | 選單固定幾個 rotation option | **v2 有 v4 無** |
| 伴隨維度不得單獨成格 | `M_COMPANION_WITHOUT_VERB`（hand/foot 不能沒有動詞）(`calculate.py:224`) | **無此檢查**（max 三者，hand 單獨也能算） | **v2 有 v4 無（重大）** |
| 未知 verb | `M_UNKNOWN` | 無 | **v2 有 v4 無** |
| 證據 | `calculate.py:189` `_m_tmu`（含 §排序註解）；`rule_set_data.py:113` `ladder_tmu`、`:138` `rotation_tmu`、`:148` `hand_tmu` | `calculation_v2.py:108` `_calc_m` | |

**M 動詞值表比對（推 push，ladder）**：

| 距離 | v2 ladder index | v4 tmu |
|---|---|---|
| ≤2.5cm | 3 (`rule_set_seed_v2.py:82`) | 3 (`M_推_LE_1_2_5CM`) |
| ≤10cm | 6 (`:83`) | 6 (`M_推_LE_4_10CM`) |
| ≤25cm | 10 (`:84`) | 10 (`M_推_LE_10_25CM`) |
| ≤45cm | 16 (`:85`) | 16 (`M_推_LE_18_45CM`) |
| ≤75cm | 24 (`:86`) | 24 (`M_推_LE_30_75CM`) |

→ **M 動詞值表一致**。CM golden「推 45cm=16」在雙方皆成立（v2 `engine_golden_test.py:68`；v4 `M_推_LE_18_45CM`=16）。

> **整合風險（M）— 結構性最大**：
> 1. **值域檢查缺失**：v2 對 M 有完整的 `M_DISTANCE_RANGE`/`M_HAND_RANGE`/`M_ROTATION_RANGE`/`M_COMPANION_WITHOUT_VERB` 防呆（`calculate.py:194-233`，且有刻意的錯誤排序註解、由黃金反例鎖定）。v4 靠「選單選不到超界值」被動避免，無主動檢查。整合時，v4 資料本身在合法選單內，不會觸發 v2 的值域錯誤；但若 v4 未來擴充選單或允許自由輸入，進 v2 會被擋。
> 2. **hand/foot 單獨成格**：v2 明確禁止（伴隨維度必須配動詞）；v4 允許 max(0,0,hand) 這種。若 v4 有「只選了手度、沒選動詞」的 M 列，進 v2 會被 `M_COMPANION_WITHOUT_VERB` 擋。需清洗。
> 3. v4 把 v2 的 `M_FOOT` 獨立腳步帶（`rule_set_seed_v2.py:88`，≤25=10/≤40=16/…）與 M_HAND（≤90=6/≤180=10）壓進 option。數值需逐筆核對：v4 `M_HAND_LE_90`=6、`M_HAND_LE_180`=10 與 v2 一致；v4 `M_STEP_LE_10_25CM`=10、`M_STEP_LE_16_40CM`=16 與 v2 M_FOOT 一致。→ **M 伴隨維度值表也同源**。

---

### X 格（製程時間）— CM 專屬

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 秒→TMU | `Decimal(sec)/0.036` **ROUND_HALF_UP 3 位**（`rule_set_data.py:165` `seconds_to_tmu`；ADR-014） | `Decimal(sec)/0.036` **ROUND_HALF_UP 3 位**（`calculation_v2.py:129` `_calc_x`，`quantize(ROUND_TMU=0.001, ROUND_HALF_UP)`） | **相同（含 rounding 口徑）** |
| fixed / dynamic | mode=`fixed`（用 fixed_seconds）/ `seconds`（用 x_seconds）/ `zero` | `fixed_seconds` / `user_input_seconds`（seconds_source） | **相同（語義）** |
| dynamic 未填秒數 | `X_SECONDS_REQUIRED`；負值 `X_NEGATIVE` | 「必須輸入正數秒數」（`≤0` 報錯） | **相同** |
| repeat | 支援（×repeat） | 支援（×repeat_count） | **相同** |
| 證據 | `calculate.py:241` `_x_tmu` | `calculation_v2.py:120` `_calc_x` + `:160` validate | |

**X 值表比對**：v4 `X_SCREW_FIX` fixed_seconds=0.216 → 0.216/0.036 = **6 TMU**（字典明示 tmu_value=6）。v2 同公式同 rounding。**【相同】** X 是雙方**rounding 口徑最一致**的一格（都採 ADR-014 的 half-up 3 位，非舊 ceil）。

> **整合風險（X）**：低。公式與 rounding 完全一致。唯一注意：v4 X 選項的 fixed_seconds（0.216 等）要對映到 v2 rule_set 的 `x_options`（mode/fixed_seconds）。數值同源，可直接對映。

---

### I 格（對位/檢查）— CM 專屬

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 聚合 | 單選 → `index × repeat` | 單選 → `tmu_value × repeat_count` | **相同** |
| 未知 code | `I_UNKNOWN` | 無 | **v2 有 v4 無** |
| repeat | 支援 | 支援 | **相同** |
| 證據 | `calculate.py:249` `_i_tmu` | `calculation_v2.py:63` (`I` → `_calc_simple_select × repeat`) | |

v4 I 值：檢查/確認(正常)=6、對準(到點)=10、對齊(兩點)=16、檢查(範圍外)=16、對齊(範圍外兩點)=32。需與 v2 `I_OPTIONS` seed 逐筆核（CM golden 用 `i_none`=0，v4 無 none 選項——同 B 的差異）。**【差異】** v4 I 無「none/0」；v2 CM golden 依賴 `i_none`=0。

---

## 3. 跨格聚合、SIMO、頻率、rounding

| 規則 | v2 | v4 | 判定 |
|---|---|---|---|
| 單列 total | `Σ slot × multiplier`，round 3 位（`calculate.py:243`） | `Σ slot`（無 multiplier），`base_tmu` quantize 3 位（`calculation_v2.py:249`） | **相同（v2 multiplier=1 時）** |
| freq | `total × freq`；freq≤0 → `FREQ_INVALID`（`calculate.py:264`） | `effective_tmu = base × freq`；freq≤0 報錯（`calculation_v2.py:236,344`） | **相同** |
| SIMO 語義 | `simo_group_id` 非空 → 該列**貢獻 0**，時間由主列吸收（`calculate.py:271`；ADR-020） | `is_simo=True` → `total_contribution_tmu=0`（`calculation_v2.py:257`） | **相同（現役引擎）** |
| SIMO（孤兒路徑） | — | `most_workbench.py:176` `preview_mi_statement` 用 **max** ← **與現役相反** | **v4 內部矛盾** |
| 秒 | `total × 0.036`，round 4 位（`calculate.py:267`） | `× 0.036`，quantize 4 位（`calculation_v2.py:253`） | **相同** |
| TMU→秒常數 | `TMU_TO_SEC=0.036`（`rule_set_data.py:16`） | `TMU_TO_SECONDS=Decimal("0.036")`（`calculation_v2.py:24`） | **相同** |

**【相同】** 現役引擎的 SIMO 語義（貢獻 0）、頻率、秒換算、rounding 位數皆一致。
**【v4 內部矛盾】** 孤兒 `most_workbench.py` 的 SIMO=max 與現役相反——整合時**絕對不能**採用這條路徑。

> **精度細節**：v2 total 用 Python `round()`（`calculate.py:263` `round(sum(t)*mult, 3)`），v4 用 `Decimal.quantize(ROUND_HALF_UP)`。兩者在多數情況一致，但 `round()`（banker's rounding）與 `ROUND_HALF_UP` 在 .5 邊界**可能不同**。v2 slot 值多為整數 index（round 無影響），僅 X 的秒換算會出小數——而 X 在**slot 層**雙方都已用 Decimal half-up 3 位對齊，故實務差異極小。整合時若把 v4 的 Decimal 結果餵進 v2，需確認 total 層 rounding 不引入 1-TMU 級偏差。**建議整合後以 v2 引擎重算，不採信 v4 的 total 數字。**

---

## 4. 黃金值（GM=28 / CM=29）v4 是否有對應基準？（任務要求核心）

### v2 黃金值（已鎖定）

`scripts/core_logic/engine_golden_test.py`：

- **GM = 28 TMU**（`:65`）：
  `A(reach20)=6 · B=0 · G_grasp=6 · A(reach25)=10 · B=0 · P_place_none=6 · A_return=0` → 6+0+6+10+0+6+0 = **28** ✓（`:31` `_gm_gold`）
- **CM = 29 TMU**（`:68`）：
  `A(reach25)=10 · B=0 · G_touch=3 · M(push45)=16 · X_none=0 · I_none=0 · A_return=0` → 10+0+3+16+0+0+0 = **29** ✓（`:34` `_cm_gold`）

（reach20→band ≤20cm=6；reach25→band ≤35cm=10；push45→ladder ≤45cm=16。與 §2 值表一致。）

### v4 有無對應基準？

- **無等價的 GM=28 / CM=29 golden**。v4 唯一的 total 斷言是 `tests/test_most_workbench.py:323` `assertEqual(result['total_tmu'], 40.0)`——這是**單一 P 格**（放一種+對準+卡合=16+8+16=40，對應字典 P.examples 第 3 筆），**不是完整 GM/CM cycle 的黃金值**。
- v4 有 slot 級單元測試（`test_most_workbench.py:34` 起測 `calculate_slot_tmu('A',...)` 等），但**沒有把七格組成一條 GM/CM 並鎖定總值**的回歸測試。

**判定**：
- **【v2 有 v4 無】** 完整 cycle 級黃金值鎖定（GM=28/CM=29）＋大量錯誤反例（`A_RETURN_COMPONENT`/`M_HAND_RANGE`/`P_DUP_ADDON`…）。v4 **缺乏 cycle 級回歸保護**。
- 用 v4 的值表**手算** GM golden 場景：A(≤20)=6 + B(必選，無0選項) + G_grasp=6 + A(≤35)=10 + B(必選) + P_place_none=6 + A(≤2.5)=0。**若 B 能取 0，v4 值表算出的七格和 = 28，與 v2 一致**；但 v4 B **無 0 選項**，故 v4 無法原樣重現 GM=28（會多出兩個 B 的 TMU）。
- CM golden 場景：A(≤35)=10 + B + G_touch=3 + M(push≤45)=16 + X + I。M/G/A 值表一致；**X_none / I_none 在 v4 無對應**（v4 X/I 無 0 選項），故 v4 也無法原樣重現 CM=29。

> **這是整合最關鍵的結論**：
> **v4 的值表與 v2 完全同源（逐格核對 A/B/G/P/M/X/I 值皆一致），但 v4 缺少 v2 golden 場景所需的「0 值選項」（B_none / X_none / I_none）與 cycle 級黃金鎖定。** 因此：
> 1. 整合時**必須以 v2 引擎為單一權威**，v4 只作為「資料/UI/功能」來源，**不得**用 v4 的計算結果覆蓋 v2 的 TMU。
> 2. v4 資料匯入 v2 前，需補齊 0 值選項對映（B/X/I 的「無」語義），否則 v2 golden 測試通不過 = 污染。
> 3. 整合後**必跑 `engine_golden_test.py`**（GM=28/CM=29 + 全反例）作為驗收門檻。

---

## 5. slot-level repeat vs frequency（任務要求對照）

| 概念 | v2 | v4 | 判定 |
|---|---|---|---|
| slot repeat（格內重複） | `repeat_count` on G/P/M/X/I；A/B 禁用（`_no_repeat`, `calculate.py:157`）；範圍 1..99（`_REPEAT_MAX`, `calculate.py:148`）；非整數/超界 → `REPEAT_INVALID` | `repeat_count` on G/P/M/X/I（`calculation_v2.py:60-66`）；A/B 不套用（程式碼路徑不乘）；`<1` 或非整數 → fallback 1（`get_slot_repeat_count:36`）；validate 另報「≥1 整數」（`:171`） | **相同（適用格一致：G/P/M/X/I）**；**不同（越界處理）**：v2 **報錯**，v4 **靜默回退 1** |
| row frequency（整列頻率） | `step.frequency`，`total × freq`；≤0 報錯 | `body.frequency`，`base × freq`；≤0 報錯 | **相同** |
| M 的 repeat 語義 | 只乘動詞類分量再進 max（hand/foot 不乘） | 同（`verb_tmu × verb_repeat` 後 max） | **相同** |
| repeat 上限 | 99（`calculate.py:148`，註明「待 IE 拍板」） | **無上限**（`get_slot_repeat_count` 不設上界） | **不同** |

**【相同】** repeat 與 frequency 是兩個正交概念，雙方皆如此；適用格（G/P/M/X/I）一致；M 的 repeat 只乘動詞一致。
**【不同】** (a) 越界：v2 報 `REPEAT_INVALID`，v4 靜默回退 1（可能掩蓋錯誤輸入）；(b) 上限：v2=99，v4 無上限。

> **整合風險（repeat）**：v4「靜默回退 1」若匯入 v2，v2 會對同一筆越界值報錯而非回退——行為不一致但**方向安全**（v2 較嚴，不會產生錯誤 TMU）。v4 無上限的極大 repeat 進 v2 會被 99 上限擋。整合以 v2 規則為準即可。

---

## 6. 總表：【相同】【不同】【v2 有 v4 無】【v4 有 v2 無】

### 【相同】（可直接對映，低風險）
- 七格 A/B/G/P/M/X/I 骨架、GM/CM 兩模型、格位順序（`calculate.py:24-25` vs 字典 sequence_models）
- 各格聚合語義：A=max、A3/返回=僅reach、B/G/I=單選、P=base+Σmod、M=max(verb×rep,hand,foot)、X=sec/0.036
- **所有值表數值同源**（逐筆核對 A reach / M push ladder / M hand / M foot / B / G / P / X 皆一致）
- SIMO=貢獻0（現役引擎）、frequency=total×freq、TMU→秒=×0.036
- X rounding：Decimal half-up 3 位（雙方 ADR-014 口徑一致）
- slot repeat 適用格（G/P/M/X/I）、M repeat 只乘動詞

### 【不同】（TMU 可能分歧，整合須處理）
- B/X/I **無 0 值選項**（v4 缺 none；v2 有 b_none/x_none/i_none）← **直接影響 GM/CM golden 可重現性，最需處理**
- repeat 越界處理（v2 報錯 vs v4 回退1）、repeat 上限（99 vs 無）
- total 層 rounding（v2 `round()` banker vs v4 `Decimal ROUND_HALF_UP`）
- multiplier（v2 有 system_tmu_multiplier=1；v4 無）
- slot 命名（v2 位置索引 vs v4 A1/A2/A3）
- P precision gating（**現行資料集下雙方等價**——v2 全 addon needs_precision=False；僅未來新增 True addon 才分歧）

### 【v2 有 v4 無】（v2 較嚴謹，v4 髒資料進 v2 會被擋）
- Cycle 級**黃金值鎖定 GM=28/CM=29** 與大量錯誤反例（`engine_golden_test.py`）
- 完整值域檢查：`M_DISTANCE_RANGE` / `M_HAND_RANGE` / `M_ROTATION_RANGE`
- `M_COMPANION_WITHOUT_VERB`（伴隨維度不得單獨成格）
- `A_RETURN_COMPONENT`（A3 不得含 twist/foot）、`A_NEGATIVE`
- `P_DUP_ADDON`（addon 去重）
- `*_UNKNOWN`（B/G/P/M/X/I 未知 code 報錯）
- rule-set **完整性 gating**（`validate_complete`, `rule_set_data.py:170`）
- 人工覆寫留痕（`manual_override`, `calculate.py:277`）
- band 定義層（原始量測→index，v4 已折進 option）

### 【v4 有 v2 無】（v4 的功能/資料特性）
- **option 級 pre-computed tmu_value**（免查表，UI 直選）— 這是 v4 的資料形態，非新演算法
- v4 有 slot `display_rule`（P modifier 的 `show_self`/`hidden`/`prefix_visible_term`）驅動敘事顯示 —（v2 亦有 display_rule 於 P addon DB 欄，見 `providers.py` load，故非全然「v2 無」；需 §敘事文件細查）
- （**注意**：v4 的 `most_workbench.py` sum/max 舊語義、`calculation.py` index+rule_adjustment 舊模型 = **v4 內部 legacy，非有效功能**，整合時排除）

---

## 7. 整合建議（不污染 v2 單一權威與黃金值）

1. **v2 引擎為唯一 TMU 權威**。v4 僅提供資料（值表 option）、UI/功能（ESOP/LineBalance/Level 等，見其他子文件），**絕不採信 v4 計算結果**。
2. **資料映射方向**：v4 option `tmu_value` → 對回 v2 band/index（值表已證同源，可機械對映）。補齊 v4 缺的 0 值選項（B/X/I none）。
3. **P 格 precision**：現行資料集下 v2 P addon 全 `needs_precision=False`、gating 停用，與 v4 等價，無需特別處理；**唯一守則**是整合過程不要在 v2 rule-set 引入 `needs_precision=True` 的 addon（會憑空製造與 v4 的分歧）。
4. **驗收門檻**：整合後在 v2 跑 `PYTHONPATH=src python scripts/core_logic/engine_golden_test.py`，GM=28/CM=29 與全反例必須全綠，否則視為污染、不得合併。
5. **排除 v4 的兩條 legacy 計算路徑**（`most_workbench.py` sum/max、`calculation.py` index+adj），只採 `calculation_v2.py` 的規則作為「v4 意圖」的參照。

---

## 附錄：本文引用的實讀檔案（證據索引）

**v4**：
- `app/services/calculation_v2.py`（現役引擎，全讀）
- `app/services/calculation.py`（legacy index 模型，全讀）
- `app/services/most_workbench.py`（孤兒 sum/max 服務，全讀）
- `app/services/default_dictionary_seed.py`（字典載入，全讀）
- `app/data/minimost_ai_dictionary_v1.json`（值表，全讀）
- `app/api/routes/most.py`（`:21` import、`:294` `api_calculate_row`、`:318` calc）
- `app/api/routes/most_workbench_v3.py`（`:25` import calculation_v2）
- `app/api/routes/analysis.py`（`:23` 僅取 TMU_TO_SECOND 常數）
- `tests/test_most_workbench.py`（`:323` 唯一 total 斷言=40，單 P 格）

**v2**：
- `src/ddm_v2/most_engine/calculate.py`（引擎，全讀）
- `src/ddm_v2/most_engine/rule_set_data.py`（值物件+查表，全讀）
- `src/ddm_v2/most_engine/providers.py`（seed/DB adapter，全讀）
- `src/ddm_v2/seed/v2/rule_set_seed_v2.py`（v3 IE 認證值表：A_BANDS `:19`、M_LADDER `:82`、M_FOOT `:88`、M_VERBS `:100`）
- `scripts/core_logic/engine_golden_test.py`（黃金值 GM=28 `:65` / CM=29 `:68` + 反例）
