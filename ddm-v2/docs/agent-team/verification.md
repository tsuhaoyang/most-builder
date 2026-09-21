> **正本**：本檔是驗證規範的權威定義（工具中立）；各工具設定引用本檔，不重抄。
> 範本來源：line-balance_stream-weaver_v2/docs/agent-team/verification.md（commit 2b59ddc），改為 MOST 的環境與指令。

# 驗證規範（Verification Workflow）

改動要驗證到「使用者實際看到／操作的結果」，不是只驗斷言布林值或磁碟檔案。
本檔補強 checkpoint（`docs/agent-team/checkpoint.md`）的「測試結果」欄——只寫**實際跑過**的，沒跑就寫「未跑」。

## 1. 前端／UI 改動：Playwright + 截圖

任何動到前端 UI、互動流程、modal、圖表、Level System 作業版、工時表編輯的改動，驗證時**必須**：

- 先建置：`cd src/frontend && npm run typecheck && npm run build`（typecheck 含 zh-TW／en i18n 對稱的 Widen 檢查）。
- 起單一伺服器 `PYTHONPATH=src python scripts/preview_server.py`（:8099，前端＋API 同源，`AUTH_DEV_USER=IEC141289`），
  或前端熱重載 `npm run dev`（:5173，proxy /api → :8099；DEV 版才有 `window.__ddmTest` hook）。
- 用 Playwright 走**真實使用者流程**：`E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test`
  （需要 DEV hook 的 store 測試改用 :5173）。
- 驗證用的 spec 要**明確呼叫 `page.screenshot(...)`**；截圖涵蓋關鍵狀態（操作前、操作後、pill 狀態、通知）。
  **輸出位置**：預設寫該次測試的輸出目錄（`test-results/`，gitignore）；要更新版控的 `docs/lb-integration/screenshots/`（設計產物）才帶 `UPDATE_SCREENSHOTS=1`（嚴格字面 `1`）——平常跑 e2e 不該改動文件截圖（`level-jobs-screenshot.spec.ts`、`wp12-screenshot.spec.ts` 已照此實作）。
- 能攔截 API 的就 `page.waitForResponse(...)` 斷言後端契約（狀態碼、關鍵欄位），不要只看 UI 沒報錯。

單元測試（vitest／pytest）仍要跑，但**不能取代** UI 端到端截圖驗證——單元綠不等於使用者操作正確。

## 2. 後端改動

- unit 與 integration **必須分開跑**（兩邊有同名 `test_search.py`，一起跑 basename 衝突）：
  `PYTHONPATH=src pytest tests/unit` 與 `PYTHONPATH=src DATABASE_URL=... pytest tests/integration`。
- 動到 `most_engine/`、rule-set seeds、level rules、`schemas/v2/most.py` → 必跑
  `PYTHONPATH=src python scripts/core_logic/run_all.py`（黃金值 GM=28／CM=29 不得變）。
- 動到 API schema → `cd src/frontend && npm run gen:api` 重生 `src/shared/types/api.d.ts`（該檔由 OpenAPI 產生、不可手改）。
- integration 需要 DB：本機 host port 常為 15432（compose dev overlay）；沒疊 dev overlay 時 integration 會整批 skip
  ——那是環境副作用不是迴歸，報告要如實說明。

## 3. e2e 測試資料

- 需要既有 worksheet／result 才能驅動的流程，spec 要**誠實 skip**（`test.skip(!seeded, "...")`），不要靜默 pass。
- 被資料卡住時，報告明說「UI 截圖驗證被 e2e 資料阻擋」，並列出還能做的替代驗證，不要假裝驗過了。

## 4. 收尾

- 驗證用臨時檔（截圖除外）清掉。設計截圖存 `docs/lb-integration/screenshots/` 供追溯（已追蹤；更新要帶 `UPDATE_SCREENSHOTS=1`）；
  臨時 spec／test-results 不 commit。
