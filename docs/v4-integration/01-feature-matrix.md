# 01 — v4 ↔ v2 大功能對照矩陣

> 審查範圍：v4 = `minimost_level/minimost/apps/api`（另一位 IE 獨立開發的 MiniMOST 系統後端）；v2 = `ddm-v2`（現行目標系統）。
> 方法：**實讀雙方程式碼**，不只信文件。每個結論標注證據（`檔案:行號`）。這是唯讀審查，不修改任何程式。
> 硬性前提：v2 的 MOST engine 是單一權威、TMU 黃金值鎖定 GM=28／CM=29，整合不得污染其計算正確性。

## 0. 一頁摘要

| 面向 | v4 | v2 | 整合結論 |
|---|---|---|---|
| TMU 計算引擎 | **兩套**（`calculation.py` 舊 index 版 + `calculation_v2.py` 新 Decimal 版），演算法散在路由 service | **單一權威** `most_engine/`，資料驅動 + 黃金值鎖 + engine_gate 守門 | v4 的計算**不可**帶入 v2；必須重接到 v2 engine |
| 認證/RBAC | 本地 JWT 登入（帳密 + bearer token），角色為集合 admin/analyst/reviewer/approver | 聯邦 Traefik ForwardAuth（gateway 注入身分），角色為階層 viewer<analyst<approver<admin | 全部 v4 端點須換掉 auth 依賴；角色需對映 |
| 規則資料 | Dictionary Version（`dictionaries.py`，含 slot/option/sequence-model） | 版本化 rule-set（`rule_set.py`，clone→改→publish→activate→retire） | 兩套版本模型不同，需資料模型對映 |
| 三層動作庫 | Action Module → WI Template → Process Route（`most_workbench_v3.py`） | Motion Module → WI Template/Worksheet → WI Set Project（`motion_module.py` + `wi_set.py`） | 概念對得上，實作/命名/版本治理不同 |
| Level System | **Level Plan**（快照 WI Set + 疊 main/sub/cub/nb + 產 CT，餵 Line Balance） | **驗證引擎**（R1–R9 validator，餵 LB export） | v2 是「驗證器」，v4 是「產出物 + 下游資料源」——差異最大的兩邊都有 |
| Line Balance | **beam-search 前序約束裝箱求解器** + 情境存檔（`line_balance.py` service） | **無求解器**；只有 LB CSV / LB API payload 匯出 | ★ v4 獨有的核心價值 |
| Line Layout | 視覺化工站布局（free/straight/u/l/two_sided），疊在 LB 情境上 | **無** | ★ v4 獨有 |
| ESOP | E-SOP 文件產生器（從 LB / Layout 快照，含步驟/圖片/標註/PDF/列印） | **無** | ★ v4 獨有 |
| Analysis 案例工作流 | 案例 + 步驟 + submit/review/request-changes/approve/archive + audit-log | 只有唯讀 `cases.py`（GET /cases） | v4 有完整審批工作流，v2 幾乎沒有 |
| WI 匯入（Excel） | 由 dictionary import（`dictionaries.py` import/import-base64） | 完整 Excel 匯入管線（upload→map→parse-jobs→submit + profiles） | v2 較完整；方向相反 |

★ = v4 有、v2 完全沒有，是整合的主要標的。

---

## 1. 逐項對照矩陣

欄位：**功能** | **v4 有（證據）** | **v2 有（證據）** | **差異** | **整合影響／優先級**

### 1.1 MOST 計算引擎（TMU 權威）

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| TMU 單一計算引擎 | 有，但**分裂成兩套**：`services/calculation.py`（index 版，`calculate_step` 用 `base_index+rule_adjustment`，`calculation.py:53-97`）與 `services/calculation_v2.py`（Decimal 版，逐參數 A/B/G/P/M/X/I 規則，`calculation_v2.py:1-88`）；`most.py` 路由用 v2 版（`most.py:293` `calculate-row`），`analysis.py` 卻 import 舊版 `from app.services.calculation import TMU_TO_SECOND`（`analysis.py:22`） | 有，**單一權威** `most_engine/calculate.py`：`TMU=(Σ slot index)×multiplier`，讀 `RuleSetData` 資料驅動（`calculate.py:1-18`），並有 `most_compiler/engine_gate.py` 執行期守門（`engine_gate.py:1-8`） | v4 算法散落且雙軌；v2 收斂單一引擎並用 engine_gate + 黃金值鎖死。v4 P 段用「base+modifier、insert⊥snap 互斥、max 2 modifier」（`calculation_v2.py:6-12`），與 v2「Σindex×multiplier」口徑**不同** | **P0 / 硬邊界**：整合任何 v4 功能時，TMU 一律改呼叫 v2 `most_engine`，**禁止**帶入 v4 兩套引擎；需驗 GM=28／CM=29 不漂移（v2 golden：`tests/unit/test_most_engine.py:38-45`、`scripts/core_logic/engine_golden_test.py:65-66`） |
| 黃金值鎖 | 未見等價的 GM=28／CM=29 golden 守衛（v4 以 dictionary option 的 `tmu_value` 直接相加，`calculation_v2.py:_calc_simple_select`） | 有，GM=28／CM=29 多層鎖（`tests/unit/test_most_engine.py`、`scripts/core_logic/engine_golden_test.py:65`、`docs/CI_GATES.md:151`、`docker_smoke.sh:242,248`） | v4 無黃金鎖，正確性靠 dictionary 資料本身 | **P0**：v4 資料匯入 v2 後須跑 v2 golden 驗證 |
| NL 草稿（自然語言預填） | 有，`most.py:240` `/nl-draft` → `services/nl_draft_parser.py`（回 slot_suggestions/confidence/badge） | 有，`nl_draft.py:42` `/worksheets/nl-draft` + `parse_jobs.py` 非同步解析 + `ai_review.py` 覆核 | 兩邊都有 NL→草稿；v2 另有 parse-jobs 佇列與 AI review 覆核閉環 | P2：概念重疊，v2 較完整；v4 parser 可作語料參考 |

### 1.2 動作/範本三層結構

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 動作模組庫（第一層） | Action Module Templates，CRUD+clone+reorder（`most_workbench_v3.py:320,370,468,484,528`；三層註解 `most_workbench_v3.py:1-6`） | Motion Module，CRUD+clone+publish+版本歷史+apply-back+row 級編輯（`motion_module.py:1-19` docstring 列 15+ 端點） | 都有動作庫；v2 有**版本治理**（draft→publish、apply-back 工序表同步回庫、ADR-022 row 級重算發版）v4 較輕 | P2：v2 已較成熟；v4 資料可對映進 v2 motion module |
| WI 範本（第二層） | WI Templates，CRUD+items reorder+clone（`most_workbench_v3.py:551,617,667,740,776`） | WI 範本以 worksheet + motion_template 表達（`worksheet.py:21-126`、`motion_template.py:59-141` 含 promote/match） | 結構對得上；命名與版本模型不同 | P2 |
| 製程路線（第三層 / WI Set） | Process Routes，CRUD+items reorder+clone+apply-to-template（`most_workbench_v3.py:838,917,967,1054`） | WI Set Projects，CRUD+items+reorder+duplicate（`wi_set.py:99-513`），且**快照值權威**：template 條目強制由 server 從 motion module 解析回填，禁止 client 繞過 engine（`wi_set.py:229-256`） | 概念一致（都是把 WI 串成製程）；v2 有值權威快照守則 | P1：整合 v4 Level/LB 需要 v2 WI Set 作上游，映射關係要對清楚 |

### 1.3 Level System

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| Level 標註（main/sub/cub/nb） | 有，**Level Plan**：從 WI Set Project 快照後疊 logic tag，plan CRUD+release+archive+items bulk/reorder+number-rules+validate+duplicate（`level_system.py:1-9` docstring、`339-670`） | 有，**驗證引擎** R1–R9（`most_engine/level.py:1-6`），API `worksheet.py:83` `/level/validate`、`calculate.py:131` `/level/validate` + `:140` `/level/build-output`（對 LB 輸出合約） | **關鍵差異**：v4 的 Level 是**有狀態的產出物**（Plan 實體、release/version、產 `adjusted_ct_seconds`、`main_instance` 操作鏈），且是 Line Balance 的**唯一資料源**（`line_balance.py service:1-30`）；v2 的 Level 是**無狀態驗證器**（給 rows 回 issues，餵 LB export 合約） | **P0**：這是整合 LB 的地基。v4 LB 依賴 Level **Plan**（有 CT、有 main_instance 鏈）。若要把 v4 LB 帶進 v2，需先決定 v2 是否新增 Level Plan 實體，或改以 v2 WI Set + validator 產出等價的原子單元 + 前序約束 |
| Level 產 CT / 難度係數 | 有，plan item 帶 `ct_seconds_snapshot`/`difficulty_factor`/`adjusted_ct_seconds`（`level_system.py:52-60`） | v2 Level row 有 `raw_seconds*coefficient=second`（`most_engine/level.py:LevelRow`），但無 plan 級快照持久化 | v4 把 CT 快照存進 plan item；v2 是即時計算 | P1 |

### 1.4 Line Balance（線平衡）★ ⛔不整合（使用者另有 LB 系統；邏輯整理見 `06`）

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 線平衡求解 | **有，核心價值**：`services/line_balance.py` beam-search 前序約束裝箱（`ALGORITHM_VERSION="v2"`、`_BEAM_WIDTH=12`、`_BRANCH_LIMIT=4`，`line_balance.py:36-46`）；前序來自 Level Plan（main 層 N→N+1、main_instance 內硬鏈、cub 區塊不可切，`line_balance.py:8-30`）；端點 `/simulate`、`/simulate-multi`、情境 CRUD（`line_balance.py:114-276`） | **無求解器**。只有匯出：`export.py:56` `/export/lb-csv`、`export.py:69` `/export/lb-api`（把 worksheet 轉成 LB 系統可吃的 payload），求解交給外部 LB 系統 | ★ v4 把「LB 求解」內建；v2 只做「餵資料給外部 LB」。這是兩系統定位的根本差異 | **P0 / 主要整合標的**：v4 LB 求解器是最有整合價值的一塊。前置條件＝先解決 Level Plan 資料源（見 1.3）與 CT 快照。求解器本身**不碰 TMU 計算**（只吃 CT 秒數），對 v2 engine 權威**無污染風險**，可較安全移植 |
| LB 情境存檔（snapshot） | 有，`LineBalanceScenario` 存自足快照，Level Plan 之後變動不影響（`line_balance.py:1-6` docstring、`_serialize_scenario` `:97-124`） | 無情境概念 | v4 有情境版本化 | P1 |

### 1.5 Line Layout（工站布局）★

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 視覺化工站布局 | 有，`line_layout.py`：疊在 LB 情境上，5 種布局 `free/straight/u_shape/l_shape/two_sided`（`line_layout.py:23`），存 canvas/zoom/pan/station_layout/arrow_layout/sync_group（`line_layout.py:44-60`）；端點 `/scenarios/from-line-balance/{id}`、CRUD、duplicate（`line_layout.py:245-391`） | **無** | ★ v4 完全獨有 | P2：依賴 LB 先落地；純視覺層、不碰計算，整合風險低但工作量大（前端為主） |

### 1.6 ESOP（電子標準作業書）★

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| ESOP 文件產生 | 有，`esop.py`（35KB，21 端點）：from-line-balance / from-layout 產文件、station-page/step 編修、regenerate-instruction、資產上傳/標註、preview/print(HTML)/export-pdf（`esop.py:356-915`）；service `esop_generator.py` 明言凍結快照、只讀不改上游（`esop_generator.py:1-8`） | **無** | ★ v4 完全獨有；且是完整子系統（文件生命週期 release/archive、圖片標註、PDF/列印輸出） | P1（業務價值高）／工程量大：依賴 LB + Layout。需新資料表 + 檔案儲存（`services/storage.py`）+ PDF 渲染管線；不碰 TMU，計算污染風險低 |

### 1.7 Analysis 案例工作流

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 案例研究 + 審批流 | 有，`analysis.py`：case+step CRUD、`submit`/`review`/`request-changes`/`approve`/`archive`、audit-log、Excel 報表（`analysis.py:97-403`、`reports.py:15`），用 4 種角色守門（`analysis.py:10-16`） | 幾乎沒有：只有唯讀 `cases.py:20` `GET /cases`（教學案例列表）；審批以 worksheet publish/retire（`worksheet.py:102-126`）表達 | v4 有正式的**多角色審批工作流**（reviewer/approver）；v2 用 worksheet 狀態機，無 review/approve 分離 | P2：審批流可作 v2 治理增強參考；但要對映 v2 的 viewer<analyst<approver<admin 階層 |

### 1.8 匯出

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| Excel / 報表 | 案例 Excel（`reports.py:15`）、ESOP PDF/print（`esop.py:900,915`） | WI 1128 Excel（`export.py:42`）、MOST 報表 xlsx（`export.py:78`）、WI 預覽（`export.py:33`） | 各有其匯出；v4 偏 ESOP/PDF，v2 偏 WI 工序單 | P2 |
| LB 匯出 | 無（LB 內建，不需匯出） | LB CSV + LB API payload（`export.py:56,69`） | 見 1.4 | — |

### 1.9 規則資料版本治理

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 規則/字典版本 | Dictionary Version：seed-default/import/activate/archive/clone/publish、option CRUD、sequence-model/slot（`dictionaries.py:266-903`），admin 守門（`dictionaries.py:14`） | Rule-set：list/active/full、clone-draft、publish/activate/retire/unretire/delete、diff、export/import、param option CRUD、bands、synonyms（`rule_set.py:62-500`、`synonyms.py`） | 兩套版本模型；v2 有 diff/retire/unretire/回放隔離鐵則（`docs/CI_GATES.md:14`），治理更嚴 | **P0（資料對映）**：v4 dictionary option 的 `tmu_value/fixed_seconds/control_key` 需對映到 v2 rule-set 的 band/option/index 語意，且對映後須通過 v2 golden |

### 1.10 認證 / RBAC

| 功能 | v4 | v2 | 差異 | 整合影響／優先級 |
|---|---|---|---|---|
| 認證方式 | **本地 JWT**：`/auth/login` 帳密驗證 + `create_access_token` + bearer（`auth.py:58-72`、`core.security`） | **聯邦** Traefik ForwardAuth：只讀 gateway 注入的身分，JIT 建 viewer；本地 dev override（`auth/identity.py:3,85`、`auth/deps.py:49`、`startup_checks.py:33,61`） | 根本不同：v4 自己管帳密，v2 委派 gateway | **P0 / 硬邊界**：所有 v4 端點的 `Depends(get_current_user)`/`require_analyst_or_admin` 都要換成 v2 的 `current_user`/`require_role`；v4 的 User/password 模型**不可**帶入 v2 |
| 角色模型 | 集合式，admin/analyst/reviewer/approver（`dependencies.py:47-51` `require_roles`） | 階層式 ROLE_ORDER viewer(0)<analyst(1)<approver(2)<admin(3)（`auth/deps.py:17,60-64`） | v4 有 reviewer（v2 無此角色）；v2 有 viewer 只讀層 | **P1**：v4 reviewer/approver 分離需對映到 v2 approver；審批流（1.7）落地時一併處理 |
| 使用者管理 | 有，`users.py` CRUD+roles+disable（`users.py:34-118`） | 有，`admin_users.py`（`:38-59`）+ audit-log（`audit_log.py:33`） | 都有；模型不同 | P2 |

---

## 2. 整合優先級彙總

> **範圍裁決（使用者 2026-09-04）：Line Balance／KPI 不整合進 v2**（使用者另有專門 LB 系統）。
> 1.4 LB 求解器與其 KPI 計算降級為「邏輯參考」，整理於 `06-line-balance-kpi-logic.md`，不在 v2 重建。

**P0（硬邊界 / 必須先處理，攸關計算正確性與安全）**
- 1.1 TMU 引擎：v4 功能一律重接 v2 `most_engine`，禁帶 v4 雙引擎；驗 GM=28／CM=29。
- 1.9 規則資料對映：v4 dictionary → v2 rule-set，對映後過 v2 golden。
- 1.10 認證：全部 v4 端點換 v2 auth 依賴，不帶 v4 帳密模型。
- 1.3 Level System 資料源：決定 v2 是否引入 Level Plan 實體（E-SOP／Layout 的地基）。

**P1（高業務價值，依賴 P0）**
- 1.6 ESOP 子系統（業務價值高、工程量大）。

**P2（增強 / 可延後）**
- 1.5 Line Layout（純視覺層，前端為主；上游資料源介面待定，因 LB 不整合，見 05 §5）。
- 1.7 Analysis 審批工作流（治理增強）。
- 1.2 / 1.8 動作庫與匯出（v2 多已具備）。

**⛔ 不整合（使用者另有系統）**
- 1.4 Line Balance 求解器＋KPI 計算：僅整理邏輯供參考（`06-line-balance-kpi-logic.md`）。v2 維持既有
  「LB CSV／API 匯出」介面（`export.py:56/:69`），不建求解器。

---

## 3. 對「不污染 v2 計算正確性」的關鍵守則（給後續子文件）

1. **v4 的 `calculation.py` / `calculation_v2.py` 一律不移植**。任何需要 TMU 的地方改呼叫 v2 `most_engine`（經 `engine_gate`）。證據：v2 單一權威 `most_engine/calculate.py:1-18`、engine_gate `most_compiler/engine_gate.py:1-8`。
2. **LB / Layout / ESOP 只吃「秒數 / CT 快照」，不重算 TMU**——這是它們可較安全移植的原因。證據：v4 LB service 只讀 plan item 的 `adjusted_ct_seconds`（`line_balance.py service`），ESOP 明言凍結快照只讀（`esop_generator.py:1-8`）。移植時必須確保 CT 來源是 v2 engine 算出的值。
3. **任何 v4 資料進 v2 後，先跑 v2 golden**（`scripts/core_logic/run_all.py`、`tests/unit/test_most_engine.py`）再談功能驗收。

---

## 附錄 A：端點清單來源（file:line）

- v4 路由（`minimost_level/minimost/apps/api/app/api/routes/`）：`most.py`(18 端點)、`most_workbench_v3.py`(23)、`esop.py`(21)、`dictionaries.py`(19)、`level_system.py`(14)、`wi_set_builder.py`(10)、`line_balance.py`(8)、`line_layout.py`(6)、`analysis.py`(15)、`users.py`(5)、`auth.py`(3)、`reports.py`(1)。逐行清單由 `grep -nE '@router\.(get|post|put|patch|delete)\('` 擷取。
- v2 路由（`ddm-v2/src/ddm_v2/api/routes/v2/`）：`rule_set.py`(20)、`motion_module.py`(15+)、`wi_set.py`(10)、`catalog.py`(9)、`worksheet.py`(7)、`import_excel.py`(7)、`calculate.py`(6)、`motion_template.py`(6)、`export.py`(5)、`vocab.py`(4)、`parse_jobs.py`(4)、`i18n.py`(4)、`admin_users.py`(3)、`synonyms.py`(3)、`wi_context.py`(3)、`ai_review.py`(2)、`dsx.py`(2)、`search.py`(1)、`cases.py`(1)、`nl_draft.py`(1)、`audit_log.py`(1)。

> 本文件所有「v4 有 / v2 有 / 無」的結論均以上述實讀之 route 與 service 程式為據；標 ★ 的 v4 獨有功能已用 v2 全庫 grep 反向確認 v2 無等價實作（`esop|line.?layout|line_balance|beam|precedence|station` 僅命中 v2 Level System 語境，無 ESOP/Layout/LB 求解器）。
