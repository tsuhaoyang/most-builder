# ADR-028: most_engine 邊界驗證加嚴與單一計算權威收斂

**狀態：** proposed
**日期：** 2026-08-11
**關聯：** [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（契約穩定與加法演進）、
[ADR-014](ADR-014-v3-dictionary-as-value-authority.md)（值權威、X 捨入由 ceil 改 half-up）、
[ADR-020](ADR-020-simo-contribution-semantics.md)（SIMO 貢獻語意）、
[ADR-023](ADR-023-dictionary-governance-unification.md)（§3.4 回放鐵則、§3.5 schema 層不得持有值權威）、
[ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md)（AI 輸出必須過 `compute_cycle`）、
[ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md)（版本軸與 policy manifest）、
[引擎與 legacy 稽核](../architecture/legacy-inventory-and-engine-audit.md)（§7.1／§7.2 為本 ADR 的事實基礎）、
[MiniMOST 核心邏輯規格](../core-logic/minimost-sequence-model-core-logic-spec.md)、
[CI 驗證關卡](../CI_GATES.md)

## 脈絡

`most_engine/` 目前是乾淨的：沒有任何 V1/V2 版本分支，五處版本行為差異全部由 rule-set
資料承載，AI 那批（L0–L4／R1–R3b）沒有動過引擎。黃金驗證器 167 項全綠。

但稽核（§7.1／§7.2）指出兩類問題，且本次已逐條實測複驗（`build_from_seed_v2()` +
`compute_cycle`，2026-08-11）：

**A 類：靜默 fallback，違反 CLAUDE.md「No error bypass」硬規則。**

| 輸入 | 實測結果 | 位置 | 對照 |
|---|---|---|---|
| M 分量 `distance_cm=-5` | **0.0，不報錯** | `rule_set_data.py:67` | A 格位有 `A_NEGATIVE`（`calculate.py:68-71`） |
| M 分量 `angle_deg=-30` | **0.0，不報錯** | `rule_set_data.py:95` | 同上 |
| 旋轉 `revolutions=99` / `0` / `2.6` | **42 / 16 / 42**，靜默夾到 1–3 圈 | `rule_set_data.py:87` | M 距離超表會報 `M_DISTANCE_RANGE` |
| A `twist_deg=9999`（twist 無 overflow 帶） | **6**，靜默夾到最後一檔 | `rule_set_data.py:63` | `hand_tmu` 超表回 `None` → `M_HAND_RANGE` |
| GM slot0 夾帶 `m_components`+`x_code` | **靜默忽略外來鍵**，只算 reach | `calculate.py:247-248` 只守 slot 3/4/5 | slot 3/4/5 有 `SLOT_CROSS_MODEL` |
| m_components 含無 `verb_code` 的分量 | **靜默略過** | `calculate.py:152-153` | — |
| **`compute_cycle(json.loads(json.dumps(cycle)))`** | **28.0 → 0.0，不報錯** | `calculate.py:240-241` | — |

最後一列是本次新發現、也是最危險的一條：`slots` 用 int 鍵，JSON 往返後變字串鍵，
`s.get(i)` 全部 miss → 每個格位變空 dict → 整條 cycle 靜默算成 0 且 `tech_line` 是
`A0 B0 G0 A0 B0 P0 A0`。任何直接讀 `most_cycles.slot_inputs` 再丟進引擎的修補腳本、
批次 worker 或 AI 消費端都會踩到，而它回傳的是一個看起來合理的數字。

另有錯誤契約不一致：`calculate.py:200` 拋裸 `ValueError`，繞過所有 `except SequenceError`
處理器 → 500 而非 422。

**B 類：第二套計算權威，且已漂移。**
`seed/v2/rule_set_seed.py:120-208` 有一份完整的引擎副本供該檔自我驗證。實測分叉四處：

| 檢查 | 重複實作 | 真引擎 |
|---|---|---|
| `X 10s` | **278**（`math.ceil`，:194-195） | **277.778**（ROUND_HALF_UP） |
| `_ladder(0)` / `_ladder(-5)` | **3** | **0** |
| 旋轉 `revolutions=2.6` | **StopIteration 裸崩**（:183 未取整） | 42 |
| ladder 超表且無 overflow 帶 | 夾最後一檔（:165） | `M_DISTANCE_RANGE` |

（第四項在 V1 資料下不可達——V1 `M_LADDER` 有 overflow 帶 `(None, 42)`；前三項是活的。）
兩邊各自綠燈。對照組是 `rule_set_seed_v2.py:211`，它 `from ddm_v2.most_engine import
compute_cycle`，不自己算。

**為什麼現在處理：** 人工點 UI 幾乎產不出這些輸入（旋轉圈數是 1/2/3 下拉、M 距離是
預設清單、A 格位由帶別下拉），但 ADR-026 的 AI parser 與批次匯入會**持續**產生它們。
今天每一條都回傳一個看起來合理的數字，而黃金錨依然全綠——這是「AI 算錯了我們抓到」
與「AI 算錯了但沒人發現」的差別。

## 決策提案

### 1. 驗證責任分三層，每層有唯一權威；引擎不設 `strict` 旗標

| 層 | 權威範圍 | 失敗形式 |
|---|---|---|
| 契約層 `schemas/v2/most.py` | **形狀**：未知欄位、型別 | Pydantic 422（`extra="forbid"`） |
| 引擎層 `most_engine/` | **語意與值域**：輸入能不能被 rule-set 資料解釋 | `SequenceError(code)` → 422 |
| 寫入／發布閘門 | **完整性與可信度**：空白占位列、rule-set 表缺陷 | publish issue／409 |

引擎恆一致：**同一份輸入 + 同一個 rule-set，永遠得到同一個結果或同一個錯誤**。
不接受 `compute_cycle(..., strict=True)`（理由見〈考慮過的選項〉B）。

### 2. 加嚴判準：rule-set 資料能不能解釋這個輸入

依此把每個靜默點分成三類，**不逐條憑感覺裁決**。

**A 類——無條件加嚴（語意上不存在正確答案，舊行為回傳的數字本來就是錯的）**

| # | 規則 | 錯誤碼 | 今天的行為 |
|---|---|---|---|
| A1 | M 分量 `distance_cm` / `angle_deg` / `diameter_cm` < 0 | `M_NEGATIVE` | 0 |
| A2 | 旋轉圈數非整數，或不在該 rule-set `m_rotation` 的圈數集合內 | `M_ROTATION_RANGE`（沿用） | 夾到 1–3 |
| A3 | A 分量超出帶表且該分量**無 overflow 帶** | `A_BAND_RANGE` | 夾最後一檔 |
| A4 | 格位出現不屬於該格位模型的鍵（擴及 slot 0/1/2/6） | `SLOT_CROSS_MODEL`（沿用） | 靜默忽略 |
| A5 | `slots` 出現非 `0..6` 的整數鍵（含字串鍵） | `SLOT_KEY_INVALID`（新增） | 整條算 0 |
| A6 | `m_components` 內出現無 `verb_code` 的分量（空 list 仍合法） | `M_VERB_REQUIRED`（新增） | 靜默略過 |
| A7 | X 選項 `mode='fixed'` 但 `fixed_seconds` 為 NULL | `X_FIXED_SECONDS_MISSING`（新增） | 裸 `ValueError` → 500 |
| A8 | M 格含 `pricing_kind` ∈ {`hand`,`foot`} 的分量，卻無任何動詞分量（`ladder`/`fixed`/`rotate`） | `M_COMPANION_WITHOUT_VERB`（新增） | 照算，通常是 0 TMU 且產出假敘事 |

A1 加在 `calculate.py::_m_tmu`（與 `_a_tmu` 的 `A_NEGATIVE` 對稱），**不加在查表 helper**
——`rule_set_data.py` 的 helper 維持「純查表」定位（`0` 仍代表未使用該分量，是合法輸入）。
A2 的多圈需求以既有 `repeat_count` 表達，不靠夾取。
A3 是**資料驅動**的：reach 有 overflow 帶（`(None, 24)`）→ 9999cm 仍合法回 24；twist 沒有
overflow 帶 → 9999° 報錯。加嚴的是「無帶可查時不得偷用最後一檔」，不是「一律報錯」。

**A8（2026-08-19 補入，User 裁決；已實作於 `calculate.py::_m_tmu`）**
依據＝IE 認證字典 `parameters.M.controls`：`verb`(**required=true**)／`hand_degree`／`foot_step`
是三個**平行控制群**，`slot_definitions.M.calculation = max(verb_tmu, hand_degree_tmu, foot_step_tmu)`。
根因是 v2 把這三群**壓扁**成單一 `rule_m_verbs` 清單、用 `pricing_kind` 當判別欄，於是
`m_hand`／`m_foot` 在 payload 與下拉裡長得像替代動詞、可以被單獨選取——字典的 `required=true`
在 v2 沒有任何東西承載它。加嚴等於把它補回來，不是新增規則。

- 只擋「有伴隨維度但沒有動詞」。伴隨維度**與動詞併用完全合法**（黃金測試有 4 處正當案例：
  `m_li`+手度180、`m_push`×3+手度180 等），加嚴後全部照舊通過。
- `m_components: []`（M0）仍然合法：M 格空著代表沒有受控移動，不是缺動詞。
- **排序**：本檢查排在逐分量值域檢查（`M_HAND_RANGE`／`M_DISTANCE_RANGE`／`M_ROTATION_RANGE`）
  **之後**。反過來會讓「單獨一顆 181° 手度」報成 `M_COMPANION_WITHOUT_VERB`，
  `M_HAND_RANGE` 在單分量輸入上從此無法出現（黃金反例正是這個形狀）。
  實測反序 mutant：engine golden **59 passed / 1 failed**（死的就是「手度 181° 超界」），
  且順帶遮掉 `M_UNKNOWN`（`m_zzz` ＋ `m_hand(90)` 報成缺動詞）。多分量輸入不受順序影響
  （`m_push(10)` ＋ `m_hand(181)` 兩種順序都報 `M_HAND_RANGE`），所以能被順序改寫的
  只有單分量那一類——`calculate.py::_m_tmu` 的錨點註解與本節同步。
- 加嚴前掃描（決策 4 的紀律）2026-08-19 實測：`most_cycles` 60 筆命中 **2**、
  `motion_module_versions` 42 筆命中 **0**、`motion_templates` 16 筆命中 **1**（掃描範圍另含
  `ai_parse_runs.drafts` 7 筆 0 命中、`excel_imports.staged_rows`／`import_rows`／
  `wi_row_contexts` 皆 0 筆）。遠低於〈重評訊號〉的 1% 門檻。
  範本那 1 筆由 migration **v2_0042** 清除（M 格改空，TMU 恆等）；`most_cycles` 那 2 筆
  依 ADR-023 §3.4 **不動**（讀取走 `total_tmu` 快取不重算；下次整份存檔才會 422）。
  另有 **`workflow_audit_log.payload`：80 列命中**——列出來只為了「掃過、有命中、
  但無風險」的完整性：那是**不可變的稽核歷史**，永不重算、不進任何計算路徑，
  不需要也不應該被修補（改它等於竄改留痕）。
- **歷史 companion-only cycle 的重算預期就是 422，包含 V1-pinned 的列。** 這條新拒絕寫在
  **引擎程式碼**裡、判準是 `pricing_kind` 這個結構欄，不是 rule-set 的值資料——所以
  `rule_set_id` 指向 V1 的 cycle 一樣被拒（實測 V1 rule-set 也拒）。
  ADR-023 §3.4 的明文禁令是「**載入不得看版本治理狀態**（retired 仍可載入、仍算原值）」，
  這裡沒有違反它；但常被連帶推論的那句「舊資料＋舊規則＝舊行為」，現在只對**讀取**成立、
  對**重算**不成立。把這個後果寫死在這裡，不要留給讀者自己推導。
- 對應的敘事排除規則（同一批落地）見 ADR-032。

**B 類——刻意保留寬鬆（資料承載的語意，回放必需；須以測試釘死並在 code 註明「這是決策不是疏漏」）**

| # | 行為 | 為何不是 bypass |
|---|---|---|
| B1 | G `requires_modifier` 未滿足 → 0 | V1 字典語意（動作未完成）；V2 資料全關。差異由資料承載 |
| B2 | P addon `needs_precision` 未滿足 → 略過 | 同上 |
| B3 | `m_foot` 空表 → 回退 ladder | V1 無獨立腳步帶（E9）；由 rule-set 資料決定，非執行期猜測 |
| B4 | 無 `b_code` 且無 `b_default` → 0 | 「未選 B ＝ 無身體動作 ＝ 0」是 MOST 正解。但「B 表沒有 default」是 rule-set 缺陷 → 移到 C 類 |
| B5 | 距離／角度為 0 或未填 → 0 | 未使用該分量 |
| B6 | `slots` 缺鍵 → 視為空 dict → 0 | **API 路徑不可能發生**：`cycle_in_to_engine` 一律具體化 7 格。改成錯誤只會打到測試與 seed 自檢，換不到任何生產保護 |

**C 類——移出引擎（引擎沒有資訊可以判斷）**

- **空白占位列／全 0 cycle**：`CycleIn` 每個欄位都有預設值，`cycle_in_to_engine` 把 7 格
  全部具體化 → 「使用者沒碰過這格」與「使用者填了 0」在引擎看到的位元層**完全相同**。
  這是先例 `Pipeline-Step-Order-Determines-Validation-Unit` 的同型問題：驗證要放在還看得到
  那個資訊的步驟。裁決：由 publish gate 產生 `EMPTY_CYCLE_ROW` issue（**不阻擋存檔**），
  引擎不介入。
- **rule-set 資料缺陷**：B 表無 `is_default`、X `mode='fixed'` 但 `fixed_seconds` NULL 等
  → 併入 `RuleSetData.validate_complete()`，發布時 409 `RULE_SET_INCOMPLETE`。

### 3. 回放鐵則的正確界定：讀取不重算，被打到的只有「重算」路徑

必須修正一個會導致錯誤結論的誤解。ADR-023 §3.4 的鐵則保護的是「**版本治理狀態不得滲進
載入路徑**」（retired 版本仍可載入、仍算出原值），它並未承諾「引擎的輸入合法性判準永不改變」。

已驗證的重算範圍：

- `read_worksheet()` 回傳 `most_cycles.total_tmu` **快取欄，不重算** → 已發布工時表的數字、
  匯出、LB 輸出、Level 都不受任何加嚴影響。
- 會重算的只有：`PUT /worksheets/{id}`（整份取代、**全列重算**）、匯入 commit、
  `POST /minimost/calculate`、模組實體化、`backfill_module_totals.py`。

所以加嚴的真實爆炸半徑是：**含有不合規舊列的工序表，下次存檔會整份 422**（整份取代語意
＝一列毒死整表），而不是「已發布的工時表再也算不出當初的數字」。這比原先的擔憂窄，
但比「只影響新資料」寬——因此必須用資料掃描確認，不能靠推測。

### 4. 加嚴的前置條件：資料掃描 + 一次性修補，不用寬鬆模式當退路

新增 `scripts/audit_slot_inputs.py`：

- 掃描 `most_cycles.slot_inputs`、`motion_module_versions.rows[].cycle`、
  `motion_templates.cycle_template`、`excel_imports.staged_rows`（及 ADR-027 §6 的 `import_rows`）。
- 每筆以**新規則**試算，輸出：命中規則、實體 id、原 `total_tmu`、新結果或錯誤碼。
- 有命中 → exit code 非 0。
- **這支腳本必須有自己的單元測試，且測試要含正向對照**：合成每一條 A 類規則的違規 payload，
  斷言偵測器真的紅。本機 dev DB 目前 0 筆 cycle，這支腳本在本機必然綠——
  **本機綠燈不構成任何證據**（先例：`Always-True-Assertion-Detector-Self-Disable` 型二，
  「差集守門的待驗集合是空的」）。
- 部署順序硬性規定：**正式環境掃描綠 → 才可部署加嚴版本**。有命中則先做一次性資料修補
  migration，把原 `slot_inputs` 與原 `total_tmu` 抄進 ~~`workflow_audit_log`（或 ADR-027 R3 的
  review event）~~ 留痕後再改值。
  > ⚠️ **上面刪除線那兩個去處都寫錯了，實測都寫不進去**（`workflow_audit_log` 的
  > `entity_type` CHECK allow-list 沒有 `most_cycle`；`ai_review_events` 是
  > `ON DELETE CASCADE`）。**留痕落在哪張表由 User 裁決，見〈不由本 ADR 決定〉#9。**
  > 在裁決下來之前，**不要自行挑一張表塞進去**——本 ADR 的位階高於 `--help`，
  > 照這行指標走過去的人讀到的必須是「待裁決」，不是一份會失敗或會被 CASCADE 刪掉的做法。

### 5. `calculate.py:200`：改拋 `SequenceError("X_FIXED_SECONDS_MISSING", ...)`，並在發布期先擋

雙層處置：發布期由 `validate_complete()` 擋（409，讓這種 rule-set 根本發不出去）＋執行期以
`SequenceError` 表達（422，與引擎其他錯誤同一契約）。
命名沿用既有構詞（格位字母 + 問題）：`X_NEGATIVE` / `X_SECONDS_REQUIRED` / `M_DISTANCE_RANGE`
→ `X_FIXED_SECONDS_MISSING`。

### 6. 刪除重複實作；`X 10S → 278` 是**已被 ADR-014 取代的期望值**，不是 V1 語意

查證結論（三個獨立證據）：

1. 舊裁決 Q3（`ceil(sec/0.036)`）寫在 `minimost-sequence-model-core-logic-spec.md:402`，
   **已由同檔 §E2 標記 superseded**；ADR-014 明文：「X 捨入（ceil→half-up）屬引擎行為變更、
   **全域生效**，但歷史 `computed` 快取不重算，回放差異 ≤1 TMU 且有 V1 回放測試守護」。
2. 結構事實：`seconds_to_tmu()` 是 `RuleSetData` 的 `@staticmethod`——**捨入規則不由 rule-set
   資料承載**。實測 `build_from_seed().seconds_to_tmu(10) == 277.778`：今天用 V1 rule-set 回放，
   引擎**早就**是 half-up。V1 seed 自檢的 278 驗的是一份已不存在的實作。
3. 影響面：所有 V1 回放斷言（`tests/integration/test_rule_set_replay_isolation.py`、
   `scripts/core_logic/engine_golden_test.py` §L、`tests/unit/test_most_engine.py::test_v1_replay_*`）
   一律使用 `x_none`（X=0），**沒有任何一條 V1 回放斷言碰到秒數換算** → 改期望值不動現有綠燈。

裁決：`_band_index` / `_a_tmu` / `_g_tmu` / `_p_tmu` / `_ladder` / `_m_tmu` / `_x_tmu` / `_i_tmu`
全部刪除，`_self_check()` 改成 `rule_set_seed_v2.py:211` 的形狀（`build_from_seed()` +
`compute_cycle`），`X 10S` 期望值改為 **277.778**。
先例 `RCPSP-Single-Solver-Authority`：同一業務規則兩份獨立實作、兩邊各自綠燈，是「數字通常
一致偶爾不一致」的前兆；這裡已經不是前兆，已實測分叉。

連帶文件更新（同批）：`core-logic-validation-test-catalog.md` §G、§3.1、§3.3（R116 合計
300 → 299.778）需標註 superseded，否則文件會反過來成為「第三套權威」。

### 7. 執行順序（不可顛倒）

1. 掃描腳本 + 其正向對照測試（**不改引擎**）
2. 正式環境掃描報告 → User 核可
3. 刪除重複實作（純刪除、零行為變更，先做可縮小後續 diff 的判讀成本）
4. schema `extra="forbid"` + 引擎 A 類加嚴 + 錯誤碼
5. publish gate 的 C 類檢查
6. 文件（spec / test catalog / CI_GATES）與前端錯誤文案同批更新

## 考慮過的選項

### A. 無條件加嚴，引擎恆 loud（提案採用）

單一行為、可稽核、與「引擎零版本分支」的現狀一致。代價是必須先做資料掃描與可能的一次性
修補（決策 4／7 即為此配套）。

### B. `compute_cycle(..., strict=True)` 雙模式，寫入路徑嚴格／回放路徑寬鬆

否決，四個理由：

1. 引擎今天的乾淨性正是來自「零版本分支」。`strict` 會把第一個分支帶回引擎，而且是
   **不由資料承載**的分支——與 ADR-014／ADR-023「V1/V2 差異全由資料承載」直接衝突。
2. 呼叫端今天有 5 處且只會變多。任何一處忘了傳 `strict`，保證就消失；而且**資料裡不會留下
   當初用哪個模式算的痕跡**，事後無法稽核——一個無法被否證的保證等於沒有保證。
3. 「寬鬆模式」保住的是一個我們已經判定為錯的夾取值，等於用架構複雜度換一個錯數字的延壽。
4. 真正需要保護的「已發布數字」根本不走重算路徑（決策 3）。這個旗標保護的是一個不存在的風險。

### C. 只在 Pydantic schema（`schemas/v2/most.py`）擋，不動引擎

否決，四個理由：

1. **值域規則多半依賴 rule-set 資料**（哪些圈數存在、A 帶有沒有 overflow）。ADR-023 §3.5 已
   明文「Pydantic 層沒有 session，不該持有值權威」，把這些搬到 schema 就是重犯 V1/V2 分裂的
   機械成因。
2. `revolutions` 只有在動詞是 rotate 時才有意義，而 `MComponent` 是扁平結構；schema 層一律
   `ge=1, le=3` 會誤殺 ladder／hand 分量帶的無害預設值。
3. **非 API 呼叫者不經 schema**：scripts、seed 自我驗證、未來 batch worker、任何直接讀
   `slot_inputs` 的修補腳本。保護只覆蓋一條路徑——先例
   `RCPSP-Silent-Fallback-Upstream-Validated` 正是「第三個入口沒驗，於是 `except: pass` 掩蓋了
   真實 bug」。
4. **反序列化風險確實存在但不在讀取路徑**：`read_worksheet()` 直接回原始 JSON、不經 `CycleIn`，
   但前端 load→save 往返**會**再進 `CycleIn`。`extra="forbid"` 只有在「`CycleIn` 從未刪過欄位」
   時才安全——這要由決策 4 的掃描證實（掃描項目之一即為「歷史 `slot_inputs` 的鍵集合是否
   為現行 schema 的子集」）。

因此 schema 層只承擔**形狀**（`extra="forbid"`），值域留在引擎——各層一個權威，不重疊。

### D. 維持現狀，只寫文件

否決。人工 UI 幾乎產不出這些輸入，但 ADR-026 的 AI parser 與批次匯入會持續產生；
黃金錨全綠不等於邊界安全（167 項驗的都是合法輸入）。

## 驗收斷言清單

每條決策對應至少一條可機械驗證的斷言；「今天」欄是實測的現行值，用來確認斷言真的有鑑別力。

**引擎加嚴（`tests/unit/test_most_engine.py`）**

| # | 斷言 | 今天 |
|---|---|---|
| 1 | M 分量 `distance_cm=-5` → `SequenceError.code == "M_NEGATIVE"` | 0.0 |
| 2 | M 分量 `angle_deg=-30` → `M_NEGATIVE` | 0.0 |
| 3 | rotate `diameter_cm=-1` → `M_NEGATIVE` | 16 |
| 4 | rotate `revolutions=99` → `M_ROTATION_RANGE` | 42.0 |
| 5 | rotate `revolutions=0` → `M_ROTATION_RANGE` | 16 |
| 6 | rotate `revolutions=2.6` → `M_ROTATION_RANGE` | 42 |
| 7 | A `twist_deg=9999`（twist 無 overflow 帶）→ `A_BAND_RANGE` | 6 |
| 8 | GM slot0 夾帶 `m_components` → `SLOT_CROSS_MODEL` | 靜默忽略 |
| 9 | `compute_cycle(json.loads(json.dumps(gm_gold)), rs)` → `SLOT_KEY_INVALID` | **0.0** |
| 10 | `slots={7: {}}` → `SLOT_KEY_INVALID` | 0.0 |
| 11 | `m_components=[{"distance_cm": 45}]`（無 verb_code）→ `M_VERB_REQUIRED` | 靜默略過 |
| 12 | X `mode='fixed'` 且 `fixed_seconds=None` → `SequenceError.code == "X_FIXED_SECONDS_MISSING"`，且 `POST /minimost/calculate` 回 **422 不是 500** | 裸 ValueError → 500 |
| 12a | M 只有 `m_hand`／`m_foot`（單獨或兩者併用）→ `M_COMPANION_WITHOUT_VERB`，且 `POST /minimost/calculate` 回 **422**（✅ 已實作） | 照算 0 TMU |
| 12b | 只有一顆 **181°** 手度 → 仍報 `M_HAND_RANGE`（排序鎖，✅ 已實作） | `M_HAND_RANGE` |

**不得過度加嚴（正向對照；缺這段就無法證明加嚴是資料驅動而非一律報錯）**

| # | 斷言 | 今天 |
|---|---|---|
| 13 | A `reach_cm=9999`（reach **有** overflow 帶）→ 24，不報錯 | 24 |
| 14 | rotate `diameter_cm=10, revolutions=2` → 32 | 32 |
| 15 | `m_components=[]` → slot3 = 0，不報錯 | 0 |
| 15a | 動詞＋手度／腳步併用 → 照 max 計算，不報錯（ladder/fixed/rotate 各一，✅ 已實作） | 照 max |
| 16 | `distance_cm=0` → 0，不報錯 | 0 |
| 17 | GM slot2 帶 `modifiers` 鍵 → 合法（G 的允許鍵集合必須含 `modifiers`） | 合法 |
| 18 | GM slot6 帶 `twist_deg=0, foot_cm=0` → 合法（`ASlot.model_dump()` 恆含這兩鍵） | 合法 |
| 19 | `compute_cycle({"seq": "GM"}, rs).total_tmu == 0.0`（缺格位仍合法，B6） | 0.0 |

**回放不變（B 類鎖）**

| # | 斷言 | 今天 |
|---|---|---|
| 20 | V1：`g_touch` 未勾 `contact` → slot2 = 0（不得變成錯誤） | 0 |
| 21 | V1：`p_place_single + a_align` 未勾 precision → 16 | 16 |
| 22 | V1：`foot_tmu(30) == 24`（`m_foot` 空 → 回退 ladder） | 24 |
| 23 | 黃金錨不漂移：V2 GM=28／CM=29（推 45cm）、V1 GM=28／CM=29（推 18cm） | 綠 |
| 24 | `test_rule_set_replay_isolation.py` 全綠、`run_all.py` 167 項全綠 | 綠 |

**契約層與閘門**

| # | 斷言 | 今天 |
|---|---|---|
| 25 | `CycleIn` 收到未知欄位（例如把 `reach_cm` 打成 `reach`）→ 422 | 靜默丟棄 |
| 26 | rule-set 的 B 表無 `is_default` → publish 409 `RULE_SET_INCOMPLETE` | 執行期靜默計 0 |
| 27 | rule-set 有 `mode='fixed'` 但 `fixed_seconds` NULL 的 X 選項 → publish 409 | 執行期 500 |
| 28 | 全 0 cycle 列 → publish gate 出 `EMPTY_CYCLE_ROW` issue，且 `PUT /worksheets` 仍 200 | 無此 issue |

**單一權威**

| # | 斷言 | 今天 |
|---|---|---|
| 29 | `grep -rnE "def _(band_index|a_tmu|g_tmu|p_tmu|ladder|m_tmu|x_tmu|i_tmu)" src/ddm_v2/seed/` → **零命中** | 8 個命中 |
| 30 | `grep -rn "math.ceil" src/ddm_v2/` → TMU 換算路徑零命中 | `rule_set_seed.py:194-195` |
| 31 | `rule_set_seed.py::_self_check()` 走 `compute_cycle`，`X 10s` 期望 **277.778**，GM=28／CM=29 仍綠 | 278（另一套實作） |

**資料掃描**

| # | 斷言 | 今天 |
|---|---|---|
| 32 | `audit_slot_inputs.py` 對 A1–A7 各一筆合成違規 payload → exit 非 0 且回報正確規則名（偵測器正向對照） | 腳本不存在 |
| 33 | 掃描項目含「歷史 `slot_inputs` 的鍵集合 ⊆ 現行 `CycleIn` 鍵集合」（決策 C-4 的前提檢查） | 未檢查 |
| 34 | 對正式環境全量資料 exit 0——**這是部署加嚴版本的放行條件，不是 CI 條件** | 未執行 |

## 後果

### 好處

- 引擎對「AI／匯入產生的髒輸入」從「回一個看起來合理的數字」改成「明確拒絕並附錯誤碼」，
  ADR-026 的 `engine_gate` 得以真正發揮 gate 作用（它已經在接 `SequenceError` 並轉成
  `engine_reject_*` issue，只是目前多數髒輸入根本不會拋）。
- 消滅 JSON 往返靜默算 0 的地雷——這是未來批次 worker／修補腳本最可能踩到的一條。
- 計算權威收斂為一份；seed 自我驗證從「驗自己」變成「驗引擎」，不可能再各自綠燈。
- 加嚴判準（「rule-set 資料能不能解釋」）是可複用的規則，後續新增格位時不必重新爭論。

### 代價

- 含不合規舊列的工序表，下次存檔會整份 422，需要一次性資料修補批次（決策 4）。
- 新錯誤碼需要前端中文文案，否則使用者看到裸 code（ADR-021 的 UX 母版須補）。
- `core-logic-validation-test-catalog.md` 的 278／300 期望值要改，過渡期會出現「文件與測試
  對不上」的短暫不一致，必須同批處理。
- `validate_complete()` 加嚴後，既有 draft rule-set 可能無法發布，需人工補資料。
- 掃描腳本必須跑在正式環境（本機 0 筆），流程上多一道人工放行關卡。

### 重評訊號

- 掃描在正式環境命中大量列（>1% 的 cycle）：代表髒資料是常態而非例外，A2／A6 應退回
  B 類並改由匯入層正規化，本 ADR 的「無條件」需重議。
- 出現 V1 時代、且 X `mode='seconds'` 的已發布資料，且客戶對 ≤1 TMU 的差異提出異議：
  代表捨入規則應該升為 rule-set 資料欄位（讓 V1 的 ceil 可回放），推翻 ADR-014 的全域裁決。

## 不由本 ADR 決定

1. `revolutions > 3` 的正確 IE 建模方式（`repeat_count` 或拆多分量）——需 IE 拍板；
   本 ADR 只決定「不得靜默夾取」。
2. `_REPEAT_MAX = 99` 的最終上限（`calculate.py:47` 殘項#4）。
3. 捨入規則是否升為 rule-set 資料欄位（見〈重評訊號〉）。
4. `EMPTY_CYCLE_ROW` 是 blocking 還是 warning、以及要不要納入 ADR-027 的 level policy
   manifest 版本軸。
5. 「哪些列可以合法為 0 TMU」的業務定義。
6. 新錯誤碼的前端 i18n 文案與 Phase 5 雙語計畫的關係。
7. 加嚴後是否重算 `most_cycles.computed` 快取——本 ADR 預設**不重算**（沿用 ADR-014 對 X
   捨入變更的同一處置）。
8. **`ai_parse_runs.drafts[].cycle` 的加嚴後處置**。`scripts/audit_slot_inputs.py` 另掃這一處，
   但**只列為指標、不列入放行條件**（不進 exit code），理由：草稿是**尚未被採用**的建議，
   不會被原樣重存回 `most_cycles`；被採用時會重新過 `CycleIn` + `compute_cycle`
   （`most_compiler/engine_gate.py`），屆時被加嚴版本擋下**正是預期行為**（ADR-026 的
   engine_gate 即為此存在）。該數字回答的是「加嚴後有多少 AI 草稿會開始被拒」——決定要不要
   加嚴時想知道的觀測值，不是阻擋部署的理由。因未改變閘門語意，此項不需重新核可本 ADR。
   附帶：掃描腳本把 **S2**（payload 連現行 `CycleIn` 都驗不過）列為 WARN 而非 BLOCK，
   同理——那種列**今天就已經會 422**，不是加嚴造成的；閘門要量的是加嚴帶來的**差值**。
   S1（斷言 #33）維持 BLOCK，那是本 ADR 明文授權的放行條件。
9. **一次性資料修補的「原值留痕」要落在哪張表**（§4 末段的 ⚠️ 指向此項）。
   本 ADR §4 原文寫的兩個去處**經實測都不可用**，這是 ADR 層級的缺陷，不由實作端自行選表：

   | 候選 | 實測結論 |
   |---|---|
   | `workflow_audit_log` | **寫不進去**。`entity_type` 的 CHECK allow-list 是 `{process_version, motion_module, rule_set, motion_template}`（`migrations/versions_v2/v2_0017_workflow_audit.py:33`），**沒有 `most_cycle`**。 |
   | `ai_review_events`（ADR-027 R3 的 review event） | **不可用**。`run_id` 是 `ON DELETE CASCADE`（`models/v2/ai_ops.py:124-128`）：parse run 一被刪，稽核軌跡跟著消失。而修補留痕的整個意義就是它必須活得比來源久。 |
   | 兩者共通 | ADR-027 §69 與 `domain-evolution-and-ai-readiness-spec.md`（:74／:500）都明文「`workflow_audit_log` **只承載低頻 workflow transition**」。把逐列的資料修補塞進去，與該裁決衝突。 |

   可能的方向（**本 ADR 不選**，僅供裁決時參考）：修補 migration 自帶一張一次性快照表、
   放寬 `workflow_audit_log` 的 allow-list、或另立資料修補專用的留痕表。
   在裁決下來之前，`scripts/audit_slot_inputs.py` 的 runbook 第 5 步與報告結論都只寫
   「待裁決、不要自行挑表」，不預設任何一種做法。
