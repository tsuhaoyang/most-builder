# MOST ↔ LB 整合契約與規範（討論中，逐題累積）

> **性質**：本文件記錄 MOST（v2）與 Line Balance（LB）兩套系統整合的**邏輯對齊與標準規範**，
> 與 `TASK_CSV_INPUT_CONTRACT.md`（LB 端提供的輸入契約）配套。
> **原則**（User 定調）：不是誰取代誰，是**兩套運行系統結合、互相配合**。先對齊邏輯，命名之後做 mapping。
> 不一定 MOST 對或 LB 對，討論出標準 SOP 與規範。
> **狀態**：討論進行中（2026-09-06 起），逐題定案累積。所有結論以實讀 code 為據。
> **LB 演算法**：CP-SAT + RCPSP（資源受限排程）；站/worker 是 LB 的**輸出**，MOST 提供帶屬性的 DAG 作**輸入**。
> **正式化（2026-09-11 晚）**：核心規範已收斂為 [`MOST_LB_DATA_CONTRACT_SPEC.md`](MOST_LB_DATA_CONTRACT_SPEC.md)（**最高原則**，`most-lb-csv-v1.1`）＋ [ADR-035](../decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md)（決策邊界）＋ [`LB_PROJECTION_IMPLEMENTATION_PLAN.md`](LB_PROJECTION_IMPLEMENTATION_PLAN.md)（實作書）＋ [`fixtures/`](fixtures/README.md)（黃金驗收）。本文件自此為**討論紀錄**；D1／D7 有追記、新增 D18；與 Spec 衝突以 Spec 為準。
> **狀態更新（2026-09-11 定稿）**：核心對齊 D1–D16 已定案並收斂為下方 **§0 正式 SOP**。中低風險項與待 LB 端資訊列於文末。

---

## §0 正式 SOP（定稿摘要，2026-09-11）

> 這是給後續實作 agent 的**規範入口**。每條指回細節 D 條款。核心哲學貫穿全篇：
> **MOST 給「工序關聯 + 屬性 + 單次工時」，LB 做「站/worker/排程/並行/合併」的決定。MOST 不代 LB 決策、不預先塌縮。**

### 0.1 兩層結構（核心，見 steering `wi-motion-core-structure.md`）
- **motion（一個七格 GM/CM model/cycle）= 一個 LB task（1:1）**；**WI（一句語句）= 多個 motion 的上層分組**（D1）。
- LB task 粒度一律對到 **motion**，不是 WI。

### 0.2 MOST → LB 的欄位對映（一覽）
| LB CSV 欄 | MOST 來源 | D |
|---|---|---|
| `task_id` | 投影層拓撲排序後單調重編號（確定性 tie-break=v2 seq_no，可重現） | D8/T3 |
| `predecessors` | level 主序/自由度（`~`用上下界框住、範圍內無邊=平行；`1/3`不做） | D8 |
| `duration` | motion 單次工時 `total_tmu × 0.036 × 1000`（ms 整數四捨五入，**未乘 frequency**） | D7/T3 |
| `quantity` | v2 `frequency`（單件內重複次數；**與 duration 拆開，讓 LB 自己乘**，勿送 eff_tmu 又送 quantity） | D7 |
| `qty_scope` | setup/cyclic（tool_action 預設、使用者可改） | D7 |
| `action` | motion `narrative_en`（LB 全英文；缺 en 匯出前警示） | D14 |
| `action_type` | 工具 motion 的英文短 code（pick/scan/put，merge 分桶鍵） | D1/D2 |
| `tool_id`/`tool_action` | vocab `kind='tool'` + 持有狀態機推 acquire/use/release | D2/D3 |
| `group` | cub（不可拆站） | D4 |
| `atomic_group` | worker_cub（不可拆動作·同一人連續，v2 新增概念） | D4 |
| `segment` | 批量分攤向量綁定（依附 group；保證參與者+件數一致、不保證工件級） | D9 |
| `offline_flag` | 純手動標（不自動推）+ 組內傳染 | D12 |
| `p2` | **不填**（並行人數交 solver） | D10 |
| （SIMO） | **待 LB 端加 SIMO 欄**；過渡：從屬列不輸出、主列 duration 含雙手 max | D15 |
| ~~machine_count/manpower~~ | **不送**（並行是 LB 職責） | D16 |
| `source_wi_row_id` | v2 `wi_row.id`（跨系統穩定對應鍵，供雙向同步；task_id 不穩定不作對應） | D13 |
| （WI 分組欄位） | WI 語句（讓 LB 知道多 task 同屬一 WI，走方案 c） | D1 |

### 0.3 硬規則（投影層 CsvContractValidator 匯出前必擋，對齊 LB §5）
- DAG：task_id 單調（pred id<自己）、無重複、pred 存在（D8/T3）。
- tool lifecycle 良構（每 acquire 有唯一 clean release、每 use 被覆蓋）（D2/D3）。
- Q>1：必須 group + duration_basis(`once`)；同 group quantity/duration_basis 一致；與 divisible/merge/atomic_group 互斥（D11）。
- 組內傳染一致：cub/worker_cub 內 offline 一致；worker_cub 成員 quantity≤1、不跨多 group、不帶 merge（D6/D4）。
- 浮動 task（無界孤立）→ 軟警示（D8）。缺 `narrative_en` → 警示（D14）。

### 0.4 雙向同步（D13）
- **屬性可雙向**（offline 等，回流須進 MOST 正門走驗證+傳染）；**結構單向**（predecessor/關聯只在 MOST 改、LB 唯讀引導回改）。
- LB 不得成為工序結構第二權威。對應鍵 `source_wi_row_id`。時序待 LB 回傳契約。

### 0.5 職責邊界一句話
MOST 負責：兩層工序組織、屬性標記（tool/cub/worker_cub/offline/segment）、單次工時、DAG（含拓撲編號）、雙語 narrative、匯出前自檢。
LB 負責：站/worker 指派、並行（max_manpower+DAG fork+quantity 分攤）、tool merge 決定、排程優化、KPI。

---

## T2（定稿）— MOST 端需新增/修改的實作清單

> 對齊後，MOST 要落地的東西。給後續實作 agent 的工作分解（非本輪實作，僅規格）。

**新增概念/資料**：
1. **worker_cub**（對齊 LB atomic_group，D4）：Level System 新增「同一人連續組」——資料落點與 UX（🔒 cub 琥珀 vs 👤 worker_cub 紫），設組即傳染（D6），成員 frequency>1 即時擋（IE H-補）。
2. **offline 標記**（D12）：Level System row 層級手動切換 + 組內傳染。
3. **segment 標記**（D9）：批量 motion 圈選同 segment（依附 group、Q>1 才有意義）。
4. **action_type 短 code**（D1/D2）：為工具 motion 產出 pick/scan/put 類英文分桶鍵。
5. **source_wi_row_id 對應鍵**（D13）：CSV 帶出、供雙向同步。

**新增後端「LB 投影層」（D5，無 UI，Level System 匯出路徑背後）**：
- ToolLifecycleResolver（D3）、PrecedenceProjector（D8＋拓撲編號 T3；**須依 D8 重寫，不可沿用現況 build_output 的保守 edges**）、
  StationGroupMapper/AtomicGroupMapper（D4）、QuantityProjector（D7 拆乘數+cyclic/setup）、OfflineMapper（D12）、
  MergeCandidateHinter（建議候選）、CsvContractValidator（0.3 全部自檢）。

**tool_action 自動推導 pipeline（D3）**：vocab `kind='tool'` + 持有狀態機 + LLM 粗判 + badge 互動 + 即時 lifecycle 驗證。

**修改/移除**：
- `to_lb_csv`：移除 machine_count/manpower 欄（D16）；改送 0.2 的欄位集。
- core-logic spec §6.2/§13 Q4 已更新（並行交 LB，D16）。

**待 LB 端確認才能定案的**：SIMO 欄（D15）、LB→MOST 回傳契約（D13）、H3 機器時間、混合粒度假設。

---

## 已定案共識

### D1 — task 粒度：一個 **motion**（most model）= 一個 LB task；WI 是上層分組（1:1 在 motion 層）

（User 裁決 2026-09-06；2026-09-11 依 Workbench 實機截圖 + 實讀 code 修正兩層結構）

> **重要更正（2026-09-11）**：原記為「WI row = task」用詞混淆了兩層。實機截圖（Workbench「WI outline: 13 WIs · 29 motions」）
> 與實讀 code 確認 MOST 是**兩層結構**（見核心定義 steering `.kiro/steering/wi-motion-core-structure.md`）：
> - **motion 層**：一個 motion = 一個七格 GM/CM model = 一個 cycle（有自己的 narrative/hand/freq/SIMO/TMU）。**最小粒度。**
> - **WI 層**：一個 WI = 一句語句 + 底下**多個 motion**（例「拿取電動起子，依圖示鎖附兩顆螺絲」= 1 句 / 3 motions）。

- **LB 的一個 task = 一個 motion（most model），1:1 在 motion 層。** 不是 WI 層（一個 WI 通常含多個 motion = 多個 task）。
  不做 1:N 結構調整、不把一個 motion 拆更小。
- **依據**：一個 GM/CM cycle（A-B-G-A-B-P-A 一次完整移動）在方法工程上就是「一次完整工序單位」，對齊 LB「最小工序單位」自然。

**WI 語句怎麼進 LB（走 (c)，User 裁決 2026-09-11）**：
- **motion 的 narrative 當 LB `action` 欄**（task 層精確描述，供 LB General 判定；D14 送 `narrative_en`）。
- **WI 語句（那句作業描述）用「WI 分組欄位」另帶**（讓 LB 知道這幾個 task 同屬一個 WI，供雙向同步 D13 對回 WI 層）。
- **不**把同一句 WI 語句灌進底下每個 motion 的 `action`（會重複、LB General 判定分不出）。
- 一個 WI 底下多個 motion 之間的關係，用既有機制表達：先後→`predecessors`(D8)、同站/同人→cub/worker_cub(D4)。

  **更正（2026-09-09 依新版 LB 契約 §3.2）**：merge 候選的**分桶鍵是 `action_type`（短標籤如 pick/scan/put），
  不是 `action`（敘述文字）**。故 MOST 還需為涉及工具的 motion 產出 `action_type`（見 D2/D3 更正）。

> **追記（2026-09-11 晚，ADR-035 D2）——1:1 是預設，不是鐵律**：持工具 motion（`tool_vocab_id` 或 `object_vocab_id` 為 `kind='tool'`）由投影層依七格結構**確定性拆為 acquire（slot 0–2）／use（slot 3–5）／release（slot 6）三列**（工具在後續 motion 才放下時為兩列）；general motion 不拆；SIMO 從屬列不輸出。判準是資料不是 IE 決定。理由與矩陣見 Spec §2、ADR-035 §1.1／D2。

### D2 — tool merge 的前提：取放要切成獨立 row（現場建模選擇，非強制）

（User 討論 2026-09-06）

- LB 的 tool merge（LB 契約 §3.2）要「拿起工具 / 用工具 / 放下工具」是**獨立 task** 才能讓 solver 合併取放。
- 當 MOST 的建模**自然地**把「拿起 scanner」「用 scanner 掃描」「放下 scanner」寫成不同句（不同 row）時，
  就天然對應 LB 的獨立 task。**不需為 LB 硬拆；MOST 本來這樣建就順帶支援。**
- **完整 tool lifecycle 必要條件**（LB 契約 §4）：必須有 `release`（放下）那一 row，否則 LB Fail-Fast（拿了不放）。
- 典型可 merge 場景（MOST 語句 → LB task）：
  ```
  拿起 scanner        → acquire
  拿起物件A           → （物件取得，非工具，無 tool_action）
  用 scanner 掃描物件A → use
  放下 scanner        → release
  …（另一條 DAG 互不可達支路重複一組 scanner acquire→use→release）
  ```
  LB 見兩組良構 lifecycle + 支路互不可達 → 決定合併成拿一次放一次（是 solver 決策，MOST 不決定合不合）。

### D3 — tool_action（acquire/use/release）的生成機制

（User 裁決 2026-09-06：採自動推導為主 + 互動確認 + 即時驗證）

**背景約束**：使用者一張 WI 可能填數百個 row，介面不能複雜；且有 LLM 解析語句轉 MOST model 的 pipeline。
→ tool_action 必須**盡量自動推導**，人只在少數模糊處確認/覆寫。

**四層設計**：

1. **從 MOST model 語義自動推導**（規則引擎與 LLM 共用同一套邏輯）。技術前提：v2 vocab 有
   `kind='tool'`（實讀 `models/v2/vocab.py:21` CHECK 約束含 `'tool'`），可分辨「工具」vs「被加工物件」。

   | MOST model 特徵 | 推導 tool_action |
   |---|---|
   | G（取得）對象 = `kind='tool'` 詞彙，且該 tool 尚未持有 | `acquire` |
   | model 用到已持有的 tool（CM 使用工具/X process） | `use` |
   | P（放置）對象 = `kind='tool'` 詞彙，放回 | `release` |
   | 無 tool，或對象是 `kind='object'` 等非工具 | 空（無 tool_action） |

2. **後端持有狀態機做配對**（不靠人手想「第幾次拿、要不要放」）：
   - G 取得未持有的 tool X → `acquire`，X 進持有集合。
   - 後續用到已持有 X → `use`。
   - P 放置持有中的 X → `release`，X 出持有集合。
   - 一段結束仍有 X 在持有集合 → 即時提示「X 拿了沒放，補放下？」。

3. **LLM 只做粗判，精確配對交後端狀態機**：LLM 解析語句時只抽「用到某工具、動作是取得/使用/放下」的
   粗略角色（延伸既有 object/tool 角色抽取）；**跨句 lifecycle 配對交後端確定性狀態機**——因為 LLM 跨數百句
   維護持有狀態不可靠（會在第 300 句忘記前面拿了沒放）。

4. **互動介面輔助**（處理「填數百次要方便」）：
   - 每個涉及 tool 的 row 顯示推導結果 badge（🔵acquire / 🟢use / 🟠release，沿用 Level System 視覺語言）。
   - badge 是**推導預設值**，正確就不動（多數情況免手動）；點 badge 可下拉覆寫，覆寫後系統記住不再自動改。
   - 主要流程：LLM 貼一段描述 → 自動產一串 row + 自動推導 tool_action → 使用者掃一眼 badge、只改少數錯的。
     **不是一格一格填數百次。**

5. **即時驗證（MOST 端就擋，不等 LB）**：持有狀態機即時檢查 lifecycle 良構（acquire→use→release 配對），
   拿了沒放在當下提示，不等匯出 LB 才 Fail-Fast。

### D4 — cub → LB `group`（不可拆站）；新增 worker_cub → LB `atomic_group`（不可拆動作）

（User 裁決 2026-09-06）

- **v2 cub（同站不可拆）對齊 LB `group`**（不可拆站，管空間：同一工站；站內誰做/順序/插什麼不管，LB 契約 §3.7）。
- **新增 `worker_cub` 概念，對齊 LB `atomic_group`**（不可拆動作，管人+時間：同一 worker 連續做完、中間不插別的，LB 契約 §3.8）。v2 目前無此概念。
- 兩者**正交獨立**（LB 契約 §3.8）：一組可只同站、可只同人連續、可兩者、可都不。
- **命名**：對齊後兩邊概念語義相同，命名做 mapping：MOST `cub`↔LB `group`；MOST `worker_cub`↔LB `atomic_group`。
  （「LB 投影層」等內部代號僅本文件/對話指稱用，非產品名。）
- **UX（在 Level System 介面，沿用既有圈選成組互動）**：
  - cub（同站組）：既有視覺 🔒 琥珀。
  - worker_cub（同一人連續組）：新增視覺（建議 👤 紫色鎖），與 cub 用不同顏色/圖示區分，一眼看出「空間限制 vs 人力限制」。
  - 使用者拖選一組 row → 選「設為同站組(cub)」或「設為同一人連續組(worker_cub)」，或兩者都設（正交）。

### D5 — MOST→LB 屬性推導層（後端單一權威翻譯層，無獨立 UI）

（User 裁決 2026-09-06）

**定位**：這是一個**後端的確定性翻譯邏輯**，把 MOST 資料（model + level 分組 + vocab）翻成 LB task CSV
需要的所有衍生屬性。**它沒有自己的 UI**——使用者所有互動都在 **Level System 介面**；本層是 Level System
匯出 CSV 路徑背後的一段後端邏輯（內部代號「LB 投影層」，非產品名）。

**為什麼要收斂成單一模組（User：不做好會亂掉）**：tool_action、predecessors、group/atomic 對映、quantity 語義、
offline… 這些推導若散在 LLM prompt／前端／後端各處，會有多份不一致的真相。收斂成單一層 → LLM、規則、UX badge、
CSV 匯出**全部呼叫同一權威**（與 v2 對 TMU「單一權威引擎」同哲學）。

**分工原則（定案）**：**LLM 只做它能解析的（語言 → 粗略角色 + tool 取/用/放粗判）；其餘（group/worker_cub 等
工藝約束）交使用者透過 Level System 互動介面設置。** 所有確定性推導（狀態機配對、拓撲排序、屬性對映、驗證）
在本層，不放 LLM（LLM 跨數百句維護狀態/拓撲不可靠）。

**本層內部推導邏輯清單（暫定名，實作時細化）**：

| 推導邏輯 | 職責 | 自動程度 |
|---|---|---|
| ToolLifecycleResolver | vocab `kind='tool'` + G/P + 持有狀態機 → acquire/use/release（D3）| 高（自動）|
| PrecedenceProjector | level 主序(1/1~2/1/3)+分組 → LB `predecessors` + 拓撲排序 + task_id 單調編號 | 高（確定性）|
| StationGroupMapper | cub → LB `group` | 高（直接對映）|
| AtomicGroupMapper | worker_cub → LB `atomic_group` | 高（直接對映）|
| QuantityProjector | frequency/quantity → LB `quantity`+`qty_scope`（語義待 T1 定）| 中 |
| OfflineMapper | offline 標記 → LB `offline_flag` | 高 |
| MergeCandidateHinter | 從 tool lifecycle **建議** worker_cub/merge 候選（不自動生效）| 中（建議）|
| CsvContractValidator | 匯出前跑 LB 契約 §4 全部 Fail-Fast 自檢（含 D6 傳染一致性）| 高（確定性）|

**group/worker_cub 的自動化界線（重要）**：tool_action 有 `kind='tool'` 這個確定訊號 → 可自動推導；
但 group/worker_cub 是**現場工藝決策**，語句本身推不出（「插HDD、鎖螺絲要不要同一人連續」取決於工站設計）。
→ **LLM 不亂猜工藝約束**；本層只在有明確訊號（如同一 tool lifecycle 的 row）時**建議候選**讓使用者一鍵確認，
不自動生效。假約束比沒有更糟（LB 會據此算錯）。

### D6 — 組內約束傳染（設組即同步傳染性屬性；匯出前再驗）

（User 裁決 2026-09-06，關鍵）

一個組（cub/worker_cub）不只是「圈在一起」，還會**強制組內成員某些屬性一致**（LB 契約 §3.7/§3.8/§4 的 Fail-Fast）：

- **cub（LB group）內**：`offline_flag` 一致、`quantity`/`duration_basis` 一致（§3.7）。
- **worker_cub（LB atomic_group）內**：`offline_flag` 一致；成員 `quantity` ≤ 1；不得跨多個不同 cub(group)；
  成員不參與 tool merge（§3.8）。

**落實兩處**：
1. **Level System UX 設定時即時傳染/檢查**：例如把組內一個成員設 offline → 提示「整組將設為 offline」並自動同步；
   違反 worker_cub 的 quantity≤1／跨組等硬規則時即時擋。**對「填數百次要方便」有幫助**——系統自動傳染，
   使用者不用手動把整組每個都設一次。
2. **投影層 CsvContractValidator 匯出前再驗一次**（確定性最後防線，對齊 LB §4 自檢清單）。

### D7 — frequency ↔ quantity：同義（單件內重複次數），但投影時必須「拆乘數」

（User 裁決 2026-09-06，實讀 v2 code 佐證）

**語義對齊（定案）**：v2 `frequency` = LB `quantity` = **單件內這個動作重複幾次**（鎖 8 顆螺絲 = frequency 8 = quantity 8）。
兩者同義。LB 也只做**一個 unit**，不考慮批量多件。
- 實讀佐證：`most_engine/calculate.py:315-319` `eff = r.total_tmu * freq`（frequency 是 TMU 乘數）；
  `most_compiler/policies.py:294-299` docstring「quantity 掛在 process/move_place → frequency=N」「quantity.value 是
  frequency（TMU 乘數）的唯一輸入」；`models/v2/worksheet.py:118` `frequency Numeric(10,3)`, CHECK `>0`。

**關鍵陷阱：投影時必須「拆乘數」，不可重複乘（會亂掉的核心點）**：
- v2 端 frequency **已經乘進 TMU**（`eff_tmu = total_tmu × frequency`）。
- LB 端要的是**分開的**：`duration` = **單次**工時（＝v2 `total_tmu`，**未乘 frequency**）＋ `quantity` = frequency，
  由 **LB 自己依 cyclic/setup 決定乘不乘**。
- **QuantityProjector 鐵則**：送 LB 的 `duration` 必須是**單次**（`total_tmu`，未乘 freq），frequency 放進 `quantity`。
  **絕不可送已乘的 `eff_tmu` 又同時送 quantity**——否則 LB 再乘一次 → 8 變 64（重複乘）。這是投影層最需嚴防的錯誤。

**cyclic / setup 不能純自動推（定案）**：
- 語義（User 釐清）：**setup**＝拿一次做很多（螺絲起子拿 1 次、鎖 8 顆，拿取不隨物件放大）；
  **cyclic**＝隨物件重複（鎖螺絲 8 顆做 8 次）。
- **同一種「拿工具」有時 setup、有時 cyclic**（User 確認：有時拿一次做 8 顆，有時每顆都重拿放）——
  **故不可只看 tool_action 硬推**。
- 設計：QuantityProjector **自動建議預設**（tool acquire/release → 預設 setup；一般加工動作 → 預設 cyclic），
  **但使用者可在該組覆寫**（同 tool_action badge 的「自動建議 + 少數點改」互動哲學）。
- 對齊 LB `qty_scope`（auto/setup/cyclic，LB 契約 §3.5）：MOST 端算出的 setup/cyclic 即對映 LB `qty_scope`。

> **追記（2026-09-11 晚，ADR-035 D3／D4）——MOST 有兩個乘數，本條只拆了一個**：`frequency`（列級，乘整個 motion）之外還有 slot `repeat_count`（E4，只乘 G/P/M/X/I，A/B 禁止；`calculate.py:50`）。「拿一次電批鎖 8 顆」正確的 MOST 表達是 `repeat_count=8` 於 M/X/I，不是 `frequency=8`。投影：`repeat_count` → use 列 `quantity=N, cyclic`、acquire／release `setup`；`frequency`（整數）→ 非持工具 motion 的 `quantity=F, cyclic`；持工具 motion `frequency>1` 依字面輸出全 cyclic ＋警告；兩者同時 >1 拒絕。NL compiler 的 `resolve_frequency` 演進為 `resolve_multiplier`：持工具 action 的數量落 `repeat_count`（ADR-035 D4）。完整矩陣 Spec §3.2；單次工時由引擎重算（§3.3）。本條「cyclic / setup 不能純自動推」的結論**由此收窄**：對持工具 motion，setup／cyclic 由七格結構決定，IE 不需標；`qty_scope` 只在 IE 用 frequency 標非持工具批量時才是 cyclic。

### D8 — level 主序/自由度 → LB `predecessors` DAG（PrecedenceProjector 核心）

（User 討論定案 2026-09-06 ~ 2026-09-08）

**表達方式（定案）**：MOST 輸出**顯式 DAG 邊**（滿足 LB `predecessors` 硬邊介面，LB 核心 CP-SAT+RCPSP+DAG 不用改）。
理由：DAG 不只餵 CP-SAT 排程偏序，還要支撐 **offline 橋接**（拔節點、祖先接後代，LB 契約 §3.1）——
這種圖操作**需要明確的邊**，用「level band 偏序」等模糊偏序做不出乾淨的祖先橋接。故顯式 DAG 是必要的。

**自由度（`~`）的正確表達 = 有界的平行，不是無邊（關鍵，修正過的結論）**：
- 天真做法「自由度 = 無邊」**是錯的**。原因（User 的致命提醒）：無 predecessor 的 task 不只是「可平行」，
  它是**完全無位置約束**——CP-SAT 為了**線平衡**會把它配到任意站/任意工人（我們 LB 的 CP-SAT 有考慮線平衡）。
  這違背 `1~2` 的原意（「第 1 或第 2 主序」是**有界**自由，不是「隨便哪裡」）。
- 正確做法：**用範圍的上下界框住**——
  - task 的 `predecessors` = 比其 level 範圍**下界更早**那層的 task（下界框住「不能更早」）。
  - 比其 level 範圍**上界更晚**那層的 task 反向把它列為 `predecessor`（上界框住「不能更晚」）。
  - 範圍**內**與它 level 重疊的 task 之間**無邊** → 可平行（對齊 LB P1：DAG fork = 無 predecessor 關係）。
  - 結果：範圍內平行、範圍外框死，**不會因線平衡亂跑**。

**逐情境驗證（predecessor 可否表達）**：
- 單點 `level=2`：predecessors = 所有 level 1；且所有 level 3 把它當 predecessor。✅
- 連續範圍 `1~2`：predecessors = level 0（下界更早層）；level 3 把它當 predecessor（上界更晚層）；與 level 1/2 平行。✅
- 離散跳號 `1/3`（可 1 或 3、排除 2）：predecessor 是區間偏序、無法表達「排除中間層」。❌
  **裁決：`1/3` 不設計**——User 確認現場工序天然有先後，無此情境（就算對前層無直接 depends，也會被其他 dependency 拉住）。
- 群組（sub/cub）＋範圍：組內 order 用組內 predecessor 鏈；整組的 level 範圍用上法框住。⚠️ 可表達，實作時分兩層處理。

**浮動 task 軟警示（防呆，採 (b)）**：
- 投影層產出 DAG 後，偵測「既無 predecessor、也不被任何人當 predecessor」的**無界孤立 task**。
- **(b) 軟警示（warning，可匯出）**：提示「此 task 無任何前後約束，可能被 LB 為平衡配到任意站，確定嗎？」不硬擋。
- 依據：User 現場通則「實務上不會有真正浮動 task（會被其他 dependency 拉住）」→ 平常不觸發、不擾民；
  一旦觸發即抓到「使用者漏標 dependency／LLM 解析漏依賴」的真實錯誤，在 MOST 端當場抓比送 LB 亂配後才發現好。
- 呼應 v2 既有防呆：`most_engine/level.py` 已有 `R3_ORPHAN`（非 main 獨立列、無 countersignature = 歸屬不明報錯），
  本規則是它在 DAG 層面的延伸。

**offline 節點**：照常進 DAG（標 `offline_flag`、predecessors 照生成），**橋接交 LB**（LB 契約 §3.1 由 LB 做祖先橋接）；
MOST 端不做橋接、只產含 offline 節點的完整 DAG。

**責任歸屬（對齊 LB 契約 §1.2/§6）**：PrecedenceProjector 產出邊後，須做**拓撲排序 + task_id 單調重編號**
（predecessor id < 自己 id），這是 MOST 端責任（見 T3）。

### D9 — segment（批量分攤向量綁定）：保證「參與者+件數一致」，不保證工件級

（User 討論定案 2026-09-09，依新版 LB 契約 §3.5「segment 保證程度」，附 code 出處 `quantity_lot.py`/`QuantityLotConstraint`）

**現場情境（User 確認有）**：插 8 個 DIMM + 鎖 8 個卡榫，分 2 人時「同一人插又鎖他負責的那幾個」。

**segment 保證程度（新契約明確）**：
- segment key = `{group}:{segment}`，**依附 `group`；無 group 則 segment 失效**（key 湊不出來）。
- **保證**：同一組 worker 參與 + 每人在各工序間分到的**件數一致**（A 在「插」分 3 件 → A 在「鎖」也鎖 3 件，且是 **A 本人**）。
- **不保證工件級對應**：模型無單顆物件 identity，**不保證 A 插的「那 3 顆」= A 鎖的「那 3 顆」**，只保證數量與參與者一致。
- **鐵則**：**MOST 不得對下游承諾 LB 做不到的工件級追蹤**。對產線平衡（算工時負載）而言，「參與者+件數一致」已足夠。

**DIMM 情境的正確標法（定案）**：兩 task 同 `group`（同站，Q>1 強制）+ 同 `segment`（共用分攤向量）+
`quantity=8` + `duration_basis=once` + `qty_scope=cyclic`。接受「不保證同一批物件、只保證 A 插 N 鎖 N 且 A 本人」。

**segment 與 group/atomic_group/p2 的維度區別**（新契約 §4 差異表，務必分開標，避免混淆）：
- `group`＝空間（同站）；`atomic_group`(worker_cub)＝同一人時間連續；`segment`＝批量分攤向量；`p2`＝批量人數鎖。四者正交。

**segment UX（MOST 端）**：圈選一組**批量 task（Q>1）**設為同 segment；同 segment 必同 group（依附）、
且 quantity/duration_basis/p2 須一致（D6 式組內傳染 + 匯出前 CsvContractValidator 驗）。

### D10 — p2：MOST 不填，由 solver 決定人數

（User 裁決 2026-09-09）

- **新契約澄清 p2 語義**（§3.4，更正舊契約誤解）：p2 **不是**「多人合力做一件更快」，而是**掛在 quantity lot 上的
  「人數鎖」**——只在 `quantity>1` 生效，凍結「這批剛好 k 個 worker 分攤」（`sum(used[w])==k`）。Q=1 時被忽略。
- **裁決：MOST 一律不填 p2**——目前批量分攤的人數**由 LB solver 自由決定**（不填 = solver 自決）。
- 註：先前「捨棄 p2」的理由（以為 p2=多人合力、現場無此情境）已被新契約更正；**正確理由是「人數交 solver 決定」**。
  未來若現場出現「某批必須固定 k 人分攤」的硬需求，再於該批量列補 `p2=k`（k≥2、同 (group,segment) 一致）。

### D11 — Quantity（Q>1）的強制硬規則（投影層 CsvContractValidator 必須擋）

（依新版 LB 契約 §3.5，Fail-Fast）

Q>1（batch）的列，投影層匯出前必須保證（否則 LB Fail-Fast 拒整份）：
- **必須有 `group`**（Q>1 無 group → 拒）。
- **必須有 `duration_basis`**（建議 `once`，`duration` 為一件工時；缺 → 拒）。
- **同一 `group` 的 `quantity`/`duration_basis` 一致**；同 `(group,segment)` 的 `p2` 一致（本輪 p2 不填，恆一致）。
- **Q>1 與 `divisible=1`、tool merge、`atomic_group` 互斥**。
- Q>1 只支援 LB 的 MULTI_LINE 模式（MOST 端無須處理，但需知此限制）。
- `qty_scope`/`duration_basis` 值域正確（`auto|setup|cyclic` / `once|lot_total`）。

這些併入 D5 的 CsvContractValidator（匯出前確定性自檢，對齊 LB 契約 §5 清單）。

### D12 — offline_flag：純手動標（不自動推），配合組內傳染

（User 裁決 2026-09-09）

- **純手動標**：使用者逐 row 在 Level System 切換 offline（建議與 tool_action badge 同區的 row 層級標記）。
- **不自動推導**：與 group/worker_cub 同理——offline 是**現場物理佈局決策**（此工序有沒有預先在離線區做），
  語句本身推不出；亂推會產生**假 offline** 讓 LB 把該工序工時歸零、算錯平衡。故 LLM/規則不猜，交使用者標。
- **組內傳染（D6）**：組（cub/group、worker_cub/atomic_group）內一個成員標 offline → 整組同步 + 提示
  （LB 契約 §3.7/§3.8：同 group、同 atomic_group 的 offline_flag 必須一致）。
- 與 General task 的關係：General（`part_id=General` 跨零件通用取放）常也是 offline，但兩者是**獨立標記**，
  不互相自動推導（General 判定見 LB 契約 §3.6，本輪未納入 MOST 自動判定範圍，如需再議）。

### D13 — 雙向同步地基（屬性可雙向、結構單向；時序待 LB 回傳契約）

（User 裁決 2026-09-10）

**背景**：兩套系統是**雙向**的——MOST 產 CSV → LB 跑平衡 → 使用者在 LB 端可改 → 可能反過來影響 MOST。
故「對齊」是硬需求，且 task 需要跨系統穩定 identity。

**核心分界（原則：屬性可雙向、結構單向）**：
- **屬性類（可在 LB 端改，回流 MOST）**：`offline`（及未來類似屬性標記，LB 端開發中）。改的是「掛在 task 上的標籤」，
  不破壞工序邏輯結構，可安全回流。
- **結構類（LB 端唯讀，引導回 MOST 改）**：`predecessor`／工序關聯／DAG 結構。改結構＝改工序邏輯，
  這是 **MOST 的核心職責與權威**（如同 TMU 權威在 v2 引擎）。LB 發現結構問題 → **引導使用者回 MOST 改、重產 CSV**，
  不在 LB 端硬改回塞。**LB 不得成為工序結構的第二權威。**

**屬性回流規則**：
- **必須進 MOST 正門**：回流的屬性走 MOST 的驗證 + D6 組內傳染，**不直接寫 DB 繞過治理**
  （與 v4 整合「不繞過 v2 治理」同理）。MOST 是屬性回流後的記錄權威。
- **兩邊都做組內傳染**：LB 端改 offline 時 LB 自己也會把整組改成 offline（與 D6/LB §3.7-3.8 同規則）；
  回流 MOST 時 MOST 再走一次自己的傳染驗證（雙重保險、結果一致、不衝突）。

**跨系統對應鍵（定案）**：
- **用 v2 穩定 `wi_row.id` 作跨系統對應 identity**（CSV 多帶一欄，如 `source_wi_row_id`），LB 記住、回流時帶回。
- **`task_id` 只是該份 CSV 的拓撲排序連續編號（會 renumber，不穩定）**，不作跨系統對應鍵——否則加 row/重排後對應會斷。

**時序（待定）**：屬性回流→是否「MOST 更新→重產 CSV→LB 重跑」的循環，或「LB 就地改、MOST 只更新記錄」——
**待 LB 端回傳契約出來再定**（LB 端功能開發中）。註：offline 改動會影響 DAG 橋接（哪些節點被跳過），
故屬性回流可能間接需要重產 CSV，此時序細節待定。

### D14 — CSV `action` / `action_type` 的語言（i18n）

（User 裁決 2026-09-11：按建議案）

- **`action` 欄送 `narrative_en`（英文）**：因 LB 端目前全英文，General task 判定（LB §3.6 比對 take/scan/transport
  類關鍵字）用英文；`action` 必須是英文 LB 才判得出。
- **`action_type` 送英文短 code**（pick/scan/put）：語言中立的機器分桶鍵（merge 用，D1 更正），不隨 locale 變
  （對齊 ADR-032「label 語意不隨 locale 變」）。
- **中文 `narrative_zh` 不佔 LB schema**：靠 `source_wi_row_id`（D13 對應鍵）對回 MOST 取得（雙向同步本就有此鍵）。
  「action 送雙語」的精確落地＝英文進 CSV 供 LB 用、中文靠對應鍵回 MOST（不塞雙語字串進單一 action 欄，
  以免污染 LB 的英文關鍵字比對）。
- **相依警告（重要）**：ADR-032 的 `narrative_en` 是選填、可能為空（fill-then-fix，英文靠 i18n review 逐步補）。
  **要餵 LB 的 row，其 `narrative_en` 必須已補齊**，否則 LB 的 `action` 為空 → General 判定/顯示失效。
  **投影層 CsvContractValidator 匯出前須檢查「要送 LB 的 row 是否缺 `narrative_en`」並警示**（連結 ADR-032 i18n review：
  先補齊英文再匯出 LB）。這是「餵 LB」與「ADR-032 雙語資料」之間的真實相依。

### D15 — SIMO（雙手同動作）→ LB：新增 SIMO 綁定欄位（方向定，待 LB 端確認）

（User 裁決方向 2026-09-11，源自 IE 審查 H1 阻擋級漏洞）

**問題（IE 審查 H1，主流程查證屬實）**：v2 SIMO 是一等公民（`wi_rows.simo_group_id`；`calculate.py:318-322`
SIMO 從屬列貢獻 **0 TMU**，時間由主列吸收，ADR-020；`export_service.py:45/86` 已輸出 simo 欄）。
但 D1–D14 原本**完全沒對映 SIMO**。若照 D1「一 motion=一 task、duration=該列 total_tmu」直接送，
**SIMO 從屬列會以 duration=0 進 LB**，被當「零工時可獨立分站工序」→ 低估站別負載、把雙手同時做的兩件事拆到兩站。

**SIMO 語義**：同一人、**同一時刻並行**做多動作，**時間取 max 不相加**（比 group「同站」、atomic_group「同人連續」都強——
那兩者仍是時序上分開做）。LB 現有 group/atomic_group 表達不了「同時並行、取 max」。

**方向（User 傾向，定案待 LB 端確認）**：**在 LB 新增 SIMO 綁定欄位**（如 `simo_group`），語義＝「這組 task 同一人同時並行、
工時取 max、不可拆」。走此路則 MOST 主列＋從屬列**都輸出**、標同一 `simo_group`，**LB 端需新增 SIMO 的 max 計算邏輯**
（從屬列不再是 0，而是參與 max）。理由：符合「MOST 給完整資訊、LB 做計算/決定」的一貫邊界（同 D7 不預先塌縮）。

**過渡方案（LB 未支援 SIMO 前）**：MOST 端沿用既有處理——從屬列 0 TMU、主列 duration 已吸收 max；
匯出時**從屬列不輸出為獨立 task**（避免 duration=0 汙染），只送主列（duration=雙手 max）。缺點：LB 不知雙手作業、
未來人因/視覺化無資訊。**此為過渡，非終態。**

**待 LB 端確認**：LB 是否願新增 SIMO 欄位 + max 計算（列入「待向 LB 端提供/釐清」）。在確認前，投影層先走過渡方案
（從屬列不輸出），並在 CsvContractValidator 標記「本份 CSV 含 SIMO、已用過渡塌縮」供追溯。

### D16 — machine_count / manpower 不送 LB：並行分攤是 LB 職責

（User 裁決 2026-09-11，解決 IE 審查 H2）

**背景（IE 審查 H2「三者矛盾」）**：v2 `level_entry` 有 `machine_count`/`manpower`（`worksheet.py:187-188`）、
`to_lb_csv` 現況在送（`export_service.py:118/130`）、level-spec §6.2 說「機台/人力→時間÷N」；但新版 LB CSV 契約移除這兩欄。

**查證真相**：這兩欄在 v2 code **從未被任何計算消費**（僅 worksheet_service 存取搬運、export 送 CSV；無「÷N」實作）；
spec §6.2「時間÷N」是教學檔轉述、v2 從未實作，且 §13 Q4「N 怎麼定」一直懸而未決。

**裁決：machine_count/manpower 對 LB 不需要、不送。** 因為「並行/時間÷N」是 **LB（CP-SAT/RCPSP）的職責**，
且它其實是兩種已涵蓋的情況（皆由 LB 端使用者跑 solver 前設 `max_manpower` + solver 動態決定）：
1. **DAG fork 平行（P1）**：`max_manpower>1` 時 solver 把 DAG 分岔分給不同 worker（RCPSP 本職，見 D8）。
2. **frequency/quantity 分攤**：一工序做多次（插 64 顆硬碟 quantity=64），solver 視情況分給不同 worker（見 D7/D9）。
   「除以 N」真正只對應**這種**，且由 LB 算（MOST 送 quantity，不預先除）。

**結論**：
- 新版 LB 契約移除 machine_count/manpower 是**對的**；MOST 不送、不算「時間÷N」（同 D7「不預先塌縮、讓 LB 算」哲學）。
- v2 `to_lb_csv` 現況仍送的這兩欄，對齊後**應移除**（實作階段）。
- `level_entries` 的 machine_count/manpower 是純儲存、無計算用途——**是否保留欄位另議**（廢除或留作他用皆不影響計算）。
- **已回頭更新 core-logic**：`docs/core-logic/level-system-core-logic-spec.md` §6.2 加註取代、§13 Q4 標記已裁決
  （「並行是 LB 職責、不用定 N」）。

### D17 — 新增 `role_type` 欄位：區分執行資源類型（解決 H3 機器時間；為未來機械手臂鋪路）

（User 裁決 2026-09-11）

**H3 解**：機台製程時間**算機台時間、不算人力**。實現不用 offline（語義不對），而是**新增 `role_type` 欄位**區分執行資源。

**值域**：`human`（人工，預設）／`machine`（機台製程，如並壓合/並熱熔）／`robot`（機械手臂，未來）。可擴充。

**半自動推導**（投影層，同 tool_action「確定訊號自動、其餘預設」哲學）：
- X `mode='seconds'`（機台製程，如 `x_press` 並壓合機台、`x_heat` 並熱熔機台，`rule_x_options.mode`）→ 自動標 `machine`
  （這是確定訊號，如同 tool_action 用 `kind='tool'`）。
- 一般 A/B/G/P 人工動作 → 預設 `human`。
- `robot`：v2 目前無此概念，未來手動或另有來源。

**machine task 仍進 DAG（與 offline 不同維度，關鍵）**：
- machine task **要輸出給 LB**、保留 `predecessors`/DAG 位置（後面的人工動作要等機台跑完）。
- `role_type=machine` 讓 LB **人力平衡時不把這段算進 worker load**（否則高估人力）。
- **與 offline 區別**：offline＝不佔線上節拍、被 LB 橋接跳過（D8/§3.1）；machine＝**佔線上時間**（後面要等）、
  **但不佔人力**。兩者正交，故用 role_type 而非 offline。
- `duration` = 機台製程時間（X seconds → ms，D7 同換算）。

**前瞻價值（User）**：未來 LB 要處理機械手臂相關時間，MOST 端先用 role_type 分好類，LB 後續按資源類型排程即有依據
（提前分類，符合「MOST 給對的資訊、LB 做決定」）。

**待 LB 端確認**：`role_type` 是 LB CSV 新欄位（目前契約無）；LB 端需能讀 role_type 並在人力平衡時據此分類
（human 算 worker load、machine 不算、robot 未來）。列入「待向 LB 端提供/釐清」。

### D18 — motion 拆列、兩個乘數、分層 DAG 與匯出前 Fail-Fast（正式化為 Spec + ADR-035）

（User 裁決 2026-09-11 晚；本條只作索引，內容以 Spec 為準）

- **粒度**：1:1 預設；持工具 motion 確定性拆 acquire／use／release（Spec §2、ADR-035 D2）。→ 解決 IE 審查 **H6**（一列內 setup+cyclic 混合）與 D1 例外。
- **乘數**：`frequency` vs slot `repeat_count` 的投影矩陣（Spec §3.2）；單次工時由引擎重算（§3.3）；compiler `resolve_multiplier`（ADR-035 D4）。
- **工具生命週期**：chain 內確定性狀態機、Pattern A／B 皆支援、`tool_id` 來自詞彙 `name_en`、acquire 列 `action_type` 恆 `pick`、`adjustable` 預設 1、`merge_lock` 標記（Spec §4）。→ 精確化 D2／D3。
- **分層 DAG**：Level System 是分層模型；層間邊＝`hi_Y < lo_X` 偏序的傳遞縮減；巢狀 cub 以 seq_no 定位；`a/b` 拒收；general 排除；nb 不輸出（Spec §5）。→ 精確化 D8，並明文 `build_output` edges 不可沿用。
- **欄位**：24 欄（21 LB 標準 ＋ `source_wi_row_id`、`role_type`、`general_role`）順序凍結；`p2`／`complexity_level` 恆空；`qty_scope` 不輸出 `auto`（Spec §6）。
- **資料模型**：`level_entries` 加 `worker_cub／offline／segment／station_pin／is_general／merge_lock`（ADR-035 D7）。
- **驗證**：MOST 端匯出前 E／W 碼＋報告（Spec §8）；過渡守衛「同 tool_id 不得同時出現於 Q>1 與 Q=1 episode」（LB ADR-001 追記缺口）。
- **黃金 fixture**：`fixtures/server_node_*`，已實跑 LB 端驗證通過；TMU 守恆 2 603.445 TMU＝93 724 ms。
- **落地**：`LB_PROJECTION_IMPLEMENTATION_PLAN.md` WP0–WP12；agent prompt `AGENT_BRIEF_LB_PROJECTION.md`。

### 待處理（IE 審查 2026-09-11 發現，尚未定案）

IE 領域審查（`IE_REVIEW_MOST_LB_CONTRACT.md`）點出的其餘缺口，狀態更新（2026-09-11）：
- ~~**H2 machine_count/manpower**~~ ✅ **已解決 D16**（並行是 LB 職責、不送這兩欄；已更新 core-logic spec §6.2/§13 Q4）。
- ~~**H3 X 機器處理/等待時間**~~ ✅ **已解決 D17**（新增 `role_type`：machine 算機台時間不算人力；X seconds mode 自動標 machine）。
- **H4 走動(A)時間 vs 佈局循環依賴** ✅ **接受為已知限制**（User 2026-09-11）：MOST 在 LB 決站別前用假設佈局算走動 TMU，
  屬 MOST/LB 整合固有難題；本輪不解，標記為已知限制，未來若走動時間佔比大再議。
- **D8 vs build_output 落差** ✅ **記為實作註記**（定案）：現況 `build_output` 的 `precedence_edges` 只是 level_min 保守相鄰鏈、
  只連 has_main 列，**未實作 D8 完整上下界框法**。**實作鐵則：PrecedenceProjector 須依 D8 重新生成，不可直接沿用現有 edges。**
- **worker_cub 成員 frequency>1 即時擋** ✅ **併入 D4/D6 UX 硬規則**（定案）：設 worker_cub 時，成員 frequency>1（=LB quantity>1）
  違反 LB atomic_group 成員 quantity≤1，UX 即時擋、投影層 CsvContractValidator 匯出前再驗。
- ~~**D7 一列內 setup+cyclic 混合**~~ ✅ **已解決 D18**（投影層依七格結構拆列；IE 不拆 motion；乘數用 `repeat_count`）。

---

## 新版 LB 契約（2026-09-09）帶來的更正摘要

新版 `TASK_CSV_INPUT_CONTRACT.md`（附 code 出處）修正了前面幾則基於舊契約的認知：

1. **merge 分桶鍵 = `action_type`（不是 `action`）**：更正 D1；D2/D3 的 tool merge 需額外產出 `action_type`
   短標籤（pick/scan/put…）作分桶鍵，`action`（narrative）只用於 General task 判定。
2. **p2 語義**：非「多人合力」，是「批量人數鎖」→ D10（MOST 不填）。
3. **segment 保證程度明確**：參與者+件數一致、不保證工件級 → D9。
4. **移除欄位**：`eligible_worker_types`、`duration_robot_ms`（MOST 不要輸出，LB 從 CSV 不讀）。
5. **merge 候選完整資格**（§3.2）：`adjustable=1` + 非 offline + `quantity≤1` + 非 atomic_group + 同 `(tool_id, action_type)` +
   DAG 互不可達 + 工具生命週期良構（每 acquire 有唯一 clean release、每 use 被 episode 覆蓋）。D2/D3 的即時驗證要對齊這份。

---

## 待討論（後續逐題）

> 依 User「一個一個來」的節奏。下列為已識別、尚未定案的對齊題目。

### T1 — 邏輯對齊表：LB 概念 ↔ MOST 概念（語義對齊，命名後做 mapping）
把 LB 的 `group` / `atomic_group` / `offline_flag` / `quantity`+`qty_scope` / `p2` / `predecessors`
逐一與 MOST 的 main/sub/cub/nb/level 自由度/frequency 對齊語義。
**釐清進度**：
- ✅ v2 cub ↔ LB `group`（不可拆站）；新增 `worker_cub` ↔ LB `atomic_group`（不可拆動作）——**已定案 D4**（正交分開）。
- ✅ v2 `frequency` ↔ LB `quantity`（單件內重複次數，同義）；投影須拆乘數＋cyclic/setup 半自動——**已定案 D7**。
- ✅ v2 level 主序/自由度 → LB `predecessors` 顯式 DAG（`~`用上下界框住、`1/3`不做、浮動軟警示、offline 交 LB 橋接）——**已定案 D8**。
- ✅ `segment`（批量分攤向量綁定）——**已定案 D9**（保證參與者+件數一致、不保證工件級；依附 group）。
- ✅ `p2`（批量人數鎖）——**已定案 D10**（MOST 不填，solver 自決人數）。
- ✅ `qty_scope`（cyclic/setup）——**已定案 D7**（tool_action 預設 + 使用者可改）。
- ✅ Q>1 硬規則——**已定案 D11**（必須 group + duration_basis；一致性；互斥）。
- ✅ `offline_flag` 單列設定 UX——**已定案 D12**（純手動標、不自動推、組內傳染）。

**→ T1 邏輯對齊表全部定案（D4/D7/D8/D9/D10/D11/D12）。**

### T2 — 落差與新增
✅ **已定稿**：見上方「T2（定稿）— MOST 端需新增/修改的實作清單」。

### T3 — 責任邊界（MOST 端產 CSV 責任）
**釐清進度**：
- ✅ **拓撲排序 + task_id 單調遞增重編號**（LB §1.2）：投影層 PrecedenceProjector 收尾步驟；
  **拓撲排序須用確定性 tie-break（照 v2 seq_no/wi_row 原始順序），保證同資料→同 CSV（task_id 穩定可重現）**（User Q2 定案）。
- ✅ **時間單位**：`duration` = 單次工時（total_tmu 未乘 freq，D7）→ `total_tmu × 0.036 × 1000` → **ms 整數、四捨五入**（User Q1 定案）。
- ✅ **duration/quantity 拆乘數**（D7）、**Fail-Fast 自檢**（D5/D11）、**據實標記不代 LB 決策**（D2-D12）。
- ✅ **跨系統對應鍵 = v2 `wi_row.id`**（D13），CSV 多帶 `source_wi_row_id`；task_id 只是 CSV 內拓撲編號。
- ⏳ CSV 實際欄位清單與匯出格式細節——實作階段定（大方向已由 D1-D13 齊備）。

### T4 — i18n
✅ **已定案 D14**：`action` 送 `narrative_en`（LB 全英文、General 判定用）；`action_type` 送英文短 code；
中文靠 `source_wi_row_id` 對回 MOST；相依警告——要餵 LB 的 row 須先補齊 `narrative_en`（投影層匯出前檢查）。

### T5 — 寫成正式 SOP/規範文件
✅ **已定稿（2026-09-11）**：見文件開頭「§0 正式 SOP（定稿摘要）」+「T2（定稿）實作清單」。D1–D16 為細節依據。

---

## 待向 LB 端提供 / 釐清（資訊缺口）

1. **LB → MOST 回傳契約（雙向同步協議）目前不存在**（D13）：需 LB 端提供「改了哪些屬性、用什麼 id 對應、
   回流格式、時序」。這是雙向同步完整成立的前提（LB 端功能開發中）。
2. **混合 task 時間粒度的假設**（見下方「待向 LB 端釐清」原記錄）。

---

## 待向 LB 端釐清（資訊不足處，記錄）

1. **混合 task 時間粒度的假設**：LB 契約說 task 是「最小工序單位」並舉例單一動作（拿起掃描槍）。
   但 MOST 的一個七格 model 可能含「取得→移動→放置」多個 MOST 參數格（一次完整移動）。
   LB 對「一個 task 內含多個物理動作、且不同 task 粒度不均」有沒有假設或要求？（D1 已定 1:1，但需 LB 確認
   接受這種「一個 task = 一次完整 GM/CM」的粒度，而非要求拆到單一物理動作。）
