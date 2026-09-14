# MOST ↔ Line Balance 資料契約 Spec（`most-lb-csv-v1.1`）

> **文件類型**：整合資料契約（Data Contract Spec）——**MOST→LB 整合的最高原則**。
> **版本**：v1.1（2026-09-11；v1.0 → v1.1：新增第 24 欄 `general_role`，見 §5.7／§6／§10）
> **修訂（2026-09-12，WP6 裁決）**：`action_type` 的來源改為「IE 選填標籤優先、附錄 A 推導為 fallback」（§4.4／§6／附錄 A）；`lb_tags` 新增 `action_type`。契約版本不變。
> **修訂（2026-09-12，WP3 裁決）**：§3.2／§3.3 新增「分桶」規則（use 段部分格 repeat 合法、須連續）、新碼 `E_REPEAT_NONCONTIGUOUS`；§4.3 修正 2 列 Pattern B 在 N>1 時 slot 6 的歸屬。契約版本不變（語意精確化，不改欄位）。
> **狀態**：✅ 依 2026-09-11 User 裁決撰寫；由 [ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md) 鎖定邊界。
> **權威順序**（衝突時）：本 Spec ＞ ADR-035 ＞ `MOST_LB_CONTRACT.md`（討論紀錄）＞ 既有 export／compiler 程式碼。
> 與 LB 端的關係：LB 的輸入契約 `TASK_CSV_INPUT_CONTRACT.md`（LB 程式碼為準）定義 **LB 讀什麼**；本 Spec 定義 **MOST 產什麼**。兩者不得矛盾；LB 端修正（Phase 2）以本 Spec §11 的保留欄位為對接面。
> **黃金 fixture**：[`fixtures/server_node_worksheet.json`](fixtures/server_node_worksheet.json) → [`fixtures/server_node_tasks.expected.csv`](fixtures/server_node_tasks.expected.csv)（34 列，已實跑 LB reader／validators／merge detector 通過）。實作必須逐格重現。

---

## 0. 一句話

**MOST 給「工序關聯＋屬性＋單次工時」，LB 做「站／worker／排程／並行／合併」的決定。**
投影層（`lb_projection`）是確定性翻譯：同一份 worksheet ＋ 同一 rule-set → 逐位元相同的 CSV。**不猜、不塌縮、不算 LB 的事。**

---

## 1. 名詞

| 名詞 | 定義 | 落點 |
|---|---|---|
| **WI** | 一句作業描述，底下多個 motion | `wi_rows.sub_activity`（worksheet 情境的 WI 分組）；motion_module（範本情境） |
| **motion** | 一條七格 GM／CM cycle；TMU 最小粒度 | `wi_rows` ⟷ `most_cycles`（1:1） |
| **task** | LB 的一列 | 投影輸出 |
| **episode** | 一個工具的 acquire → use… → release 區間 | 投影層推導 |
| **lot** | LB 的 quantity>1 批量（`units[s,w]` 分攤） | 投影輸出 `quantity/qty_scope/segment/duration_basis` |
| **layer** | Level System 主序 level 值形成的執行層 | `level_entries.level` |
| **chain** | 一個 sub／cub 群組內依 `order` 形成的執行序列；standalone motion 自成一 chain | `level_entries.countersignature/order_in_group` |
| **tool-held motion** | `wi_rows.tool_vocab_id` 指向 `kind='tool'` 詞彙、或 `object_vocab_id` 為 `kind='tool'` 的 motion | `work_vocab_items.kind` |

---

## 2. 粒度：motion → task

| 情況 | 產出 | 依據 |
|---|---|---|
| 一般 motion（非 tool-held） | **1 列** | D1 |
| **tool-held motion，工具在本 motion 內取得**（Pattern B） | **3 列**：acquire（`setup_pre`：slot 0–2 ＋ 重複區塊**前**的不重複 use 格）／use（重複區塊 R；無重複則整個 slot 3–5）／release（`setup_post`：重複區塊**後**的不重複 use 格 ＋ slot 6）；若工具在後續 motion 才放下（§4.3），則 **2 列**（acquire／use；`setup_post` 依 §4.3 歸屬） | ADR-035 D2；§3.3 分桶 |
| tool-held motion，工具已持有（Pattern A 的中段） | **1 列** `tool_action=use` | §4 |
| `object` 為工具且未持有（Pattern A 的「拿起工具」GM） | **1 列** `tool_action=acquire` | §4 |
| `object` 為工具且已持有、GM 放置（Pattern A 的「放下工具」） | **1 列** `tool_action=release` | §4 |
| `is_general=true` | **1 列**，不拆、不帶工具欄、`part_id=General`、`general_role` 明填、無邊 | §5.7 |
| SIMO 從屬列（`simo_group_id` 非空） | **0 列**（時間已在主列；LB 尚無 SIMO 欄） | 過渡方案 D15 |

三列共用：`group`／`segment`／`quantity`／`duration_basis`／`atomic_group`／`offline_flag`／`station_name`／`part_id`／`fixed_station`／`source_wi_row_id`。
拆列**不改工時標準**：`acquire_tmu + N×use_once_tmu + release_tmu == total_tmu`（§7.1）。

---

## 3. 兩個乘數

### 3.1 定義（引擎為準）

| 乘數 | 位置 | 引擎行為 | 物理語意 |
|---|---|---|---|
| `frequency` | `wi_rows.frequency`（Numeric，>0，可為分數） | `compute_table`：`eff_tmu = total_tmu × freq`（`most_engine/calculate.py:319`） | **整個 motion** 重複 N 次（每次都伸手、抓、放、回） |
| `repeat_count` | `slot_inputs.{g2,p5,m3,x4,i5}.repeat_count`（1..99） | `_repeat`（`calculate.py:50`）：G/P/X/I 整格 ×N；M 僅乘動詞分量再 max；**A/B 禁止**（`_no_repeat`） | **手不放、動作重複 N 次**（拿一次電批鎖 8 顆） |

MiniMOST V2 的「A/B 不准 repeat」本身就是 LB 的 setup/cyclic 分界：伸手／身體動作每個 episode 一次，可重複的格才是 cyclic。

### 3.2 投影矩陣（唯一權威）

| motion | `frequency` | slot `repeat_count` | 產出 | 註 |
|---|---|---|---|---|
| 非 tool-held | 1 | 任意 | 1 列，Q=1，repeat 已燙進 `duration` | fixture WI-O（I×12） |
| 非 tool-held | 整數 F>1 | 任意 | 1 列，`quantity=F`、`qty_scope=cyclic`、`duration_basis=once`、`duration`=單次（含 repeat） | fixture WI-G/H；需 group（§6 `group`） |
| 非 tool-held | 非整數 | 任意 | 1 列，Q=1，`duration = round(total_tmu × F × 36)` | `W_FRACTIONAL_FREQUENCY_BAKED` |
| tool-held（Pattern B） | 1 | 全 1 | 3 列（或 2 列），Q=1 | fixture WI-D/F/K/M |
| tool-held（Pattern B） | 1 | use 段**連續區塊 R** 的 repeat = N>1（可為 M/X/I 全部，或其中連續一段） | acquire：`setup`（`setup_pre`）；use：`quantity=N`、`cyclic`、`duration`=單次（只含 R）；release：`setup`（`setup_post`）；三列 `quantity=N`、`duration_basis=once` | fixture WI-I（R={M,X,I}）；「移一次、掃 8 次」＝ R={X,I}，M 進 `setup_pre` |
| tool-held（Pattern B） | 整數 F>1 | 全 1 | 3 列 `quantity=F`、**全部 `cyclic`**（字面語意：拿 F 次） | `W_TOOL_FREQ_ALL_CYCLIC`（幾乎一定是 IE 想用 repeat） |
| tool-held | F>1 | N>1 | **拒絕** | `E_TOOL_FREQ_AND_REPEAT`（無法用單一 quantity 表達） |
| tool-held | 非整數 | — | **拒絕** | `E_TOOL_FRACTIONAL_FREQUENCY` |
| tool-held | — | slot 0–2 有 repeat（G） | **拒絕** | `E_TOOL_ACQUIRE_REPEAT`（取得段必須一次） |
| tool-held | — | R 內 repeat 值不一致 | **拒絕** | `E_REPEAT_MIXED` |
| tool-held | — | 重複格不連續（如 M×8、X 一次、I×8 的夾心） | **拒絕** | `E_REPEAT_NONCONTIGUOUS`（物理上說不通；零工時格不算斷開） |
| tool-held | — | M 含伴隨維度（手度／腳步）且 repeat>1 | **拒絕** | `E_REPEAT_NONLINEAR`（M=max(verb×N, hand, foot) 不可線性拆） |

### 3.3 單次工時的取得——分桶規則（引擎唯一權威，投影層不做 TMU 算術）

**分桶（2026-09-12 裁決）**：一個 tool-held motion 的七格分成三個桶，切點是 use 段（slot 3–5）的**重複區塊**，不是固定的 slot 界線：

```
U   = use 段的非零格，依 slot 順序（3 → 4 → 5）；零工時格不參與判定
R   = U 中 repeat_count > 1 的格
若 R 為空：N = 1；setup_pre = Σ slot_tmus[0..2]；use_once = Σ slot_tmus[3..5]；setup_post = slot_tmus[6]
否則：
  R 內 repeat 值必須相同 → N；不同 → E_REPEAT_MIXED
  R 必須在 U 中連續（前後可有不重複格，中間不可夾不重複格）→ 否則 E_REPEAT_NONCONTIGUOUS
  pre  = U 中位於 R 之前的格；post = U 中位於 R 之後的格
  setup_pre  = Σ slot_tmus[0..2] + Σ_{s∈pre}  slot_tmus[s]          # 每個 episode 一次
  use_once   = Σ_{s∈R} once_slot_tmu(s)                             # 每件一次
  setup_post = Σ_{s∈post} slot_tmus[s] + slot_tmus[6]               # 每個 episode 一次

once_slot_tmu(s)：
  引擎路徑（有 slot_inputs 時必走）= compute_cycle(strip_repeats(slot_inputs, slots=R), rs_snapshot).slot_tmus[s]
  靜態路徑（fixture／無 slot_inputs）= slot_tmus[s] / N            # 逐格除，不是 Σslot[3..5]/N
斷言（兩路徑皆驗）：setup_pre + N × use_once + setup_post == total_tmu（|Δ| ≤ 1e-6 TMU），否則 E_TMU_DECOMPOSITION
```

- 三列時：acquire 列 `duration` ← `setup_pre`、use 列 ← `use_once`、release 列 ← `setup_post`；N=1 時 use 列 Q=1。
- 2 列時（§4.3）：`setup_post` 的歸屬見 §4.3。
- M 含伴隨維度（手度／腳步）且 M∈R → `E_REPEAT_NONLINEAR`（M=max(verb×N, hand, foot) 不可逐格線性拆）。
- `rs_snapshot` = 該列 `most_cycles.rule_set_id`（回放鐵則，ADR-023）。
- 為什麼不是「slot 0–2／3–5／6 固定切」：「拿 scanner → 移到料架（M 一次）→ 掃 8 個（X×8、I×8）」是正常 MOST 建模；固定切會把一次性的 M 乘 8。分桶讓 setup／cyclic 的分界跟著 IE 標的 repeat 走，而不是跟著格子走。

---

## 4. 工具生命週期狀態機（ToolLifecycleResolver）

### 4.1 事件

對每個 chain（§5.3）依執行序逐 motion 判定，對每個工具詞彙 T 維持 `held` 集合：

| 條件 | 事件 | 產出 |
|---|---|---|
| `m.tool_vocab == T` 且 T ∉ held | **IMPLICIT_ACQUIRE**（Pattern B） | 依 §4.3 決定 3 列或 2 列；T 進 held（2 列時） |
| `m.tool_vocab == T` 且 T ∈ held | **USE** | 1 列 `use` |
| `m.object_vocab == T`（kind=tool）、`m.tool_vocab` 空、T ∉ held | **ACQUIRE**（Pattern A） | 1 列 `acquire`；T 進 held |
| `m.object_vocab == T`、T ∈ held、`seq_kind=GM` | **RELEASE**（Pattern A） | 1 列 `release`；T 出 held |
| `m.object_vocab == T`、T ∈ held、`seq_kind=CM` | **USE** | 1 列 `use` |
| `m.tool_vocab` 與 `m.object_vocab` 都是工具且不同 | — | `E_TOOL_TWO_TOOLS`（一列一工具，請拆 motion） |

### 4.2 chain 結束檢查
chain 結束時 `held` 非空 → `E_TOOL_NOT_RELEASED`（列出工具與最後持有的 motion）。跨 chain 持有（A chain 拿、B chain 放）→ `E_TOOL_CROSS_CHAIN`。

### 4.3 Pattern B 的 release 落點
IMPLICIT_ACQUIRE 後**向後看同一 chain**：若在下一次 T 的 ACQUIRE／IMPLICIT_ACQUIRE 之前出現 T 的 RELEASE 事件（GM、object=T）→ 本 motion 產 **2 列**，T 持續 held 到該 RELEASE；否則產 **3 列**，`setup_post`（含 slot 6）即 release 列，T 出 held。

**2 列時 `setup_post` 的歸屬（2026-09-12 修正）**：`setup_post`（區塊後不重複格 ＋ 返回 A）是每個 episode 一次的工時，不得併入會乘 N 的 cyclic 列。
- N = 1：併入 use 列（Q=1，純加總，無乘數問題）。
- N > 1：併入 **acquire 列**（setup 桶；TMU 正確、每 worker 一次；時序上雖發生在最後，但 LB 的 setup 列不帶時序語意）。
原文「slot 6 併入 use 列」在 N>1 時會把一次性的返回 A 乘 N，已由本段取代。

### 4.4 欄位
- `tool_id`：T 的 `name_en` 轉 snake_case（`electric driver` → `electric_driver`）；缺 `name_en` → `tool_<vocab_id 前 8 碼>` ＋ `W_TOOL_NAME_EN_MISSING`。**不同拿取位置＝不同詞彙**（`scanner_holster`／`scanner_cart`），不用 `action_type` 區分。
- `tool_action`：`acquire`／`use`／`release`。
- `action_type`：acquire 列恆 `pick`、release 列恆 `put`（保證 LB 分桶鍵 `(tool_id, action_type)` 在同工具所有取放列相等）；use 列依 §6 `action_type` 規則（IE 標籤優先）。
- `adjustable`：acquire／release 列 **預設 1**；motion 帶 `merge_lock=true` → 0。use 列與非工具列恆 0。
- 同 `tool_id` 的所有 acquire 列 `duration` 必須相等，release 亦然 → 否則 `E_TOOL_ACQUIRE_DURATION_MISMATCH`／`E_TOOL_RELEASE_DURATION_MISMATCH`（對應 LB `MergeCandidateError` C4）。

---

## 5. 分層 DAG 投影（PrecedenceProjector）

### 5.1 前提
先跑 `most_engine.level.validate()`；任何 R1–R9／格式 issue → `E_LEVEL_INVALID`（帶原 code）。投影層**不重寫** Level 規則。

### 5.2 排除
`is_general=true` 的 motion 與 SIMO 從屬列不進 DAG。

### 5.3 群組與 chain
- 群組 = `countersignature`（`sub\d+`／`cub\d+`），`parent_countersignature` 為巢狀（僅 sub ⊃ cub）。
- **chain**：群組直接成員依 `order_in_group` 排序；巢狀 cub 視為一個**區塊**，插入位置＝其成員最小 `seq_no` 相對於直接成員 `seq_no` 的位置（worksheet 列序＝執行序，T3 同一 tie-break）。區塊內依 `order` 排序。
- standalone main motion 自成 chain。
- chain 內相鄰項連邊；tool-held 拆出的 acquire→use→release 是該項的內部鏈（項的 **source**＝acquire 列、**sink**＝release 列；單列項 source=sink=自己）。

### 5.4 層範圍
- **頂層項**（standalone main，或無 parent 的群組）：由其 head 的 `level` 解析為集合 S：`k` → {k}；`a~b` → {a..b}。`lo=min(S)`、`hi=max(S)`。
- 群組成員與巢狀 cub 區塊**繼承所屬頂層項的 [lo,hi]**（巢狀 cub head 自帶的 level 只用於 R1 合法性，不另成層）。
- `a/b`（離散跳號）→ `E_LEVEL_DISCRETE_UNSUPPORTED`（User 裁決不設計，D8）。

### 5.5 層間邊
定義偏序 `Y ≺ X ⟺ hi_Y < lo_X`（頂層項之間）。取其**傳遞縮減**（transitive reduction）為層間邊；每條層間邊由 **Y 的 sink** 連到 **X 的 source**。
- 整數 level：第 k 層所有項 → 第 k+1 層所有項的 source ✅（D8）。
- `1~2`：與第 1、2 層無邊（平行），第 3 層以它為前置 ✅（有界平行）。
- 同一層的頂層項之間無邊 ＝ LB P1 平行。

### 5.6 offline
`offline=true` 的 motion 照常進 DAG（LB 橋接）。

### 5.7 general
無邊；`part_id=General`；`general_role` 明填三值之一：`take_unit`（首站站頭一次，例：把機箱上線）／`scanner`（每站站頭，例：掃工單）／`transport`（每站站尾，例：推到下一站）。**LB 現況**仍靠 `action` 關鍵字分類（`general_task/processor.py::classify_category`：含 transport/transfer → TRANSPORT；含 scan/scanner → SCANNER；其餘 → TAKE_UNIT），因此投影層產出的 `action` 必須與 `general_role` 相容：`take_unit` 的 `action` **不得**含 transport／transfer／scan；`transport` 的 `action` 必含 transport；`scanner` 的 `action` 必含 scan。不相容 → `E_GENERAL_ROLE_ACTION_MISMATCH`。LB Phase 2 改讀 `general_role` 欄後，此關鍵字相容規則降為 W。

> **為什麼要明填（2026-09-11 實跑發現）**：fixture v1.0 把「把機箱上線」寫成 `transport chassis onto conveyor`，LB 依關鍵字歸為 TRANSPORT，於是在**每一站站尾**各插一份 2 160 ms（6 站 ＝ 12 960 ms 假負載）。一次性的上線動作是 TAKE_UNIT，只該出現在首站站頭。

### 5.8 nb（不可同站）
LB 無對應欄 → **不匯出**，`W_NB_UNSUPPORTED`（列入 §11 保留）。

### 5.9 編號（T3）
Kahn 拓撲排序，就緒集合以 `(seq_no, part_index)` 最小者優先（part_index：acquire=0、use=1、release=2）。`task_id` 自 1 連號；保證 `pred_id < task_id`。同資料同輸出。

### 5.10 浮動偵測
非 general、無前置、無後繼 → `W_FLOATING_TASK`。

---

## 6. 欄位契約（輸出 24 欄，順序凍結）

**順序**：`task_id, action, part_id, group, atomic_group, duration, predecessors, station_name, action_type, complexity_level, adjustable, fixed_station, offline_flag, tool_id, tool_action, divisible, p2, quantity, segment, qty_scope, duration_basis, source_wi_row_id, role_type, general_role`
（前 21 欄 = LB `TASK_CSV_COLUMN_DEFS` 順序；後 3 欄為擴充，LB reader 現況忽略未知欄——已實測。）

| 欄 | 值域 | MOST 來源／推導 | 空值規則 |
|---|---|---|---|
| `task_id` | 正整數 | §5.9 | 必填 |
| `action` | 英文字串 | use／單列：`most_cycles.narrative_en`；acquire：`pick up {tool name_en}`；release：`put down {tool name_en}` | 缺 `narrative_en` → `E_NARRATIVE_EN_MISSING`（D14：要餵 LB 的列必須先補英文） |
| `part_id` | 字串 | `wi_rows.key_parts`；general → 字面 `General` | 空可 |
| `group` | int | `cub\d+` → 直接取 label 數字（`cub30 → 30`；label 唯一 R8，不會衝突）；Q>1 且無 cub → 合成 `9000+seq_no` ＋ `W_AUTO_GROUP_FOR_LOT`；tool-held 三列同 group | Q=1 且無 cub → 空 |
| `atomic_group` | int | `wcub\d+` → 數字 | 空可 |
| `duration` | 非負整數 ms | `round_half_up(tmu × 36)`；tmu 依 §3.3 | 必填 |
| `predecessors` | `a,b,c` 逗號 | §5 | 空可 |
| `station_name` | 字串 | `wi_rows.sub_activity`（passthrough，LB 不綁定） | 空可 |
| `action_type` | 短英文碼 | **優先序**：① acquire 列恆 `pick`、release 列恆 `put`；② general 列依 `general_role`（take_unit→`take`、scanner→`scan`、transport→`transport`）；③ `lb_tags.action_type`（IE 在 Level System 選填的動作標籤，如 `remove`／`test`／`latch`）；④ 附錄 A 由 slot 選項碼推導；⑤ `op` ＋ `W_ACTION_TYPE_FALLBACK`。只有 ①② 有求解意義（LB 分桶鍵／General 分類），③④⑤ 純顯示 | 必填 |
| `complexity_level` | — | **恆空**（LB solver 不消費；Phase 2 擬刪） | 空 |
| `adjustable` | 0/1 | §4.4 | 必填 |
| `fixed_station` | 正整數（1-based） | `station_pin` | 空可 |
| `offline_flag` | 0/1 | `offline` | 必填 |
| `tool_id` | snake_case | §4.4 | 非工具列空 |
| `tool_action` | acquire/use/release | §4 | 非工具列空；與 `tool_id` 同空同非空 |
| `divisible` | 0/1 | `splittable`；tool-held 或 Q>1 motion 標 splittable → `E_SPLITTABLE_CONFLICT`。**追記（2026-09-12）**：`splittable` 只存在於投影層輸入（fixture 路徑，為覆蓋 24 欄）；`level_entries` 無此欄、UI 不提供，**產品路徑恆 0**——LB ADR-023 §4：「MOST 不輸出 `divisible`；與 quantity 收斂另立 ADR」。 | 必填 |
| `p2` | — | **恆空**（D10：人數交 solver；LB 端可自行填） | 空 |
| `quantity` | 正整數 | §3.2 | 必填（預設 1） |
| `segment` | 字串 | `lb_tags.segment`；Q>1 時建議明填；同 segment 必同 cub（`E_SEGMENT_CROSS_GROUP`） | 空可 |
| `qty_scope` | setup/cyclic | §3.2；**不輸出 `auto`** | Q=1 空 |
| `duration_basis` | `once` | Q>1 恆 `once` | Q=1 空 |
| `source_wi_row_id` | UUID | `wi_rows.id`（D13 對應鍵；同 motion 三列相同） | 必填 |
| `role_type` | human/machine | ~~CM 的 X 格 `x_seconds ≥ 1`（機台製程）→ `machine`；其餘 `human`（D17；LB 現況忽略）~~ **修訂（2026-09-12，Howard 裁決）**：`machine` ⇔ CM ∧ `x_seconds ≥ 1` ∧ `lb_tags.machine_unattended == true`（IE 明確斷言「人不用顧」）；其餘一律 `human`（含 `machine_unattended` 為 null／false）。理由：X 格只有秒數，不知道人走不走得開（黃金 N2「握著擋板熱熔」即為看顧中的機台時間）；保守預設避免 LB 人力偏樂觀。LB 端另有求解政策 `unattended_machine_policy`（free／busy，ADR-023 D9 追記）決定 `machine` 是否真的不佔人——**事實在 MOST、政策在 LB**。v1 已知近似：`machine` 列的 A B G M I 人工格（黃金三列 0.11–0.65 s）併入機台時間、不佔人；拆列見 §11。 | 必填 |
| `general_role` | take_unit/scanner/transport | `lb_tags.general_role`；僅 general 列有值（§5.7；LB 現況忽略，Phase 2 改讀） | 非 general 空 |

---

## 7. 不變量（匯出前必驗、測試必鎖）

1. **TMU 守恆**：`Σ_motions(total_tmu × freq_int) == Σ_tasks(once_tmu × (quantity if cyclic else 1))`（TMU 域，精確；單一 motion 的分桶守恆見 §3.3）；ms 域 `|Δ| ≤ tasks_out`（每列 ≤0.5 ms 捨入）。SIMO 從屬列與 general 列以各自規則計入。
2. **拓撲**：`task_id` 唯一連號；每個 predecessor id < 自身；無重複、皆存在。
3. **生命週期良構**：每個 acquire 恰一個 clean release；每個 use 被 episode 覆蓋；chain 結束 held 空。
4. **組內傳染**：同 cub 內 `offline` 一致；同 cub 內 Q>1 列 `quantity`／`duration_basis` 一致；同 wcub 內 `offline` 一致、成員 Q≤1、不跨多個 cub。
5. **互斥**：Q>1 ⊥ `divisible`；Q>1 ⊥ `atomic_group`；`divisible` ⊥ acquire/release；`atomic_group` 成員無工具欄（wcub 標在 tool-held motion → `E_ATOMIC_ON_TOOL_MOTION`）。
6. **取放等長**：同 `tool_id` 所有 acquire 列 `duration` 相等；release 相等。
7. **過渡期守衛（LB ADR-001 追記缺口）**：同一 `tool_id` 不得同時出現在 Q>1 episode 與 Q=1 episode → `E_TOOL_ID_SHARED_ACROSS_LOT`（提示：為批量情境另立詞彙，如 `electric_driver_lot`）。**降級條件：LB `feature/most-integration-phase2` 合入 master 後**（`detect_merge_candidates` 修好、過渡缺口消除）方可降為 W；在此之前**維持 E**（擋匯出），不得提前降級。
8. **表頭凍結**：24 欄名與順序 ＝ §6；任何變動 ＝ `contract_version` 升版 ＋ LB 契約同步。

---

## 8. 匯出前驗證與報告（CsvContractValidator）

### 8.1 錯誤碼（E＝擋匯出；W＝放行、進報告）

| 碼 | 觸發 | 修法提示（給 IE） |
|---|---|---|
| `E_LEVEL_INVALID` | `level.validate()` 有 issue | 先修 Level 表（附原 code） |
| `E_LEVEL_DISCRETE_UNSUPPORTED` | level 含 `/` | 改用連續範圍 `a~b` 或單值 |
| `E_TOOL_NOT_RELEASED` | chain 結束仍持有 | 補「放下 X」motion，或確認最後一個持工具 motion 的返回即放回 |
| `E_TOOL_CROSS_CHAIN` | 跨 chain 持有 | 把拿／放放進同一 sub |
| `E_TOOL_TWO_TOOLS` | 一 motion 兩工具 | 拆 motion |
| `E_TOOL_FREQ_AND_REPEAT` | 持工具 F>1 且 N>1 | 二擇一：整體重複拆成多列 motion，或只用 repeat |
| `E_TOOL_FRACTIONAL_FREQUENCY` | 持工具 frequency 非整數 | 改整數或拆 motion |
| `E_TOOL_ACQUIRE_REPEAT` | slot 0–2 有 repeat | 取得只做一次；重複放 3–5 |
| `E_REPEAT_MIXED` | 重複區塊 R 內 repeat 值不一致 | 統一 repeat |
| `E_REPEAT_NONCONTIGUOUS` | use 段重複格之間夾著不重複的非零格（§3.3） | 夾在中間的動作拆成獨立 motion，或也標 repeat |
| `E_REPEAT_NONLINEAR` | M 伴隨維度＋repeat | 伴隨動作拆獨立 motion |
| `E_TMU_DECOMPOSITION` | §3.3 斷言失敗 | 系統錯誤，回報開發 |
| `E_TOOL_ACQUIRE_DURATION_MISMATCH` / `E_TOOL_RELEASE_DURATION_MISMATCH` | 同工具取／放工時不同 | 不同位置用不同詞彙 |
| `E_TOOL_ID_SHARED_ACROSS_LOT` | §7.7 | 批量用獨立工具詞彙（過渡） |
| `E_NARRATIVE_EN_MISSING` | 要匯出的 motion 無英文敘事 | 先跑 i18n review（ADR-032） |
| `E_SEGMENT_CROSS_GROUP` | 同 segment 跨 cub | segment 依附 cub |
| `E_SPLITTABLE_CONFLICT` | splittable 標在工具／批量 motion | 移除 |
| `E_ATOMIC_ON_TOOL_MOTION` | wcub 標在 tool-held motion | 移除（工具 episode 由 segment 綁同人） |
| `E_ATOMIC_QUANTITY` | wcub 成員 Q>1 | 移除 wcub 或 frequency |
| `E_ATOMIC_CROSS_GROUP` | wcub 跨多個 cub | 調整分組 |
| `E_OFFLINE_INCONSISTENT` | cub／wcub 內 offline 不一致 | UI 傳染應已擋；修資料 |
| `E_GENERAL_IN_GROUP` | general motion 帶 cub／wcub | general 不分組 |
| `E_GENERAL_ROLE_MISSING` | `is_general` 但無 `general_role` | 選 take_unit／scanner／transport |
| `E_GENERAL_ROLE_ACTION_MISMATCH` | `action` 關鍵字與 `general_role` 不相容（§5.7） | 改 `narrative_en` 或改 role |
| `W_TOOL_FREQ_ALL_CYCLIC` | 持工具 F>1 | 想要「拿一次做 N 次」請用 repeat |
| `W_FRACTIONAL_FREQUENCY_BAKED` | 非整數 frequency 燙進 duration | — |
| `W_AUTO_GROUP_FOR_LOT` | 無 cub 的 Q>1 motion 合成 group | 可明標 cub |
| `W_NB_UNSUPPORTED` | nb 標記被丟棄 | 等 LB 支援 |
| `W_FLOATING_TASK` | §5.10 | 確認是否漏標依賴 |
| `W_TOOL_NAME_EN_MISSING` | 工具詞彙無 `name_en` | 補英文 |
| `W_GENERAL_WITH_TOOL` | general motion 持工具 | 以單列輸出、工具欄丟棄 |
| `W_SIMO_COLLAPSED` | 有 SIMO 從屬列被略過 | 過渡方案 D15 |
| `W_ACTION_TYPE_FALLBACK` | 無 IE 標籤且附錄 A 推不出（無 slot 選項碼）→ `op` | 在 Level System 補動作標籤 |

### 8.2 匯出報告（與 CSV 同時產出）

```json
{ "contract_version": "most-lb-csv-v1.1", "worksheet_id": "...", "revision_no": 7, "rule_set_code": "MINIMOST_FACTORY_V2",
  "rows_in": 24, "rows_simo_collapsed": [], "tasks_out": 34,
  "tmu_total_most": 2603.445, "ms_total_lb_one_worker": 93724,
  "groups": {"30": [11,12], "40": [13,14,15], "10": [22,23,24,25,26,27], "11": [28,29,30]},
  "atomic_groups": {"20": [16,17,18], "21": [28,29,30]},
  "tool_episodes": [{"tool_id":"scanner","acquire":4,"use":[5],"release":6}, ...],
  "warnings": [{"code":"W_...","wi_row_id":"...","message":"..."}],
  "nb_dropped": [], "columns": ["task_id", "...", "role_type"] }
```

> **報告加法欄位（2026-09-12，實作書 `LEVEL_SYSTEM_JOB_UX`）：** `errors[]`／`warnings[]` 各項可帶 `params`（結構化參數，供前端組使用者語言句；訊息字串不變）；新增 `rows[]`（每列摘要：`wi_row_id`／`task_ids`／`tool_id`／`parts`／`repeat_n`／`frequency`／`quantity`／`qty_scope`／`x_seconds`／`is_general`／`general_role`／`duration_ms_total`）、`hints[]`（確定性提示，種類見實作書 §7.2）、`tasks[]`（僅 `include_tasks=true` 時）。皆為加法欄位——**CSV 24 欄與 `contract_version` 不變**。（§6 `divisible` 列的追記已由架構師加，不重寫。）

---

## 9. 黃金 fixture 與驗收

- 輸入：`fixtures/server_node_worksheet.json`（24 motions；欄位形狀＝`ProjectionRow`，見實作書 WP2）。
- 期望：`fixtures/server_node_tasks.expected.csv`（34 列 × 24 欄）。**逐位元相等**（含空值、順序、`\n` 換行）。
- 數字：Σ MOST 2 603.445 TMU；Σ LB（一人）93 724 ms；merge 候選恰 1 組（scanner 4/8）；`torque_driver` 因 `merge_lock` 排除；`electric_driver` 因 Q>1 排除。
- 覆蓋：Pattern B ×5（D/F/I/K/M）、repeat 拆乘數（I）、frequency 批量（G/H）、巢狀 cub（cub30 ⊂ sub2）、cub only（10）、wcub only（20）、cub+wcub（11/21）、station pin（P）、offline（B）、general（A）、splittable（O）、role machine（L2/N2/P2）、有界平行（L2 六個入口）、L1 兩根（B、C）。
- 補充 fixture（實作書 WP10）：Pattern A 三 motion、2 列 Pattern B（後續 GM 放下）、SIMO 略過、每個 E／W 碼各一反例。

---

## 10. 版本規則

- `contract_version` 字串進匯出報告；CSV 本體無 metadata。**版本字串的唯一權威是本檔 §0 的標題**（現為 `most-lb-csv-v1.1`）；`emit.CONTRACT_VERSION`、§8.2 報告、fixture `contract_version`、freeze test 四處必須與之相等。
- **加欄**（尾端、LB 忽略）＝ minor（v1.x），仍須同步 LB 契約「保留欄位」表。**改名／改序／改語意／刪欄**＝ major（v2），須新 ADR ＋ LB 端同步落地後才切換。
- 表頭凍結測試（實作書 WP10）是升版的唯一開關。

---

## 11. 保留欄位與未來（LB Phase 2 對接面）

| 欄／概念 | 狀態 | 對接 |
|---|---|---|
| `source_wi_row_id` | v1 已輸出 | LB 需保留並在回寫（D13）帶回 |
| `role_type` | v1 已輸出；2026-09-12 規則修訂為需 `machine_unattended` 斷言（§6） | LB Phase 2 WP-L9 消費：`machine` 不佔 worker、仍進站 makespan；求解政策 `unattended_machine_policy` 可整批降級為 busy（ADR-023 D9 追記） |
| `machine` 列拆成「人工前段（A B G M）／X／人工後段（I A）」 | 未做（v1 近似：整列不佔人） | Phase 3：沿工具拆列的分桶機制（§3.3）新增 machine 分解；黃金 task 數會變 |
| `general_role` | v1.1 已輸出 | LB Phase 2 以此取代 `part_id=General` ∧ 無 pred ∧ `action` 關鍵字三欄魔術值 |
| `simo_group` | 未輸出 | LB 加欄＋max 計算後，MOST 從屬列改為輸出（D15） |
| `nb`（不可同站） | 丟棄＋W | LB 加 `max_per_station` 類約束 |
| `wi_group` | 未輸出 | 待 WI 層物件在 worksheet 情境有穩定 id |
| `p2` | 恆空 | LB 端規劃者覆蓋 |
| 「lot 必須同一人一氣完成」 | 不可表達 | LB 允許 `p2=1` 或 atomic 對 Q>1 定義為 Σused=1 |
| `complexity_level` | 恆空 | LB 擬刪 |

---

## 附錄 A：`action_type` 推導（fallback；優先序見 §6）

> **定位（2026-09-12）**：本表只在 `lb_tags.action_type` 缺值時用 slot **選項碼**（`slot_inputs` 的 `g_code`／`p_base_code`／`p_addon_codes`／`m_components[].verb_code`／`x_code`）推導；沒有 `slot_inputs` 的靜態 fixture 路徑不走本表。像 `remove`（從治具取出 vs 放入治具，slot 形狀相同）、`test`（ICT 測試不是 MiniMOST X 字典選項）這類語意，**結構碼推不出來**，只能由 IE 標。黃金 fixture 因此每個 motion 都帶 `lb_tags.action_type`。

| 條件（依序） | 值 |
|---|---|
| acquire 列 | `pick` |
| release 列 | `put` |
| general：依 `general_role` → `take`／`scan`／`transport` | — |
| CM 且 X 格 code 屬掃描類（`x_scan*`／刷條碼） | `scan` |
| CM 且 X 格 code 屬鎖附類 | `fasten` |
| CM 且 X 格 code 屬壓合／熱熔／點膠類，或 `x_seconds ≥ 1` | `press` |
| CM 且 X=0、I 非零、M=0 | `inspect` |
| CM 其他 | M 動詞碼字典英文（`push`/`pull`/`rotate`…）；無 → `move` |
| GM 且 P 含 insert 附加 | `insert` |
| GM 且 P 含 snap／pressure 附加 | `latch` |
| GM 且 G 為 collect | `collect` |
| GM 且 object 為 tool（Pattern A 取放已在前兩列處理） | — |
| GM 其他 | `place`（P 非 hold）／`pick`（P=hold） |
| 任一為空 | `op`（＋ `W_ACTION_TYPE_FALLBACK`） |

僅 acquire/release 列的值有求解意義（LB 分桶鍵）；其餘為顯示標籤。

## 附錄 B：本契約刻意繞開／揭露的 LB 端缺口（Phase 2 清單）

1. ADR-001 追記：Q>1 release／USE 側未過濾 → §7.7 過渡守衛。
2. `fixed_station` 僅固定站數模式生效。
3. D8 浮動警示對 general 應豁免（本 Spec 已排除）。
4. `action_type` 作分桶鍵是求解器等長簡化的洩漏 → 本 Spec 以恆值 `pick`/`put` ＋ 等長驗證吸收。
5. `adjustable` 預設 0 → 本 Spec 主動輸出 1。
6. 「Q>1 必須有 group」對單列 lot 是樣板 → 本 Spec 合成 group。
7. 表達力缺口：lot 必須一人完成（§11）。
