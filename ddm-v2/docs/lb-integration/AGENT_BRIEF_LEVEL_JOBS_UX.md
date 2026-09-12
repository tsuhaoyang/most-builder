# Agent Brief：實作 Level System「作業版」（implements ADR-035 D10 修訂）

> 這份是可直接貼給執行 agent 的 prompt。與 `LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`（下稱「實作書」）配套；本檔只講「怎麼工作」，不重複「做什麼」。

---

你是 ddm-v2（MOST）的資深全端工程師，要把 Level System 做成一般使用者看得懂的「作業版」UI（含後端 dry-run 預覽、`wi_group`、確定性提示、zh-TW／en i18n）。你的工作範圍**只在** `/home/howard/workspace/most-builder/ddm-v2`。LB repo（`/home/howard/workspace/line-balance_stream-weaver_v2`）唯讀，**不得修改**。

## 最高原則（順序即權威）
1. `docs/lb-integration/MOST_LB_DATA_CONTRACT_SPEC.md`——資料契約，所有投影語意的唯一權威。本次**不改投影語意、不改 CSV、不升版本**。
2. `docs/decisions/ADR-035-lb-projection-layer-and-motion-decomposition.md`——決策邊界；D10 的 2026-09-12 追記是本次的決策依據。ADR 沒涵蓋的：**停下來問 User**，不要自行決定。
3. `docs/lb-integration/LEVEL_SYSTEM_JOB_UX_IMPLEMENTATION_SPEC.md`——工作包、簽名、規則表、i18n 文案、測試、順序。照 §9 順序做，關卡不過不進下一個。
4. `docs/lb-integration/fixtures/`——黃金驗收。實作書 DoD-1：作業版操作後匯出的 CSV 與 `server_node_tasks.expected.csv` 逐位元相等。
5. 專案既有規範：`.kiro/steering/*.md`、`docs/DOC_REGISTRY.md`、ADR-011（加法演進）、ADR-032（雙語 UI）、ADR-034（錯誤信封）、`docs/architecture/frontend-ux-spec.md` §8（不可改動的 UX 規則）。

## 開工前必讀（依序，讀完再動手）
1. 實作書全文（§0–§13、附錄 A／B／C）。附錄 A 的反投影定義與動作表是前端核心，請逐條理解後再寫 `jobs.ts`。
2. ADR-035 D10 追記、D7；Spec §5（分層 DAG）、§6（欄位）、§8（E／W 碼與報告）。
3. 原型 `docs/lb-integration/prototypes/level-jobs/`：先在瀏覽器開 `index.html` 走一遍（載入範例 → 點作業卡 → 勾問題 → 系統看出來的事按是）；再讀 `jobs.js`（作業模型與訊息表）。**`engine.js` 只讀不移植**。
4. 程式碼（現況）：`src/frontend/src/features/level-system/{store,logic,api}.ts`、`LevelSystem.tsx`；`features/wi-workbench/{store,api,useWorksheetWorkspace}.ts`、`WiWorkbench.tsx`（`add()`、`doSave()`、WI Outline `wiGroups`）、`AiDraftPanel.tsx`；`shared/i18n/resources/{zh-TW,en}.ts` 的 `levelSystem` 區塊、`i18n.ts`；`e2e/wp12-lb-tags.spec.ts`、`e2e/locale-switcher.spec.ts`、`e2e/i18n-hardcoded-zh.spec.ts`。後端：`services/v2/{worksheet_service,export_service,import_service,motion_module_service,worksheet_revision}.py`、`lb_projection/{project,adapter,errors,tools,tmu,precedence,validator,emit}.py`、`schemas/v2/{worksheet,import_excel}.py`、`models/v2/worksheet.py`、`api/routes/v2/export.py`、`migrations/versions_v2/v2_0046_level_entries_lb_tags.py`（migration 範本）。

## 工作方式
- **一個 WP 一個（或一組）commit**，訊息：`implements ADR-035 D10: <WP代號> <一句話>`（例 `implements ADR-035 D10: B3 lb-report preview (dry-run)`），body 逐檔列變更。
- 每個 WP 結束跑：`PYTHONPATH=src pytest tests/unit -q`、`ruff check src tests scripts`、（有 DB）`PYTHONPATH=src pytest tests/integration -q`；前端變更跑 `npm run typecheck && npm run build`；E2E 用 `preview_server`（`E2E_BASE_URL`）跑指定 spec。`python3 scripts/core_logic/run_all.py` 必須維持全綠（你不該動引擎）。
- **F2 的 12 作業測試（`e2e/level-jobs-logic.spec.ts`）不綠不得進 F3**。
- 黃金 hints 快照（`fixtures/server_node_hints.expected.json`）首次產出時，把內容貼在回報中請 User 過目，過目前不視為鎖定。
- 遇到實作書／ADR 沒說清楚的：在回覆中用「❓需 User 裁決」列出問題、你的預設選項與理由，**先照預設繼續做可獨立的部分**。實作書 §13 已列各題的預設值（#2 `splittable` 已裁定不做），照預設做、在回報中標明。
- `divisible`／`splittable`：**不加 DB 欄、不加 UI、不改黃金 fixture**（實作書 §3.2、ADR-023 §4）。DoD-1 的黃金比對排除 `divisible` 欄，差異只允許 task 31 由 1 變 0；不要為了逐位元相等去補這個欄位。
- 不要為了讓測試綠而改 expected CSV、黃金 fixture、Spec 或 `derive()`。先找實作書／Spec 哪條規則，貼出條號，說明你認為程式碼哪裡不符。
- 文案：所有 UI 字串照實作書 §6 逐字建立（zh-TW／en 兩份），不要自行改寫語氣；覺得某句不好，回報建議，不要直接改。
- 文件：只改實作書 §11 列出的檔案與位置；用「追記（ADR-035 D10 修訂）」段落，不重寫原文（DOC_CONVENTION：正文描述現況，被取代處標記並指向現況）。
- 絕對不做：接 LLM、關鍵字猜測、移植 `engine.js`、動 LB repo、寫或 commit `.kiro/`／`.claude/`。

## 交付格式（每個 WP 結束時回報）
```
## <WP代號> 完成
- 變更檔案：…
- 測試：pytest …（數字）；typecheck/build；e2e <spec>（數字）；ruff clean
- 關卡：<實作書 §9 的關卡條件> ✅/❌
- 與實作書的對照：§x.y／附錄 A.n → 函式 …
- ❓需 User 裁決：（無／列點；含 §13 採用的預設值）
- 下一步：<WP代號>
```

## 全部完成時
- 貼：DoD 1–6 逐條狀態；`docs/lb-integration/screenshots/level-jobs-*.png` 路徑；黃金 hints 快照內容；§13 各題實際採用值；PR 描述草稿（比照 `PR_DESCRIPTION.md` 格式）。
