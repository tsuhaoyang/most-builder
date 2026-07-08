# 萃取證據：字典管理／分析工作流／Auth／報表 API 完整合約（自 v3 程式碼直接萃取）

> 產出方式：2026-07-05 由查證 agent 直讀 `ddm-v3/apps/api/app/api/routes/{dictionaries,analysis,auth,users,reports}.py`、`services/{dictionary_import,report_export,default_dictionary_seed}.py`、`models/`、`core/`、`db/init_db.py` 萃取；**未參考 v3 markdown 文件**。此為 analysis/features 各規格的證據底稿（唯讀）。

## DICTIONARIES ROUTES（/api/dictionaries）

### GET /dictionaries/versions
- 權限：get_current_user ｜ 目的：列出全部字典版本（created_at DESC）
- Response[]：id, version_name(unique), source_filename?, is_active, created_at?, notes?

### POST /dictionaries/{version_id}/suggest-code
- 權限：user ｜ 目的：由 slot code＋中文顯示字產生唯一 option code
- Request：slot_code(A|B|G|P|M|X|I, 必填)、display_text_zh(必填)
- Response：suggested_code、base_code、alternatives[]（≤3，數字後綴）、is_unique
- 錯誤：400 slot_code 非法

### POST /dictionaries/seed-default
- 權限：admin ｜ 目的：從內建 JSON seed 初始化預設字典
- 行為：已有 active 版本→直接回傳既有；否則**刪除全部字典資料**後重建 seed（is_active=True）
- 錯誤：500 seed JSON 檔缺失

### POST /dictionaries/import（multipart）與 POST /dictionaries/import-base64
- 權限：admin ｜ 目的：Excel 匯入建立新版本（is_active=False）
- 驗證：副檔名 .xlsx/.xls、非空、≤10MB；base64 版另驗 base64 合法
- Response：version_id、version_name、counts{sequence_models, parameter_slots, parameter_options, lexical_options}、warnings[]
- 副作用：建 DictionaryVersion＋四類子表；import_warnings_json 落檔

### POST /dictionaries/{version_id}/activate
- 權限：admin ｜ 行為：全部版本 is_active=False → 目標=True ｜ 錯誤：404

### POST /dictionaries/{version_id}/publish
- 權限：admin ｜ 前置：目標 is_active=False；**每個核心參數（A~I）至少 1 個 active 選項**
- 行為：同 activate ＋ 呼叫 `invalidate_synonym_cache()`
- 錯誤：404；400（已 active／核心參數缺選項）

### POST /dictionaries/{version_id}/archive
- 權限：admin ｜ 前置：is_active=False ｜ 行為：**placeholder（無實際 soft-delete 欄位）**

### GET /dictionaries/{version_id} ／ /sequence-models ／ /slots ／ /options-by-param/{code} ／ /options?slot_id&category ／ /export
- 權限：user（export=admin）｜ 唯讀查詢；options-by-param 以 option_code 去重；export 回 JSON 全量

### PUT /dictionaries/options/{option_id}
- 權限：admin ｜ 目的：更新單一選項（全部欄位選填）：display_text_zh、sentence_text_zh、helper_text_zh、tmu_value、fixed_seconds、seconds_source、is_active、sort_order、display_rule、metadata_json、option_code、control_key、synonyms_json
- 行為：option_code 改名時檢查同版本+slot 唯一（409）；normalized_text_zh=display_text_zh（**直接 copy，未 normalize**）
- ⚠️ **無 active 版本唯讀防護**（active 版 TMU 可直接改）；⚠️ synonyms 更新**不**失效快取（僅 publish 會）

### POST /dictionaries/{version_id}/options
- 權限：admin ｜ option_code 必須以 `A_|B_|G_|P_|M_|X_|I_` 開頭（首字母決定參數）；同版本+slot 唯一（409）；掛到該參數的代表 slot

### POST /dictionaries/{version_id}/options/{option_id}/duplicate ／ DELETE .../options/{option_id}
- duplicate：copy 全欄位、code 加 `_COPY`/遞增後綴
- delete：**active 版本→軟刪（is_active=False）；非 active→硬刪**

### POST /dictionaries/{version_id}/clone
- 權限：admin ｜ 行為：整版深拷貝為新 draft（is_active=False，版名加 `_draft_YYYYMMDDHHMM`），models/slots/options/lexical 全 remap

## ANALYSIS ROUTES（/api/analysis）

### 案件 CRUD
- GET /cases?status= ：user；updated_at DESC；回 summary（id, case_no, product, station, operation, status, allowance_percent, timestamps）
- POST /cases（201）：analyst|admin；**case_no = `CASE-{count+1:05d}`（以現有筆數產號）**；需有 active 字典（400）；status=draft
- GET /cases/{id}：user；全細節含 steps[]（每步 slot_values[]：slot_key, parameter_code, selected_option_id, selected_text_zh, index_value, tmu_value, slot_order）
- PATCH /cases/{id}：analyst|admin；限 status ∈ {draft, changes_requested}（400）
- DELETE /cases/{id}：analyst|admin；限 draft；cascade 刪 steps/slots/audit

### 步驟 CRUD 與計算（inline 手算）
- POST /cases/{id}/steps（201）／PATCH steps/{id}／DELETE steps/{id}（刪後 step_no 重排）；限 editable status
- **TMU 公式（inline）**：`base_tmu=Σ slot.index_value`；`step_tmu=base×frequency`；`normal_sec=step_tmu×0.036`；`standard_sec=normal×(1+case.allowance_percent/100)`
- ⚠️ **slot_values 的 index_value/tmu_value 由前端傳入，後端不對照字典驗證**（tmu_value 預設=index_value）
- POST /steps/preview：user；同公式試算不落檔

### 工作流遷移（VALID_TRANSITIONS）
```python
{"draft": {"submitted"}, "submitted": {"reviewed", "changes_requested"},
 "reviewed": {"approved"}, "changes_requested": {"draft"}, "approved": {"archived"}}
```
| Endpoint | from→to | 角色 |
|---|---|---|
| POST /cases/{id}/submit | draft→submitted | analyst\|admin |
| POST /cases/{id}/review | submitted→reviewed | reviewer\|admin |
| POST /cases/{id}/request-changes | submitted→changes_requested | reviewer\|admin |
| POST /cases/{id}/approve | reviewed→approved | approver\|admin |
| POST /cases/{id}/archive | approved→archived | admin |

- 每次遷移：更新 status＋對應時間戳（submitted_at/reviewed_at/approved_at）＋寫 WorkflowAuditLog{case_id, actor_user_id, from_status, to_status, comment, created_at}；非法遷移 400
- GET /cases/{id}/audit-log：user；時間序稽核清單（含 actor_name）

## AUTH／USERS

- POST /auth/login：email+password → bcrypt 驗證＋is_active → JWT（HS256, sub=user_id, exp=480min）＋更新 last_login_at；401/403
- GET /auth/me：token→User；401
- POST /auth/change-password：驗舊密→bcrypt 新雜湊→must_change_password=False；400
- GET /users（admin）；POST /users（admin，email 唯一、預設密碼 changeme123、must_change_password=True、預設角色 analyst）；PATCH /users/{id}（name/is_active）；PATCH /users/{id}/roles（整組替換）；PATCH /users/{id}/disable
- 角色 seed（init_db.seed_defaults）：admin/analyst/reviewer/approver/viewer 五角色＋初始 admin（INITIAL_ADMIN_EMAIL/PASSWORD 環境變數）
- guard 機制：`require_roles(*names)` Depends 工廠 → require_admin / require_analyst_or_admin / require_reviewer_or_admin / require_approver_or_admin；User.role_names 為 property

## REPORTS

### GET /reports/cases/{case_id}/excel
- 權限：user ｜ StreamingResponse（openpyxl xlsx，三 sheet）
- Sheet1「案件資訊」：case_no/product/model_name/station/operation/site/line/字典版本/寬放率/狀態(STATUS_LABELS)/建立/更新＋步驟總數/總TMU(round2)/總正常秒(round3)/總標準秒(round3)
- Sheet2「動作明細」：步驟/說明/序列模型(name_zh)/頻率/插槽明細（`A1(A)=2 | B1(B)=1 | …` 由 slot_values 組字）/步驟TMU(2)/正常秒(4)/標準秒(4)
- Sheet3「簽核歷程」：時間/動作(from→to)/從狀態/至狀態/執行者/備註
- STATUS_LABELS：draft=草稿, submitted=已送審, reviewed=已審核, changes_requested=退回修改, approved=已核准, archived=已封存

## dictionary_import.py 完整流程（Excel 格式）

- 單一 active sheet（data_only=True）；區域：GM 參數卡 rows4-18 cols D-47、CM 參數卡 rows50-66、GM 詞庫 rows21-47 cols B-49（hand/object/from/to 四類）、CM 詞庫 rows67-94（＋tool 五類）
- 步驟：建 version（inactive）→ 建兩個 sequence models＋固定 7 slots（GM: A1,B1,G,A2,B2,P,A3；CM: A1,B1,G,M,X,I,A3）→ 逐 cell：`normalize_text()`（NFKC/繁簡；ambiguous 產 warning 含 cell 位置）→ **index 以 regex `\(\d+\)` 或全數字 fallback 抽取** → 依相對欄位分配 slot/類別
- warnings 來源：正規化 ambiguous 詞（手度/眼步動作等）、cell 解析失敗

## 模型欄位全表（節錄關鍵）

- **DictionaryVersion**：id(String36 PK), version_name(unique), source_filename?, is_active(def False), created_by_user_id FK?, created_at, notes?, import_warnings_json?
- **SequenceModel**：id, dictionary_version_id FK(cascade), code, name_zh, sequence_pattern, description?
- **ParameterSlot**：id, dictionary_version_id FK, sequence_model_id FK, slot_key, slot_order, parameter_code, display_name_zh?, is_required(def False)
- **ParameterOption**：id, dictionary_version_id FK, slot_id FK, option_code, control_key(reach_distance|hand_degree|foot_step|verb|base_action|modifier|option|x_option), display_text_zh, sentence_text_zh, helper_text_zh, normalized_text_zh, index_value?, tmu_value(Float)?, fixed_seconds?, seconds_source(fixed_seconds|user_input_seconds)?, display_rule(prefix_visible_term|show_self|hidden)?, rule_type?(保留), rule_effect?(保留), metadata_json?, synonyms_json?, is_active(def True), sort_order(def 0)
- **LexicalOption**：id, dictionary_version_id FK, category(hand|object|from_location|to_location|tool|process_term), display_text_zh, normalized_text_zh, metadata_json?, is_active, sort_order
- **AnalysisCase**：id, case_no(unique), product, model_name?, station, operation, site?, line?, dictionary_version_id FK, status, allowance_percent(Float def 0), created_by_user_id FK, created/updated/submitted/reviewed/approved_at, notes?
- **AnalysisStep**：id, case_id FK(cascade), step_no, description?, sequence_model_id FK, frequency(Int def 1), step_tmu(Float), normal_time_seconds, standard_time_seconds, sentence_preview_zh?, video_timestamp_start/end?(HH:MM:SS 字串)
- **AnalysisStepSlot**：id, step_id FK(cascade), slot_key, parameter_code, selected_option_id FK?, selected_text_zh?, index_value(Int def 0), tmu_value(Float def 0), rule_applied_json?, slot_order
- **User**：id, email(unique), name, password_hash(bcrypt), is_active, must_change_password, created/updated/last_login_at；roles M2M
- **Role**：id, name(unique：admin|analyst|reviewer|approver|viewer), description?
- **WorkflowAuditLog**：id, case_id FK(cascade), actor_user_id FK, from_status, to_status, comment?, created_at

## 常數

- TMU_TO_SECOND=0.036；SECOND_TO_TMU=27.7777777778
- JWT：HS256、480 分鐘、sub=user_id；bcrypt 自動 salt
