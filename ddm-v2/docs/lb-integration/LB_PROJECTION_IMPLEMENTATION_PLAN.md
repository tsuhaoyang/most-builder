# LB 投影層修正實作書（MOST 端，implements ADR-035）

> **給誰**：執行 MOST（ddm-v2）修正的 agent／開發者。
> **最高原則**：[`MOST_LB_DATA_CONTRACT_SPEC.md`](MOST_LB_DATA_CONTRACT_SPEC.md)（以下簡稱 **Spec**）。本書只說「改哪裡、怎麼改、怎麼驗」；**語意一律以 Spec 為準，本書與 Spec 衝突時以 Spec 為準並回修本書**。
> **邊界**：[ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md)。ADR 未涵蓋的設計問題 → 停下問 User，不自行擴張。
> **驗收物**：[`fixtures/`](fixtures/README.md)（golden 逐位元相等）。
> **狀態**：v1.0（2026-09-11）。WP 完成後在本書 §3 的表格打勾並附 commit。

---

## 0. 範圍、不做、完成定義

**做**：後端投影層（新 package）、`level_entries` 六個 LB 標記欄、匯出端點重寫、匯出前驗證與報告、NL compiler 乘數目的地、測試、文件同步、Level System UI 的標記層。
**不做**：LB 端任何修改（Phase 2 另案）；SIMO 輸出（等 LB 加欄）；nb 輸出；WI 層 `wi_group` 欄；D13 回寫；改 TMU 計算（引擎不動）。
**完成定義（DoD）**：
1. `PYTHONPATH=src pytest tests/unit -q` 全綠，且新增測試覆蓋 Spec §8.1 **每一個** E／W 碼至少一個反例。
2. golden：`fixtures/server_node_worksheet.json` → 與 `server_node_tasks.expected.csv` **逐位元相等**。
3. 表頭凍結測試存在且鎖住 24 欄。
4. `scripts/lb_projection_check.py` 對 golden 輸出跑 LB 端驗證通過（LB repo 可用時）。
5. `ruff check` 乾淨；`mypy`（若專案已啟用）不新增錯誤；前端 `npm run typecheck && npm run build` 通過。
6. §5 文件同步全部落地；`MOST_LB_CONTRACT.md` D18 指回 Spec。
7. 每個 commit message 含 `implements ADR-035: WPn …`。

---

## 1. 目標架構

```
src/ddm_v2/lb_projection/
├── __init__.py          # public: project_worksheet(), project_rows(), COLUMNS, CONTRACT_VERSION
├── errors.py            # ProjectionError(code, wi_row_id, message) + E_*/W_* 常數（Spec §8.1 全表）
├── models.py            # ProjectionRow / ProjectionVocab / LbTask / ExportReport（pydantic v2）
├── adapter.py           # read_worksheet() dict + vocab 查表 → list[ProjectionRow]；load_fixture(path)
├── tmu.py               # TmuDecomposer：from_breakdown(static) / from_engine(slot_inputs, rs)
├── tools.py             # ToolLifecycleResolver：chain 內事件與 held 狀態機（Spec §4）
├── precedence.py        # PrecedenceProjector：層範圍、chain、傳遞縮減、Kahn 編號（Spec §5）
├── quantity.py          # QuantityProjector：乘數矩陣（Spec §3.2）
├── mappers.py           # group/atomic/offline/station/general/action_type/duration_ms
├── validator.py         # CsvContractValidator：Spec §7 不變量 + §8.1 碼 → (errors, warnings)
├── emit.py              # RowEmitter：LbTask → 24 欄 dict；write_csv()（\n、UTF-8、無 BOM）
└── project.py           # 編排：adapter → level.validate gate → tools → quantity → precedence → validator → emit → report
```

資料流（不可重排）：
`read_worksheet` → **adapter** → `level.validate()`（E_LEVEL_INVALID）→ **tools**（每 motion 產 1–3 個 `LbTask` 雛形＋內部鏈）→ **quantity**（Q／scope／duration）→ **precedence**（層邊＋編號）→ **validator**（E 擋／W 報）→ **emit**（CSV＋report）。

投影層**不 import** SQLAlchemy／FastAPI；唯一外部相依是 `most_engine`（TMU 重算）與 `most_engine.level.validate`。

---

## 2. 工作包（WP）

每個 WP：目標／改動檔案／介面／規則出處／驗收。**順序見 §3。**

### WP0 骨架與表頭凍結
- 新建 `src/ddm_v2/lb_projection/` 上述檔案（可先空實作）。
- `emit.py`：
  ```python
  CONTRACT_VERSION = "most-lb-csv-v1.1"   # Spec §0 標題為版本權威；報告 §8.2 同字串
  COLUMNS: tuple[str, ...] = ("task_id","action","part_id","group","atomic_group","duration","predecessors",
      "station_name","action_type","complexity_level","adjustable","fixed_station","offline_flag","tool_id",
      "tool_action","divisible","p2","quantity","segment","qty_scope","duration_basis","source_wi_row_id","role_type","general_role")
  ```
- 測試 `tests/unit/test_lb_projection_contract_freeze.py`：`COLUMNS` 與上列**逐字相等**；`server_node_tasks.expected.csv` 第一行 == `",".join(COLUMNS)`。任何人動表頭必先改這個測試＝升版（Spec §10）。
- 出處：Spec §6、§10。

### WP1 資料模型：`level_entries` 八個 LB 標記欄
- **migration** `migrations/versions_v2/v2_0046_level_entries_lb_tags.py`（`down_revision="v2_0045"`）：
  ```python
  op.add_column("level_entries", sa.Column("worker_cub", sa.Text(), nullable=True))
  op.add_column("level_entries", sa.Column("offline", sa.Boolean(), nullable=False, server_default=sa.text("false")))
  op.add_column("level_entries", sa.Column("segment", sa.Text(), nullable=True))
  op.add_column("level_entries", sa.Column("station_pin", sa.Integer(), nullable=True))
  op.add_column("level_entries", sa.Column("is_general", sa.Boolean(), nullable=False, server_default=sa.text("false")))
  op.add_column("level_entries", sa.Column("general_role", sa.Text(), nullable=True))
  op.create_check_constraint("general_role_enum", "level_entries", "general_role IS NULL OR general_role IN ('take_unit','scanner','transport')")
  op.add_column("level_entries", sa.Column("merge_lock", sa.Boolean(), nullable=False, server_default=sa.text("false")))
  op.add_column("level_entries", sa.Column("action_type", sa.Text(), nullable=True))   # IE 選填顯示標籤（Spec §6 優先序 ③）
  op.create_check_constraint("worker_cub_format", "level_entries", "worker_cub IS NULL OR worker_cub ~ '^wcub[0-9]+$'")
  op.create_check_constraint("station_pin_pos", "level_entries", "station_pin IS NULL OR station_pin >= 1")
  ```
  downgrade 對稱。`machine_count`／`manpower` **不動**（ADR-035 D7；待 User 裁決 4）。
- `src/ddm_v2/models/v2/worksheet.py::LevelEntry` 加對應 `mapped_column`（命名與 CheckConstraint 短名慣例同檔案註解：`ck_level_entries_*` 由 naming_convention 加前綴）。
- `src/ddm_v2/schemas/v2/worksheet.py::LevelFieldsIn` 加：`worker_cub: str | None = None`（pattern `^wcub\d+$`）、`offline: bool = False`、`segment: str | None = None`、`station_pin: int | None = Field(default=None, ge=1)`、`is_general: bool = False`、`general_role: Literal['take_unit','scanner','transport'] | None = None`、`merge_lock: bool = False`、`action_type: str | None = Field(default=None, max_length=32, pattern=r'^[a-z][a-z_]*$')`。
- `services/v2/worksheet_service.py`：`save_worksheet` 的 `LevelEntry(...)` 建構（約 L211）帶入六欄；`read_worksheet` 的 `"level": {...}`（約 L280）輸出六欄。`clone_worksheet` 若逐欄複製 LevelEntry，補六欄。
- 前端型別：依 `src/frontend/package.json` 既有 OpenAPI 型別產生腳本重生 `src/frontend/src/shared/types/api.d.ts`（**不手改**）。
- 資料模型文件同步：見 §5。
- 驗收：`tests/integration/test_worksheet_lb_tags_roundtrip.py`（需 DB；save → read 六欄原樣）；無 DB 環境 skip。
- 出處：ADR-035 D7；Spec §1 tool-held／§6。

### WP2 `ProjectionRow` 與 adapter
- `models.py`：
  ```python
  class ProjectionVocab(BaseModel): kind: Literal["object","component","tool","from","to","hand"]; name_en: str | None
  class ProjectionCycle(BaseModel):
      seq_kind: Literal["GM","CM"]; slot_tmus: list[float]  # len 7, 已含 repeat
      repeat_counts: dict[str, int] = {}   # {"3": 8, "4": 8, "5": 8}（slot index 字串）
      x_seconds: float = 0; total_tmu: float; tech_line: str | None; narrative_en: str | None; narrative_zh: str | None
      slot_inputs: dict | None = None      # 引擎路徑用；fixture 可缺
      rule_set_code: str | None = None
  class ProjectionLevel(BaseModel): ascription, level, countersignature, parent_countersignature, order, number, number_count
  class ProjectionTags(BaseModel): action_type: str|None=None; is_general=False; general_role: Literal['take_unit','scanner','transport']|None=None; offline=False; worker_cub: str|None=None; segment: str|None=None;
      station_pin: int|None=None; merge_lock=False; splittable=False
  class ProjectionRow(BaseModel):
      wi_row_id: str; seq_no: int; sub_activity: str|None; key_parts: str|None; hand: str|None
      object_vocab: str|None; tool_vocab: str|None    # vocab key（fixture）或 vocab_id（DB）
      frequency: float; simo_group_id: str|None; cycle: ProjectionCycle; level: ProjectionLevel; lb_tags: ProjectionTags
  ```
  `splittable` 目前**無 DB 欄**（Phase 2 若要 UI 標記再加欄；v1 由 fixture／API 帶入，DB 路徑恆 False）。
- `adapter.py`：
  - `rows_from_worksheet(data: dict, vocab: dict[str, ProjectionVocab]) -> list[ProjectionRow]`：`data` 為 `read_worksheet()` 回傳；`cycle.slot_tmus` 取 `cycle.computed.breakdown[].tmu`（需 `read_worksheet` 補輸出 `computed`——目前只輸出 `tech_line`；**加法擴充**：在 `"cycle"` dict 加 `"breakdown": (cyc.computed or {}).get("breakdown")`）；`repeat_counts` 從 `slot_inputs` 的 `g2/p5/m3/x4/i5.repeat_count` 取；`x_seconds` 從 `slot_inputs.x4.x_seconds`。
  - `load_vocab(session, ids) -> dict[str, ProjectionVocab]`（唯一會碰 DB 的函式，放在 `services/v2/export_service.py` 而**不是**投影層；adapter 只吃 dict）。
  - `load_fixture(path) -> tuple[list[ProjectionRow], dict[str, ProjectionVocab], dict]`。
- 驗收：`test_lb_projection_adapter.py`：fixture 24 列全數 validate；`read_worksheet` 假資料 → ProjectionRow 對齊。

### WP3 TmuDecomposer（Spec §3.3）
- `tmu.py`：
  ```python
  @dataclass(frozen=True)
  class Decomposed: setup_pre_tmu: float; use_once_tmu: float; setup_post_tmu: float; n: int; total_tmu: float; block: tuple[int, ...]
  def repeat_block(cycle) -> tuple[int, ...]   # Spec §3.3：use 段非零格中 repeat>1 的連續區塊 R；值不一致 → E_REPEAT_MIXED；不連續 → E_REPEAT_NONCONTIGUOUS；slot 0–2 有 repeat → E_TOOL_ACQUIRE_REPEAT
  def decompose_static(cycle: ProjectionCycle) -> Decomposed      # fixture 路徑：use_once = Σ_{s∈R} slot_tmus[s]/n（逐格）；pre/post 依 §3.3 分桶
  def decompose_engine(cycle: ProjectionCycle, rs: RuleSetData) -> Decomposed   # 權威路徑：compute_cycle(strip_repeats(slot_inputs, slots=R))
  ```
  - 兩路徑皆斷言 `setup_pre + n*use_once + setup_post == total_tmu`（|Δ|≤1e-6）否則 `E_TMU_DECOMPOSITION`；M 格含 `hand/foot` 伴隨分量且 n>1 → `E_REPEAT_NONLINEAR`（判法：`slot_inputs.m3.m_components` 任一 `angle_deg>0 or foot…`——以引擎 `M_COMPANION_KINDS` 為準）。
  - `project.py` 有 `slot_inputs` 時**必走** `decompose_engine`；靜態路徑僅 fixture／無 slot_inputs。
- 驗收：`test_lb_projection_tmu.py`：WI-I（190 = 22 + 8×19 + 16，R={M,X,I}）、WI-D（48 = 16+22+10）、**部分 repeat**（M 一次＋X×8、I×8：M 進 `setup_pre`，守恆成立）、**夾心**（M×8、X 一次、I×8 → `E_REPEAT_NONCONTIGUOUS`）、`E_REPEAT_MIXED`、`E_TOOL_ACQUIRE_REPEAT`、`E_REPEAT_NONLINEAR`；`test_lb_projection_engine_path.py`：以真 `slot_inputs` 走 `build_from_seed_v2()` 引擎，兩路徑結果相等。

### WP4 ToolLifecycleResolver（Spec §4）
- `tools.py`：
  ```python
  class ToolEvent(Enum): ACQUIRE, IMPLICIT_ACQUIRE, USE, RELEASE, NONE
  def resolve_chain(chain: list[ProjectionRow], vocab) -> list[MotionPlan]
  # MotionPlan: row, parts: list[Literal["acquire","use","release"]] (長度 1／2／3), tool_id, tool_vocab_key, action_types, adjustable_flags
  def tool_id_of(vocab: ProjectionVocab, key: str) -> tuple[str, list[Warning]]   # name_en → snake_case；缺 → tool_<key[:8]> + W_TOOL_NAME_EN_MISSING
  ```
  - 事件判定表 Spec §4.1；release 落點向後看 §4.3；**2 列且 N>1 時 `setup_post` 併入 acquire 列，N=1 併入 use 列**（§4.3 修正）；chain 結束 held 非空 → `E_TOOL_NOT_RELEASED`；跨 chain → `E_TOOL_CROSS_CHAIN`（由 project.py 在所有 chain 跑完後比對 held 集合）。
  - general motion：不進 resolver；有工具 → `W_GENERAL_WITH_TOOL`。
- 驗收：`test_lb_projection_tools.py`：Pattern B 3 列（D）、Pattern B 2 列（CM 後接 GM 放下）、Pattern A 3 motion → 3 列（acquire/use/release 各一）、`E_TOOL_NOT_RELEASED`、`E_TOOL_CROSS_CHAIN`、`E_TOOL_TWO_TOOLS`、`merge_lock` → adjustable 0、預設 1。

### WP5 PrecedenceProjector（Spec §5）
- `precedence.py`：
  ```python
  def build_chains(rows) -> list[Chain]            # Chain: top_level item; items: ordered [MotionRef|NestedBlock]; lo, hi
  def layer_edges(chains) -> list[tuple[ChainRef, ChainRef]]   # hi_Y < lo_X 偏序的傳遞縮減
  def assign_task_ids(nodes, edges) -> dict[NodeKey, int]        # Kahn，heap key=(seq_no, part_index)
  ```
  - 先呼叫 `most_engine.level.validate(rows→LevelRow)`；有 issue → `E_LEVEL_INVALID`（message 帶原 code 列表）。
  - `a/b` → `E_LEVEL_DISCRETE_UNSUPPORTED`；nb → `W_NB_UNSUPPORTED`；浮動 → `W_FLOATING_TASK`；general／SIMO 從屬排除。
  - 巢狀區塊位置：成員最小 `seq_no`（ADR-035 D6）。
- 驗收：`test_lb_projection_precedence.py`：golden 的 42 條邊逐條斷言（L2 六個 source 皆 ← {2,3}；`31 ← {6,12,15,21,27,30}`——sub2 是單一 chain E→F→G→H，sink 是 12，10→31 為傳遞冗餘（§5.5）；chain 邊）；`1~2` 有界平行案例；`a/b` 拒收；巢狀 cub 在 seq_no 位置；編號 tie-break（兩個同層 standalone 依 seq_no）。

### WP6 QuantityProjector、mappers、RowEmitter
- `quantity.py`：`plan_quantity(row, plan: MotionPlan, dec: Decomposed) -> QuantityPlan`（Spec §3.2 矩陣逐格；acquire／use／release 列的 `duration` 分別取 `dec.setup_pre_tmu`／`use_once_tmu`／`setup_post_tmu`；含 `W_TOOL_FREQ_ALL_CYCLIC`、`W_FRACTIONAL_FREQUENCY_BAKED`、`E_TOOL_FREQ_AND_REPEAT`、`E_TOOL_FRACTIONAL_FREQUENCY`）。
- `mappers.py`：
  - `group_id(row, plan) -> int | None`：`cub\d+` → 數字；Q>1 無 cub → `9000 + seq_no` ＋ `W_AUTO_GROUP_FOR_LOT`；tool-held 三列同值。
  - `atomic_id(row) -> int | None`：`wcub\d+` → 數字。
  - `duration_ms(tmu) -> int`：`Decimal(str(tmu)) * 36` 以 `ROUND_HALF_UP` 取整。
  - `action_type(...)`：Spec §6 優先序（acquire/release 恆 pick/put → general 依 role → `lb_tags.action_type` → 附錄 A（需 `slot_inputs` 選項碼）→ `op`＋`W_ACTION_TYPE_FALLBACK`）。附錄 A 路徑用真 `slot_inputs` 的單元測試另寫（`test_lb_projection_action_type_fallback.py`），golden 走標籤路徑。
  - `role_type(row)`：`x_seconds >= 1` → `machine`。
  - `part_id(row)`：general → `"General"`。
- `emit.py`：`to_row(task: LbTask) -> dict[str,str]`（空值→`""`；bool→`0/1`；預設 `quantity=1`）；`write_csv(rows) -> str`（`csv.DictWriter`, `lineterminator="\n"`, `fieldnames=COLUMNS`）。
- `project.py`：`project_rows(rows, vocab, rs=None) -> ProjectionResult(csv_text, report, tasks)`；`project_worksheet(session, ws_id)`（在 export_service 內組裝 rs 與 vocab 後呼叫 `project_rows`）。
- 驗收：**golden** `test_lb_projection_golden.py`：`csv_text == expected` 逐位元；report 的 `tmu_total_most`、`ms_total_lb_one_worker`、groups、atomic_groups、tool_episodes 與 fixtures/README 數字一致。

### WP7 CsvContractValidator 與 ExportReport
- `validator.py`：`validate(tasks, rows, plans) -> tuple[list[ProjectionError], list[ProjectionError]]`，逐條實作 Spec §7 不變量與 §8.1 表（E 與 W 分列）。**不變量 1（TMU 守恆）在 TMU 域比對**。
- `ExportReport`（Spec §8.2）由 `project.py` 組裝。
- 驗收：`test_lb_projection_validator.py`：Spec §8.1 **每個碼**至少一個最小反例 fixture（放 `tests/unit/fixtures/lb_projection/*.json`，形狀同 golden 的 `rows[]` 子集）。

### WP8 匯出端點與 LB API payload
- `services/v2/export_service.py`：
  - `to_lb_csv(session, ws_id) -> str` 改為呼叫 `project_worksheet`；**移除** `machine_count`／`manpower` 與所有 Level dump 欄（D16）。有 E 碼 → raise `LbExportBlocked(errors, warnings)`（新例外，繼承 `ddm_v2.exceptions.ValidationError`，`detail={"code": ErrorCode.LB_EXPORT_BLOCKED, "errors":[...], "warnings":[...]}`；在 `errors/registry.py` 新增 `LB_EXPORT_BLOCKED`；ADR-034 D1 信封）。
  - 新增 `lb_export_report(session, ws_id) -> dict`（不擋，永遠回報告，含 E 與 W）。
  - `lb_api_payload`：`payload` 改為 `{"contract_version", "csv": csv_text, "tasks": [...dict...], "report": {...}}`；保留 `status:"interface-ready"` 語意；**移除** `build_output` 直送（保守邊不可沿用）。
  - 需要 `load_vocab`（kinds/name_en）與 `rs`（`load_rule_set_from_db` by 該 worksheet 各列的 `rule_set_id`；同 worksheet 多版本時逐列取）。
- `api/routes/v2/export.py`：`/export/lb-csv` 回 CSV（BOM 維持）；新增 `GET /worksheets/{id}/export/lb-report`；`LbExportBlocked` 由 error handler 轉 422 信封（依 ADR-034 現有 `register_exception_handlers` 路徑）。
- 驗收：`tests/integration/test_export_lb_csv.py`（DB）：seed 一份含工具 CM 與 cub 的 worksheet → CSV 表頭 == COLUMNS、含三列 scanner episode；缺 `narrative_en` 時 422 且 `error.code == "LB_EXPORT_BLOCKED"`；`lb-report` 200 帶 warnings。無 DB skip。

### WP9 NL compiler：QuantityPolicyV2（ADR-035 D4）
- `most_compiler/policies.py`：新增
  ```python
  def resolve_multiplier(action, plan) -> tuple[float, int | None, list[str]]:
      """回 (frequency, repeat_count, reasons)。持工具(is_tool_held) 且 N 為整數>1 → (1.0, N, reasons+['repeat_policy_v2'])；否則沿用 resolve_frequency。"""
  ```
  `resolve_frequency` **保留**（相容、ADR-033 註明不刪），改由 `resolve_multiplier` 呼叫。
- `most_compiler/compile.py`：CM 分支把 `repeat_count` 寫進 `m3`（若有分量）、`x4`（若 x_code 或 x_seconds）、`i5`（若 i_code）；GM 分支寫進 `p5`（持工具 GM 罕見，允許）。`StrictMSlot/StrictXSlot/StrictISlot/StrictPSlot`（`intermediate.py`）加 `repeat_count: int | None = None`（Strict 模型 `extra="forbid"` 需顯式加欄）。
- 測試 `tests/unit/test_compiler.py`：`test_unevidenced_quantity_flagged_but_frequency_unchanged`（L524）等三處 `cycle["frequency"] == N` 斷言：**若該 action 為持工具**改斷言 `repeat_count`；非持工具維持。新增 `test_tool_held_quantity_goes_to_repeat_count`（gold g02：a2 process quantity=2 + tool_held_for → `x4.repeat_count==2`、`frequency==1.0`，且 `compute_cycle` TMU 與改前相等——TMU 中性斷言）。
- gold：`tests/gold/wi_plans/*.json` 的 `expected_cycles` 若含 `frequency` 於持工具 action → 依新政策更新（僅形狀，TMU 不變）；跑 `test_gold_plans.py`。
- 文件：`docs/llm/wi-ai-parser-implementation-spec.md` §9.2 追記（見 §5）。
- 出處：ADR-035 D4；Spec §3。

### WP10 測試總表與跨 repo 檢查
- 單元（無 DB，`@pytest.mark.unit`）：WP0/2/3/4/5/6/7/9 各自檔案；`test_lb_projection_golden.py` 為總驗收。
- 補充 fixture（`tests/unit/fixtures/lb_projection/`）：`pattern_a_three_motions.json`、`pattern_b_two_rows.json`、`simo_skip.json`、`bounded_parallel_1to2.json`、每個 E／W 碼一檔。
- `scripts/lb_projection_check.py`：
  ```
  usage: lb_projection_check.py --csv <path> [--lb-repo /home/howard/workspace/line-balance_stream-weaver_v2]
  ```
  以 `<lb-repo>/test/.venv/bin/python` 執行內嵌腳本（`PYTHONPATH=src`）：`read_problem_from_csv` → `validate_quantity_contract(mode="MULTI_LINE")` → `GroupValidator.validate/validate_atomic_groups` → `is_general_candidate` → `_to_solver_task` → `detect_merge_candidates`；印 groups／atomic／merge 候選（以 `Task.id` 列出）；exit 非 0 即失敗。LB repo 不存在 → 印 SKIP、exit 0。CI 不強制（跨 repo）。
- `scripts/core_logic/README.md` 加一列指向。

### WP11 文件同步（見 §5 逐條文字）

### WP12 Level System UI：LB 標記層（ADR-035 D10；設計為建議，實作時可調，變動回寫 ADR D10）
- `features/level-system/logic.ts`：`LevelCell` 加 `workerCub, offline, segment, stationPin, isGeneral, mergeLock`；`derive()` 輸出對應 `LevelPayloadRow` 欄（命名對齊 `LevelFieldsIn`）。
- `store.ts`：`createGroup('wcub', ...)`（獨立於 countersignature 的第二個群組維度：`workerCubMeta`）、`toggleOffline(rowId)`（同 cub／wcub 傳染＋確認）、`setSegment`、`setStationPin`、`toggleGeneral`、`toggleMergeLock`；設 wcub 時成員 `frequency>1` 或 tool-held → 擋並提示。
- `LevelSystem.tsx`：群組盒新增 👤 紫（wcub）；列級工具列：⏸ offline、📍 pin、G general、🔧🔒 merge_lock；Q>1 列顯示 segment chip 編輯；**投影預覽 badge**（呼叫新端點 `GET .../export/lb-report` 的 `tasks`／`warnings`，顯示 1／2／3 列、Q、setup/cyclic、tool_id）。
- 匯出面板：顯示 report；有 E 碼時匯出按鈕 disabled 並列出修法提示（Spec §8.1 第三欄）。
- i18n：`zh-TW.ts`／`en.ts` `levelSystem.*` 新 key（`createWcub`、`offline`、`segment`、`stationPin`、`general`、`mergeLock`、`preview.*`、`export.blocked`）。
- E2E（Playwright）：圈 wcub → 切 offline → 整組傳染 → 匯出 report 有 `W_*`；含工具 motion 的 wcub → 即時擋。
- 出處：ADR-035 D10；Spec §6、§8。
- **後續：作業版（使用者語言）UI 見 [`LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`](LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md)**（ADR-035 D10 修訂：WP12 的 IE 詞彙檢視改為「進階檢視」，另加作業版兩層視圖、同一 store；已落地 `08f59e7`..`49d02c1`）。

---

## 3. 執行順序與關卡

| 序 | WP | 前置 | 關卡（過了才進下一個） | 完成（commit） |
|---|---|---|---|---|
| 1 | WP0 | — | 表頭凍結測試綠 | ✅ `d194868` |
| 2 | WP2 | WP0 | fixture 24 列 validate；adapter 測試綠 | ✅ `081e570` |
| 3 | WP3 | WP2 | tmu 測試綠；engine path 與 static 相等 | ✅ `8e35a5d`→`e475ab7`（分桶重做） |
| 4 | WP4 | WP2 | tools 測試綠（含 Pattern A／B／2 列） | ✅ `19e3e58` |
| 5 | WP5 | WP2 | precedence 測試綠（golden **42** 邊，見下註） | ✅ `d91d339`→`247dcca`（裁決 A） |
| 6 | WP6 | WP3–5 | **golden 逐位元相等** | ✅ `ab913dc` |
| 7 | WP7 | WP6 | 每個 E／W 碼反例綠（34 碼全覆蓋） | ✅ `e6b16ec`→`87f684d`→`639bce0` |
| 8 | WP1 | — | migration up/down；roundtrip 測試 | ✅ `3555a03` |
| 9 | WP8 | WP1, WP7 | 整合測試綠；`lb-csv` 不再輸出 machine_count/manpower | ✅ `3f3dd43`+`d106a85`+`b37cdc1` |
| 10 | WP9 | — | compiler 測試綠；gold TMU（effective）不變 | ✅ `9f78263`+`61fb5dc` |
| 11 | WP10 | WP6–9 | `lb_projection_check.py` 對 golden 通過（LB reader/group/general；merge 待 LB WP-L2） | ✅ `e570e2a` |
| 12 | WP11 | WP8, WP9 | 文件逐條落地；DOC_REGISTRY 狀態更新 | ✅ `7ac2ea3`+`7b9fed3` |
| 13 | WP12 | WP1, WP8 | typecheck/build/E2E 綠 | ✅ `4ada705`+`d73467f` |

> **邊數訂正**：原「38 邊」為舊估，實際 golden = **42 邊**（WP5 程式驗證，`test_lb_projection_precedence.py` 斷言 42）。
> **DoD（§0）逐條**：1 ✅（unit 1643 綠、§8.1 每碼反例）；2 ✅（golden 逐位元）；3 ✅（freeze 鎖 24 欄）；4 ✅（LB reader/quantity/group/general 通過，merge 待 LB WP-L2 修 NameError 後可驗）；5 ✅（ruff 我方檔案乾淨、前端 typecheck+build 通過）；6 ✅（§5 文件全落地、D18 指回 Spec）；7 ✅（每 commit `implements ADR-035: WPn …`）。

WP1／WP9 與投影層核心（WP2–7）互不相依，可平行。**WP6 golden 不綠不得進 WP8**（避免把錯的投影接上端點）。

---

## 4. 檔案變更總表

| 路徑 | 動作 | WP |
|---|---|---|
| `src/ddm_v2/lb_projection/*.py`（11 檔） | 新增 | 0,2–7 |
| `migrations/versions_v2/v2_0046_level_entries_lb_tags.py` | 新增 | 1 |
| `src/ddm_v2/models/v2/worksheet.py` | 改：`LevelEntry` +6 欄 | 1 |
| `src/ddm_v2/schemas/v2/worksheet.py` | 改：`LevelFieldsIn` +6 欄 | 1 |
| `src/ddm_v2/services/v2/worksheet_service.py` | 改：save／read／clone 帶六欄；read 的 cycle 加 `breakdown` | 1,2 |
| `src/ddm_v2/services/v2/export_service.py` | 改：`to_lb_csv` 重寫、`lb_api_payload` 重寫、新 `lb_export_report`、`load_vocab` | 8 |
| `src/ddm_v2/api/routes/v2/export.py` | 改：新 `lb-report` 端點 | 8 |
| `src/ddm_v2/errors/registry.py` | 改：`LB_EXPORT_BLOCKED` | 8 |
| `src/ddm_v2/exceptions.py` | 改：`LbExportBlocked` | 8 |
| `src/ddm_v2/most_compiler/policies.py` | 改：`resolve_multiplier` | 9 |
| `src/ddm_v2/most_compiler/compile.py` | 改：repeat_count 落格 | 9 |
| `src/ddm_v2/most_compiler/intermediate.py` | 改：Strict slots +`repeat_count` | 9 |
| `tests/unit/test_lb_projection_*.py`（8 檔）、`tests/unit/fixtures/lb_projection/` | 新增 | 0–7,10 |
| `tests/unit/test_compiler.py`、`tests/gold/wi_plans/*.json` | 改 | 9 |
| `tests/integration/test_worksheet_lb_tags_roundtrip.py`、`test_export_lb_csv.py` | 新增 | 1,8 |
| `scripts/lb_projection_check.py` | 新增 | 10 |
| `src/frontend/src/features/level-system/{logic,store}.ts`、`LevelSystem.tsx`、`shared/i18n/resources/{zh-TW,en}.ts`、`shared/types/api.d.ts`（重生） | 改 | 12 |
| `docs/…`（§5） | 改 | 11 |

---

## 5. 文件同步（WP11，逐條可貼文字）

1. **`docs/lb-integration/MOST_LB_CONTRACT.md`**：已由架構師加 D18、D1／D7 追記與檔頭指向（2026-09-11）。實作落地後在 D18 補「已落地（commit）」。
2. **`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §6**：末尾加
   > **LB 投影語意（ADR-035，2026-09-11）**：`frequency`＝整 motion 乘數 → LB `quantity`（非持工具）；slot `repeat_count`＝持工具動作的 cyclic 乘數 → LB use 列 `quantity`，acquire／release 為 setup。單次工時由引擎以 repeat 歸 1 重算，投影層不做 TMU 算術。完整矩陣見 `docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md` §3。
3. **`docs/core-logic/level-system-core-logic-spec.md` §9**：在「匯出載體」段加
   > **更新（ADR-035）**：`lb-csv` 改由 `lb_projection` 依 `MOST_LB_DATA_CONTRACT_SPEC.md` 產出 24 欄 LB task CSV；`build_output` 的 `precedence_edges`（level_min 相鄰鏈）**不再是** LB 匯出來源，僅供人看。層間邊＝`hi_Y < lo_X` 偏序的傳遞縮減；巢狀 cub 區塊位置以成員最小 `seq_no` 定；`a/b` 離散跳號不支援（E_LEVEL_DISCRETE_UNSUPPORTED）；nb 暫不輸出。
4. **`docs/architecture/system-architecture-v2-spec.md` §8**：JSON 範例上方加「⚠️ 已被 ADR-035 取代：LB 對接改為 24 欄 task CSV（Spec 連結）；`/export/lb-api` payload 改為 `{contract_version, csv, tasks, report}`」。
5. **`docs/architecture/data-model-and-storage-spec.md` §2.8**：表格加六欄（型別／說明同 WP1），並註 `machine_count`／`manpower`「純儲存、不匯出（D16）」。
6. **`docs/llm/wi-ai-parser-implementation-spec.md` §9.2**：`frequency` 段落後加「QuantityPolicyV2（ADR-035 D4）：持工具 action 的整數數量落 `repeat_count`（X／M／I），`frequency=1`；非持工具維持 V1。供給端時程仍依 ADR-033。」；§9.2 表 `process` 列補 `X4.repeat_count`。
7. **`docs/DOC_REGISTRY.md`**：已由架構師新增〈LB 整合〉章節；落地後把實作書狀態改 ✅。
8. **`docs/decisions/README.md`**：已加 ADR-035 列；User 核可後改 🟢。
9. **`docs/CI_GATES.md`**：核心關卡加「`tests/unit/test_lb_projection_golden.py` 與 `test_lb_projection_contract_freeze.py` 必綠」。
10. **`scripts/core_logic/README.md`**：加 `scripts/lb_projection_check.py` 一列。

---

## 6. 禁止事項（違反即退回）

1. 投影層**不得**做 TMU 加減乘除以外的推導（單次工時只能來自引擎重算或 fixture 靜態值）。
2. **不得**用敘事文字、`sub_activity`、`key_parts` 猜工具／群組／setup-cyclic；唯一訊號是 `kind='tool'`、`countersignature`、`repeat_count`、`frequency`、六個 LB 標記欄。
3. **不得**輸出 `p2`、`complexity_level`、`qty_scope=auto`、`machine_count`、`manpower`。
4. **不得**沿用 `level.build_output().precedence_edges`。
5. **不得**改 `COLUMNS` 順序／名稱而不升 `CONTRACT_VERSION`。
6. **不得**為了測試變綠修改 `fixtures/*.expected.csv`；先對照 Spec 找出哪一條規則說應該不同，回報 User。
7. **不得**修改 LB repo。
8. **不得**在 Spec／ADR 未涵蓋處自行決定語意；停下問。

---

## 7. 風險與回退

| 風險 | 緩解 |
|---|---|
| `read_worksheet` 加 `breakdown` 使回應變大 | 只在 `cycle` 內加一個 list（7 元素）；ADR-011 加法相容 |
| 既有 worksheet 無 `narrative_en` → 匯出被擋 | `lb-report` 先看 E 碼；ADR-032 review 流程補英文；不得改成 fallback 中文（LB General 判定會壞） |
| gold `expected_cycles` 形狀變（frequency→repeat） | 只改持工具 action；TMU 斷言不變；PR 附 diff 說明 |
| 分層模型表達力被現場質疑 | 記錄為 ADR-035 明文限制；收集案例供 Phase 3（LB 是否接受 sub 級偏序） |
| 回退 | 投影層為新 package，`to_lb_csv` 舊實作以 git 保留；migration 有 downgrade |
