# CL-01：序列模型與 TMU 計算（可執行核心邏輯）

> 分類：核心邏輯 ｜ 來源：`calculation_v2.py`（v3 唯一正確引擎）＋ IE 認證字典 ｜ 值表：[impl-01 §2](../../impl/impl-01-rule-set-factory-v2.md)
> 本文件是「一格 TMU 怎麼算」的完整演算法。合計/時間鏈見 [CL-04](CL-04-aggregation-and-time.md)。禁止在任何 feature 程式內重複實作本文件邏輯（DISC-03）。

## 1. 序列模型

| 模型 | 七格（slot_key） | 模式 |
|---|---|---|
| GENERAL_MOVE（GM，一般移動） | A1 B1 G A2 B2 P A3 | `A B G A B P A` |
| CONTROLLED_MOVE（CM，控制移動） | A1 B1 G M X I A3 | `A B G M X I A` |

- 每格由 `parameter_code`（A/B/G/P/M/X/I）決定演算法；GM↔CM 的獨有格不可混用（違者 422 `SLOT_CROSS_MODEL`）。
- **輸入只收 option code＋物理量**（cm、度、秒、次數）；TMU 由引擎查值表得出（DISC-02：拒收 client 端 TMU）。

## 2. 各參數演算法（權威）

記號：`T(code)` = 值表中該選項的 TMU；`repeat` = slot 級重複次數（整數 ≥1，預設 1，上限暫 99——DISC-15）。

### A（距離）
```
A1, A2： tmu = max( T(reach_band(reach_cm)), T(twist_band(twist_deg)), T(foot_band(foot_cm)) )
         未提供的分量視為 0；任何分量 < 0 → 422 A_NEGATIVE
A3（返回）： tmu = T(reach_band(reach_cm))   ← 只算伸手；出現 twist/foot → 422 A_RETURN_COMPONENT
不支援 repeat。
```

### B（身體動作）
```
tmu = T(b_code)；未選 = b_none = 0。不支援 repeat。
```

### G（取得控制）
```
tmu = T(g_code) × repeat；未選 = 0。
選項即完整語意（無修飾 gating——ADR-014；v3 實況同）。
```

### P（放置，僅 GM）
```
tmu = ( T(base) + Σ T(addon_i) ) × repeat
驗證：addons ≤ 2（P_TOO_MANY_ADDONS）；不可重複（P_DUP_ADDON）；
     a_insert ⊥ a_snap（P_ADDON_CONFLICT）；有 addon 無 base → 422 P_ADDON_NO_BASE；
     全空 P = 0（合法，如純「保持」情境由 base 表達）。
```

### M（控制移動，僅 CM）
```
tmu = max( T(verb) × repeat, T(hand_band(angle_deg)), T(foot_band(foot_cm)) )
     ← repeat 只乘 verb、再進 max（v3 認證規則：推×16 不影響手度/腳步分量）
verb 計價 kind：fixed（按鈕/滑螺絲=3）｜ladder（距離階梯查表）｜rotate（直徑+圈數查表）
超出值表範圍 → 422 M_DISTANCE_RANGE / M_ROTATION_RANGE / M_HAND_RANGE（不得靜默套最大檔）
```

### X（製程時間，僅 CM）
```
mode=zero    → 0
mode=fixed   → round_half_up( fixed_seconds / 0.036, 3位 )      （0.216s → 6.000）
mode=seconds → round_half_up( user_seconds  / 0.036, 3位 )；user_seconds ≤ 0 → 422
再 × repeat。
```

### I（對位/檢查，僅 CM）
```
tmu = T(i_code) × repeat；未選 = i_none = 0。
```

## 3. 精度與常數

- 全程 **Decimal**；TMU quantize 3 位、秒 4 位，ROUND_HALF_UP。
- `1 TMU = 0.036 秒`（唯一常數；禁用 27.8 近似值）。
- 合計不乘 10（multiplier=1）。

## 4. 人工覆寫（v2 新增，v3 僅構想——DISC 見 impl-02 E7）

slot 可帶 `manual_override {tmu ≥ 0, reason 非空, by}`：該格採 override 值、快照記 `{auto_tmu, override_tmu, reason, by}`、tech_line 標 `*`、入 audit。

## 5. 驗收黃金值（實作必測）

| 案例 | 期望 |
|---|---|
| GM：reach20 / b_none / g_grasp / reach25 / b_none / p_place_none / 0 | **28** |
| CM：reach25 / b_none / g_touch / 推45cm / x_none / i_none / 0 | **29**（推45cm=18吋檔→16） |
| 推 18cm | 10（防單位回歸反例） |
| X user 10s | 277.778 |
| M 推45cm repeat=3, hand≤90 | max(48, 6)=48 |
| A3 帶 twist_deg | 422 A_RETURN_COMPONENT |
| P insert+snap | 422 P_ADDON_CONFLICT |

完整黃金/反例目錄：[impl-02 §E8](../../impl/impl-02-engine-changes.md)。
