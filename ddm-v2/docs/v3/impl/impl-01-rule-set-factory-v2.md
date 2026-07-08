# impl-01：rule-set `MINIMOST_FACTORY_V2` — 值表、schema 變更、converter、migration

> **Phase**：P1 ｜ **ADR**：ADR-014 ｜ **前置**：ADR-014 accepted、[impl-02](impl-02-engine-changes.md) 黃金目錄重錨完成（先紅後綠）
> **值來源**：[reference/minimost_ai_dictionary_v1.json](../reference/minimost_ai_dictionary_v1.json)（IE 認證，唯一權威）。
> **鐵則**：seed 由 converter 程式化轉換產生，**禁止手抄數值**；`MINIMOST_FACTORY_V1` 保留 published 供既有 cycle 回放。

## 1. Schema 變更（migration `v2_0009_rule_set_v3_alignment`）

依 [[database-v2]]：手寫 migration、必附 `downgrade()`、新 model import 進 `models/v2/__init__.py`。

### 1.1 新表

```sql
-- M 腳步帶（獨立於 M 距離階梯；v3 認證值與階梯不同）
CREATE TABLE rule_m_foot_bands (
  id uuid PRIMARY KEY,
  rule_set_id uuid NOT NULL REFERENCES rule_sets(id) ON DELETE CASCADE,
  max_cm numeric NULL,              -- NULL = overflow 檔（>75）
  tmu int NOT NULL,
  sort_order int NOT NULL,
  UNIQUE (rule_set_id, sort_order)
);
```

### 1.2 加欄（既有表，加法演進，全部 NULLABLE 或帶 default）

| 表 | 新欄 | 型別 | 用途 |
|---|---|---|---|
| `rule_p_addons` | `display_rule` | text CHECK IN ('show_self','hidden','prefix_visible_term') DEFAULT 'show_self' | 敘事三態（v3 認證顯示規則） |
| `rule_i_options` | `vision_scope` | text CHECK IN ('normal','outside') NULL | UI 分組（i_none 為 NULL） |
| 各選項表（B/G/P base/P addon/M verb/X/I） | `sentence_text_zh` | text NULL | 敘事用字與計算標籤分離（v3 字典提供；NULL 時 narrative 回退 `label_zh`） |

### 1.3 `m_foot` 動詞計價來源切換

`rule_m_verbs.pricing_kind = 'foot'` 的查表對象由 `rule_m_ladder_bands` 改為 `rule_m_foot_bands`（引擎變更見 impl-02 E9；V1 rule-set 無 foot bands 資料時引擎回退階梯，保回放相容）。

## 2. `MINIMOST_FACTORY_V2` 完整值表（converter 驗收基準）

> 以下為 converter 輸出的**驗收快照**：converter 跑完後，逐表比對必須完全一致（自動化比對，見 §4 測試）。v2 code 沿用既有命名慣例；`v3_option_code` 欄為對照與追溯用。

### 2.1 A 帶（`rule_a_bands`，與 V1 相同——v3 認證值一致）

| component | max_value | index | 對應 v3 |
|---|---|---|---|
| reach | 2.5 / 5 / 10 / 20 / 35 / 60 / NULL | 0 / 1 / 3 / 6 / 10 / 16 / 24 | A_REACH_LE_1_2_5CM … A_REACH_GT_24_60CM |
| twist | 30 / 60 / 120 / 180 | 0 / 1 / 3 / 6 | A_HAND_LE_30 … A_HAND_LE_180 |
| foot | 20 / 30 / 45 / 65 / NULL | 6 / 10 / 16 / 24 / 32 | A_STEP_LE_8_20CM … A_STEP_GT_26_65CM_2STEP |

### 2.2 B 選項（`rule_b_options`，值不變）

| code | label_zh | index | default | v3_option_code |
|---|---|---|---|---|
| b_none | 無身體動作 | 0 | ✓ | （v3 無顯式列；未選=0） |
| b_eye | 眼部動作 | 10 | | B_EYE_MOVE |
| b_bend | 起身或彎腰/坐 | 32 | | B_BEND_OR_SIT |
| b_stand | 站 | 42 | | B_STAND |

### 2.3 G 動作（`rule_g_actions`，值不變；**gating 全關**）

**全部 `requires_modifier = false`、`modifier_key = NULL`**（v3 認證「選項即完整語意」，ADR-014）。修飾語意留在 label。

| code | label_zh | base_tmu | v3_option_code |
|---|---|---|---|
| g_tap | 輕按 | 3 | G_LIGHT_PRESS |
| g_touch | 接觸 | 3 | G_TOUCH |
| g_pat | 輕拍 | 3 | G_LIGHT_TAP |
| g_grasp | 抓握 | 6 | G_GRASP |
| g_grab | 抓取 | 6 | G_PICK |
| g_regrasp | 重新抓握 | 6 | G_REGRASP |
| g_handchange | 換手(轉移) | 10 | G_TRANSFER_HAND |
| g_pick_sel | 拿取(選取) | 10 | G_SELECT |
| g_pick_small | 拿取(選取-小) | 16 | G_SELECT_SMALL |
| g_pullout | 拔出(分離) | 16 | G_SEPARATE |
| g_pick_collect | 拿取(收集) | 24 | G_COLLECT |

### 2.4 P base（`rule_p_bases`，值不變）＋ P addon（`rule_p_addons`）

Base 七項同 V1（丟3/保持住3/放無6/放多10/放一16/組多10/組一16）。

| addon code | label_zh | delta | needs_precision | display_rule | sentence_text_zh | v3_option_code |
|---|---|---|---|---|---|---|
| a_align | 對準(精度<4mm) | 8 | **false**（選項自含精度語意） | prefix_visible_term | 對準 | P_ALIGN_LT_4MM |
| a_insert | 插入 | 8 | false | show_self | 插入 | P_INSERT |
| a_hard | 較難處理 | 8 | false | **hidden** | （空） | P_DIFFICULT_HANDLE |
| a_snap | 卡合 | 16 | false | show_self | 卡合 | P_SNAP_FIT |
| a_press | 施加壓力 | 16 | false | **hidden** | （空） | P_APPLY_PRESSURE |

互斥規則 `a_insert ⊥ a_snap` 為引擎驗證（impl-02 E3），不入資料表。

### 2.5 M 距離階梯（`rule_m_ladder_bands`）——**單位修正（C1 裁決）**

| max_cm | 2.5 | 10 | 25 | 45 | 75 |
|---|---|---|---|---|---|
| tmu | 3 | 6 | 10 | 16 | 24 |

- 門檻語意＝**cm**（v3 字典「≤1(2.5)…≤30(75)」括號值）。V1 的 1/4/10/18/30 是吋數誤存，V2 修正。
- **`>75cm` overflow 檔（42）暫不建**——v3 字典動詞無此檔（殘項 #1，IE 裁決後若要加，補一列 `(NULL, 42)` 即可，schema 已支援）。引擎行為：超出最大檔 → 422 `M_DISTANCE_RANGE`（impl-02 E9），**不得靜默套用最大檔**。

### 2.6 M 腳步帶（`rule_m_foot_bands`，新表）——C2 裁決採 v3

| max_cm | 25 | 40 | 55 | 75 | NULL(>75) |
|---|---|---|---|---|---|
| tmu | 10 | 16 | 24 | 32 | 42 |

### 2.7 M 動詞（`rule_m_verbs`，集合不變）／旋轉／手度

- 動詞：`m_btn`/`m_screw`（fixed 3）；`m_li 理`/`m_through 穿`/`m_push 推`/`m_pull 拉`/`m_attach 貼附`/`m_remove 去除`/`m_teartape 撕除`/`m_fold 折`/`m_wipe 擦拭`/`m_tearopen 撕開`（ladder）；`m_rotate`（rotate）；`m_hand`（hand）；`m_foot`（**foot → 新表**）。
- 旋轉（`rule_m_rotation_bands`）：≤12.5cm 1/2/3 圈 = 16/32/42；≤50cm 1/2 圈 = 24/42。**V1 的 `(NULL, 3, 42)` 大直徑 3 圈檔移除**（v3 無，殘項 #2）；超範圍（>50cm 或 3 圈大直徑）→ 422 `M_ROTATION_RANGE`。
- 手度（`rule_m_hand_bands`）：≤90→6、≤180→10；**>180° → 422 `M_HAND_RANGE`**（V1 為 open-ended，V2 封頂依 v3）。

### 2.8 X 選項（`rule_x_options`）——九檔＋x_none

| code | label_zh | mode | fixed_seconds | v3_option_code |
|---|---|---|---|---|
| x_none | 無機台等待 | zero | — | （v3 無；未選=0） |
| x_press | 並壓合機台 | seconds | — | X_PRESS_MACHINE |
| x_snap_press | 並卡合&壓合機台 | seconds | — | X_SNAP_PRESS_MACHINE |
| x_heat | 並熱熔機台 | seconds | — | X_HOT_MELT_MACHINE |
| x_glue | 並點膠 | seconds | — | X_DISPENSE_GLUE |
| x_screw_fix | 並鎖附固定 | fixed | 0.216 | X_SCREW_FIX |
| x_laser | 並鐳雕 | seconds | — | X_LASER_MARK |
| x_scan_ppid | 刷PPID | fixed | 0.216 | X_SCAN_PPID |
| x_scan_wo | 刷工單二維碼 | fixed | 0.216 | X_SCAN_WORK_ORDER_QR |
| x_scan_bar | 刷條形碼 | fixed | 0.216 | X_SCAN_BARCODE |

秒→TMU 捨入改 half-up（impl-02 E2）；0.216s → 6.000 TMU（兩制相同，黃金錨點）。

### 2.9 I 選項（`rule_i_options`）——八檔＋i_none

| code | label_zh | index | vision_scope | v3_option_code |
|---|---|---|---|---|
| i_none | 不額外對齊 | 0 | NULL | （v3 無；未選=0） |
| i_check | 並檢查(正常視線範圍) | 6 | normal | I_CHECK_NORMAL |
| i_confirm | 並確認(正常視線範圍) | 6 | normal | I_CONFIRM_NORMAL |
| i_align1 | 並對準(正常視線範圍到點) | 10 | normal | I_ALIGN_POINT_NORMAL |
| i_align2 | 並對齊(正常視線範圍到兩點) | 16 | normal | I_ALIGN_TWO_POINTS_NORMAL |
| i_check_out | 並檢查(正常視線範圍外) | 16 | outside | I_CHECK_OUTSIDE |
| i_confirm_out | 並確認(正常視線範圍外) | 16 | outside | I_CONFIRM_OUTSIDE |
| i_align1_out | 並對準(正常視線範圍外到點) | 24 | outside | I_ALIGN_POINT_OUTSIDE |
| i_align2_out | 並對齊(正常視線範圍外到兩點) | 32 | outside | I_ALIGN_TWO_POINTS_OUTSIDE |

## 3. Converter：`scripts/import_v3_dictionary.py`

```
輸入：docs/v3/reference/minimost_ai_dictionary_v1.json
輸出：src/ddm_v2/seed/v2/rule_set_seed_v2.py（DATA 常數，格式同 rule_set_seed.py）
     ＋ 轉換報告（stdout：逐參數筆數、v3_option_code 對照、丟棄/待裁決項）
```

規則：
1. **純函數轉換**，v3 option_code → v2 code 對照表寫在 converter 內（即 §2 各表的對照欄），任何 JSON 中出現而對照表沒有的 option_code → **報錯中止**（不得靜默丟棄）。
2. `b_none`/`x_none`/`i_none` 三個顯式零值列由 converter 注入（v3 以「未選=0」表達，v2 schema 慣例用顯式列）。
3. M 動詞×距離檔在 v3 是展開的（`M_推_LE_4_10CM`…）：converter 驗證**每個 ladder 動詞的檔位值與 §2.5 階梯完全一致**後收斂成單一階梯表；不一致 → 報錯中止。
4. seed 檔尾附 `_self_check()`（同 V1 慣例）：用 V2 資料重算黃金值（見 impl-02 E8 新黃金）。

## 4. Seed 與測試

- `seed_rule_set_factory_v2(session)`：插入 V2（published）；**idempotent**（以 code 查存在即跳過）。V1 不動。
- `most_worksheets.default_rule_set_id` 的預設指向改為 V2（僅影響新建 worksheet；既有 cycle 快照不變）。
- 測試（[[testing-ci-hard-rules]]：每 feature 有 endpoint 測試）：
  1. `test_rule_set_v2_values.py`：DB 內 V2 各子表逐列比對 §2 快照（防 converter/seed 漂移）。
  2. `test_rule_set_v2_options_endpoint.py`：`GET /api/v2/rule-sets/MINIMOST_FACTORY_V2/options` 回傳完整選項（含新欄 vision_scope/display_rule）。
  3. converter 單元測試：對照表完整性、未知 code 中止、ladder 收斂驗證、idempotent。
  4. 回放測試：既有 V1 cycle 重算結果不變（快照隔離證明）。

## 5. Migration 清單

| revision | 內容 | downgrade |
|---|---|---|
| `v2_0009` | `rule_m_foot_bands` 新表；`display_rule`/`vision_scope`/`sentence_text_zh` 加欄 | drop table / drop columns |
| `v2_0010` | （見 impl-02）`slot_inputs` 為 JSONB 不需 migration；`most_worksheets.allowance_percent numeric NULL` 加欄 | drop column |

驗證：`alembic upgrade head` → `alembic heads` 單一 head → `downgrade -2` → `upgrade head` 可逆實測。
