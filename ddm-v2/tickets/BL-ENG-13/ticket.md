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

- 2026-10-28 G9：human 原始「G9核可」，後以 HD-7 原話「按你建議的 並且核可此結案方案」明確核可本票結案方案；交棒與終態以 [state.yaml](state.yaml) 為準，票面原始八欄保留。
- 已交付：auth-rbac 前端 paths 收窄為 api／types／auth，7 檔進白名單，兩個 outbox 測試與 ADR-027 登記；兩條 invariants、i18n 與其他領域不變。實作 commit：`ec51a1910762579638bf4e1caef704dd9b0e4981`；`TASK-BL-ENG-13-1` 由 `agent_done` 翻 `done`。
- 驗收證據：[verify-report.md](verify-report.md) 與 [acc/evidence/](acc/evidence/)；G8 的 c1～c16 為 16/16 PASS，PRE-1～PRE-6 全部 PASS，G9 未重跑。
- 不同步決定：依 [design.md 的 DESIGN-8](design.md#design-8auth-rbacmd-本票不同步記殘留一行對應-req-8) 與 HD-7，本次不改 `docs/domains/auth-rbac.md`，亦不再修改 `docs/agent-team/domains.yaml`。已知索引程式入口仍寫 `shared/**` 且未列 ADR-027，接受為本票殘留；備案 B 與未來索引同步仍須另取 human 授權，`open_questions` 保留，不得清 context。
- 流程記錄：`awaiting_human(verify)/verify → awaiting_human(docsync)/docsync → closed/docsync` 的連續轉移見 state log；control-flow.md §1.3 缺對應具體列，故手動記錄。FB30 仍為候選流程回饋，不代表規則已改。
- 結案範圍僅 BL-ENG-13；DW-38 bounds 的 status 10 行對基線 9 行既有 FAIL 不豁免，不宣稱 DW-38 完成。10 個既有 untracked 檔不得動。`decisions.log` 由主 context 追加；本次單筆 MOST 結案 commit 的檢查、審查與提交亦由主 context 完成。
