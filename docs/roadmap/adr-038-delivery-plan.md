# ADR-038 統一 WI 工作區：12 月底交付計畫與驗收條件

**文件類型：** Roadmap／執行分期與驗收（非規則權威）
**建立日期：** 2026-11-23
**決策邊界：** [ADR-038](../decisions/ADR-038-unified-wi-workspace-and-two-stage-distance.md)（accepted 2026-11-23，D7 於同日修訂）、
[ADR-037](../decisions/ADR-037-ai-service-integration.md)、[ADR-031](../decisions/ADR-031-spatial-layout-and-distance-acquisition.md)（proposed）

## 狀態

🔄 執行中。W1（PR #16）、W2（PR #19）已合併；W3 審查完成、PR 開立中（`feat/w3-drafts-from-ai`）。與 ADR-038 衝突時以 ADR-038 為準。

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

### W7：區域與自動算距離（後端）
1. migration（加法）：區域類別（固定清單、admin 可新增）、按 SKU 的區域（類別、名稱、DSX 物件 id、中心座標 3D）、按 SKU 的座標快照（DSX `placement_revision`、同步時間、同步者）、按 SKU 的物件歸區（含預留的物件座標）。
2. MOST 代理 DSX `GET /api/v1/objects`（下拉清單）與 `GET /api/v1/placements`（同步）；DSX 連不到、座標未就緒（409）、物件找不到各有明確結果，不偽裝成空清單。
3. 建模政策新增：伸手／走動門檻（預設 70 cm）、人端偏移（預設肩高 140 cm）；工時表記住使用的政策版本。
4. 算距離：a3（從區到區）、M（推拉位移）、a0／a6（人到區）；≤門檻填 `reach_cm`、>門檻填 `foot_cm`；M>75 cm、a6>門檻標「需 IE 裁決」不截斷；每個結果記錄起點、門檻、快照版本、來源（`zone_center`｜`object_coordinate`）。
5. 結果是建議：預填到草稿或列上、不直接寫入 TMU 路徑；確認後 `distance_status=confirmed`。
6. 用假 DSX（測試內的 ASGI app）測；**不需要真 DSX**。
7. 產出 `docs/architecture/dsx-changes-for-adr-038.md`：DSX 方需要配合或確認的事項（交 Howard 轉給 DSX repo）。

### W4：工作區畫面（前端）
1. 從工時表編輯器改造：編輯區列表（依 WI 分組、來源與狀態標示）、單列與整組確認、修改、刪除、「寫入工時表」。
2. 三種輸入在同一畫面切換：手動、單句 AI（W3 端點）、整份上傳入口（W5 接）。
3. 不再有「採用到編輯器」直接載入 AI cycle 的捷徑。
4. AI 狀態（`GET /wi-ai/status`）與降級訊息；zh-TW／en 文案對稱。
5. 寫入遇到 409：提示重新載入，草稿維持已確認。
6. e2e（mock API）：手動新增→確認→寫入；單句→草稿分組→整組確認→寫入；降級訊息；409 提示。
7. （2026-11-24，W3，依審查建議，Howard 授權，W3 帶來的畫面需求）草稿列顯示 `stale_reason`（`rule_set_changed`｜`import_row_changed`，兩個值要有 zh-TW／en 標籤）、`parse_snapshot.wi_group_truncated`、`parse_snapshot.issues`。`stale_reason=import_row_changed` 時提示「刪除後重新解析」（重新解析不會取代人動過的草稿）。確認「不完整但已被改過」的草稿前，可先乾算引擎提早報錯。處理 409 `DRAFT_INCOMPLETE`、`DRAFT_STALE`。

### W5：整份上傳整合進工作區（前端）
1. 匯入改為工作區內的一種輸入；上傳、欄位對應後建 parse job，顯示進度，解析完的列先出現在編輯區。
2. 失敗與需人工檢查的列有標示。
3. e2e（mock API）：上傳→進度→草稿出現→確認→寫入。
4. （2026-11-24，W3，依審查建議，Howard 授權）超長（>2000 字）與解析失敗的 Excel 列不產生草稿，畫面必須列出，並提供「建空白草稿」。
5. 成功的 item 可能帶 `last_error.drafts`（原因：`rule_set_mismatch`、`NotEditable`、`WorksheetNotFound`、`TooManyDrafts`、`already_reviewed`），前端不得當失敗顯示。
6. 建 job 時先驗證目標工時表（存在、draft、編輯區有空位）。

### W8：區域與距離畫面（前端）
1. SKU 的區域設定（類別、名稱、從 DSX 下拉選物件）與「從 DSX 同步座標」（顯示目標 SKU 與 DSX 版本）。
2. 「本份 WI 用到的物件」清單逐一歸區；按「算距離」後各列出現建議值與來源，可逐列或整組確認。
3. 「需 IE 裁決」與 DSX 連不到等狀態有明確顯示。
4. 每列可標「此動作無距離」或手動值；核准時缺狀態的錯誤能指到該列。
5. e2e（mock API）：設區域→同步→歸區→算距離→確認→核准通過；缺狀態時核准被擋。

### W6：移除舊畫面（前端）
1. 側欄移除 MOST 工作台與 WI 專案；工時表編輯器移除「從 WI 庫插入」；對應 e2e 移除或改寫。
2. 後端路由與資料不動（資料已備份：`data/backups/adr038-legacy-library-20261123-211312/`）。
3. 全套 e2e 過。

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
