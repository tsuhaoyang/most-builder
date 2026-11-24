# ADR-038 統一 WI 工作區：12 月底交付計畫與驗收條件

**文件類型：** Roadmap／執行分期與驗收（非規則權威）
**建立日期：** 2026-11-23
**決策邊界：** [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md)（accepted 2026-11-23，D7 於同日修訂）、
[ADR-037](../decisions/ADR-037-ai-service-integration.md)、[ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed）

## 狀態

🔄 執行中。W1（PR #16）、W2（PR #19）、W3（PR #20）已合併；W7a 已合併（PR #21）；W7b 已合併（PR #22）；W4 已合併（PR #23）；W3b 已合併（PR #27）；W5 已合併（PR #28）；標頭匯入按鈕依 Howard 裁決 A 改導工作區（PR 開立中，`feat/header-import-to-workspace`）；W8（區域與距離前端）已合併（PR #30）；W6（移除舊畫面）實作完成，PR 開立中（`feat/w6-remove-legacy-screens`）。W7 拆為 W7a／W7b（2026-11-24，W7a，依審查建議，Howard 授權）。與 ADR-038 衝突時以 ADR-038 為準。

## 工作方式（Howard 2026-11-23）

- 每個 PR 由主 context 開、驗證、合併，不逐一詢問；**只有需要 Howard 決策的事項才停下來問**。主 context 有建議的，照建議做，記在本檔〈決策紀錄〉。
- **合併前必須滿足本檔的驗收條件**（下列共同關卡＋各 PR 的條件）。條件不成立就不合併，修到成立為止；真的做不到，記入〈決策紀錄〉並問 Howard。

## 共同關卡（每個 PR）

| # | 關卡 | 證據 |
|---|---|---|
| G1 | checkpoint：`most-code-reviewer`、受影響領域的 `most-logic-reviewer`、資安審查都沒有阻擋級；建議項處理或記明不處理的理由 | 審查報告 |
| G2 | `pytest tests/unit tests/contract` 全過 | 指令輸出 |
| G3 | 動到 DB／後端：在**拋棄式測試 DB**（照 CI 順序 migrate＋4 支 seed）跑 `pytest tests/integration` 全過。**不連開發庫（5432）** | 指令輸出 |
| G4 | 有 migration：手動驗 upgrade → downgrade → upgrade，以及 downgrade 的拒絕條件 | 指令輸出 |
| G5 | 動到 most_engine／rule-set／level：`scripts/core_logic/run_all.py` 全綠（GM=28／CM=29） | 指令輸出 |
| G6 | 動到前端：`npm run typecheck`、`typecheck:e2e`、`build`、i18n 守衛（`e2e/i18n-hardcoded-zh.spec.ts`）全過；新流程有 e2e | 指令輸出 |
| G7 | 動到 API：`api.d.ts` 由 OpenAPI 重產，前端 typecheck 過 | diff＋輸出 |
| G8 | 動到 docs 或 agent 設定：`docs_check.py`、`check_agent_config.py` 0 error | 指令輸出 |
| G9 | ruff：本 PR 動到的檔案乾淨 | 指令輸出 |
| G10 | GitHub CI 全綠（依賴、前端、後端、端對端）後才合併 | `gh pr checks` |

## 各 PR 驗收條件

### W2：每列距離狀態與完成檢查（後端）
1. migration（加法）：`wi_rows.distance_status`（可空；`confirmed`｜`manual`｜`not_applicable`）、`most_worksheets.distance_check_required`（預設 false）。downgrade 遇到有值的狀態或已開啟的檢查就拒絕。
2. 存檔、編輯區草稿、寫入工時表都能帶 `distance_status`；讀取回傳兩欄；整份存檔未帶該欄時保留既有值；clone 複製兩欄。
3. 經編輯區寫入工時表後，該份 `distance_check_required=true`，之後不會自動關閉。
4. 核准（publish）：開啟檢查時，任一列狀態為空 → 409，錯誤列出缺的列（`seq_no`、`wi_row_id`）；未開啟的工時表行為不變（既有 publish 測試全過）。
5. 測試涵蓋上述每一條，含「舊工時表照舊可核准」。

### W3：單句 AI、整份上傳寫進編輯區（後端）
1. `POST /worksheets/{id}/drafts/from-sentence`：呼叫既有解析（含 AI 與降級），每個 motion 一列草稿；同一句共用 `group_key`；`wi_group` 預設原句（≤200 字）；來源 `ai_service`／`rule_based`；`ai_candidates` 存候選；需 analyst。
2. 整份上傳：parse job 每處理完一列，把結果寫進目標工時表的編輯區（規則解析）。~~批次也走 AI（batch lane）；~~ （2026-11-24，W3，依審查建議，Howard 授權：批次外部 AI 移到 W3b。）AI 不可用時降級為 rule_based 照樣寫入。
3. AI 草稿寫入檢查（取代 W1 的一律拒絕）：每列須 cycle 完整、引擎算得出、engine_gate 無 `engine_reject_*`；不合格 → 拒絕並指出草稿 id。
4. stale：草稿建立後工時表的規則版本改變 → 不能寫入，草稿標示原因、需重新確認。
5. 既有 `nl-draft` 與匯入 submit 行為不變（既有測試全過）。
6. 用假 port 與假 ai_service 測完整流程；**不需要真 ai_service**。

### W3b：批次外部 AI 與 Excel 數量權威（後端；2026-11-24，W3，依審查建議，Howard 授權）
1. `parse_interactive` 的外部路徑只支援單句，且會在呼叫 ai_service 前 commit（ADR-037 D8）；`tick_job` 先改成逐列交易，批次才能走外部 AI（batch lane）。
2. 批次外部 AI 失敗時降級為 rule_based，草稿照樣寫入編輯區；來源標示與單句相同。
3. 同時做 ADR-037 D6：批量只送 description，Excel 數量為權威，歸屬規則預填並逐項審核。
4. tick 內寫草稿目前會持有工時表列鎖到 tick 結束（limit ≤4），改逐列交易後解除。
5. 用假 port 與假 ai_service 測；不需要真 ai_service。順序：W3 之後、W5 之前。

**W3b 驗收對應與已知限制（2026-11-24，W3b，依審查建議，Howard 授權）**：
- 第 1 項：`tick_job` 改為逐列交易。認領後先 commit，每列各自 commit，計數逐列原子遞增。外部時一次只認領 1 列，lease＝`LEASE_SECONDS`＋AI 總時限；AI 回來後鎖住 item 並確認仍是本 worker 的才寫回，被重認領就放棄。API tick 的 `worker_id` 每次加隨機尾碼。
- 第 2 項：批次走外部 AI（路徑 A，`lane=batch`），失敗或額度用完降級 `rule_based`，草稿照寫；降級原因在 `item.last_error.ai`。建立者執行時被降權則以 `rule_based` 完成（建立時仍是 403）。
- 第 3 項：只送 `description`；Excel 數量由 `apply_excel_quantity` 預填 `frequency`，依據在 `parse_snapshot.quantity`，草稿仍 pending（ADR-037 D6 追記）。
- 第 4 項：外部呼叫期間不持有 job 列鎖或工時表列鎖，W3 的已知限制解除。
- 已知限制：批次占用建立者每分鐘額度（30）與全站每日額度，額度用完的列降級、不自動重試；guard 額度是行程內記憶體，API 與 worker 行程各自計；取消只在每列開頭檢查。
- 第 5 項：以假 port 與假 ai_service 測。

### W7a：區域、DSX 座標快照、物件歸區（後端；2026-11-24，W7a，依審查建議，Howard 授權）
1. migration `v2_0054`（加法）：`zone_categories`（6 個內建，admin 可新增）、`sku_zones`、`sku_placement_snapshots`（每 SKU 保留最近 20 份）、`sku_object_zones`（複合 FK 保證同 SKU，RESTRICT；物件座標欄預留）。downgrade 有使用者資料就拒絕。
2. 11 個端點（見 rbac-spec）：讀 viewer、寫 analyst、新增類別 admin、`GET /dsx/objects` analyst。
3. 同步：區域中心取快照中的 DSX `anchor_cm`，沒有時退回 `station_local_cm`，每筆記 `point_source`；快照找不到的綁定物件 → 清空中心並回報；換綁清空；回傳前一份快照。呼叫 DSX 前結束交易。
4. DSX 失敗分開回報：`DSX_DISABLED` 503、`DSX_UNREACHABLE` 502、`DSX_NOT_READY` 409；物件清單連不到回 200＋`available=false`，不回空清單。`ZONE_IN_USE` 409。
5. DSX 回應當不可信輸入：本文 ≤ 2 MB、≤ 2000 筆（超過整份拒絕不截斷）、字串 ≤ 200、座標 |v| ≤ 1000 cm、拒絕重複 id、`station_id` 必填、`placement_revision` 0..2^31−1。
6. 鎖順序先 SKU 再區域；歸區只接受未刪除且啟用的物件；既有 `external_code`／`__to` 綁定與 a3 查詢不動（D7）。
7. 用假 DSX（測試內的 ASGI app）測；**不需要真 DSX**。

### W7b：算距離與建議（後端；2026-11-24，W7a，依審查建議，Howard 授權）
1. 建模政策新增：伸手／走動門檻（預設 70 cm）、人端偏移（預設肩高 140 cm）；工時表記住使用的政策版本。
2. 算距離：`a0`＝人→「從哪裡」（沒有 from 用 object）、`a3`／M＝從哪裡→到哪裡、`a6`＝到哪裡→人（沿用 DSX 現行語句模型）；≤門檻填 `reach_cm`、>門檻填 `foot_cm`；M>75 cm、a6>門檻標「需 IE 裁決」不截斷。
3. 每個結果記錄 `snapshot_id`、`point_source`、使用的門檻、人端偏移、來源（`zone_center`｜`object_coordinate`）。
4. 結果是建議：預填到草稿或列上、不直接寫入 TMU 路徑；確認後 `distance_status=confirmed`。
5. 決定「改動作內容後已 `confirmed` 的距離狀態是否退回」（W2 留待項）。
6. 用假 DSX 測；**不需要真 DSX**。
7. 產出 `docs/architecture/dsx-changes-for-adr-038.md`：DSX 方需要配合或確認的事項（交 Howard 轉給 DSX repo）。須列：`anchor_cm` 是否已含旋轉與人端偏移。

**W7b 完成對應**（2026-11-24，W7b，依審查建議，Howard 授權；migration `v2_0055`，API 見 `api/routes/v2/distance.py`）：
- 第 1 項 ✅：距離設定在 `policy_json["distance"]`，沒有時用凍結的 `DEFAULT_DISTANCE_SETTINGS`；`modeling_policy_defaults` 明確指定新工時表的政策版本；admin 發布新版本；既有工時表沿用自己的版本。
- 第 2 項 ✅：端點與欄位判定如 ADR-038 D5.6 W7b 追記（列上沒有 from 時 a0 與 a3／m3 起點都用 object；用未取整距離）。
- 第 3 項 ✅：`wi_row_distance_suggestions` 記錄 `snapshot_id`、端點出處、門檻、人端偏移與政策版本。
- 第 4 項 ✅：`apply` 列級套用，需 `base_revision` 與 `computed_at`；成功後 `distance_status=confirmed`。
- 第 5 項 ✅：決定「退回」（ADR-038 D6 W7b 追記，取代 W2 的「暫不退回」）。
- 第 6 項 ✅：以假 DSX 測（`tests/integration/test_distance_suggestions.py`、`tests/unit/test_distance_suggest.py`）。
- 第 7 項 ✅：文件已寫；待 DSX 方回覆。
- 已知限制：距離設定沒有「指回舊版」路徑、沒有獨立稽核表、既有工時表不能改用新版本。

~~### W7：區域與自動算距離（後端）~~（2026-11-24，W7a，依審查建議，Howard 授權：已拆為 W7a／W7b，原條目如下保留）

<details><summary>原 W7 條目</summary>

1. migration（加法）：區域類別（固定清單、admin 可新增）、按 SKU 的區域（類別、名稱、DSX 物件 id、中心座標 3D）、按 SKU 的座標快照（DSX `placement_revision`、同步時間、同步者）、按 SKU 的物件歸區（含預留的物件座標）。
2. MOST 代理 DSX `GET /api/v1/objects`（下拉清單）與 `GET /api/v1/placements`（同步）；DSX 連不到、座標未就緒（409）、物件找不到各有明確結果，不偽裝成空清單。
3. 建模政策新增：伸手／走動門檻（預設 70 cm）、人端偏移（預設肩高 140 cm）；工時表記住使用的政策版本。
4. 算距離：a3（從區到區）、M（推拉位移）、a0／a6（人到區）；≤門檻填 `reach_cm`、>門檻填 `foot_cm`；M>75 cm、a6>門檻標「需 IE 裁決」不截斷；每個結果記錄起點、門檻、快照版本、來源（`zone_center`｜`object_coordinate`）。
5. 結果是建議：預填到草稿或列上、不直接寫入 TMU 路徑；確認後 `distance_status=confirmed`。
6. 用假 DSX（測試內的 ASGI app）測；**不需要真 DSX**。
7. 產出 `docs/architecture/dsx-changes-for-adr-038.md`：DSX 方需要配合或確認的事項（交 Howard 轉給 DSX repo）。

</details>

### W4：工作區畫面（前端）
1. 從工時表編輯器改造：編輯區列表（依 WI 分組、來源與狀態標示）、單列與整組確認、修改、刪除、「寫入工時表」。
2. 三種輸入在同一畫面切換：手動、單句 AI（W3 端點）、整份上傳入口（W5 接）。
3. 不再有「採用到編輯器」直接載入 AI cycle 的捷徑。
4. AI 狀態（`GET /wi-ai/status`）與降級訊息；zh-TW／en 文案對稱。
5. 寫入遇到 409：提示重新載入，草稿維持已確認。
6. e2e（mock API）：手動新增→確認→寫入；單句→草稿分組→整組確認→寫入；降級訊息；409 提示。
7. （2026-11-24，W3，依審查建議，Howard 授權，W3 帶來的畫面需求）草稿列顯示 `stale_reason`（`rule_set_changed`｜`import_row_changed`，兩個值要有 zh-TW／en 標籤）、`parse_snapshot.wi_group_truncated`、`parse_snapshot.issues`。`stale_reason=import_row_changed` 時提示「刪除後重新解析」（重新解析不會取代人動過的草稿）。確認「不完整但已被改過」的草稿前，可先乾算引擎提早報錯。處理 409 `DRAFT_INCOMPLETE`、`DRAFT_STALE`。

8. （2026-11-24，W7b，依審查建議，Howard 授權）整份存檔開始帶 `distance_status` 時，要「讀回什麼就帶回什麼」，且不得讓 `confirmed` 的退回規則失效（ADR-038 D6 W7b 追記）；建議未改動的列不帶此欄。存檔後某列的 `distance_status` 被退回為空時，畫面要提示。

**W4 完成對應**（2026-11-24，W4，依審查建議，Howard 授權；純前端，無 migration）：
- 第 1 項 ✅：`drafts/DraftArea.tsx`（分組、來源與狀態標示、單列與整組確認、編輯、刪除、寫入工時表）。
- 第 2 項 ✅（W5 部分待辦）：手動、單句（`drafts/SentenceInput.tsx`）已接；整份上傳入口開既有匯入精靈並先確認，目前直接寫進工時表，W5 改為進編輯區。
- 第 3 項 ✅：`AiDraftPanel`、`aiDraft.store`、`detectLanguage`、`workbench.aiDraft.*` 已刪；`workbench-v3` 的 `ActionModuleWorkspace` 同類路徑由 W6 移除。
- 第 4 項 ✅：AI 狀態與降級文案；zh-TW／en 對稱。
- 第 5 項 ✅：409 版本衝突提示並重新載入、草稿維持已確認；`DRAFT_INCOMPLETE`／`DRAFT_STALE` 標出列。
- 第 6 項 ✅：`src/frontend/e2e/workspace-drafts.spec.ts` 9 個（mock API）。全套 e2e 在 `workers=1` 時 204 passed、13 skipped；並行時有既有的順序依賴（共用 DB）。
- 已知限制：見 ADR-038 D3 W4 追記（即時試算用 active 規則版本、PATCH 無版本欄後者覆蓋、乾算引擎以編輯器試算代替、解析 issues 顯示原始代碼）。

### W5：整份上傳整合進工作區（前端）
1. 匯入改為工作區內的一種輸入；上傳、欄位對應後建 parse job，顯示進度，解析完的列先出現在編輯區。
2. 失敗與需人工檢查的列有標示。
3. e2e（mock API）：上傳→進度→草稿出現→確認→寫入。
4. （2026-11-24，W3，依審查建議，Howard 授權）超長（>2000 字）與解析失敗的 Excel 列不產生草稿，畫面必須列出，並提供「建空白草稿」。
5. 成功的 item 可能帶 `last_error.drafts`（原因：`rule_set_mismatch`、`NotEditable`、`WorksheetNotFound`、`TooManyDrafts`、`already_reviewed`），前端不得當失敗顯示。
6. 建 job 時先驗證目標工時表（存在、draft、編輯區有空位）。

**W5 完成對應**（2026-11-24，W5，依審查建議，Howard 授權；後端加 2 個端點，無 migration）：
- 第 1 項 ✅：`drafts/UploadInput.tsx`＋`ImportModal` 的 `drafts` 模式：上傳綁工時表→欄位對應→建 job→每 3 秒輪詢、每處理一列重讀編輯區。進行中的 job id 記在 `sessionStorage`，job 不存在時自動清除。
- 第 2 項 ✅：`GET /imports/{id}/parse-jobs/{job_id}/items` 列出每列結果，畫面標示沒產生草稿的列。
- 第 3 項 ✅：`workspace-drafts.spec.ts` 加上傳流程（mock API）。
- 第 4 項 ✅：超長、解析失敗、寫不進去的列列出，「建空白草稿」＝`POST /worksheets/{id}/drafts/blank-from-import`（`complete=false`，補齊前 `DRAFT_INCOMPLETE`）。
- 第 5 項 ✅：`last_error.drafts` 不當失敗顯示，原因列出。
- 第 6 項 ✅：建 job 前驗證：工時表不存在 404、不可編輯 409、編輯區滿 422、規則版本不同 409（`field=rule_set_code`）。
- ~~未完成：標頭「匯入 Excel」按鈕維持舊流程~~ → 2026-11-24 Howard 裁決 A：標頭按鈕打開工作區上傳，舊流程從畫面移除，範本採用見 BL-ENG-21。
- 已知限制：`has_drafts` 是「現在還有草稿」，刪掉草稿後該列會再列出；items 無分頁；`drafts` 模式的 `/map` 仍算範本比對但不顯示。

### W8：區域與距離畫面（前端）
1. SKU 的區域設定（類別、名稱、從 DSX 下拉選物件）與「從 DSX 同步座標」（顯示目標 SKU 與 DSX 版本）。
2. 「本份 WI 用到的物件」清單逐一歸區；按「算距離」後各列出現建議值與來源，可逐列或整組確認。
3. 「需 IE 裁決」與 DSX 連不到等狀態有明確顯示。
4. 每列可標「此動作無距離」或手動值；核准時缺狀態的錯誤能指到該列。
5. e2e（mock API）：設區域→同步→歸區→算距離→確認→核准通過；缺狀態時核准被擋。

6. （2026-11-24，W7a，依審查建議，Howard 授權，W7a 帶來的待辦）同步時提示「與上次站別／版本不同」（用回應附的前一份快照比對 `dsx_station_id`、`placement_revision`）。
7. （同上）同一 DSX 物件被多個區域綁定時提示。
8. （同上，後續）快照回復功能。W7a 只保留最近 20 份，沒有回復入口。
9. （2026-11-24，W7b，依審查建議，Howard 授權，W7b 帶來的待辦）套用失敗（409 `DISTANCE_NOT_APPLICABLE`）時依回應列出每列原因（`no_suggestion`、`marked_not_applicable`、`needs_ie`、`unavailable` 與其原因）；`DISTANCE_SUGGESTION_CHANGED` 時提示重新計算再確認。
10. （同上，後續）重新同步 DSX 後，提示「已確認的距離與新座標不同」（已 `confirmed` 的列不自動退回）。
11. （同上）顯示與修改距離設定（admin）；說明只影響之後新建的工時表。

**完成狀態（2026-11-24，W8，依審查建議，Howard 授權）**：實作在 `src/frontend/src/features/wi-workbench/distance/{api.ts,DistancePanel.tsx}`，掛在 WiWorkbench；核准失敗時 CasesPage 列出缺距離狀態的 #seq_no；e2e 為 `src/frontend/e2e/workspace-distance.spec.ts`（5 例）。
- 第 1–7、9、11 項 ✅。
- 第 10 項 ⚠️ 部分完成：重新同步後 DSX `placement_revision` 變了會提示「已確認的距離不會自動改，請重新算距離比對」，但沒有逐列比對已確認值與新座標。
- 第 8 項（快照回復）未做，仍屬後續。
- 行為：面板在工時表 `distance_check_required=true` 時預設展開、否則收起，標頭顯示未標列數；只有整列每格都是 `suggested` 的列可勾選套用；逐列可標「此動作無距離」或「手動值」，按儲存才寫回；沒有「清除標示」按鈕（後端也沒有此語意需求）。
- 前端不變量：整份存檔只對使用者在畫面上改過距離狀態的列帶 `distance_status`（store 的 `distanceStatusChanged`），其餘列不帶；每列都帶會繞過 W7b 的「改了距離輸入就退回」。

### W6：移除舊畫面（前端）
1. 側欄移除 MOST 工作台與 WI 專案；工時表編輯器移除「從 WI 庫插入」；對應 e2e 移除或改寫。
2. 後端路由與資料不動（資料已備份：`data/backups/adr038-legacy-library-20261123-211312/`）。
3. 全套 e2e 過。

**完成狀態（2026-11-24，W6，依審查建議，Howard 授權）**：實作完成，PR 開立中（`feat/w6-remove-legacy-screens`）。
- 側欄移除「MOST 工作台」與「WI 專案」；刪除 `features/workbench-v3/` 與 `features/wi-project/WISetBuilderPage.tsx`；工時表編輯器移除「從 WI 庫插入」（ADR-022 E-4）。
- DSX 元件（`DsxA3Suggestion`、`dsxA3Distance`、`DsxUiViewer`、`dsxUiUrl`）搬到 `features/wi-workbench/dsx/`，仍在使用。
- 動作範本（`motion_templates`）管理入口保留在主數據管理的「動作模組範本」分頁（`features/dictionaries`）。
- 後端 `/motion-modules`、`/wi-sets`、`rows/from-module`、`imports/{id}/submit` 與資料保留，沒有畫面入口。
- e2e 刪除 `workbench-nl-*.spec.ts`、`support/workbenchNlMocks.ts`、`wi-set-add.spec.ts`、smoke 的工作台測試，以及 `ux-compliance.spec.ts` 的 §B-01、C-01-1、§E-04、G-03-2d、G-03-4、G-03-5（ux-compliance 現為 42 個 test）。
- 只被已刪畫面使用的 i18n 鍵（`workbench.wiOutline`、`inspector`、`slot`、`nl`、`wiSet` 等）暫留，清理排 BL-ENG-22；`workbench.wiEditor` 的插入相關鍵已在本 PR 刪。

## 整體驗收（12 月底）

在開發環境（`make up` 起的完整服務）以一份新 SKU 走完：
1. 設區域、綁 DSX 物件、同步座標（真 DSX；**需要 DSX 有在跑並已載入 3D 場景**）。
2. 手動建一列；單句 AI 一句；上傳一份 Excel（**真 ai_service：需 Howard 安排**，屆時一併做 ADR-037 的 30 句延遲量測）。
3. 在編輯區審核、整組確認、寫入工時表。
4. 物件歸區、算距離、確認；核准通過。
5. 驗證：TMU 由引擎算、來源標示正確、缺距離時核准被擋、viewer 只能看不能改、AI 關閉時全流程照樣可用（rule_based）。

## 決策紀錄（主 context 依建議自行決定的事項）

| 日期 | PR | 事項 | 決定與理由 |
|---|---|---|---|
| 2026-11-23 | — | 驗收方式 | 本檔；CI 全綠＋checkpoint 無阻擋級＋各 PR 條件成立才合併 |
| 2026-11-23 | W2 | 開關由誰打開（審查 A） | 目前只有 `drafts/commit` 打開；W4 上線時，在工作區建立的新工時表一開始就設 true。匯入 submit 與模組實體化不打開（匯入改走編輯區後自然涵蓋）。理由：D6 只套用新工作區的工時表，舊流程不受影響 |
| 2026-11-23 | W2 | 改了動作內容，已 confirmed 的狀態要不要退回（審查 B） | 暫不退回，留到 W7 自動算距離時一併決定。理由：W2 還沒有自動距離，只有人工標示 |
| 2026-11-23 | W2 | 核准時 level 與距離錯誤的順序（審查 C） | 維持先 level 再距離。理由：體驗取捨，不影響正確性；前端可在 W8 一次顯示兩者 |
| 2026-11-23 | W2 | 核准與並行存檔的競態（資安審查） | 核准先鎖工時表列；存檔與編輯區寫入拿到列鎖後再確認版本仍是 draft。理由：否則核准可能看到舊列而放行 |
| 2026-11-24 | W3 | 可接受的 motion（ADR-037 D3 在工作區） | 人按確認＝人工採用（取代「人寫入 chosen」，`chosen` 仍為 null 只供顯示）；寫入時 `compute_rows_for_save` 重算，等價 engine_gate（唯一拒絕條件是 `compute_cycle` 丟 `SequenceError`）。`parse_snapshot.complete` 只是提示：不完整且 cycle 未被改 → 409 `DRAFT_INCOMPLETE`。`rule_based` 同規則；W1 的 Fail-Fast 移除。理由：ADR-038 D3 已規定確認時畫面值才是決定值 |
| 2026-11-24 | W3 | stale 條件 | 只看 `source_rule_set_id`≠工時表 `default_rule_set_id`、Excel 列 `input_hash` 變了或被刪；409 `DRAFT_STALE`，整筆作廢，另開交易退回 pending 並記 `stale_reason`。「引用列被改」不適用（草稿追加表尾），一般存檔不算過期 |
| 2026-11-24 | W3 | provenance | `ai_service`→`ai_external`；Excel 列→`imported`（帶 `source_import_id`）；其餘→`manual`。修訂 W1 追記 |
| 2026-11-24 | W3 | 拆出 W3b | 批次外部 AI 與 Excel 數量權威移到 W3b，排在 W5 之前。理由：`parse_interactive` 外部路徑只支援單句且呼叫前會 commit，`tick_job` 要先改逐列交易；W3 驗收第 2 項「批次也走 AI」隨之移動 |
| 2026-11-24 | W3 | 重新解析同一 Excel 列 | 取代沒人動過的 pending 草稿；已確認、寫入或改過的不動、也不追加。理由：避免覆蓋人的工作與重複列 |
| 2026-11-24 | W3 | 超長與解析失敗的 Excel 列 | 不產生草稿；W5 畫面必須列出並提供「建空白草稿」。理由：超長列不外送（`MAX_PARSE_TEXT_CHARS`），失敗列沒有可放的 cycle |
| 2026-11-24 | W3 | job 規則版本與工時表不同 | 不寫草稿，原因記在 `item.last_error.drafts`，job 照跑。理由：用別的規則版本算的 cycle 進編輯區，寫入時才重算失敗，也判斷不出過期 |
| 2026-11-24 | W3 | 已知限制：列鎖時間 | tick 內寫草稿會持有工時表列鎖到 tick 結束（limit ≤4）；W3b 改逐列交易時一併解決 |
| 2026-11-24 | W3b | 批次外部 AI 走路徑 A，不做路徑 B（flow）（2026-11-24，W3b，依審查建議，Howard 授權） | 整份上傳逐句走 `lane=batch`；路徑 B 延後，需求清單記在 ai-service-integration-plan〈路徑 B（延後）〉。理由：重用 guard／mapper／plan adapter／快取／run 紀錄；MOST interactive 1＋batch 1＝ai_service 並行 2，429 很少 |
| 2026-11-24 | W3b | 持工具時數量預填 `frequency`，不走 `repeat_count` | 暫不走 QuantityPolicyV2 的 `repeat_count`，一律預填 `frequency`；出處記在 `parse_snapshot.quantity`，不用 `quantity_source` 欄。理由：TMU 中性；LB 投影形狀差異留待後續 |
| 2026-11-24 | W3b | Excel 數量規則順序與無效值 | 規則 3（同物件同動作類型剛好 N 個）排在規則 1 之前，避免 N²；被修飾物件＝數量詞後 4 字內、遇標點停；「次」與 x N 不綁物件；認不得的「數字＋量詞」、Excel＝1 但句中非 1、Excel 非正整數或 >10000 都走規則 4。與 `import_service.submit`（≤0 設 1、接受 2.5）不同，W5 改走編輯區後統一 |
| 2026-11-24 | W3b | 批次額度限制 | 批次與單句共用建立者每分鐘 30 與全站每日額度；用完的列降級 `rule_based`，不自動重試；guard 額度為行程內記憶體，API 與 worker 各自計；取消只在每列開頭檢查。理由：先讓功能打通（同 BL-ENG-15／16） |
| 2026-11-24 | W3b | W3 已知限制：列鎖時間 已解除 | 逐列交易後外部呼叫與草稿寫入不再持有 job 列鎖或工時表列鎖 |
| 2026-11-24 | W7 | 拆成 W7a／W7b（2026-11-24，W7a，依審查建議，Howard 授權） | W7a：區域類別、區域、DSX 物件清單代理、同步快照、物件歸區、這份 WI 用到的物件。W7b：建模政策、算距離與建議、`distance_status=confirmed`、DSX 配合文件。理由：資料與同步可先獨立審查，算距離依賴其結果；驗收條件隨之拆開 |
| 2026-11-24 | W7a | 區域中心取哪個點 | 取 DSX `anchor_cm`（取放錨點後的量測點），沒有才退回 `station_local_cm`，每筆記 `point_source`。理由：距離要量到手會去的地方；`anchor_cm` 是否已含旋轉與人端偏移需 DSX 確認（W7b 文件列出） |
| 2026-11-24 | W7a | DSX 回應超過筆數上限 | 整份拒絕、不截斷（2000 筆、本文 2 MB）。理由：截斷會讓快照靜默缺物件，距離算錯而看不出來 |
| 2026-11-24 | W7a | 鎖順序 | 一律先鎖 SKU 再鎖區域。理由：避免同步、刪除、歸區互相死結 |
| 2026-11-24 | W7b | a0／a3／M／a6 的起訖點 | a0＝人→「從哪裡」（沒有 from 用 object）；a3／M＝從哪裡→到哪裡；a6＝到哪裡→人。沿用 DSX 現行語句模型（其 schema 註解 a0=人→從哪裡、a6=到哪裡→人）；結果記 `snapshot_id`、`point_source`、門檻、人端偏移 |
| 2026-11-24 | W7b | 〈W2 留待 W7〉改動作內容是否退回 `confirmed` | 在 W7b 決定（有自動距離後才有依據） |
| 2026-11-24 | W8 | W7a 帶來的待辦 | 同步時提示站別／版本不同、快照回復功能（後續）、同一 DSX 物件被多個區域綁定時提示 |
| 2026-11-24 | W7b | 列上沒有「從哪裡」時的起點 | a0 與 a3／m3 的起點都用 object（審查建議保留）。理由：沿用 DSX 現行語句模型，句子沒有「從」時物件就是起點 |
| 2026-11-24 | W7b | 〈W2 留待 W7〉改動作內容是否退回 `confirmed`（取代 W2「暫不退回」） | 退回：整份存檔沒帶 `distance_status`、舊值 `confirmed` 且 `distance_inputs` 有任何不同 → 退回未標示；`manual`／`not_applicable` 不動，明確帶值以帶的為準。重新同步 DSX 不自動退回（符合 D5.4）。理由：確認的是那組距離，內容變了確認就不成立 |
| 2026-11-24 | W7b | 套用粒度 | 列級，不做格位級部分套用；全部格位 `suggested` 才套用，並要帶 `computed_at`。理由：部分套用會讓一列的距離一半是建議、一半是舊值，卻標成 `confirmed` |
| 2026-11-24 | W7b | 欄位判定用未取整距離 | 比門檻與 75 cm 時不先取整；`needs_ie`／`unavailable` 不寫入、不截斷（ADR-031 I5） |
| 2026-11-24 | W7b | 距離設定放哪、誰能改 | 放建模政策 `policy_json["distance"]`；沒有時用凍結的 `DEFAULT_DISTANCE_SETTINGS`；admin 發布新版本；新工時表的版本由 `modeling_policy_defaults` 明確指定（種 V1，符合 R2a）。理由：既有工時表的距離算法不能被悄悄改變 |
| 2026-11-24 | W7b | 已知限制（不處理） | 沒有指回舊版的路徑、沒有獨立稽核表（版本列與指標有 created_by／published_by／set_by／set_at）、既有工時表不能改用新版本 |
| 2026-11-24 | W7b | `wi_row_id` 不設 FK | 整份存檔會刪除重建 `wi_rows`，有 FK 會連帶刪掉建議；讀取時過濾、計算時清除孤兒 |
| 2026-11-24 | W7b | DSX 配合文件 | 寫成 `docs/architecture/dsx-changes-for-adr-038.md`，由 Howard 轉交 DSX repo；ADR-038 D5.4 的「路徑待定」改指向它 |
| 2026-11-24 | W4 | 手動列要不要確認（審查） | 要：手動列進編輯區後也要確認再寫入，與 AI、匯入一致。ADR-038 D2 追記澄清「確認」就是使用者那一個點擊，沒有另外的審核者 |
| 2026-11-24 | W4 | 既有工時表列怎麼改（審查） | 仍可在表上直接修改、排序、刪除後整份存檔。D3 的範圍是新產生的內容 |
| 2026-11-24 | W4 | 學習迴圈（nl-draft review 事件）（審查） | 暫停：工作區不再送。後續由後端在 `commit_drafts` 以 `ai_parse_run_id` 與最終 content 產生，前端不補送；開 BL-ENG-20（docs/BACKLOG.md） |
| 2026-11-24 | W4 | W4～W5 間整份上傳（審查） | 仍直接寫工時表、不經編輯區、不開距離檢查開關；入口文案明講並先確認。W5 改進編輯區 |
| 2026-11-24 | W4 | 編輯草稿不改格位（審查） | 原封保留草稿 cycle，不重新產生；避免改動 AI 內容形狀，也避免繞過後端 `DRAFT_INCOMPLETE` 的「沒人補過」判斷 |
| 2026-11-24 | W4 | 已知限制（審查，接受） | 即時試算用 active 規則版本、寫入以工時表規則版本重算；PATCH 無版本欄後者覆蓋；`DRAFT_INCOMPLETE` 乾算以編輯器試算代替；parse issues 顯示原始代碼。e2e 並行順序依賴為既有問題，以 `workers=1` 驗證 |
| 2026-11-24 | W3b | W3b 合併 | PR #27 已合併 |
| 2026-11-24 | W5 | 工作區上傳沒有範本採用面板（審查） | 不做。解析器本身仍參考範本；範本採用留在舊流程，去留見下列「標頭匯入按鈕」 |
| 2026-11-24 | W5 | 建 job 前驗目標工時表（審查） | 不存在 404、不可編輯 409、編輯區滿 422、規則版本不同 409；理由：不讓整批跑完才發現寫不進去。建立後才變的仍走 `last_error.drafts` |
| 2026-11-24 | W5 | 沒產生草稿的列（審查） | 新增 items 端點與 `blank-from-import`；空白草稿 `complete=false`，補齊前 `DRAFT_INCOMPLETE`，納入過期判斷。理由：W3 已定「超長與失敗列畫面必須列出並可建空白草稿」 |
| 2026-11-24 | W5 | **標頭「匯入 Excel」按鈕：待 Howard 裁決** | 審查建議 **A**：標頭按鈕改導到工作區上傳、舊流程從畫面移除、範本採用搬進工作區另開票。**B** 先把範本採用搬進工作區；**C** 維持到 W6。裁決前這條路仍繞過編輯區與距離檢查開關（ADR-038 D6） |
| 2026-11-24 | W5 | 已知限制（審查，接受） | `has_drafts` 是「現在還有草稿」；items 無分頁（受匯入列數上限）；`drafts` 模式 `/map` 仍算範本比對但不顯示 |
| 2026-11-24 | W5 後 | 標頭「匯入 Excel」按鈕（Howard 裁決 A） | 打開工作區的整份上傳；舊的範本採用＋直接寫工時表沒有畫面入口（程式與端點保留），D10 e2e 移除；範本採用搬進工作區排入 BL-ENG-21 |
| 2026-11-24 | W8 | 距離面板預設展開條件（2026-11-24，W8，依審查建議，Howard 授權） | 工時表 `distance_check_required=true` 時預設展開，否則收起；標頭顯示未標列數。理由：只有已開距離檢查的工時表才會被核准擋，其餘不打擾 |
| 2026-11-24 | W8 | 前端送哪些列的 `distance_status`（2026-11-24，W8，依審查建議，Howard 授權） | 整份存檔只對使用者改過距離狀態的列帶（store `distanceStatusChanged`），其餘不帶。理由：每列都帶會讓後端視為「明確帶值」，繞過 W7b「改了距離輸入就退回未標示」 |
| 2026-11-24 | W6 | 移除舊畫面的範圍與保留項（2026-11-24，W6，依審查建議，Howard 授權） | 刪 `workbench-v3`、`WISetBuilderPage`、「從 WI 庫插入」與對應 e2e；DSX 元件搬到 `wi-workbench/dsx/`；動作範本管理入口留在「動作模組範本」分頁；後端路由與資料不動；未用 i18n 鍵暫留、排 BL-ENG-22。理由：D4 只移畫面，`motion_templates` 仍供匯入比對與規則解析；i18n 清理與畫面移除分開，降低本 PR 風險 |
