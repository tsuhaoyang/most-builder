# impl-02：引擎變更 E1–E9 與黃金測試重錨

> **Phase**：P1 ｜ **ADR**：ADR-014 ｜ **原則**：單一引擎（`most_engine/`）單點修改；每項變更**先寫黃金/反例再改碼**（先紅後綠）；改完必跑 `validate-core-logic`。
> 影響檔案：`most_engine/calculate.py`、`most_engine/rule_set_data.py`、`most_engine/narrative.py`、`schemas/v2/most.py`、`services/v2/worksheet_service.py`、`scripts/core_logic/`、`tests/unit/test_most_engine.py`。

## 0. 精度口徑（全引擎統一，先於各項）

- TMU 以 **Decimal** 運算，輸出 quantize 3 位小數（ROUND_HALF_UP）；秒 4 位小數。
- 整數值表（A/B/G/P/I）運算結果仍為整數語意，Decimal 只保證 X 與合計不失真。
- `TMU_TO_SEC = Decimal("0.036")` 唯一常數；**禁止** 27.8 之類的近似倒數出現在程式與文件。

## 1. 變更清單

### E1 — A3 返回格僅算 reach

- `compute_cycle` slot6 改走新函式 `_a_return_tmu`：僅接受 `reach_cm`；出現 `twist_deg`/`foot_cm` → `SequenceError("A_RETURN_COMPONENT", ...)`。
- slot0/slot3（GM）維持三分量 max。
- Pydantic：`schemas/v2/most.py` 的 slot6 形狀收斂為 `{reach_cm}`。

### E2 — X 捨入：ceil → half-up 3 位

- `rule_set_data.seconds_to_tmu`：`math.ceil(sec/0.036)` → `(Decimal(sec)/Decimal("0.036")).quantize(Decimal("0.001"), ROUND_HALF_UP)`。
- 錨點：0.216s → **6.000**（不變）；10s → **277.778**（原 278）。
- 適用於 V1 與 V2 rule-set（捨入是引擎行為非資料；ADR-014 記載此為全域口徑變更，V1 回放的 X 值差異在 ±1 TMU 內，`computed` 快取不重算故歷史數值不動）。

### E3 — P 附加互斥與顯式錯誤

- `_p_tmu` 新增：`{"a_insert","a_snap"} ⊆ addons` → `SequenceError("P_ADDON_CONFLICT", "插入與卡合不可同時選擇")`。
- 有 addons 而無 base：由現行「回 0」改為 `SequenceError("P_ADDON_NO_BASE", ...)`（顯式擋，v3 認證驗證）。
- `needs_precision` gating 依 V2 資料自然失效（a_align 已 false）；引擎邏輯保留（讀資料）。

### E4 — slot 級 `repeat_count`

- `slot_inputs` 各 slot 新增選填 `repeat_count: int ≥ 1`（預設 1；非整數/＜1 → `SequenceError("REPEAT_INVALID")`；上限暫 99，殘項 #4）。
- 適用格：G、P、X、I → `slot_tmu × repeat_count`；**M → 僅 verb 分量 × repeat 後再進 max**（v3 認證規則：推×16 不影響手度/腳步分量）；A、B 不支援（出現即 422）。
- `tech_line` 與 narrative 顯示 `×N`（N>1 時）。

### E5 — SIMO：配對 UX → 群組引擎

- 引擎 `compute_table` **不變**（群組取 max）。
- `worksheet_service.save_worksheet` 新增正規化：前端送 `simo_with_row_id` 配對 → service 以 union-find 收斂成 `simo_group_id`（既有欄）；配對指向不存在列/自指 → 422 `SIMO_PAIR_INVALID`。
- ⚠️ 查證 C-9：v3 的 `simo_with_row_id` **僅儲存、零驗證**（`models/most.py:51`）——本項驗證為 v2 新增防線，非 v3 移植。
- WiRow 不加欄（配對是輸入形式，群組是儲存形式——單一真相）。

### E6 — narrative 顯示規則（讀 `display_rule`）

`narrative.py` P 段組字算法（v3 認證）：

```
visible = base.sentence_text_zh
if a_insert 選中: visible = "插入"          # show_self 取代 base
elif a_snap 選中: visible = "卡合"
if a_align 選中: visible = "對準" + visible   # prefix_visible_term
a_hard / a_press: 不出現（hidden，僅計 TMU）
```

另：GM slot3（A_move）含 `twist_deg` 時，敘事插入「翻轉+{object}」（v3 dependency 規則）。全部由 rule-set 的 `display_rule`/`sentence_text_zh` 資料驅動，narrative 不寫死選項字。

### E7 — 人工覆寫留痕

> ⚠️ 查證 C-4：此為**採納 v3 規格構想**（spec 的 `step_slot_value.manual_index_value`＋`calculation.py` dataclass），v3 **並未**接線至任何 live API——v2 為首次實作，UI 形式待 IE 確認。

- `slot_inputs` 各 slot 新增選填 `manual_override: {tmu: number ≥ 0, reason: str 非空, by: str}`。
- 引擎：有 override → 該格 TMU 採 override 值，`computed` 記 `{auto_tmu, override_tmu, reason, by}`；`tech_line` 標 `*`（如 `M16*`）。
- reason 空/負值 → 422 `OVERRIDE_INVALID`。service 層寫 audit（P5 前先落 `computed`，audit 表就緒後補投）。

### E8 — 黃金測試重錨（值語意依 v3）

| 錨點 | V1（舊） | **V2（新，權威）** |
|---|---|---|
| GM 典型 | A6 B0 G6 A10 B0 P6 A0 = **28** | 不變（輸入：伸手20cm、抓握、伸手25cm、放無方向） |
| CM 典型 | 推「18cm」→ M16 | 推 **45cm**（=18吋檔）→ M16；**推 18cm → M10**（新反例，防單位回歸） |
| X 10s | 278 | **277.778** |
| X 0.216s | 6 | 6.000 |
| M 推 30cm | 24 | **16**（≤45 檔） |
| M 推 76cm | 42 | **422 M_DISTANCE_RANGE**（無 overflow 檔） |
| M 腳步 30cm | （走階梯）24 | **16**（foot 帶 ≤40） |
| 旋轉 dia60cm | 24（NULL 檔） | **422 M_ROTATION_RANGE** |
| G 接觸未勾 contact | 0 | **3**（gating 移除，資料驅動） |
| A3 twist 輸入 | 計入 max | **422 A_RETURN_COMPONENT** |
| I i_confirm_out | （無此檔） | 16 |
| repeat：推45cm ×3 | （無此概念） | M = max(16×3, hand, foot) = 48 |

- `scripts/core_logic/minimost_sequence_validator.py` 與 89 案例逐案過帳：**每案標注「值不變 / 值變更（原因=C1..C9）/ 新增」**，產出過帳表附於 `core-logic-validation-test-catalog.md` 改版。
- V1 rule-set 的舊黃金保留為「回放測試」（用 V1 算仍得 28/29 舊口徑，證明快照隔離）。

### E9 — M 腳步/範圍檢查（配合 impl-01 §2.5–2.7）

- `rule_set_data.py` 新增 `foot_tmu(cm)` 讀 `rule_m_foot_bands`；rule-set 無 foot 資料（V1）→ 回退 `ladder_tmu`（回放相容）。
- `ladder_tmu`/`rotation_tmu`/`hand_tmu` 超出最大檔 → 分別拋 `M_DISTANCE_RANGE`/`M_ROTATION_RANGE`/`M_HAND_RANGE`（V2 資料下才會觸發；V1 有 overflow 檔不受影響）。

## 2. 錯誤碼一覽（新增）

`A_RETURN_COMPONENT`、`P_ADDON_CONFLICT`、`P_ADDON_NO_BASE`、`REPEAT_INVALID`、`SIMO_PAIR_INVALID`、`OVERRIDE_INVALID`、`M_DISTANCE_RANGE`、`M_ROTATION_RANGE`、`M_HAND_RANGE`、`X_SECONDS_REQUIRED`。全部 422，錯誤格式沿用 `SequenceError(code, message)` → API `{detail: {code, message}}`。

- `X_SECONDS_REQUIRED`（CL-01 §2 X，v3 認證「X 動態秒數項目必須輸入正數」）：`mode=seconds` 且秒數未填或 ≤0 → 422。**負值維持既有 `X_NEGATIVE` 先攔（不併入）**——理由：(1) 語意區分「方向/符號錯誤」與「必填未填」，前端可分別給提示；(2) 既有負秒反例（unit／engine_golden／standalone validator）斷言不動，避免無謂的黃金測試改帳。此為引擎行為（同 E2 half-up 全域生效）：V1 回放段無 `mode=seconds` 且 0 秒之案例（V1 seed 自檢用本地 ceil 函式，不經引擎）；歷史 `computed` 快取不重算故不受影響。
- 單一驗證來源：`REPEAT_INVALID` 範圍驗證（1..99、A/B 格禁用）權威在引擎 `_repeat`/`_no_repeat`；`schemas/v2/most.py` 的 `repeat_count` 只驗型別 `int|None`（不設 ge/le），A/B slot 亦開 passthrough 欄使引擎防線經 API 可達。

## 3. Worksheet 層

- `most_worksheets.allowance_percent numeric NULL`（migration v2_0010）：`standard_seconds = total_seconds × (1 + allowance_percent/100)`，僅出現在讀取/匯出投影，**不落列級欄**；與 `level_entries.coefficient` 語意分離（OQ-002 追蹤命名/預設）。
- 匯出（`export_service.py`）：Excel 增列 normal/standard 兩時間欄；lb-csv 合約**不變**（LB 拿 normal，寬放政策屬 MOST 端——如需變更走 ADR-011 加法程序）。

## 4. 完成定義（P1 gate）

1. 新黃金目錄全綠（`validate-core-logic`）；V1 回放測試綠。
2. `pytest tests/unit tests/integration` 綠；新錯誤碼各有反例測試。
3. `docs/core-logic/minimost-sequence-model-core-logic-spec.md` §4/§8/§10 改版完成（V2 值表、v3 權威聲明、舊 Q3/Q4 裁決標 superseded by ADR-014）。
4. `.claude/skills/ie-most-engineer/SKILL.md` 口徑段落同步（X half-up、M 單位、G gating 移除、A3）。
5. CI_GATES.md 增列本 phase 驗證點。
