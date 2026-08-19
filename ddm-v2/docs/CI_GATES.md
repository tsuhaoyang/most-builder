# CI 門檻：重大驗證測試點

**這些過了，CI 才綠**（`.github/workflows/ci.yml`）。每個功能都有對應的 testing script；新增/改功能時，先在這裡補上驗證點與測試，再寫實作。

## 規則（硬性）

1. **凡 `src/` import 的第三方套件，必在 `pyproject.toml` `dependencies`**（不是只 dev）。CI 用宣告的依賴跑 → 漏宣告會紅。
2. **每個 feature（每組端點）至少一個整合測試**涵蓋：正常路徑 + 一個邊界/RBAC。
3. 改核心邏輯（引擎/rule-set/level）→ 必過 `core_logic/run_all.py` 黃金值。
3b. **測試資料零殘留（P0-0.2）**：整合測試一律走 conftest 的 transaction-rollback 隔離（`db_ctx`/`client`/`db_session` fixtures）；**測試內禁止自建 engine 打 `DATABASE_URL`**（會繞過隔離、汙染真實 DB）。驗收：跑兩遍 `pytest tests/integration` 前後，下列測試簽名計數皆不得增加——`motion_modules` 的 `UT-%`、`sites`/`products` 的 `AGGTEST\_%`／`GUARDTEST\_%`、`skus` 的 `UTSKU-%`／`AGGTEST\_%`／`GUARDTEST\_%`、`process_versions` 總數。歷史殘留用 `scripts/cleanup_test_data.py`（預設 dry-run）清理，新增簽名必須同步進該腳本的 pattern。**自動保險絲**：`tests/integration/test_isolation_guard.py` 以獨立唯讀連線比對真實 DB，覆蓋兩條寫入路徑（clone 端點 ×N、fixture 直接 commit ×N）＋殘留掃描；資料全由測試自建（`GUARDTEST_%`），**不依賴 dev_seed，乾淨 CI DB 上照樣生效**（保險絲不得有靜默 skip 的「沒接上」狀態）。該檔是「測試內禁止自建 engine」的唯一例外，且只讀不寫。
4. **值權威（ADR-014）**：黃金錨＝`MINIMOST_FACTORY_V2`（v3 IE 認證字典）；`rule_set_seed_v2.py` 為 converter 產物**禁手改**（改值＝改字典 JSON 後重跑 `scripts/import_v3_dictionary.py`）；V1 回放測試必須維持綠（快照隔離）。
4b. **字典治理不變式（ADR-023）**——動 `rule_sets`／`rule_*` 子表／`rule_set_service` 必驗：
   - **恰好一個 active**：`SELECT count(*) FROM rule_sets WHERE is_active` 恆為 1。由 partial unique index `uq_rule_sets_single_active` 保證，`activate` 走「先全部 deactivate→flush→設目標」原子路徑。
   - **回放鐵則**：`load_rule_set_from_db` **不得**出現 `status` 或 `is_active` 過濾。治理狀態只在*選版*生效、不在*載入*生效；否則歷史 cycle 會在舊版本被封存後算不出原值或靜默改值。守護＝`test_rule_set_replay_isolation.py`（V1 被 retire＋deactivate 後仍載得到並得 GM=28/CM=29）。**這條是負向規則，CI 另以 grep 守：該函式所在查詢不得含治理欄位。**
   - **認證血緣不可寫**：`provenance='certified_import'` 的版本，任何寫入端點（選項 CRUD／`PUT /full`／publish 前編輯）必須擋下；線上調值一律走 clone-on-write。UI 或 `POST /rule-sets/import` 產生的版本恆為 `status='draft'`＋`provenance='manual'`，**不得由 payload 指定**。
   - **帶型整組驗證**：A（reach/twist/foot）與 M（ladder/foot/rotation/hand）是「帶」不是「選項」——上界遞增不重疊、末帶開放，且**每條寫入帶表的路徑**（`replace_bands`／`PUT /full`／`import`）都要過 `validate_full_bands`。漏一條就會出現「靜默夾取到末帶、不報錯但算錯值」。
   - **子表數＝12**（含 `m_foot`）。新增子表時 `load_full`／`_insert_children`／export／import 四處必須同步；守護＝以 `inspect(model).mapper.column_attrs` 反射逐欄比對的 round-trip 測試（漏欄會紅）。
5. 前端改動 → typecheck + build + Playwright smoke 綠。
6. **依賴一律從鎖檔安裝**（`requirements.lock` / `requirements-dev.lock` / `requirements-build.lock`）。
   改了 `pyproject.toml` 的依賴宣告（含 `[build-system].requires`）就**必須**重跑
   `./scripts/lock_deps.sh` 並把三個 `.lock` 與 `requirements-build.in` 一起 commit，否則 `deps` job 紅。
   安裝時**一律** `--require-hashes`，且**不得** `pip install --upgrade pip`（那是唯一不受
   hash 保護的抓取）、`-e .` **必須**帶 `--no-build-isolation`（否則 build backend 走隔離環境
   無 hash 下載並執行）。
   **`Dockerfile` 兩個 `FROM` 一律帶 `@sha256:`（manifest list digest），不得只留 tag**——
   那是跑上述所有 hash 驗證的信任根。**重跑 `lock_deps.sh` 前 uv 版本必須等於
   `EXPECTED_UV_VERSION`**，否則腳本拒絕執行（不同 resolver 產出不同鎖檔＝同步關卡假紅）。
   詳見下方「依賴鎖版與安全稽核」。
7. **測試必須自足，且反向斷言必須附 mutation 證據。** 兩條都是 2026-08-12 這一輪
   各抓到實例後成文的（一輪內共三條假測試），不是預防性條文：
   - **不得依賴環境既存資料。** 不要撈「第一列」「任一筆」——自己建。CI 後端 job 的 seed
     只有 `dev_seed_v2` + `dev_seed_templates` + `dev_seed_synonyms` + `dev_seed_i18n_labels`
     （**不含** `dev_seed_30rows`），e2e job 的 DB 也**沒有**跑過 `migrate_v3_user_data.py`，
     所以 `most_cycles`、`wi_rows`、`wi_set_projects`、`category='wi-template'` 的 motion
     modules 在 CI 上**都是 0 列**；`work_vocab_items` 在 CI 後端 job 上也只有
     `dev_seed_v2.py` 建的 3 筆（完整 59 筆需要 `dev_seed_30rows.py`，backend job 不跑），
     依賴 `work_vocab_items` 精確列數的斷言必須動態查 DB 現況，不得硬編 59
     （ADR-032 Phase B 灌值/待審清單測試已踩過這個坑並改成動態查詢）。
     實例：`test_delete_referenced_draft_returns_409_*`（撈 `most_cycles` → CI `NoResultFound`）、
     `wi-add-live.spec.ts`（需 v3 遷移資料 → CI 永遠 0）。
     本機綠不代表通過——複現 CI 請建乾淨 DB 只跑 CI 那幾支 seed（指令見文末）。
   - **反過來的那一面（D3-030 B1，2026-08-17 抓到）：判定對象本來就是「環境資料」的守門，
     那份資料必須有版控 seed。** 同義詞守門（`test_synonym_registration_governance`）判的是
     DB 現存的 `rule_option_synonyms`，而當時 seed 鏈一步都不寫它——22 條詞典只活在開發機的
     執行期資料裡，於是**本機 8 綠、乾淨 DB 3 紅**（拋棄式庫實測），守門在 CI 上從未真的守過。
     修法不是把測試改成自建資料（那會讓守門對象變成測試自己造的東西、失去「守 DB 現況」的
     語意），是把該批資料本身納入版控 seed（`scripts/dev_seed_synonyms.py`，逐條標 IE 裁決
     出處、冪等）並在 CI seed 鏈補一步。判準：**這份資料是不是「規格的一部分」**——是就進
     seed，不是就由測試自建。
   - **反向斷言（`toHaveCount(0)`／`not.toBeVisible`／`assert not …`）必須證明它會紅。**
     正向斷言用壞掉的定位器會**大聲失敗**；反向斷言用壞掉的定位器會**安靜變成恆真**。
     實例：`ux-compliance.spec.ts` 的 E-04-4 用 `getByText('B2', {exact:true})` 斷言
     `toHaveCount(0)`，而色塊抬頭早已改成 `A · A1` 形式使該定位器永遠 0 命中——
     把 `B2`/`P` 塞回 `CM_ITEMS`（直接違反 GM→CM 清空規則）該測試**依然全綠**。
     （後記 2026-08-15：`A · A1` 本身是 b66829d 偏離規格的發明，已依 accepted
     ADR-021:53 收編回單一格位鍵標籤「A1」，B-01-2 的抬頭斷言同步收緊為精確比對；
     E-04-4 維持 data-testid 序列比對——文字錨點是當初假綠的根因，不因收編而回頭。）
     ⚠️ Playwright 的 `getByText(exact:true)` 比對的是元素內**連續 immediate 文字節點的
     合併值**，任何在同一個節點加前綴／分隔符的 UI 改動都會讓它靜默失準。
     定位錨點請用 `data-testid`／`aria-label` 這類**不隨版面文案漂移**的語意錨點。
   - 對應的正向要求：**新增或修改測試時附 mutation 證據**（改壞 → 紅，改回 → 綠）。
     「沒看過它紅過的守門不算守門」——參見 `architecture/v2-authoritative-model-guide.md` §6。
8. **動到 linker 掛值（`nlp/linking.py` 的 chosen／掛格語意）的改動，驗證必須含
   「核心格可填＋新格面命中」的合成句跑完整 engine_gate**（linker→compile→engine→
   routing，斷言 routing 不得 invalid、該掛值的旗標在）。理由：語料對「complete=True
   才觸發」的失效**結構性失明**——D3-024 複審 H1 實證：語料 X/I 句全卡
   `missing_core_m`（incomplete 根本不進 engine gate），於是「seconds 模式 X 掛進
   chosen → 引擎 `X_SECONDS_REQUIRED` 硬拒 → 合法草稿整筆 invalid」這條路徑在
   56 筆草稿＋38 筆 gold 上**零覆蓋**，unit／golden／eval 全綠照樣翻車
   （「按壓把手並清潔卡槽」實測 invalid）。現行合成句閘門＝
   `tests/unit/test_linking.py` 的 `test_engine_gate_*` 四條（fixed X 真 TMU／
   seconds X 不 invalid＋X0＋旗標／I 掛值旗標擋 auto／D3-026 E 型純 I 句
   「核心格空＋I 面命中」豁免帶真 TMU＋G 面反例不豁免）。同規則適用完整性
   判定的豁免改動（`most_compiler/compile.py` face_hit_params 分支）。

## Feature → 驗證測試點 → script

| Feature | 重大驗證測試點 | Script |
|---|---|---|
| MOST 引擎 | GM=28 / CM=29 黃金；TMU=Σindex×1；邊界 | `tests/unit/test_most_engine.py`、`scripts/core_logic/run_all.py` |
| Level System | R1–R9 填表規則；巢狀；變動度 | `tests/unit/test_level_engine.py` |
| 身分/RBAC | `/me` 身分；viewer 打 IE 端點→403 | `tests/integration/test_v2_api.py` |
| 計算 | `POST /minimost/calculate` GM 黃金 | `tests/integration/test_v2_api.py` |
| 範本庫 | CRUD + 治理(promote) + `/match`；RBAC | `tests/integration/test_v2_api.py` |
| **Rule-set** | list / options / full（**12 區塊**有資料，含 `m_foot`）；**publish analyst→403（approver gate）** | `tests/integration/test_rule_set.py` |
| **字典治理：生命週期（ADR-023 D1）** | clone-draft→編輯→publish（發布前完整性驗證：每參數至少一啟用選項）→原子 activate；**恰好一個 active** 不變式；retire；`certified_import` 寫入被擋；`catalog_service`/`worksheet_service` 改讀 active（V1/V2 分裂已解） | `tests/integration/test_rule_set_lifecycle.py` |
| **字典治理：回放鐵則（ADR-023 §3.4）** | V1 **retire＋deactivate 後**仍載得到並得 GM=28/CM=29；引用已封存版本的 cycle 重算＝原值；`load_rule_set_from_db` 查詢不含 `status`/`is_active` | `tests/integration/test_rule_set_replay_isolation.py` |
| **字典治理：選項級 CRUD＋帶界（ADR-023 D2）** | 七參數選項 CRUD；**帶型整組替換**（上界遞增不重疊、末帶開放，違反→400）；clone 逐欄保真（反射比對 400+ 格，含 `m_foot`／`sentence_text_zh`／`display_rule`／`max_select`／`vision_scope`） | `tests/integration/test_rule_set_options.py` |
| **字典治理：匯出/匯入 draft（ADR-023 D3）** | export＝`load_full` 形狀＋metadata（**雙向**釘死 `set(export)-set(full)==META`）；round-trip 逐欄保真；匯入產物恆 `draft`＋`manual`＋`is_active=False`（payload 內治理欄位一律忽略）；缺區塊／畸形列／非法帶界 → **400 且零寫入** | `tests/integration/test_rule_set_export_import.py` |
| **主數據詞彙** | create→list→delete；viewer 403 | `tests/integration/test_vocab.py` |
| **Worksheet 存讀** | PUT→GET roundtrip，TMU 引擎算=28 | `tests/integration/test_worksheet.py` |
| **SOP 版本** | versions / clone / publish / 再發布 409 / RBAC；**publish analyst→403（approver gate）**；**audit log 建立（action=approve）** | `tests/integration/test_worksheet.py` |
| **Worksheet revision 樂觀鎖（R1 / ADR-027 §2）** | 同 `base_revision` 二次存檔 → 409 `WORKSHEET_REVISION_CONFLICT` 且不留半套；clone 重置為 1；publish 不 bump；`from-module`／`imports/submit` 帶 `base_revision` 的 bump + 409。**bump／`set_content_hash` 走 Core UPDATE，其 session 快取語意有三條不變量**：(A) 目標物件即時對齊 DB 真值、衝突須回報 DB 真 `current_revision`；(B) **不得 `expire_all()`** 誤傷 session 內其他物件（否則呼叫端下次屬性存取 = `MissingGreenlet`）；(C) `_resync_worksheet` 必須用 `refresh(..., attribute_names=)` **窄化到純量欄位**——整顆 `refresh()` 會把已載入的 `rows`／`process_version` expire 掉。**⚠️ 測試 setup 必須先 `session.get()` 再讓 relationship 被填充**：若直接用 `selectinload` 載入，SQLAlchemy 會把 loader options 記在 `InstanceState.load_options` 並在整顆 refresh 時**重放**，把 bug 遮掉（實測會產生一條恆綠的假測試） | `tests/integration/test_worksheet_revision_api.py` |
| **使用者管理** | list / upsert / patch；bad role 422；自鎖 409；404；viewer 403 | `tests/integration/test_admin_users.py` |
| **目錄/結構** | Site→Product→Sku→建立工序表；停用(is_active)；RBAC 403；404；重複 sku 409 | `tests/integration/test_catalog.py` |
| **計算 V2（ADR-014）** | `POST /minimost/calculate` 走 `MINIMOST_FACTORY_V2`：GM=28 / CM=29（推45cm=18吋檔）/ 推18cm→M10 反例；覆寫值取代+tech_line 標 `*` | `tests/integration/test_calculate_v2.py` |
| **計算錯誤碼（E1/E3/E4/E7）** | API 422：`A_RETURN_COMPONENT` / `P_ADDON_CONFLICT` / `OVERRIDE_INVALID`（檢 `detail.code`）；repeat 超界（0/100/1.5）422（schema 攔） | `tests/integration/test_calculate_v2.py` |
| **Worksheet SIMO（E5）** | `simo_with_row_id` 配對→存檔正規化為同一 `simo_group_id`、合計取群組 max；配對指向不存在列/自指 → 422 `SIMO_PAIR_INVALID` | `tests/integration/test_worksheet_v2_engine.py` |
| **Worksheet repeat/覆寫（E4/E7）** | repeat+manual_override 經 CycleIn 存→讀回：`slot_inputs` 原樣保留、TMU 乘算/覆寫正確、tech_line 含 `M48`/`G10*`、narrative 含 `×3`；repeat=0 存檔 422 | `tests/integration/test_worksheet_v2_engine.py` |
| **匯出** | wi-preview / excel(openpyxl) / lb-csv / lb-api | `tests/integration/test_export.py` |
| **匯入** | upload→map(正規化/警告/分秒) / profile；RBAC；openpyxl | `tests/integration/test_import.py` |
| **Excel 匯入 2b submit（ADR-013）** | submit happy-path、uploaded→409、ws不存在→404、viewer→403、重複提交→409 | `tests/integration/test_import.py` |
| **Motion Modules（impl-04）** | create→get；SM-1 IDOR；SM-2 max rows；SM-3 scope escalation；SM-4 owner immutable；SM-5 publish guard；SM-6 reorder RBAC；SM-7 apply-back version increment；DELETE happy+409；clone；instantiate；**ADR-019 Option A 迴歸（viewer 可讀任意 worksheet→200）**；**promote analyst→403（approver gate）**；**audit log 建立（action=promote）[promote 501 中；impl-06c 補 endpoint 後補整合測試]** | `tests/integration/test_motion_modules.py` |
| **搜尋基礎設施（impl-03）** | normalize 標點/空白/lower；build_content_norm 多欄串接；NullProvider 降級 semantic=False；空查詢不碰 DB；RRF 融合：兩路共鍵排首且 match_type=fused；單路鍵 rank=1000 懲罰、仍在結果、match_type=fused | `tests/unit/test_search.py` |
| **Migration v2_0016 角色改名（impl-06）** | IE→analyst / manager→approver CASE 轉換正確；admin/viewer 不動；混合角色；空陣列；downgrade 對稱 | `tests/unit/test_migration_role_rename.py` |
| **workflow_audit_log（impl-06b）** | publish process_version → action=approve / entity_type=process_version / to_status=approved / actor 非空；DB 直查驗證（用 conftest `db_session`，與 client 同 transaction；端點 impl-06c 補） | `tests/integration/test_worksheet.py` |
| **測試資料隔離（P0-0.2）** | 整合測試全走 transaction-rollback fixture（`db_ctx` 外層 BEGIN＋savepoint session，teardown ROLLBACK）；跑兩遍 `tests/integration` 後 `UT-%` motion_modules 計數不變；匿名請求（無 header、無 AUTH_DEV_USER）→401 | `tests/conftest.py`、`tests/integration/test_search.py`、`scripts/cleanup_test_data.py`（dry-run） |
| **NLP 同義詞 + nl-draft（impl-05）** | synonyms list(200)/create IE(201)/duplicate(409+SYNONYM_CONFLICT)/**同面撞 priority(409+SYNONYM_PRIORITY_COLLISION，D3-018 H1——一面多 code 需以不同 priority 顯式宣告偏好序)**/viewer(403)/delete(204)；**option_code 不存在→422 OPTION_CODE_NOT_FOUND（Fix-T1）**；**全形空白 normalize 後空→422 VALIDATION_ERROR（Fix-T3）**；nl-draft GM/CM 判型（**D3-017 起動詞字典參與判型**，衝突矩陣見 `nlp/rule_based.py` classify_seq——名詞觸發詞只是矩陣一象限：治具→GM／執行/進行/**機台（Fix-T2）**→CM 是**無動詞訊號時**的行為，動詞訊號可改判：生產詞典下「接觸治具拉至」→CM）；v3 名詞觸發單元（壓合站/壓合位置/治具；F-05 §4.1 治具防護＝同象限）；normalize OR 兜底消除（Fix-Low-T：測试机器→測試機器；機台機臺→機臺機臺） | `tests/unit/test_nlp.py`、`tests/integration/test_nlp_api.py` |
| **WI gold set 擴充（harvest／draft／eval 守門）** | harvest 決定性（同 DB 兩次 byte-identical）＋`--force` 覆蓋守衛；草稿隔離（sibling 目錄、loader 不遞迴、mutation：塞進 wi_plans 筆數必動）；轉正空殼守門（P1-3）＋**seed 豁免釘 `SEED_GOLD_IDS` 3 筆白名單（R6：第 4 筆自標 seed 必紅——字串豁免曾可穿透空殼守門＋自我指涉排除，實測假指標 0.9841）**；草稿 schema 重放自洽（pending_ie 整份 plan 相等＋compile 重放）＋**provenance 來源一致（R5：換 `source_text` 不動 `source_provenance` 必紅——spec §19 要「真實案例」）**；動詞幽靈命中排除＋GM/CM 配對中性旗標與覆核表配對題**同一判定函式**（R1/R2）；引擎拒絕期望 `expected_engine_rejected` 重放驗「仍拒絕」不假綠（R3，stub 複現舊踩雷）；自我指涉排除＋橡皮圖章回歸（P0-1）＋`[SELF-REF]` 逐案標記＋dataset_note 頭條但書（R4）；`--recompile` 拒改正式 gold（`--relock-approved --reason` 留痕） | `tests/unit/test_gold_harvest_heuristics.py`、`tests/unit/test_gold_draft_schema.py`、`tests/unit/test_gold_draft_isolation.py`、`tests/unit/test_planner_eval.py`、`tests/unit/test_gold_harvest_recompile.py`、`tests/integration/test_gold_harvest.py`、`scripts/gold_harvest.py`、`scripts/wi_ai_eval.py` |
| 前端（全分頁） | 載入/身分/分頁渲染/匯入精靈 | `src/frontend/e2e/smoke.spec.ts` |
| **前端 UX 合規（v3 規格）** | §A-01/02/03 Sidebar 結構/背景色/折疊/角色可見性；§B-01/B-02/B-03 workbench-v3 NlDraft+Slot Strip；§C-01 MiCompositionTable gap 文件化；§E-04/05/06 WI Pool 三層 Tab；§G-01/G-02 分析案件+RBAC gating；§H-01 字典管理頁；§I-01 viewer RBAC；§L-03/04 退役確認（33 條，Type A mocked-API，無需 preview_server） | `src/frontend/e2e/ux-compliance.spec.ts` |
| **字典治理：刪除／解除封存（ADR-023 D3b）** | DELETE 僅 draft（published／retired／certified_import／is_active 各自 409，**斷言 `detail.code` 不只狀態碼**）；**被引用的 draft 不可刪**（現為五個 RESTRICT 引用方：`most_cycles`／`most_worksheets`／`motion_module_versions`／`ai_parse_runs`／`ai_parse_jobs`）→ 409 `RULE_SET_IN_USE`＋筆數（回放鐵則的另一面）；刪除連帶 13 張子表歸零；audit 先寫後刪且自帶 `code`/`provenance`/`children_deleted`（實體消失後它是唯一紀錄）；unretire 後 `is_active` **仍為 false**；引用方清單以 `pg_catalog` 比對常數，比對粒度為 **(表, 欄) 對**（張數不寫死；只比表名的話「欄名寫錯→靜默數 0」與「同一表兩條 RESTRICT FK→dict 塌成一條」都測不出來），新增引用表／改錯欄名都會先紅；**引用情境由測試自建 Site→SKU→worksheet→WiRow→MostCycle（不撈既有 `most_cycles`）——CI 後端 job 不跑 `dev_seed_30rows.py`，依賴既有列＝本機綠／CI 紅** | `tests/integration/test_rule_set_delete_unretire.py` |
| **前端字典管理（ADR-023 D4）** | L1 版本清單（狀態徽章＋啟用中＋血緣中文）→ L2 七參數分頁（A 三分量／M 四分量次級 tab）；**對認證版的任何寫入動作攔截跳 clone-on-write**；帶界違規顯示後端人話錯誤而非原始 JSON；**無硬編碼 rule-set code**（一律經 `useActiveRuleSet`） | `src/frontend/e2e/dictionary.spec.ts`（Type A mocked-API） |
| **AI 批次解析 worker 硬化複驗（ADR-030）** | `fail_job` 終態必經 `_finalize_job_status` 計算：先推進 1 筆再結構性失敗→**partial**、`cancel_requested_at` 已設再結構性失敗→**cancelled**（直寫 `failed` 的旁路兩條皆紅；n_rows=1 首 tick 毒殺分不出直寫與計算）；**parse 段**（`RuleBasedParser.parse`）的 executor＋wait_for 獨立釘死（只拆 parse 段→TimeoutError 不發生、normalize 段測試不動＝靜默 wedge 現形）；done callback 在 **app 運行中（未進 shutdown）** 即出 worker 死亡 ERROR log（斷言全程在 lifespan context 內，finally 那句救不了場）；啟動訊息 **WARNING 級**（DEBUG 級捕捉＋斷言 `levelno`，降級即紅）；配額預設 `MAX_INFLIGHT_JOBS_PER_USER == 5` 防漂移（機制由 429 整合測試以 monkeypatch 常數驗證） | `tests/integration/test_parse_job_worker.py`、`tests/unit/test_wi_ai_cpu_guards.py`、`tests/unit/test_parse_job_worker.py`、`tests/unit/test_parse_job_service.py` |
| **雙語敘事（ADR-032 D7／D8／I2／I4）** | 中文字面**位元級不變**（I2，刻意綁字面）；雙語參數化語意不變式（D8）：hidden 不入句（**兩條 addon 都查**——只查一條會被後一條覆蓋而逃過）／`prefix_visible_term` 可見詞恰一次（**位置刻意不斷言**：中文前綴、英文後綴是 D7.3.2 的設計）／show_self 取代 base（base 取 `p_hold`，避免「放」是「放置」子字串的假紅）／repeat ×N／vocab 三槽／twist 點名受詞；**`display_rule` 值域完備性＝行為覆蓋同一條測試**——參數取自 `schemas/v2/rule_set_options.py` 的 `Literal`（與 DB CHECK `ck_rule_p_addons_ck_rule_p_addons_display_rule` 一致），新增第四個值時**缺 fixture 或缺雙語行為斷言都紅**（分成「先 `assert covered == declared` 再另外寫死斷言」會留下「補了 fixture 沒補斷言」的綠色中間態）；**`x_none`／`i_none` 哨兵**：fixture 照真實 DB 形狀（句面空、`label`／`label_en` 皆有值）並查**哨兵自己的**標籤不得入句——查別條選項的標籤在該 cycle 下恆真；D7.4 四個語序案例逐字；D10 英文素材缺漏回退中文；`_noun()` 空白／純 tab 詞彙名不炸且不留殘骸。端點層：存檔中英同產＋讀回兩語並列（D3.3）、clone 帶 `narrative_en`、寫入路徑仍 `require_role(analyst)`、module version **讀取時即時產生且不落盤**（JSONB 不得含 `narrative_en`）；**I4 釘版回放**——V1／V2 各發一版，V2 版含 V2 的英文句面、V1 版回退中文且**不得**出現 active 的英文素材（把 `load_options_by_rule_set_id` 換成 `load_options_from_db(…, V2)` 必紅）；版本一律**由 rule-set code 指名解析 id**（`list_rule_sets` 是 `ORDER BY created_at`，而 V1／V2 的`created_at` 實測完全相同，撈「第一筆」既非 active 也不穩定——硬性規則 7 第一則） | `tests/unit/test_narrative.py`、`tests/integration/test_narrative_en_endpoints.py` |
| **i18n 覆核側表與灌值腳本（ADR-032 D5／D6）** | DB CHECK（`source='human'` 必填 `reviewed_by`／entity_type／field／locale／source 值域）＋ UNIQUE(entity_type, scope_key, field, locale)；`upsert_review_state` get-or-create、未知 scope_key fail-closed、只存在於 draft 的 code 仍放行（D4）；sha256 過期偵測（中文改了→stale；區分 fresh machine 與 stale）；scope_key 跨 rule-set 版本共用；**灌值腳本兩條寫入路徑都驗**——測試先把 V2 的 `label_en`／`sentence_text_en` 與對應側表列清空再灌（真實 DB 早已 commit 過值，不清空等於寫入路徑根本沒被執行到：把句面寫入整段停掉照樣全綠），灌後**無條件**斷言兩欄皆非 NULL、側表 `field='label'` 與 `field='sentence'` 各一列且 `source='machine'`（句面路徑若靜默 no-op，`test_narrative_en_endpoints.py` 的「英文敘事不得殘留中文」會因 skip 條件成立而**關掉自己**）；冪等；D6 範圍不碰 published 非 active（V1 兩欄維持 NULL）；legacy_seed 只登記不覆寫既有值；未知 option code fail-loud；英文標籤在同一張表內唯一；待審清單 summary/pending 反映現況 | `tests/integration/test_i18n_review_state.py` |
| 依賴完整性 | `create_app()` 乾淨 import；端點測試抓 lazy import | CI「乾淨 import」step + 上列各端點測試 |

## 依賴鎖版與安全稽核

### 為什麼有鎖檔

在鎖檔之前，CI 與 Docker build 都是 `pip install -e .`，**每次重裝都重新解析到當下的最新版**，
而本機 `.venv` 是幾個月前裝的。於是**同一份 commit 在 CI 與本機跑的是不同的依賴**，
而且本機永遠複現不出 CI 的問題。實際發生過：fastapi 本機 0.136 / CI 0.141.1
（`include_router()` 資料結構改了 → 走訪路由表的守衛失效，兩條 unit CI 紅本機綠）；
starlette 本機裝到帶 CVE 的 1.0.0。完整經過見
`docs/architecture/legacy-inventory-and-engine-audit.md` §12。

### 形狀

| 檔案 | 內容 | 誰用 |
|---|---|---|
| `pyproject.toml` `[dependencies]` | **相容區間**＝「這份程式碼支援哪些版本」（每個下界都有實測依據，見該檔註解） | 人；`lock_deps.sh` 的輸入 |
| `requirements.lock` | **runtime 封閉集合**，逐一釘死版本 + sha256（33 個套件，含遞移依賴） | Dockerfile（production image） |
| `requirements-dev.lock` | runtime + dev 工具鏈的超集合（46 個），以 `requirements.lock` 為 constraints 解析 | CI 各 job、本機開發 |
| `requirements-build.in` | 由 `pyproject` `[build-system].requires` **生成**（勿手改） | `lock_deps.sh` 的輸入 |
| `requirements-build.lock` | **PEP 517 build backend 集合**（`setuptools` / `wheel` / `packaging`），釘死 + sha256 | Dockerfile、CI 各 job |
| `.pip-audit-ignore` | 具名、有理由、有 `REVIEW-BY` 日期的漏洞豁免清單 | `audit_deps.sh` |

**區間與鎖檔是兩件不同的東西，都要留著**：區間是「支援什麼」，鎖檔是「實際部署哪一組」。
鎖檔不取代區間宣告。

要點：

- **產生器＝`uv pip compile`**（`./scripts/lock_deps.sh`），輸出是標準 pip requirements 格式，
  所以 **CI 與 Dockerfile 用原生 pip 就能安裝，image 內不需要 uv**。uv 只在「重新產生鎖檔」時需要。
- **`--universal` 與 `--python-version` 是兩個不同的保證，不要混為一談**：
  - `--universal` ＝「**同一份鎖檔在 3.11 與 3.12 上都裝得起來**」。跨 OS／架構／直譯器
    解析同一組，差異用 marker 標註（例：`colorama ; sys_platform == 'win32'`、
    `tomli ; python_full_version <= '3.11'`）。
  - `--python-version` ＝「**同一份輸入在不同機器上跑出同一份鎖檔**」。這一項
    `--universal` **不提供**：`uv pip compile` 解析範圍的**下界預設取自「跑的人那台機器上
    被 uv 挑到的直譯器」**，而不是 `pyproject.toml` 的 `requires-python`
    （`uv help pip compile`：「Defaults to the version of the Python interpreter used for
    resolution」）。少了它，開發機（3.12）解 [3.12, ∞)、CI（3.11）解 [3.11, ∞)，
    後者多一個 `tomli`，同步關卡因此**假紅**（2026-08-12，CI run 31591161223）。
    `lock_deps.sh` 的三個 compile 一律帶 `--python-version`，值由腳本讀 `requires-python`
    的下界得到（目前 3.11），不另寫死一份常數。
  - 實測（2026-08-12）：3.11 與 3.12 兩種直譯器下跑 `lock_deps.sh`，四份產出**位元組相同**；
    兩種版本各建乾淨 venv 以 `--require-hashes` 安裝均成功，且**實際安裝的套件集合相同**
    （`tomli` 的 marker 在 3.11.15／3.12.13 上皆為 False，兩邊都不會裝到它）。
- **`--generate-hashes` + 安裝時 `--require-hashes`**：釘的是 **artifact 的位元組**，不只版本字串。
  採用的決定性理由：公司 build 走 HTTP proxy（`Dockerfile` 的 `HTTP_PROXY` ARG），
  而 proxy 正是「換掉套件內容而不改版號」最不容易被發現的位置。版本相同 ≠ 內容相同。
  代價評估後認為很低：`--require-hashes` 只作用在該次安裝指令內，不影響日常 `pip install`；
  加依賴的成本是「改 pyproject + 跑 `lock_deps.sh`」（實測 1.4 秒）。
- **`pip install --no-deps --no-build-isolation -e .`**：依賴已由鎖檔裝好，這行只註冊本專案套件。
  - 少了 `--no-deps`，pip 會拿相容區間再解析一次，**可能把鎖檔釘住的版本升掉**（鎖了等於沒鎖）。
  - 少了 `--no-build-isolation`，**hash 驗證會被繞過一個缺口**：`--no-deps` 關掉的只是
    *執行期*依賴解析，關不掉 PEP 517 build isolation。pip 仍會另開隔離環境向索引抓
    `[build-system].requires` 的 `setuptools>=68`／`wheel`（**不驗 hash**）然後**執行它們**，
    而 build backend 正是產生「最終安裝進 image 的 `ddm_v2` 套件」的那段程式碼。
    因此必須**先**裝 `requirements-build.lock` 再加這個旗標。
    實測（`--network none`）：舊寫法會去打 `/simple/setuptools/` 並失敗；新寫法零連線即完成。
- **不得 `pip install --upgrade pip`**：那會抓一個**沒有版本、沒有 hash** 的 pip，
  再用它去驗證全部 sha256——等於信任根本身不受該控制措施保護。base image 內建的 pip
  自 pip 8 起就支援 `--require-hashes`。真要升 pip 必須另立一份帶 hash 的鎖檔。
- **base image 必須以 digest 釘死**（2026-08-15 起）。`Dockerfile` 兩個 `FROM` 都帶
  `@sha256:`，**不得**只留 tag。
  - 理由是上一條的延伸：上面 800+ 個 wheel 的 sha256 驗證，**全部是跑在 base image 裡面**
    的（驗 hash 的 pip、解壓的 tar、跑 build backend 的直譯器都來自它）。base image 是整套
    控制措施的信任根；移除 `pip install --upgrade pip` 之後，它是**唯一**沒被釘住的一環。
    tag 是可變指標——上游 rebuild 後 `python:3.11-slim` 指到不同位元組，而 Dockerfile 沒變、
    鎖檔 diff 空的、CI 全綠，同一份 commit 前後建出不同的 image，沒有任何關卡看得見。
  - ⚠️ **釘的必須是 manifest list（OCI image index）的 digest，不是單平台 image 的。**
    釘錯層級的症狀是在非 amd64 機器上 build 以「no match for platform」失敗，而錯訊看不出根因。
    取值與驗證層級——**一次抓取同時得到 digest 與層級**（分兩次抓，中間上游剛好 rebuild
    就會拿到「A 的 digest ＋ B 的層級」，正是這裡要防的錯）：
    ```bash
    docker buildx imagetools inspect python:3.11-slim --raw > /tmp/mf.json
    echo "sha256:$(sha256sum /tmp/mf.json | cut -d' ' -f1)"   # ← 貼進 Dockerfile 的值
    python3 -c 'import json;print(json.load(open("/tmp/mf.json"))["mediaType"])'
    # 後者必須是 application/vnd.oci.image.index.v1+json；
    # 若是 ...image.manifest.v1+json 就是單平台的，不要用。
    ```
    ⚠️ **判層級一定要真的解析 JSON，不要用 grep 湊**。2026-08-15 實測：`python:3.11-slim`
    的 index manifest 是**壓成一行**的，且 `"manifests"` 排在頂層 `"mediaType"` **之前**，
    於是 `grep -o '"mediaType"…' | head -1` 取到的是**子 manifest** 的
    `...image.manifest.v1+json`，看起來就像「單平台、不能用」，會擋掉一次完全合法的升級。
    （`node:20-slim` 的是多行縮排格式，grep 剛好會對——「在一個 tag 上試通就當通用」正是入口。）
    推薦這條的理由：digest 的定義就是 manifest 位元組的 sha256，所以它**自我驗證**，
    不依賴任何人類可讀輸出的格式維持穩定。
    人工看一眼用 `docker buildx imagetools inspect <tag>`（頂層 `Digest:`／`MediaType:` 兩行都在）；
    腳本要裸值用 `... inspect <tag> | awk '/^Digest:/{print $2; exit}'`。

    ⚠️ **不要用 `--format '{{.Manifest.Digest}}'` 或 `'{{.Manifest.MediaType}}'`**。
    2026-08-15 實測（docker 29.3.0 / buildx v0.31.1）：格式字串若**只由一個 `.Manifest`
    選擇子構成**，buildx 會忽略它、改印整段人類可讀的預設輸出，且 **exit 0、stderr 全空**。
    照這個寫自動化比對會**恆不相等而毫無錯誤訊號**。（成因是「只有選擇子」這個形狀：
    `{{println .Manifest.Digest}}` 或前面多一個字元都能正常印裸值；但只需記上面那條。）

    也不要用 `docker pull` + `docker images --digests` 取值：取到哪個層級取決於本機 daemon
    當下拉了哪個平台，正是釘錯層級的來源。
  - tag 保留不刪：同時給 tag 與 digest 時 **Docker 只認 digest**，tag 是給人看的「哪一條線」。
  - **代價（刻意接受，但要有人管）**：釘死＝**不再自動拿到 base image 的安全修補**。
    在此之前 nightly 的 `docker-image` job 會因上游 rebuild 順帶碰到新 base image，
    **釘死之後它不會了**——pin 過期這件事目前**沒有自動化守門**，靠人依 `Dockerfile`
    `FROM` 註解的升級程序定期複查。升 digest 後 `./scripts/docker_smoke.sh` 必須綠。
  - 目前 pin（2026-08-15 實測）：`node:20-slim` → `sha256:2cf067cf…`（20-bookworm-slim，
    上游建置 2026-04-22）；`python:3.11-slim` → `sha256:a630a63c…`（3.11.16-slim-trixie，
    上游建置 2026-08-13）。容器內實測 `Python 3.11.16` / `Debian 13 (trixie)` / `pip 24.0`。

### 誰在什麼時候要更新鎖檔

| 情境 | 動作 |
|---|---|
| 改了 `pyproject.toml` 的 `[dependencies]`、`[dev]` 或 `[build-system].requires` | **必須** `./scripts/lock_deps.sh`，三個 `.lock` + `requirements-build.in` 一起 commit |
| 只改 `src/` / `tests/` / 文件 | **不用動**。鎖檔不隨程式碼變動 |
| 要刻意升級某套件 | `./scripts/lock_deps.sh --upgrade-package fastapi`（顯式，不會順手升到別的） |
| 全面升級 | `./scripts/lock_deps.sh --upgrade`（要跑完整測試 + docker smoke 才算數） |
| `pip-audit` 報漏洞 | 優先升到修正版；升不了才在 `.pip-audit-ignore` 具名豁免 |
| nightly 紅了 | 上游有破壞性變更。先判斷是「我們要跟進」還是「上游的 bug」，再決定升不升 |
| 要升 uv | **不是換工具而是換依賴解析器**：改 `lock_deps.sh` 的 `EXPECTED_UV_VERSION` → 重鎖（會有 diff，逐行看過）→ 同步 `ci.yml` 的 uv 版本 → 完整測試 + `docker_smoke.sh` |
| 要升 base image（安全修補／例行複查） | `docker buildx imagetools inspect <tag> --raw > /tmp/mf.json` → `sha256sum` 取新 digest、**同一份輸出用 `python3 -c 'import json;…["mediaType"]'`** 確認是 index（見上節兩個雷：`--format '{{.Manifest.Digest}}'` 會靜默印出整段預設輸出且 exit 0；`grep` 取 mediaType 會取到子 manifest）→ 換 `Dockerfile` 兩個 `FROM` 的 `@sha256:` → 更新該處 pin 日期 → `./scripts/docker_smoke.sh` 必須綠。**無自動守門，需人為排程複查** |

`lock_deps.sh` **不帶 `--upgrade`**：`uv pip compile` 會把既有 `.lock` 的 pin 當偏好值，
所以它是**冪等**的——沒改依賴時重跑產出位元組相同。CI 的同步關卡正是靠這個性質
（「重跑一次、diff 必須為空」），也因此**不會因為上游發了新版就無故變紅**。

**但冪等的前提是「同一版 uv」，而那個前提從前只寫在註解裡、沒有被檢查**（腳本只驗
`command -v uv`，不驗版本）。uv 的 resolver 改版足以讓同一份 `pyproject` 解出不同鎖檔，
於是同步關卡會在**沒有人改過依賴**的情況下變紅，且 diff 看起來像依賴真的變了——
這種假紅的辨識成本極高（可對照 2026-08-12 CI run 31591161223 那次下界問題，
而那次 diff 只有一行 `tomli`；resolver 改版的 diff 會是整份檔）。
因此 `lock_deps.sh` 頂部宣告 **`EXPECTED_UV_VERSION`**，
版本不符即以非 0 退出並印出實際／期望版本與兩條處置路徑。
（**本文件刻意不抄那個版本號**——查現值請跑 `./scripts/lock_deps.sh --print-expected-uv-version`
或直接看腳本頂部。先前這裡抄了一份，等於同一個值有三處拷貝、且文件那份沒有任何東西會發現它過期。）

升 uv 是**變更依賴的動作，不是換個工具**，完整程序見 `scripts/lock_deps.sh` 檔頭：
改常數 → 重跑產生 diff → 逐行看過 diff → 三份 `.lock` 一起 commit →
同步 `.github/workflows/ci.yml` 的 uv 版本 → 跑完整測試 + `audit_deps.sh` + `docker_smoke.sh`。

⚠️ **這個版本號目前有兩份拷貝**：`scripts/lock_deps.sh` 的 `EXPECTED_UV_VERSION`
與 `.github/workflows/ci.yml` 安裝 uv 那步的 URL。兩份必須一起動。
為了讓 CI 停止手抄，腳本提供 `./scripts/lock_deps.sh --print-expected-uv-version`。
`ci.yml` 要改的話**必須寫成「先賦值再驗證」**（**尚未套用**）：

```bash
UV_VERSION="$(./scripts/lock_deps.sh --print-expected-uv-version)"
[ -n "$UV_VERSION" ] || { echo "無法取得 EXPECTED_UV_VERSION"; exit 1; }
curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
```

**不可以**寫成一行 `curl -LsSf https://astral.sh/uv/$(...)/install.sh | sh`。
2026-08-15 實測（`bash -e`，即 Actions `run:` 的預設 shell，無 pipefail）：命令替換用在
**參數位置**時失敗不會讓 `-e` 中止，URL 塌成 `https://astral.sh/uv//install.sh`；而該 URL
**不是 404**——astral.sh 回 200 並轉到 `installers/uv/latest/uv-installer.sh`，
於是**安靜地裝上 latest**（實測當下 latest 為 0.12.5，與 `EXPECTED_UV_VERSION` 釘的並非同一版），
curl 與 sh 的退出碼都真的是 0，連 `pipefail` 都救不了。
賦值形式的命令替換失敗則會確實中止，再加一道空值檢查連「印出空字串」也擋掉。

### CI 怎麼用

- **`deps` job（每個 PR/push，阻斷式）**
  1. **鎖檔同步關卡**：重跑 `lock_deps.sh`，`git diff` 必須為空。
     擋的是唯一會讓鎖檔腐爛的情況——有人改了 `pyproject` 卻沒重跑。
     那會讓 image 少裝一個套件（因為 `--no-deps`），**build 成功但 import 時才炸**。
  2. **`./scripts/audit_deps.sh`（pip-audit，阻斷式非警告）**。

- **`backend` / `e2e` job**：`pip install --require-hashes -r requirements-build.lock`
  ＋ `pip install --require-hashes --no-build-isolation -r requirements-dev.lock`
  ＋ `pip install --no-deps --no-build-isolation -e .`（與 Dockerfile 同一套作法）。
  ⚠️ 原本「只裝宣告的依賴 → 漏宣告 runtime 依賴（如 openpyxl）會爆」這個性質**完整保留**：
  鎖檔是從 pyproject 宣告解析出來的封閉集合，沒宣告的套件不會出現在鎖檔裡。

- **`nightly.yml`（排程 + 手動）**：見下方「Nightly」。

### 為什麼 pip-audit 是阻斷式而不是警告

設成 warn 的守門等於沒有守門——「零告警」會同時代表「沒事」和「根本沒在跑」，兩者無法分辨
（vault 先例 `Built-Gate-Never-Executed`：三層機密守門設計得很好，13 天內保護了零次，
因為 hooks 從沒被安裝）。所以是**阻斷式 + 具名豁免清單**：要放行就得在 `.pip-audit-ignore`
留下理由與 `REVIEW-BY` 日期，並且會出現在 PR diff 裡被看到。

兩份鎖檔的豁免政策**刻意不同**：

- `requirements.lock`（會被部署出去）→ **無豁免**。要放行只能升版或換套件。
- `requirements-build.lock`（build backend）→ **無豁免**。它在 build 時被執行，且為了
  `--no-build-isolation` 也實際留在 production image 裡。
- `requirements-dev.lock`（開發/CI 工具鏈）→ 允許具名豁免。

「上游今天發 CVE、明天 CI 就紅」這個代價是**接受的**，因為紅的理由是真的
（我們確實裝著一個有已知漏洞的套件），而修法很便宜（重跑 lock 升版）。
nightly 的 `audit-latest` 會讓它通常在半夜先紅，而不是砸在隔天某個無關的 feature PR 上。
`audit_deps.sh` 另有**豁免過期檢查**：`REVIEW-BY` 過期就紅，不讓任何豁免無限期沉默。

**目前狀態（2026-08-12 實測）**：`requirements.lock` **0 findings**；
`requirements-dev.lock` 1 筆具名豁免 `PYSEC-2026-1845`（pytest ≤9.0.2 的 `/tmp/pytest-of-{user}`
本機提權/DoS）——不在 production image、威脅前提（同主機另一個本機使用者）在
一次性 CI runner 與單人開發機都不成立、且修正版 pytest 9.0.3 超出 `pytest>=8.3,<9.0` 宣告區間。
理由全文與複查日期見 `.pip-audit-ignore`。

### Nightly（`.github/workflows/nightly.yml`）

走鎖檔之後主 CI 是完全決定性的——好處是 PR 不再被上游發版波及，
代價是**我們也不再知道上游有沒有把我們弄壞**。nightly 把那個代價買回來：

| job | 做什麼 | 抓什麼 |
|---|---|---|
| `latest-resolution`（py3.11 + py3.12 矩陣） | **不用鎖檔**、`pip install -e ".[dev]"` 解析最新版，跑 core_logic + unit + integration + ruff | 上游破壞性變更。**在 nightly 紅，不在無辜的 feature PR 上紅** |
| `audit-latest` | 對鎖檔重跑 `audit_deps.sh` | 隨時間出現的新 CVE 公告（早期預警） |
| `docker-image` | `./scripts/docker_smoke.sh`＝build image → 起全新 postgres → 打端點 + 驗 GM=28/CM=29 | Dockerfile／entrypoint／COPY 路徑腐爛；釘住的 base digest 是否還拉得到；鎖檔安裝路徑是否仍成立 |

> ⚠️ **措辭已更新（2026-08-15）**：`docker-image` 這列原本寫的是它會抓
> 「**base image（`python:3.11-slim`／`node:20-slim`）被上游重建**的漂移」。
> 自 base image 以 digest 釘死後**那句話是假的**——tag 再怎麼被上游重建，這支 job
> build 到的都是同一份位元組，它不會、也不可能再看到 base image 漂移。
> 換來的新風險是**反向的**：pin 會過期（base image 出了安全修補而我們還停在舊 digest）。
> 這個風險**沒有任何自動化守門**。若要補，合理作法是加一步比對「tag 當下解析到的 digest」
> 與「Dockerfile 釘住的 digest」，不一致時**警告而非擋**（那是提醒該複查，不是建置失敗）。

矩陣跑 3.11 **和** 3.12 的理由：3.11 是 CI 與 Dockerfile 的實際部署版本，
3.12 是開發機的實際版本，`requires-python` 宣告的是 `>=3.11`——只跑一條就是宣告又一次說謊。

> ⚠️ **`schedule` 只在預設分支（`202603-rc1`）上觸發。** 這個檔合併進預設分支之前，
> 排程一次都不會跑。合併後請**手動 `workflow_dispatch` 觸發一次並確認綠燈**，
> 再把它當作在保護你——守門的驗收問題不是「寫好了嗎」而是「它執行過幾次」。

## CI jobs（`.github/workflows/ci.yml`）

- **deps**：鎖檔同步關卡（重跑 `lock_deps.sh` → diff 必須為空）→ `audit_deps.sh`（pip-audit，阻斷式）
- **backend**：postgres service → **裝鎖檔依賴（`--require-hashes`）** → 乾淨 import → migrate+seed → core_logic → `pytest tests/unit` → `pytest tests/integration`
  - ⚠️ **兩段式不可合併回 `pytest -q`**：`tests/unit` 與 `tests/integration` 有同名檔案（`test_search.py`）
    且兩個目錄都不是 package，單一 `pytest -q` 會 import file mismatch → collection error →
    **整批中斷、一條測試都不算數**（守衛型測試因此可能長期沒真的跑過）。
- **frontend**：`npm ci` → typecheck → build
- **e2e（smoke）**：full stack（seed + build + preview_server :8099）→ `smoke.spec.ts`
- **e2e（ux-compliance）**：Type A mocked-API；只需 Vite dev server 或 preview_server 提供靜態資源 → `ux-compliance.spec.ts`（33 條，E2E_BASE_URL=`http://localhost:5173`）

## 本機快速重現 CI

```bash
cd ddm-v2
# ⚠️ 用鎖檔安裝，不要用 `pip install -e ".[dev]"`——後者會解析到當下最新版，
#    等於刻意重現「本機與 CI 裝到不同版」這個病。
pip install --require-hashes -r requirements-build.lock
pip install --require-hashes --no-build-isolation -r requirements-dev.lock
pip install --no-deps --no-build-isolation -e .
DATABASE_URL=... PYTHONPATH=src alembic upgrade head
DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_v2.py
DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_templates.py
DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_synonyms.py
DATABASE_URL=... PYTHONPATH=src python scripts/dev_seed_i18n_labels.py
DATABASE_URL=... PYTHONPATH=src python scripts/core_logic/run_all.py
PYTHONPATH=src pytest tests/unit -q                       # 免 DB
DATABASE_URL=... PYTHONPATH=src pytest tests/integration -q
( cd src/frontend && npm run typecheck && npm run build )

# deps job（改了依賴才需要；audit 需先 pip install pip-audit==2.10.1）
./scripts/lock_deps.sh && git diff --exit-code -- requirements.lock requirements-dev.lock requirements-build.in requirements-build.lock
./scripts/audit_deps.sh

# 容器交付路徑（host 的 pytest 完全不經過 image，兩者可以分叉數天）
./scripts/docker_smoke.sh
```

⚠️ **本機 DB ≠ CI DB**：backend job 只跑 `dev_seed_v2.py` ＋ `dev_seed_templates.py` ＋
`dev_seed_synonyms.py` ＋ `dev_seed_i18n_labels.py`，
**不跑 `dev_seed_30rows.py`**（那支只在 e2e job）——所以 CI 的 `most_cycles` / `wi_rows` 是 **0 列**，
`work_vocab_items` 也只有 `dev_seed_v2.py` 建的 3 筆（非 30rows 種出的完整 59 筆），
而開發機通常早就被 30rows 種過。任何「撈一列既有資料來用」或「硬編列數」的整合測試都會
**本機綠、CI 紅**（2026-08 `test_delete_referenced_draft_returns_409_with_reference_count` 即此；
ADR-032 Phase B 的待審清單測試也曾誤把 59 寫死，改成動態查 `work_vocab_items` 現況才通用）。
**整合測試必須自建所需資料**（自己建 Site→SKU→worksheet→row），不得依賴既有列，
也不得以 UPDATE 劫持 demo 資料（那只是靠 fixture rollback 沒落盤而已）。
要在合併前驗證，請在**乾淨 DB** 上重現：

```bash
createdb ddm_ci_repro   # 或 docker compose exec db psql -U ... -c 'CREATE DATABASE ddm_ci_repro'
export DATABASE_URL=postgresql+asyncpg://.../ddm_ci_repro
PYTHONPATH=src alembic upgrade head
PYTHONPATH=src python scripts/dev_seed_v2.py && PYTHONPATH=src python scripts/dev_seed_templates.py
PYTHONPATH=src python scripts/dev_seed_synonyms.py   # 同義詞詞典（守門判定對象；漏跑＝守門 3 紅）
# i18n 覆核狀態灌值（ADR-032 Phase B）：部署腳本的煙霧測試，不是測試依賴——每個
# 需要 i18n 資料的測試都自建（見 test_i18n_review_state.py／test_i18n_routes.py），
# 漏跑不影響 pytest 結果（L-2，2026-08-18 第三輪複審實測澄清）
PYTHONPATH=src python scripts/dev_seed_i18n_labels.py
PYTHONPATH=src pytest tests/integration -q     # 這裡綠才算真的綠
```
