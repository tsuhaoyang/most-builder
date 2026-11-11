# Line Balance 系統 — Task CSV 輸入契約（給 MOST 系統的整合規格）

> **對象**：MOST（工時標準來源系統）的 agent / 開發者。
> **目的**：讓 MOST 清楚知道要產出什麼樣的 task CSV，才能餵給 Line Balance（下稱 **LB**）系統做產線平衡優化。
> **關係**：MOST 是**工時標準與資料來源**（產生 task CSV）；LB 是**消費方**（讀 CSV → CP-SAT 求解 → 產出站別/人力/KPI）。本文只描述「LB 需要什麼輸入」，不描述 LB 內部求解演算法細節。
> **權威來源**：本文內容取自 LB 程式碼與 ADR。若本文與 LB 程式碼衝突，以程式碼為準。逐欄語意與硬規則的查證出處：
> - 欄位 SSOT 與 header 別名、跨欄驗證：`src/shared/domain/task_csv_columns.py`（`TASK_CSV_COLUMN_DEFS`、`_HEADER_ALIAS_TO_STD`、`map_csv_row_to_task_row_dict`）
> - CSV 讀取 schema（哪些欄真的會被讀）：`src/optimization/io/reader.py`（`_process_tasks_v2` 的 `CSVSchema`）
> - CSV→solver 唯一轉換：`src/optimization/algorithms/multi_line_engine/engine.py`（`_to_solver_task`，含 `p2` 閘門在 line 206）
> - Quantity lot 契約驗證（Fail-Fast）與 qty_scope 解析：`src/optimization/features/quantity/policy.py`（`validate_quantity_contract`、`_validate_group_quantity`、`resolve_qty_scope`）；值域解析：`src/shared/domain/quantity.py`（`parse_qty_scope`、`parse_duration_basis`）
> - Quantity lot 求解語意（segment 保證程度、p2 人數鎖）：`middle-earth-pkg/src/multi_line_solver/solver/quantity_lot.py`（`segment_key`、`collect_quantity_segments`）與 `middle-earth-pkg/src/multi_line_solver/solver/constraints.py`（`QuantityLotConstraint`，line 1097–1150）
> - 工具閉包 merge 候選判定：`middle-earth-pkg/src/multi_line_solver/solver/merge_candidate_detector.py`
> - 決策背景：ADR-001（tool closure）、ADR-006（兩種 parallel）、ADR-008（quantity lot）、ADR-017（atomic group）

---

## 0. LB 在做什麼（一句話版）

LB 讀一份 **task CSV**（一列一個工序 task），把這些 task 依「前後關係（DAG）」與各種約束，分配到**生產線 → 工站（station）→ 工人（worker）**上，讓每站的工作量平衡、逼近目標節拍（takt），並算出人力數、瓶頸、平衡率等 KPI。

MOST 要做的事：**產生這份 task CSV**，每個欄位的值都要符合下面的契約，否則 LB 會 Fail-Fast 拒絕（丟錯，不會猜）。

---

## 1. Task DAG 的邏輯

### 1.1 每一列是一個 task

一列 = 一個最小工序單位（例：「拿起掃描槍」「掃描 a 面」「鎖 HDD 螺絲」）。每個 task 有唯一 `task_id`（正整數）。

### 1.2 前後關係用 `predecessors` 表達，形成有向無環圖（DAG）

- `predecessors` 欄列出「這個 task 開始前必須先完成的 task_id」，多個用分隔符隔開（見 §2）。
- 整體構成一個 **DAG**（有向無環圖）：node = task，edge = 「先做 A 才能做 B」。
- **硬規則（LB 會驗證，違反即拒絕）**：
  - **每個 predecessor 的 task_id 必須「小於」該 task 自己的 task_id**。即 CSV 的 task_id 必須是一個**拓撲排序後的編號**——上游 task 編號一定比下游小。
    - 例：task 5 的 predecessors 可以是 `1;3`，但**不能**是 `7`（7 > 5，會被拒）。
    - 這條規則讓 LB 不需要另外偵測環（cycle）——編號單調遞增本身就保證無環。
    - **MOST 必須負責**：輸出前先對 task 做拓撲排序並重新編號，確保「predecessor 的 id < 自己的 id」。
  - `task_id` 不可重複（重複列會被拒）。
  - predecessor 指向的 task_id 必須存在於同一份 CSV。
- LB 內部會把 task_id 正規化（renumber，從 1 開始連續），但**你送進來時就必須滿足上面的單調性**。

### 1.3 DAG 不等於執行順序，而是「約束」

DAG 只表達「誰必須在誰之前」。LB 求解器會在滿足 DAG 的前提下，決定：
- 每個 task 落在哪條線、哪一站、由哪個 worker 做；
- 同一站內 task 的先後（仍受 DAG 約束）。

沒有 predecessor 關係的兩個 task 之間，LB 可以自由安排順序、可以放不同站、可以並行（由不同 worker 同時做）。這就是「結構平行 P1」（見 §3.4）。

### 1.4 跨站的 predecessor（paced line 語意）

LB 是節拍線（paced line）模型：上游站在前一個節拍就已把半成品做完傳下來。所以「跨站」的 predecessor 只約束「站的先後順序（上游站的 slot 編號要小）」，不要求 LB 在同一個節拍內把上下游擠在一起。**MOST 不需要為此做特殊處理**——照實填 predecessors 即可。

---

## 2. Task CSV 所有欄位定義

**時間單位**：LB 的 `duration` 欄位單位由部署宣告（`.env` 的 `CSV_INPUT_TIME_UNIT`，預設 `ms` 毫秒）。**MOST 產出的所有 duration 必須用同一個宣告單位**（整份 CSV 一致）。LB 不會從數值大小猜單位——宣告是毫秒就當毫秒。**建議 MOST 與 LB 約定統一用毫秒（ms）整數，且填「一件」的工時**，避免小數與單位歧義（批量語意見 §3.5 `duration_basis`）。

**欄位大小寫 / 別名**：LB 會正規化 header（小寫、空白/連字號轉底線，見 `task_csv_columns.py::_normalize_header_key`）並支援別名（`_HEADER_ALIAS_TO_STD`）。下表「別名」欄列出可接受的 header 寫法；建議 MOST 直接用「標準欄名」。

**必填 vs 選填**：只有 `task_id` 與 `duration` 是必填（`reader.py` schema `required=True`）。其餘皆選填，缺欄或空值走預設值。

> **⚠️ 已移除的欄位（MOST 不要再輸出）**：`eligible_worker_types`、`duration_robot_ms`。經逐條查證確認這兩欄**接不上 CSV 輸入路徑**——`reader.py` 的 `_process_tasks_v2` schema 不讀、主 domain `TaskDetail` 沒有這兩個欄位、`engine.py::_to_solver_task`（CSV→solver 的唯一轉換）不傳。middle-earth solver 的 `Task` 雖有 `eligible_worker_types` 與 `duration_by_type`（注意：不是 `duration_robot_ms`），但**只能由直接呼叫該套件的程式碼設定**，MOST 從 CSV 標這兩欄完全無作用。因此本契約不承認這兩欄，MOST 標了會被靜默忽略、造成誤解。

### 2.1 核心欄位（必填 + 常用）

| 標準欄名 | 型別 | 必填 | 預設 | 別名 | 意義與對 LB 的影響 |
|---|---|---|---|---|---|
| `task_id` | 正整數 | ✅ | — | id, task, taskid | 唯一識別。必須滿足「predecessor id < 自己 id」（§1.2）。不可重複。 |
| `duration` | 整數（時間單位見上） | ✅ | — | time, processing_time, task_time, dur | 這個 task 做**一次（一件）**要多久。是平衡的基本量。不可為負。**批量時的語意見 §3.5（`duration_basis`）**——預設就是「一件」。 |
| `predecessors` | task_id 清單 | 否 | 空 | dependencies, preds, succ, prior | 前置 task。多個以 `;` 或 `,` 或空白分隔（LB 用寬鬆整數清單解析 `to_int_list`）。每個值必須 < 自己 task_id。 |
| `action` | 字串 | 否 | 空 | （無別名） | 工序的敘述文字（如「拿起掃描槍」）。**用於 General task 判定**（見 §3.6）。**注意：merge 候選的分桶鍵是 `action_type`，不是 `action`**（見 §3.2）。 |
| `action_type` | 字串 | 否 | 空 | operation_type | 動作類型短標籤（如 `pick`/`scan`/`put`）。**是 merge 候選的分桶鍵之一**（正規化後與 `tool_id` 組成 `(tool_id, norm_desc)`，見 §3.2）。 |
| `part_id` | 字串 | 否 | 空 | part, component, bom_id | 零件識別。**特殊值 `General`**：配合無 predecessor + 特定 action，會被當「通用工序」前抽後插（見 §3.6）。 |
| `station_name` | 字串 | 否 | 空 | station, station_id, station_index, configuration | 建議站別（軟性參考）。一般留空讓 LB 決定。 |
| `complexity_level` | 字串 | 否 | 空 | complexity, difficulty | 複雜度標籤，餵給 solver 的複雜度映射。 |

### 2.2 約束類欄位（決定 task 怎麼被分配）

| 標準欄名 | 型別 | 必填 | 預設 | 別名 | 意義與對 LB 的影響 |
|---|---|---|---|---|---|
| `offline_flag` | bool（0/1） | 否 | 0 | offline, is_offline | 1 = 離線工序，不佔線上節拍（見 §3.1）。 |
| `group` | 整數 \| 空 | 否 | 空 | grp, group_id, task_group | **不可拆站**群組：同 group 值的 task 必須分到**同一工站**（見 §3.7）。 |
| `atomic_group` | 整數 \| 空 | 否 | 空 | atomic, atomic_group_id, action_group | **不可拆動作**群組：同值 task 必須**同一 worker 連續完成、中間不插入其他工序**（見 §3.8）。與 `group` 正交。 |
| `fixed_station` | 字串 | 否 | 空 | fixed_st, fix_station, fixedstation | 把 task 釘死在指定站（0-based 索引）。慎用——可能造成無解。 |
| `adjustable` | bool（0/1） | 否 | 0 | is_adjustable, flex, flexible | 是否允許參與 merge 合併（merge 候選的必要條件之一，見 §3.2）。 |

### 2.3 工具閉包 merge 欄位（ADR-001，見 §3.2）

| 標準欄名 | 型別 | 必填 | 預設 | 別名 | 意義 |
|---|---|---|---|---|---|
| `tool_id` | 字串 \| 空 | 否 | 空 | tool, tool_name | 工具識別（如 `scanner`）。同一實體工具用同一 id。空 = 這個 task 不涉及工具。 |
| `tool_action` | enum: `acquire`/`use`/`release` | 條件必填 | 空 | tool_op | 對工具做什麼：取起 / 使用中 / 放下。**`tool_id` 非空時此欄必填**；**此欄非空時 `tool_id` 必填**（雙向）；值域外會被 Fail-Fast 拒絕（`map_csv_row_to_task_row_dict`）。 |

### 2.4 Quantity lot 欄位（ADR-008，見 §3.5）

| 標準欄名 | 型別 | 必填 | 預設 | 別名 | 意義 |
|---|---|---|---|---|---|
| `quantity` | 整數 ≥1 | 否 | 1 | qty, lot_quantity | 這個 task 要做幾件（批量）。>1 觸發 lot 分攤機制，並帶一串強制硬規則（見 §3.5）。 |
| `segment` | 字串 \| 空 | 否 | 空 | qty_segment | 批量分段鍵。同 `(group, segment)` 的 task 共用同一組人力分攤向量（見 §3.5 的 segment 保證程度）。 |
| `qty_scope` | enum: `auto`/`setup`/`cyclic` | 否 | auto | quantity_scope | 這列的工時是否隨件數放大：`cyclic`=每件都做（×該人分到的件數）、`setup`=每人做一次（不隨件數）、`auto`=由 tool_action 推定。值域外 Fail-Fast（`parse_qty_scope`）。 |
| `duration_basis` | enum: `once`/`lot_total` \| 空 | 否 | 空 | duration_includes_quantity | `duration` 填的是「一件」還是「整批總和」。**Q>1 時必填**（缺 → Fail-Fast）。**強烈建議填 `once`（一件）**。值域外 Fail-Fast（`parse_duration_basis`）。 |

### 2.5 其他選填欄位

| 標準欄名 | 型別 | 預設 | 別名 | 意義 |
|---|---|---|---|---|
| `divisible` | bool（0/1） | 0 | splittable, dividable | 是否可被拆給多人分工（R3 split overlay）。與 `quantity>1` 互斥、與 tool `acquire`/`release` 互斥（皆 Fail-Fast，見 §3.9）。 |
| `p2` | 整數 ≥2 \| 空 | 空 | p2_share_worker_count | **quantity lot 的可選人數鎖**：只在 `quantity>1` 時生效，凍結該 lot 剛好由 k 個 worker 分攤（見 §3.4）。不是通用的「多人平行」旗標。 |

---

## 3. 與 task CSV 相關的功能（MOST 要理解才能正確產資料）

### 3.1 Offline（離線工序）

**語意**：`offline_flag=1` 的 task 不佔線上節拍。物理假設是「它在被需要之前就已在旁邊做好」（例如預先在離線區備料），所以它**不進工站的 cycle time、不算進 worker load、不會成為瓶頸**。它的工時只記在專屬的離線負載欄供顯示。

**對 DAG 的影響**：offline task 若是某 online task 的 predecessor，LB 會把它「橋接跳過」——`online A → offline X → online B` 在求解時視為 `A → B`（保留順序、工時歸零）。

**MOST 要做的**：
- 只需在該 task 標 `offline_flag=1`。
- **不要**因為某 task 離線就把它從 CSV 拿掉——它仍要在 CSV 裡，predecessors 關係照填，LB 自己會處理橋接。
- 同一個 `group` 內的 offline_flag 必須一致（見 §3.7）；同一個 `atomic_group` 內的 offline_flag 也必須一致（見 §3.8）。

### 3.2 Merge（工具閉包合併，ADR-001）

**語意**：當兩條互不可達的支路各自都有「拿起同一個工具 → 用 → 放下」，LB 可以決定合併，讓工具只拿放一次（省掉重複的取放時間）。例：a 面掃描與 b 面掃描各自「拿起掃描槍…放下掃描槍」，合併後掃描槍拿一次貫穿兩段、放一次。

**merge 候選的資格（LB 用這些欄位判定，MOST 要正確標）**——出處 `merge_candidate_detector.py`：
- `tool_id`：同一實體工具用**同一個 id**（分桶鍵的一部分）。
- **分桶鍵是 `(tool_id, norm_desc)`，其中 `norm_desc = " ".join(action_type.split())`**。也就是說，兩個 acquire 要成為共同 merge 候選，必須 **`tool_id` 相同、且 `action_type`（短標籤）正規化後（去多餘空白）相同**。**比對的是 `action_type`，不是 `action`（敘述文字）。**
- `adjustable=1`（`adjustable=0` 直接跳過，不進候選）。
- 非 offline（`offline_flag=1` 跳過）。
- `quantity ≤ 1`（`quantity>1` 的 task 不參與 merge）。
- 非 `atomic_group` 成員（`atomic_group` 有值就跳過）。
- 兩個 acquire 必須 **在 DAG 上互不可達** 才會成為同一組候選（同一支路的先後兩次取放不會被互相合併）。

**工具生命週期良構性（Fail-Fast，`ToolSequenceError`）**：
- 每個 `acquire` 必須有**唯一**一個 clean paired `release`（0 個或 ≥2 個可達 release → `ToolSequenceError`）。「clean」= 從 acquire 到該 release 的所有路徑中間，沒有同工具的其他 acquire/release。
- 每個 `use` task 必須被某個 acquire→release episode 覆蓋（沒被覆蓋的孤兒 use → `ToolSequenceError`）。
- `tool_action` 值域 `{acquire, use, release}`；`tool_action` 非空時 `tool_id` 必填（`reader.py` + `map_csv_row_to_task_row_dict` 皆驗）。

**MOST 要做的**：
- 對「會重複取放同一工具」的工序，據實填 `tool_id` + `tool_action` + `action_type`（分桶鍵）+ `adjustable=1`。一組工具生命週期必須是「acquire → (use…) → release」良構配對，否則 LB 會 Fail-Fast（拿了不放、或放了沒拿）。
- **合不合由 LB 的 solver 決定**（是決策變數，權衡省時 vs 集中負載）。MOST 只提供正確的工具標記與分桶鍵，不需要、也不能自己決定要不要合。
- 範例列：
  ```csv
  task_id,action_type,action,duration,predecessors,tool_id,tool_action,adjustable
  2,pick,拿起scanner,1500,1,scanner,acquire,1
  3,scan,scan a,3000,2,scanner,use,0
  5,put,放下scanner,1200,4,scanner,release,1
  7,pick,拿起scanner,1500,6,scanner,acquire,1
  8,scan,scan b,3000,7,scanner,use,0
  10,put,放下scanner,1200,9,scanner,release,1
  ```
  上例 task 2 與 task 7 的 acquire 分桶鍵都是 `("scanner","pick")` 且 DAG 上互不可達，故成為共同 merge 候選。

**重要互斥**：`quantity>1` 的 task **不參與 merge**（ADR-008）；`atomic_group` 成員也不參與 merge（ADR-017）。MOST 不要在同一 task 同時標 tool merge 與這兩者。

### 3.3 沒有「舊式 merge_multiplier」

LB 沒有「同站同 action_type 全部打折」的粗糙 merge，也沒有任何折扣係數欄位。MOST **不需要**、也**不應該**提供任何折扣係數。合併效果完全由 tool closure 機制（§3.2）+ solver 決定。

### 3.4 兩種 Parallel（P1 結構平行 vs P2 人數鎖，ADR-006）

LB 區分兩種「同時作業」，**MOST 要用不同方式表達**：

- **P1（結構平行）**：由 **DAG fork** 自然產生——兩個沒有 predecessor 關係的 task 可被不同 worker 同時做。**MOST 不需要特別標記**，只要 predecessors 正確反映「沒有先後關係」即可。這是「不同工作各做各的」。

- **P2（quantity lot 人數鎖，`p2` 欄）**：**`p2` 不是通用的「多人平行」旗標，而是掛在 quantity lot 上的可選人數鎖**。實況（`engine.py` line 206：`p2=detail.p2 if detail.quantity > 1 else None`；`constraints.py::QuantityLotConstraint`：`model.add(sum(used[w]) == segment.freeze_worker_count)`，其中 `freeze_worker_count = task.p2`）：
  - **只在 `quantity>1` 時生效**。對 `quantity=1` 的 task，`p2` 被 `_to_solver_task` 直接改成 `None`（忽略）。
  - 作用：凍結「這個 quantity lot 剛好由 k 個 worker 分攤」。
    - **不填 `p2`** → solver 自由決定用幾個 worker 分攤這批件數。
    - **填 `p2=k`** → 硬約束剛好 k 個 worker 參與這個 lot 的分攤（`sum(used[w]) == k`）。
  - 約束 `p2 ≥ 2`。
  - 同一 `(group, segment)` 的 `p2` 必須一致（Fail-Fast）。

**MOST 要做的**：
- 一般情況不用管 `p2`——留空即可（P1 由 DAG 自然得到；quantity lot 的人數由 solver 決定）。
- 只有當某個**批量工序（`quantity>1`）**在現場**必須固定用 k 個人分攤**時，才在該 lot 的列標 `p2=k`。
- **不要**把 `p2` 拿來標 `quantity=1` 的 task（會被忽略），也不要拿它表達「不同工作各做各的」（那是 P1，靠 DAG）。

### 3.5 Quantity lot（批量分攤，ADR-008）

**語意**：一個工序要做 `quantity=Q` 件（Q>1）。LB 用決策變數 `units[s,w]` 把這 Q 件分攤給多個 worker（每人做幾件），硬約束 `Σ_w units[w] == Q`（`constraints.py` line 1133）。這是「同一工序做很多件、可分給多人各做一部分」。

**關鍵欄位語意**：
- `quantity`：件數 Q。
- `duration` + `duration_basis`：
  - `duration_basis=once`（**強烈建議**）：`duration` 是**一件**的工時。
  - `duration_basis=lot_total`：`duration` 是**整批 Q 件的總和**。此時 LB 驗 `duration % quantity == 0` 且換算後的一件工時 `≥ 1`，否則 Fail-Fast（`convert_lot_total_durations_to_once`）。
- `qty_scope`（`resolve_qty_scope` + `constraints.py` line 1143–1150）：
  - `cyclic`：每件都要做，某 worker 的工時 = 一件 × 他分到的件數（`size = once × units[w]`）。例：鎖每顆螺絲。
  - `setup`：每個碰到這批的 worker 只做一次，不隨件數放大（`size = once`，只看 `used[w]`）。例：拿起工具。
  - `auto`（預設）：由 `tool_action` 推定——`tool_action ∈ {acquire, release}` → `setup`，否則 → `cyclic`。
- `segment`：見下方「segment 保證程度」。

**Q>1 的硬規則（Fail-Fast，`validate_quantity_contract` + `_validate_group_quantity`）——這些是強制，不是建議**：
- **Q>1 必須有 CSV `group`**（無 group → Fail-Fast `'Q>1 requires a group'`）。
- **Q>1 必須有 `duration_basis`**（缺 → Fail-Fast `'duration_basis is missing; set once or lot_total'`）。
- **Q>1 與 `divisible=1` 互斥**（Fail-Fast）。
- **Q>1 只支援 MULTI_LINE 模式**（非多線 + Q>1 → `QuantityNotSupportedError`）。
- **同一 `group` 的 `quantity` 必須一致、`duration_basis` 必須一致**（Fail-Fast，混值即拒）。
- **同一 `(group, segment)` 的 `p2` 必須一致**（Fail-Fast）。

**segment 的保證程度（最需要講清楚，`quantity_lot.py` + `QuantityLotConstraint`）**：
- segment key = `{group}:{segment}`（**segment 依附 `group`；無 group 時 segment 失效**，因為 key 就湊不出來）。
- 同一 segment 的每個工序**共用同一組 `units[w]` 與 `used[w]` 變數**，且對每個成員工序 `t` 硬約束 `assigned[t_idx, w] == used[w]`。
- 因此 segment **保證**：同一組 worker 參與 + 每人在各工序間分到的件數一致（例：A 在「插」這道分到 3 件 → A 在「鎖」這道也鎖 3 件；而且是 **A 本人**參與這兩道）。
- **但 segment 不保證「工件級對應」**：模型沒有單顆物件的 identity，所以**不保證 A 插的「那幾顆」就是 A 鎖的「那幾顆」**，只保證數量與參與者一致。**MOST 不得對下游承諾 LB 做不到的工件級追蹤保證。**

**MOST 要做的**：
- 批量工序標 `quantity=Q`、`duration_basis=once`、`duration` 填一件工時。
- 分辨每列是 `cyclic`（隨件數）或 `setup`（一次性）；不確定就靠 `auto` + 正確的 `tool_action`。
- 一個 lot 的多工序用**同一個 `group`**（Q>1 強制要 group），要讓多道工序共用同一組分攤向量再加同一個 `segment`。
- **互斥**：`quantity>1` 不可與 `divisible=1`、tool merge、`atomic_group` 併用（見 §3.9）。

### 3.6 General task（通用工序前抽後插）

**語意**：`part_id=General`、**無 predecessors**、`action` 含 take/scan/transport 類動作的 task，會被抽出以「一件時間」插回線頭/線尾，避免通用取放被 lot 放大。

**MOST 要做的**：只有真的是跨零件的通用取放/掃描/搬運才標 `part_id=General` 且不給 predecessor。誤標會讓工時被抽掉、算錯。

### 3.7 Group（不可拆站）

**語意**：同一 `group` 值的 task 必須分到**同一工站**（solver 硬約束：同 group ⇒ 同 station）。約束「空間」——在哪一站。站內誰做、順序、中間插什麼都不管。

**硬規則（Fail-Fast）**：同 group 內 `offline_flag` 一致；若涉及批量，`quantity`/`duration_basis` 一致（§3.5）；組內順序由 predecessor 拓撲決定。

**MOST 要做的**：把「必須同站完成」的一組工序標同一個 `group` 整數。確保該組 offline 一致、批量欄位一致。

### 3.8 Atomic group（不可拆動作，ADR-017）

**語意**：同一 `atomic_group` 值的 task 必須由**同一個 worker 連續完成、且該 worker 在做這組期間不得插入其他工序**（per-worker span 排他）。約束「同一個人時間軸上的連續性」。例：插 HDD 途中不能去鎖別的螺絲，必須做完才做別的。

- 與 `group`（不可拆站）**正交獨立**：可只不可拆站、可只不可拆動作、可兩者、可都不。
- 「同 worker」隱含同站；反之同站不隱含同 worker。
- span 排他允許組內成員間有空檔（只要空檔不塞組外 task），不要求背靠背；只約束該 worker，別的 worker 不受限。
- 恆定硬約束（不是 solver 可選）。

**硬規則（Fail-Fast，ADR-017）**：
- atomic_group 成員 `quantity` 必須 ≤1（與批量分攤衝突：一批件不能既分多人又同一人連續做）。
- atomic_group **不得跨多個不同 `group`**（同 worker 隱含同站，跨兩個不可拆站 group 是矛盾資料）。
- atomic_group 成員 `offline_flag` 必須一致。
- atomic_group 成員不參與 merge。

**MOST 要做的**：把「必須一個人連續做完、中間不能插別的」的一組工序標同一個 `atomic_group` 整數。確保這些成員 quantity≤1、同一個 group（或都不屬 group）、offline 一致、不帶 tool merge。

### 3.9 divisible（可拆分工，R3）

**語意**：`divisible=1` 表示這個 task 可被拆給多人分工（split overlay）。

**硬規則（Fail-Fast，`map_csv_row_to_task_row_dict` + `validate_quantity_contract`）**：
- `divisible=1` 與 `quantity>1` **互斥**。
- `divisible=1` 與 tool `acquire`/`release` **互斥**（取放工具的動作不可拆）。

**MOST 要做的**：只有真的可多人分工的一般工序才標 `divisible=1`，且該列不得同時是批量或工具取放。

---

## 4. 三個「綁定」概念 + p2 差異表（務必看懂）

MOST 最容易混淆的是 `group`、`atomic_group`、`segment`、`p2` 這四個東西。它們管的是**完全不同的維度**，必須分開標：

| 概念 | 管什麼維度 | 綁定內容 | 硬約束 / 生效條件 | 一句話 |
|---|---|---|---|---|
| `group` | **空間（在哪一站）** | 同 group ⇒ 同一 station | 恆定硬約束；同組 offline/quantity/duration_basis 須一致 | 「這幾道必須在同一站做」 |
| `atomic_group` | **同一人的時間連續性** | 同 atomic_group ⇒ 同一 worker 連續完成、期間不插別的工序 | 恆定硬約束；成員 quantity≤1、不得跨多 group、offline 一致、不參與 merge | 「這幾道必須同一個人一氣呵成、中間不能插別的」 |
| `segment` | **批量怎麼拆（分攤向量）** | 同 `(group, segment)` ⇒ 共用同一組 `units[w]`/`used[w]`（同組人 + 每人件數一致） | 只對 Q>1 有意義；依附 group（無 group 則失效）；**不保證工件級對應** | 「這幾道批量工序，是同一批人、每人分到的件數也對齊」 |
| `p2` | **這批用幾個人分攤** | 凍結某 quantity lot 剛好 k 個 worker 分攤（`sum(used[w])==k`） | **只對 Q>1 生效**；`p2≥2`；同 `(group,segment)` 須一致；Q=1 時忽略 | 「這批強制剛好 k 個人分」 |

**為什麼要分開**：一組工序可能「同站」（group）但不必「同人連續」（atomic_group）；可能「批量」（quantity/segment）但不必「鎖人數」（p2）。把它們合成一欄會讓 solver 少了自由度、或承諾了做不到的保證。MOST 只據實標每個維度，其餘交給 solver 決定。

---

## 5. LB 的驗證規則（MOST 產出前的自檢清單）

LB 讀 CSV 時會 Fail-Fast（丟錯、不猜）。MOST 產出前務必逐條自檢：

**DAG / id**
- [ ] `task_id` 唯一、正整數。
- [ ] 每個 predecessor 的 id < 該 task 自己的 id（拓撲遞增編號）。
- [ ] predecessor 指向的 id 都存在。
- [ ] `duration` ≥ 0，整份 CSV 同一時間單位（建議 ms 整數、一件工時）。

**工具 merge**
- [ ] `tool_action` 非空 ⇔ `tool_id` 非空（雙向必填）。
- [ ] `tool_action` ∈ {acquire, use, release}。
- [ ] 每個工具生命週期良構配對（每個 acquire 有唯一 clean release；每個 use 被某 episode 覆蓋）。
- [ ] 要參與 merge 的 acquire 標 `adjustable=1`、非 offline、`quantity≤1`、非 atomic_group 成員，且同工具同 `action_type`（分桶鍵）。

**quantity lot（Q>1）**
- [ ] `quantity` ≥ 1（>1 才觸發下列規則）。
- [ ] Q>1 有 `group`。
- [ ] Q>1 有 `duration_basis`（建議 `once`，`duration` 為一件工時）。
- [ ] Q>1 不與 `divisible=1` 併用。
- [ ] Q>1 只用於 MULTI_LINE 模式。
- [ ] 同一 `group` 的 `quantity`/`duration_basis` 一致。
- [ ] 同一 `(group, segment)` 的 `p2` 一致。
- [ ] `qty_scope`/`duration_basis` 值域正確（`auto|setup|cyclic` / `once|lot_total`）。

**p2（quantity lot 人數鎖）**
- [ ] 只在 `quantity>1` 的列填 `p2`（Q=1 會被忽略）。
- [ ] `p2` ≥ 2。

**group（不可拆站）**
- [ ] 同 group 的 `offline_flag` 一致、批量欄位一致。

**atomic_group（不可拆動作）**
- [ ] 成員 `quantity` ≤ 1。
- [ ] 成員不跨多個不同 `group`。
- [ ] 成員 `offline_flag` 一致。
- [ ] 成員不帶 tool merge。

**divisible / 互斥組合（不可同時出現在同一 task）**
- [ ] `divisible=1` 不可與 `quantity>1` 併用。
- [ ] `divisible=1` 不可與 tool `acquire`/`release` 併用。
- [ ] `quantity>1` 不可與 tool merge、`atomic_group` 併用。
- [ ] `atomic_group` 成員不可與 tool merge 併用。

---

## 6. 最小可用 CSV（MOST 輸出範本）

最精簡（只有必填 + DAG）：
```csv
task_id,action,duration,predecessors
1,取料,1500,
2,組裝外殼,3000,1
3,鎖螺絲,2000,2
4,測試,2500,3
```

含常見功能（General 離線、group 同站、tool merge、atomic_group 不可拆動作）：
```csv
task_id,action,action_type,duration,predecessors,part_id,group,offline_flag,tool_id,tool_action,adjustable,atomic_group
1,備料,take,1200,,General,,1,,,,
2,拿起掃描槍,pick,1500,1,A,10,0,scanner,acquire,1,
3,掃描A面,scan,3000,2,A,10,0,scanner,use,0,
4,放下掃描槍,put,1200,3,A,10,0,scanner,release,1,
5,插HDD,insert,4000,4,A,,0,,,,20
6,鎖HDD螺絲,screw,800,5,A,,0,,,,20
```
上例：
- task 1 是 General 離線備料（`offline_flag=1`，前抽）。
- task 2–4 是 group 10（必須同站）、掃描槍 tool merge 候選（分桶鍵 `("scanner","pick")` 由 task 2 的 `action_type=pick` 決定；`adjustable=1`）。
- task 5–6 是 atomic_group 20（插 HDD + 鎖螺絲必須同一人連續做完），且都 `quantity=1`，符合 atomic_group 成員必須 quantity≤1 的規則。

含批量分攤（quantity lot，需 group；示範 cyclic + p2 人數鎖）：
```csv
task_id,action,action_type,duration,predecessors,group,segment,quantity,qty_scope,duration_basis,p2
1,拿起電批,pick,1500,,30,s1,4,setup,once,2
2,鎖螺絲,screw,800,1,30,s1,4,cyclic,once,2
```
上例：group 30 的 lot 做 4 件（`duration_basis=once`，一件工時）。task 1 是 setup（拿工具，每人只做一次）、task 2 是 cyclic（每件都鎖）。`(group=30, segment=s1)` 共用同一組分攤向量，`p2=2` 鎖定剛好 2 個 worker 分攤這 4 件。**注意**：批量列不可再帶 `atomic_group`、tool merge 或 `divisible=1`（互斥）。

---

## 7. 摘要：MOST 的責任邊界

1. **產生拓撲排序、id 單調遞增的 task CSV**（predecessor id < 自己 id）。
2. **每個 task 的 duration 用一致時間單位、填一件工時**（建議 ms 整數）。
3. **據實標記工具（tool_id/tool_action/action_type/adjustable）**——讓 LB 決定要不要 merge，MOST 不決定合不合。分桶鍵是 `action_type` 不是 `action`。
4. **正確區分 P1（DAG fork，不用標）與 p2（只對批量生效的人數鎖，非通用平行旗標）**。
5. **批量用 quantity（+ group/segment/qty_scope/duration_basis），滿足所有 Q>1 硬規則**；不要用 p2 表達「不同工作各做各的」。
6. **同站需求用 group、不可拆動作用 atomic_group、批量分攤向量用 segment、人數鎖用 p2**，四者管不同維度（見 §4 差異表）。
7. **不要輸出 `eligible_worker_types` / `duration_robot_ms`**——LB 從 CSV 不讀，標了無作用。
8. **遵守所有互斥規則**（§5），否則 LB 會拒絕整份輸入。
9. LB 不猜、不修——資料不合理就 Fail-Fast。MOST 端把資料做對，是整合成功的前提。
