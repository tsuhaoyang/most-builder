# DDM v2 ↔ ddm-v3 核心邏輯差異分析與整合規劃

> **狀態**：分析完成，未改任何程式。本文件是「將 v3 邏輯整合進 v2」的前置差異盤點。
> **⚖️ 裁決更新（2026-07-04，User/IE）**：**v3 的資料與使用邏輯經 IE 認證，為權威**。§8 裁決清單已定案：C1/C2/C3/C5/C6/C8/C9 依 v3；C4 SIMO 採「UX 用 v3 配對、引擎仍取 max」；C7/C10 列殘項。後續設計見 [v3-to-v2-refactor-blueprint.md](v3-to-v2-refactor-blueprint.md)。
> **🔍 程式碼查證（2026-07-05）**：本文件所有宣稱已對 ddm-v3 程式碼逐條查證，更正 C-1~C-12 見 [verification-code-audit.md](verification-code-audit.md)（重點：seed=字典 JSON 證實；人工覆寫非 v3 live 功能；v3 另有三層組裝系統；allowance 僅 analysis 層半接線）。
> **撰寫日期**：2026-07-04
> **比對基準**：
> - v2 = `ddm-v2/`（本團隊修正版；權威規格在 `ddm-v2/docs/core-logic/`，權威引擎在 `ddm-v2/src/ddm_v2/most_engine/`）
> - v3 = `ddm-v3/`（IE 工程師新做的系統；權威字典在 `ddm-v3/minimost_ai_dictionary_v1.json`，引擎在 `ddm-v3/apps/api/app/services/calculation_v2.py`）

---

## 0. 結論速覽（TL;DR）

1. **兩版的序列模型骨架完全一致**：GM = A B G A B P A、CM = A B G M X I A，1 TMU = 0.036 秒，slot 加總後乘頻率。整合沒有結構性障礙。
2. **參數值大部分一致**（A 距離帶、B、G、P base/addon、旋轉、手度的 TMU 值幾乎逐格相同），代表兩邊都源自同一份工廠 Excel 體系。
3. **三個高風險分歧必須先由 IE 裁決，否則不能動手整合**：
   - **C1：M 距離階梯的單位詮釋**（v2 當作 cm；v3 標明是「吋(cm)」→ 同一數字門檻差 2.5 倍）
   - **C2：M 腳步的三套不同數值**（v2 規格、v2 程式、v3 字典三者互相矛盾）
   - **C4：SIMO 合計語意**（v2 = 群組取 max；v3 = 被標記列貢獻 0）
4. **v3 真正的新價值**不在計算引擎（那部分 v2 更嚴謹），而在：**AI 字典（機器可讀 + Excel 匯入 + 版本化）、自然語言 WI 解析（nl_draft_parser + wi-parser-upgrade 路線圖）、I/X 選項的 1205 完整檔位（視線外、更多機台）、slot 級重複次數、人工覆寫留痕、5 角色審核工作流**。
5. **v2 不可退讓的資產**：Level System（R1–R9 + LB 輸出合約）、Site/Product/SKU/ProcessVersion 階層、rule-set 快照回放、黃金測試（GM=28 / CM=29 + 89 案例）、單一權威引擎反漂移原則、GM/CM 跨模型防呆。v3 全部沒有。
6. **建議整合方向**：v3 的內容以「新 rule-set 版本（值層）＋功能移植（NL 解析、正規化、審核流）」進入 v2；**不採用 v3 的引擎程式本體**（v3 自身有兩套引擎並存的漂移風險，且缺黃金測試錨定）。

---

## 1. 兩版定位與權威來源

### 1.1 v2（ddm-v2）

| 項目 | 內容 |
|---|---|
| 架構 | FastAPI + async SQLAlchemy 2.0 + React（`src/frontend`）；hexagonal、單一權威引擎 |
| 核心規格 | `docs/core-logic/minimost-sequence-model-core-logic-spec.md`（序列模型）、`docs/core-logic/level-system-core-logic-spec.md`（Level System R1–R9）、`docs/core-logic/core-logic-validation-test-catalog.md`（黃金/反例） |
| 權威引擎 | `src/ddm_v2/most_engine/calculate.py`（GM/CM 唯一計算）、`most_engine/level.py`（R1–R9 驗證 + LB 輸出）、`most_engine/narrative.py`（METHOD 句生成） |
| 值的權威 | rule-set 版本化：`src/ddm_v2/seed/v2/rule_set_seed.py`（`MINIMOST_FACTORY_V1`），DB 子表 `rule_a_bands` … `rule_i_options` |
| 資料階層 | Site → Product → SKU → ProcessVersion → MostWorksheet → WiRow（1:1 MostCycle、1:1 LevelEntry） |
| 測試錨定 | 黃金值 GM=28（A6 B0 G6 A10 B0 P6 A0）、CM=29（A10 B0 G3 M16 X0 I0 A0）；`tests/unit/test_most_engine.py`、`test_level_engine.py` |

### 1.2 v3（ddm-v3）

| 項目 | 內容 |
|---|---|
| 架構 | FastAPI + Vue 3（Element Plus）；SQLite(dev)/PostgreSQL(prod) |
| 核心規格 | `MiniMOST_system_data_spec.md`（Excel→系統映射）、`minimost_ai_dictionary_v1.md`、`docs/minimost-domain.md`、`docs/most-workbench.md` |
| **值的權威** | `minimost_ai_dictionary_v1.json`（43.6KB 機器可讀字典，源自 `MiniMOST_rag.xlsx`）→ Excel 匯入器 `apps/api/app/services/dictionary_import.py` → DB 表 `dictionary_versions` / `parameter_options` / `lexical_options` |
| 引擎 | **兩套並存**：`services/calculation.py`（舊，float、直接吃 index）與 `services/calculation_v2.py`（新，Decimal、字典驅動、含 P/X 驗證與 slot repeat） |
| 資料模型 | DictionaryVersion → MostSequenceItem（個人序列庫）→ MostMiStatement（MI 語句容器）→ MostMiStatementItem（快照）；ActionModuleTemplate（動作模組範本） |
| 特色功能 | 自然語言解析 `nl_draft_parser.py`（規則式，約 1000 行）＋ `docs/wi-parser-upgrade/`（01–09 的四階段混合管線升級計畫）；`normalization.py`（NFKC/OpenCC 繁簡）；5 角色審核工作流；audit log |
| 測試 | 11 份 unittest（公式/解析/正規化/流程/RBAC/匯出），**無領域黃金值錨定**（測試用任意數字驗公式，不驗 28/29 這類工廠事實） |

### 1.3 v3 內部自我矛盾（整合時以字典 JSON 為準）

v3 自己的文件之間有出入，整合時**一律以 `minimost_ai_dictionary_v1.json` 為 v3 的事實基準**：

| 矛盾點 | spec MD 說法 | 字典 JSON / 程式實況 |
|---|---|---|
| G 抓握 TMU | `MiniMOST_system_data_spec.md` §8 範例寫 `抓握 index=16` | 字典 `G_GRASP tmu_value=6`（與 v2 一致）→ spec 範例是筆誤 |
| 秒→TMU | spec §5 寫 `seconds × 27.8` | `calculation_v2.py` 用 `seconds / 0.036`（= ×27.777…）；`calculation.py` 常數 27.7777777778 |
| 規則引擎 | spec §5 設計「升一級/升二級索引」的 index ladder | 字典與 `calculation_v2` 實作為**平面加法修飾**（+8/+16），與 v2 相同；「升級索引」構想未實作 |

---

## 2. 序列模型與計算骨架對照

| 面向 | v2 | v3 | 判定 |
|---|---|---|---|
| 模型 | GM=`A B G A B P A`、CM=`A B G M X I A` | GENERAL_MOVE 同、CONTROLLED_MOVE 同（slot 命名 A1/B1/G/A2/B2/P/A3 與 A1/B1/G/M/X/I/A2） | ✅ 一致 |
| TMU→秒 | 0.036（精確，不四捨五入常數） | 0.036 | ✅ 一致 |
| 合計 | `Σ slot × system_tmu_multiplier(=1)`；**不乘 10**（v2 已裁決 OQ-001） | `Σ slot`（無 multiplier 概念，等效 ×1） | ✅ 等效 |
| 頻率 | 列級 `frequency`（>0，允許分數），乘整列 | 列級 `frequency`（float>0）＋ **slot 級 `repeat_count`**（G/P/M/X/I，重複單一動詞不乘整列） | ⚠️ v3 多一層，見 §5.4 |
| 精度 | 引擎 slot 為 int，合計 float；秒 round 6 位 | `calculation_v2` 全程 Decimal，TMU 3 位、秒 4 位 ROUND_HALF_UP | ⚠️ 捨入策略需統一（見 C3） |
| 寬放 | 不在 MOST 層；放在 Level System `coefficient`（`second = raw_seconds × coefficient`） | 在 MOST 層：`standard_time_sec = normal_time_sec × (1 + allowance_percent/100)` | ⚠️ 概念重疊，見 C7 |
| 錯誤邊界 | 嚴格：`SEQ_KIND` / `SLOT_CROSS_MODEL`（GM↔CM 不可混用）/ `A_NEGATIVE` / `X_NEGATIVE` / `P_TOO_MANY_ADDONS` / `P_DUP_ADDON` / `FREQ_INVALID`（`most_engine/calculate.py:152-160`） | 較鬆：只有 P（≤2 修飾、insert⊥snap、有修飾必有 base）、X 正秒數、repeat 整數（`calculation_v2.py:125-161`）；無跨模型防呆 | ✅ 整合時保留 v2 的邊界，吸收 v3 的 P/X 規則 |
| 人工覆寫 | 無 | `manual_index_value` 覆寫 + `rationale` + `step_rule_application` 留痕（`calculation.py:68-78`、spec §3 `step_slot_value`） | ➕ v3 新能力，整合候選 |

---

## 3. 參數逐格比對（值層）

> v2 值出處：`ddm-v2/src/ddm_v2/seed/v2/rule_set_seed.py`（`MINIMOST_FACTORY_V1`）＋ `docs/core-logic/minimost-sequence-model-core-logic-spec.md` §4。
> v3 值出處：`ddm-v3/minimost_ai_dictionary_v1.json` → `parameters`。

### 3.1 A — 距離（伸手 / 手度 / 腳步，取 max）✅ 幾乎一致

| 分量 | v2（cm 門檻 → index） | v3（吋(cm) 門檻 → tmu_value） | 判定 |
|---|---|---|---|
| 伸手 reach | ≤2.5→0, ≤5→1, ≤10→3, ≤20→6, ≤35→10, ≤60→16, >60→24 | ≤1(2.5)→0, ≤2(5)→1, ≤4(10)→3, ≤8(20)→6, ≤14(35)→10, ≤24(60)→16, >24(60)→24 | ✅ 完全一致 |
| 手度 twist/hand_degree | ≤30°→0, ≤60°→1, ≤120°→3, ≤180°→6 | 同 | ✅ 一致 |
| 腳步 foot | ≤20→6, ≤30→10, ≤45→16, ≤65→24, >65→32 | ≤8(20)→6, ≤12(30)→10, ≤18(45)1步→16, ≤26(65)→24, >26(65)2步→32 | ✅ 一致（v3 多了「1步/2步」的顯示註記） |
| 計算 | `max(reach, twist, foot)`，三 slot（取得/移動/返回）都用三分量 | A1/A2 = `max(reach, hand, foot)`；**A3（返回）只算 reach** | ⚠️ 小差異：v2 的返回格也接受手度/腳步輸入；v3 明確限定返回只有伸手。**建議採 v3 語意**（返回不會有腳步/翻轉的工廠常識），列 C10 |
| 顯示規則 | 無 | A_move 選「手度」時句子須出現「翻轉+目標物」（spec §5 dependency 規則） | ➕ v3 句子規則，narrative 整合候選 |

### 3.2 B — 身體動作 ✅ 值一致

| 選項 | v2 | v3 | 判定 |
|---|---|---|---|
| 無 | `b_none`=0（顯式選項，預設） | 無此選項；未選=0 | ⚠️ UI/資料表示差異，值等效 |
| 眼部動作 | 10 | `B_EYE_MOVE`=10 | ✅ |
| 起身或彎腰/坐 | 32 | `B_BEND_OR_SIT`=32 | ✅ |
| 站(立) | 42 | `B_STAND`=42 | ✅ |

v2 已於 2026-06-16 裁定採 1205 值（0/10/32/42），v3 字典同源，**B 參數無衝突**。

### 3.3 G — 取得控制：值一致，**gating 機制不同**

| 選項 | v2 code（base_tmu） | v3 option（tmu_value） | 判定 |
|---|---|---|---|
| 輕按/接觸/輕拍 | g_tap/g_touch/g_pat = 3 | G_LIGHT_PRESS/G_TOUCH/G_LIGHT_TAP = 3 | ✅ |
| 抓握/抓取/重新抓握 | g_grasp/g_grab/g_regrasp = 6 | G_GRASP/G_PICK/G_REGRASP = 6 | ✅ |
| 換手 | g_handchange = 10 | G_TRANSFER_HAND = 10 | ✅ |
| 拿取(選取) | g_pick_sel = 10 | G_SELECT = 10 | ✅ |
| 拿取(選取-小) | g_pick_small = 16 | G_SELECT_SMALL = 16 | ✅ |
| 拔出 | g_pullout = 16 | G_SEPARATE = 16 | ✅ |
| 拿取(收集) | g_pick_collect = 24 | G_COLLECT = 24 | ✅ |

**機制差異（C6）**：v2 有 `requires_modifier` gating——需勾修飾（contact/transfer/select…）而未勾 → 該格 **0（視為未完成）**（`calculate.py:68-78`）。v3 是純單選，修飾語意內含在選項名稱裡，選了就計 TMU。v2 的 gating 是刻意的「填寫防呆」，v3 走「選項即完整語意」。兩者擇一即可，但**選 v3 路線時 v2 的黃金測試中「未勾修飾→0」的反例要改**。

### 3.4 P — 放置 ✅ 值一致，v3 多句子顯示規則

Base 七項（丟3/保持住3/放無6/放多10/放一16/組多10/組一16）：**兩版完全一致**。

Modifier 五項（對準+8/插入+8/較難處理+8/卡合+16/施加壓力+16）：**TMU 完全一致**，但機制有三處差異：

| 面向 | v2 | v3 |
|---|---|---|
| 對準的精度條件 | 獨立 `precision` 旗標：勾「精度<4mm」才 +8，否則忽略（`needs_precision` gating） | 選項本身就叫 `P_ALIGN_LT_4MM`「對準(精度<4mm)」——選了就 +8，無獨立旗標 |
| 互斥/上限 | ≤2 個附加（`P_TOO_MANY_ADDONS`）；**無 insert⊥snap 互斥** | ≤2 個附加；**插入與卡合互斥**；有修飾必有 base（`calculation_v2.py:129-141`） |
| 句子顯示 | narrative.py 由 rule-set 標籤組句 | **display_rule**：`P_INSERT`/`P_SNAP_FIT` = show_self（句子只顯示「插入/卡合」取代 base 動詞）、`P_ALIGN_LT_4MM` = prefix（前綴「對準」）、`較難處理`/`施加壓力` = hidden（只計 TMU 不出現在句子）（`calculation_v2.py:198-231`） |

**判定**：v3 的「插入⊥卡合互斥」與「display_rule 三態」是 1205/詳解版本來就有的顯示規則，v2 規格提過但引擎未實作 → **整合候選（值不變，加驗證與 narrative 規則）**。

### 3.5 M — 控制移動：**最大衝突區（C1、C2）**

動詞集合一致：按動按鈕(3)/滑出螺絲(3)＝固定；理/穿/推/拉/貼附/去除/撕除/折/擦拭/撕開＝距離階梯；旋轉；手度；腳步。

**C1 距離階梯門檻——單位詮釋分歧（高風險）**：

| TMU | 3 | 6 | 10 | 16 | 24 | 42 |
|---|---|---|---|---|---|---|
| v2（`M_LADDER`，欄名 max_cm） | ≤1 | ≤4 | ≤10 | ≤18 | ≤30 | >30 |
| v3（字典，吋(cm) 標法） | ≤1(2.5) | ≤4(10) | ≤10(25) | ≤18(45) | ≤30(75) | **（無此檔）** |

兩版的「數字門檻」相同（1/4/10/18/30），但 v2 把它們當 **cm**、v3 明確標為 **吋（括號才是 cm）**。同時 v2 自己的 A 帶（reach ≤2.5/5/10/20/35/60 cm）確實採「括號內 cm 值」，M 階梯卻用了「吋數字當 cm」——**v2 內部單位不一致，v3 的標法與 A 帶邏輯、與 1205「≤4(10)」的格式一致，v3 很可能才是對的**。

影響示範：作業員推 40cm——v2 算 >30cm → **42 TMU**；v3 算 ≤18(45cm) → **16 TMU**，差 2.6 倍。
黃金測試影響：CM=29 的「推 18→M16」在兩版都成立（數字層等價），但**語意上 v2 是推 18cm、v3 是推 18 吋=45cm**。若裁定 v3 詮釋，v2 的 `M_LADDER` 門檻要改成 2.5/10/25/45/75，且黃金測試的輸入註解與 UI 單位提示要同步修正。

另注意：v3 M 動詞**沒有 >30(75) 的 42 TMU 檔**（v2 有）。42 檔在 v3 只出現在 M 腳步的 >75。是否保留動詞 >75→42 檔需 IE 確認。

**C2 M 腳步——三套數值互相矛盾（高風險）**：

| 來源 | 門檻 → TMU |
|---|---|
| v2 規格（spec §4.5：「同 A 腳步帶」） | ≤20→6, ≤30→10, ≤45→16, ≤65→24, >65→32 |
| v2 程式（`calculate.py:115-116`：kind "foot" 走 `ladder_tmu`） | ≤1→3, ≤4→6, ≤10→10, ≤18→16, ≤30→24, >30→42 |
| v3 字典（M 的 foot_step control） | ≤10(25)→10, ≤16(40)→16, ≤22(55)→24, ≤30(75)→32, >30(75)→42 |

v2 的規格與程式**自己就不一致**（規格說同 A 腳步帶，程式卻走 M 距離階梯）；v3 又是第三組值。這必須回到工廠 Excel（1205 / MiniMOST_rag.xlsx）由 IE 一次裁定。

**旋轉**（次要，C10）：

| 檔位 | v2 | v3 |
|---|---|---|
| 直徑≤12.5cm：1/2/3 圈 | 16/32/42 | 16/32/42 ✅ |
| 大直徑 1 圈 | >12.5cm（無上限）→24 | ≤50cm→24 |
| 大直徑 2 圈 | 42 | 42 ✅ |
| 大直徑 3 圈 | 42 | **無此檔** |

**手度**：v2 `≤90→6, >90→10`（無上限）；v3 `≤90→6, ≤180→10`＋顯式 `M_HAND_NONE=0`。值等效，v3 多了 180° 上限語意。

**結構差異**：v2 的 M slot 是 `m_components` 陣列（可放多個 verb 分量取 max）；v3 是固定三 control（verb + hand_degree + foot_step）取 max，且 **repeat 只乘 verb 再進 max**（`calculation_v2.py:98-107`，推×16 不影響手度/腳步）。v3 結構是 v2 的子集＋repeat 擴充。

### 3.6 X — 處理時間：v3 檔位是超集；**捨入規則不同（C3）**

| 選項 | v2 | v3 |
|---|---|---|
| 無機台等待 | `x_none`=0 | 無此選項（未選=0） |
| 並壓合機台 | `x_press`（輸入秒） | `X_PRESS_MACHINE`（輸入秒） |
| 並卡合&壓合機台 | — | `X_SNAP_PRESS_MACHINE`（輸入秒） |
| 並熱熔機台 | `x_heat`（輸入秒） | `X_HOT_MELT_MACHINE`（輸入秒） |
| 並點膠 | — | `X_DISPENSE_GLUE`（輸入秒） |
| 並鎖附固定 | — | `X_SCREW_FIX`（固定 0.216s → 6） |
| 並鐳雕 | — | `X_LASER_MARK`（輸入秒） |
| 刷條碼 | `x_scan`（固定 0.216s → 6） | 拆三項：`X_SCAN_PPID` / `X_SCAN_WORK_ORDER_QR` / `X_SCAN_BARCODE`（皆固定 0.216s → 6） |

v3 的 9 檔就是 v2 spec §4.6 已註記的「1205 離散清單（并压合/卡合/热熔/点胶/锁附/镭雕/刷PPID/刷工单/刷条形码）」——**v2 早已預告 Phase 2 要補，v3 幫忙做完了選項盤點 → 直接採用**。

**C3 捨入**：v2 已裁決（Q3）`ceil(sec/0.036)`；v3 用 Decimal 除法 ROUND_HALF_UP 保留 3 位小數。10 秒 → v2 = **278**、v3 = **277.778**。建議維持 v2 的 ceil 裁決（已寫入 OQ），v3 的值層併入即可。

### 3.7 I — 對齊/檢查：v3 檔位是超集 ✅ 建議採用

| 選項 | v2 | v3 |
|---|---|---|
| 不額外對齊 | `i_none`=0 | 無此選項（未選=0） |
| 並檢查（正常視線） | 6 | `I_CHECK_NORMAL`=6 |
| 並確認（正常視線） | — | `I_CONFIRM_NORMAL`=6 |
| 並對準（正常視線·到點） | 10 | `I_ALIGN_POINT_NORMAL`=10 |
| 並對齊（正常視線·到兩點） | 16 | `I_ALIGN_TWO_POINTS_NORMAL`=16 |
| 並檢查/確認（視線範圍外） | — | 16 / 16 |
| 並對準（視線外·到點） | — | 24 |
| 並對齊（視線外·到兩點） | — | 32 |

重疊的 4 檔 TMU 完全一致；v3 補上「確認」同義項與「正常視線範圍外」整組檔位（16/24/32）。這正是 v2 Q6 裁決保留到 Phase 2 的「1205 完整表（視線外）」→ **值層直接採用，無衝突**。

---

## 4. 合計、SIMO 與時間鏈差異

### 4.1 SIMO（C4，高風險語意差異）

| 面向 | v2 | v3 |
|---|---|---|
| 標記 | `simo_group_id`（同組=雙手同時） | `is_simo` 布林 + `simo_with_row_id`（指向配對列） |
| 合計 | `Σ(非SIMO tmu×freq) + Σ(每組 max(tmu×freq))`（`calculate.py:196-214`） | 標 `is_simo=true` 的列**貢獻 0**，只有未標記列計入（`calculation_v2.py:261-266`） |
| 風險 | 無（引擎自動取組內最大） | 若使用者把「較長的那隻手」標成 SIMO，總工時會**被低估**；正確性依賴人工判斷 |

**建議**：保留 v2 的 group-max 語意（數學上安全），v3 的 `simo_with_row_id` 配對 UX 可作為前端輸入方式（配對後自動生成 group）。

### 4.2 時間換算鏈與寬放（C7）

```
v2： slot Σ → cycle TMU → ×freq → (WI 合計) → 秒(×0.036)
     寬放在 Level System：second = raw_seconds × coefficient（LevelEntry GENERATED 欄）
v3： slot Σ → ×freq(列) → normal_time_sec(×0.036) → standard_time_sec = ×(1+allowance%/100)
     allowance 掛在 analysis_case 層級（⚠️ 查證更正 C-3：僅 analysis 層有欄位並輸出於報表；workbench/MI 層完全未接線）
```

兩者都是「先算純 MOST 時間、再乘一個係數」，但掛的層級不同（v2 在列級 LevelEntry、v3 在案件級）。**需裁決**：寬放屬於列級（v2，供 LB 精細分攤）還是案件級（v3，IE 慣用的整站寬放率）——也可能兩層都要（案件級預設值 + 列級覆寫），此為典型 IE 決策。

---

## 5. 資料模型對照與概念映射

| 概念 | v2 | v3 | 整合映射 |
|---|---|---|---|
| 規則/字典版本 | `rule_sets`（code 如 MINIMOST_FACTORY_V1，published 後凍結） | `dictionary_versions`（每次 Excel 匯入產生新版，`is_active` 切換） | 同一概念。v2 的 rule-set 目前**只能由 seed 程式碼建立**；v3 的 **Excel 匯入器**（`dictionary_import.py`）是 v2 缺的能力 → 整合候選 |
| 參數值表 | `rule_a_bands`…`rule_i_options`（11 張強型別子表） | `parameter_slots` + `parameter_options`（泛型單表 + `synonyms_json`） | v2 強型別較利於引擎防呆；v3 泛型較利於 Excel 直進。建議保留 v2 子表，匯入器負責轉換 |
| 詞彙庫 | `work_vocab_items`（object/from/to/tool/component，中英名、external_code） | `lexical_options`（hand/object/from_location/to_location/where…，`normalized_text_zh`） | 同一概念；v3 多 `normalized_text`（配合 NL 解析）與 `where_location` 類別 |
| 分析單元 | `WiRow`（穩定 id）+ 1:1 `MostCycle`（`slot_inputs` 權威 + `computed` 快取 + `rule_set_id` 快照） | `MostSequenceItem`（`selected_slots_json` + `calculation_snapshot_json` + `dictionary_version_id`） | **快照哲學相同**（原始輸入=真相、計算=可重生快取、綁定值版本）。v2 多了「穩定 id 保 Level 標註不流失」設計，必須保留 |
| 語句容器 | WiRow 的 `narrative_zh`（單句） | `MostMiStatement`（多 sequence 組成一句 MI）+ `MostMiStatementSequence`（順序連結）+ `MostMiStatementItem`（**編輯時快照**，不回寫原序列） | ➕ v3 的「個人序列庫 → 組裝 MI 語句」是新工作流概念；v2 是「一列一 cycle」直填。整合時可作為 v2 匯入精靈/範本的前置層，非必要 |
| 動作範本 | `motion_templates`（site 級、keywords[]、`cycle_template` JSONB、draft/standard） | `ActionModuleTemplate`（個人、含 context/slots/快照） | 同一概念，v2 較完整（廠級標準 + 關鍵字檢索供 Excel 匯入自動建 MOST） |
| 組織階層 | Site → Product → SKU → ProcessVersion（publish/clone/血緣） | 無（只有 analysis_case 的 product/station 文字欄） | **v2 獨有，保留** |
| Level System | `level_entries` + R1–R9 + LB 輸出合約 | **完全沒有** | **v2 獨有，整合的絕對保留項** |
| 句子編輯 | 無（narrative 由後端生成） | `system_generated_sentence_zh` / `user_edited_sentence_zh` / `is_manual_edited` / `manual_edit_note` 四欄並存 | ➕ v3 的「系統句 vs 人工改句分開存」值得帶進 v2（IE 常要微調口語句又不想失去可重生性） |

### 5.4 slot 級 repeat（v3 新概念）

v3 的 `repeat_count`（`calculation_v2.py:25-37`）：對 G/P/M/X/I 單一動詞重複 N 次（例：鎖 16 顆螺絲 = 推×16），**不乘整列**、M 的 repeat 只乘 verb 再進 max。v2 只有列級 frequency，要表達「單格重複」得開多列或用分數頻率。此為工廠實務常見需求（1205 的「×N」註記）→ **整合候選**，需 IE 確認語意（尤其 M 的 repeat×verb-then-max 規則）。

---

## 6. v3 獨有能力盤點（整合候選清單）

| # | 能力 | v3 位置 | 對 v2 的價值 | 建議 |
|---|---|---|---|---|
| F1 | **AI 字典 JSON + Excel 字典匯入器 + 版本化** | `minimost_ai_dictionary_v1.json`、`dictionary_import.py`、`dictionary_versions` | v2 rule-set 目前 seed 硬編，IE 無法自助改值 | **高優先**。做 rule-set Excel 匯入器，字典 JSON 作為交換格式 |
| F2 | **自然語言 WI 解析（nl_draft_parser）** | `nl_draft_parser.py`（規則式）＋ `POST /api/most/nl-draft` | v2 只有「口語句子填空 + 下拉」；貼上自由文本自動預填 slot 是 IE 錄入效率關鍵 | **高優先但不要照搬**：v3 現版有 5 項已知結構缺陷（先命中先贏、G 詞表遮蔽、缺正規化、context regex 脆弱、信心反置 bug——見 `docs/wi-parser-upgrade/01`、`08`）。應按其升級計畫的 Stage 0-1（正規化+最長匹配）重寫進 v2 |
| F3 | **wi-parser-upgrade 路線圖（01–09）** | `ddm-v3/docs/wi-parser-upgrade/` | 完整的四階段混合管線設計（正規化→抽取→本體連結→信心分流），含 Profile A(LLM)/B(地端) 對照、資料契約 `NLDraftResultV2` | 全部 ⬜ 未實作。**採納為 v2 的 Phase 3 設計輸入**，不必在 v3 上做 |
| F4 | **文本正規化服務** | `normalization.py`（NFKC/OpenCC 繁簡/大小寫） | v2 詞彙搜尋與未來匯入都需要 | 高優先、成本低 |
| F5 | **I 視線外檔位 + X 九檔機台** | 字典 JSON | 即 v2 Q6/Q3 註記的 1205 Phase 2 完整表 | **直接併入新 rule-set 版本** |
| F6 | slot 級 repeat_count | `calculation_v2.py` | 鎖多顆螺絲等場景 | 中優先，需 IE 確認規則 |
| F7 | 人工覆寫 index + 理由留痕 | ⚠️ 查證更正 C-4：v3 僅 `calculation.py` dataclass 與 spec 構想，**無 live route 接線**——此為「採納 v3 規格構想」非移植 | IE 現場常需覆寫；v2 無、v3 也未實作 | 中優先；掛進 v2 `slot_inputs`（加 `manual_override` 欄）並入 audit |
| F8 | P 顯示規則（show_self/hidden/prefix）＋插入⊥卡合互斥 | 字典 + `calculation_v2.py:129-141,198-231` | v2 narrative 未實作 1205 顯示規則 | 中優先，補進 `narrative.py` + 引擎驗證 |
| F9 | 系統句/人工句分離（4 欄） | `models/most.py:42-45` | 保住「句子可重生」又允許 IE 潤飾 | 中優先 |
| F10 | 5 角色審核工作流 + audit log | `draft→submitted→reviewed→approved→archived`（`docs/minimost-domain.md`）、`models/audit.py` | v2 只有 draft/published + RBAC(IE/manager/admin) 規劃 | 低-中優先；與 [[rbac-hard-requirement]] 的 LB 共享登入整合一起設計，**角色體系要收斂成一套** |
| F11 | MI 語句組裝（序列庫→語句） | `MostMiStatement*` 三表 | 可重用序列片段 | 低優先；v2 motion_template 已覆蓋大部分需求 |

## 7. v2 獨有資產（整合時不可退讓）

1. **Level System 全套**：R1–R9 驗證、四功能字符（main/sub/cub/nb）、變動層級（`1~2`/`1/3`）、LB 輸出合約（nodes/groups/number_constraints/precedence_edges）。v3 完全沒有此層，而它是 MOST→LB 的橋樑（見 [[lb-most-auth-integration]]、`level-system-core-logic-spec.md`）。
2. **黃金測試錨定**：GM=28 / CM=29、89 個黃金/反例、seed 自我驗證（`rule_set_seed._self_check`）。v3 測試只驗公式不驗工廠事實——整合後所有 v3 來的值都要補進黃金測試。
3. **單一權威引擎（反漂移）**：v3 自己就有 `calculation.py` 與 `calculation_v2.py` 兩套並存、行為不同（float vs Decimal、有無 P 驗證）的活例證。整合時**只有 v2 `most_engine` 一個引擎**，v3 的任何邏輯以規則資料或引擎修改進入，不允許第二套計算路徑。
4. **rule-set 快照回放**：`MostCycle.rule_set_id` 快照，規則改版仍可回放歷史（v3 的 `dictionary_version_id` 綁定同哲學，但 v2 的 published 凍結 + 血緣更完整）。
5. **穩定 id 設計**：WiRow id 跨編輯穩定 → Level 標註不因 MOST 修改而流失。
6. **組織階層與發布流**：Site/Product/SKU/ProcessVersion、publish/clone/versions。
7. **嚴格錯誤邊界**：GM/CM 跨模型防呆、負值、重複附加等（v3 大多缺）。
8. **匯出合約**：Excel / lb-csv / lb-api（`export_service.py`），對 LB 的輸出契約。

---

## 8. 裁決清單（整合前必須由 User/IE 拍板）

| # | 議題 | 影響 | 建議傾向 | 風險等級 |
|---|---|---|---|---|
| **C1** | M 距離階梯單位：v2 當 cm（1/4/10/18/30），v3 標吋(cm)（2.5/10/25/45/75） | 所有 M 距離類動詞 TMU，最大差 2.6 倍；黃金 CM=29 的輸入語意 | **傾向 v3 詮釋**（與 A 帶格式、1205「≤4(10)」標法一致；v2 疑似把吋數當 cm 存進 `max_cm`）；需回 `MiniMOST_rag.xlsx`/1205 原檔確認 | 🔴 高 |
| **C2** | M 腳步三套值（v2 規格=A 腳步帶；v2 程式=M 階梯；v3=25/40/55/75 cm 檔） | M 腳步 TMU | 無傾向，三者都可能對；**只能由 IE 對 Excel 原檔裁定**。注意 v2 規格與程式本來就互相矛盾，即使不整合 v3 也要修 | 🔴 高 |
| **C3** | X 秒→TMU 捨入：v2 ceil（已裁決 Q3）vs v3 half-up 3 位小數 | X 格 TMU（10s：278 vs 277.778） | 維持 v2 ceil 裁決 | 🟡 中 |
| **C4** | SIMO：v2 群組取 max vs v3 標記列歸零 | WI 合計正確性 | **維持 v2**（自動取 max 安全）；v3 的配對 UX 可借鏡 | 🔴 高 |
| **C5** | I/X 擴充檔位（視線外、9 檔機台）是否全採 | 選項範圍 | **採用**（即 v2 Q6/Q3 預告的 1205 Phase 2） | 🟢 低 |
| **C6** | G 修飾 gating：v2「未勾修飾→0」vs v3「選項即完整語意」 | G 格 TMU 與 UI 流程 | 傾向 v3（選項語意自含，UI 簡單），但要 IE 確認「輕按未確認接觸型」這類半完成輸入如何呈現 | 🟡 中 |
| **C7** | 寬放層級：v2 列級 coefficient（Level System）vs v3 案件級 allowance% | 標準工時鏈、LB 分攤 | 傾向兩層並存（案件級預設 + 列級覆寫），需 IE 定義優先序 | 🟡 中 |
| **C8** | v3 內部矛盾（spec 抓握16 vs 字典6；×27.8 vs /0.036） | 整合資料來源 | **以 `minimost_ai_dictionary_v1.json` 為 v3 唯一事實基準**，spec MD 僅參考 | 🟢 低 |
| **C9** | A3（返回格）只算 reach（v3）vs 三分量（v2） | 返回格 TMU | 傾向 v3（返回無腳步/翻轉的工廠常識），列黃金測試新增反例 | 🟢 低 |
| **C10** | 旋轉大直徑：v2 無上限+3圈檔 vs v3 ≤50cm 無 3 圈檔；M 動詞 >75cm 檔存廢；手度 180° 上限 | 邊緣檔位 | 對 1205 原檔逐檔確認 | 🟢 低 |

---

## 9. 整合策略建議（規劃，不改程式）

### 原則

- **引擎不換**：v2 `most_engine` 仍是唯一計算真相；v3 的值以「新 rule-set 版本」進入，v3 的行為差異以「引擎功能 + 黃金測試」進入。
- **值先於功能**：C1/C2 未裁決前，任何 M 相關整合都凍結。
- **每一步都有黃金測試**：v3 帶入的每個新檔位/新規則，先寫進 `core-logic-validation-test-catalog.md` 再實作（遵循 [[testing-ci-hard-rules]]）。

### Phase A — 值層對齊（先裁決 C1–C4）

1. IE 對 `MiniMOST_rag.xlsx` / 1205 原檔逐項確認 §8 裁決清單。
2. 依裁決起草 rule-set **`MINIMOST_FACTORY_V2`** seed：I 八檔、X 九檔、M 階梯單位修正、M 腳步裁定值、旋轉/手度邊緣檔。
3. 更新 `minimost-sequence-model-core-logic-spec.md` §4 與黃金測試目錄；黃金 28/29 若受 C1 影響，重新標定輸入語意。

### Phase B — 功能移植（v3 → v2）

依 §6 優先序：F4 正規化 → F1 字典/rule-set Excel 匯入器 → F2 NL 解析（按 wi-parser-upgrade Stage 0-1 重寫，不照搬 v3 現碼）→ F8 P 顯示規則 → F6 slot repeat → F7 人工覆寫留痕 → F9 句子雙欄 → F10 審核流（與 RBAC/LB 登入一併設計）。

### Phase C — 進階（評估後決定）

wi-parser-upgrade Stage 2-3（BGE-M3 檢索 + 信心分流）、MI 語句組裝層（F11）。

### 不整合清單（明確排除）

- v3 `calculation.py`（舊引擎）與 `calculation_v2.py` 程式本體——只取其規則語意。
- v3 SIMO 歸零合計。
- v3 spec MD 中與字典 JSON 矛盾的數值。
- v3 的「升一級/升二級索引」規則引擎構想（未實作，v2 平面加法已等效）。

---

## 10. 附錄：關鍵檔案對照表

| 主題 | v2 | v3 |
|---|---|---|
| 序列模型規格 | `ddm-v2/docs/core-logic/minimost-sequence-model-core-logic-spec.md` | `ddm-v3/MiniMOST_system_data_spec.md`、`ddm-v3/docs/minimost-domain.md` |
| 值的權威 | `ddm-v2/src/ddm_v2/seed/v2/rule_set_seed.py` | `ddm-v3/minimost_ai_dictionary_v1.json` |
| 計算引擎 | `ddm-v2/src/ddm_v2/most_engine/calculate.py` | `ddm-v3/apps/api/app/services/calculation_v2.py`（新）、`calculation.py`（舊） |
| Level System | `ddm-v2/docs/core-logic/level-system-core-logic-spec.md`、`most_engine/level.py` | （無） |
| 句子生成 | `ddm-v2/src/ddm_v2/most_engine/narrative.py` | `calculation_v2.generate_slot_sentence`（slot 片段）＋`routes/most.py _compose_full_sentence`（整句）；`sentence_generation.py` 為模板（查證 C-1：`most_workbench.py` 為 orphan） |
| NL 解析 | （無） | `ddm-v3/apps/api/app/services/nl_draft_parser.py`、`docs/wi-parser-upgrade/01–09` |
| 正規化 | （無） | `ddm-v3/apps/api/app/services/normalization.py` |
| 字典/規則匯入 | （seed 硬編） | `ddm-v3/apps/api/app/services/dictionary_import.py` |
| 資料模型 | `ddm-v2/src/ddm_v2/models/v2/worksheet.py`、`rule_set_tables.py` | `ddm-v3/apps/api/app/models/most.py`、`dictionary.py` |
| 黃金測試 | `ddm-v2/tests/unit/test_most_engine.py`、`test_level_engine.py`、`docs/core-logic/core-logic-validation-test-catalog.md` | `ddm-v3/apps/api/tests/test_calculation.py` 等（公式測試，非黃金值） |
| 匯出 | `ddm-v2/src/ddm_v2/services/v2/export_service.py`（Excel/lb-csv） | `ddm-v3/apps/api/app/services/report_export.py`（Excel） |
