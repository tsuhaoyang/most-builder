> **正本**：本檔是 commit 慣例的權威定義（工具中立）；各工具設定引用本檔，不重抄。
> 本檔把 MOST（ddm-v2）**現行未成文的慣例寫下來**（先前散在 agent brief 與 git log 裡）。

# MOST（ddm-v2）commit 慣例

## 標題

兩種格式，依變更性質擇一：

```
implements ADR-NNN: <WP> <一句話描述>
docs: <一句話描述>
```

- `implements ADR-NNN: …` — 實作某 ADR 的工作包。`<WP>` 是工作包代號（如 `WP12`、`B1`、`F9`、`F7`）；
  一個 ADR 有多個工作包時，每個工作包一組 commit。
- `docs: …` — 純文件變更（ADR／spec／registry／agent 設定）。
- 其他既有前綴（歷史 commit 有 `fix(worksheet): …`、`[Phase N][Scope] type(scope): …`）保留閱讀相容，
  但新工作以上面兩種為主。修 bug 而非實作 ADR 工作包時，可用 `fix(<scope>): …`。

實例（取自 git log）：

```
implements ADR-035 D10: F9 golden replica DoD-1 + fix repeat_counts propagation
implements ADR-035: WP12 Level System UI (LB tags) + E2E + screenshots
docs: update MOST contract §11 for LB Phase 2 landed
fix(worksheet): serialize version_no allocation per SKU with advisory lock
```

## Body

逐檔列出變更，一檔一行（或一組相關檔一段）。與 ADR 相關的 commit 在 body 標明對應 ADR／條號與工作包。
發現並修正的既有 bug、對既有資料的影響，也寫進 body。

## 硬規則

- **只 stage 指定檔案**。禁止 `git add -A` / `git add .`。
- **`.claude/` 永不 commit**（本 repo `.gitignore` 忽略 `.claude/`；Claude 本地設定，非版控素材）。
  **`.kiro/` 在本 repo 是被追蹤的**（現有 `.kiro/skills/`、`.kiro/steering/` 已進版控，與 LB 不同——LB 兩者皆 gitignore）：
  `.kiro/agents/`、`.kiro/hooks/` 的薄轉接**可隨正本一起 commit**，但**必須維持薄轉接**（摘要＋指路＋`resources`／`@`，
  規則本體只在 `docs/agent-team/` 正本）。⚠️ 此為 MOST 與 LB 的分歧點，已於階段一回報 Howard（見 decisions.log）。
- 子 agent 不得寫 `.kiro/`／`.claude/`（只有主 context 在使用者要求下改設定）。
- 不在預設分支（`feature/lb-projection` 等主線）直接做未經同意的 commit；功能在功能分支。
- commit 前必須跑 checkpoint 品質關卡（見 `docs/agent-team/checkpoint.md`）。
- **不 push、不合入**除非使用者明確要求。
- 架構師的未追蹤文件、他人未追蹤檔一律不代為 stage。

## 切分原則

一個 commit 一件事。跨層功能（domain/schema → service → route → 前端）拆成數個 commit，順序由下而上，
讓每個 commit 都能單獨解釋。文件（ADR／spec）通常放第一個 commit，後續程式碼 commit 才有東西可引用。
