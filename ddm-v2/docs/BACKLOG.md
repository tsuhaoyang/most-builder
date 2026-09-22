# docs BACKLOG — 缺口票

> **兩類票**（2026-09-21 起）：
> - **`BL-DOC-n` 文件缺口票**（WP-D1 盤點 → WP-D2 開票）：有程式、缺單一權威規格的區域。**不得現場編規格**
>   （只開票、領域索引誠實標「現況以程式為準」）；補 spec 需另行排程並經核准。
>   每票：領域、現況、影響、建議補的 spec 範圍。
> - **`BL-ENG-n` 工程票**：程式／UI 的已知缺陷或待統一項，開票是為了讓「另案」有編號可追。
>   每票：領域、現況、影響、建議做法、對應文件。
>
> 優先序由 Howard 裁定（2026-09-17）。

## BL-DOC-1（最高）— rule-set 生命週期規格
- 領域：`rule-set`
- 現況：`rule_set_service.py`（clone→改→發布→retired）、`synonym_service.py`（同義詞治理）、per-cycle `rule_set_id` 回放**只存在於程式與對話**；ADR-023 偏「詞彙治理」，無單一「rule-set 生命週期」spec。
- 影響：**「回放鐵則」（舊 worksheet 以釘版 rule_set_id 維持原值）沒有 spec＝那條鐵則只在程式與對話裡**；改到版本狀態機、synonym 唯一性、published 凍結時無權威可比對。
- 建議 spec 範圍：版本狀態機（draft/published/certified/retired）、clone provenance、`version_no` 配號序列化（advisory lock）、回放語義、synonym 正規化與唯一性（EN_LABEL_NOT_UNIQUE）、retired 閘門。

## BL-DOC-2（次之）— nlp/ lexicon／linking／routing 行為規格
- 領域：`nlp-compiler`（`nlp/**` 部分）
- 現況：`most_compiler`（policies/compile）有 ADR-033；但 `nlp/**` 20 檔（`lexicon.py`、`linking.py`、`routing.py`、`rule_based.py`、`normalization.py`、`quantities.py`…）**只有程式可讀**，AI 路徑行為無文件。
- 影響：AI 解析路徑（詞彙比對、連結、路由、規則式 planner）的行為與邊界只在程式，難審語意漂移。
- 建議 spec 範圍：lexicon 來源與正規化、linking 決策、routing（rule_based vs llm）門檻、quantities 解析與 QuantityPolicy 對接、與 engine_gate 的關係。

## BL-DOC-3（第三級）— motion-module／wi-set 規格
- 領域：`motion-module`
- 現況：`motion_module_service.py`（WI 大綱、實體化 from-module、reorder、range）、`wi_set_service.py`、`wi_context_service.py` **無專屬權威文件**（ADR-025 只談範本比對）。
- 影響：WI 兩層結構（WI⊃motion）在 worksheet 情境的實體化與版本語義無 spec。
- 建議 spec 範圍：module category（wi-template/action）、實體化與 wi_group 帶入、reorder/delete 的 SIMO 約束、版本與 TMU drift。

## BL-DOC-4（第三級）— auth-rbac 的 outbox／search 規格
- 領域：`auth-rbac`
- 現況：RBAC 有 `rbac-spec.md`＋ADR-019；但 `outbox_service.py`（R3b 事件與 review／save 同交易）、`search/**`（bge-m3 向量檢索）**無專屬文件**。
- 影響：outbox event 契約（claim/publish、payload schema version）與 search provider 邊界只在程式。
- 建議 spec 範圍：outbox event 型別與交易保證、claim_pending/mark_published 可見性、search port/adapter 契約與正規化。

## BL-DOC-5（第三級）— excel-import 流程細節規格
- 領域：`excel-import`
- 現況：ADR-013 僅骨架（2KB）；staging→submit、column_map、TARGET_FIELDS、profile 重用的細節散在 `import_service.py`。
- 影響：匯入兩階段流程與欄位對應規則無完整 spec。
- 建議 spec 範圍：staging schema、column_map 驗證（缺 description 擋）、TARGET_FIELDS（含 wi_group）、rule-set 缺庫時 fallback 的報告義務、profile 重用。

---

# 工程票（BL-ENG）

## BL-ENG-1 — offline 組內傳染兩份實作，統一為共用函式
- 領域：`lb-projection`（回寫 apply-offline）、`job-ux`（作業版 store）
- 現況：同一條「同 `countersignature` cub 或同 `worker_cub` wcub 一起翻 offline」的規則有兩份實作——後端
  `src/ddm_v2/services/v2/lb_writeback_service.py` 的 `_group_members()`（權威），前端
  `src/frontend/src/features/level-system/store.ts` 的 `toggleOffline()`（UX 即時回饋）。後端註解自述「規則與前端一致」，
  但一致性只靠人維護，沒有任何測試或守衛把兩邊綁在一起。
- 影響：任一側改了傳染規則（例如日後把 `segment` 或 `station_pin` 納入同組），另一側會靜默不同步：前端顯示的
  連動範圍與後端實際寫入的不一致，IE 勾選後看到的結果和畫面預期不同。
- 建議做法：把傳染規則抽成單一來源（後端純函式 ＋ 前端以相同輸入呼叫，或前端改為送出後以後端回應的 `propagated`
  為準、不自行預測），並補一條「兩側對同一組輸入得到相同傳染集合」的測試。
- 一併處理（2026-09-21 審查發現）：兩份實作的**比對判準本身**也不一致——後端 `_group_members()` 以原始字串比對
  `countersignature`／`worker_cub`，前端 store 走 `mappers.group_id` 的數值判準。即使規則文字一致，前後空白或
  `"01"` vs `1` 這類寫法差異就會讓兩邊算出不同的組。統一時要連判準一起定死（以哪一側為準需在票內裁定）。
- 對應文件：實作書 `LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md` §2 B6-2 與 §7 (f) 指向本票。

## BL-ENG-2 — 投影層「拋出例外」而非「收集 E 碼」
- 領域：`lb-projection`
- 現況：`src/ddm_v2/lb_projection/` 對部分 E 碼是直接 `raise`（`QuantityError`／`ToolResolveError`／
  `TmuDecompositionError`／`PrecedenceError`），不像其餘 E 碼收進 `ProjectionResult.errors`。`project_rows()` 只捕捉
  `PrecedenceError`。凡是呼叫投影的路徑都要各自防守：回寫件數基準已降級（`_units_baseline` 標
  `units_baseline=unavailable`）、apply-offline 的投影報告已降級（`report.status=unavailable`），但
  `GET /export/lb-report`、`GET /export/lb-csv` 對同一批 worksheet 仍會落成無信封 500。
- 影響：使用者存得進去的 worksheet 狀態（例如持工具列同時設 frequency>1 與 repeat>1、非整數 frequency）會讓
  匯出端點 500；每個呼叫端都要重複寫一次 try/except，漏一個就是 500。`export.py` 對 lb-report 宣稱的「永遠回報告」
  也因此不成立。
- 建議做法：把這幾類例外在投影層收成 E 碼（`ProjectionResult.errors`），讓「E 碼擋、不拋例外」成為單一規則
  （`QuantityError`／`ToolResolveError`／`TmuDecompositionError` 是真的會逃出去的三類；`PrecedenceError` 已在
  `project_rows` 內被接住轉成收集型 E，收斂時順手把那段 try/except 也收掉）；
  之後移除各呼叫端的防守性 try/except。**動到投影層必跑黃金驗收**（`tests/unit/test_lb_projection_golden.py`
  逐位元 34 列、`scripts/core_logic/run_all.py` 不受影響）。
- **完成條件要先裁決一件事（2026-09-21，lb-projection reviewer 提案，待 Howard 裁）**：實際逃得到降級路徑的是**三類**
  （`QuantityError`／`ToolResolveError`／`TmuDecompositionError`；`PrecedenceError` 在 `project.py` 內就被接住
  轉成收集型 E，服務端仍列著它只是縱深），而這三類**都攜帶確定的 E 碼**，所以 apply-offline 目前的降級
  等於「閘門跑不起來時放行」（fail-open）。reviewer 主張把 E 碼餵進
  `proj_errors`（約三行）即可整批 rollback ＋ 422 `LB_EXPORT_BLOCKED`（fail-closed）；Howard 在 2026-09-21 指定
  本輪維持降級 200。本票收斂時會**翻轉這個行為**，屬於使用者可見的變更，不得當成重構順手做掉——
  需 Howard 明示採 fail-open 或 fail-closed，並同步實作書 §7 (g) 與 UI 文案。
- **降級跳過的那一關，正好包含這個操作自己可能製造出來的 E**（2026-09-21 查證）：`E_OFFLINE_INCONSISTENT`
  是收集型，由 validator 在 `project_rows` 最尾端產生；三類拋出型例外全在它之前拋出，投影一拋例外
  validator 根本沒跑。而傳染與投影的分組判準不等價——傳染用 `countersignature` 原字串相等、投影的 group
  用 `cub\d+` 取出的數字，`"cub1"` 與 `"cub01"` 不互相傳染卻落進同一個 group。正常情況這一關會擋，
  降級時不會。機率低但路徑真實。（分組判準本身見 BL-ENG-1。）
- **收斂時必須守住的三件事（2026-09-21 lb-projection reviewer）**：
  (1) 不得改用 `report_status`／`report_errors` 這兩個 key 表達別的意思——既有歷史列會被誤讀；
  (2) 收斂後 `detail.projection_errors` 別再只留裸 code，否則新路徑保留的資訊反而比現在少；
  (3) `lb_writeback_service` 目前是**手抄**一份 `lb_projection/report.py` 的 `_err_dict`；那邊哪天加第 5 欄，
      這份持久化的複本會無聲落後、落差烙進歷史列。收斂時把 `_err_dict` 匯出共用。
- 對應文件：ADR-035（投影層 E/W 碼）、實作書 §7 (g) 與本票。

## BL-ENG-3 — 回寫產線視角把異常講成正常（五處，同一類）
- 領域：`job-ux`（`src/frontend/src/features/level-system/WritebackPanel.tsx`）
- 現況：
  1. `GET …/lb-writeback/latest` 的**任何**失敗（404／5xx／舊快照 422）都落到同一分支，畫面顯示
     「這份工序表還沒有產線平衡的實際結果」——把「讀取失敗」說成「還沒有結果」。
  2. 站別文案只看 `stations.length > 1` 就顯示「每站都有（通用步驟）」，非通用動作被排到多站時，會同時出現
     「每站都有（通用步驟）」與「⚠ 同一步驟被排到不同站」兩句互相矛盾的話。
  3. offline 動作的 `stations` 為空，`(stations[0] ?? 0) + 1` 算出 1，顯示成「排到第 1 站，0 個人做」——
     實際是離線先做、不排站。
  4.（2026-09-21 新增）apply-offline 降級時，`applied_report_reasons`（E 碼）**存了但畫面從不顯示**，
     作業者看得到「那一關沒跑」卻查不到原因。`levelSystem.plain.*` 已有這幾類 E 碼的中英可執行文案，
     缺的是把 code 接上去：但 `reasons` 目前只帶裸 code（`[exc.err.code]`），不帶 `wi_row_id`／params，
     直接餵 `plainDiag` 會渲染出 `{{step}}` 空洞殘句。要指路得先讓 reasons 帶上 `exc.err.wi_row_id`
     （後端已有、目前只寫進 log）。**2026-09-21 更新**：完整診斷已改為存進 `applied_rows.report_errors`
     並由 `latest`／apply 回應帶出（`{code, wi_row_id, message, params}`，形狀與 `plainDiag` 吃的
     `LbReportDiag` 逐欄相同，`stepOf` 直接傳 `WritebackPanel` 既有的 `label`）——**接線本身現在只差 UI**。
     接上去之前要先修一個既存的鍵名不匹配：`notices.ts` 讀 `params.freq`，投影層存的是 `params.frequency`
     （`lb_projection/quantity.py`），`E_TOOL_FRACTIONAL_FREQUENCY` 會渲染成「（目前 ）」。
     建議改 `params.freq ?? params.frequency`（加法、不動投影層、不必重跑黃金驗收）。
     另注意：此時 `GET /export/report` 本身也 500（BL-ENG-2），作業版的「要處理」清單同樣是空的——
     兩票要一起看才有完整的下一步。
  5.（2026-09-21 新增，**嚴重度最高的一處**）`JobsShell.tsx` 的預覽 `onError` **只有 422 會設 `previewError`**，
     其他狀態碼（含投影例外造成的 500）只 `setUpdating(false)`、**不清掉上一次成功的 `report`**。於是
     `ready===true`、`errCount===0` → 頂端顯示綠色 pill「可以交出」，且「儲存並交給產線平衡」按鈕是 enabled，
     按下去導向的 `/export/lb-csv` 對同一份工序表會落成 500。預設子檢視就是這個視角（產線視角要手動切）。
     **修法（job-ux reviewer 2026-09-21 提供，約 8 行、0 個新 i18n key）**：加 `previewUnavailable` state；
     `onSuccess` 清成 false；`onError` 的非-422 分支設 `setReport(null)` ＋ `setPreviewUnavailable(true)`；
     **`{!ready && !previewUnavailable && <preview-updating>}`**（這一行就是「會永遠停在更新中」的解——
     不加這一攔截才會卡住，不是不能修）；pill 加第三態 `pill-preview-unavailable`，可直接用既有但零引用的
     `levelSystem.jobs.preview.failed`（zh/en 都已存在）；匯出按鈕 `disabled` 加 `|| previewUnavailable`。
     reviewer 的評估：正常路徑逐位元不變，既有 e2e（`pill-ok`／`preview-updating`）不受影響。
     **注意**：預覽失敗不只源自 BL-ENG-2（DB 中斷、gateway 逾時、部署中都會），所以這個第三態是常設需求，
     不是 BL-ENG-2 的附屬品——修好根因後仍應保留。
- 影響：四者都讓異常看起來像正常狀態，IE 不會去查。這是同一類錯誤（顯示層沒有分辨資料的語意），分開修會東補西補。
- 建議做法：一次處理顯示語意——讀取失敗與「無快照」分開（沿用 ADR-034 catalog 的訊息）、站別文案改依
  `cross_station`／`is_general`／`offline` 決定、offline 用作業版既有的「離線先做」用語；並補 e2e 斷言三種狀態。
- 對應文件：實作書 §3 F2、§7 (d)(e) 與本票。

## BL-ENG-4 — 回寫五支端點沒有 RBAC 測試
- 領域：`auth-rbac`（`src/ddm_v2/api/routes/v2/lb_writeback.py`）
- 現況：五支端點的權限已依 ADR-019 標好（讀 viewer+、寫 `require_role("analyst")`），但整合測試一律以具權限的
  client 呼叫，沒有任何一支驗證「viewer 打寫入端點得 403」。權限裝飾被誤刪或誤改成 `current_user` 時，測試全綠。
- 影響：回寫是**會改別人工序表**的寫入路徑（apply-offline 直接改 `lb_tags.offline`），權限退化不會被擋住。
- **本輪已補（2026-09-21）**：`tests/integration/test_lb_writeback_endpoints.py` 加了兩組參數化測試——
  `fetch`／`import`／`apply-offline` 以 viewer 身分 → 403，`latest`／`snapshots` → 不得 403。突變驗證：
  把 apply-offline 的 `require_role("analyst")` 降成 `current_user` → 該測試轉紅。
  作法不需要新 fixture（票原本寫「主要成本是 conftest fixture」是錯的）：丟一個從未出現過的員編當
  `X-Username`，`current_user` 就 JIT 出 `roles=[]` 的 viewer（既有 pattern 在
  `tests/integration/test_i18n_review_mutations.py` 的 `_viewer_headers`）。
- **剩餘範圍**：其餘 v2 端點的 RBAC 覆蓋率未盤點；本票縮小為「把同一組 viewer 斷言推廣到其他寫入端點」。
- 對應文件：ADR-019、`docs/architecture/rbac-spec.md`。

## BL-ENG-5 — apply-offline 的留痕會被蓋掉、被刪掉，且「被 E 碼擋下」那條完全不留紀錄
- 領域：`lb-projection`（回寫）、`auth-rbac`（稽核）
- 現況（2026-09-21 lb-projection reviewer 逐行查證）：`applied_rows` 是**整份覆寫**的 JSONB，不是 append-only。
  1. **被蓋**：同一快照可被套用第二次（每次重算 `offline_diffs`，其他仍有差異的列仍在清單內）。
     「投影壞掉時套 A（unavailable）→ 修好後套 B（ok）」會把 `report_status`／`report_errors` 蓋成 ok／空，
     降級那次的紀錄與前端琥珀提示一起消失。
  2. **被刪**：`_enforce_retention` 按 `fetched_at` 刪第 10 筆以後的快照，**不看 `applied_at`**。
     再 fetch 10 次，「沒跑投影就套用」的證據連同 payload 一起刪掉。
  3. **擋下那條不留紀錄**：E 碼存在 → rollback ＋ 422，整件事**完全沒有紀錄**，且 `detail.projection_errors`
     只留裸 code。「jsonb 歷史現在不存、日後救不回」這個理由同樣適用於它。
- 影響：回寫是會改別人工序表的寫入路徑，而本 service **沒有任何 audit 寫入**（grep `audit|log_action|AuditLog`
  無結果），`applied_rows` 是唯一痕跡——而它會被蓋、會被刪。事後要問「這批 offline 是誰在什麼狀態下套的」答不出來。
- 建議做法：改用現成的 append-only 設施 `workflow_audit_log`（`services/v2/audit_service.py`，ADR-018 裁決 3
  「僅追加」）。**不是順手改**：`entity_type` 值域在 DB CHECK 裡，加值要走 migration，屬決策層級。
  `level_validation_runs` 不能代替（同 `input_hash` 直接回既有列，是內容鍵不是動作紀錄）。
- 對應文件：ADR-018（稽核）、ADR-036、ADR-019。

## BL-ENG-6 — 422 信封原樣回吐輸入值，缺 body 大小上限
- 領域：全域（`src/ddm_v2/api/error_handlers.py`）
- 現況（2026-09-21 資安審查實測，fastapi 0.141.1／pydantic 2.13.4）：`VALIDATION_ERROR` 的 detail 直接用
  `jsonable_encoder(exc.errors())`，pydantic 每筆錯誤都帶 `input`（原樣輸入值）。
  回寫 `apply-offline` 加了 `max_length=1000` 之後，1000 筆以內的天花板約 285 KB（最壞比例仍 60×：
  1000 個空字串 4 KB → 247 KB）；超過上限雖只剩一筆 `too_long`，但它的 `input` **是整份 list**——
  4 MB 請求換 3.9 MB 回應（1:1），100 MB 換 100 MB。全專案沒有 body 大小上限（uvicorn 未設，
  只有 `import_excel.py` 自己擋上傳檔 10 MiB），而 ADR-036 §4 的回寫又是不經 gateway 直連。
  同一支路由的 `import` 端點 `payload: dict` 也完全無上限。
- 影響：單一請求即可讓後端讀入整包 body 再序列化一份回吐，放大或等量；這是全端點共通面，不只回寫。
- 建議做法：在 `error_handlers` 截斷（留前 N 筆錯誤、砍過長 `input`）——一改全端點受益。
  **注意**：ADR-034 §D5 明寫 detail「原封不動」，所以這是**契約變更**，要 ADR 追記，不是順手改。
  另可在部署層（uvicorn／Traefik）加 body 上限，但掛 gateway 前不成立。
- 對應文件：ADR-034 §D5、ADR-036 §4。
- **2026-09-22 部分處置與更正**：`707d0c0` 讓 `_parse_int`／`_parse_bool` 的錯誤訊息改為限長（`_brief`），
  但該 commit 訊息寫「rows[] 共用同一 helper 一併受益」**不完全正確**——doc-sync 實測 `qty_scope`、
  `units[].units`、`contract_version` 的錯誤訊息仍原樣帶入輸入值（100 KB 輸入 → 約 100 KB 訊息；
  `contract_version` 的 `got` 還會出現在 detail 裡）。這幾處仍屬本票範圍。

## BL-ENG-7 — level 範圍展開無上界：11 字元的輸入可讓每次讀取吃掉數十 GB
- 領域：`most-engine`／`level-system`（`src/ddm_v2/most_engine/level.py`、`src/ddm_v2/schemas/v2/most.py`）
- 現況（2026-09-21 資安審查實測）：`_parse_level` 對 `a~b` 直接 `set(range(lo, hi + 1))`，**沒有跨距上限**；
  上游 `level` 在 schema 是裸 `str | None`（無 `pattern`、無 `max_length`），DB 是 `Text`。
  於是 `level="1~999999999"`（11 字元）存得進去、存檔不擋，之後**每一次**投影都會展開這個集合——
  實測 `1~5000000` 為 0.39 秒／294 MB，外推 `1~999999999` 約 57 GB／77 秒。
  同類的還有 `level='1/'*200000+'1'`（400 KB）可通過 `_parse_level` 與 R1–R9。
- 影響：任何 analyst 存一次，之後**每個 viewer** 呼叫 `lb-writeback/latest`（或任何走投影的端點）都會觸發，
  形同放在資料裡的定時炸彈；不需要重複發請求。ADR-036 §4 的回寫又是不經 gateway 直連。
- 建議做法：**需要 Howard 先裁一件事——合法 level 的上界是多少**（工程上 level 是動作層級，實務值遠小於 100）。
  裁定後兩邊一起收：schema 加 `pattern`／`max_length`（擋掉超長與超大數字），`level.py` 對跨距加明確上限並
  回既有的 `R7_LEVEL_FORMAT`。**動到 level → 必過 `PYTHONPATH=src python scripts/core_logic/run_all.py`
  （黃金 GM=28／CM=29）**，所以不是順手改。
- 一併緩解：同一個 pattern 也會擋掉 BL-ENG-5 提到的「400 KB message 進 jsonb 並每次回吐」（該處已先截到 500 字）。
- 對應文件：`docs/core-logic/`（level 規則）、ADR-036 §4。

## BL-ENG-8 — outbox 整合測試會被共用 dev DB 的既有資料擠掉（**2026-09-22 已修**）
- **結案說明**：Howard 2026-09-22 指示本輪修（「根因不是資料太多，是測試依賴全域狀態——和 fixture 佔固定 id
  是同一個病；不要用清 dev DB 解決」）。做法：測試以自己的 `run_id` 直接找到自己那筆，只把**自己那一列**的
  `created_at` 調到最前面，`claim_pending(limit=1)` 就確定領到它；發布後再領一次確認不會被領回。
  不清 DB 即綠（當時 dev DB 有 284 筆 pending），突變兩條皆紅（不調 created_at／`mark_published` 失效）。
- **留下的缺口（新發現，未處理）**：`tests/integration/test_outbox_api.py` 在 `domain_guard.py map` **零命中**——
  outbox（ADR-027）沒有登記在任何領域的 paths 裡，改它不會觸發任何 logic reviewer。
- 領域：`wi-workbench`／測試基礎建設（`tests/integration/test_outbox_api.py`）
- 現況（2026-09-21 查證）：`test_claim_pending_and_mark_published` 先建一筆事件，再 `claim_pending(db_session, limit=50)`
  然後從結果裡找自己那筆。共用 dev DB 目前有 **272 筆 `published_at IS NULL`** 的 outbox 事件，`limit=50`
  取的是最舊的 50 筆——新建的那筆永遠不在裡面，`assert len(ours) == 1` 得到 0。**現在就是紅的**，
  且與任何程式改動無關（在乾淨工作樹上同樣失敗，2026-09-21 以 `git stash` 驗過）。
- 為什麼會一直惡化：outbox 沒有消費端（publisher 卡在 ADR-027 R0 待裁），所以未發布筆數只增不減。
- 影響：一支與本功能無關的測試長期紅，會把「整合測試全綠」這個訊號廢掉——下一個人看到 1 failed 會習慣性略過。
- 建議做法（二擇一，屬測試設計決策）：(a) 測試改為只 claim 自己那筆（依 `run_id`／`id` 過濾後再 claim，
  或把 `limit` 提高到「保證涵蓋」不可行——資料會繼續長），(b) 測試自備乾淨的 outbox 範圍（例如在交易內先把
  既有 pending 標記為已發布——但本測試走 conftest 外層交易會 rollback，可行性要確認）。
  **不要用「清掉 dev DB 既有資料」解**（那是別人的資料；2026-09-18 已有前例）。
- 對應文件：ADR-027（outbox）。

## BL-ENG-9 — 件數聚合的三個「把不確定講成確定／靜默消失」
- 領域：`lb-projection`（`_motion_units`）、`job-ux`（`WritebackPanel`）
- 現況（2026-09-21 job-ux reviewer 查證，皆無測試覆蓋）：
  1. **多列 cyclic 值不一致時靜默取大**：`_motion_units` 對 `qty_scope=="cyclic"` 的列取 `max`，docstring
     假設「值相同」，但 parse 不檢查。LB 若回兩列 cyclic 且值不同，MOST 取大的那個並標 `units_source="cyclic"`
     ——UI 顯示成**確定值**。這正是「把不確定講成確定」。
  2. **部分標註 → 件數整個消失**：若一部分列有 `qty_scope`、而真正 cyclic 的那列沒有，會走進 cyclic 分支
     得到 `(None, None)`：UI 的件數整行不顯示，`unit_mismatches` 也跳過比對——失敗是靜默的。
  3. **`unit_mismatches` 有型別但沒有畫面**：`api.ts` 宣告了、`WritebackPanel` 不渲染、i18n 無對應 key。
     LB 件數與 MOST 投影 Q 不符時，UI 仍平鋪直敘「共 8 件」。對作業者而言，這比 cyclic／inferred 之分更關鍵
     （與 BL-ENG-3 同一類：顯示層沒有分辨資料的語意）。
- **lb-projection reviewer 的建議解（2026-09-21）：不是 422，是「不可判定」。** 422 的既有判準是「格式／值域錯、
  整份不可解讀」（D7 追記）；多列 cyclic 值不一致是**內容矛盾、不是格式錯**，回 422 會讓 IE 連站別／人／
  offline 差異都看不到——把局部不可信放大成整份不可用，與 D6 的 `units_baseline=unavailable`、D2／D7 的降級
  模式相反。LB 自己也是這個哲學（守恆檢查失敗時輸出 `units: null` ＋ WARN，唯讀端點不因資料缺陷整份失敗）。
  具體做法：件數判為不可判定（`units_total=None`，**不得標 `units_source="cyclic"`**），列入 `units_uncomparable`
  並加新 reason（如 `cyclic_conflict`／`partial_scope`）。**一併要修**：`units_uncomparable` 現在只在 MOST
  投影 Q>1 時才列，Q=1 或投影不可用時完全無聲。
- **另一個同源的不同步（2026-09-21 兩席各自指出）**：`LbRowPlacement` 這張正規化表**沒有 `qty_scope` 欄**。
  目前功能正確（`latest` 重新 parse `snap.payload`），但這張表已與 payload 不同步——日後有人改讀 placements
  算件數會無聲拿到錯答案。收斂時一併補欄或在表上標明「件數不得由此表推導」。
- 3 併入 BL-ENG-3 一起處理顯示語意。
- 對應文件：ADR-036 D6、實作書 §2 B4。

## BL-ENG-10 — LB `export_warnings` 尚未消費：MOST 會把「LB 丟掉的列」講成「沒有結果」（**2026-09-22 已消費**）
- **結案說明**：Howard 2026-09-22 給出消費規則後實作（ADR-036 D7／實作書 §2 B4）。丟列不再講成「未排入」——
  缺口保留原本的歸因、加旗標並補一句「也可能是沒送回來的那幾列之一」，頂端講「至多 N 步」；件數被 LB 降級時
  掛在該步驟上並帶 LB 工作項編號；未知 reason 降級為「原因無法辨識」並照常存快照；真機（LB HEAD）驗過三欄在且為空。
- **仍然存在的已知限制**（實作書 §7）：(a) 清單被截到上限時，第 50 筆之後被降級的步驟只會講成「LB 沒給件數」；
  (b) 丟列若只丟掉**已對上**的步驟的其中一列，該步驟會顯示成沒件數或站數偏少，而且不帶旗標（→ BL-ENG-14）。
- 領域：`lb-projection`（回寫消費）
- 狀態：**本輪不做**（Howard 2026-09-21：「LB 這輪還在做 export_warnings，這一輪不要動它，等 LB 的 §8
  定稿我再給你消費規則」）。開票只為留下已查證的事實，不要在拿到消費規則前自行實作。
- 現況（2026-09-21 主 context 於 LB repo 查證；**票面初稿寫錯，此處為更正版**）：LB 正本
  `MOST_INTEGRATION_INPUT_SPEC.md` 已宣告頂層 `export_warnings`「恆存在」（`units_degraded`／
  `dropped_rows`／`truncated`），**而且已經實作**（LB `bb0d340`，文件 `b90c611`；HEAD `1454b05` 上
  `git grep -c export_warnings -- src` 命中 3 檔，`writeback_use_case.py` 會組出並放進回應）。
  初稿寫「全 repo 零命中、尚未實作」是錯的。
  fixture 不帶這個欄位**仍然對**，但理由是 `106bf14` **早於** `bb0d340`，不是 LB 沒做——
  下次 re-vendor 就會開始帶（MOST parser 忽略未知頂層欄位，不會因此壞掉）。
- 影響：MOST 端**完全沒有解析**這個欄位。LB 若丟掉某些列，MOST 會把它們算進 `missing`，UI 講成
  「這一步沒有產線平衡結果」——真相是「LB 有結果、只是被丟掉了」。**合理但錯誤的故事**，
  屬 BL-ENG-3／BL-ENG-9 同一類。
  至於 `units_degraded`：LB 對違反 ADR-008 D3 的列**把 `units` 降成 `null`** 並登記在該清單
  （`writeback_use_case.py` 的 `_units_if_valid`：「Degrade, do not Fail-Fast」），所以 MOST 這邊
  讀到的是「LB 沒給件數」→ 走 `units_uncomparable`／推算退路，**不會顯示一個錯的件數**。
  初稿寫「會被當成正常值顯示」也是錯的——真正的損失是**不知道為什麼沒有件數**。
- 建議做法：等 LB §8 定稿 → Howard 給消費規則 → 解析並在 UI 分辨「沒有結果」與「被丟掉／被降級」，
  同時在實作書 §7 把這條已知限制撤下。
- 對應文件：LB `MOST_INTEGRATION_INPUT_SPEC.md` §8、實作書 §7、ADR-036 D6。

## BL-ENG-11 — `latest` 只按 `fetched_at` 排序、沒有 tiebreaker
- 領域：`lb-projection`（回寫快照）
- 現況（2026-09-22 寫整合測試時撞到）：`lb_writeback_snapshots.fetched_at` 是 `server_default=now()`——
  PostgreSQL 的 `now()` 是**交易開始時間**。同一個交易內存兩筆快照，兩者時間戳完全相同，
  `latest()`、`list_snapshots()`、`_enforce_retention()` 都只按 `fetched_at` 排序，於是「最新」是任意一筆。
- 影響：正式環境每個 HTTP 請求各自一個交易，**目前不會發生**；但整合測試（conftest 外層交易）會，
  而保留策略刪錯一筆就是資料遺失。這是潛在缺陷，不是現在的故障。
- 建議做法：排序加 tiebreaker（例如 `id` 或單調序號），或 `fetched_at` 改由應用端 `clock_timestamp()`／
  `datetime.now()` 給值。三處排序要一起改。
- 本輪處置：整合測試改為每個情境各用一份工序表，繞開而不依賴它。

## BL-ENG-12 — 回寫產線視角把「不屬於這份工序表的 LB 列」畫得跟正常列一樣（標籤 `00000000`）
- 領域：`job-ux`（`WritebackPanel.tsx`）
- 現況（2026-09-22 job-ux reviewer 從截圖發現，**既有行為**、非本輪造成）：`diff.motions` 含 unmatched 的 motion
  （LB 有、MOST 沒有），而步驟標籤查不到時以 id 前 8 碼當標籤——合成 id 就是一整排 `00000000`，旁邊照常顯示
  「排到第 N 站，1 個人做」。不屬於這份工序表的結果看起來跟正常步驟一模一樣。
- 影響：作業者會以為那是這份工序表的步驟；與 BL-ENG-3 同一類（顯示層沒有分辨資料的語意）。
- 建議做法：unmatched 另成一區並講明「產線平衡這份結果裡有 N 個步驟不屬於這份工序表」，或預設收合。

## BL-ENG-13 — 領域守衛的 glob 一寬一漏
- 領域：agent-team（`docs/agent-team/domains.yaml`）
- 現況（2026-09-22 auth-rbac reviewer）：(a) auth-rbac 的 `src/frontend/src/shared/**` 太寬，i18n 資源檔也算進去——
  本輪 auth-rbac 的命中是誤命中；(b) 反過來，`tests/integration/test_outbox_api.py` 等 outbox／RBAC 的整合測試
  **沒有任何 glob 覆蓋**（outbox＝ADR-027 未登記在任何領域），改了它不會觸發任何 logic reviewer。
- 建議做法：auth-rbac 收窄為 `shared/api/**`、`shared/types/**`、`shared/auth/**`；outbox 登記領域並把對應整合測試納入。
  動到 agent 設定，要跑 `check_agent_config.py`。

## BL-ENG-14 — 偵測「已對上的步驟被 LB 丟掉其中一列」
- 領域：`lb-projection`
- 現況（2026-09-22 lb-projection reviewer 的建議解③，本輪未做）：LB 丟掉的列若屬於一個仍有其他列回來的步驟
  （例如工具三列只丟了 cyclic 列），該步驟照樣 matched，只是顯示成「LB 沒給件數」或站數偏少，**而且不帶
  「可能被丟」的旗標**——目前的旗標只加在整步都沒回來的缺口上。
- 建議做法：用 MOST 自己投影出的每步列數（非 general）比對聚合後的 `task_ids` 數，不必用到 LB 的 id（§8 禁止）。
  需要投影提供新資料、diff 新增一類，§8 不要求，屬新能力。
