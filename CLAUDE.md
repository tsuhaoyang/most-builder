# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

> **薄轉接**：規則本體不在此。單一事實來源是 `@AGENTS.md`（工具中立入口）與其指向的
> `docs/agent-team/` 正本。本檔只保留 Claude 專屬設定與指路，避免規則兩處漂移（DOC_CONVENTION R3）。

@AGENTS.md

## Claude 專屬

- 子 agent（薄轉接）在 `.claude/agents/`：`most-code-reviewer`、`most-logic-reviewer`、`most-doc-sync`；
  完整定義在 `docs/agent-team/agents/<name>.md`。`.claude/` 為 gitignore，不 commit。
- Claude skills 在 `.kiro/skills/`（db-schema、fastapi-dev、graphify、most-review、react-dev）。
- 品質關卡的委派機制：讀 `docs/agent-team/checkpoint.md`，用 subagent／task 機制派 reviewer；
  「派誰、帶什麼 domain_id」以該檔為準。

## repo 邊界（給 Claude 的提醒）

- git 根＝專案根（2026-11-11 起；原 `` 已上移），所有指令都在 repo 根執行。
- 處理 line-balance 檔案前，先讀它的入口（`/home/howard/workspace/line-balance_stream-weaver_v2/AGENTS.md`）——
  其測試環境、時間單位契約、commit 規範定義在那裡。

## 已知過時修正（2026-09-16，本輪逐條查證）

先前本檔（146 行版）有數處敘述與現況不符，已在改薄時一併校正：

1. `/dev-team:checkpoint` slash command — MOST **無**此 command／dev-team；實際機制是
   `docs/agent-team/checkpoint.md`（本輪新建）。
2. 「委派對應席位」引用的 `ddm-backend`／`ddm-frontend`／`ddm-validator`／`ddm-testing` agent —
   **不存在**（`.kiro/agents`、`.claude/agents` 先前皆空）；正確清單為 `most-code-reviewer`／
   `most-logic-reviewer`／`most-doc-sync`（本輪新建）。
3. `/arch-decisions` skill、`unified-arch` agent — **不存在**（skills 僅 db-schema／fastapi-dev／
   graphify／most-review／react-dev）。改為指向 `docs/decisions/`。
4. 「Hard Rules (from `.cursor/rules/`)」 — `.cursor/` 是不同工具（Cursor）的本機設定（gitignore），
   非本專案 agent 設定；該三條硬規則（no error bypass、DB 雙邊、agent 委派）語意仍有效，
   併入 AGENTS.md 的核心不變量。
5. `DATABASE_URL=...localhost:5432` 範例 — 本機 dev（compose dev overlay）host port 常為 **15432**；
   5432 僅為通用範例，實際以 compose 的 db 服務為準。
6. app 綁 `127.0.0.1:8877:8000`（docker）／preview_server `:8099`（本機）——已與現況核對一致，保留於 AGENTS.md 指向的 README。
