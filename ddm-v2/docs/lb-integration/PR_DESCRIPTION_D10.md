implements ADR-035 D10: Level System 作業版 (job-oriented UX) — two-view, one store

在已落地的 LB 投影層（WP0–WP12）之上，為 Level System 加一層**使用者語言**的作業版 UI：
一般使用者只看「作業／步驟／順序／四個是非題」，不碰 sub／cub／wcub／segment／pin／general／
merge_lock 等模型詞彙。作業視圖是對既有 store 的**反投影**（純函式），動作寫回同一 store；
IE 詞彙檢視保留為「進階檢視」。**不接 LLM、不做關鍵字猜測、不移植原型 engine.js**。

分支：`feature/lb-projection`（D10 commit 範圍 `08f59e7`..`3fef07e`）。
權威順序：`MOST_LB_DATA_CONTRACT_SPEC` ＞ ADR-035 ＞ 作業版實作書 ＞ 程式碼。

---

## WP 對照（每組一 commit）

| WP | 內容 | commit |
|---|---|---|
| B1 | `wi_rows.wi_group`（作業名）全路徑：migration v2_0047、model、schema（max200 strip→None）、4 輸入路徑、read/clone/hash、測試 | `08f59e7` |
| F1 | hydrate 還原 9 個 lb_tags + 同 chain level 統一（I-1）+ `Row.wiGroup` + `savePayload` 抽出 | (F1) |
| B4 | `report.py`（build_report）+ `hints.py`（§7.2 4 規則）+ `ProjectionError.params` + `rows[]` 摘要 | (B4) |
| B4b | hints Pattern A episode 狀態機（取代錯誤的 by_tool 分組）+ 黃金快照鎖定 | (B4b) |
| fix | `fix(worksheet): serialize version_no allocation per SKU with advisory lock`（clone 並發競態，非 D10） | (concurrency) |
| B3+B5 | preview 乾跑端點 + lb-report 走 build_report + `compute_rows_for_save` 抽出（byte-identical） | (B3+B5) |
| F2/F2b | `jobsModel/jobs/jobsActions/layers.ts` 反投影與 A.2 全動作（純邏輯，19 測試；golden→11 作業） | (F2) |
| B7 | `machine_unattended` 三態（NULL/true/false）migration v2_0048 + 5 對稱落點 + mapper role_type + hints | (B7) |
| F3–F6 | `LevelSystem`（薄殼 jobs\|advanced）/`JobsShell`/`JobsFlow`/`JobDrawer`/`Notices`/`notices.ts`/`LineView`/`DevGrid`/`AdvancedView`（WP12 搬移）+ 預覽 hook + 視圖切換 | (F3–F6) |
| F9 | 黃金複本 DoD-1 + UI e2e + 4 截圖 | `3ef92c2`+`bf849fe` |
| F7 | 四輸入路徑帶 `wi_group`（工時表作業欄+datalist、AI 草稿 sourceText≤80、作業大綱、Excel 匯入欄） | `2453119` |
| F8 | i18n zh-TW/en 全字串（§6）+ plainDiag 34 碼覆蓋測試 | `49d02c1` |
| docs | §11 七處加法同步 + DOC_REGISTRY | `3fef07e` |

---

## 兩個真實後端錯誤（本輪發現並修正）

1. **clone 漏帶 9 個 LB tag 欄（B7 發現）**：`worksheet_service.clone` 的 LevelEntry 複製只帶了部分欄，
   遺漏全部 9 個 LB tag 欄（WP1 起就存在的缺口）。另存新檔會靜默丟掉 offline/segment/pin/general/
   wcub/merge_lock/machine_unattended 等標註。已修為複製全 9 欄，加 3-state roundtrip 測試。
2. **adapter `repeat_counts` 硬寫空 dict（F9 發現）**：`adapter._build_projection_row` 的 `repeat_counts`
   一直是 `{}`（WP2「結構搬運」佔位未完成）。導致 DB／save-payload 投影路徑找不到重複區塊 R，
   工具列 repeat 的 motion 被投影成 N=1（quantity/qty_scope/adjustable 全錯）——只有 fixture 路徑對。
   已修為從 `slot_inputs`（g2/m3/x4/i5/p5 的 repeat_count）推導。golden 單元、adapter-equiv（兩路徑
   一致）皆綠。**DoD-1 的 electric_driver 三列 Q=8 就是靠這個修正才對。**

兩者皆為既有缺陷、非 D10 新增；因作業版 golden 複本走真實 save→read 路徑才暴露出來。

---

## 測試數字（本輪總驗）

- `PYTHONPATH=src pytest tests/unit -q` → **1669 passed**（unit 與 integration 有同名 `test_search.py`，**分開跑**）。
- `PYTHONPATH=src pytest tests/integration -q` → **616 passed, 1 skipped, 1 failed**。
  唯一 failed＝`test_outbox_api.py::test_claim_pending_and_mark_published`——**pre-existing，與 D10 無關**：
  已驗證它在 D10 之前的 base commit（`2321f5e`）以相同方式失敗，且不觸及 lb_projection／worksheet／
  level 任何路徑（outbox event claim/publish）。已回報 Howard，out of scope。
- `python3 scripts/core_logic/run_all.py` → **✅ 全部通過**（引擎黃金值全程未動）。
- 前端 `npm run typecheck && npm run typecheck:e2e && npm run build` → **全通過**。
- Playwright e2e（dev server，`__ddmTest` hook）：`level-jobs-golden`（DoD-1）、`level-jobs-ui`、
  `level-jobs-screenshot`、`level-jobs-f7`、`level-jobs-logic`（19）、`level-hydrate-tags`、
  `wp12-lb-tags`、`level-jobs-plaindiag` → **全綠**（27 併跑 + 純邏輯）。
- i18n 守衛：`i18n-review`（zh-TW/en 對稱）、`i18n-hardcoded-zh`、`level-jobs-plaindiag`（34 碼）→ 綠。
- `ruff check` D10 觸碰的後端檔乾淨（repo 另有 44 個 pre-existing 錯誤在未觸碰檔——已回報，out of scope）。

---

## DoD 對照

- **DoD-1（黃金複本逐欄相等）✅**：`e2e/support/goldenReplica.ts` 以真實 CycleIn 建 24 列，對照
  `server_node_worksheet.json` 結構（seq_kind/tool/frequency/repeat 格位/x_seconds/level/lb_tags）；
  存→lb-csv 與 `server_node_tasks.expected.csv` **21 個語意欄逐欄相等**，`tasks_out==34`、`errors==[]`。
  排除 `duration`（複本 TMU 不同，§8.3）、`divisible`（§3.2）、`action`（複本敘述由不同 MOST 內容產）、
  `source_wi_row_id`（複本 UUID）。
- **DoD-2 反投影無損（I-4）✅**：`jobsFromStore` + `derive()` 往返；`level-jobs-logic` 19 測試含 I-1/I-2/I-3。
- **DoD-3 作業版純確定性（無 LLM）✅**：`jobs.ts`/`notices.ts`/`hints.py` 皆純規則；原型關鍵字規則未進正式碼；
  frontend-ux-spec §8 規則 11 明列。
- **DoD-4 i18n 全目錄 ✅**：§6 全 key 兩語系；34 plain 碼對稱；Widen typecheck + guard 測試綠。
- **DoD-5 四輸入路徑帶作業名 ✅**：F7（工時表欄/AI 草稿/作業大綱/Excel 匯入）。
- **DoD-6 截圖 ✅**：`level-jobs-flow.png`/`-drawer.png`/`-line.png`（zh-TW）+ `-flow.en.png`，皆 11 作業載入狀態。

---

## 待 User 過目

- **黃金 hints 快照** `server_node_hints.expected.json` = 3 條 `H_TOOL_DECOMPOSED`（scanner {4,6}／
  electric_driver {9}／torque_driver {13,17}）；machine 三列已回答故無 `H_MACHINE_TIME`。首次產出，請過目後鎖。
- **DoD-1 排除 `action`/`source_wi_row_id`**：§8.3 只寫排除 duration/divisible，但複本是不同 worksheet，
  敘述（narrative-derived `action`）與 UUID 本就不同。已在 spec 逐欄比對排除並註明理由——若 User 認為
  應改用固定 UUID／敘述使複本 100% 位元相等，請裁決（目前判斷 21 個語意欄相等已足以證明作業版正確）。
