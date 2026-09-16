> **正本**：本檔是品質關卡（checkpoint）的權威定義（工具中立）。
> 描述「派哪些 reviewer、帶什麼 `domain_id`、跑哪些檢查」，不綁定任何工具的指令名或觸發語法；
> 各工具設定引用本檔，不重抄。範本來源：line-balance_stream-weaver_v2/docs/agent-team/checkpoint.md（commit 2b59ddc）。

# checkpoint — 品質關卡（commit 前必跑）

MOST（ddm-v2）品質關卡：機械 review + 逐領域邏輯 review + 資安檢查，並就邏輯變更詢問是否更新文件。
**主對話不得自行做 code review 或資安檢查**——一律委派給對應自訂 agent（`most-code-reviewer`、
`most-logic-reviewer`、`most-doc-sync`；角色正本在 `docs/agent-team/agents/`）。委派機制依所用工具
（Kiro `#invoke_sub_agent`、其他工具的 subagent／task 機制），但「派誰、帶什麼」以本檔為準。

範圍：未指定時就是整個工作區的 `git diff` 加上 untracked 檔案。

## 步驟 1：算出受影響的領域

```bash
FILES=$(git diff --name-only; git status -s | grep '^??' | awk '{print $2}')
python3 scripts/agent_team/domain_guard.py map $FILES
```

輸出每行是 `domain_id \t title \t docs`。這份清單決定要派幾個 logic reviewer。
沒有任何領域命中就在報告裡明說——那代表這批只動到領域外的東西（多半在 `no_domain_allowlist`），
不是「跳過檢查」。

## 步驟 2：併發委派（同一則回覆內全部派出去）

- **一個** `most-code-reviewer`：給它檔案清單，做機械面檢查。
- **每個命中領域一個** `most-logic-reviewer`：prompt 開頭必須寫明 `domain_id: <id>`，並附該領域命中的檔案。
- **資安**：做資安審查（主對話不得自己下資安判斷）。

領域多時仍一次全派，不要分批——它們彼此獨立。

## 步驟 3：彙整

合成一份報告：

```
## 阻擋級（必須修才能 commit）
## 建議（可以之後處理）
## 資安
## 測試結果（實際跑過的指令與數字）
## 邏輯變更提案（需要你裁決）
```

**不要**自己重寫 reviewer 的判斷。它說「違反」你就照列；不同意其結論就寫下反對理由，讓使用者看到兩邊說法。

## 步驟 4：邏輯變更——問，不要自己決定

若任何 logic reviewer 回報「變更提案」，逐項問使用者：

- 選項一：**核可並更新文件** → 派 `most-doc-sync` 改對應文件
- 選項二：**這是 bug，改回程式碼** → 列進阻擋級
- 選項三：**先擱置** → 記進報告，不改文件也不改程式

這一步不可跳過。悄悄改了規則卻沒更新 ADR，正是這套機制要防的事。

## 步驟 5：agent／文件設定一致性（改到 agent 設定或 docs/agent-team/ 時必跑）

若動到任何 agent 設定（`docs/agent-team/`、`.kiro/`、`.claude/`、`CLAUDE.md`、`AGENTS.md`）或搬動
`scripts/agent_team/` 腳本：

```bash
python3 scripts/agent_team/check_agent_config.py
```

非零退出碼即阻擋 commit（正本／轉接引用斷裂、agent 名單不一致、業務檔無領域守衛、舊路徑殘留等）。

## 步驟 6：文件與圖同步

- 若改到 `docs/`：階段二起跑 `python3 scripts/docs_check.py`（斷鏈 error 擋 commit；孤兒／缺狀態標頭／
  領域索引與 domains.yaml 不一致／graphify 落後為 warning）。**此腳本於階段二 WP-D3 建立**。
- 若跑動過程式：跑 `graphify update .`（圖需先以 `graphify .` 建立；現有 `graphify-out/` 落後 ADR-035，
  階段二 WP-D1 會重建），讓知識圖與 HEAD 同步。

## 步驟 7：收尾

- 有阻擋級問題 → 明說「不可 commit」，列出待修項。
- 全綠 → 說明可以 commit，並依 `docs/agent-team/commit-convention.md` 提出 commit 切分建議。
- 步驟 6 的腳本依這次改了什麼決定要不要跑。

## MOST 測試指令（實際）

- unit 與 integration **必須分開跑**（同名 `test_search.py`，一起跑 basename 衝突）：
  - `PYTHONPATH=src pytest tests/unit`
  - `PYTHONPATH=src DATABASE_URL=... pytest tests/integration`
  - `PYTHONPATH=src python scripts/core_logic/run_all.py`（引擎黃金值；動到 most_engine／rule-set／level 必跑）
- 前端：`cd src/frontend && npm run typecheck && npm run build`；e2e 需先起 `scripts/preview_server.py`（:8099）
  再 `E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test`（UI 驗證見 `docs/agent-team/verification.md`）。
- ruff：`ruff check src/`。

## 紀律

- 測試結果只寫**實際跑過**的。沒跑就寫「未跑」，不要從程式碼推測會不會過。
- reviewer 回報的問題若你驗證後認為是誤報，寫「已驗證為誤報」並附證據，不要默默刪掉。
- 這個關卡只做檢查與提問，**不會自己 commit**。
