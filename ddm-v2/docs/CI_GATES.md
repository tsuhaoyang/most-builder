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
   無 hash 下載並執行）。詳見下方「依賴鎖版與安全稽核」。

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
| **NLP 同義詞 + nl-draft（impl-05）** | synonyms list(200)/create IE(201)/duplicate(409+SYNONYM_CONFLICT)/viewer(403)/delete(204)；**option_code 不存在→422 OPTION_CODE_NOT_FOUND（Fix-T1）**；**全形空白 normalize 後空→422 VALIDATION_ERROR（Fix-T3）**；nl-draft GM 治具防護(F-05 §4.1)；v3 治具全套單元（壓合站/壓合位置/治具→GM；執行/進行/**機台（CM 觸發詞，Fix-T2）**→CM）；normalize OR 兜底消除（Fix-Low-T：測试机器→測試機器；機台機臺→機臺機臺） | `tests/unit/test_nlp.py`、`tests/integration/test_nlp_api.py` |
| 前端（全分頁） | 載入/身分/分頁渲染/匯入精靈 | `src/frontend/e2e/smoke.spec.ts` |
| **前端 UX 合規（v3 規格）** | §A-01/02/03 Sidebar 結構/背景色/折疊/角色可見性；§B-01/B-02/B-03 workbench-v3 NlDraft+Slot Strip；§C-01 MiCompositionTable gap 文件化；§E-04/05/06 WI Pool 三層 Tab；§G-01/G-02 分析案件+RBAC gating；§H-01 字典管理頁；§I-01 viewer RBAC；§L-03/04 退役確認（33 條，Type A mocked-API，無需 preview_server） | `src/frontend/e2e/ux-compliance.spec.ts` |
| **字典治理：刪除／解除封存（ADR-023 D3b）** | DELETE 僅 draft（published／retired／certified_import／is_active 各自 409，**斷言 `detail.code` 不只狀態碼**）；**被引用的 draft 不可刪**（現為五個 RESTRICT 引用方：`most_cycles`／`most_worksheets`／`motion_module_versions`／`ai_parse_runs`／`ai_parse_jobs`）→ 409 `RULE_SET_IN_USE`＋筆數（回放鐵則的另一面）；刪除連帶 13 張子表歸零；audit 先寫後刪且自帶 `code`/`provenance`/`children_deleted`（實體消失後它是唯一紀錄）；unretire 後 `is_active` **仍為 false**；引用方清單以 `pg_catalog` 比對常數，比對粒度為 **(表, 欄) 對**（張數不寫死；只比表名的話「欄名寫錯→靜默數 0」與「同一表兩條 RESTRICT FK→dict 塌成一條」都測不出來），新增引用表／改錯欄名都會先紅；**引用情境由測試自建 Site→SKU→worksheet→WiRow→MostCycle（不撈既有 `most_cycles`）——CI 後端 job 不跑 `dev_seed_30rows.py`，依賴既有列＝本機綠／CI 紅** | `tests/integration/test_rule_set_delete_unretire.py` |
| **前端字典管理（ADR-023 D4）** | L1 版本清單（狀態徽章＋啟用中＋血緣中文）→ L2 七參數分頁（A 三分量／M 四分量次級 tab）；**對認證版的任何寫入動作攔截跳 clone-on-write**；帶界違規顯示後端人話錯誤而非原始 JSON；**無硬編碼 rule-set code**（一律經 `useActiveRuleSet`） | `src/frontend/e2e/dictionary.spec.ts`（Type A mocked-API） |
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

### 誰在什麼時候要更新鎖檔

| 情境 | 動作 |
|---|---|
| 改了 `pyproject.toml` 的 `[dependencies]`、`[dev]` 或 `[build-system].requires` | **必須** `./scripts/lock_deps.sh`，三個 `.lock` + `requirements-build.in` 一起 commit |
| 只改 `src/` / `tests/` / 文件 | **不用動**。鎖檔不隨程式碼變動 |
| 要刻意升級某套件 | `./scripts/lock_deps.sh --upgrade-package fastapi`（顯式，不會順手升到別的） |
| 全面升級 | `./scripts/lock_deps.sh --upgrade`（要跑完整測試 + docker smoke 才算數） |
| `pip-audit` 報漏洞 | 優先升到修正版；升不了才在 `.pip-audit-ignore` 具名豁免 |
| nightly 紅了 | 上游有破壞性變更。先判斷是「我們要跟進」還是「上游的 bug」，再決定升不升 |

`lock_deps.sh` **不帶 `--upgrade`**：`uv pip compile` 會把既有 `.lock` 的 pin 當偏好值，
所以它是**冪等**的——沒改依賴時重跑產出位元組相同。CI 的同步關卡正是靠這個性質
（「重跑一次、diff 必須為空」），也因此**不會因為上游發了新版就無故變紅**。

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
| `docker-image` | `./scripts/docker_smoke.sh`＝build image → 起全新 postgres → 打端點 + 驗 GM=28/CM=29 | Dockerfile／entrypoint 腐爛；**base image（`python:3.11-slim`／`node:20-slim`）被上游重建**的漂移 |

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

⚠️ **本機 DB ≠ CI DB**：backend job 只跑 `dev_seed_v2.py` ＋ `dev_seed_templates.py`，
**不跑 `dev_seed_30rows.py`**（那支只在 e2e job）——所以 CI 的 `most_cycles` / `wi_rows` 是 **0 列**，
而開發機通常早就被 30rows 種過。任何「撈一列既有資料來用」的整合測試都會**本機綠、CI 紅**
（2026-08 `test_delete_referenced_draft_returns_409_with_reference_count` 即此）。
**整合測試必須自建所需資料**（自己建 Site→SKU→worksheet→row），不得依賴既有列，
也不得以 UPDATE 劫持 demo 資料（那只是靠 fixture rollback 沒落盤而已）。
要在合併前驗證，請在**乾淨 DB** 上重現：

```bash
createdb ddm_ci_repro   # 或 docker compose exec db psql -U ... -c 'CREATE DATABASE ddm_ci_repro'
export DATABASE_URL=postgresql+asyncpg://.../ddm_ci_repro
PYTHONPATH=src alembic upgrade head
PYTHONPATH=src python scripts/dev_seed_v2.py && PYTHONPATH=src python scripts/dev_seed_templates.py
PYTHONPATH=src pytest tests/integration -q     # 這裡綠才算真的綠
```
