# LB 投影黃金 fixture

| 檔 | 用途 |
|---|---|
| `server_node_worksheet.json` | 投影層**輸入**：一份 server node 組裝 worksheet 的 24 個 motion（七格 TMU、repeat、frequency、vocab、Level System 標註、LB 標記）。形狀＝`ProjectionRow`（實作書 WP2）。`slot_tmus` 為引擎 `computed.breakdown` 的 7 格值（已含 repeat）。 |
| `server_node_tasks.expected.csv` | 投影層**期望輸出**：34 列 × 24 欄，`\n` 換行、UTF-8 無 BOM。實作必須逐位元相同。 |

## 這份 fixture 證明什麼

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
