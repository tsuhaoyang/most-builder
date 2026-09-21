# LB 投影黃金 fixture

| 檔 | 用途 |
|---|---|
| `server_node_worksheet.json` | 投影層**輸入**：一份 server node 組裝 worksheet 的 24 個 motion（七格 TMU、repeat、frequency、vocab、Level System 標註、LB 標記）。形狀＝`ProjectionRow`（實作書 WP2）。`slot_tmus` 為引擎 `computed.breakdown` 的 7 格值（已含 repeat）。 |
| `server_node_tasks.expected.csv` | 投影層**期望輸出**：34 列 × 24 欄，`\n` 換行、UTF-8 無 BOM。實作必須逐位元相同。 |
| `server_node_hints.expected.json` | 黃金 hints 快照（ADR-035 D10 B4）：`build_report` 對本 golden 產出的 `hints[]`（確定性提示，§7.2）。首次由 agent 產出經 User 過目後鎖定；= 3 條 `H_TOOL_DECOMPOSED`（scanner {4,6}／electric_driver {9}／torque_driver {13,17}）。machine 三列（L2/N2/P2）已回答，故無 `H_MACHINE_TIME`（只在未答時問）。 |
| `writeback_sample.json` | LB 回寫消費（ADR-036）**輸入 fixture**：`lb-most-writeback-v1` payload，34 列（24 個 `source_wi_row_id`），**34 列都有 `qty_scope` 這個 key**（Q=1 的列值為顯式 `null`）。**由 LB 端實跑產生，逐位元複製、不得編輯**（來源 repo `line-balance_stream-weaver_v2`、commit `106bf14`、原路徑 `test/backend/integration/fixtures/most_integration/writeback_sample.json`）。sha256 `c38b03dfb6577ed9c4177a72c5ac95a9f543ebb83dba66d691d65a97f0c0c9b3`、ortools `9.14.6206`。 |

## writeback_sample.json 的產法與 sha256（LB `106bf14` 起已決定性化）

**產法**：LB `scripts/gen_writeback_sample.py`，以黃金複本結果呼叫 writeback 端點。LB 於 `106bf14` 把產生器
決定性化——固定 seed、`SOLVER_NUM_SEARCH_WORKERS=1`（且設在任何 src 模組載入前，config 在 import 期讀 env）、
固定 time limit、凍結 `generated_at`；五次重生一致。

**比對 sha256 時的三個坑（都來自 LB 端的檔頭說明，照抄以免重踩）**：

0. **有一支測試會驗這個 sha**（`tests/unit/test_lb_writeback_service.py::test_vendored_fixture_is_the_pinned_lb_artifact`，
   連同 34 列與 3／2／29 的 `qty_scope` 分布）。它紅了代表有人動過這份檔案——**正確的反應是刻意更新
   README 與該測試的常數，不是重跑產生器把它弄綠**。
1. **檔尾沒有換行**。sha256 是對「寫進檔案的位元組」算的（`write_bytes`，不經 newline 轉譯）——任何
   end-of-file-fixer 補一個 `\n` 就會對不上。本 repo 目前無 pre-commit hook（2026-09-21 確認）。
2. **對不上時頭號嫌疑是 ortools 版本**（LB `requirements.txt` 只寫 `ortools>=9.7.0`）。換一個 CP-SAT build，
   即使單 worker 也可能回一個不同的等價最優解，故產生器會一併印出版本；本版為 `9.14.6206`。
3. **求解從未在 time limit 前跑完**（10／25／60 秒三檔的 wall time 都等於上限）。決定性靠的不是「跑完」，
   而是 incumbent 在前 10 秒內就定下來（三檔同 sha256，安全邊際 ≥6 倍）。真正與機器負載無關的旋鈕是
   CP-SAT 的 `max_deterministic_time`，LB 端目前未接——**這代表決定性是經驗性的，不是結構保證**。

**被取代的版本**：~~sha256 `6a57d0a2…`、來源 commit `aac992f`、分支 `feature/most-integration-phase2`~~
（2026-09-21 取代）。該版尚無 `qty_scope`，且求解未決定性化；其「根因與修正」紀錄留在下一節。

**決定性化的副作用（vendor 時必須一起改測試）**：求解結果本身變了——12 個 task 的 `station_index` 與
`workers` 與舊版不同（黃金三列 task 13/14/15 由 `W-2-0`／station 2 變為 `W-0-0`／station 0）。
`units` 數值未變（1／8／1）。任何釘住 worker id 或站號的斷言都要跟著更新。

## writeback_sample.json 情境覆蓋（34 列，24 個 source_wi_row_id）

- 頂層 `unattended_machine_policy=free`／`_source=persisted`。
- **general 列已回寫**（seq1 take_unit，單站）。**根因與修正（歷史）**：`84f9689` 版（33 列）不含 general 列——
  LB 的 general 為求解後插回、取得新 task id，但 `source_wi_row_id` 在插回鏈遺失，導致回寫略過；
  LB `aac992f`（保留 re-inserted general 的 `source_wi_row_id`，ADR-023 D8/D11）修正後重生。
- **`qty_scope` 覆蓋**（`106bf14` 起）：3 列 `cyclic`、2 列 `setup`、29 列 **顯式 `null`**。
  注意措辭：這份 fixture 是 **34 列都有這個 key**、Q=1 的列值為 `null`——不是「不輸出該欄」。
  MOST 的 parser 對「缺欄」與「顯式 null」一視同仁（都是 `None` → 走推算退路），兩種都要有測試覆蓋。
  黃金三列（task 13/14/15，electric_driver repeat 8）為 `setup`／`cyclic`／`setup`，units 1／8／1
  → 件數取 cyclic 列＝**8**（確定值，`units_source="cyclic"`）。
- 工具 episode 三列（acquire/use/release，同站同 worker）：5 組 `source_wi_row_id` 各 3 列。
- offline 列（`line_index`/`station_index=null`、`workers=[]`）。
- Q>1 `units` 列（`[{worker, units}]`）。
- 本版 general 為 take_unit 型、**單站**；general 多站不標 cross_station（ADR-036 D6）由合成資料測試覆蓋。


## 這份 fixture 證明什麼

- WI-I 的重複區塊 R={M,X,I}（三格同步 ×8），所以「逐格除」與舊的「Σ/N」結果相同；部分 repeat 的案例不在本 golden，見 `tests/unit/test_lb_projection_tmu.py`。
- 兩個乘數同時存在且投影形狀不同：WI-G/H 用 `frequency=8`（→ 1 列 Q=8 cyclic），WI-I 用 slot `repeat_count=8`（→ 3 列 setup／cyclic／setup）。
- Pattern B 持工具 motion 拆三列 ×5（scanner ×2、electric_driver、torque_driver ×2）。
- 分層 DAG：L1={B(offline), C}，L2 六個平行入口（D、sub2、cub40、sub3、cub10、cub11），L3={O}，L4=sub5；巢狀 cub30 ⊂ sub2 以 seq_no 定位在 F 之後。
- 標記全覆蓋：general（A，`general_role=take_unit`）、offline（B）、cub only（10）、wcub only（20）、cub+wcub（11/21）、segment（dimm/screw）、station_pin（6）、merge_lock（K/M）、splittable（O）、role machine（L2/N2/P2）。
- TMU 守恆：Σ MOST eff = 2 603.445 TMU = 93 724 ms = Σ LB（一人做）。
- LB 端實跑通過（2026-09-11，LB @ 8ed7911）：reader、`validate_quantity_contract`、`GroupValidator`、`is_general_candidate`（task 1 → TRANSPORT）、`detect_merge_candidates`（恰 1 組：scanner acquire 4/8、release 6/10；torque_driver 因 `adjustable=0` 排除；electric_driver 因 Q>1 排除）。

## 怎麼用

```python
fx = json.load(open("docs/lb-integration/fixtures/server_node_worksheet.json"))
rows = [ProjectionRow.model_validate(r) for r in fx["rows"]]
csv_text, report = project_to_lb_csv(rows, vocab=fx["vocab"], rs=build_from_seed_v2())
assert csv_text == open("docs/lb-integration/fixtures/server_node_tasks.expected.csv", encoding="utf-8").read()
```

`slot_tmus` 在 fixture 內為靜態值；WP3 的引擎重算需要 `slot_inputs`——golden test 以 fixture 的 `slot_tmus`＋`repeat_counts` 走「靜態路徑」（`TmuDecomposer.from_breakdown`），另有 `test_lb_projection_engine_path.py` 用真 `slot_inputs` 走引擎路徑並斷言兩路徑相等。

## 修改守則

- 改 fixture ＝ 改契約：任何欄值變動需同時更新 Spec §9 的數字，並重跑 LB 端驗證（`scripts/lb_projection_check.py --lb-repo <path>`，見實作書 WP10）。
- 不得為了讓測試變綠而改 expected CSV；先問「Spec 哪一條說應該這樣」。

## 變更紀錄
- 2026-09-12：每個 motion 的 `lb_tags` 新增 `action_type`（IE 標籤；Spec §6 優先序 ③）。expected CSV 不變。由 WP6 實作發現附錄 A 無法從結構碼推出 remove／test 等語意，架構師裁決標籤優先。
- 2026-09-12：修正 task 31 的 `predecessors`（移除傳遞冗餘邊 10→31；sub2 是單一 chain E→F→G→H，sink 為 12，Spec §5.5 要求傳遞縮減）。由 WP5 實作發現，架構師核可。LB 端驗證重跑通過。

- L2（seq 15）／P2（seq 23）`lb_tags.machine_unattended: true`、N2（seq 19）`false`（ADR-035 D10 §3.4；`role_type=machine` 需 CM∧x≥1∧unattended==true）。expected CSV 僅 task 29 role_type=human；hints 快照 = 3 條 H_TOOL_DECOMPOSED（machine 三列已回答）。
