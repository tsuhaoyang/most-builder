# ADR-035：LB 投影層與 motion 拆列——兩個乘數、工具生命週期、分層 DAG 的確定性翻譯

- **狀態**：🟢 **accepted**（2026-09-12，Howard 核可；撰寫內容依 2026-09-11 User 整合討論裁決，另含 2026-09-12 (c) 分桶／(A) 傳遞縮減／(B) action_type 三項裁決）。實作 agent 遇本 ADR 未涵蓋處停下詢問，不得自行擴張
- **日期**：2026-09-11
- **決策者**：Howard（IE／兩系統 owner）＋ 整合架構師（論證與規格）
- **最高原則**：[`docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`](../lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md)（`most-lb-csv-v1.1`）。本 ADR 記錄「為什麼」，Spec 記錄「是什麼」；衝突時 Spec 為準並回修本 ADR。
- **關聯**：
  - [`MOST_LB_CONTRACT.md`](../lb-integration/MOST_LB_CONTRACT.md) D1／D2／D3／D7／D8（本 ADR 修訂 D1 的 1:1、精確化 D3／D7／D8，新增 D18）
  - [ADR-011](ADR-011-schema-evolution-and-contract-stability.md)（加法演進：level_entries 加欄、CSV 尾端加欄）
  - [ADR-014](ADR-014-v3-dictionary-as-value-authority.md)／[ADR-028](ADR-028-most-engine-boundary-validation-and-single-authority.md)（唯一引擎：投影層不做 TMU 算術，單次工時由 `compute_cycle` 重算）
  - [ADR-020](ADR-020-simo-contribution-semantics.md)（SIMO 從屬列貢獻 0 → 過渡期不輸出）
  - [ADR-033](ADR-033-llm-planner-scope-narrowing.md)（`quantity` 暫無供給端；本 ADR 只定 D4 的目的地，不改供給時程）
  - [ADR-034](ADR-034-language-aware-error-contract.md)（匯出 E 碼走結構化錯誤信封）
  - `.kiro/steering/wi-motion-core-structure.md`（兩層結構）
  - LB 端：`docs/adr/ADR-001`（tool closure）、`ADR-008`（quantity lot `units[s,w]`）、`ADR-017`（atomic group）、`TASK_CSV_INPUT_CONTRACT.md`

---

## 1. 脈絡

### 1.1 觸發問題（User 2026-09-11）
「拿起 scanner、掃描、放下 scanner」在 MOST 是**一個 motion**（一條 CM），在 LB 必須是**三列**才能跑 tool merge（ADR-001）與 setup/cyclic 分攤（ADR-008）。契約 D1 寫 1:1、D2 假設 IE 會自然拆三句——與實際 MOST 建模不符。IE 審查已把這件事標為 **H6「一列內 setup+cyclic 混合」**，掛「待 User 確認」。

### 1.2 程式碼事實（2026-09-11 實讀）
1. **MOST 有兩個乘數**：`frequency`（列級，`compute_table` `eff = total_tmu × freq`，`most_engine/calculate.py:319`）乘整個 motion；`repeat_count`（格級 E4，`_repeat` `calculate.py:50`）只乘 G/P/M/X/I，**A/B 禁止**（`_no_repeat`）。後者正是 LB setup/cyclic 的分界，但契約 D7 只拆了前者。
2. **NL 解析器把數量導向錯的乘數**：`most_compiler/policies.py:294 resolve_frequency` 把 quantity 掛成 `frequency=N`；持工具動作（`is_tool_held`，`policies.py:274`）因此變成「拿 N 次」。ADR-033 後供給端暫停（恆 1），但**目的地**沒改。
3. **`to_lb_csv` 尚未對接 LB 契約**：`services/v2/export_service.py:111` 是 Level System 欄位 dump（`seq_no/level/machine_count/manpower`），D5 投影層完全未蓋——沒有既有輸出要相容。
4. **Level System 是分層模型**：`level.build_output` 以 `level_min` 相鄰鏈產保守邊；同 level 的 main 互為平行、下一層依賴上一層。它**不能**表達「F 只依賴 E、不依賴 D」的任意分支——D8 的「上下界框住」正是分層語意，PrecedenceProjector 必須照此實作，且 `build_output` 的 edges 不可沿用（契約已註）。
5. **LB 端驗證通過**：以本 ADR 規則手工投影的 34 列 fixture 已實跑 LB `read_problem_from_csv` → `validate_quantity_contract` → `GroupValidator` → `is_general_candidate` → `detect_merge_candidates`，全部通過；Σ TMU 兩邊相等（2 603.445 TMU＝93 724 ms）。

### 1.3 不做會怎樣
- IE 用 `frequency=8` 標「拿一次鎖 8 顆」→ LB 把取放多算 7 次；用 `repeat_count` → LB 收到黑盒單列，無法分攤、無法 merge。**單列無論怎麼填都不對。**
- 若逼 IE 把拿／用／放建成三個 motion：「拿起 scanner」GM 得用 P=保持住湊數、下一條 CM 的 G 要填重新抓握——方法論扭曲，且與現場 MOST 資料形狀不符。

---

## 2. 決策

### D1 契約 Spec 為最高原則；CSV 表頭凍結
`MOST_LB_DATA_CONTRACT_SPEC.md` 是 MOST→LB 的唯一權威。輸出 24 欄（21 LB 標準欄 ＋ `source_wi_row_id`、`role_type`、`general_role`）名稱與順序由測試凍結；變動即 `contract_version` 升版並同步 LB 契約。既有 `MOST_LB_CONTRACT.md` 降為討論紀錄，逐條指向 Spec。

### D2 粒度：1:1 為預設；持工具 motion 由投影層確定性拆為 acquire／use／release
- 切點是**七格結構**：slot 0–2（A B G）→ acquire；slot 3–5 → use；slot 6（返回 A）→ release。
- 判準是**資料**：`tool_vocab_id` 或 `object_vocab_id` 指向 `kind='tool'` 詞彙。不是 IE 決定、不是啟發式。
- 三列共用 group／segment／quantity／`source_wi_row_id`。**general motion 不拆**（LB General 機制要求單列）。
- SIMO 從屬列**不輸出**（過渡；ADR-020 貢獻 0，LB 尚無 SIMO 欄）。

### D3 兩個乘數的投影語意
- `repeat_count`（slot 3–5）= 持工具動作的 **cyclic 乘數** → use 列 `quantity=N, qty_scope=cyclic`；acquire／release 列 `setup`。單次工時由**引擎**以 repeat 歸 1 重算（`compute_cycle`），投影層不做 TMU 除法。
- `frequency`（整數）= **整 motion 乘數** → 非持工具 motion 的 `quantity=F, cyclic`（每件都伸手抓放，物理正確）；持工具 motion 的 `frequency>1` 依字面輸出三列全 cyclic ＋ **警告**（幾乎一定是 IE 想用 repeat）。
- 兩者同時 >1 於持工具 motion → **拒絕**（單一 quantity 無法表達「F 輪、每輪 N 次」且保住輪次綁定）。
- 非整數 `frequency`：非持工具 → 燙進 duration（Q=1）＋警告；持工具 → 拒絕。
- 完整矩陣：Spec §3.2。

### D4 NL compiler：QuantityPolicyV2——持工具動作的數量落到 `repeat_count`，不落 `frequency`
- `resolve_frequency` 演進為 `resolve_multiplier(action, plan) -> (frequency, repeat_count, reasons)`：`is_tool_held(action, plan)` 為真且數量為整數 → `repeat_count=N` 掛在該 action 的 X／M／I（有值的格），`frequency=1`；非持工具維持 V1（`frequency=N`）。
- **TMU 中性**（現況）：持工具 action 的 G 已留空（已持有）、A0／A6 目前不編（impl-spec §9.2 註 3），故 `frequency=N` 與 `repeat=N` 在現行編譯路徑算出的 TMU 相同——本決策是為 **LB 投影形狀**，不是改工時值。P3 補上 `A6` 後兩者才會分歧，那正是本決策要提前釘住的原因。
- 供給端仍受 ADR-033 D1 管制（`quantity` 暫由 IE 手填／`quantity_policy_review`）；本 ADR **不改**供給時程，只改目的地。既有 gold `expected_cycles` 的 TMU 不變；`cycle["frequency"]` 斷言處需同步（見實作書 WP9）。

### D5 ToolLifecycleResolver：chain 內確定性配對，支援 Pattern A／B
- 事件表與 held 狀態機見 Spec §4.1；Pattern B 的 release 落點以**同 chain 向後看**決定 3 列或 2 列（§4.3）。
- 跨 chain 持有拒絕；chain 結束仍持有拒絕（D3 原則「拿了沒放」在 MOST 端即擋）。
- `tool_id` 來自詞彙 `name_en`；**不同拿取位置＝不同詞彙**。acquire 列 `action_type` 恆 `pick`、release 恆 `put`，並驗同工具取放等長——把 LB 端「`action_type` 作分桶鍵」這個求解器簡化在 MOST 端吸收掉，IE 不需要知道分桶鍵存在。
- `adjustable`：acquire／release **預設 1**；`merge_lock` 標記 → 0。

### D6 PrecedenceProjector：分層偏序的傳遞縮減；巢狀區塊以 seq_no 定位；`a/b` 拒收；general 排除
- 頂層項層範圍 `[lo,hi]` 由 head level 解析；成員與巢狀 cub 繼承。`Y ≺ X ⟺ hi_Y < lo_X`，取傳遞縮減；邊由 Y 的 sink 連 X 的 source。
- chain 內相鄰連邊；巢狀 cub 區塊插入位置＝成員最小 `seq_no`（T3 同一 tie-break；`build_output` 未記錄區塊在母組中的位置，這是唯一確定性且與 IE 列序一致的來源）。
- `a/b` 離散跳號 → 拒絕（D8 User 裁決）。nb → 不輸出＋警告（LB 無欄）。
- 編號：Kahn ＋ `(seq_no, part_index)` 最小優先。

### D7 資料模型：`level_entries` 加 8 個 LB 標記欄（加法演進）
`worker_cub text`、`offline bool`、`segment text`、`station_pin int`、`is_general bool`、`general_role text`（take_unit／scanner／transport；Spec §5.7）、`merge_lock bool`、`action_type text`（IE 選填顯示標籤，Spec §6；2026-09-12 WP6 裁決：結構碼推不出 remove／test 等語意，標籤優先、附錄 A 為 fallback）（＋對應 `LevelFieldsIn`／`read_worksheet`／`api.d.ts`）。`machine_count`／`manpower` **停止匯出**（D16），欄位保留另議。`role_type` 由 X 格推導，不落欄。

> **D7 追記（2026-09-12，Howard 裁決）**：第 9 個 LB 標記 `machine_unattended boolean NULL`（三態：null＝未回答、false＝人要顧、true＝人不用顧）。它是 solver 消費的物理事實（Spec §6 `role_type` 修訂：只有 true 才送 `machine`），與被否決的 `splittable` 不同（那是 LB 結果頁 what-if 許可位，且與 quantity 重疊）。作業版 UI 以「人要在旁邊顧著嗎？」提問，未回答＝要顧。實作：`LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md` §3.4／B7／F10。

### D8 MOST 端匯出前 Fail-Fast（E 碼擋、W 碼報）＋匯出報告
錯誤碼表 Spec §8.1；報告形狀 §8.2。E 碼經 ADR-034 信封（`code=LB_EXPORT_BLOCKED`，`detail.errors[]`）。**不因為 LB 也會擋就不擋**——在 IE 還看得到 motion 的地方報錯，比送到 LB 變 500 好。

### D9 過渡期守衛（LB 缺口未修前）
1. 同 `tool_id` 不得同時出現在 Q>1 與 Q=1 episode（LB ADR-001 追記：Q>1 release／USE 側未過濾會 500）。
2. `p2` 恆空（D10）。3. `complexity_level` 恆空（LB solver 零消費）。4. SIMO 從屬列不輸出（D15）。5. nb 不輸出。
每條在 LB Phase 2 對應修正落地後，於 Spec §11 降級或移除。

### D10 UI：Level System 增加 LB 標記層（建議設計，可於實作時調整）
- 既有：`sub`（↕ 天藍）、`cub`（🔒 琥珀）。新增：`worker_cub`（👤 紫，圈選成組，設組即傳染 offline／擋 Q>1）、`offline`（列級切換，組內傳染提示）、`segment`（Q>1 列的 chip，依附 cub）、`station pin`（📍 站號）、`general`（線頭／線尾通用列）、`merge_lock`（🔧🔒 此工具取放不可省）。
- 每列右側 **投影預覽 badge**：會變幾列（1／2／3）、Q、setup/cyclic、tool_id、warnings——IE 不看 CSV 就知道 LB 會收到什麼。
- 匯出前顯示 §8.2 報告；E 碰擋、W 碼列出。
- i18n：zh-TW／en 同步（ADR-032）。E2E 覆蓋「圈 wcub → offline 傳染 → 匯出報告」。

> **追記（2026-09-12，D10 修訂）**：上述「LB 標記層」UI 已於 WP12 落地（`4ada705`/`d73467f`），但 User 實測回饋：sub／cub／wcub／segment／pin／general 是模型詞彙，一般使用者只懂「工序」。因此 D10 修訂為**兩層視圖、同一 store**：
> 1. **作業版（預設）**：使用者只操作「作業（一組接著做的步驟，有名字）」「排（同一排＝可同時做）」與每個作業最多四個是非題（同一工站／同一個人一口氣／離線先做／固定站）；sub／cub／wcub／offline／pin 由作業視圖**反投影**自 `useLevelStore`（store 仍是唯一真相，`derive()` 不變）。作業名稱新增 `wi_rows.wi_group`，由手動、AI 草稿、Excel 匯入、模組實體化四條路徑填入。
> 2. **進階檢視**：WP12 的 IE 視圖原樣保留（nb、離散層級、難度係數仍在此）。
> 3. **「系統看出來的事」不接 LLM**：提示（同站建議、批量建議、工具自動拆列說明、機台時間說明）由後端投影資料以確定性規則產生（`lb_projection/hints.py`），E／W 碼由前端 i18n 模板轉成使用者語言；不做敘述關鍵字猜測。
> 4. **未存檔預覽**：新增 `POST …/export/lb-report/preview`（dry-run，與存檔後 `lb-report` 同一投影路徑、同一報告 builder）；報告加法欄位 `rows[]`／`hints[]`／`params`，CSV 與 `CONTRACT_VERSION` 不變。
> 5. `divisible`／`splittable` **不加 DB 欄、不加 UI**：LB 端 ADR-023 §4 明列「MOST 不輸出 `divisible`；與 quantity 收斂另立 ADR」。產品路徑恆 0；黃金 fixture O 列的 `lb_tags.splittable` 僅為覆蓋 24 欄，投影層對應保留。
> 6. **機台時間「事實在 MOST、政策在 LB」**（2026-09-12 Howard 裁決）：作業版把 `H_MACHINE_TIME` 從說明改為提問「人要在旁邊顧著嗎？」→ 第 9 標記 `machine_unattended`（D7 追記）→ 契約 `role_type`；LB 端以求解參數 `unattended_machine_policy`（free／busy）決定不佔人的機台時間是否真的釋放人力（ADR-023 D9 追記）。節拍永遠含機台時間，兩邊都不可改。
> 實作書：`docs/lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`（含反投影形式定義、動作→store 變更表、i18n 全目錄、規則表）。設計原型：`docs/lb-integration/prototypes/level-jobs/`。

---

## 3. 被否決的方案

| 方案 | 否決理由 |
|---|---|
| A. 逼 IE 把拿／用／放建成三個 motion（維持 D1 嚴格 1:1） | 方法論扭曲（P=保持住、G=重新抓握湊數）；與現場資料形狀不符（User 觀察）；且解不了 repeat 隱藏乘數 |
| B. LB 單列加 `setup_ms/cyclic_ms/release_ms` 欄 | CP-SAT 需新增複合 interval 型別（ADR-008 D3/D8 建在逐列 setup/cyclic 上）；CSV 更肥；違反「LB 已有正確原語」 |
| C. 投影層用啟發式（敘事關鍵字）猜哪列是工具 | 與 D5 單一權威哲學相悖；`kind='tool'` 是確定訊號，不需要猜 |
| D. 持工具 motion `frequency>1` 直接改讀成 repeat | 靜默改寫計算語意（同 S-2 教訓：乘數不被靜默改寫）；改為字面輸出＋警告，並在 compiler 端把預設導向 repeat |
| E. 沿用 `build_output.precedence_edges` | 只連 has_main 列、只 level_min 相鄰鏈、無組內鏈、無 sink→source（契約已註「不可沿用」） |
| F. 把 LB 標記存在 `wi_rows` | Level System 是這些標記的編輯面、`level_entries` FK→wi_row 穩定 id、save 時每列必建——落點一致 |

---

## 4. 後果

### 正面
- IE 用 MOST 自然建模（一條 CM 掃描），LB 仍得到可 merge、可分攤的三列；工時標準零改動（TMU 守恆為測試不變量）。
- 「×8 到底是 frequency 還是 repeat」在資料層有明確答案，投影層只讀不猜。
- LB 21 欄成為機器對機器契約；人面對的是 Level System 的六個標記。

### 代價／風險
- Level System 分層模型的表達力上限（任意分支 DAG 不可表達）成為明文限制；IE 需用 sub 把「只依賴前一步」的鏈包起來。
- `level_entries` 加欄＋migration；`read_worksheet` 形狀加法擴充（ADR-011 相容）。
- 三列共用 `source_wi_row_id` → D13 回寫需能處理一對多（Phase 2）。
- 過渡守衛 D9.1 在「同一把起子鎖 8 顆也鎖 1 顆」的現場很常見，會被擋——這是 LB 該修的，實作書把它列為 Phase 2 第一優先。

### 待 User 明示裁決（不阻擋實作；預設採本 ADR 值）
1. D3 持工具 `frequency>1` 且 `repeat>1` → 拒絕（vs. 接受為全 cyclic 放棄輪次綁定）。
2. D3 非整數 frequency 燙進 duration（vs. 拒絕）。
3. D6 巢狀 cub 區塊以最小 `seq_no` 定位（vs. 要求 IE 在 UI 明指位置）。
4. D7 `machine_count`／`manpower` 欄位是否在同一 migration 一併移除（預設：保留欄、停止匯出）。

---

## 5. 落地追蹤
實作書：[`docs/lb-integration/LB_PROJECTION_IMPLEMENTATION_PLAN.md`](../lb-integration/LB_PROJECTION_IMPLEMENTATION_PLAN.md)。
commit／PR 引用：`implements ADR-035: …`。狀態轉 🟢 時回填 accepted 日期並在 `decisions/README.md` 更新。

- **D10 作業版 UI（兩層視圖）落地（2026-09-12）**：實作書 [`LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`](../lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md)；commit 範圍 `08f59e7`（B1）…`49d02c1`（F8）。作業版反投影 store 為唯一真相、不接 LLM、不移植原型 engine。附帶修正兩個真實後端錯誤：clone 漏帶全部 9 個 LB tag 欄（B7）、adapter `_build_projection_row` 的 `repeat_counts` 硬寫空 dict 導致 save 路徑投影 N=1（F9）。
