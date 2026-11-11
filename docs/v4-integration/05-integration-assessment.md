# 05 — 整合評估：建議、風險、順序（Synthesis）

> 本文件是 01–04 的**交叉檢查與收斂**。所有結論由前四份子文件（皆已實讀 v4/v2 code、附 `檔案:行號`）彙整而來，
> 引用時標注來源子文件與其證據錨點。這是唯讀審查，**不修改 v4、不改 v2 程式碼**。
>
> - v2 = `ddm-v2`（現行目標系統。FastAPI + SQLAlchemy 2.0 async + React 19 + PostgreSQL；MOST engine 單一權威、黃金值鎖 GM=28／CM=29）。
> - v4 = `minimost_level/minimost/apps/api`（另一位 IE 延伸早期系統獨自開發。FastAPI + SQLAlchemy **1.4** + SQLite/PostgreSQL + **Vue 3**）。
>
> 審查日期：2026-09-04

---

## 0. 執行摘要（給決策者）

> **範圍裁決（使用者 2026-09-04）：Line Balance／KPI 不整合進 v2**。使用者已有另一套專門做 Line
> Balance 的系統，故 v4 的 LB 求解器與 KPI 計算**降級為「邏輯參考、不在 v2 重建」**（邏輯整理見
> `06-line-balance-kpi-logic.md`）。本節下方原將 LB 列為主要標的的敘述已據此修正；**Line Layout／
> E-SOP 仍為整合標的**，但其上游 LB 產出改由使用者的外部 LB 系統提供，而非 v2 內建。

1. **整合本質＝邏輯／功能移植，不是 code 搬遷**。v4 與 v2 技術棧全面不相容（見 §1），沒有任何 v4 檔案能「複製貼上」進 v2。整合成本＝重寫（async 化、換認證、換 schema、換 ORM 用法），加上**領域規則對映**。
2. **v4 的整合價值（扣除 LB 後）集中在**：Level System Plan（有狀態快照層）、E-SOP、Line Layout，外加 Case 審批工作流與 Process Routes（依 01 §1.5-1.7、04 §6-7、03 §4）。**Line Balance 求解器不整合**（使用者另有系統）。
3. **最高風險不是功能移植，而是「計算正確性污染」**。三份子文件（01/02/03）各自從不同角度得出**同一條硬底線**：v4 有自己的 TMU 計算路徑與凍結快照，若被採信進 v2，會製造第二份真相、破壞單一權威與 GM=28／CM=29 黃金鎖。所有 v4 資料進 v2 都必須「只取原始選擇 → v2 引擎重算 → v4 值僅作移轉驗證」。
4. **好消息：整合標的的污染風險低**。Layout／E-SOP 只吃「CT 秒數快照」、不重算 TMU（01 §3.2、04 §6），只要確保其 CT 來源是 v2 引擎算出的值，就能相對安全地移植。真正碰 TMU 的是「字典/規則資料對映」與「單列計算 UX」，這兩塊才是紅線所在。
5. **建議分階段**（§4）：Phase 0 治理地基（認證、規則資料對映、golden gate）→ Phase 1 Level Plan 資料層決策 → Phase 2 Line Layout／E-SOP／審批流。每階段結束都以 `engine_golden_test.py` 全綠為驗收門檻。（原 Phase 2「LB 求解器」已移除。）
6. **有開放問題必須由使用者（IE + 架構）裁決**（§5），最關鍵的是 Level System 的模型哲學二選一（03 §2.4）——它是 E-SOP／Layout 的地基。**另註**：Level Plan 在 v4 是 LB 的資料源；LB 既不整合，Level Plan 的整合價值需重新評估（見 §5 開放問題 1 修訂）。

---

## 1. 技術棧不相容 → 整合是「邏輯移植」而非「code 搬遷」

（依 00-overview 名詞基準 + 04 §0 技術棧差異 + 03 §1 資料模型分歧）

| 維度 | v4 | v2 | 對整合的意義 |
|---|---|---|---|
| ORM / DB 存取 | SQLAlchemy **1.4** 同步 `Session`（`Depends(get_db)`，04 §0）| SQLAlchemy **2.0 async** `AsyncSession`（`get_db_session, scope="function"`，04 §0）| 所有 v4 route/service 需改寫為 `async def` + `await`；同步 ORM 慣用法（lazy load、`session.query`）不可搬 |
| 認證 | 本地 JWT 登入（`auth.py:58` login、`:69` `create_access_token`，04 §8）| 聯邦 Traefik ForwardAuth（無本地登入；gateway 注入身分，04 §8、01 §1.10）| **硬邊界**：v4 `auth.py`/`users.py` 的密碼模型不可搬入；所有端點 `Depends` 換 v2 `current_user`/`require_role` |
| Web 前端 | Vue 3 + Element Plus（00-overview）| React 19 + TypeScript + TanStack Query（README）| v4 前端**完全不可重用**；所有 UI 需以 React 重寫 |
| Schema/驗證 | 未統一（v4 route 內組 dict/dataclass，04 §1）| Pydantic v2 schema（`schemas/v2/`，專案慣例）| v4 的回傳結構需重新定義為 Pydantic v2 |
| 錯誤處理 | v4 route 內散落 | v2 `error_handlers.py` 結構化錯誤（04 §0）| 需改用 v2 錯誤合約 |
| 規則資料 schema | 通用 5 表（`parameter_options` 一表打天下，03 §1.1）| MOST 專用 12 表（把 MOST 語意編碼進 CHECK/pricing_kind，03 §1.2）| v4 字典無法直接 import；需寫「通用選項 → 分表」映射器（03 §6.1）|

**結論**：整合 = 讀懂 v4 的**領域意圖與演算法**，在 v2 的架構（async / ForwardAuth / Pydantic v2 / 12 表規則模型 / React）中**重新實作**。唯一可高保真移植的是「純演算法邏輯」（如 LB beam-search 的裝箱策略），因為那是與框架無關的計算過程；但即使是它，資料進出口也要改接 v2 模型。

---

## 2. v4 有、v2 無的高價值功能（整合優先序）

（依 01 §1.4-1.7、01 §2、04 §5-7、03 §4 交叉確認。★ = v2 全庫 grep 反向確認無等價實作，見 01 附錄／03 §4）

| # | 功能域 | v4 證據 | v2 現況 | 業務價值 | 污染風險 | 建議優先序 |
|---|---|---|---|---|---|---|
| A | **Line Balance 求解器** ★ ⛔**不整合** | beam-search 前序約束裝箱（`services/line_balance.py`，`ALGORITHM_VERSION="v2"`、`_BEAM_WIDTH=12`，01 §1.4）；端點 `/simulate`、`/simulate-multi`、scenario CRUD（04 §5）| 僅 LB CSV／API **匯出**（`export.py:56/:69`），無求解器（01 §1.4）| —（使用者另有專門 LB 系統）| **低**（只吃 CT 秒數快照，不重算 TMU，01 §3.2）| ⛔**不整合**（使用者裁決 2026-09-04）；改為**邏輯整理供參考**（見 `06-line-balance-kpi-logic.md`）。v4 LB／KPI 計算方式已如實抽出，供外部 LB 系統對照 |
| B | **Level System Plan（有狀態快照層）** ★ | `level_system_plans`＋items＋number_rules 3 表（`most.py:357/389/437`，03 §4.3）；from-wi-set 快照、release/archive、產 `adjusted_ct_seconds`＋`main_instance` 鏈（04 §3）| 無狀態 R1-R9 validator（`most_engine/level.py`），掛 wi_row 的 `level_entries` 活資料（03 §2.4）| 中（原為 LB／E-SOP 地基；LB 既不整合，價值主要剩 E-SOP／Layout 地基與難度係數）| **中**（含 CT 快照；快照值不得採信為權威，須 v2 重算）| **P1 前置（E-SOP／Layout 地基）**，需先裁決模型哲學（見 §5 開放問題 1）|
| C | **E-SOP 子系統** ★ | 5 表（`esop.py:27-170`，03 §4.1）；21 端點：from-LB/from-layout 生成、站別頁/步驟、圖片標註、preview/print/export-pdf（04 §6）| 完全無（03 §4 grep 0 命中）| 高（現場作業書輸出）| **低**（`esop_generator.py` 明言凍結快照、只讀不改上游，01 §1.6）| **P2**，工程量大（新表＋檔案儲存＋PDF 渲染）；原依賴 v4 LB，改為依賴使用者外部 LB 系統的產出（見下）|
| D | **Line Layout（工站布局）** ★ | 5 種布局視覺化，疊在 LB scenario 上（`line_layout.py`，01 §1.5）；from-line-balance 派生（04 §5）| 完全無 | 中 | **低**（純視覺層，不碰計算）| **P2**，原疊在 v4 LB scenario 上；LB 不整合後需重新界定其資料源（見 §5 開放問題 2 修訂）| 
| E | **Case 審批工作流** | submit/review/request-changes/approve/archive＋audit（`analysis.py:97-403`，01 §1.7、04 §7）；含 `video_timestamp`（v2 完全缺，03 §4.4）| 僅唯讀 `GET /cases`（`cases.py:20`）；審批以 worksheet publish/retire 表達（04 §7）| 中（治理增強）| **低**（工作流狀態機，不碰 TMU）| **P3**，角色需對映 v2 階層（見 §3）|
| F | **Process Routes** | 整域 CRUD＋apply-to-template（`most_workbench_v3.py:838-1054`，04 §4d）| 無此實體（04 §4d）| 中 | 低 | **P3**，需評估是否對映到 worksheet/wi-set |

**優先序邏輯**（依使用者裁決修正）：
- **Line Balance 求解器不整合**（使用者另有系統）。其邏輯已整理於 `06`，供外部系統參考。
- **B（Level Plan）改為 E-SOP／Layout 的地基**（原亦為 LB 地基，LB 移除後地基角色縮小但仍是 E-SOP/Layout 前置）。是 P1 前置，需先裁決模型哲學。
- **C（E-SOP）與 D（Layout）是扣除 LB 後的主要整合標的**，排 P2；兩者原依賴 v4 內建 LB scenario，現改為依賴使用者外部 LB 系統的輸出——**此依賴改動需在整合設計時界定介面**（見 §5）。
- E/F 屬治理增強，排 P3。

> 交叉檢查註記：01 把 LB/ESOP 列 P1、Layout/審批列 P2；04 把 LB/Layout/ESOP/LevelPlan/Case 並列為「最大整合工作量」。本文件**收斂**為：以「依賴關係 + 污染風險 + 投報率」重排為 Phase 化順序（§4），把 Level Plan 資料層決策提到 A 之前，因為 01/03/04 一致指出它是 LB 的資料源（01 §1.3、03 §2.4、04 §3）。

---

## 3. MOST sequence 差異對 v2 治理不變式的風險

（依 02 全文，對照 v2 兩條核心不變式：**I1 = TMU 單一權威**、**I2 = 黃金值 GM=28／CM=29 不得污染**）

### 3.1 風險總表（依污染嚴重度排序）

| 風險 | 來源差異（02 證據）| 對 I1／I2 的威脅 | 緩解措施 |
|---|---|---|---|
| **R1：v4 三套計算引擎語義互斥** | v4 有 `calculation_v2.py`（現役，SIMO→0）、`calculation.py`（legacy index）、`most_workbench.py`（孤兒，SIMO=**max**，與現役相反）（02 §0）| 若整合誤採 legacy/孤兒路徑，SIMO 語義相反會直接算錯 | **只採信 `calculation_v2.py` 作為 v4 意圖參照；另兩套明確排除**（02 §7.5）。且無論採哪套，TMU 一律轉呼叫 v2 engine |
| **R2：v4 缺 B/X/I 的「0 值選項」** | v4 B/X/I 無 `none`，v2 有 `b_none/x_none/i_none`（02 §2 B/I、§4）| **直接威脅 I2**：GM=28 依賴 B=0、CM=29 依賴 X=0/I=0（02 §4）。v4 資料若當 v2 GM/CM 算會多出 TMU | v4→v2 映射**必須補齊 0 值選項**（02 §4.2、§7.2）；映射後跑 golden |
| **R3：v4 各層凍結 TMU 快照** | v4 每層自帶 `calculation_snapshot_json`＋TMU 欄（`most.py:41-62`，03 §2.3）| **直接威脅 I1**：採信快照＝引入第二份可寫真相 | **只匯入 `selected_slots_json` → 映射 v2 `slot_inputs` → v2 引擎重算**；v4 快照僅作移轉驗證（03 §2.3、§6.3）|
| **R4：字典有影響 TMU 的實質差異** | v2 多 M 選項 `M_PRESS`（fixed 3 TMU），v4 無（M leaf：v2=67/v4=66，03 §3 差異1）| 合併時若單方覆蓋會遺失／新增 M 選項，改變可算出的 TMU | **合併非覆蓋**（03 §3.1、§6.2）；合併後過 golden |
| **R5：CM 返回槽命名分歧** | v2 字典=`A2`，v4=`A3`（v4 有 migration `58a3d1cca6f1` 改名，03 §3 差異2）| 不改 TMU **數值**，但改 slot 識別／narrative 對映，錯位會導致重算對不上 | 對齊 slot_key（以 v4 A3 慣例為準較合理，因符合 A1=obtain/A2=move/A3=return），列入映射規格 |
| **R6：v4 缺 v2 的值域/結構防呆** | v4 無 `M_*_RANGE`、`M_COMPANION_WITHOUT_VERB`、`A_RETURN_COMPONENT`、`P_DUP_ADDON`、`*_UNKNOWN`（02 §2 各格、§6）| **方向安全**（v2 較嚴）：v4 髒資料進 v2 會被**擋下**而非算錯 | 移轉時需**清洗**被擋資料（如 A3 帶 twist/foot、M 只選手度沒動詞、重複 addon），或以 v2 規則重算 |
| **R7：total 層 rounding 口徑** | v2 `round()`（banker's）vs v4 `Decimal ROUND_HALF_UP`（02 §3）| 極小（v2 slot 多為整數 index；X 在 slot 層已對齊 half-up）；.5 邊界理論上可差 1 TMU | **整合後一律以 v2 引擎重算 total，不採信 v4 total**（02 §3、§7.1）|
| **R8：repeat 越界/上限差異** | v2 越界報 `REPEAT_INVALID`、上限 99；v4 靜默回退 1、無上限（02 §5）| 方向安全（v2 較嚴）| 以 v2 規則為準；v4 靜默回退可能掩蓋的錯誤輸入需在移轉時檢視 |

### 3.2 關鍵收斂結論

- **同源但不同權威**：02 §4 逐格核對證明 v4 與 v2 的**值表完全同源**（A/B/G/P/M/X/I 數值一致），差異在「表徵」（v2 存 band、v4 存 pre-computed tmu_value）與「防呆強度」。這意味著整合**在數值上是可對映的**，風險不在數值本身，而在：(a) 缺 0 值選項（R2）、(b) 採信快照（R3）、(c) 字典合併方向（R4）。
- **P precision gating 已澄清為非風險**：02 的重要更正記錄——v2 全 5 個 P addon `needs_precision=False`，gating 為停用死碼，現行資料集下與 v4 等價（02 §2 P 格、§6）。唯一守則是整合過程**不要**在 v2 引入 `needs_precision=True` 的 addon。此更正正是「必須實讀 code」的體現，本文件採信之。
- **I1/I2 的統一防線**：無論哪個功能域，只要涉及 TMU，一律走「v4 原始選擇 → v2 slot_inputs → v2 引擎重算 → golden 驗收」。這條防線同時擋住 R1/R3/R7，是整個整合的**單一安全閥**。

---

## 4. 建議的整合分階段順序

每個 Phase 的**共同驗收門檻**：`PYTHONPATH=src python scripts/core_logic/engine_golden_test.py` 全綠（GM=28／CM=29＋全反例），以及 `scripts/core_logic/run_all.py`。任一 Phase 若導致 golden 破損，視為污染，不得合併（02 §7.4、03 §6.2）。

### Phase 0 — 治理地基（P0，不碰功能，先立防線）
目標：把「安全閥」與「資料對映」建好，之後每個功能域才能安全接入。
1. **認證換接規格**：定義 v4 端點如何從本地 JWT 改為 v2 ForwardAuth；v4 角色（admin/analyst/reviewer/approver）對映 v2 階層（viewer<analyst<approver<admin），`reviewer`→`approver`（01 §1.10、04 §8）。**v4 密碼模型不搬**。
2. **字典/規則資料對映器**：寫 v4 `parameter_options` →（依 `parameter_code`+`control_key`+`input_type`）分流到 v2 12 表；**M 一表→五表**是最複雜項（03 §1.3、§6.1）。合併字典差異（納入 `M_PRESS`、對齊 CM A3），**合併非覆蓋**（03 §3.1）。補齊 v4 缺的 B/X/I 0 值選項（02 §7.2）。
3. **移轉驗證框架**：建立「匯入 v4 selected_slots → v2 slot_inputs → v2 重算 → 比對 v4 快照」的驗證腳本，作為所有後續資料移轉的閘門（03 §6.3）。
4. **golden gate 接上 CI**：確保每次整合 commit 都跑 golden（02 §7.4）。

### Phase 1 — Level System 資料層（P1 前置地基）
目標：拍板並實作 Level Plan 的資料形狀（LB/E-SOP 的地基）。
1. **裁決** §5 開放問題 1（獨立 plan 層 vs 吸收進 level_entries）。03 §6.4 建議方案 (A)（新增獨立分析層），因 v4 plan 的快照/生命週期與 v2 `level_entries`（活資料、跟 worksheet 版本、wi_row 穩定 id）不相容（03 §2.4）。
2. 依裁決結果實作：Level Plan 實體（from-wi-set 快照、release/archive、number-rules），或把欄位吸收進 `level_entries`。
3. **CT 來源鐵則**：plan item 的 `ct_seconds`/`adjusted_ct_seconds` 必須源自 v2 引擎算出的值，不得採信 v4 快照（R3）。

### ~~Phase 2 — Line Balance 求解器~~ ⛔ 移除（使用者裁決 2026-09-04）
使用者已有另一套專門做 Line Balance 的系統，**v2 不重建 LB 求解器**。v4 的 beam-search 前序約束
裝箱演算法與 KPI 計算方式已如實整理於 `06-line-balance-kpi-logic.md`，供該外部系統對照參考。
v2 維持既有的 LB CSV／API 匯出（`export.py:56/:69`）作為「餵資料給外部 LB」的介面，整合過程不得回退此能力（04 §9）。

### Phase 2 — Line Layout / E-SOP / 審批流 / Process Routes
目標：扣除 LB 後的整合標的與治理增強。**注意**：Layout／E-SOP 在 v4 原疊在內建 LB scenario 上，
v2 不建 LB scenario，故整合時須先界定其資料源介面——是接使用者外部 LB 系統的產出（站別指派＋CT），
還是以 v2 WI Set／Level Plan 的原子單元為輸入（見 §5 開放問題 2）。
1. **Line Layout**（純視覺層，前端為主，01 §1.5）；資料源介面待定（見上）。
2. **E-SOP**（需新表＋檔案儲存＋PDF 渲染，工程量最大，01 §1.6、04 §6）；資料源介面待定（見上）。
3. **Case 審批工作流**（狀態機＋video_timestamp 欄位，對映 v2 角色階層，01 §1.7、03 §4.4）。
4. **Process Routes**（評估對映 worksheet/wi-set 或新增實體，04 §4d）。

### 每 Phase 都要做的「反向保護」
04 §9 列出 **v2 有、v4 無** 的功能域（Catalog 樹、Excel 匯入管線、i18n 審查回路、Vocab 主數據、全文搜尋、DSX、synonyms/bands/diff、AI 草稿人審回饋）。整合任何 v4 功能時**不得回退掉這些 v2 既有能力**。撞名表（`wi_set_projects`、`workflow_audit_log(s)`、`users`/`app_users`）migration 前必查、必改名（03 §4.5、§6.6）。

---

## 5. 需使用者裁決的開放問題

以下問題**無法由審查單方決定**，牽涉領域政策或架構取捨，須由使用者（IE ＋ 架構負責人）拍板：

1. **【最關鍵】Level System 模型哲學二選一**（03 §2.4、§6.4；01 §1.3）
   - (A) 把 v4 Level Plan 平移為 v2 之上的**獨立分析層**（新增表），保留 `level_entries` 不動。
   - (B) 用 v2 `level_entries` 語意**吸收** v4 Plan 欄位（`difficulty_factor`→`coefficient` 等），放棄 v4 獨立快照生命週期。
   - 審查建議 (A)，但這會讓 v2 同時存在「無狀態 validator」與「有狀態 plan」兩套 level 概念，是否接受此複雜度？**這是 E-SOP／Layout 的地基**（LB 不整合後不再是 LB 地基），仍需先定案才能動 P1／P2。

2. **Layout／E-SOP 的上游資料源介面**（因 LB 不整合而新增的問題；04 §5-6、01 §1.5-1.6）
   - v4 的 Layout／E-SOP 原本 from-line-balance／from-layout 派生，吃 v4 內建 LB scenario 的站別指派與 CT。
   - v2 不建 LB 求解器，故整合 Layout／E-SOP 時，其「站別指派＋CT」輸入要從哪來？選項：(a) 定義一個
     介面接使用者外部 LB 系統的輸出；(b) 以 v2 WI Set／Level Plan 的原子單元為輸入、由使用者手動指派站別。
     此決策影響 Layout／E-SOP 的整合設計與工作量。

3. **字典/規則合併的權威來源與 M_PRESS／CM-A3 處理**（03 §3.1、§6.2）
   - v2 有 `M_PRESS`（3 TMU）、v4 無；v4 CM 返回槽已正規化為 `A3`、v2 字典仍 `A2`。合併需雙向納入。
   - 開放點：合併後的權威落點是 v2 DB 的 `rule_sets` 12 表（seed 由 `import_v3_dictionary.py`），JSON 差異需再對 **DB 實表值** 複核（03 §3 註記把 DB 複核列為整合實作階段）。是否要在 Phase 0 先做一次 DB 實值複核？

4. **v4 認證角色 `reviewer` 的對映**（01 §1.10、04 §8）
   - v4 有 `reviewer`＋`approver` 兩個分離角色；v2 只有 `approver`。整合 Case 審批工作流（需 reviewer/approver 分離）時，是否要在 v2 新增 `reviewer` 階層，還是把 v4 reviewer 併入 v2 approver（可能弱化審批分權）？

5. **Process Routes 與 v4「sequence/mi-statement」獨立實體的去留**（04 §1、§4d）
   - v4 有獨立的 sequence CRUD、mi-statement CRUD、process-routes 整域；v2 以 worksheet + wi-row 承載。是否為 v4 的這些實體在 v2 建立對應資料模型，還是全部對映到 v2 現有的 worksheet/wi-set/motion-module？此決策影響資料模型複雜度與遷移工作量。

---

## 6. 一頁風險-緩解對照（給 PM／Reviewer 快速核對）

| 不變式 | 威脅 | 緩解（單一安全閥）| 驗收 |
|---|---|---|---|
| I1 TMU 單一權威 | v4 三引擎（R1）、凍結快照（R3）、rounding（R7）| v4 原始選擇 → v2 slot_inputs → **v2 引擎重算**；v4 值僅移轉驗證 | 重算值 == v2 引擎值 |
| I2 黃金值 GM=28／CM=29 | 缺 0 值選項（R2）、字典單方覆蓋（R4）、slot 錯位（R5）| 補 0 值選項；字典**合併非覆蓋**；對齊 A3 slot_key | `engine_golden_test.py` 全綠 |
| v2 既有能力不回退 | 撞名表、漏保留 v2 專有域 | migration 前查撞名必改名；對照 04 §9 清單 | v2 既有測試不破 |

---

## 附錄：本文件的證據鏈（指向前四子文件的錨點）

- **技術棧不相容（§1）**：00-overview「名詞基準」、04 §0「技術棧差異」、03 §1「字典組織分歧」。
- **高價值功能與優先序（§2）**：01 §1.4-1.7／§2、04 §5-7、03 §4；★ 反向確認 = 01 附錄／03 §4 grep 0 命中。
- **MOST sequence 風險（§3）**：02 全文，特別 §0（三引擎判定）、§2（逐格值表同源）、§3（SIMO/rounding）、§4（黃金值 + 0 值選項）、§6（相同/不同/單方有 總表）、§7（整合建議）；P precision 更正記錄。
- **資料層鐵則（§3 R3、§4 Phase 0）**：03 §2.3（權威輸入 vs 凍結快照）、§6.3（快照僅移轉驗證）。
- **開放問題（§5）**：03 §2.4／§6.4（Level 哲學）、04 §5（LB 定位）、03 §3（字典合併）、01 §1.10／04 §8（角色）、04 §1／§4d（獨立實體）。

> 本文件未新增任何未經前四子文件驗證的結論；所有優先序調整（如把 Level Plan 提到 LB 之前）均基於 01/03/04 一致指出的依賴關係，並在 §2、§4 標明收斂理由。
