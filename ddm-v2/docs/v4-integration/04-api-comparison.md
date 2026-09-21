# 04 — API 對照（v4 → v2）

> 審查範圍：v4 `apps/api/app/api/routes/*` 全部端點，逐一對照 v2 `src/ddm_v2/api/routes/v2/*`。
> 唯讀審查，不修改任何程式碼。所有結論標注證據來源（`檔案:行號`），關鍵語義均回到實際檔案驗證。
> 目的：作為「把 v4 功能整合進 v2」的 API 層依據，並明確標出 **v4 有但 v2 無** 的端點。

## 0. 方法與證據基礎

**v4 router 掛載**（全部掛在 `/api` 前綴之下）：
`app/main.py:37-49` 依序 include：`auth, users, dictionaries, analysis, reports, most, most_workbench_v3, wi_set_builder, level_system, line_balance, line_layout, esop`。
router 各自帶 prefix（`app/api/routes/*.py` 的 `APIRouter(prefix=...)`）：

| router | prefix（＋`/api`）| 檔案:行 |
|---|---|---|
| auth | `/api/auth` | `auth.py:14` |
| users | `/api/users` | `users.py:15` |
| dictionaries | `/api/dictionaries` | `dictionaries.py:25` |
| analysis | `/api/analysis` | `analysis.py:25` |
| reports | `/api/reports` | `reports.py:12` |
| most | `/api/most` | `most.py:32` |
| most_workbench_v3 | `/api/most` | `most_workbench_v3.py:34` |
| wi_set_builder | `/api/most` | `wi_set_builder.py:24` |
| level_system | `/api/most/level-system` | `level_system.py:29` |
| line_balance | `/api/most/line-balance` | `line_balance.py:22` |
| line_layout | `/api/most/line-layout` | `line_layout.py:22` |
| esop | `/api/esop` | `esop.py:29` |

**v2 router 掛載**：唯一入口 `route_registry.py`（`V2_ROUTERS`，`route_registry.py:127-149`），
共 21 支 router，各自 prefix 直接寫死完整路徑（如 `APIRouter(prefix="/api/v2")`），
`mount_v2_routers()` 不再疊加 prefix（`route_registry.py:314+`）。v2 全部端點在 `/api/v2` 之下。

**兩邊路徑前綴的根本差異**
- v4：`/api` + 功能域 prefix；MOST 相關集中在 `/api/most*`。
- v2：一律 `/api/v2` + 功能名（少數子域再加：`/api/v2/admin`、`/api/v2/imports`、`/api/v2/i18n`、`/api/v2/dsx`）。
- 整合時 v4 端點路徑一律需重寫成 `/api/v2/...`（見各節整合備註）。

**技術棧差異（影響所有端點的整合成本）**
- v4：同步 `Session`（`Depends(get_db)`）、本地 JWT 認證（`auth.py`）、SQLAlchemy 同步 ORM。
- v2：async `AsyncSession`（`get_db_session, scope="function"`）、聯邦 ForwardAuth（無本地登入）、Pydantic v2 schema。
- 任何 v4 端點搬進 v2 都需：改 async、換認證依賴、改用 v2 的 `error_handlers`/結構化錯誤、Pydantic v2 schema。

---

## 1. MOST Workbench（單列計算 / NL 草稿 / 字典讀取）

v4：`most.py`（prefix `/api/most`）。v2：`calculate.py`、`nl_draft.py`、`ai_review.py`（prefix `/api/v2`）。

| v4 endpoint | v2 對應 endpoint | 差異（路徑/方法/語義）| 整合備註 |
|---|---|---|---|
| `GET /api/most/dictionary/active`（`most.py:217`）| `GET /api/v2/rule-sets/active`（`rule_set.py:71`）| 語義相近：取當前生效規則集。v4 稱 dictionary version，v2 稱 rule-set。| 併入 v2 rule-set 概念；v4 dictionary=v2 rule-set。 |
| `GET /api/most/dictionary/workbench-options`（`most.py:230`）| `GET /api/v2/rule-sets/{code}/options`（`calculate.py:83`）；另 `GET /api/v2/rule-sets/{code}/params/{param}/options`（`rule_set.py:390`）| v4 一次回整包 workbench 選項（含 control 結構，`most.py:_build_workbench_options`）；v2 分成 options 總表 + 逐 param 選項。| v2 需確認 options 是否含 v4 的 control 結構；若前端需要 control-key，v2 options 合約可能要擴充（不改 engine）。 |
| `POST /api/most/nl-draft`（`most.py:240`）| `POST /api/v2/worksheets/nl-draft`（`nl_draft.py:42`）| 皆為 AI 預填草稿、非最終計算。v4 回 `slot_suggestions` dataclass 序列化（`most.py:240-289`）；v2 走 worksheet context。| 語義對齊；欄位結構不同，需 schema 對映。v2 另有 `POST /api/v2/nl-drafts/{run_id}/reviews`（`ai_review.py:42`）做人審回饋，v4 無此審查回路。 |
| `POST /api/most/calculate-row`（`most.py:293`）| `POST /api/v2/minimost/calculate`（`calculate.py:96`）| **核心語義差異**：v4 是「單列 MI row」計算（slot_selections + frequency + is_simo → row_result，`most.py:293-360`），逐 slot 呼叫 `calculate_slot_tmu` 並自組句子；v2 是整個 **cycle** DTO → 權威 TMU + per-slot breakdown（`calculate.py:96-129`），engine 為單一權威、黃金值鎖定（GM=28/CM=29）。| **整合紅線**：v4 的 slot TMU 計算路徑（`calculate_slot_tmu`）不得取代 v2 engine。v4 的「單列 + frequency + is_simo + 自動組句」在 v2 目前無對應——可能需在 v2 新增「單列預覽」端點，但 TMU 一律轉呼叫 v2 `compute_cycle`。 |
| `POST /api/most/sequences`（201, `most.py:363`）；`GET /sequences`（`:461`）；`GET/PATCH/DELETE /sequences/{id}`（`:473/:486/:540`）| **v2 無直接對應**（v2 以 worksheet + wi-row 承載，非獨立 sequence CRUD）| v4 有一套獨立「sequence（MI row）」持久化 CRUD。v2 的資料模型是 worksheet/wi-row（`worksheet.py`、`wi_context.py`）。| **v4 有 v2 無**（模型層面差異）。整合須決定：把 v4 sequence 映到 v2 wi-row，或評估是否需要獨立實體。屬資料模型議題，另見 02/03 文件。 |
| `POST /api/most/mi-statements`（201, `most.py:560`）；`GET /mi-statements`（`:632`）；`GET/PATCH/DELETE /mi-statements/{id}`（`:644/:657/:686`）；`PUT /mi-statements/{id}/items/reorder`（`:717`）；`PUT/DELETE /mi-statements/{id}/items/{item_id}`（`:744/:811`）| **v2 無直接對應**（概念近似 WI 工時表/worksheet 的列集合）| v4 「MI statement」= 一組 MI row 的集合（含 items reorder）。v2 對應概念散落在 worksheet + wi_set。| **v4 有 v2 無**（實體命名/邊界不同）。整合須做概念對映：v4 mi-statement ≈ v2 worksheet 的 WI rows 集合。 |
| `PUT /api/most/admin/dictionary/options/{option_id}`（`most.py:847`）| `PATCH /api/v2/rule-sets/{code}/params/{param}/options/{option_code}`（`rule_set.py:422`）| 皆為改單一選項。v4 用全域 option_id；v2 用 (code, param, option_code) 三元組定位（版本化）。| v2 定位更嚴謹（綁 rule-set 版本）。v4 option 編輯須轉成 v2 的版本化 clone→改→publish 流程。 |

---

## 2. Dictionary（v4） vs Rule-set（v2）

v4：`dictionaries.py`（prefix `/api/dictionaries`）。v2：`rule_set.py`、`synonyms.py`（prefix `/api/v2`）。
**兩者是同一件事的兩種實作**：版本化的 TMU 計算規則資料。

| v4 endpoint | v2 對應 endpoint | 差異（路徑/方法/語義）| 整合備註 |
|---|---|---|---|
| `GET /api/dictionaries/versions`（`dictionaries.py:266`）| `GET /api/v2/rule-sets`（`rule_set.py:62`）；`GET /rule-sets/active`（`:71`）| 皆列版本。v4「version」≈ v2「rule-set code + version」。| 概念對齊。 |
| `GET /api/dictionaries/{version_id}`（`:425`）；`/{version_id}/sequence-models`（`:433`）；`/slots`（`:448`）；`/options-by-param/{parameter_code}`（`:470`）；`/{version_id}/options`（`:869`）| `GET /api/v2/rule-sets/{code}/full`（`rule_set.py:79`）；`/params/{param}/options`（`:390`）| v4 拆多支細粒度讀取（sequence-models/slots/options-by-param）；v2 以 `/full` 一次取完整規則集 + 逐 param options。| 讀取粒度不同；v2 `/full` 已涵蓋大部分。整合以 v2 `/full` 為主，必要時補細粒度端點。 |
| `POST /api/dictionaries/{version_id}/clone`（`:727`）| `POST /api/v2/rule-sets/{code}/clone-draft`（`rule_set.py:99`）| 語義相同：clone 出 draft。| 直接對齊 v2 的 clone→改→publish 治理。 |
| `POST /api/dictionaries/{version_id}/publish`（`:827`）| `POST /api/v2/rule-sets/{code}/publish`（`rule_set.py:205`）| 相同：發布 = 凍結。| 對齊。 |
| `POST /api/dictionaries/{version_id}/activate`（`:395`）| `POST /api/v2/rule-sets/{code}/activate`（`rule_set.py:222`）| 相同：設為 active。| 對齊。 |
| `POST /api/dictionaries/{version_id}/archive`（`:410`）| `POST /api/v2/rule-sets/{code}/retire`（`rule_set.py:239`）；`/unretire`（`:256`）| v4 只 archive；v2 有 retire + unretire。| v2 生命週期更完整。 |
| `POST /api/dictionaries/import`（`:358`）；`import-base64`（`:376`）| `POST /api/v2/rule-sets/import`（`rule_set.py:179`）| 皆匯入。v4 多一支 base64 變體（前端上傳便利）。| v2 可視需要補 base64 入口。 |
| `GET /api/dictionaries/{version_id}/export`（`:903`）| `GET /api/v2/rule-sets/{code}/export`（`rule_set.py:155`）| 相同。| 對齊。 |
| `PUT /api/dictionaries/options/{option_id}`（`:514`）；`POST /{version_id}/options`（`:575`）；`POST .../options/{option_id}/duplicate`（`:642`）；`DELETE .../options/{option_id}`（`:697`）| `POST/PATCH/DELETE /api/v2/rule-sets/{code}/params/{param}/options[/{option_code}]`（`rule_set.py:407/:422/:468`）；`/duplicate`（`:484`）；英文欄 `PATCH .../{option_code}/en`（`:439`）| v4 option 以全域 id；v2 以 (code, param, option_code) + 綁版本。v2 另有 i18n（en）欄位專用端點。| v2 定位/i18n 更嚴謹。 |
| `POST /api/dictionaries/{version_id}/suggest-code`（`:272`）| **v2 無**（無自動建議 option code）| v4 提供 option code 自動建議。| **v4 有 v2 無**（便利功能，非核心）。可選整合。 |
| `POST /api/dictionaries/seed-default`（`:331`）| **v2 無 HTTP 端點**（v2 seed 走 `scripts/`）| v4 用 API 觸發預設字典 seed。| **v4 有 v2 無**（v2 以離線 script seed，設計差異；不建議搬）。 |
| — | `GET/POST/DELETE /api/v2/rule-sets/{code}/synonyms[/{syn_id}]`（`synonyms.py:35/:51/:112`）；`PUT .../bands`（`rule_set.py:500`）；`GET /rule-sets/{code}/diff`（`:129`）；`DELETE /rule-sets/{code}`（`:277`）| **v2 有 v4 無**：同義詞管理、band（連續值分段）編輯、版本 diff、刪除 rule-set。| v2 規則集治理較 v4 完整；整合方向以 v2 為權威。 |

---

## 3. Level System

v4：`level_system.py`（prefix `/api/most/level-system`）— **持久化 Plan 實體**。
v2：`calculate.py` 的 level 端點 + `worksheet.py` 的 worksheet-level 驗證 — **無狀態驗證引擎 + per-worksheet 驗證**。
**這是全文件最大的架構語義差異。**

| v4 endpoint | v2 對應 endpoint | 差異（路徑/方法/語義）| 整合備註 |
|---|---|---|---|
| `POST /api/most/level-system/plans/{plan_id}/validate`（`level_system.py:648`）| `POST /api/v2/level/validate`（`calculate.py:131`）；`POST /api/v2/worksheets/{id}/level/validate`（`worksheet.py:83`）| v4：對「已存的 Level Plan」跑驗證，回 categorized issues（blocking/warning 計數，`level_system.py:648-668`）。v2：**無狀態** — 傳 level rows 進去回 R1–R9 issues（`calculate.py:131`），或針對某 worksheet 驗證（`worksheet.py:83`）。| v2 的 level engine 是驗證器；v4 把「一組 level items」升格為有生命週期的持久化 Plan。整合須決定是否引入「Level Plan」實體，或把 v4 plan 對映到 v2 worksheet。**engine 正確性不受影響**（純結構層）。 |
| `GET /plans`（`:339`）；`GET /plans/{plan_id}`（`:419`）；`PUT /plans/{plan_id}`（`:430`）；`DELETE /plans/{plan_id}`（`:500`）| **v2 無**（無 Level Plan 實體）| v4 Level Plan CRUD。| **v4 有 v2 無**（核心新實體）。 |
| `POST /plans/from-wi-set/{wi_set_project_id}`（`:359`）| **v2 無**| v4 從 wi-set project 快照生成 Level Plan（`level_system.py:359`，item 帶 `wi_snapshot_json`/`tmu_snapshot`/`ct_seconds_snapshot`）。| **v4 有 v2 無**（關鍵資料流：wi-set → level plan snapshot）。 |
| `POST /plans/{plan_id}/release`（`:448`）；`/archive`（`:466`）；`/unarchive`（`:483`）| **v2 無**（v2 生命週期在 worksheet：`publish`/`retire`）| v4 Level Plan 有 draft/release/archive 生命週期。| **v4 有 v2 無**。若整合，可對齊 v2 worksheet 的 publish/retire 語彙。 |
| `PUT /plans/{plan_id}/items/bulk`（`:527`）；`/items/reorder`（`:557`）；`/items/{item_id}`（`:578`）| **v2 無**（v2 level rows 是計算輸入，非持久 items）| v4 Level Plan item 的 bulk/reorder/單筆編輯。| **v4 有 v2 無**。 |
| `PUT /plans/{plan_id}/number-rules`（`:609`）| **v2 無**| v4 的 nb（number）規則：per-plan 的 `number_tag` + `limit_count`（`level_system.py:609-641`）。| **v4 有 v2 無**（Level System 的 nb limit 治理，對應 domain 的 main/sub/cub/nb）。 |
| `POST /plans/{plan_id}/duplicate`（`:670`）| **v2 無**（v2 有 `worksheets/{id}/clone`）| v4 深拷貝 Level Plan（items + number_rules，`level_system.py:670-740`）。| **v4 有 v2 無**。 |
| — | `POST /api/v2/level/build-output`（`calculate.py:140`）| **v2 有 v4 無**：先驗證再產「Line Balance 輸出合約」（level rows → LB output）。| v2 的 level→LB 是無狀態轉換；v4 的 LB 走另一條 Line Balance 實體路徑（見 §5）。 |

---

## 4. WI Set / Action Modules / Templates / Process Routes

v4：`wi_set_builder.py`（prefix `/api/most`）+ `most_workbench_v3.py`（prefix `/api/most`）。
v2：`wi_set.py`、`motion_module.py`、`motion_template.py`（prefix `/api/v2`）。

### 4a. WI Set Projects

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `GET /api/most/wi-library`（`wi_set_builder.py:184`）| **v2 無同名**（近似 `GET /api/v2/motion-templates`，`motion_template.py:59`）| v4 wi-library = 可重用 WI 素材庫。| 概念近 v2 動作範本庫；需對映確認。 |
| `GET /api/most/wi-set-projects`（`:270`）| `GET /api/v2/wi-set-projects`（`wi_set.py:99`）| 相同語義。| 對齊（僅路徑改 `/api/v2`）。 |
| `POST /wi-set-projects`（`:284`）| `POST /api/v2/wi-set-projects`（`wi_set.py:116`）| 相同。| 對齊。 |
| `GET /wi-set-projects/{project_id}`（`:313`）| `GET /api/v2/wi-set-projects/{project_id}`（`wi_set.py:154`）| 相同。| 對齊。 |
| `PUT /wi-set-projects/{project_id}`（`:326`）| `PUT /api/v2/wi-set-projects/{project_id}`（`wi_set.py:167`）| 相同。| 對齊。 |
| `DELETE /wi-set-projects/{project_id}`（`:350`）| `DELETE /api/v2/wi-set-projects/{project_id}`（`wi_set.py:200`）| 相同。| 對齊。 |
| `POST /wi-set-projects/{project_id}/items`（`:366`）| `POST /api/v2/wi-set-projects/...`（`wi_set.py:217`）| 相同域。| 對齊（欄位需比對）。 |
| `PUT /wi-set-projects/{project_id}/items/reorder`（`:463`）| `PUT /api/v2/wi-set-projects/...`（`wi_set.py:307`）| 相同。| 對齊。 |
| `DELETE /wi-set-projects/{project_id}/items/{item_id}`（`:487`）| `DELETE /api/v2/...`（`wi_set.py:281`）| 相同。| 對齊。 |
| `POST /wi-set-projects/{project_id}/duplicate`（`:513`）| `POST /api/v2/...`（`wi_set.py:349` 或 `:411`）| 相同域（v2 wi_set 有兩支 POST 尚需逐一比對用途）。| 對齊（需核 v2 wi_set.py:349/:411 具體語義）。 |

> **註**：v2 `wi_set.py` 兩支 POST（`:349`、`:411`）與一支 PUT（`:307`）用途需逐檔核對（本次已確認端點存在，具體語義建議整合前再讀 body）。

### 4b. Action Modules（v4 workbench v3） vs Motion Modules（v2）

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `POST /api/most/action-modules`（201, `most_workbench_v3.py:320`）| `POST /api/v2/motion-modules`（201, `motion_module.py:73`）| 皆建立 draft 模組。v4 稱 action-module，v2 稱 motion-module。| 命名對映；語義同（可重用動作模組）。 |
| `GET /action-modules`（`:370`）| `GET /api/v2/motion-modules`（列表+關鍵字，`motion_module.py:57`）| 相同（v2 明列支援關鍵字搜尋）。| 對齊。 |
| `GET /action-modules/{module_id}`（`:382`）| `GET /api/v2/motion-modules/{module_id}`（`motion_module.py:88`）| 相同。| 對齊。 |
| `PUT /action-modules/{module_id}`（`:394`）| `PUT /api/v2/motion-modules/{module_id}`（`motion_module.py:118`）| 相同。| 對齊。 |
| `DELETE /action-modules/{module_id}`（`:468`）| `DELETE /api/v2/motion-modules/{module_id}`（204, `motion_module.py:141`）| 相同。| 對齊。 |
| `POST /action-modules/{module_id}/clone`（201, `:484`）| **v2 無 clone**（v2 有 `promote`，`motion_module.py:337` 為 501 未實作）| v4 支援 module clone；v2 clone 缺、promote 是 501 stub。| **v4 有 v2 無**（clone）。v2 的 promote 尚未實作。 |
| `POST /action-modules/reorder`（`:528`）| `PUT /api/v2/motion-modules/reorder`（`motion_module.py:105`）| 方法不同（v4 POST vs v2 PUT），語義同。| 對齊（方法差異需注意）。 |

### 4c. WI Templates（v4） vs Motion Templates（v2）

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `POST /api/most/wi-templates`（201, `most_workbench_v3.py:551`）| `POST /api/v2/motion-templates`（201, `motion_template.py:69`）| 皆建範本。| 概念對映。 |
| `GET /wi-templates`（`:617`）；`GET /wi-templates/{id}`（`:628`）| `GET /api/v2/motion-templates`（`motion_template.py:59`）| v2 無單筆 GET（僅列表）。| **v4 有 v2 無**（單筆 template GET）。 |
| `PATCH /wi-templates/{id}`（`:640`）| `PATCH /api/v2/motion-templates/{id}`（`motion_template.py:105`）| 相同。| 對齊。 |
| `PUT /wi-templates/{id}/items/{item_id}`（`:667`）；`POST /wi-templates/{id}/items/reorder`（`:740`）| **v2 無**（v2 motion-template 無 item 級操作）| v4 template 有 items 結構。| **v4 有 v2 無**（template 內含 items 是 v4 特有）。 |
| `DELETE /wi-templates/{id}`（`:760`）| `DELETE /api/v2/motion-templates/{id}`（204, `motion_template.py:130`）| 相同。| 對齊。 |
| `POST /wi-templates/{id}/clone`（201, `:776`）| **v2 無 clone**（v2 有 `promote`，`motion_template.py:83`；`match`，`:141`）| v4 clone；v2 有 promote（草稿→標準治理）與 keyword match。| 各有特色：v4 clone、v2 promote/match（`motion_template.py:83/:141`）。 |

### 4d. Process Routes（v4 特有）

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `POST /api/most/process-routes`（201, `most_workbench_v3.py:838`）；`GET /process-routes`（`:917`）；`GET/PATCH/DELETE /process-routes/{id}`（`:928/:940/:987`）；`POST /process-routes/{id}/items/reorder`（`:967`）；`POST /process-routes/{id}/clone`（201, `:1003`）；`POST /process-routes/{id}/items/{item_id}/apply-to-template`（`:1054`）| **v2 全無** | v4 有完整「Process Route（工序路線）」CRUD + item reorder + clone + apply-to-template。| **v4 有 v2 無（整個功能域）**。v2 無「process route」概念。整合須評估是否引入此實體，或對映到 worksheet/wi-set。 |

---

## 5. Line Balance / Line Layout（v4 特有的持久化功能域）

v4：`line_balance.py`（prefix `/api/most/line-balance`）、`line_layout.py`（prefix `/api/most/line-layout`）。
v2：**無等價功能域**；v2 只有「匯出給 LB」的 CSV/API 合約（`export.py`）+ level→LB 輸出（`calculate.py:140`）。

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `POST /api/most/line-balance/simulate`（`line_balance.py:114`）；`simulate-multi`（`:127`）| **v2 無**（v2 不做 LB 演算，只輸出資料給外部 LB）| v4 內建 LB 模擬（單/多情境）。| **v4 有 v2 無（核心新功能）**。v2 定位是「產 LB 輸入」；v4 把 LB 演算收進系統。整合須決策：v2 是否要納入 LB 引擎。 |
| `GET/POST /line-balance/scenarios`（`:155/:169`）；`GET/PUT/DELETE /scenarios/{id}`（`:207/:220/:276`）；`POST /scenarios/{id}/duplicate`（`:242`）| **v2 無** | v4 LB scenario 持久化 CRUD。| **v4 有 v2 無**。 |
| `GET /api/most/line-layout/scenarios`（`line_layout.py:245`）；`GET/PUT/DELETE /scenarios/{id}`（`:301/:311/:391`）；`POST /scenarios/{id}/duplicate`（`:354`）| **v2 無**（無 Line Layout 概念）| v4 產線佈局 scenario CRUD。| **v4 有 v2 無（整個功能域）**。 |
| `POST /line-layout/scenarios/from-line-balance/{scenario_id}`（`line_layout.py:259`）| **v2 無** | v4 由 LB scenario 派生 Layout scenario（資料流：LB → Layout）。| **v4 有 v2 無**（關鍵串接）。 |
| — | `GET /api/v2/worksheets/{id}/export/lb-csv`（`export.py:56`）；`POST /export/lb-api`（`export.py:69`）| **v2 有 v4 無**：v2 把 LB 當外部系統，提供 CSV / API 匯出合約。| 整合須釐清：v4 內建 LB vs v2 對外 LB 匯出，是兩種產品定位。 |

---

## 6. E-SOP（v4 特有功能域）

v4：`esop.py`（prefix `/api/esop`）。v2：**完全無 E-SOP 功能域**。

| v4 endpoint | v2 對應 | 差異 | 整合備註 |
|---|---|---|---|
| `GET /api/esop/documents`（`esop.py:356`）；`POST /documents/from-line-balance`（`:376`）；`POST /documents/from-layout`（`:400`）| **v2 無** | 由 LB / Layout 生成 E-SOP 文件。| **v4 有 v2 無（整個功能域）**。依賴 §5 的 LB/Layout。 |
| `GET/PATCH/DELETE /documents/{id}`（`:428/:438/:610`）；`POST /documents/{id}/duplicate`（`:467`）；`release`（`:561`）；`archive`（`:578`）；`unarchive`（`:593`）| **v2 無** | E-SOP 文件生命週期（draft/release/archive）。| **v4 有 v2 無**。生命週期語彙可與 v2 worksheet publish/retire 對齊。 |
| `PATCH /station-pages/{id}`（`:641`）；`PATCH /steps/{id}`（`:665`）；`POST /steps/{id}/regenerate-instruction`（`:691`）；`POST /documents/{id}/reset-instructions`（`:711`）| **v2 無** | E-SOP 站別頁 / 步驟 / 指令自動生成。| **v4 有 v2 無**。 |
| `POST /steps/{id}/assets`（`:747`）；`PATCH /assets/{id}/reorder`（`:782`）；`DELETE /assets/{id}`（`:810`）；`GET/PUT /assets/{id}/annotations`（`:836/:853`）| **v2 無** | 圖片素材上傳 + 標註（v4 有 static 檔案掛載，`main.py:52-57`）。| **v4 有 v2 無**。需檔案儲存/上傳基礎設施，v2 目前無對應（v2 export 是唯讀產出）。 |
| `GET /documents/{id}/preview-data`（`:890`）；`GET /documents/{id}/print`（HTML, `:900`）；`POST /documents/{id}/export-pdf`（`:915`）| 近似 v2 `GET /api/v2/worksheets/{id}/export/wi-preview`（`export.py:33`）僅在「預覽」語義上部分重疊 | v4 產 E-SOP 的 preview/print/PDF；v2 只有 worksheet 匯出（Excel/CSV/report.xlsx）。| **v4 有 v2 無（PDF/HTML 列印）**。v2 匯出以 Excel 為主（`export.py:42/:78`）。 |

---

## 7. Analysis / Cases（審查流程）

v4：`analysis.py`（prefix `/api/analysis`）+ `reports.py`（prefix `/api/reports`）。
v2：`cases.py`（prefix `/api/v2`，僅列表）+ `audit_log.py`。

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `GET /api/analysis/cases`（`analysis.py:97`）| `GET /api/v2/cases`（`cases.py:20`）| 皆列案件。v2 僅列表（唯讀清單）。| 對齊列表；其餘 v4 有 v2 無（見下）。 |
| `POST /cases`（201, `:110`）；`GET/PATCH/DELETE /cases/{id}`（`:147/:155/:177`）| **v2 無**（v2 案件不從此 API 建立/編輯）| v4 案件 CRUD。| **v4 有 v2 無**。v2 的「案件」概念邊界不同（v2 以 worksheet/wi-set 為主體）。 |
| `POST /cases/{id}/steps`（201, `:196`）；`PATCH/DELETE /cases/{id}/steps/{step_id}`（`:257/:306`）；`POST /steps/preview`（`:331`）| **v2 無**（步驟預覽近似 `calculate-row`，但 v2 無「case step」實體）| v4 案件內步驟 CRUD + preview。| **v4 有 v2 無**。 |
| `POST /cases/{id}/submit`（`:353`）；`review`（`:363`）；`request-changes`（`:373`）；`approve`（`:383`）；`archive`（`:393`）| **v2 無工作流端點**（v2 審查回饋在 `ai_review.py`，語義不同）| v4 有完整案件審核 workflow（submit→review→approve/request-changes→archive）。| **v4 有 v2 無（審核工作流）**。v2 目前無等價 case 狀態機。 |
| `GET /cases/{id}/audit-log`（`:403`）| `GET /api/v2/audit-log`（`audit_log.py:33`）| v4 per-case audit；v2 全域 audit-log（可篩）。| v2 audit 是跨資源；v4 綁 case。整合可用 v2 audit-log + 篩選對映。 |
| `GET /api/reports/cases/{id}/excel`（`reports.py:15`）| `GET /api/v2/worksheets/{id}/export/excel`（`export.py:42`）；`report.xlsx`（`export.py:78`）| 皆 Excel 匯出；主體不同（v4 case vs v2 worksheet）。| 語義近；主體對映需釐清。 |

---

## 8. Auth / Users

v4：`auth.py`（prefix `/api/auth`）+ `users.py`（prefix `/api/users`）— **本地 JWT 認證**。
v2：`calculate.py` 的 `/me`（prefix `/api/v2`）+ `admin_users.py`（prefix `/api/v2/admin`）— **聯邦 ForwardAuth**。

| v4 endpoint | v2 對應 endpoint | 差異 | 整合備註 |
|---|---|---|---|
| `POST /api/auth/login`（`auth.py:58`，回 bearer token）| **v2 無**（v2 無本地登入；認證由 Traefik ForwardAuth 前置）| **根本架構差異**：v4 自己驗密碼、發 JWT（`create_access_token`, `auth.py:69`）；v2 不持有密碼、由聯邦閘道注入身分（已確認 v2 全庫無 `login`/`create_access_token` 路由，僅 `settings.py` 有 token 過期設定常數）。| **不可搬入 v2**。v4 的本地登入與 v2 的聯邦模型互斥；整合時 v4 使用者須改走 ForwardAuth。這是整合的重大前提。 |
| `GET /api/auth/me`（`auth.py:73`）| `GET /api/v2/me`（`calculate.py:45`）| 皆回目前使用者。v4 回 email/name/roles/JWT-based；v2 回 employee_no/roles/plant_code/level/locale（ForwardAuth-based）。| 語義對應，欄位模型不同。 |
| `POST /api/auth/change-password`（`auth.py:78`）| **v2 無**（密碼不在 v2 管） | v4 本地改密碼。| **不可搬入 v2**（密碼由聯邦身分源管理）。 |
| `GET /api/users`（`users.py:34`）；`POST /users`（201, `:50`）；`PATCH /users/{id}`（`:81`）；`PATCH /users/{id}/roles`（`:101`）；`PATCH /users/{id}/disable`（`:118`）| `GET /api/v2/admin/users`（`admin_users.py:38`）；`POST /admin/users`（`:44`）；`PATCH /admin/users/{employee_no}`（`:59`）| 皆使用者管理。v4 用 user id + email；v2 用 employee_no（聯邦鍵），且 v2 無獨立 disable/roles 專用端點（合併在 PATCH）。| 對映需以 employee_no 為鍵；v4 的 roles/disable 專用端點在 v2 併入單一 PATCH。 |
| — | `PATCH /api/v2/me/locale`（`calculate.py:51`）| **v2 有 v4 無**：本人自助改語言偏好（i18n）。| v2 i18n 較完整（另見 §9）。 |

---

## 9. v2 有、v4 無的功能域（反向盤點，供整合時保留）

以下 v2 端點在 v4 無對應，整合 v4 功能時**不得回退掉這些能力**：

| v2 功能域 | 代表端點 | 證據 |
|---|---|---|
| Catalog（site/product/sku/worksheet 樹）| `GET /api/v2/sites`、`/products`、`/skus`、`POST /skus/{id}/worksheets` | `catalog.py:32/:37/:55/:80` |
| Worksheet（工時表版本/發布/clone/retire）| `PUT/GET /api/v2/worksheets/{id}`、`/versions`、`/publish`、`/clone`、`/retire` | `worksheet.py:21/:61/:73/:102/:116/:126` |
| Excel 匯入（含 profile + 分段 parse job）| `POST /api/v2/imports/upload`、`/{id}/map`、`/{id}/submit`、`/profiles`、`/parse-jobs*` | `import_excel.py:50/:97/:186/:140`；`parse_jobs.py:42/:94/:110/:147` |
| i18n 審查回路 | `GET /api/v2/i18n/review/summary`、`/pending`、`POST /mark-reviewed`、`/assign` | `i18n.py:74/:84/:95/:126` |
| Vocab（詞彙庫 + 中英）| `GET/POST/PATCH/DELETE /api/v2/vocab` | `vocab.py:36/:60/:69/:88` |
| 全文搜尋 | `GET /api/v2/search` | `search.py:16` |
| WI Row Context | `GET/PUT/DELETE /api/v2/wi-rows/{id}/context` | `wi_context.py:20/:29/:48` |
| DSX 整合（A3 距離）| `GET /api/v2/dsx/ui-url`、`POST /a3-distance` | `dsx.py:27/:32` |
| Rule-set synonyms / bands / diff | `synonyms.py:35/:51/:112`；`rule_set.py:500/:129` | 見 §2 |
| AI 草稿人審回饋 | `POST/GET /api/v2/nl-drafts/{run_id}/reviews` | `ai_review.py:42/:71` |

---

## 10. 結論（整合優先序與紅線）

**整合紅線（不可污染 v2 計算正確性）**
- v4 `POST /calculate-row` 的 slot TMU 計算路徑（`most.py:293`, `calculate_slot_tmu`）**不得**取代或旁路 v2 `compute_cycle`（`calculate.py:96`，engine 單一權威、GM=28/CM=29 黃金值鎖定）。若需 v4 的「單列 + frequency + is_simo + 自動組句」UX，TMU 一律轉呼叫 v2 engine。
- v4 本地 JWT 登入（`auth.py:58/:78`）**不可搬入** v2；v2 是聯邦 ForwardAuth，兩者互斥。v4 使用者須改走 ForwardAuth。

**v4 有 v2 無的整個功能域（最大整合工作量）**
1. **Line Balance + Line Layout**（§5）：內建 LB 模擬 / 佈局 scenario 持久化。v2 目前只對外匯出。
2. **E-SOP**（§6）：文件生成 / 站別頁 / 步驟指令 / 圖片標註 / PDF-HTML 列印 + 檔案上傳基礎設施。
3. **Level System Plan 實體**（§3）：把 level 從無狀態驗證升格為有生命週期的持久化 Plan（from-wi-set 快照、release/archive、number-rules）。
4. **Process Routes**（§4d）：工序路線 CRUD。
5. **Case 審核工作流**（§7）：submit→review→approve/request-changes→archive 狀態機。

**可直接對齊（低風險，多為路徑改寫 `/api/most*` → `/api/v2`）**
- Dictionary↔Rule-set 生命週期（clone/publish/activate/export，§2）。
- WI-set projects CRUD（§4a）。
- Action/Motion modules 與 templates 基本 CRUD（§4b/4c）。
- `/me`、users 管理（以 employee_no 為鍵，§8）。

**每一節的差異與證據均已標注 `檔案:行號`；v4 全部 12 支 router、約 143 條端點與 v2 全部 21 支 router、約 111 條端點已逐一盤點。**
