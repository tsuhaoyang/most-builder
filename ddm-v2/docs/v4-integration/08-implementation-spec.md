# v4 → v2 整合實作規格（Implementation Spec）

> **狀態**：草案 v1（2026-09-04）。本文件指導後續 agent 進行整合實作。
> **前置**：本 spec 建立在 `00`–`07` 審查文件之上（皆實讀 v4/v2 code、附行號）。讀本 spec 前，
> 實作者應先讀 `00-overview.md`（基準與範圍裁決）、`02-most-sequence-comparison.md`（MOST 計算對照）、
> `07-level-system-ux-gap.md`（Level UX 差距）。
> **性質**：這是「在 v2 架構下重新實作 v4 的設計邏輯」的規格，**不是搬 v4 的 code**。

---

## 0. 使用者已裁決的共識（實作前提，不可自行推翻）

以下由 User 於 2026-09-04 討論裁決，是本 spec 的固定前提：

1. **Line Balance／KPI 不整合**。User 另有專門 LB 系統。v4 的 LB 求解器與 KPI 計算只作**邏輯參考**
   （見 `06-line-balance-kpi-logic.md`），v2 不重建求解器，維持既有「LB CSV／API 匯出」介面
   （`export.py:56/:69`）餵外部系統。
2. **Level System：要 v4 的 UX，不要 v4 的 Plan 版本管理**。
   - 抄 v4 的拖／拉／選／呈現手感（降低使用者操作負擔）。
   - **資料留在 v2 既有 `level_entries` 活資料模型**（掛 `wi_row`、跟 worksheet 版本），
     編輯**即作用在 worksheet 活資料、不另存快照**。
   - **不引入** v4 的 `level_system_plans` 獨立快照層與 release/archive/version 版本管理——
     其存在主要服務不整合的 LB，且 v2 的 `ProcessVersion`（worksheet 版本、發布凍結、另存新檔）
     已涵蓋版本治理需求。
3. **i18n 資料雙語走 (a)**：整合新增的任何可讀文字欄位，一律遵循 **ADR-032** 的 `_zh`／`_en`
   雙欄 + i18n review 治理；`_en` **先留空**，之後走 ADR-032 的 i18n review 流程補（不強迫整合時做翻譯）。
4. **spec 粒度 = per-功能域細規格**（本文件 §3 各節）。

---

## 1. 全域架構約束（每個功能域都必須遵守）

這些約束凌駕於任何 v4 設計之上。違反即為整合失敗。

### C1 — TMU 單一權威不可污染（v2 I1／I2）
- 任何涉及 TMU 的路徑，一律走 v2 `most_engine`（經 `most_compiler/engine_gate.py`）。
  **禁止**移植 v4 的 `calculation.py`／`calculation_v2.py`／`most_workbench.py` 任一計算路徑
  （`02` §0：v4 三套引擎語義互斥，`most_workbench.py` 的 SIMO 甚至與現役相反）。
- v4 各表遍布的 `calculation_snapshot_json`／`tmu` 欄，**只作移轉驗證，不作權威**
  （`03` §2.3）。移轉鐵則：**v4 原始選擇（`selected_slots_json`）→ 映射 v2 `slot_inputs`
  → v2 引擎重算 → 比對 v4 快照僅供驗證**。
- **驗收門檻**：任一整合 commit 後，`PYTHONPATH=src python scripts/core_logic/run_all.py`
  與 `engine_golden_test.py` 全綠（GM=28／CM=29 不得漂移）。

### C2 — 雙語資料層遵循 ADR-032（不另造）
- 整合新增的可讀文字欄位（Level 敘述、E-SOP 步驟文字、Case 敘述等）一律 `_zh`／`_en` 雙欄。
- API 語言中立（ADR-032 D3.3）；前端依 locale 選欄（沿用 `pickNarrative` 模式／`useRowNarr`）。
- 不翻譯、不合併、不猜測（ADR-032 D7／I4）；`_en` 缺值時前端不得在 en locale 顯示 `_zh` 偽裝。
- `_en` 初始留空，之後由 ADR-032 i18n review 流程補（fill-then-fix，D2）。
- 錯誤訊息走 ADR-034 的 code + 結構化參數 + 前端 catalog（新端點錯誤沿用此契約）。

### C3 — 不搬 code，重新實作（技術棧不相容）
- v4 = SQLAlchemy 1.4 同步 + Vue 3 + 本地 JWT；v2 = SQLAlchemy 2.0 async + React 19 + Traefik
  ForwardAuth（`01` §0、`04` §0）。**沒有任何 v4 檔案可複製貼上**。
- 後端：v4 route/service 的領域邏輯 → v2 `async def` + `AsyncSession` + Pydantic v2 schema +
  `error_handlers` 結構化錯誤 + `require_role` 授權。
- 前端：v4 Vue 元件 → v2 React 19 + TanStack Query + Zustand + TailwindCSS 重寫。
- 認證：v4 端點的 `Depends(get_current_user)`／`require_analyst_or_admin` → v2 `current_user`／
  `require_role`；**v4 的 User/password 模型不搬**（v2 是聯邦認證）。角色對映見 §2。

### C4 — 不回退 v2 既有能力
- 整合任何 v4 功能，不得移除 v2 專有域（`04` §9：Catalog 樹、Excel 匯入管線、i18n 審查回路、
  Vocab 主數據、全文搜尋、DSX、synonyms/bands/diff、AI 草稿人審回饋）。
- **撞名表必改名**：v4 `wi_set_projects`／`workflow_audit_log(s)`／`users` 與 v2 同名但不同構
  （`03` §4.5、§5）。migration 前必查、必改名或映射，否則直接衝突。

### C5 — 加法演進與治理（ADR-011）
- 所有 schema 變更走 Alembic migration，加法為主（ADR-011）。
- 新 API 端點走 v2 慣例：`/api/v2` 前綴、`require_role`、Pydantic v2、結構化錯誤、`route_registry` 掛載。
- RBAC 尊重 v2 階層 viewer<analyst<approver<admin。

---

## 2. 認證與角色對映（所有功能域共用的 Phase 0 前置）

（依 `01` §1.10、`04` §8）

| v4 角色 | v2 對映 | 說明 |
|---|---|---|
| admin | admin | 直接對映 |
| analyst | analyst | 直接對映 |
| approver | approver | 直接對映 |
| **reviewer** | **approver**（暫定）| v2 無獨立 reviewer 階層。Case 審批流（§3.4）若需 reviewer/approver 分權，需 User 裁決是否在 v2 新增 reviewer 階層（見 `05` §5 開放問題 4）。**此決策未定前，Case 審批流不動工。** |
| viewer（v2 有、v4 隱含）| viewer | v2 唯讀層 |

- v4 端點全部改用 v2 auth 依賴。v4 `users.py`／`auth.py`／password 模型不移植。

---

## 3. 功能域實作規格

整合標的（扣除不整合的 LB）：**Level System UX（P1）**、**E-SOP（P1，工程量大）**、
**Line Layout（P2）**、**Case 審批流（P2，待角色裁決）**、**Process Routes（P3，待實體去留裁決）**。
外加貫穿性的 **i18n 資料層（C2）**。

本文件先詳寫**已可動工、共識明確**的 §3.1 Level System UX（含 i18n）。其餘功能域（§3.2–3.5）
列出規格骨架與待決前提，待各自的開放問題（`05` §5）裁決後再展開細規格。

---

### 3.1 Level System UX 移植（P1，共識明確，可動工）

**目標**：把 v4 的 Level 編輯手感補進 v2，資料落在 v2 `level_entries` 活資料（不新增 Plan 層）。

**現況（實讀證據）**：v2 已具備 v4 Level UX 的大部分核心——
- 拖拉：`LevelSystem.tsx` `Card` draggable + `Container` onDrop + `moveTo(id,label)`。
- sub/cub 巢狀盒：`Box`（cub 🔒／sub ↕）、`createGroup`／`dissolveGroup`／`createCubChild`。
- nb 標記：`NbArea` nbMode/confirmNb/removeNb。
- 資料推導：`logic.ts::derive()` → `ascription`／`level`／`countersignature`／
  `parent_countersignature`／`order`，掛 `level_entries`，即時 R1–R9 validate。

因此**這不是從零抄 v4，而是補齊 `07-level-system-ux-gap.md` 列出的差距**。實作者必須先讀 `07`，
以其 §3 差距清單與 §5 行動總結為準。以下是把 `07` 差距轉為實作要求的規格：

**3.1.1 需補的 UX 差距 → v2 實作要求**（細節與證據見 `07` §3；此處定實作邊界與資料對應）

| 差距（07 §3）| v2 實作要求 | 資料落點 | 治理 |
|---|---|---|---|
| **main_instance 硬鏈**（07 §3 標為最大缺口：v4 有 hidden group identity 把多列綁成一個不可拆的主序實例；v2 `countersignature`/`parent_countersignature` 不等價）| **先裁決**（見下方「本節待決」），再實作。若採 v2 既有分組語義能表達則優先；不足才最小加欄 | `level_entries`（優先既有欄；加欄需 migration + ADR 記錄）| C1 不涉 TMU；C5 加法 |
| **難度係數 difficulty_factor**（07 §3：v4 有難度係數調整，資料與 v2 `coefficient` 等價，只缺前端 UI）| 補前端調整 UI（每列可設係數，影響 `second = raw_seconds × coefficient`）| v2 `level_entries.coefficient`（既有欄，**無需加欄**）| 顯示層；`second` 由 v2 既算 |
| 其餘 07 §3 列出的呈現/互動差距 | 依 `07` §3 逐項在 React 補；優先用 v2 既有 store action | `level_entries` 既有欄為主 | C2 若涉文字則雙語 |

**3.1.2 明確不做**（07 §4：依賴不整合的東西）
- v4 的獨立 Plan 版本（release/archive/version）、LB scenario 連動、`station_code` 站別指派
  （屬 LB/Layout 範疇）、WI Set 快照式 plan item、`*_snapshot_json` 凍結欄——**全部不做**。
- v4 前端 V1 本來就隱藏的 sub/nb/station 互動（`07` 記錄「僅後端有、前端未實作」）——
  不以 v4 為對照基準；v2 這些面向反而較完整，維持 v2 現況。

**3.1.3 i18n（C2）**
- Level 列顯示的敘述沿用 `useRowNarr`（已雙語，讀 `narrative_zh`/`narrative_en`）。
- 若本功能域新增任何可讀文字欄位（如群組顯示名），一律 `_zh`/`_en` 雙欄 + i18n review。

**3.1.4 資料關聯性（User 特別要求思考的點）**
- 每個拖拉/分組操作對應的資料異動必須明確（`07` §1/§3 已逐項對應）：
  - 拖 row 進群組 → 改該 row 的 `countersignature`（所屬群組）。
  - 建 sub/cub 群組 → `groupMeta` + 群組的 `parent_countersignature`（巢狀 sub⊃cub）。
  - 設主序 → head 列的 `level`；`ascription='main'`；群組內 `order`。
  - nb 標記 → `number` + `number_count`。
  - 難度係數 → `coefficient`（→ `second`）。
- **鐵則**：這些是掛在 `wi_row` 的活資料，跟 worksheet 版本走；`wi_row.id` 在同版本編輯期穩定
  （「改 MOST 不丟 level」，`worksheet.py` WiRow docstring）。UX 操作即時改活資料 + 即時 R1–R9 validate，
  不進獨立快照。

**3.1.5 本節資料模型決策（已由 User 裁決 2026-09-04：採 (i)，見 `09-open-question-A-main-instance.md`）**
- **main_instance 硬鏈的資料表達 → 採 (i)：用 v2 既有 cub group 語義，不加欄，零 schema 變更。**
  - 依據：main_instance 的實際消費者只有 LB solver 與 Line Layout（`line_balance.py:9-13/53/80`、
    `line_layout.py:93-178`），兩者皆不整合/待定；v2 無讀取端，加 `main_instance_id` 會是孤兒欄。
  - v2 既有 **cub group**（`same_station:True`、`movable:False`、ordered members，`level.py::build_output`）
    已表達「不可拆 + 內部有序的硬鏈」，即 main_instance 在 Level 標註上的等價。
  - **落地**：前端拖拉圈選一組動作 → 建 cub 群組（`createGroup('cub',...)`），落
    `level_entries` 既有欄（`countersignature=cubN` + `parent_countersignature` + `order`），**無新欄、無 migration**。
  - **不做**：v4「同 main 多 instance 可互換」的 solver 自由度提示（無消費者）。
  - 可逆：日後若整合需要該自由度的下游，再以加法補 `main_instance_id` 並在其消費端一起落地。

**3.1.6 驗收準則**
- 使用者可用拖拉完成 v4 等價的 main/sub/cub 分組與難度係數調整；操作即時反映在 `level_entries`。
- R1–R9 validate 即時、後端權威（沿用 v2 現有 `/level/validate`）。
- 切 en locale，Level 面板無中文殘留（C2）。
- 未新增任何 TMU 計算路徑；`run_all.py` golden 全綠（C1）。
- 未新增 Plan 表、未回退 v2 既有 Level 能力（C4）。

---

### 3.2 E-SOP（P1，工程量大，骨架先行）

**v4 設計邏輯（參考，證據 `01` §1.6、`03` §4.1、`04` §6）**：Station-based E-SOP，5 表
（document/station_page/step/asset/annotation）；from-LB／from-layout 快照生成、站別頁、
步驟、圖片標註（原圖保留）、preview/print/export-pdf；`esop_generator.py` 凍結快照、只讀不改上游。

**v2 目標實作骨架**：
- 新增 E-SOP 資料表（async ORM、加前綴避免撞名）；文字欄雙語（C2）。
- **資料源介面待決**（`05` §5 開放問題 2）：v4 E-SOP 吃 LB scenario 的站別指派；v2 不建 LB，
  故 E-SOP 的「站別 + CT」輸入需重新界定——接 User 外部 LB 系統輸出，或以 v2 WI Set/Level 為輸入手動指派。
  **此決策未定前，E-SOP 不動工。**
- 檔案儲存（對應 v4 `storage.py`）用 v2 既有機制；PDF 渲染管線需新建。
- TMU 顯示回算沿用 v2 引擎值，不採 v4 快照（C1）。

**待決前提**：**B'（E-SOP 在新邊界下的定位）**——見 `10`。站別不在 MOST（User 裁決 2026-09-04），
v4 的站別式 E-SOP 屬 LB 系統下游；v2 若做 SOP 只能做「工序級 SOP」（不含站別）。**是否做、未定前不動工。**

---

### 3.3 ~~Line Layout~~ ⛔ 移出 v2 整合範疇（User 裁決 2026-09-04）

**v4 設計邏輯**：5 種工站布局，疊在 LB scenario 上——本質是**「站」的視覺化**。
**裁決**：站別的決定不在 MOST 系統（見 `10`）；工站布局屬**外部 LB 系統**範疇，**v2 不做**。

---

### 3.6 DAG 輸出屬性補齊（取代原 LB/Layout，成為 MOST→LB 契約的真正整合價值）

**背景（User 定義的邊界，見 `10`）**：MOST 系統的產物是「帶屬性的 DAG」，交給外部 LB 系統決定
站別/worker。v2 已有此 DAG 骨架——`most_engine/level.py::build_output()` +
`export_service.py::lb_api_payload()`（dry-run，LB request model 待 User 提供）。整合價值 = **補齊 DAG 屬性完整度**。

**v2 現有 DAG 屬性**（實讀 `build_output`）：`nodes`（含 `levels`/`level_min`/`level_max`/`variable` 自由度）、
`precedence_edges`、`groups`（sub 可移動 / cub 同站不可拆）、`cub_groups`/`sub_groups`/`group_parents`、`number_constraints`。

**待補齊（對照 User 屬性清單，見 `10` 差距表）**：
| 屬性 | v2 現況 | 動作 |
|---|---|---|
| 群組 / 不可拆分站 / 前序 | ✅ 有（groups/cub same_station/precedence_edges） | 無 |
| 可否 offline | ❌ 無 | **新增屬性**（`level_entries` 加欄或 build_output 帶出；純標註、不進 TMU，C1 安全） |
| quantity | ⚠️ 有 frequency | 確認 frequency 是否即 LB 要的 quantity，或另定義 |
| 可否平行 | ⚠️ level 自由度部分表達 | 確認用既有 `variable` 或新增明確布林 |
| 不可拆分動作 | ⚠️ cub 表達同站不可拆 | 確認「單一動作內部不可拆」是否已涵蓋 |

**待決前提**：**B''（DAG 屬性清單精確定義）**——見 `10`。確認 offline/quantity/可平行/不可拆分動作的
精確語義後，擴充 `build_output` 合約（MOST→LB 契約）。此為 Phase 2 主要標的。

---

### 3.4 Case 審批工作流（P3，reviewer 角色已裁決）

**v4 設計邏輯（`01` §1.7、`03` §4.4、`04` §7）**：analysis_case + step + step_slot + audit；
submit/review/request-changes/approve/archive 狀態機；含 `video_timestamp_start/end`（影片工時研究，v2 完全缺）。

**裁決（User 2026-09-04）：整合 Case 審批流，並採 (a) 新增 reviewer 階層**
（`viewer<analyst<reviewer<approver<admin`，見 `12`）。保留 v4 四眼分權（提交者 analyst 不能自審自核；
狀態機 `submitted→reviewed→approved`，review 是 approve 前的獨立品管關卡）。

**v2 目標實作**：
- RBAC：`auth/deps.py` ROLE_ORDER 插入 reviewer（v2 無硬編數字、具名查表，插入安全，見 `12`）。
- 狀態機 + 角色分權（submit=analyst / review+request-changes=reviewer / approve=approver / archive=admin）。
- 可選 `video_timestamp_start/end` 欄位（影片工時研究）；文字欄雙語（C2）。
- **E（實體對映）已裁決全對映 v2 現有實體**（見下 §3.5）；Case 若對映到 worksheet 版本流程，需協調
  v2 既有 `ProcessVersion` publish/retire 與 v4 五段狀態機的關係（實作階段細化）。

---

### 3.5 v4 獨立實體 → 全對映 v2 現有實體（P3，已裁決 E：零新增表）

**裁決（User 2026-09-04，採 `13` 建議）：全部對映到 v2 現有實體，零新增資料模型、零 schema 變更。**

| v4 實體（證據）| v2 對映 |
|---|---|
| MostSequenceItem（`most.py:28`）| `wi_row` + `most_cycle`（`worksheet.py:106/147`）|
| MostMiStatement（`most.py:65`）| `most_worksheet` + `wi_rows`（`worksheet.py:63`）|
| MostMiStatementItem（`most.py:106`）| `wi_row`（v2 列天生 WI-owned，無 v4 共享列缺陷）|
| ActionModuleTemplate（`most.py:151`）| `motion_module` category='action'（`motion_module.py:49`）|
| WITemplate（`most.py:186`）| `motion_module` category='wi-template'（v2 schema 註解明寫「對應 v3 MI statements」）|
| ProcessRoute（`most.py:245`）| `wi_set_project`/`wi_set_item`（`wi_set.py`）|
| WISetProject（`most.py:300`）| `wi_set_project`（同名同義）|

- **鐵則**：對映到 v2 後，TMU 一律交回 v2 單一引擎（v4 route 端自算 sum/max 不採信），golden 安全（C1）。
- 落地順序（P3）：中段列→wi_row+most_cycle；MI→worksheet；範本→motion_module 兩 category；ProcessRoute/WISetProject→wi_set。

---

## 4. 字典/規則資料整合（Phase 0 前置，所有 MOST 相關功能的地基）

（依 `02` §4／§7、`03` §3／§6；DB 實值複核見 `11`，已完成）

- **權威落點**：v2 DB 的 `rule_sets` 12 表（seed 由 `scripts/import_v3_dictionary.py`）。
- **DB 實值複核已完成（C 裁決，見 `11`）**：實查確認 `m_press`(fixed,3 TMU) 已在 v2 DB `rule_m_verbs`；
  CM「A2 vs A3」是 v4 端命名重構、v2 DB 無 slot_key 表、無對應資料差異（引擎靠位置消費）；
  live DB 重算 GM=28／CM=29 全綠。**不需另設阻擋關卡**，把此實查登記為 Phase 0 驗收紀錄即可。
- **映射器**：寫 v4 `parameter_options`（通用一表）→ v2 12 分表的映射（依 `parameter_code`+`control_key`+
  `input_type`）。**M 參數最複雜**（v4 一表 → v2 五表 + pricing_kind），逐 option 驗。
- **字典差異合併非覆蓋**（`03` §3.1）：`M_PRESS` 已在 v2；CM A2→A3 對 v2 無影響（僅 v4 命名）。
  合併後**必過 golden**（GM=28／CM=29）。
- **零值選項補齊**（`02` §4）：v4 缺 B/X/I 的 `none` 選項，映射時必須補（否則 GM/CM 黃金值算錯）。

---

## 5. 建議的實作階段（扣除 LB／Layout）

每階段驗收門檻：`run_all.py` + `engine_golden_test.py` 全綠（C1）；不回退 v2 既有測試（C4）。

- **Phase 0 — 治理地基**：認證換接（§2）；字典/規則映射器 + 差異合併 + 零值補齊（§4）；
  移轉驗證框架（原始選擇→v2 重算→比對快照）；golden gate 接 CI。（DB 實值複核已完成，見 `11`，登記為驗收紀錄。）
- **Phase 1 — Level System UX**（§3.1，共識明確、問題 A 已裁決，**可動工、零 schema 變更**）。
- **Phase 2 — DAG 輸出屬性補齊**（§3.6，MOST→LB 契約擴充；先確認 B'' 屬性清單）＋
  **（若 B' 裁決要做）工序級 SOP**（§3.2）。**Line Layout 已移出範疇**（站屬 LB 系統）。
- **Phase 3 — Case 審批流（含新增 reviewer 階層，§3.4）＋ v4 實體對映 v2（§3.5，E 已裁決）**。

---

## 6. 開放問題裁決狀態（2026-09-04 User 已裁決 A/C/D/E；B 修正為 B'/B''）

| # | 開放問題 | 狀態 | 來源 |
|---|---|---|---|
| A | main_instance 硬鏈的資料表達 | **✅ 裁決 (i)：用既有 cub group、不加欄** | `09`、§3.1.5 |
| B | ~~E-SOP/Layout 上游資料源~~ | **✅ 修正：站不在 MOST。MOST 輸出帶屬性 DAG；Layout 移出範疇** | `10` |
| B' | E-SOP 在新邊界下的定位（工序級 SOP 要不要做？還是 SOP 全歸 LB 系統）| ⏳ **待裁決**（阻擋 §3.2）| `10` |
| B'' | DAG 屬性清單精確定義（offline/quantity/可平行/不可拆分動作）| ⏳ **待裁決**（阻擋 §3.6 Phase 2）| `10` |
| C | 字典 DB 實值複核 | **✅ 已完成複核，登記為 Phase 0 驗收紀錄**（m_press 在 DB、CM A2/A3 對 v2 無影響、golden 全綠）| `11` |
| D | v4 reviewer 角色對映 | **✅ 裁決：整合 Case 審批流 + 新增 reviewer 階層（analyst<reviewer<approver）** | `12` |
| E | v4 獨立實體去留 | **✅ 裁決：全對映 v2 現有實體、零新增表** | `13` |

> **可動工**：Phase 0（治理地基，無阻擋）、Phase 1（Level System UX，無阻擋）。
> **待裁決才動工**：Phase 2 需 B''（DAG 屬性清單）＋ B'（工序級 SOP 是否做）；Phase 3 已具備裁決（D/E）可規劃。

---

## 7. 給實作 agent 的總則

1. **先讀審查文件再動工**：`00`（基準）、`02`（MOST 計算，C1 的依據）、`07`（Level UX 差距）、
   以及對應功能域的 `03`/`04` 章節。
2. **每個功能域動工前確認其「待決前提」已由 User 裁決**（§6 表）。未裁決不動工。
3. **C1–C5 是硬約束**，任何一條違反即回退。特別是 C1（golden 全綠）每個 commit 都驗。
4. **不搬 v4 code**：讀懂 v4 領域邏輯，在 v2 架構重寫。v4 的 `calculation*.py` 與快照 TMU 永不採信。
5. **資料關聯性優先**：實作 UX 前，先確認每個互動對應的 v2 資料欄位異動（§3.1.4 是範例模式）。
