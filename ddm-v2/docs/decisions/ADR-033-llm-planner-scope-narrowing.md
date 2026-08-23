# ADR-033: WI AI Parser 的 LLM 職責收窄——只做語意分段與角色片語，不產任何數值

**狀態：** **accepted**（User 2026-08-23 核可）
**核可範圍：** D1–D7 全部；§7 的七個未決問題**全數裁決完畢**（U-1 走 IE 親筆／U-2·U-3 現階段
不做延後另案／U-4 左至右指派可採用／U-5 返回起點／U-6 證據已入版控 `3d01f61`／U-7 設觀察期）。
⚠️ **核可不等於已實作**——遷移路徑 §5 的 P0–P5 逐階段推進、**不得跳階**；P3 動 TMU 路徑，
上線前必須確認 `DDM_WI_AI_AUTO_ENABLED` 仍為 false。
**日期：** 2026-08-23
**裁決來源：** User 2026-08-23（逐字見 §1.1；三點確認見 §1.2）
**關聯：**
[ADR-026](ADR-026-wi-ai-parser-pipeline-boundary.md) §2（AI 輸出 MOST-neutral plan、deterministic compiler 保留權威
——本 ADR 是它的**收緊**，不是修訂）、
[ADR-015](ADR-015-nl-parsing-in-scope.md)（NL 解析＝建議層隔離，輸出永遠是建議）、
[ADR-031](ADR-031-spatial-layout-and-distance-acquisition.md) D3／D4／D7（站內佈局產生帶出處的距離
——本 ADR 讓它成為距離的**唯一**來源）、
[ADR-013](ADR-013-excel-import-architecture.md)（Excel 匯入 `TARGET_FIELDS` **早已含** `hand`／`seconds`／`quantity`）、
[ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（欄位只增不改——本 ADR 的契約變更全部是
「必填→選填」的放寬，理由見 §3.5）、
[ADR-014](ADR-014-v3-dictionary-as-value-authority.md) E1（A6 返回格僅計伸手）、
[ADR-020](ADR-020-simo-contribution-semantics.md)（SIMO 貢獻語意，與 `hand` 的歸屬相關）、
[ADR-027](ADR-027-domain-evolution-versioning-and-ai-readiness.md) §1（版本軸）、
`docs/llm/wi-ai-parser-implementation-spec.md` §5／§5.1／§7.5／§19、
`docs/llm/wi-ai-parser-worklog.md` §8（量測紀錄）／§9（S-2、S-8、T-3、T-8）／§10（Q-1、Q-2）、
`docs/core-logic/minimost-sequence-model-core-logic-spec.md` §2（七格模型）

---

## 1. 脈絡

### 1.1 User 裁決（逐字）

> 「頻率／數量並不會出現在語句，但是之後會做 parser 去解析 csv。所以 llm 要做的只是把語句中的
> **從哪裡做什麼到哪裡做什麼，還有返回（若有）**解析出來。並不是要你真的整個透過 llm 解析，
> 有些必須特殊處理。我是希望你能把**解出來的詞與對應的 most sequence model 看對應到哪一步**。」

### 1.2 三點逐項確認（User 回覆「1. 對的 2. 距離也不用管我有其他方式處理 3. 對的」）

1. **詞要抽出來**，不只分段——下游 `SlotLinker` 要拿詞去比對字典選項。輸出＝「片語 ＋ 它屬於哪個角色」。
2. **距離不歸 LLM**。A0／A3 的檔位靠距離，但句子多半沒寫距離；User 另有機制處理
   （＝ADR-031 的站內佈局；本 ADR 把它確立為唯一來源）。
3. **一句話對應一條 cycle**；`×16` 這類頻率**不由 LLM** 拆成 16 個動作。

### 1.3 這三件事在序列模型上的位置（已對 sequence spec §2 查證）

七格固定為 GM＝`A B G | A B P | A`、CM＝`A B G | M X I | A`。User 講的四件事正好是它的分段：

| User 的講法 | 序列位置（GM） | 序列位置（CM） |
|---|---|---|
| 從哪裡 | **A0**（取得段的伸手） | **A0** |
| （取得）做什麼 | **G2** | **G2** |
| 到哪裡 | **A3 ＋ P5** | 控制段 **M3／X4／I5** |
| 返回（若有） | **A6** | **A6** |

> ⚠️ **查證發現（本 ADR 的第一個事實缺口）**：`most_compiler/compile.py` 目前
> **GM 分支只填 `a0/b1/g2/a3/p5/frequency`、CM 分支只填 `b1/g2/m3/x4/i5/frequency`**。
> 也就是說 **`a6` 在兩條分支都從未被填過（恆為 0），CM 的 `a0` 也從未被填過**。
> `StrictGmDraft`／`StrictCmDraft` 有這些欄位、引擎也算得出來，但編譯路徑不產生它們。
> 換言之 User 說的「返回（若有）」**今天在管線裡完全無法表達**——這不是 LLM 沒解出來，
> 是下游沒有接口。收窄之後補上這個接口，是本 ADR 提案的一部分（D2、§4.1）。

### 1.4 現況的病：**契約要求的，比 gold 評的多，而且比下游用得到的多**

三組獨立量測，全部指向同一件事。

#### (a) 逐一查證每個 `ROLE_KEYS` 的下游消費者

（方法：`grep` 全 `src/`，逐處讀呼叫點；`hand` 的粗 grep 會命中 rule parser 欄名／M 的
`pricing_kind`／Excel 匯入欄，已逐一排除。）

| role key | 誰真的讀它 | 讀來做什麼 | 影響 TMU？ |
|---|---|---|---|
| `object` | `linking._LINK_SPEC`（G／P／M／X／I 五池查詢）、`_B_BODY_HINTS` 判定 | 併進候選查詢字串 | 間接（決定選到哪個 option code） |
| `tool` | `linking._LINK_SPEC`（G／P／M／X 四池） | 同上 | 間接 |
| `destination` | `linking._LINK_SPEC`（P 池）；`compile.py:332`「acquire 無 destination → `next_operation`」 | 查詢字串 ＋ 一個旗標 | 間接 |
| `process_kind` | `_LINK_SPEC`（M／X 池）；`linking._x_seconds_source_present` 讀 `.unit`／`.value`；`compile.py:282-287` → `x4.x_seconds` | 查詢字串 ＋ **秒數直達引擎** | **直接**（＝S-8 ⑵ 那條路） |
| `inspect_kind` | `_LINK_SPEC`（I 池）；`_apply_i_range_rule` 只看 `.text` 在不在 | 查詢字串 ＋ 一個假設旗標 | 否 |
| `from_location` | **只有** `compile.py:245` `_resolve_distance_cm(role_key="from_location")` → `a0.reach_cm` | **數值直達 A 檔位**；**完全不進任何候選查詢**（`_LINK_SPEC` 沒有它） | **直接** |
| `distance` | `compile.py` → `a3.reach_cm`（GM）／`m_components[].distance_cm`（CM） | **數值直達 A／M 檔位** | **直接** |
| `quantity` | `policies.resolve_frequency` → `frequency`（TMU 乘數） | **數值直達乘數** | **直接** |
| `tool_ref` | `policies.is_tool_held` 讀 `.action_ref` → G 留空＝0 TMU；`sanitize_planner_output` 的工具狀態守衛 | 結構參照 | **直接**（讓 G 歸零） |
| `hand` | **零消費者** | — | 否 |

再往下一層看 `RoleValue` 的欄位本身：

| 欄位 | 誰讀 | 結論 |
|---|---|---|
| `text` | `linking._query_text`（候選查詢）、`compile._role_distance_cm` 的文字退路 | **有用**：這正是 User 要的「詞」 |
| `value`／`unit` | `compile._role_distance_cm`、`policies.resolve_frequency`、`compile` 的 `x_seconds`、`linking._x_seconds_source_present` | **全部是 User 裁定要移出 LLM 的三類數值**（距離／數量／秒數） |
| `status` | **只有 `contracts.py:214` 與 `:219` 兩處，而那兩處都在 `validate_planner_output` 自己裡面** | **零下游消費者**。它存在的唯一目的是讓驗證器有東西可以拒絕；`most_compiler` 完全不讀（S-2 已記載） |
| `action_ref` | `policies.is_tool_held`（僅 `tool_ref` 那一支）＋ sanitize／validate 自己 | 只有 `tool_ref` 這一個鍵有真實用途 |

同樣的查證套到 `dependencies`：`plan.dependencies` 在 `src/` 只有 **一處**功能性消費
（`policies.is_tool_held`，接受 `uses_tool`／`tool_held_for`／`same_object`）。
**`precedes` 在型別宣告之外零引用**——`sequence_order` 已經表達了順序，模型花在它上面的 token 是純浪費。

前端也一樣：`features/wi-workbench/aiTypes.ts:27` 宣告了 `roles` 型別，
但整個 `src/frontend/src` **沒有任何 `.tsx` 讀它**。覆核者其實看不到 roles。

#### (b) gold 語料：IE 核准的案例根本沒有 roles

（方法：直接統計 `tests/gold/wi_plans/*.json`。）

| 量測 | 數字 |
|---|---|
| 正式 gold 案例 | **55**（IE 核准 52 ＋ seed fixture 3） |
| action 總數 | **60** |
| 帶 roles 的 action | **3**——而且**全部**在手寫的 seed fixture `g01`／`g02` 裡；**52 個 IE 核准案例的 roles 全空** |
| role value 總數 | **5**（`object`／`tool`／`process_kind`／`quantity`／`tool_ref` 各 1） |
| dependency 總數 | **1**（同樣在 seed `g02`） |
| `expected_cycles` 的 `distance_cm` | **19 筆，全部 `0.0`** |
| 51 條 `tech_line` 的 A 格 | **全部三格皆 `A0`**（10 種相異 tech_line，無一例外） |
| 標 `expected_incomplete_reason` 含 `distance_unstated` 的案例 | **19／55**（其中 1 筆併 `x_seconds_required`、1 筆併 `count_unstated`） |

最後一列是 User 裁決 2 的**語料實證**：**三分之一的 IE 核准案例，IE 自己標記「距離句子裡沒寫」**。
這與 ADR-031 §1.1 的量測是同一件事，從另一個欄位再測一次。

> 這一節就是 worklog §9 T-8「gold 語料承載不了任何 roles-based 判準」的完整數字版。
> 差別在於：T-8 說的是「gold 太少 roles」，實際量到的是**更強的敘述**——
> **gold 裡的每一個 role 都出自我們自己手寫的 fixture，沒有任何一個來自 IE 的判斷。**

#### (c) 最新一輪（plan-v1.4）的失敗：8 案全部敗在角色層，零案敗在語意

（來源：`--planner llm`、qwen2.5:14b、`--llm-timeout-s 300`、gold n=55 的兩輪執行；
**兩輪逐案完全一致**（temperature=0），所以不是抽樣抖動。報告尚未入版控，見 §7 未決 U-6。）

| 案例 | 原文 | 失敗碼 | 性質 |
|---|---|---|---|
| `g07` | 雙手接觸×16dimm卡槽的左右卡扣按壓×16並確認卡扣按壓規定位置 | `unknown_role_key:a2:object_ref` | 自創鍵名；語意本身沒錯 |
| `g23` | 右手抓握假dimm的包裝袋撕除 | `unknown_role_key:a2:object_ref` | 同上 |
| `g13` | 右手抓握風槍按動按鈕並吹風清潔dimm卡槽 | `json_or_schema`：dependency type 自創 `same_hand` | **一個沒人消費的欄位**打掉整份輸出 |
| `g20` | 右手從dimm材料盒拿取label貼附至主機板 | `explicit_without_evidence:a1:hand`、`:a1:from_location`、`inferred_without_ref:a1:object` | 三條都是角色層形式規則；`hand` 還是零消費者 |
| `g24` | 左手重新抓握主機板的包裝袋放至料架 | `inferred_without_ref:a1:from_location` | 同上 |
| `g35` | 雙手從dimm材料盒拿取dimm組至主機板 | `inferred_without_ref:a1:object` | 同上。**這句正是 User 講的標準形狀**（從哪裡／什麼／到哪裡），gold＝單一 `move_place` |
| `g46` | 右手並鎖附固定並確認螺絲到位 | `action_ref_unknown:a1:object`、`explicit_without_evidence:a2:inspect_kind` | 同上 |
| `g48` | 電動鎖附(多顆) | `json_or_schema`：`quantity.value` 收到 `'多'` | **正是 User 裁定不該由 LLM 產的東西** |

**8／8 的失敗都落在「角色的形式」或「dependency 的型別」，沒有任何一案是動作切分或 action_type 判錯。**
而角色與 dependency，正是 §1.4(b) 說的、gold 完全不評的兩個維度。

指標代價（同一份報告）：

| | plan-v1.3（重測基準） | plan-v1.4 |
|---|---|---|
| 硬失敗 | 7／55 | **8／55** |
| `action_count_accuracy` | 0.764 | **0.727** |
| `boundary_span_f1` | 0.707（P 0.732／R 0.683） | **0.712**（P 0.724／R 0.700，tp 42／fp 16／fn 18） |

硬失敗案例被記為 `pred_action_count=0`＋gold span 全記 FN（`planner_eval` 的刻意設計，避免指標獎勵崩潰），
所以那 8 案**獨力貢獻了 18 個 FN 裡的 8 個**——**recall 的損失有 44% 來自「因為角色寫壞而整份丟掉」**，
不是來自切分錯誤。

### 1.5 為什麼這不是「再調一版 prompt」

worklog §8 已經記過：v1.1→v1.4 連加四版規則（角色鍵名白名單、`action_ref` 值域、禁佔位字、
dependency type 白名單），失敗形態換了幾種但總數不降（7↔8），§10 Q-2 的結論是
**「規則寫了但模型不遵守，加規則已達邊際效益遞減」**。

本 ADR 的主張比那個更強：**這些規則要求的東西，下游本來就不需要。**
`status` 零下游消費者、`precedes` 零消費者、`hand` 零消費者、gold 零 roles 判準——
我們花了四版 prompt、一輪一輪 25 分鐘的評測，去教模型滿足一組**只有驗證器自己在看**的形式要求，
而每次沒滿足就把**語意正確的切分**整份丟掉、退回 rule parser。

---

## 2. 決策（提案）

> 一句話：**LLM 只回答「這句話有幾個動作、每個動作的哪幾個字扮演哪個角色」。
> 凡是「多少」（距離／數量／秒數）都不由它產生；凡是「哪一格、幾 TMU」更不由它產生（ADR-026 既有邊界不變）。**

### D1 LLM **不輸出任何數值**

- `RoleValue.value` 與 `RoleValue.unit` **不再向模型索取**，prompt 不再示範，schema 說明不再列。
  模型若仍輸出，adapter 邊界**剝除並記名**（`role_numeric_stripped:<action>:<role>`），不因此整筆失敗。
- 三類數值的新歸屬：

  | 數值 | 收窄前 | 收窄後的唯一來源 |
  |---|---|---|
  | 距離（A0／A3／M 分量） | `from_location`／`distance` 的 `value`＋`unit`，**或**句面 regex（`quantities.extract_distances`）。role 優先 | ⑴ 句面 regex（**保留**，它讀的是原文不是模型主張）；⑵ **ADR-031 的站內佈局**（帶出處、IE 確認才落值）。**role 這條路關閉** |
  | 數量／頻率 | `quantity.value` → `frequency` | CSV／Excel 匯入欄（ADR-013 `TARGET_FIELDS` **已有** `quantity` 欄）或 IE 手填 |
  | 製程秒數 | `process_kind.value`＋`unit` → `x4.x_seconds` | 同上（`TARGET_FIELDS` **已有** `seconds` 欄） |

- **注意「距離不歸 LLM」不等於「距離消失」**：`compile._evidence_distance_cm` 走的是
  `quantities.extract_distances(normalized_text)`——那是對**原文**跑 regex，不是模型的主張，
  留著它是對的。收窄關掉的是**與它競爭的第二個來源**（role 值優先於句面，可以覆蓋 regex 讀到的真值）。
  這正是 S-2 記載的實例：「推動治具450mm至定位」＋模型 `value=450 unit="cm"` ＝真值的 10 倍。

### D2 role key 依 User 的四段重述；**補上「返回」**；`hand` 移出 LLM

收窄後**要求**模型產出的鍵（其餘一律不要求）：

| User 的講法 | role key | 下游用途 |
|---|---|---|
| 從哪裡 | `from_location` | ADR-031 D7 的名詞→物件對應（**新用途**，見 §4.1）；不再產生數值 |
| （取得）做什麼 | `object`、`tool` | G／P／M／X／I 候選查詢（既有） |
| 到哪裡 | `destination` | P 候選查詢（既有）＋ ADR-031 D7 對應（**新用途**） |
| （受控／製程／檢查）做什麼 | `process_kind`、`inspect_kind` | M／X／I 候選查詢（既有） |
| **返回（若有）** | **`return_to`（新增，ADR-011 加法）** | **A6**；今天完全無接口（§1.3 的查證），需同時補 compiler 分支 |
| 用的是前面拿的那個工具 | `tool_ref`（**唯一保留的結構參照**） | `is_tool_held` → G 留空＝0 TMU |

- **`hand` 移出 LLM 的輸出**：它零消費者、spec §19 待決 #3 的 v1 保守解本來就是「全部 missing/review」、
  而 `TARGET_FIELDS` 已有 `hand` 欄。**不從 `ROLE_KEYS` 白名單刪除**（避免 enum 收窄）——
  只是 prompt 不再要求、模型若給就當未知鍵剝除。
- `distance`／`quantity` 兩個鍵同樣留在白名單但不再索取（D1）。
- **不讓 LLM 直接吐 MOST 字母**（不輸出 `A0`／`G2`／`P5`）：role→參數→序列格的對應已經是
  `linking._LINK_SPEC` ＋ `policies.SEQ_BY_ACTION`／`CORE_PARAM_BY_ACTION` 的確定性表。
  讓模型輸出 MOST 結構會違反 ADR-026 §2（AI 輸出必須 MOST-neutral），
  也會把「哪一步」變成第二個可漂移的權威。**User 要的對應由這張表提供，不由模型提供。**

### D3 「這個詞有沒有出處」改用**可機械驗證的事實**，取代模型的自我宣告

- **廢止**：`status`（explicit／inferred／…）作為向模型索取的欄位；連帶廢止
  `explicit_without_value`／`explicit_without_evidence`／`inferred_without_ref`／`action_ref_unknown`
  四條驗證規則。
- **取代它的單一不變式**：**任何 role 的 `text` 必須是 `normalized_text` 的字面子字串**。
  - 這比舊規則**更嚴**：舊的 `_role_covered_by_evidence` 是**雙向**子字串比對
    （`text in ev.text` **或** `ev.text in text`），所以「role.text 是 evidence 的超集」可以通過
    ——那正是 S-2 記載的第二條繞過。新不變式直接比對全句原文，沒有這個洞。
  - 這也不需要模型誠實：模型宣告 `status` 是自陳，子字串是可驗證的事實。
- `RoleValue.status` 欄位本身**保留在契約裡**（ADR-011 只增不改），改為 `status: RoleStatus | None = None`；
  既有 gold／既有 `ai_parse_runs` 資料照常解析。

### D4 evidence 保留，但 **offset 由我們算，不由模型報**

- `boundary_span_f1` 是**唯一**量得到「切在哪裡」的指標，而 User 的裁決保留了分段職責，所以 **span 必須留**。
- 但**模型只給 `text`，不給 `start`／`end`**：worklog §8 量到 `evidence_offset_repaired`
  在 v1.3 兩輪各觸發 62／63 次（55 案），即**幾乎每一份輸出都要修**；
  `contracts.repair_evidence_offsets` 的 docstring 本來就寫著「這個次數是之後決定要不要讓模型
  根本別輸出 offset 的依據」。**依據已經到齊。**
- 收窄後的定位規則（確定性，取代 `repair_evidence_offsets` 的三分支）：
  1. `text` 在 `normalized_text` 恰好出現一次 → 直接定位。
  2. 出現多次 → 依 `sequence_order` **由左至右單調指派**（同一位置不重用），
     掛 `evidence_span_assumed_order` 旗標並**擋 auto**——這是假設不是觀測，覆核者必須看得到。
  3. 找不到（模型改寫／幻覺）→ 該 action 剔除（沿用既有 `planner_invented_action` 語意）。
- 規則 2 的正確性沒有語料背書（gold 全是整句單 span），**列為未決 U-4**。

### D5 `dependencies` 降為**選用且非致命**；`precedes` 不再索取

- 保留 `tool_held_for`／`same_object`／`uses_tool`——它們透過 `is_tool_held` 讓 G 歸零，是**真實的 TMU 效果**。
- `precedes` 零消費者，prompt 不再要求（型別保留，ADR-011）。
- **型別不合法的 dependency 一律丟棄並記名，不得讓整份輸出失敗**（`g13` 就是被這個打掉的）。

### D6 **驗證失敗改為逐項降級，不再整筆退回 rule parser**

現況：`validate_planner_output` 回任一 error → `llm_planner` retry 一次 → 仍錯就
`raise PlannerError` → `wi_ai_service` fallback 到 rule parser（＝**丟掉整份語意正確的切分**）。

提案的責任分層（架構原則：**嚴格屬於契約，寬容屬於 adapter 邊界**）：

| 層 | 職責 | 失敗處理 |
|---|---|---|
| `llm_planner`（adapter 邊界） | 寬容前處理：剝未知鍵、剝數值、丟壞 dependency、算 offset | 逐項剝除＋記名 reason；**不 raise** |
| `contracts.validate_planner_output`（契約） | 只驗**結構完整性**：`action_id` 唯一、`sequence_order` 連續、role text 是原文子字串、dependency 端點存在 | 違反才 raise（這幾條違反代表輸出真的壞了） |
| `routing` | 把所有剝除 reason 變成可見旗標並擋 auto | — |

**保留整筆失敗的情形只剩三種**：JSON 解析失敗、`actions` 全空、`sequence_order` 不連續。

**對 §1.4(c) 那 8 案的預期影響**（誠實標明推論邊界）：
6 案（`g20`／`g24`／`g35`／`g46` 的角色形式問題、`g07`／`g23` 的 `object_ref`）
所觸發的檢查在收窄後**不再存在**，`g13`（壞 dependency）與 `g48`（`quantity` 非數值）
在 D5／D1 下也不再是失敗。
**但「不再硬失敗」不等於「答對」**——那 8 份輸出的切分是否正確**無從得知**，
因為被拒絕的原始回應沒有留存（報告只記錯誤碼）。已知的是 `g07`／`g23`／`g46` 都出現了 `a2`，
而這三案 gold 都是**單一 action**，所以它們會從「硬失敗」變成「切分錯誤」——
**那正是我們要量的東西**。留存被拒回應以便回答這個問題，列為 §4.4 的新票 T-12。

### D7 距離的**單一來源**成為架構不變式

**I-D1：`most_compiler` 不得從 LLM 產出的 role 取得任何進入 TMU 檔位的數值。**
距離只能來自 ⑴ 對原文的確定性抽取，或 ⑵ ADR-031 的佈局服務（帶出處、經 IE 確認）。
可機械檢查：`_role_distance_cm` 這條路徑刪除後，`compile.py` 不得再出現 `role.value` 的讀取。

這順帶關掉 ADR-031 D4 的一個張力：ADR-031 說「算出的距離＝帶出處的建議，IE 確認才落值」，
但只要 LLM 這條路還開著，就存在一個**不帶出處、不需 IE 確認**的競爭來源。收窄後不存在。

---

## 3. 收窄後的最小契約（提案；實作細節歸 spec §5，本節只定形狀與理由）

### 3.1 模型被要求產出的東西（`PlannerOutput`）

```
language
actions[]:
    action_id            # a1, a2…（run 內唯一）
    action_type          # 既有 7 種列舉；決定 GM/CM 與核心格，不變
    sequence_order       # 1..N 連續
    roles{}              # key ∈ {object, tool, tool_ref, from_location,
                         #        destination, return_to, process_kind, inspect_kind}
                         # value = { text: <原文字面片語> }  ← 只有 text
                         #         tool_ref 另可帶 { action_ref: "aN" }
    evidence[]           # [{ text: <原文字面片語> }]  ← 只有 text，無 start/end
dependencies[]           # 選用；type ∈ {uses_tool, tool_held_for, same_object}
unresolved[]
```

### 3.2 與現行契約的差異

| 項目 | 現況 | 提案 | 理由 |
|---|---|---|---|
| `RoleValue.status` | 必填列舉 | **不索取**；欄位改選填 | 零下游消費者（§1.4a）；被子字串不變式取代（D3） |
| `RoleValue.value`／`unit` | 索取 | **不索取**，adapter 剝除 | User 裁決；三類數值另有來源（D1） |
| `RoleValue.action_ref` | 任意 role 可帶 | **僅 `tool_ref`** | 只有 `tool_ref` 有消費者（`is_tool_held`） |
| `EvidenceSpan.start`／`end` | 模型產出、驗證 | **我方推導** | 模型幾乎每份都算錯（62／63 次修復）；`text` 可驗證、offset 可推導（D4） |
| `hand`／`distance`／`quantity` | 索取 | **不索取**（白名單保留） | 零消費者／數值另有來源 |
| `return_to` | **不存在** | **新增**（加法） | User 明講「還有返回」；今天連 compiler 都沒有接口（§1.3） |
| `dependencies` | 必要且型別致命 | 選用、壞的丟棄 | 一處消費者；`precedes` 零消費者（D5） |
| 驗證失敗 | 整筆退回 rule parser | 逐項降級（三種除外） | 8／8 失敗都在不評的維度（§1.4c、D6） |

### 3.3 為什麼不乾脆讓模型輸出 MOST 格

見 D2 最後一點：違反 ADR-026 §2，且會製造第二個「哪一步」的權威。
**User 要的「對應到哪一步」由 `_LINK_SPEC`／`SEQ_BY_ACTION` 這張確定性表提供**，
本 ADR §1.3 的表就是它的人類可讀版本。

### 3.4 為什麼不乾脆把 `roles` 整個拿掉、只留 evidence

因為 User 裁決 1 明講「詞要抽出來」，而且下游確實用得到：
`linking._query_text` 目前是「role text ＋ evidence text ＋（都空才）整句」。
只留 evidence 會讓查詢退化成「整段動詞片語」，把 `g35` 這種
「從 A 拿 B 到 C」的三個名詞糊成一團去查 P 池。**roles 是查詢精度的來源，不是裝飾。**

### 3.5 ADR-011 相容性

本 ADR 對 `contracts.py` 的變更**全部是放寬**（必填→選填）與**新增**（`return_to`、
`EvidenceSpan` 的 offset 改為可省略）。
既有 gold 檔（5 個帶 `status` 的 role value）、既有 `ai_parse_runs` 的 `plan` JSON **照常解析**。
**沒有任何欄位被刪除，沒有任何列舉被收窄。**

---

## 4. 影響清單

### 4.1 要改（實作）

| 檔案 | 改動 | 風險 |
|---|---|---|
| `nlp/contracts.py` | `RoleValue.status` 改選填；`EvidenceSpan.start/end` 改選填；`validate_planner_output` 砍四條角色規則、加子字串不變式；`repair_evidence_offsets` 改為 `derive_evidence_offsets` | 中：契約檔，跨層 |
| `nlp/llm_planner.py` | 新增寬容前處理層（剝未知鍵／數值／壞 dependency）；失敗條件收窄為三種 | 中 |
| `nlp/prompts/plan_v1.py` | **12 條規則預估剩 8 條**：移除規則 4（status 四態）、8（offset 數法）、9（quantity 抽數值）、12（dependency 白名單）；規則 4 的「禁止猜測／禁佔位字」改寫為「role text 必須是原文字面片語」，規則 7 的鍵名清單縮短；升 `PROMPT_VERSION` → `plan-v2.0`（形狀變了，不是微調）；四則 few-shot 全部重寫（現行每一則都示範了 `status`／offset／數值） | **高**：改教材必重跑評測 |
| `most_compiler/compile.py` | 刪 `_role_distance_cm`（I-D1）；`x_seconds` 不再讀 `process_kind.value`；**補 `a6`（`return_to`）與 CM 分支的 `a0`** | **高**：動 TMU 路徑 → 觸發黃金值關卡＋`ddm-validator` 派工 |
| `most_compiler/policies.py` | `resolve_frequency` 的 `quantity.value` 入口關閉（保留函式供未來 CSV 供給者） | 中 |
| `nlp/linking.py` | `_LINK_SPEC` 加入 `from_location`／`return_to` 進查詢字串（今天 `from_location` 只產數值、不進查詢）；`_x_seconds_source_present` 恆 False | 低–中 |
| `nlp/routing.py` | 新旗標進 `ROUTING_REASONS` 並擋 auto：`role_numeric_stripped`／`role_key_dropped`／`dependency_dropped`／`evidence_span_assumed_order` | 低。⚠️ **不要**順手宣稱關掉 S-5：S-5 的病是白名單**宣告了卻不執行**（`compute_routing` 無條件 `reasons.extend(plan.unresolved)`），加旗標不會讓它被執行 |
| `services/v2/wi_ai_service.py` | fallback 條件跟著 D6 收窄 | 低 |
| 前端 `aiTypes.ts` ＋ `ActionCard.tsx` | roles 從「宣告了但沒人讀」變成**應該顯示**——覆核者要看得到「這個詞被判成哪個角色」 | 中：需對照 v3 母版＋Playwright 截圖（CLAUDE.md 前端驗收） |

### 4.2 要刪／降級

- `validate_planner_output` 的 `explicit_without_value`／`explicit_without_evidence`／
  `inferred_without_ref`／`action_ref_unknown`（四條）。
- `_role_covered_by_evidence`（雙向子字串，S-2 的第二條繞過來源）。
- `most_compiler/compile.py` 的 `_role_distance_cm`。
- prompt 規則 4（status 四態）、規則 7 的 `hand`、規則 8（offset 數法）、規則 12（dependency 白名單的白話版）。

### 4.3 既有記票的重新分級（逐票，含「為什麼是這個級別」）

| 票 | 現級 | 收窄後 | 理由 |
|---|---|---|---|
| **S-2**（無憑據角色值直達 TMU） | High | **降為 Medium，但守衛一律保留** | LLM 這個**輸入通道關閉**，威脅模型從「模型捏造數字」變成「**非 LLM 的數值供給者**（CSV 匯入、佈局服務）未經證據綁定」。`numeric_claim_is_evidenced`／`DISTANCE_UNEVIDENCED_REVIEW`／`finite_or_reject` **不得刪除**——它們正好是新供給者要撞上的邊界檢查。**這是本 ADR 最容易被誤讀的一條：收窄不是「問題解決了」，是「攻擊面換人了」** |
| **S-8 ⑵**（`x_seconds` 無證據判準） | High | **降為 Low**（條件式） | `process_kind.value` 的唯一寫入者是 LLM，關閉後這條路**不可達**。⑴（非有限值）已修，保留。**降級的前提是先驗證沒有第二個寫入者**——落地前必須 grep 確認 |
| **S-11**（`calculate` 端點吃 NaN） | Low–Medium | **不變** | 與 LLM 無關（是 API 契約層）。原建議「與 S-8 一起做」失效，改為與 S-2 的邊界檢查同批 |
| **S-1**（prompt injection 逸出） | High | **不變，但相對重要度上升** | 收窄減少了模型能造成的**數值**破壞，injection 能造成的**語意**破壞（引導出錯誤的角色片語）不受影響。而收窄後 LLM 的產出更被信任（不再整筆退回），這條的份量變重 |
| **S-4**（`nl-draft` 缺 `require_role`） | Medium ⭐ | **不變，維持往前拉** | 一行修法、零評測成本；理由（覆核者是唯一防線）不因收窄改變 |
| **S-5**（`ROUTING_REASONS` 宣告了卻不執行） | Medium | **不變，但相對重要度上升** | 查證：全 `src/` 對它零引用，唯一引用在 `tests/unit/test_routing.py:234`（斷言成員資格，不是執行過濾）。D6 之後模型可控字串進 `routing_reasons` 的路徑更多（每個剝除 reason 都是），**白名單值得被執行**——但那仍是 S-5 自己的修法，本 ADR 不代它宣告完成 |
| **T-8**（gold 承載不了 roles 判準） | 結構性限制 | **從「限制」升為「阻擋項」** | 收窄後 roles 是 LLM 的**主要**產出，而 gold 對它零標註。**指標必須補**（§4.4） |
| **T-3**（切分守衛檢查 2 空跑） | 未修 | **不變，但前瞻風險提前** | 收窄提高了「從已核准 LLM plan 回填 gold」的誘因，而回填正是 T-3 預告會誤報的動作 |
| **T-10／T-11**（`model_served_confirmed`、model 名截斷） | Low | **不變** | 與 roles 無關，講的是 LLM 呼叫的 provenance |
| **Q-1**（few-shot 捏造 quantity） | 進行中 | **被本 ADR 吸收** | 收窄後 few-shot 全部重寫；工作目錄裡未 commit 的 v1.4 改動仍應保留為獨立提交（它是這次討論的起點與證據） |
| **Q-2 的 `g48`** | 待 IE 裁 §19 #1 | **從 parser 問題變成資料來源問題** | 「多顆」不再需要模型表示成數字；§19 #1 的問題改寫為「CSV／IE 如何提供 N」（見 U-2） |
| **§19 待決 #3**（手別／SIMO） | v1 全 missing | **確立為「不歸 LLM」** | `hand` 移出模型輸出；來源候選＝`TARGET_FIELDS.hand`（U-3） |

### 4.4 gold 語料與評測指標

| 指標 | 收窄後是否仍正確 | 說明 |
|---|---|---|
| `action_count_accuracy` | **仍正確，且更有意義** | 分段是收窄後保留的核心職責。分數會**上升**（8 案不再記 0 個 action），但**那不是能力提升**——是量測終於量到東西。**必須在報告 note 裡標明版本斷點**，否則會被誤讀成改善 |
| `boundary_span_f1` | **仍正確** | span 從模型自報 offset 改為我方推導後，量的是「模型指認的**片語**」而不是「模型數對的**座標**」——這反而更接近指標想量的東西 |
| `dependency_f1` | **建議正式作廢** | D5 把 dependencies 降為選用且 `precedes` 不再索取；spec §14.4 的「boundary/dependency F1」該列需改寫。**不是「未實作」而是「不再適用」** |
| **role slot accuracy（新）** | **缺，必須補** | 這是收窄後 LLM 的**主要產出**，而現在**零指標**。定義建議：對每個 gold action，比對 `{(role_key, text)}` 集合的 P／R／F1。**前提是 gold 要有 roles，而它今天沒有**（§1.4b） |

**gold 的動作（本 ADR 的最大成本，也是最大風險）**：
55 案要補 roles 標註。兩條路都有問題，需 User／IE 裁決（U-1）：

- **(A) IE 親筆標**：唯一真 ground truth，但 55 案 × 每案數個片語，是 IE 的實際工時。
- **(B) 從已核准的 LLM plan 回填**：成本低，但 **⑴** 觸發 T-3 的前瞻誤報；
  **⑵** 觸發 `planner_eval` 的自我指涉排除（`plan_origin=<planner>_preannotation` 且 `ie_modified≠true`
  的案例會被排除出 Plan 層指標——這個守門是對的，不要為了讓分數好看去繞過它）。
  可行的折衷是「LLM 預標註 → IE **逐案改過**（`ie_modified=true`）」，那仍需 IE 的時間，只是從
  「從零標」降為「審改」。

---

## 5. 遷移路徑（每階段可獨立驗收，且**不得跳階**）

| 階段 | 內容 | 完成判準 |
|---|---|---|
| **P0** | 本 ADR 核可；spec §5／§5.1／§7.2／§7.5／§19 同步改寫 | User 核可，狀態轉 accepted |
| **P1** | 契約與 adapter 放寬（D3／D4／D5／D6），**prompt 先不動**、**compiler 先不動** | 以 **plan-v1.4 原 prompt** 重跑 55 案：硬失敗數應顯著下降。**這是唯一能把「契約放寬」與「prompt 改寫」兩個變因分開量的機會，不要合併** |
| **P2** | prompt 改寫為 `plan-v2.0`（D1／D2 的索取範圍），few-shot 全部重寫並過 `test_prompt_few_shots.py` 守衛 | 兩輪評測（單輪落在 ±2 案變異帶內不足以下結論，worklog §8 已立此規矩） |
| **P3** | compiler 側：刪 `_role_distance_cm`、關 `x_seconds` 入口、**補 `a6`／CM `a0`** | **黃金值關卡**（`scripts/core_logic/run_all.py`，GM=28／CM=29）＋ `ddm-validator` 派工＋compile 段 55/55 不退 |
| **P4** | gold roles 標註（U-1 裁決後）＋ role slot accuracy 指標上線 | 指標有分母；`dependency_f1` 正式標記為不適用 |
| **P5** | 前端顯示 roles（覆核者看得到角色判斷）＋ 新旗標的中文文案（併 S-10） | Playwright 截圖對照 v3 母版 |

**回退**：P1–P2 只動 `nlp/`，回退＝revert。**P3 動 TMU 路徑**，回退必須連同黃金值重跑，
且若期間已有 IE 採用的 cycle 落入 `most_cycles`，那些不會因 revert 改變（`slot_inputs` 是快照）——
**P3 上線前必須確認 `DDM_WI_AI_AUTO_ENABLED` 仍為 false**。

---

## 6. 考慮過的選項

### A. 維持現況，繼續調 prompt（否決）
四版規則後失敗數 7↔8 不降（worklog §8／§10 Q-2 已判定邊際效益遞減），
且要求的維度 gold 不評、下游不讀。**繼續投入是把成本花在量不到的地方。**

### B. 只放寬驗證（D6），不動索取範圍（部分採納為 P1）
能立刻回收 6–8 案，成本最低。但模型仍會產生數值，S-2／S-8 的通道仍開著，
User 裁決 2（距離不歸 LLM）沒有落地。**採納為遷移路徑的第一階，不作為終局。**

### C. 讓 LLM 直接輸出 MOST 七格（否決）
違反 ADR-026 §2（AI 輸出必須 MOST-neutral），並製造第二個 sequence 權威——
CLAUDE.md 的「單一權威引擎（反漂移）」明確禁止。

### D. 廢掉 LLM planner，回到純 rule-based（否決）
rule_based_v1 **恆輸出單一 action**、evidence 恆為整句、dependencies 恆空
（`planner_eval.RULE_DEGENERATE_NOTE`）。它處理不了多動作句，而多動作正是 ADR-026 §1 列的動機第一項。

### E. 本 ADR 的提案：收窄索取範圍 ＋ 放寬失敗處理 ＋ 數值改由確定性來源（選定）
把 LLM 放在它擅長的事上（中文語意分段與片語指認），把它不擅長也不該做的事
（數字、字元座標、自我宣告的憑據）交給確定性元件或另一條資料管道。

---

## 7. 未決問題（**需 User 或 IE 裁決**；本 ADR 不擅自填）

| # | 問題 | 為什麼不能由實作端決定 | 建議的裁決者 |
|---|---|---|---|
| ~~**U-1**~~ ✅ **已裁決 2026-08-23：走 (A) IE 親筆** | **gold 的 roles 標註走 (A) IE 親筆 還是 (B) LLM 預標註＋IE 逐案審改？** | 這決定收窄後**唯一**的能力指標有沒有證據力；(B) 若 IE 不逐案改，`planner_eval` 的自我指涉排除會把案例排除，等於白做 | User（工時）＋ IE（標註品質）。**User 裁決：親筆。** 連帶效果：親筆標的不帶 `plan_origin=<planner>_preannotation`，所以 P4 的 role slot accuracy 從第一天就有完整分母。⚠️ **2026-08-23 更正**：本欄原寫「不像現在 55 案裡 46 案被排除、有效樣本只剩 9」——**那組數字屬 `--planner rule_based`，不屬 LLM 評測**。排除判準綁 planner（`planner_eval.planner_preannotation_origin(planner)`），而 gold 的 `plan_origin` 全是 `rule_based_v1_preannotation`（52 筆，另 3 筆 seed 無此欄），所以拿 **LLM** 去評 rule 的預標註**不構成自我指涉**——實測 `plan-v1.4-run1` 的 `self_referential_excluded.count = 0`、`plan_metrics_n = 55`。**更正後 U-1 的理由更強**：親筆的好處不是「解除現有排除」（LLM 側本來就沒有），而是**避免把排除引進來**——走選項 B 從已核准 LLM plan 回填會讓 `plan_origin` 變成 `llm_preannotation`，屆時 LLM 評測就會開始排除那些案例，今天為 0 的排除數會反過來咬 |
| ~~**U-2**~~ ⏸ **2026-08-23 User 裁決：現階段不做，延後** | **`quantity`／`seconds` 由 CSV parser 供給的具體契約**：欄位語意、與 `frequency` 的關係、「多顆」這類非數值量詞如何表示 | 原 spec §19 待決 #1 的問題形狀被本 ADR 改寫；`resolve_frequency` 的 QuantityPolicyV1 是否仍適用取決於此 | IE。**User：「以後會開案做 csv parser 去帶出數量／frequency，現階段重點是 LLM 能不能解出四段結構」——本 ADR 只需確立「不歸 LLM」，供給端另案。** |
| ~~**U-3**~~ ⏸ **2026-08-23 User 裁決：同 U-2，延後** | **`hand`（手別）的來源**：`TARGET_FIELDS.hand` 欄？IE 手填？還是併入 SIMO 判定（ADR-020）？ | spec §19 待決 #3 尚未裁決；本 ADR 只確立「不歸 LLM」 | IE |
| ~~**U-4**~~ ✅ **2026-08-23 User 裁決：左至右指派可採用** | **同一片語在句中出現多次時的 evidence 定位規則**（D4 規則 2 的單調指派） | 沒有語料背書（gold 全是整句單 span）；選錯會把 span 掛到錯的 action | IE（看幾個實例即可裁）。**User：「應該不會有倒裝」**——動作順序與文字順序一致，故左至右單調指派安全，**不需額外旗標**。⚠️ User 另更正協調者的例子：`g32`「拿取主板，去除包裝袋，將主板放置工作台」的兩個「主板」**是同一塊**（中文自然的指代重述），不是歧義；且該句**少一個「並」**（應為「…包裝袋，並將主板…」）——屬 gold 原文的文字問題，**不擅自改**，但記在此：缺字會讓 D3 的「字面子字串」不變式多一分脆弱（記票 T-14） |
| ~~**U-5**~~ ✅ **2026-08-23 User 裁決：返回起點** | **`return_to` → A6 的語意**：「返回」是回到起點（`from_location`）還是回到中性位置？距離由 ADR-031 的哪一對端點算？ | 直接影響 A6 的 cm，屬 MOST 建模決策；ADR-014 E1 只說「A6 僅計伸手」，沒說量哪一段 | IE（＋ADR-031 P1 閾值一併）。**User：「是起點（照理來說是返回身體最初始狀態）」**——即 A6 量的是「終點 → 身體初始位置」，不是回到 `from_location` 這個物件。⚠️ 實作時要注意：`from_location` 是**取件處**，身體初始位置是**站位**，兩者不同；距離端點需 ADR-031 佈局提供 |
| ~~**U-6**~~ ✅ **已完成 2026-08-23（commit `3d01f61`）** | **plan-v1.4 的兩份評測報告是否入版控** | 本 ADR §1.4(c) 的全部數字出自它們，但它們目前只在 scratchpad。**證據不入版控＝這份 ADR 的關鍵論據無法被覆核** | User。**已入 `docs/llm/eval-reports/local-14b/`**，連同 `plan-v1.3-rebaseline`（三份皆 v7 schema、自述 prompt 版本與 model_served，可獨立覆核） |
| ~~**U-7**~~ ✅ **2026-08-23 User 裁決：要** | **是否在 P1 之後、P2 之前設一個「只放寬不收窄」的觀察期** | 兩個變因分開量的價值 vs. 多一輪 25 分鐘評測的成本 | User。**裁決：要**——P1 後先跑一輪（單輪即可，P1 的預期效果大到單輪看得出來）。理由不只變因分離：**若 P1 之後數字沒有明顯改善，那本身就是重要訊號**——代表失敗不只是契約刁難造成的，收窄的假設有問題，該在動 prompt 之前搞清楚。且這是**唯一**的機會：舊契約一旦拆掉，就造不出「舊契約＋新 prompt」的對照組 |

**新增技術債票（不需裁決，記錄以免遺忘）**

- **T-12**：`planner_eval` 未留存**被拒絕的原始回應**，導致「那 8 案的切分到底對不對」無法回答
  （§1.4c／D6 的推論邊界）。修法＝報告多存 `planner_raw_rejected`（需先確認不含憑證，
  沿用 `_redact_urls`）。**這一票應在 P1 之前做**，否則 P1 的「硬失敗下降」量得到、
  「切分正確率」仍量不到。
- **T-13**：前端 `aiTypes.ts:27` 宣告 `roles` 但零 `.tsx` 消費——收窄後 roles 是主要產出，
  「宣告了卻不顯示」會讓覆核者看不到最該看的東西（同 S-10／T-9 的可見性族）。

---

## 8. 重新評估的訊號（proposed 必填）

1. **P1 重跑後硬失敗數沒有明顯下降** → §1.4(c) 的歸因（失敗集中在角色層）錯誤，本 ADR 的前提失效，
   必須重新分析失敗形態，不得逕行進 P2。
2. **U-1 裁決為「gold 不補 roles」** → 收窄後的主要產出永遠無指標。此時應**縮小提案**：
   只採納 D6（放寬失敗處理）與 D1（不產數值），保留現行 role 索取範圍，不宣稱能力改善。
3. **IE 認為 `from_location`／`destination` 的名詞無法對應到佈局物件**（ADR-031 D7 的同義詞層不夠用）
   → D2 給 `from_location` 的「新用途」落空，它會退回成零消費者，應考慮一併移出索取範圍。
4. **出現第二個寫入 `RoleValue.value` 的來源（CSV adapter／佈局服務直接寫 plan）**
   → S-2 的降級（§4.3）立即失效，`numeric_claim_is_evidenced` 必須擴充到新來源，
   且 I-D1 的機械檢查要跟著改寫。
5. **模型換代（qwen2.5:14b → 設定模型 32B 或更強）後，角色層形式錯誤自然消失**
   → 收窄的「回收失敗案例」動機減弱，但**「不產數值」與「單一距離來源」的動機不變**
   （那是架構理由不是模型能力理由）。此時 D6 可重新評估，D1／D7 不動。
6. **`×16` 這類頻率被 IE 判定應該由 LLM 拆解**（與 User 裁決 3 相反）
   → D1 的 quantity 部分失效，需新 ADR 而非在此改字。

---

## 9. 不由本 ADR 決定

- CSV／Excel parser 的欄位對應與時間單位契約（歸 ADR-013 的後續，U-2 只提出問題）。
- ADR-031 的閾值 P1（臂展內／外）與距離端點定義（U-5 只指出 A6 需要它）。
- 手別／SIMO 的自動判定規則（spec §19 #3，U-3 只確立「不歸 LLM」）。
- 前端覆核 UI 的具體版面（歸 ADR-021／ADR-022 母版對照）。
- `deployment_bundle` 與 `input_hash` 是否納入 `PROMPT_VERSION`（worklog §9 D2-A；
  **但注意 `plan-v2.0` 是形狀變更，落地時 D2-A 的「下次 prompt 有實質變更」觸發條件成立**）。
- 是否把 `wi_ai` 抽成獨立服務（ADR-026 §1 已定的漸進路徑，不受本 ADR 影響）。
