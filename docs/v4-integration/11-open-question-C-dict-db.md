# 開放問題 C 技術評估：字典合併前是否需先做 DB 實值複核

> 目的：為 v4 整合的字典合併（`03-data-model-and-dictionary.md` §3 提出的差異）決定 Phase 0 是否要「先對 v2 seed 後的 DB 實表值複核一次」。
> 方法：實查 v2 現行 DB（port 15432，`MINIMOST_FACTORY_V2` 為 active rule set）的 rule_* 12 表，比對 v4 資料與 migration，並實跑黃金值。附 `檔案:行號` 與實查輸出。唯讀分析，不改 v2/v4 程式碼。
> 日期：2026-09-04

---

## 裁決結論（結論在前）

**不需要把 DB 實值複核當成一個獨立的 Phase 0 前置關卡。** 我已在本次評估中對 active DB（`MINIMOST_FACTORY_V2`）實查完成三項複核，結果如下：

1. **M_PRESS 已在 DB**：active rule set 的 `rule_m_verbs` 有一列 `code=m_press`、`label_zh=按壓`、`pricing_kind=fixed`、`fixed_tmu=3`。03 文件「v2 多一個 M_PRESS（fixed 3 TMU）」在 DB 實表為**真**。
2. **CM 返回槽 A2/A3 在 v2 DB 根本不存在為資料**：v2 沒有 `parameter_slots` / `slot_key` 這類表，A 帶只以 `component`(reach/twist/foot) 存值、由引擎**位置**消費（`CM_LETTERS` 第 6 位是返回 A）。「A2→A3」是 **v4 端的 slot_key 字串改名**（v4 migration `58a3d1cca6f1`，只改 label＋display_name，不動任何 tmu/index 值），對 v2 沒有對應的資料可複核，也沒有任何 TMU 影響。
3. **黃金值現在算得出來**：對 **live DB active rule set** 直接載入重算，`GM=28.0`、`CM=29.0`（PASS）；`scripts/core_logic/run_all.py` 全綠（60 引擎黃金 + 88 sequence + 26 level = 全通過）。

**因此 Phase 0 的「DB 複核」實質已完成（見本文附證據），差異已被證實或證偽，字典合併可直接以本文結論為基準進行，不需另開一個阻擋性前置階段。** 建議把本文的三項實查輸出直接當成 Phase 0 的驗收紀錄。

一句話：**該複核的已複核完，結果與 03 文件一致（M_PRESS 真、A2/A3 是 v4 命名非 v2 資料），golden 現況全綠；不必再為此開獨立 Phase 0 關卡。**

---

## 1. 背景與問題

`03-data-model-and-dictionary.md` §0.2 依 **JSON 對照**（v4 `app/data/minimost_ai_dictionary_v1.json` vs v2 `docs/v3/reference/minimost_ai_dictionary_v1.json`）宣稱兩項字典差異：

- v2 多一個 M 選項 `M_PRESS`（按壓 / fixed 3 TMU）。
- v2 把 CONTROLLED_MOVE 返回槽命名 `A2`，v4 已改名 `A3`（v4 migration `58a3d1cca6f1`）。

但 **v2 的現行權威是 DB 的 `rule_sets` 12 表**（seed 由 `scripts/import_v3_dictionary.py` 產生 `rule_set_seed_v2.py`，再入庫）。問題 C：JSON 對照的結論，在 seed 後的 DB **實表**是否成立？是否要先做一次 DB 實值複核才能安全合併字典？

---

## 2. 實查證據（live DB，port 15432，`ddm_v2_most`）

DB 內有兩個 rule set，active 的是 v2：

```
rule_sets:
  MINIMOST_FACTORY_V1  status=published  is_active=False
  MINIMOST_FACTORY_V2  status=published  is_active=True   ← active（單一權威）
```

`rule_*` 實際 14 張表（含 `rule_option_synonyms`）：
`rule_a_bands, rule_b_options, rule_g_actions, rule_i_options, rule_m_foot_bands, rule_m_hand_bands, rule_m_ladder_bands, rule_m_rotation_bands, rule_m_verbs, rule_option_synonyms, rule_p_addons, rule_p_bases, rule_sets, rule_x_options`。
（03 文件說「12 表」，指去掉版本頭 `rule_sets` 與衍生 `rule_option_synonyms` 後的 12 張規則子表；實表計數一致，無矛盾。）

### 2.1 M_PRESS —— DB 實表確認為真

live 查 `rule_m_verbs`（active rule set）按 `sort_order`：

```
MINIMOST_FACTORY_V2 verbs:
  m_btn      (fixed, 3)   sort 0
  m_screw    (fixed, 3)   sort 1
  m_li ... m_tearopen     (ladder)   sort 2..11
  m_rotate   (rotate)     sort 12
  m_press    按壓 (fixed, 3)  sort 13   ← M_PRESS 在此
  m_hand     (hand)       sort 14
  m_foot     (foot)       sort 15
```

對照 `MINIMOST_FACTORY_V1`：**沒有** `m_press`（只到 `m_foot` sort 14，共 15 verbs）。

模糊比對 `code ilike '%press%' or label ilike '%按壓%'` 只命中一列：
`{rs=MINIMOST_FACTORY_V2, code=m_press, label=按壓, pricing_kind=fixed, fixed_tmu=3}`。

seed 來源可回溯：`scripts/import_v3_dictionary.py` 的 `M_FIXED_MAP` 明列
`"M_PRESS": "m_press"  # v3 現場字典同步 2026-07-14（按壓 / fixed 3 TMU）`，
且 v2 reference JSON `docs/v3/reference/minimost_ai_dictionary_v1.json:1071` 確有 `"option_code": "M_PRESS"`；
v4 JSON `app/data/minimost_ai_dictionary_v1.json` **無**獨立 `"M_PRESS"`（只有 `M_PRESS_BUTTON`，:565）。

**結論**：M_PRESS 是 v2 現場字典（2026-07-14 同步）多出的一個 fixed 3 TMU 動詞，DB 實表已落地、v4 沒有。合併方向明確——**這是 v2 有、v4 缺的加項，v4→v2 合併時無需引入任何東西；反向（若要餵回 v4）才需補**。與 03 文件 JSON 判讀一致。

### 2.2 CM 返回槽 A2/A3 —— v2 DB 無此資料，純 v4 命名差異

v2 側查證：

- 全庫**沒有** `%slot%` / `%param%` / `%seq%` 的表（`information_schema` 查詢回 `NONE`）。v2 不存 slot_key。
- `rule_a_bands` 欄位僅：`id, rule_set_id, component, max_value, index_value, sort_order, is_active`——**無 slot_key 欄**。A 值以 `component`(reach/twist/foot) 分組（active 共 16 列：reach 7、twist 4、foot 5）。
- 引擎按**位置**消費 A：`most_engine/calculate.py:15-16`
  `GM_LETTERS = ("A","B","G","A","B","P","A")`、`CM_LETTERS = ("A","B","G","M","X","I","A")`——
  CM 的**返回距離是第 6 位（最後一個 A）**，靠位置索引而非字串 key。`calculate.py:6` docstring 註明「A3 僅 reach」是指第三個 A 位置只吃 reach 分量，屬引擎語義註解，非 DB 欄位。

v4 側查證：

- v4 有 `parameter_slots.slot_key`（`app/models/dictionary.py:60`：`# e.g. A1, B1, G, A2, B2, P, A3`）。
- migration `58a3d1cca6f1_cm_rename_a2_to_a3_return_slot.py` 的 `upgrade()` 只做：
  `UPDATE parameter_slots SET slot_key='A3', display_name_zh='距離(A)-返回' WHERE slot_key='A2' AND parameter_code='A'`，
  並同步改 `most_sequence_items` 的 `selected_slots_json` / `calculation_snapshot_json` 裡的 `"A2"→"A3"` 字串。
  **全程只改命名 key 與顯示名，未觸碰任何 tmu_value / index_value。**

**結論**：A2 vs A3 是 **v4 內部把「返回距離槽」的字串 key 對齊 GM 慣例（A1 取得／A2 移動／A3 返回）** 的純命名重構，零 TMU 影響。v2 根本不用 slot_key，因此**在 v2 DB 沒有任何可複核／可污染的對應資料**。整合時只需在 v4↔v2 映射層把 v4 的 `A3`（CM 返回）對到 v2 CM 第 6 位 A，無資料遷移風險。03 文件把此列為「差異」正確，但需澄清：**它不是 v2 DB 的值差異，而是 v4 的命名，v2 端無物可改**。

### 2.3 黃金值 GM=28 / CM=29 —— 現在算得出、全綠

（a）對 **live DB active rule set** 直接 `load_rule_set_from_db(s, "MINIMOST_FACTORY_V2")`（`most_engine/providers.py:166`）後 `compute_cycle` 重算：

```
[LIVE DB active rule set MINIMOST_FACTORY_V2]
  GM total_tmu = 28.0  (expect 28) -> PASS
  CM total_tmu = 29.0  (expect 29) -> PASS
  m_press in verbs: True  fixed_tmu=('fixed', 3)
```

（b）`scripts/core_logic/run_all.py` 全綠：

```
  most_engine golden (讀 DB 資料引擎): PASS — 引擎黃金/反例：60 passed, 0 failed
  MiniMOST Sequence Model (standalone spec): PASS — 88 passed, 0 failed
  Level System (standalone spec): PASS — 26 passed, 0 failed
  整體：✅ 全部通過
```

（c）seed 自我驗證（`rule_set_seed_v2.py::_self_check`）：`GM 黃金=28`、`CM 黃金=29（推 45cm=18 吋檔）` 等 10 項全 ✅。

**結論**：黃金值在 seed 值、DB 實表值、引擎重算三個層面一致鎖定為 GM=28/CM=29。M_PRESS 存在於 active rule set **不影響**黃金值（它是不參與 GM/CM 黃金案例的獨立 fixed 動詞）。

---

## 3. 對「字典合併」的意義（回答問題 C）

| 03 文件 JSON 判讀 | DB 實查結果 | 對合併的影響 | 是否需 Phase 0 阻擋 |
|---|---|---|---|
| v2 多 `M_PRESS`（fixed 3 TMU） | **真**：`rule_m_verbs` 有 `m_press`(fixed,3)，v1 無、v4 無 | v2→v2 無需動作；v4 無此項，合併不引入 | 否（已證實） |
| CM 返回槽 v2=A2 / v4=A3 | v2 **無 slot_key 資料**；A2/A3 是 v4 命名（migration 只改 key/顯示名） | 映射層把 v4 `A3` 對 v2 CM 第 6 位 A；零資料遷移 | 否（v2 無物可改） |
| 黃金值須維持 GM=28/CM=29 | live DB 重算 PASS；run_all 全綠 | 合併任何字典改動的驗收線就是這條 golden | 否（現況已綠，作為回歸基準） |

三項差異在 DB 實態均已釐清：兩項為「v2 有/命名對齊」而非「v2 DB 有錯待修」，一項（golden）現況即為合格基準。**沒有發現任何「JSON 說有、DB 實態卻不同」的隱藏落差**，也沒有需要在合併前先修的 DB 髒資料。

---

## 4. 建議

1. **不設獨立阻擋式 Phase 0「DB 複核」關卡**。理由：本文已完成該複核（§2 附實查輸出），差異全部證實/證偽，無隱藏落差。再開一個前置階段是重複工。
2. **把本文 §2 的三段實查輸出登記為 Phase 0 驗收紀錄**（等同「已做過 DB 複核」的證據存檔），供後續字典合併 PR 引用。
3. **合併時的唯一硬性驗收線**：任何字典/rule-set 改動後，`scripts/core_logic/run_all.py` 必須全綠、且 live DB 重算 GM=28/CM=29。此線已存在且現況通過，直接沿用即可（不需新建機制）。
4. **文件更正建議（給 03）**：把「CM 返回槽 A2 vs A3」的描述精確化為「**v4 端 slot_key 命名重構（migration `58a3d1cca6f1`，無 TMU 影響）；v2 不使用 slot_key，返回距離由引擎位置（CM 第 6 位 A）承載，故 v2 DB 無對應差異可改**」，避免被誤讀為 v2 有值需修。
5. **合併方向落地（不搬 code、在 v2 架構重寫的前提下）**：
   - M_PRESS：v2 已有 `m_press`，無動作；若日後要與 v4 對齊，屬 v4 缺項而非 v2。
   - A 返回槽：在 v4↔v2 的字典/序列映射層維護對照（v4 `A3`(CM) → v2 CM 位置 6），i18n 文案走 ADR-032 `_zh`/`_en`；不引入 v4 的 slot_key 表到 v2（維持 v2 位置式引擎，TMU 單一權威不受污染）。

---

## 5. 附錄：本次實查方法

- DB 連線：`postgresql+asyncpg://howard:111111@localhost:15432/ddm_v2_most`（無 psql，改用 venv `asyncpg` / SQLAlchemy async）。
- 查詢對象：`rule_sets`、`rule_m_verbs`（全 rule set）、`rule_a_bands`、`information_schema`（確認無 slot_key 表/欄）。
- 黃金重算：`load_rule_set_from_db("MINIMOST_FACTORY_V2")` + `compute_cycle`（GM/CM 黃金 DTO 同 seed self-check）。
- 交叉比對檔：
  - v2 seed 轉換器 `scripts/import_v3_dictionary.py`（`M_FIXED_MAP["M_PRESS"]="m_press"`）。
  - v2 引擎 `src/ddm_v2/most_engine/calculate.py:6,15-16`（位置式 A、CM_LETTERS）。
  - v2 DB provider `src/ddm_v2/most_engine/providers.py:166`（`load_rule_set_from_db`）。
  - v4 `app/models/dictionary.py:60`（slot_key）、`alembic/versions/58a3d1cca6f1_*.py`（A2→A3 純命名）、`app/data/minimost_ai_dictionary_v1.json`（無獨立 M_PRESS）。
- 唯讀：未修改任何 v2/v4 程式碼或 DB 資料；臨時查詢腳本已刪除。
