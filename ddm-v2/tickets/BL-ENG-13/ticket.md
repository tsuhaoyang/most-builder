---
類別: "TICKET"
開票: "2026-09-22，原條目由 auth-rbac reviewer 記入 docs/BACKLOG.md；2026-10-24 human 裁示挑此票在 MOST 側以公版票形走 L1，orchestrator 建票目錄。`state` / `stage` / `depth` 一律在 `state.yaml`，本檔不寫（C30）"
---

# BL-ENG-13 — 領域守衛的 glob 一寬一漏

| 欄位 | 內容 |
|---|---|
| **領域** | agent-team（`docs/agent-team/domains.yaml`） |
| **現況** | BACKLOG 原條目：`docs/BACKLOG.md#BL-ENG-13` — 領域守衛的 glob 一寬一漏。（2026-09-22 auth-rbac reviewer）：(a) auth-rbac 的 `src/frontend/src/shared/**` 太寬，i18n 資源檔也算進去——本輪 auth-rbac 的命中是誤命中；(b) 反過來，`tests/integration/test_outbox_api.py` 等 outbox／RBAC 的整合測試**沒有任何 glob 覆蓋**（outbox＝ADR-027 未登記在任何領域），改了它不會觸發任何 logic reviewer。 |
| **影響** | 原條目未寫，待 requirement 階段補。就原條目所述：(a) 誤命中讓 auth-rbac 領域的 reviewer 被不相關的前端檔觸發；(b) 漏覆蓋讓 outbox／RBAC 整合測試被改時沒有任何 logic reviewer 被觸發。 |
| **要做** | auth-rbac 收窄為 `shared/api/**`、`shared/types/**`、`shared/auth/**`；outbox 登記領域並把對應整合測試納入。動到 agent 設定，要跑 `check_agent_config.py`。 |
| **範圍** | 原條目所指：`docs/agent-team/domains.yaml` 的 auth-rbac 區塊與 outbox 的領域登記。確切路徑與是否另需 ADR，待 requirement／design 階段定。 |
| **權威文件** | `docs/agent-team/domains.yaml`；`docs/domains/auth-rbac.md`；`docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md` |
| **assignee** | `orchestrator` |
| **depends_on** | 無 |

---

## 與既有票的關係

本票原為 `docs/BACKLOG.md` 單檔內的一個條目；2026-10-24 起另有公版票形目錄（本目錄），狀態以同目錄 `state.yaml` 為準。

## 結果

<!-- 結案時追記。 -->
