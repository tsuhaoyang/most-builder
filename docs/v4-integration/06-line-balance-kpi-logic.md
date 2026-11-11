# v4 Line Balance 與 KPI 計算邏輯（參考文件，不整合進 v2）

> **定位**：這份文件是**邏輯參考**，不是整合規劃。
> 使用者已有另一套專門的 Line Balance 系統，因此 v4 的 LB／KPI **不會整合進 v2**。
> 本文件的目的是把 v4（`minimost_level/minimost/apps/api`）的 LB 求解演算法與
> KPI／efficiency／balance-rate 等計算方式**如實從程式碼抽出**，供外部 LB 系統對照參考。
> 內容全部實讀程式碼取得，每項附「檔案:行號」證據；本次為唯讀審查，未修改任何程式碼。

## 來源檔案

| 角色 | 檔案 |
|---|---|
| 求解器核心 | `app/services/line_balance.py` |
| API 端點 / KPI 欄位 / scenario 序列化 | `app/api/routes/line_balance.py` |
| KPI 消費（Layout 快照） | `app/api/routes/line_layout.py` |
| KPI 消費（ESOP 產生器） | `app/services/esop_generator.py` |
| CT 來源（Level Plan item） | `app/api/routes/level_system.py` |
| 反推行為的測試 | `tests/test_line_balance.py`（含 40+ 測試） |

演算法版本常數：`ALGORITHM_VERSION = "v2"`（`line_balance.py:36`）。
模式字串固定回傳 `"mode": "dependency_aware"`（`line_balance.py:465`）。

---

## 1. 求解演算法（precedence-constrained packing + beam search）

### 1.1 核心參數

```python
EPS = 1e-6                 # line_balance.py:35
ALGORITHM_VERSION = "v2"   # line_balance.py:36
_BEAM_WIDTH = 12           # line_balance.py:41  每次擺放後存活的部分排程數
_BRANCH_LIMIT = 4          # line_balance.py:42  每個部分排程最多分支的下一步數
```

證據：`line_balance.py:35-42`。註解明言「Small on purpose … keep the solve well
under a second」（`line_balance.py:38-40`）——beam 刻意開很小，因為 ready pool 本來就窄。

### 1.2 前序約束來源（precedence）

前序**只**來自 Level Plan，沒有其他來源（`line_balance.py` module docstring `:6-18`）。三條硬規則：

1. **main 層 N → N+1**：main N 的每個 WI 都排在 main N+1 的每個 WI 之前。
   - 實作：`_main_key(item)`（`:45-51`）把 `item.main_group` 轉成可排序的 main level；
     無法解析者排到最後（`10000 + base`，`:50`）。
   - `_build_graph` 依 `main_key` 建立 `level_of` 與 `chains_per_level`（`:150-176`），
     求解時 `_Partial.level` 只往前推進，較高 main level 的 chain 不會提早進入 ready pool
     （`_ready_heads` 只看 `state.level`，`:227-233`）。
   - 測試佐證：`test_main_precedence`（`test_line_balance.py:113-121`）、
     `test_main_barrier_holds_under_reordering`（`:322-327`）。

2. **main_instance 內部是硬鏈（hard chain）**：同一 `main_instance_id` 內宣告順序不可換
   （例如 C 必在 D 之前）。
   - 實作：`_build_graph` 以 `(main_key, group_id)` 為 key 把 unit 分組成 chain，
     並依 `(order_index, source_sequence_index)` 排序（`:161-172`）。
   - chain 一旦開始就「佔住求解器直到耗盡」：`_place` 設定 `active=cid` 直到 chain 走完
     （`:288`），`_moves` 在 `state.active is not None` 時只允許該 chain 的下一個 unit
     （`:210-212`）。這保證群組 WI 連續、不被兄弟群組打斷。
   - 測試佐證：`test_group_internal_order_respected`（`:139-144`）、
     `test_chain_is_never_inverted_at_any_ct`（`:316-320`）、
     `test_a_group_is_never_interrupted_by_a_sibling_group`（`:434-439`）。

3. **同 main 的不同 main_instance 可互換順序（interchangeable siblings）**：
   兩個 sibling 群組沒有彼此的前序邊，可任一順序、可分左右、CT 夠時可併到同一操作員；
   但**其 WI 永不交錯**（`A1 B1 A2 B2` 非法，`A1 A2 B1 B2` 合法）。
   - 這是「調度自由度」，不是站別邊界。
   - 測試佐證：`test_spec_no_interleaving_example`（`:441-452`）、
     `test_groups_may_still_be_swapped_as_whole_chains`（`:466-477`）。

4. **cub 區塊不可切（non-splittable）**：`is_cub_locked` 且相同 `cub_group` 的連續 item
   合併成單一原子 unit，永不跨站切分。
   - 實作：`build_atomic_units` 把連續同 `cub_group` 的 locked item 收成一個 block
     （`:117-125`），一個 cub block 就是一個 unit，其 `adjusted_ct_seconds` 為區塊加總（`:58`）。
   - 測試佐證：`test_cub_never_split_across_stations`（`:66-82`）、
     `test_cub_block_travels_with_its_chain`（`:479-494`）。

### 1.3 裝箱策略（beam search 主迴圈）

求解器排的是「chain（main_instance 有序鏈）」而不是散裝 WI。ready pool 存 chain heads。

`_solve`（`line_balance.py:378-403`）的步驟：

```
輸入: units（原子單元）, cycle_time, interleave 旗標
1. g = _build_graph(units)                # 排序、分 level、分 chain、算 chain_ct
2. total = 單元總數；若 0 直接回空
3. beam = [ 初始空 _Partial(level=0, ...) ]
4. for _ in range(total):                 # 每輪擺一個 unit
     successors = {}
     for state in beam:
        for (i, close_first) in _moves(state, g, cycle_time, interleave):
            nxt = _place(state, i, close_first, ...)
            key = (pos, active, 已關站數, round(load,3), round(max_closed,3),
                   左鄰站 signature, 開啟站 signature)   # 相同 key = 相同未來
            若 key 未見過或新狀態的 _partial_key 較小 → 保留較佳者
     若無 successors → break
     beam = 依 _partial_key 排序後取前 _BEAM_WIDTH(12) 個
5. best = beam 中 _final_key 最小者
6. 回傳 best 的各站 unit 清單
```

**下一步候選（`_moves`，`:203-249`）**：
- 若有 `active` chain，唯一合法動作是接續該 chain（`:210-212`）。
- 否則取 ready heads（`_ready_heads`，`:227-233`），排序後挑候選：
  - 非 interleave：依 `chain_ct` 由大到小（`:220`，先排大鏈，優先塞重工作）。
  - 前兩名 + 最小 head + 「還塞得下的最大者」（`fitting`，`:239-241`）。
  - 去重後截到 `_BRANCH_LIMIT`（4）個（`:243-247`）。
- 若已有開啟中的 station，額外加入「先開新站再放」的動作（`close_first=True`，前兩個候選，`:250-253`），
  因為「把 chain head 塞進殘餘容量」常不如「開新站」平衡（`:251-252` 註解）。

**擺放（`_place`，`:256-291`）**：
- 若「要求先關站」或「放進去會超過 `cycle_time + EPS`」，先把 open station 封存到 `closed`，
  更新 `max_closed`，開新的空站（`:262-266`）。
- 推進該 chain 指標 `pos[cid] += 1`，遞減該 level 的 `remaining`；
  當目前 level 的 `remaining == 0` 就把 `level` 往前推（`:274-278`）——這實現 main 層屏障。

### 1.4 站數 / 節拍（CT）的決定方式

- **節拍 CT 是輸入，不是求出來的**：`cycle_time_seconds` 由 API 呼叫端提供
  （`SimulateRequest.cycle_time_seconds`，`line_balance.py:37`(route)），
  必須 `> 0`（`_validate_cycle_time`，route `:88-90`）。
- **站數是求解結果**：由裝箱過程決定；一個 unit 若單獨就超過 CT，會**獨佔一站**並標記
  over-CT / bottleneck（module docstring `:34-36`；`test_wi_over_ct_placed_alone_and_marked`
  `:84-92`）。
- **最佳解排序（`_final_key`，`:355-372`）**依序比較：
  1. `over`（各站超過 CT 的秒數總和，越小越好）——「站別撐不住節拍是最糟結果」。
  2. `len(stations)`（操作員數，越少越好）。
  3. `max_ct`（瓶頸站 CT，越小越好）。
  4. `-affinity`（兩側 beat 配對加分，僅用來 tie-break）。
  5. `_flat(state)`（擺放序列，確保**決定性 deterministic**）。
  - 註解點出關鍵關係：總工作固定，`LBR = work / (stations × bottleneck)`，
    所以「最少站數 + 最小瓶頸」即最大化 LBR（`:361-365`）。
- **部分排程排序（`_partial_key`，`:344-353`）**：`round(used×CT − work, 6)`
  （目前為止最少浪費容量），其次已用站數、affinity、`max_closed`、擺放序列。
- 決定性由測試 `test_result_is_deterministic`（`:544-548`）驗證。
- 站數隨 CT 單調不增：`test_station_count_never_increases_with_ct`（`:236-242`）。

### 1.5 group interleaving（進階逃生口）

`simulate(..., allow_group_interleaving=False)`（預設關）。開啟時放棄 main_instance
連續性規則、允許 sibling 群組 WI 混排，可達理論最小站數但輸出可讀性差
（`:406-415`；`_place` 對 `active` 的處理，`:288`）。
測試 `test_interleaving_is_available_as_an_explicit_option`（`:496-514`）顯示：
CT 10、chains A(6,6)+B(4,4) → 預設 3 站（run 為 A,B）；interleave 開 → 2 站（A,B,A,B）。
API 端點**未暴露**此旗標——`simulate` / `simulate-multi` 都用預設值呼叫
（route `:99`、`:120`）。

---

## 2. KPI／計算公式（全部從 `_summarize` 抽出，`line_balance.py:427-490`）

CT 秒數來源請見第 5 節；以下所有 KPI 的「工作內容」都是各 unit 的 `adjusted_ct_seconds`。

### 2.1 每站（station）層級

輸入：`st` = 某站的 unit 清單；`cycle_time` = 節拍。（`:436-467`）

| 欄位 | 公式 | 證據 |
|---|---|---|
| `total_ct_seconds`（站負載） | `round(Σ item.adjusted_ct_seconds, 3)` | `:440` |
| `idle_seconds`（閒置） | `round(max(cycle_time − load, 0.0), 3)` | `:441` |
| `over_ct_seconds`（超 CT） | `round(max(load − cycle_time, 0.0), 3)` | `:442` |
| `utilization`（站利用率） | `round(load / cycle_time, 4)`，`cycle_time>0` 否則 `0.0` | `:443` |
| `is_over_ct` | `over > EPS`（EPS=1e-6） | `:444` |
| `is_bottleneck` | 最大 `load` 的那一站設為 `True`（其餘 False） | `:445-447, 468-469` |

瓶頸判定：迴圈中追蹤 `max_ct` 與 `bottleneck` index，若 `load > max_ct` 則更新
（`:445-447`）；結束後把該站 `is_bottleneck = True`（`:468-469`）。

### 2.2 產線（line）層級

| 欄位 | 公式 | 證據 |
|---|---|---|
| `total_work_content_seconds`（總工作內容） | `round(Σ 所有 unit.adjusted_ct_seconds, 3)` | `:431` |
| `station_count`（站數/操作員數） | `len(out_stations)` | `:471` |
| `max_station_ct_seconds`（瓶頸站 CT） | `round(max_ct, 3)`（= 最大站負載） | `:481` |
| `bottleneck_station_index` | `bottleneck + 1`（1-based）或 `None` | `:482` |
| **`line_balance_rate`（平衡率 %）** | `round(total_work / (station_count × max_ct) × 100, 2)`；分母為 0 時 `0.0` | `:473` |
| `total_idle_seconds` | `round(Σ 各站 idle, 3)` | `:484` |
| **`average_utilization`（平均利用率）** | `round(total_work / (station_count × cycle_time), 4)`；分母為 0 時 `0.0` | `:474` |
| `over_ct_station_count` | 超 CT 的站數 | `:485` |
| `over_ct_seconds` | `round(Σ 各站 over, 3)` | `:486` |

**關鍵區別（`:472` 註解 + 測試 `test_line_balance_rate_uses_bottleneck` `:159-167`）**：
- **平衡率（LBR）用「瓶頸站 CT」`max_ct` 當分母，不是節拍 `cycle_time`。**
- **平均利用率用「節拍 CT」`cycle_time` 當分母。**

  範例（`test_line_balance_rate_uses_bottleneck`）：5×6=30 秒，CT=20，裝成 18+12：
  - `max_station_ct_seconds = 18`
  - `line_balance_rate = 30 / (2×18) × 100 = 83.33`（用瓶頸 18，不是 takt 20）
  - `average_utilization = 30 / (2×20) = 0.75`（用 takt 20）

  另一範例（`test_summary_metrics` `:146-157`）：30 秒、CT=12、3 站，瓶頸 12 →
  `LBR = 30 / (3×12) × 100 = 83.33`。
  完美平衡（`test_independent_groups_may_be_reordered_for_balance` `:329-342`）：
  6+4 / 6+4、CT 10 → idle=0、`line_balance_rate = 100.0`。

> 沒有獨立的「balance loss / balance delay」欄位；loss 可由 `100 − line_balance_rate`
> 推得，但 v4 未直接輸出。「efficiency」在 v4 也沒有單獨命名欄位——最接近的是
> `line_balance_rate`（相對瓶頸）與 `average_utilization`（相對 takt）。

### 2.3 圖表輔助

`chart_data`（`:487-490`）：`cycle_time_seconds` 與 `y_max = round(max(cycle_time, max_ct), 3)`。

### 2.4 警告

`warnings`：若有超 CT 站，加入
`"{over_count} 個工站超過節拍時間（CT {cycle_time}s），已標示為瓶頸／超 CT"`（`:476-478`）。

### 2.5 Sync Group（兩側/同步群組）的節拍計算

在 Layout 層（下游），一個 Sync Group 的節拍取**成員站 CT 的最大值（平行 beat），非加總**：
`sync_group_cycle = round(max(member CTs), 3)`（`esop_generator.py:206-208`）。

---

## 3. 輸入 / 輸出資料形狀

### 3.1 求解吃什麼（輸入）

**Level Plan items**（`LevelSystemPlanItem`）→ `build_atomic_units` 讀取的欄位
（`_make_unit` `:53-101`；測試 `_item` 工廠 `test_line_balance.py:26-42`）：

| 欄位 | 用途 |
|---|---|
| `id` | 追溯 `source_level_plan_item_ids` |
| `sequence_index` / `source_order_index` | 自然順序 / main_key 備援 |
| `adjusted_ct_seconds` | **求解實際使用的工作時間**（見 §5） |
| `ct_seconds_snapshot` | 原始 CT（僅存快照，不參與 KPI 計算） |
| `main_group` | main level（前序 N→N+1） |
| `main_instance_id` / `main_instance_name` | chain 分組（硬鏈） |
| `order_index` | chain 內順序 |
| `cub_group` + `is_cub_locked` | cub 不可切區塊 |

API 入口：`simulate_plan(list(plan.items), cycle_time, allow_group_interleaving=False)`
（route `/simulate` `:99`、`/simulate-multi` `:120`、`/scenarios` `:171`）。

### 3.2 吐什麼（輸出）

`_summarize` 回傳 dict（`:479-490`），station-level 陣列每項含
`station_index / total_ct_seconds / idle_seconds / over_ct_seconds / utilization /
is_over_ct / is_bottleneck / items[]`（`:459-467`）。每個 station item（`_station_item`
`:418-436`）保留 `unit_id / unit_type / is_cub / cub_group_id / source_level_plan_item_ids /
main_instance_id / adjusted_ct_seconds / ct_seconds_snapshot / children[]` 等。

### 3.3 scenario snapshot（存檔）

`POST /most/line-balance/scenarios`（route `:161-206`）存成 `LineBalanceScenario`：
- `summary_json`：`result` 去掉 `stations` 後的 KPI 摘要（`:180`）。
- `stations_json`：完整 station 陣列（`:194`）。
- `source_level_plan_snapshot_json`：`units`（原子單元），使 scenario 自足、
  Level Plan 之後修改也不影響（`:195`；測試 `test_save_scenario_snapshot_stable` `:696-730`）。
- 同時記 `cycle_time_seconds`、`algorithm_version`、`source_level_plan_version_no`。
- simulate / simulate-multi **不自動存檔**（route docstring `:99`、module docstring `:4-6`）。
- 存檔需 `require_analyst_or_admin`；simulate 只需 `get_current_user`（route `:94-97, 164-167`）。

---

## 4. 邊界與規則

- **不可切分的單元**：
  - 單一 WI 永不切分（超 CT 也整顆佔一站，`test_wi_not_split` `:94-104`）。
  - cub block（連續同 `cub_group` 的 locked items）合併成單一原子 unit，永不跨站
    （`build_atomic_units:117-125`；`test_cub_never_split_across_stations`）。
  - main_instance chain 不可被兄弟群組打斷（連續性），但**可作為前綴跨兩站延續**
    （長度超過 CT 時），這算 split 不算 interleave（`test_chain_prefix_may_span_two_stations`
    `:456-464`）。
- **SIMO / 同步群組（Sync Group）**：求解器本身**不處理 SIMO 同時性**；它只做前序約束的裝箱。
  「兩側（two-sided）beat 配對」只在 tie-break 時用 `_beat_bonus`（`:184-204`）加分：
  相鄰兩站同 main、不同 main_instance、各自單一群組時可配對（回傳 1）。
  真正的 Sync Group / 左右 lane 語意在**下游 Layout 層**處理
  （`line_layout.py` 的 `_validate_pair_main_instance` / `sync_group`，
  `esop_generator._layout_context_for_station` `:170-230`），Sync Group 節拍取成員 CT 最大值。
- **頻率（frequency）如何納入**：**求解器沒有 frequency 概念**。找不到 `frequency` 欄位參與
  裝箱或 KPI。工作量的調整改由 `difficulty_factor` 乘進 `adjusted_ct_seconds`（見 §5）。
  （grep `frequency` 在 LB 相關檔案無命中；CT 調整唯一來源是難度係數。）

---

## 5. 與 TMU 的關係（重要：LB 與 MOST engine 的邊界）

**結論：v4 的 Line Balance 只吃 CT 秒數，完全不重算 TMU。** 證據如下：

1. **求解器的工作量全部是 `adjusted_ct_seconds`（秒）**：
   `_build_graph` 的 `ct = [u["adjusted_ct_seconds"] ...]`（`:149`）；
   `_summarize` 的 `total_work` 與各站 `load` 都用 `adjusted_ct_seconds`（`:431, :440`）。
   整個 `line_balance.py` **沒有任何 TMU 計算**（無 `tmu`、無 `0.036`、無 rule-set 讀取）。

2. **`adjusted_ct_seconds` 的來源是「快照 CT × 難度係數」**，不是即時 TMU 計算：
   ```python
   # level_system.py:264-266
   def _recompute_adjusted_ct(item):
       factor = item.difficulty_factor if item.difficulty_factor is not None else 1.0
       item.adjusted_ct_seconds = round((item.ct_seconds_snapshot or 0.0) * factor, 3)
   ```
   而 `ct_seconds_snapshot` 在建 Level Plan 時就從 WI Set item 的
   `total_seconds_snapshot` 凍結下來（`level_system.py:389-407`：
   `ct = wi_item.total_seconds_snapshot`）。TMU→秒的換算發生在**更上游**（WI 引擎），
   LB 只接收既有的秒數快照。

3. **TMU 只在 ESOP 產生器被「反推顯示」，且不回饋 LB**：
   `esop_generator._steps_for_station`（`:250-252`）用
   `tmu = resolved["tmu"] or round(ct / TMU_PER_SECOND, 3)`，其中
   `TMU_PER_SECOND = 0.036`（`esop_generator.py:22`）。這是「若無 TMU 快照就由秒數回算」的
   顯示用途，屬 ESOP 文件生成，不影響 LB 求解或 KPI。

因此對外部 LB 系統而言：**v4 的 LB 邊界就是「秒」**。TMU（1 TMU = 0.036 秒）由 MOST 引擎
負責、在進入 Level Plan 前已換算為 `ct_seconds_snapshot`；LB 端唯一的時間調整是
`difficulty_factor` 這個純量乘數，其餘完全以秒為單位運算。

---

## 附錄：端點清單（`routes/line_balance.py`，prefix `/most/line-balance`）

| 方法 | 路徑 | 說明 | 權限 |
|---|---|---|---|
| POST | `/simulate` | 單一 CT 模擬，不存檔（`:93-101`） | `get_current_user` |
| POST | `/simulate-multi` | 多 CT 模擬（去重、保序），不存檔（`:104-127`） | `get_current_user` |
| GET | `/scenarios` | 列出已存 scenario（可依 plan 過濾）（`:133-145`） | `get_current_user` |
| POST | `/scenarios` | 模擬並存成 scenario（自足快照）（`:148-206`） | `require_analyst_or_admin` |
| GET | `/scenarios/{id}` | 取單一 scenario（含完整 station 快照）（`:209-219`） | `get_current_user` |
| PUT | `/scenarios/{id}` | 改名 / 備註，**不重跑模擬**（`:222-241`） | `require_analyst_or_admin` |
| POST | `/scenarios/{id}/duplicate` | 複製 scenario（含快照）（`:244-273`） | `require_analyst_or_admin` |
| DELETE | `/scenarios/{id}` | 刪除 scenario（`:276-288`） | `require_analyst_or_admin` |
