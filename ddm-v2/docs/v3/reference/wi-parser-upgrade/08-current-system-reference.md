# 08 · 現況系統事實清單（Current System Reference）

> **用途**：這是「**今天的 parser 到底長什麼樣**」的單一事實來源（single source of truth）。
> 其他文件需要引用現況的具體結構/缺陷時，都連到這裡，避免把原始碼細節散落各處。
> 來源：[apps/api/app/services/nl_draft_parser.py](../../apps/api/app/services/nl_draft_parser.py) 與 [routes/most.py](../../apps/api/app/api/routes/most.py)。
> **升級時：本檔列的「行為」要嘛保留、要嘛在 [05](05-implementation-plan.md) 明確處理，不可無聲改變。**

---

## 8.1 資料結構（升級的相容基準）

`SlotSuggestion`（每個 slot 的建議）欄位：

| 欄位 | 型別 | 說明 |
|------|------|------|
| `option_code` | str | 對到的選項碼 |
| `display_text_zh` | str | 顯示文字 |
| `sentence_text_zh` | str | 造句片段 |
| `tmu_value` | int/float/None | TMU（**來自詞典**，預設值除外見 §8.8） |
| `confidence` | float | 信心（**目前是寫死常數**，見 §8.8） |
| `source` | str | `inferred` / `default` / `explicit` |
| `badge` | str | 顯示徽章（如「AI 推斷」「預設值，請確認」） |
| `control_key` | str/None | 模態控制鍵（`reach_distance` / `base_action` / `verb`） |
| `modifiers` | list/None | P 的修飾項（最多 2） |
| `seconds_source` / `fixed_seconds` | — | X 製程秒數來源 |

`NLDraftResult`：`raw_text, suggested_sequence_model, confidence, context_fields{hand_type, show_hand_in_sentence, from_location, target_object, component, to_location, where_location}, slot_suggestions{}, missing_fields[], warnings[]`。

> 升級後的 `NLDraftResultV2`（[04 §4.3](04-architecture-design.md)）必須能 `to_legacy()` 還原成上面這兩個結構，[`/nl-draft` 路由](../../apps/api/app/api/routes/most.py) 才不會壞。**新欄位只增不改**。

---

## 8.2 解析管線順序（`parse()` 八步）

```
1 _parse_hand        左/右/雙手 → hand_type、show_hand_in_sentence
2 _parse_context     regex 抽 from_location / target_object / to_location
3 _parse_distance    regex 抽顯式距離(cm)
4 _parse_b           身體動作 B → 只設 B1（B2 從不從文字推！見 §8.9）
5 _parse_actions     判 sequence model；GENERAL→G+P，CONTROLLED→G+X+I+M+context重解
6 _apply_a_defaults  顯式距離→區間；否則 A1/A3 預設 35cm，A2 留空
7 _apply_b_defaults  B1 預設「站」、(GENERAL)B2 預設「眼部動作」
8 _compute_warnings  default 來源 → 加 warning / missing
```

---

## 8.3 Slot 與 option_code 全清單（候選池）

> 這就是**封閉本體**；Phase 1 向量化、Phase 2 linking、LLM 的 enum 都以此為準（實際以 active 詞典版本為主，下表為內建種子）。

| Slot | option_code（依現況同義詞表/詞典） |
|------|-----------------------------------|
| **G** 取得 | G_LIGHT_PRESS, G_TOUCH, G_LIGHT_TAP, G_GRASP, G_PICK, G_SELECT, G_SELECT_SMALL, G_TRANSFER_HAND, G_SEPARATE, G_COLLECT |
| **P** base | P_THROW, P_HOLD, P_PLACE_NO_DIRECTION, P_ASSEMBLE_MULTI_DIRECTION |
| **P** modifier | P_ALIGN_LT_4MM, P_INSERT, P_SNAP_FIT |
| **X** 製程 | X_PRESS_MACHINE, X_SNAP_PRESS_MACHINE, X_HOT_MELT_MACHINE, X_DISPENSE_GLUE, X_SCREW_FIX, X_LASER_MARK, X_SCAN_PPID, X_SCAN_WORK_ORDER_QR, X_SCAN_BARCODE, X_BLOW_CLEAN |
| **I** 檢查 | I_CHECK_/CONFIRM_/ALIGN_POINT_/ALIGN_TWO_POINTS_ × {NORMAL, OUTSIDE} |
| **B** 身體 | B_EYE_MOVE, B_BEND_OR_SIT, B_STAND |
| **M** 控制 | M_PRESS_BUTTON, M_SLIDE_OUT_SCREW（＋詞典 `controls.verb` 的簡單動詞：推/拉/旋轉/擦拭/貼附/去除/撕除/折/撕開/理/穿） |
| **A** 距離 | 見 §8.4（數值映射，非同義詞） |

---

## 8.4 A 距離區間對照表（確定性，**勿丟模型**）

| 上限 cm | option_code | display | TMU |
|---------|-------------|---------|-----|
| ≤ 2.5 | A_REACH_LE_1_2_5CM | <=1(2.5) | 0 |
| ≤ 5 | A_REACH_LE_2_5CM | <=2(5) | 1 |
| ≤ 10 | A_REACH_LE_4_10CM | <=4(10) | 3 |
| ≤ 20 | A_REACH_LE_8_20CM | <=8(20) | 6 |
| ≤ 35 | A_REACH_LE_14_35CM | <=14(35) | 10 |
| ≤ 60 | A_REACH_LE_24_60CM | <=24(60) | 16 |
| > 60 | A_REACH_GT_24_60CM | >24(60) | 24 |

**預設**：`A_REACH_LE_14_35CM`（35cm, TMU 10）。Stage 2 的「距離→區間」直接沿用此表（[05 Phase 1](05-implementation-plan.md)）。

---

## 8.5 詞典 JSON 結構（Phase 1 向量化要讀的路徑）

`_load_dict()` 載入 [data/minimost_ai_dictionary_v1.json](../../apps/api/app/data/minimost_ai_dictionary_v1.json)，路徑如下（**索引時要逐一抽 `display_text_zh + sentence_text_zh + synonyms` 編碼**）：

```text
d["parameters"]["G"]["options"]                  # G/B/X/I 同構
d["parameters"]["B"]["options"]
d["parameters"]["X"]["options"]                  # option 另有 seconds_source / fixed_seconds
d["parameters"]["I"]["options"]
d["parameters"]["P"]["base_actions"]             # P 拆 base 與 modifier 兩池
d["parameters"]["P"]["modifiers"]
d["parameters"]["M"]["controls"]["verb"]["options"]
```

每個 option 至少有：`option_code, display_text_zh, sentence_text_zh, tmu_value`。
> **注意**：P 的 base 與 modifier 是**兩個獨立候選池**；M 在 `controls.verb` 之下。向量索引要**按這個結構分庫**，否則候選會跨池污染。

---

## 8.6 DB 同義詞機制（active learning 的回灌點）

- `load_db_synonyms(db_session)`：讀 active 詞典版本中 `ParameterOption.synonyms_json` 非空者，依 `ParameterSlot.parameter_code` 分組，回傳 `{param_code: [(keywords, option_code)]}`。**鍵只有 G/X/M/P/B/I（A 不走同義詞）**。
- 快取：`_DB_SYNONYMS_CACHE` 以 active version id 為鍵；`invalidate_synonym_cache()` 在**詞典發布後**呼叫（[dictionaries.py](../../apps/api/app/api/routes/dictionaries.py) 既有鉤子）。
- `_get_synonyms(code, hardcoded)`：DB 優先、串接 hardcoded。

> **這是 [06 §6.7 active learning](06-evaluation-and-audit.md) 的落點**：人工修正 → 寫 `synonyms_json` → `invalidate_synonym_cache()` →（升級後再加）觸發向量 reindex。**沿用既有鉤子，不要另造一套。**
> **既有量化 quirk**：`_parse_p` 只把 DB 的 `"P"` 同義詞用在 **modifier** 檢查；**base action 只用 hardcoded** `P_BASE_SYNONYMS`（不吃 DB）。升級時要把 base/modifier 都納入可回灌。

---

## 8.7 sequence model 與句子組裝（確定性骨架）

- **判定**（`_parse_actions`）：偵測到 X/I 或 `CONTROLLED_MOVE_KEYWORDS` → `CONTROLLED_MOVE`，否則 `GENERAL_MOVE`。升級時把此啟發式**集中成一個規則函式**（[04 §4.6.1](04-architecture-design.md)）。
- **組裝順序**（[most.py `_compose_full_sentence`](../../apps/api/app/api/routes/most.py)）：
  - GENERAL：`手 + 從X + A1 + B1 + G + 目標物 + 元件 + A2 + B2 + P + 至Y + A3`
  - CONTROLLED：`手 + 從X + A1 + B1 + G + 目標物 + 元件 + M + 至Y + X + I + 哪裡 + A3`

---

## 8.8 信心常數現況（為何不能拿來分流）

| 來源 | confidence |
|------|-----------|
| G / I / B 推斷 | 0.85 |
| X / M 推斷 | 0.9 |
| P 推斷 | 0.8 |
| M 簡單動詞 fallback | 0.6 |
| A 由語句距離 | 0.9 |
| **default（預設值，純猜）** | **1.0** ⚠️ |

> ⚠️ **反置問題**：**純預設（猜的）信心 1.0，反而比真正推斷（0.8–0.9）還高**。這代表現況的 `confidence` **完全不能**拿來做審核分流——這正是 [06 §6.5 必須做校準](06-evaluation-and-audit.md) 的最佳實證。升級後 `confidence` 一律改為**校準後機率**，預設值要標**低**信心 + 待確認。

---

## 8.9 已確認的具體缺陷與脆弱行為（升級必處理）

| # | 缺陷 | 位置 | 影響 |
|---|------|------|------|
| D1 | **最長匹配遮蔽**：`拿取小`被`拿取`(G_SELECT)先吃 | `G_SYNONYMS` 順序 + `_parse_g` first-win | `G_SELECT_SMALL` 不可達 |
| D2 | **只有 M 做最長匹配**：G/P/X/I/B 沒有 | 各 `_parse_*` | 同類遮蔽散落 |
| D3 | **零正規化**：繁簡/全半形/英文全 miss；全形數字距離抽不到 | 全檔；`_parse_distance` | 大量輸入失配 |
| D4 | **跨 slot 關鍵字碰撞**：`對準`/`對齊` 同時是 P modifier 與 I；`卡合` 同時是 P modifier、X(卡合壓合) 與 sequence keyword | `P_MODIFIER_SYNONYMS` vs `I_SYNONYMS` vs `X_SYNONYMS` | 同詞依路徑對到不同 slot → 歧義（適合做多引擎不一致送審） |
| D5 | **信心反置**：default=1.0 > inferred | 各 `_apply_*` | 無法分流（見 §8.8） |
| D6 | **parser 內硬編 TMU**：B1 預設 `B_STAND tmu=42`、B2 `B_EYE_MOVE tmu=10` 直接寫死，未走詞典 | `_apply_b_defaults` | 詞典改值會與預設不一致 |
| D7 | **B2 從不從文字推斷** | `_parse_b` 只設 B1 | B2 永遠是預設 |
| D8 | **context 靠字元黑名單 regex** | `_parse_context` `[^\s從到至放…]` | 語序/用詞一變就抓錯 |
| D9 | **CONTROLLED context 靠位置假設**：G verb 必須在 M/X 之前 | `_parse_controlled_move_context` | 語序顛倒即崩 |
| D10 | **I 視線判定脆弱**：僅靠「範圍外/視線範圍外」字串；normal/outside 詞表重複 | `_match_i` / `I_SYNONYMS` | outside 漏判即錯 slot |
| D11 | **module singleton 無 db** | `_parser = RuleBasedDraftParser()` | 無 db_session 路徑只用 hardcoded 同義詞 |

> D4 與 D10 是**語意歧義**類，不是純 bug——升級後正解是讓**多引擎不一致 → 送審**（[04 §4.7](04-architecture-design.md)），而非硬寫死。

---

## 8.10 升級時的相容錨點（不可破壞）

1. **`/nl-draft` 回傳格式**：用 `to_legacy()` 還原 `slot_suggestions` 結構；新欄位只增不改。
2. **`invalidate_synonym_cache()` 鉤子**：reindex 掛在這裡，別另造。
3. **計算引擎權威**：本 parser 僅「建議預填」，TMU 仍由計算引擎決定。
4. **A 區間表（§8.4）/ 組裝順序（§8.7）**：屬領域規則，升級沿用，勿改數值。

---

← 回 [README 索引](README.md)　|　相關：[01 診斷](01-problem-and-requirements.md)、[04 架構](04-architecture-design.md)、[05 施工](05-implementation-plan.md)、[06 評測](06-evaluation-and-audit.md)
