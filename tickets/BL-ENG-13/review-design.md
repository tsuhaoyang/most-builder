# BL-ENG-13 reviewer(design) 第 1 輪審查報告
審查對象：ddm-v2/tickets/BL-ENG-13/design.md（Draft，未 commit）
代存說明：reviewer 無寫入權限，以下為其回報原文，由 scribe 原樣代存，未改動。

## type ／ 範圍
- review_type: design　領域: 不適用（artifact 審查）　diff 範圍: `ddm-v2/tickets/BL-ENG-13/design.md`（Draft，未 commit，349 行）對照已定案 REQ-1～REQ-8
- 讀了：reviewer.md、_common.md、stage-table 第 4 列與 §1.2、doc-taxonomy §1.9、templates/DESIGN.md、ticket.md、requirements.md、review-req.md 相關段、state.yaml log（含 human 答覆全文）、AGENTS.md、checkpoint.md、domain_guard.py、check_agent_config.py check_8、docs_check.py、domains.yaml、ADR-027 §5、各被點名的前端檔。
- 沒動任何真實 most-builder 或 dev-workflow 的檔。真實 repo 只做讀取（含 `git status` 唯讀）。所有重現都在自建副本上做。

## 結論：PASS（無阻擋項；有建議項）
設計逐條覆蓋 REQ-1～REQ-8，主案 A 不依賴備案 B。我在獨立副本上重現的結果，與 design.md 宣稱的數字逐項相符。沒有把 human 沒說過的授權寫成已有授權：design.md 第 214 行如實承認白名單與檔頭 `updated` 不是 H1 字面，並交 orchestrator 向 human 回報。需要修的是措辭與一個論證支點，不影響設計可執行。

## 阻擋項
無。

## 建議項（均不阻擋）
- **S1　`config.ts` 與 `codes.py`「同型」的支點不實（DESIGN-3 第 66 行、白名單 reason 文字）。**
  - `domains.yaml` 現有的 `models/v2/codes.py` 白名單理由寫「共用列舉／代碼常數」，但該檔實際是 `CodePrefixRegistry` ORM 表（含 `next_seq`、`issuer_role`），不是常數檔。
  - 所以「比照 codes.py（共用常數）」是拿一個標籤不準的先例當依據。建議白名單 reason 刪掉「比照 models/v2/codes.py」，改成只講事實：兩個 `export const`、無函式與分支。DESIGN 論證改成「常數、無邏輯」，不靠同型。
  - 結論本身（config.ts 進白名單）我認為站得住：5 行，兩個 const，無函式與分支。`TMU_SEC` 的使用處（`WiWorkbench.tsx`、`CasesPage.tsx`、`WiOutline.tsx` 等）皆為 `tmu * TMU_SEC` 的顯示換算。`WiWorkbench.tsx:582`、`:858` 把它寫進 Row 的 `seconds`，但 `savePayload.ts` 不含 seconds，所以不進儲存 body。
  - R3 的殘留描述應補一句：後端權威常數其實是 `most_engine/rule_set_data.py:14 TMU_TO_SEC`。design 只引了 `rule_set_tables.py:217` 的 docstring，沒提到真正的常數。前端這份是重複常數，改動時沒有 logic reviewer，R3 的風險是真實的，已被接受。
- **S2　DESIGN-6／驗收對照的「271 個輸入」未列舉第 7 個點名檔。**
  - 我數到 264 + 6 = 270：2 個 outbox 測試、`test_admin_users.py`、2 支 migration、ADR-027。
  - 第 7 個推定是 `e2e/i18n-review.spec.ts`。理由是 design 稱 auth-rbac 命中數 49 → 35，我的 270 檔算出 48 → 34，差 1 恰為該檔（它仍命中 `i18n,auth-rbac`）。
  - 建議把 7 個點名檔逐一列在 DESIGN-6，不然 verifier 無法照做。「恰 18 檔不同」我已重現，不受影響。
- **S3　「須 human 裁決的邏輯變更」清單（第 207–212 行）把兩類混在一起。**
  - 清單開頭說「屬『邏輯變更』、須 human 裁決」，但其中「編輯其他領域的 paths／docs」「編輯 `docs/domains/*.md`」依 MOST 規則字面並不是邏輯變更，而是超出 REQ-6／REQ-8 或 H1 授權範圍。
  - 第 211 行把「其他領域 paths」說成「超出 H1 答覆字面」也不精確：H1 字面涵蓋 paths，擋它的是 REQ-6。
  - 建議拆成「邏輯變更（動 invariants 語意）」與「超出授權範圍（需 human 另行核可）」兩組。
- **S4　「失敗與回滾」第 226–232 行與「驗收對照」第 316–327 行貼近 DESIGN §1.9 的邊界。**
  - §1.9 規定 DESIGN 寫「要做什麼」，不寫「不能壞什麼」（那是 ACC 的 REGRESSION 型）。
  - 這兩節已標明「非 ACC」，且是回滾與失敗定義所需，我判為建議，不是阻擋。
  - 風險是數字（`16 ok`、`18 檔`、`49→35`）若被 verifier 原樣搬進 ACC，日後改 design 會連動 hash。建議在這兩節標「預期值，ACC 另定」，並把 49→35 這類不必要的數字刪掉。
- **S5　`decisions.log` 的「該 commit」欄（第 222 行）。**
  - domains.yaml 單一 commit 完成後，commit hash 才存在，所以追加 log 必然是第二次寫入。
  - 授權路徑表沒說這是第二個 commit，還是填分支名。建議在銜接節寫明，免得 implement 當場決定。
- **S6　備案 B 的 invariants 草擬（第 288–290 行）。** 見下方「備案 B 對 ADR 的核對」。
- **S7　「收窄與白名單必須在同一 commit」只出現在「失敗與回滾」第 234 行，授權路徑表只寫「單一 commit」。** 建議在授權表也寫一句理由：缺任一半，check_8 會有 error 或守衛失效。

## 對『關鍵判斷』(4) 的專項結論
**結論：可由 design 自行處理（design 階段不需先向 human 取得授權）；但不得宣稱 H1 已涵蓋，且須在 human 的下一個必到關卡（ACC 定案）明列揭露。**

**(a) 白名單新增不屬 MOST 規則所說的「邏輯變更」。** 三處出處一致：
- `domain_guard.py` 的 `render()` 收尾文字：「若這次改動或討論會**改變**上述任一條規則的語意，先問使用者要不要更新邏輯」。對象是領域 invariants 規則的語意。
- `checkpoint.md` 步驟 4：觸發條件是 logic reviewer 回報「變更提案」，即有意識地改變某條 invariant 的語意。
- `most-logic-reviewer.md` 第三步：三選一（維持／違反／變更提案）都是針對 invariants。

我在副本上用 `yaml.safe_load` 逐領域逐欄比對，兩條 auth-rbac invariants 與 i18n 區塊全欄逐字相同，白名單不是 invariants，也不是任何領域欄位。檔頭 `updated` 同理：不是領域欄位，也不影響任何 invariant 的語意。

**(b) H1 字面沒有涵蓋它，但規則本身也不要求為它設 human 關卡。**
- human 的原話只有「按你建議」，其內容是 H1「只動 domains.yaml 的 paths 與文件登記，不算邏輯變更」。白名單與 `updated` 不是 `paths`，也不是文件登記。
- 但 orchestrator 當時給的理由是「規則的對象是 invariants 的語意，不是 paths 的歸屬」，並明說「把 7 個檔移出 auth-rbac」。這個理由同樣適用於白名單，因為兩者都是登記表的歸屬變動。
- 不屬 H1 字面，同時又不屬邏輯變更，所以既不是「H1 已授權」，也不是「必到關卡要先問」。design 第 214 行如實承認這點，做法正確。
- 有一個真實的後果值得 human 知道：7 檔進白名單後，`TMU_SEC` 改動時不再派任何 logic reviewer（R3）。

**(c) REQ-3 那句話的效力與來源。**
- 「去處不需另走 human 裁決」出自 analyst 起草的 REQ-3；其依據「下游影響：原 H2、H3 不再需要 human 裁決」是 analyst 對 H1 的推論。`state.yaml` 紀錄的 human 原話是「按你建議」，沒有這句措辭。
- reviewer(req) 兩輪 PASS 只審 REQ 的形式（可驗證、不含實作決定等），沒有授權人類決定的權限。
- 所以這句話只有一個效力：它界定了 REQ-3 的合格條件（命中某領域，或在白名單且合乎判準）。design 因此可以提出白名單方案。它不是 human 授權，design 不應引它當授權。
- design 第 214 行的寫法「REQ-3 明文允許…這一點由 orchestrator 向 human 回報時一併帶到」可接受。
- 建議把依據改寫為「依規則字面不屬邏輯變更，且屬 REQ-3 合格路徑之一」，不要引「寫明不需另走 human」。

**建議 orchestrator 在 ACC 定案向 human 的一行揭露**（不是 design 的前置條件）：
- 問題：「BL-ENG-13 的 design 把 `shared/` 被移出 auth-rbac 的 7 個檔（config.ts、workspace.ts、ui/ 5 檔）放進 `no_domain_allowlist`，另更新 domains.yaml 檔頭日期。這兩項不是你答 H1 時說的 paths 與文件登記字面。我們判為不屬邏輯變更（兩條 invariants 逐字不變）。其中 config.ts 的 `TMU_SEC`（TMU 換算 0.036）進白名單後，日後改動不會派 logic reviewer。你接受嗎？」
- 建議答案：接受。
- 若 human 不接受 config.ts 進白名單，design 內已有被否決的替代方案 (b)（以精確路徑留在 auth-rbac，副本 0 error），只影響一檔，不影響其餘設計。

## 其他審查重點結論
- **覆蓋度（重點 1）**：REQ-1～8 各有 DESIGN-1～8 對應，且每條有可驗證結果。REQ-8（should）有明確表態（不同步）並記殘留一行，符合其兩條限制。
- **白名單判準（重點 3）**：我逐檔讀了內容。
  - `ui/Hint.tsx`（9 行）是單一 span，`ui/ComboBox.tsx`（57 行）是 props 驅動的通用下拉，`ui/ErrorBoundary.tsx` 是 React 錯誤邊界，`ui/WorksheetRequiredNotice.tsx`（33 行）只派送 `ddm:switch-tab` 事件，`ui/RuleSetUnavailable.tsx`（22 行）只顯示傳入錯誤與 `t()` 文案。全部符合「框架接線／通用基底」。
  - `workspace.ts`（29 行）是 zustand store，兩個 setter、無條件式。被 wi-project（motion-module）、import（excel-import）、wi-workbench、level-system（job-ux）等多個領域的檔引用，無單一歸屬，「跨領域共用」成立。
  - `config.ts` 見 S1。
  - `useActiveRuleSet.ts` 留在 auth-rbac：理由成立。它在 `shared/api/**` 之內，經 `apiGet`（`client.ts`）發請求，屬 invariant 2「client.ts 唯一 API 入口」要守的一類，且檔內有「不提供預設 code」的契約，不是純接線，不適合進白名單。
- **備案 B 對 ADR 的核對（重點 5）**：備案 B 設計完整（領域區塊、`outbox.md`、`DOC_REGISTRY.md`、授權路徑、回滾），並標示待 human 裁決，主案不依賴它。三條 invariants 回 ADR-027 §5（標題在第 64 行）逐條核對：
  - 第 1 條逐字取自 §5 第 1 點。
  - 第 3 條逐字取自 §5 第 4 點。
  - 第 2 條把 §5 第 2 點（AI consumer at-least-once）與第 3 點合併，並截掉第 3 點後半「不直接寫 DDM 正式表」，所以不算忠於原文。
  - design 已聲明「是否逐字、是否再加或刪由 human 認可」，我列為建議 S6：建議拆成兩條，或補回被截的子句，並在草稿旁標明這一處。
- **授權路徑與 reviewer 派工（重點 6）**：路徑上限（`domains.yaml`、`state.yaml`、`decisions.log` 追加）合理；`auth-rbac.md` 與備案 B 的新檔明確排除。派工（一個 most-code-reviewer、一個 most-logic-reviewer 帶 `domain_id: auth-rbac`、資安一個、i18n 不派）符合 `checkpoint.md` 步驟 2。
  - 「domain_id 要手動指定」屬實：我對 `domains.yaml`、`decisions.log`、`tickets/BL-ENG-13/design.md` 實跑領域對應，輸出 0 行，步驟 1 算不出領域。
  - 不派 i18n：該領域全欄零差異（我已逐欄比對），理由成立。
- **與既有流程衝突（重點 7）**：未發現衝突。`decisions.log` 追加一行有既有先例（2026-09-21、2026-09-22 的列），檔頭寫明只由主 context 追加；commit 慣例 `docs:` 類正確；步驟 5、6 的檢查正確列入。回滾與失敗定義完整（五條失敗情況加整筆 `git revert`，且寫明缺 pyyaml 不算通過），僅 S5 的一處缺口。
- **其餘（重點 8）**：
  - L1 判定依 `_lib.manifest.yaml` 的 `project_facts`（含 `domains`、`decisions_log`）判為專案事實層，屬實。ADR-0001 正本不在 MOST 倉庫，design 已誠實聲明這個限制。
  - 「不立 ADR」「不動 invariants 與 i18n」屬實（見重現）。
  - 硬規則：本票目錄只出現 `BL-ENG-13`，無其他 BL-ENG 編號；design 只提到 `BL-DOC-4`，非 BL-ENG。design 內無 `state:`／`stage:`／`depth:` 欄位寫法，僅在授權表提到 `state.yaml` 檔名。無懸空引用。

## 我重現的結果
副本位置：`/tmp/claude-1000/-home-howard-workspace-dev-workflow/8a1f69a5-911b-4e2d-95de-9b7ade958d01/scratchpad/rv-design-13/`
建法：自 most-builder 根 rsync，排除 `.venv`、`node_modules`、`graphify-out`、各 cache、`.git`，含根層 `CLAUDE.md`、`AGENTS.md`，再 `git init` 並提交基線。所有 python 都用 `python3 -B` 並設 `PYTHONDONTWRITEBYTECODE=1`。
我另寫了命中探測腳本，載入副本的 `domain_guard`，對 264 個業務檔加 6 個點名檔共 270 檔逐檔算命中集合。

| # | 動作 | 結果 |
|---|---|---|
| 1 | 基線 `check_agent_config.py` | `16 ok, 0 warn, 0 error`；check_8＝264 檔全命中或在白名單 |
| 2 | 基線 `docs_check.py`（存檔作比對基準） | `4 ok, 13 warn, 0 error` |
| 3 | 套用主案 A（改檔頭 `updated`、白名單 +7、`shared/**` 換三條、+2 測試路徑、+ADR-027；白名單 reason 用占位字串，不影響檢查） | 同下 |
| 3a | `check_agent_config.py` | `16 ok, 0 warn, 0 error`；check_8 仍為 264 檔 |
| 3b | `docs_check.py` 與基準逐行比對 | 無差異；`4 ok, 13 warn, 0 error` |
| 3c | 命中全量前後比對 | 恰 18 檔不同：`config.ts`、`workspace.ts`、`ui/` 5 檔（`auth-rbac` → 無）；`shared/i18n/` 9 檔（`auth-rbac,i18n` → `i18n`）；2 個 outbox 測試（無 → `auth-rbac`）。與 design 預期相符。 |
| 3d | `yaml.safe_load` 逐領域逐欄比對 | 領域 id 順序相同；僅 `DIFF auth-rbac docs`、`DIFF auth-rbac paths`；auth-rbac invariants 相同、i18n 整個區塊相同；白名單 24 → 31 |
| 3e | 領域對應對 `domains.yaml`、`decisions.log`、`design.md` | 輸出 0 行（領域算不出） |
| 3f | 領域對應 `tests/unit/test_outbox.py` | 第三欄含 ADR-027 |
| 4 | 對照組：只把 `shared/**` 換成三條子目錄，不加白名單 | `15 ok, 0 warn, 7 error`；7 條 ERR 恰為 `config.ts`、`workspace.ts`、`ui/` 5 檔 |
| 5 | 對照組 2：主案 A 但少加 `workspace.ts` 白名單 | `15 ok, 0 warn, 1 error`（只報 `workspace.ts`），證明 check_8 逐檔精確比對 |
| 6 | 其他命中 | `client.ts`、`useActiveRuleSet.ts`、`useMe.ts`、`api.d.ts` 仍為 `auth-rbac`；`test_admin_users.py`、`v2_0032` 皆 `-`；`e2e/i18n-review.spec.ts` 仍為 `i18n,auth-rbac`。auth-rbac 命中數 48 → 34（design 稱 49 → 35 差 1，見 S2 推論）。 |

未跑：備案 B 的副本實跑（design 已自述跑過，我未獨立重現；備案 B 非主案的依賴）。未跑 pytest 與前端建置（本票不動程式）。

## 抽查的事實（皆已對照實檔）
1. `domains.yaml:368` 為 `shared/**`；`:307` 為 i18n 的 `shared/i18n/**`；`:371` 為 `i18n-review.spec.ts`；`:374` 為 `rbac-spec.md`；`:351` anchors、`:375` keywords、`:377–378` 兩條 invariants、`:320–324` i18n invariants、`:69–70` App.tsx 白名單末條。全部相符。
2. `domains.yaml:21` 判準註解為「純結構／框架接線／設定／通用基底，無業務邏輯…每條附理由」，與 design 引用相符。
3. check_8 以 `rel in allow` 精確比對（`check_agent_config.py` 約 275–310 行），不認 glob，相符；其 docstring 稱排除 `api.d.ts` 但程式未排除（REQ 證據 6 的說法屬實，design 列為不處理 R8）。
4. `shared/` 下檔數 20，相符。
5. 行數：`Hint.tsx` 9、`RuleSetUnavailable.tsx` 22、`WorksheetRequiredNotice.tsx` 33、`workspace.ts` 29、`config.ts` 5，皆與 design 相符。
6. `config.ts:3` 為 `TMU_SEC = 0.036`；`rule_set_tables.py:217` docstring 含 `ceil(sec/0.036)`，屬實。
7. ADR-027 `## 5` 標題在第 64 行，相符。
8. `domains.yaml:177` 為 wi-workbench 的「前端不算 TMU」invariant，相符。
9. `decisions.log` 檔頭寫「只由主 context 追加；tab 分隔」，且 2026-09-21 有 `domains.yaml` 相關列、2026-09-22 有測試基礎建設列（含 `test_outbox_api.py`），先例屬實。
10. `_lib.manifest.yaml` 的 `project_facts` 含 `domains`、`decisions_log`，且 `_lib/` 內無 ADR-0001 正本（find 無結果），屬實。
11. 兩個 outbox 測試檔存在；`docs/domains/auth-rbac.md` 第 15 行含 `src/frontend/src/shared/**`、第 30 行測試清單含 `test_outbox_api.py`，相符。
12. `stage-table.md` 第 4 列離開條件三件事（每條 REQ 有設計、外部依賴失敗行為、違反既有 invariant 已標示）：design 皆有對應節。
13. 抽查 `codes.py` 內容，發現與白名單 reason「共用列舉／代碼常數」不符（S1 的根據）。

## 設計是否足以進 implement
足夠。主案 A 可獨立執行：差異完整（見 design 第 152–191 行），我在副本套用後所有宣稱結果皆重現。進 acceptance 前，建議 architect 處理 S1、S2、S3，並由 orchestrator 在 ACC 定案時依上方問題向 human 揭露白名單與 `TMU_SEC` 殘留；S4–S7 可併入同一次修訂。備案 B 與 `auth-rbac.md` 同步維持「待 human」，不阻擋。
