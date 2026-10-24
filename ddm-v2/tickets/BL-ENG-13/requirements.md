---
類別: REQ
狀態: 已定案
票: BL-ENG-13
凍結於: DESIGN 定案（rules/doc-taxonomy.md §1.8）
偏離: 無
---

# BL-ENG-13 需求條目

**本檔為修訂稿**（依據 `tickets/BL-ENG-13/review-req.md` 的 S1～S6 與 human 2026-10-24 對 Q1／Q2／H1 的答覆，見文末修訂紀錄）。

本批 REQ 抽自 `tickets/BL-ENG-13/ticket.md`（現況／要做／範圍）與 `docs/BACKLOG.md` 該票原條目（289–296 行），
並經 analyst 在專案副本上實跑查證（可重跑的指令見「證據」節末的「重現指令」）。
`ticket.md` 的「影響」欄寫「待 requirement 階段補」，「對應文件」欄缺；兩者在下方「問題與證據」與「對應文件」補齊。
所有行號指 `ddm-v2/` 底下的檔案（目前 HEAD 加工作樹）。
**讀了什麼：** 領域登記（`domains.yaml`）、檢查腳本的匹配段（`check_agent_config.py` check_8、`docs_check.py` 領域索引段、`domain_guard.py` 的 `map`）、
檔案清單，以及少數點讀的行（`shared/config.ts` 第 3 行，作為白名單判準的反例；`docs/domains/auth-rbac.md` 第 9、15、30、31 行；ADR-027 第 64 行）。
未讀各業務檔的實作邏輯。

---

## 問題與證據

**影響（補）：** 領域守衛（`scripts/agent_team/domain_guard.py map`，checkpoint.md 第 18 行使用）以 `domains.yaml` 各領域的 `paths` 決定
「改了哪些檔就派哪些領域的 logic reviewer」（checkpoint.md 第 28 行）。登記一寬一漏的後果：
(a) 與認證無關的前端檔被改時，auth-rbac 的 reviewer 被多派一次（誤觸發，浪費 reviewer 額度並稀釋命中訊號）；
(b) outbox 的測試與決策文件被改時，沒有任何 logic reviewer 被派（漏觸發，邏輯變更無人把關）。

**證據（逐項為實查結果）：**

1. auth-rbac 區塊在 `docs/agent-team/domains.yaml` 349–378 行；其 `paths` 含單條 `"src/frontend/src/shared/**"`（368 行）。
2. `src/frontend/src/shared/` 下實有 20 個檔（`find` 結果）：`api/`（2：client.ts、useActiveRuleSet.ts）、`auth/`（1：useMe.ts）、`types/`（1：api.d.ts）、
   `i18n/`（9：errorCodes.ts、errorMessage.ts、i18n.ts、pickNarrative.ts、useLocaleSync.ts、resources/{en,zh-TW,errors.en,errors.zh-TW}.ts）、
   `ui/`（5：ComboBox、ErrorBoundary、Hint、RuleSetUnavailable、WorksheetRequiredNotice，皆 .tsx）、根層 2（config.ts、workspace.ts）。
3. 現況命中（`domain_guard.py map` 逐檔實跑）：`shared/i18n/` 的 9 檔同時命中 `i18n` 與 `auth-rbac`（`i18n` 領域另有 `"src/frontend/src/shared/i18n/**"`，307 行）；
   其餘 11 檔只命中 `auth-rbac`。所以 i18n 檔「被 auth-rbac 多算」屬實，但 i18n 檔一直有 `i18n` 領域歸屬，不是無主。
   DW-38 基線（公版 `tickets/DW-38/acc/evidence/baseline/domain-map.txt`）與此一致。
4. outbox 的程式路徑**已登記**：`services/v2/outbox_service.py`（355 行）、`models/v2/outbox.py`（361 行）在 auth-rbac 的 `paths`；
   `anchors` 含 `outbox_service`（351 行）、`keywords` 含 `outbox`（375 行）。未登記的是：
   `tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py`、`migrations/versions_v2/v2_0032_outbox_events.py`、`v2_0033_outbox_event_no_unique.py`、
   以及 ADR-027（`docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md`，其 §5 第 64 行為 outbox 決策；`domains.yaml` 內無 `ADR-027` 字樣）。
   `map` 實跑：`test_outbox_api.py`、`test_outbox.py`、ADR-027、兩支 migration 皆命中 0 領域。
5. **更廣的事實：** `domains.yaml` 內沒有任何 `tests/` 路徑（grep 無命中）。`map tests/integration/test_admin_users.py` 亦命中 0 領域。
   即「測試檔無領域」是全面現象，不只 outbox；而 `docs/domains/auth-rbac.md` 第 30 行把 `test_admin_users*.py`、`test_audit*.py`、`test_outbox_api.py`、`test_search.py` 列為本領域測試——索引說有、登記表沒有。
6. 檢查腳本（讀碼）：`check_agent_config.py` 的 check_8（275–310 行）掃 `src/ddm_v2/**/*.py` 與 `src/frontend/src/**/*.{ts,tsx}`，
   命中 0 領域且不在 `no_domain_allowlist` 者報 ERR，有 ERR 則退出碼 1，checkpoint.md 步驟 5 規定非零即阻擋 commit。
   故 check_8 **不管** tests／migrations／docs；(b) 這類漏只有 `map` 看得出來，沒有任何機械檢查會攔。
   **api.d.ts 的實際行為：** check_8 的 docstring（276–278 行）寫「排除產生檔 api.d.ts」，但程式的 glob（`**/*.ts`）與過濾（只排除 `__pycache__`）並未排除它，
   所以 `shared/types/api.d.ts` 實際被納入 check_8 的 264 檔，且目前因 `shared/**` 命中 auth-rbac。docstring 與程式不一致；本票不處理這個不一致，
   但任何使 `api.d.ts` 失去領域命中的變動都會讓 check_8 對它報 ERR。
7. **票面「要做」的收窄會製造 7 個無主檔（實跑）：** 在副本把 368 行換成 `shared/api/**`、`shared/types/**`、`shared/auth/**` 後跑 `check_agent_config.py`：
   `-- 15 ok, 0 warn, 7 error --`，7 條 ERR 為 `shared/config.ts`、`shared/workspace.ts`、`shared/ui/` 下 5 檔（命中 0 領域且不在白名單）。
   基線（未改）為 `16 ok, 0 warn, 0 error`、264 個業務檔全命中。同一變更下 `shared/i18n/` 9 檔只剩命中 `i18n`（符合 (a) 的意圖），
   `client.ts`／`useActiveRuleSet.ts`／`useMe.ts`／`api.d.ts` 仍命中 auth-rbac。
8. 白名單判準（`domains.yaml` 21 行起的註解）是「純結構／框架接線／設定／通用基底，無業務邏輯」。`shared/config.ts` 第 3 行有 `TMU_SEC = 0.036`（一個計算常數），
   是否符合「無業務邏輯」不由 REQ 判，交 design 提案。
9. invariants：auth-rbac 的 `invariants` 在 376–378 行，兩條分別在 377、378 行（378 行含 `shared/api/client.ts`、`shared/types/api.d.ts` 字樣）。
   i18n 的 `invariants` 在 320–324 行。副本中收窄 auth-rbac `paths` 後逐領域逐欄比對，**只有 auth-rbac 的 `paths` 欄不同**，其餘欄（含兩領域 invariants）逐字相同。
   即收窄在技術上不需要動任何 invariants 文字。
10. 對應文件的關係（見下節）：`docs/domains/auth-rbac.md` 第 15 行的「程式入口」仍寫 `src/frontend/src/shared/**`；
    副本 `docs_check.py` 的「領域索引程式入口與 domains.yaml paths 一致」檢查在收窄前後都 OK（比對規則為有交集即可，見 `scripts/docs_check.py` 219–236 行）。
    該檢查只比對各領域索引的「程式入口」與 `paths`，不檢查索引是否列出 ADR 或測試。

**重現指令**（在 `most-builder` 根目錄；`$S` 為任一 repo 外的新目錄，**不要在真實 repo 內執行會寫檔的步驟**）：

```
S=<新目錄>; rsync -a --exclude .venv --exclude node_modules --exclude graphify-out --exclude __pycache__ --exclude .git ./ "$S"/
cd "$S"/ddm-v2; export PYTHONDONTWRITEBYTECODE=1
python3 -B scripts/agent_team/check_agent_config.py | tail -1          # 基線：16 ok, 0 warn, 0 error
find src/frontend/src/shared -type f | sort | while read f; do echo "$f $(python3 -B scripts/agent_team/domain_guard.py map "$f" | cut -f1 | paste -sd,)"; done   # 證據 2、3
for f in tests/integration/test_outbox_api.py tests/unit/test_outbox.py tests/integration/test_admin_users.py \
         migrations/versions_v2/v2_0032_outbox_events.py migrations/versions_v2/v2_0033_outbox_event_no_unique.py \
         docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md; do
  echo "$f -> [$(python3 -B scripts/agent_team/domain_guard.py map "$f" | cut -f1 | paste -sd,)]"; done      # 證據 4、5：皆 []
sed -i '368s|.*|      - "src/frontend/src/shared/api/**"\n      - "src/frontend/src/shared/types/**"\n      - "src/frontend/src/shared/auth/**"|' docs/agent-team/domains.yaml
python3 -B scripts/agent_team/check_agent_config.py | tail -1          # 證據 7：15 ok, 0 warn, 7 error
python3 -B scripts/docs_check.py | tail -3                              # 證據 10：改前改後各跑一次比較
```

（`map` 一次給多檔時輸出的是聯集，要逐檔判斷須逐檔呼叫。副本須含 repo 根的 `CLAUDE.md`、`AGENTS.md`，否則 check_agent_config 會多出 2 條無關的 ERR；上面的 rsync 已含。）

---

## 對應文件（補）

| 文件 | 與本票的關係 | 本票可否改 |
|---|---|---|
| `docs/agent-team/domains.yaml` | 本票的變更對象（auth-rbac 區塊、outbox 的登記、必要時 `no_domain_allowlist`） | 可（agent 設定；改後須跑 `check_agent_config.py`，checkpoint.md 步驟 5） |
| `docs/domains/auth-rbac.md` | auth-rbac 的領域索引，第 15 行路徑、第 30 行測試清單與登記表有落差；其「不變量」節明言以 `domains.yaml` 為單一權威 | 預設不改；是否同步由 design 提出建議（見 REQ-8） |
| `docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md` | accepted（2026-08-10）；§5 為 outbox 決策；目前不在任何領域的 `docs` 清單 | 本票只可能把它**登記**為某領域的權威文件，不改其內容 |
| `docs/architecture/rbac-spec.md`、ADR-019 | auth-rbac 現有權威文件，不因本票改變 | 否 |

---

## REQ-1　auth-rbac 的前端範圍不得含與認證／RBAC 無關的檔

- **statement：** `shared/` 底下與認證／RBAC 無關的前端檔（至少 `shared/i18n/` 全部 9 檔）被改動時，不得再觸發 auth-rbac 領域；
  與認證／RBAC 有關的前端檔（至少 `shared/api/client.ts`、`shared/auth/useMe.ts`、`shared/types/api.d.ts`）仍須觸發 auth-rbac。
- **驗收意圖：** 不能壞：上述三個有關檔的 auth-rbac 命中不得消失；auth-rbac 其他 `paths`（後端 auth／audit／outbox／search、`features/{users,layout,dashboard}`）命中不變。
  失敗：收窄後 `shared/i18n/` 任一檔仍命中 auth-rbac；或 `client.ts`／`useMe.ts`／`api.d.ts` 任一檔命中 0 或不含 auth-rbac。
- **priority：** must

## REQ-2　`shared/i18n/` 全部檔的領域歸屬是 i18n，且只有 i18n

- **statement：** `shared/i18n/` 底下每個檔（含 `resources/` 四檔）的領域命中集合恰為 `{i18n}`。
- **驗收意圖：** 不能壞：`i18n` 領域的 `paths`、`invariants`、`docs`、`keywords`、`anchors` 全欄不得因本票改變。
  失敗：任一 `shared/i18n/` 檔命中集合不等於 `{i18n}`（含命中 0、含多命中）。
- **priority：** must

## REQ-3　收窄不得製造無主業務檔

- **statement：** 收窄後，`shared/` 下被移出 auth-rbac 的檔（現查為 `config.ts`、`workspace.ts`、`ui/` 5 檔）每一個都必須有明確去處，
  即達到 check_8 既有的合格條件（命中某領域，或在 `no_domain_allowlist` 且理由合乎該白名單判準，證據 8）。
  各檔的具體去處由 design 提案（human 對 H1 的答覆見「需要 human 決的點」：只動 `paths` 與文件登記不算邏輯變更，故去處不需另走 human 裁決，前提見 REQ-5）。
- **驗收意圖：** 不能壞：`check_agent_config.py` 對全部業務檔的 check_8 維持通過（基線「所有業務檔（264 檔）都命中領域或在白名單」），整體退出碼 0、0 error、0 warn。
  失敗：check_8 出現任何 ERR（實跑顯示只照票面建議收窄會有 7 條）；或有檔靠不合白名單判準的理由過關。
- **priority：** must

## REQ-4　outbox 相關的測試與決策文件必須被領域守衛覆蓋

- **statement：** 改動 `tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py` 時，`domain_guard.py map` 必須命中至少一個領域（含該領域的 logic reviewer 會被派）；
  ADR-027 必須登記為某領域的權威文件（`docs` 清單）。outbox 現有程式路徑（`outbox_service.py`、`models/v2/outbox.py`）的命中不得消失。
  （outbox 的兩支 migration 與 outbox 以外的測試不在本條，見「不立條」之「不做」。）
- **驗收意圖：** 不能壞：outbox 兩個程式路徑仍命中至少一個領域；被選為歸屬的領域其 `invariants` 文字不變。
  失敗：上述兩個測試檔任一命中 0 領域；ADR-027 不在任何領域的 `docs`；outbox 程式路徑命中變 0。
- **priority：** must

## REQ-5　兩條 invariants 與 i18n 領域的規則文字不得被動

- **statement：** 本票完成後，auth-rbac 的 `invariants` 兩條（`domains.yaml` 377、378 行）與 i18n 領域的所有欄位（`paths`、`invariants`、`docs`、`keywords`、`anchors` 等，invariants 在 320–324 行）逐字不變。
  若 design 認為非動不可（動 invariants，或動 i18n 領域任何欄位），該動作是邏輯變更，不在 human 對 H1 的答覆範圍內，須回報並由 human 另行裁決，不得併入本票自行決定。
  同一邊界也適用於新增領域：若 design 的做法必然需要新增領域（連帶新增 invariants 區塊與領域索引檔），該部分不在 H1 答覆內，須回報 human 另行裁決。此為邊界規則，REQ 不選 outbox 併入既有領域或新增領域。
- **驗收意圖：** 不能壞：兩領域 `invariants` 的每一條字串，以及 i18n 領域的其餘欄位。失敗：兩領域的 `invariants`（或 i18n 的任一欄）與變更前有任何字元差異，而 human 尚未對該差異做過裁決。
- **priority：** must

## REQ-6　範圍外的領域命中維持不變

- **statement：** 以全部業務檔（基線 264 個）加本票點名的 tests／ADR 檔為輸入，變更前後 `domain_guard.py map` 的命中集合，
  差異只能落在 REQ-1～REQ-4 明列的檔；其餘所有領域的 `paths` 不得被改。
  本票「不做」的檔（outbox 的兩支 migration、outbox 以外的測試）命中集合也須維持變更前（現為 0 領域）。
- **驗收意圖：** 不能壞：其餘 10 個領域（most-engine、rule-set、level-system、wi-workbench、motion-module、nlp-compiler、lb-projection、job-ux、i18n、excel-import）的全欄位。
  失敗：變更前後命中差異含 REQ-1～REQ-4 以外的檔，或「不做」的檔被順帶納入某領域。
- **priority：** must

## REQ-7　領域索引檢查不得新增 error／警告

- **statement：** 本票完成後，`docs/domains/*.md` 與 `domains.yaml` 的一致性檢查（`scripts/docs_check.py` 的「領域索引檔名」與「程式入口」兩項）維持通過，
  且不得因本票新增 docs_check 的 error 或 warning。
  本條只管 docs_check 的 error／warning 數，**不要求**索引文件全文（例如 `auth-rbac.md` 第 15 行的字面路徑）與 `paths` 逐字一致；該檢查本來就只比對「有交集即可」（證據 10）。
- **驗收意圖：** 不能壞：docs_check 現有 error／warning 數。失敗：本票造成新增任何一條 docs_check 的 error 或 warning。verifier 只比對改前改後的 error／warning 數，不比對索引全文。
- **priority：** must（理由：REQ-3 的「不得新增警告」與 REQ-8 (1) 都以本條為前提，本條若為 should 則兩者無可驗的基準）

## REQ-8　auth-rbac 領域索引的同步與否須有理由

- **statement：** 本票預設只改 `domains.yaml` 的登記（`paths` 與 `docs` 清單）。`docs/domains/auth-rbac.md` 是否同步（第 15 行程式入口、第 30 行測試清單、是否列 ADR-027），
  由 design 提出建議並寫明理由；REQ 不預決。兩條限制：
  (1) REQ-7 一律適用，即無論同步與否，docs_check 不得新增 error／warning。若選擇不同步，索引第 15 行與 `paths` 的字面落差是被接受的已知殘留，design 須記一行；
  (2) 本票預設不動 `auth-rbac.md`。human 對 H1 的答覆沒有提到領域索引文件，因此 REQ 保守要求（analyst 的讀法，並非既有規則或 human 的明文）：若 design 建議同步，須先取得 human 明確核可才可執行。
  旁證（非直接依據）：`docs/agent-team/checkpoint.md` 步驟 4（邏輯變更要問，不自行決定）與 `agents/most-doc-sync.md` 前置條件 1（無明確核可訊號不動作）、前置條件 3（目標文件路徑來自 `domains.yaml` 的 `docs`；`auth-rbac.md` 不在任何領域的 `docs` 清單，故前置條件 3 並不直接管到它）。
- **驗收意圖：** 不能壞：REQ-7 的 docs_check 結果；`auth-rbac.md` 在未取得核可前內容不變。
  失敗：`auth-rbac.md` 在沒有 design 理由與 human 核可的情況下被改；或 design 對同步與否未表態。
- **priority：** should

---

## 票面與現況出入

- log 指路：該票 log 目前三條皆為建票與轉移紀錄，未記出入；出入由本節詳列，orchestrator 視需要補記。
- REQ 節詳列：
  1. 票面「outbox 相關領域登記不全」：outbox 的**程式**已登記在 auth-rbac（證據 4）；實際漏的是測試、migration、ADR-027，且「測試沒領域」是全面現象（證據 5）。以此處為準。
  2. 票面「i18n 資源檔也算進去」：屬實但只是雙重命中，i18n 檔不會因收窄變無主（證據 3、7）。
  3. 票面「要做」的收窄寫法會讓 check_8 出 7 條 ERR（證據 7），票面未提；以此處為準，該 7 檔的去處由 design 提案（REQ-3）。
  4. 票面 `權威文件` 把 `docs/domains/auth-rbac.md` 與 ADR-027 並列；前者是領域索引（派生文件，以 `domains.yaml` 為準），後者是被登記對象，關係不同，見「對應文件」。
  5. 票面「現況 (b)」及 BACKLOG 原條目稱「`tests/integration/test_outbox_api.py` 等 outbox／RBAC 的整合測試」；字面含 RBAC 測試，但「要做」只寫 outbox 的對應整合測試。
     human 已答覆 RBAC 的整合測試不納入本票（見「需要 human 決的點」Q1），以此為準。
- 誰的判讀待誰確認：以上皆為 analyst 判讀，待 reviewer(req) 與 human 確認。

## 票面指 PROCESS-RECORD 時怎麼用

無。（本票未指向過程紀錄；DW-38 的基線 `domain-map.txt` 僅作為與本 REQ 自己實跑結果相互印證的旁證，不作依據。）

## 票面用集合詞未列舉時的判讀

- 集合詞：「outbox／RBAC 的整合測試」「等」、「與認證無關的前端檔」。
- 判讀清單（analyst 讀法）：
  - outbox 測試 = `tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py`（兩檔檔名含 outbox，已查實存在）。
  - 「RBAC 的整合測試」= 不做（human 已答覆，見 Q1）。
  - outbox 的 migration（v2_0032、v2_0033）= 不做（human 已答覆，見 Q2）。
  - 「與認證無關的前端檔」= 至少 `shared/i18n/` 9 檔（REQ-1、REQ-2 已鎖）；`shared/api/useActiveRuleSet.ts`（讀 rule-set 啟用旗標）、`config.ts`、`workspace.ts`、`ui/` 5 檔是否與認證有關，analyst 不判，交 design 提案（REQ-3）。
- 待確認者：human（透過 orchestrator）；Q1、Q2 已答，餘者為 design 輸入。

## 不立條

- 不立「新增 outbox 專屬領域 vs 併入 auth-rbac」：這是解法選擇，屬 design 的輸入。兩種做法的機械後果已在副本實跑過，但 REQ 不預決，由 design 取捨並自行重跑。
- 不立「補 outbox 的專屬 spec」：`docs/domains/auth-rbac.md` 已記為另一張票的缺口，本票不處理。
- 不立「讓 check_8 也掃 tests／migrations／docs」：這是擴大檢查能力，屬新能力，若要做應另開票（見 Q4）。
- 不立 ADR：本票是 agent 設定登記（`domains.yaml` 的 `paths`／`docs`），不新增架構決定，因此不立 ADR；ADR-027 只被登記，不被改寫。
  若 design 發現本票其實需要一項新的架構決定，須回報，不得自行立 ADR。
- **不做（human 已答覆，見 Q1、Q2）：**
  - outbox 以外（auth-rbac 其餘）的測試，如 `test_admin_users*.py`、`test_audit*.py`、`test_search.py` 及整個 `tests/` 的領域覆蓋，不在本票；
  - outbox 的兩支 migration（`v2_0032_outbox_events.py`、`v2_0033_outbox_event_no_unique.py`），不在本票。
  - 另開票的邊界：上述兩項若日後另開票，其內容與範圍由該票決定；本票不替它決定、不為它預留登記，也不因本票的設計而使它更難做或更易做（REQ-6 要求這些檔的命中維持現狀）。
- 不立「若新增領域則缺索引警告」之類的解法例：新增領域導致 docs_check 新增警告，已由 REQ-7 的「不得新增」一般性涵蓋，不在 REQ 內舉解法。

## 需要 human 決的點

**已答覆（human Howard，2026-10-24，手打原話「按你建議」，回應 orchestrator 提出的三題與其建議；orchestrator 的建議即其答案）：**

- **Q1（已答）　outbox 以外的測試是否納入：** 不納入本票，另開票。落實為「不立條」之「不做」與 REQ-6。
- **Q2（已答）　outbox 的兩支 migration 是否納入：** 不納入本票。落實同上。
- **H1（已答）　本票是否構成「邏輯變更」：** 只動 `domains.yaml` 的 `paths` 與文件登記，**不算** MOST 規則所說的「邏輯變更」。
  **前提（為 REQ-5 既有條件，非 human 補述）：** REQ-5 的 invariants 不動。若 design 日後需要動 invariants 或 i18n 領域任何欄位，仍屬邏輯變更，須 human 另行裁決（REQ-5）。
  下游影響：原 H2（7 檔去處）、H3（`useActiveRuleSet.ts` 去留）不再需要 human 裁決，併入 design 輸入（REQ-3）；原 H4（是否同步 `auth-rbac.md`）併入 REQ-8；原 H5 併入 REQ-5。
  這個答覆**只涵蓋** `domains.yaml` 的 `paths` 與文件登記；它不等於核可修改 `docs/domains/*.md` 或 ADR 內容（REQ-8、「對應文件」）。

原題與 orchestrator 建議的全文見該票 log。

**仍待 human（可選）：**

- **Q4　是否另開票讓 check_8 涵蓋 tests／migrations**（證據 6）。不在本票，僅供 human 決定要不要另開。
- **Q5　`src/frontend/e2e/i18n-review.spec.ts` 同時命中 `i18n`（`i18n-*.spec.ts`，311 行）與 `auth-rbac`（371 行，註解稱為角色可見性斷言）。**
  這是另一處疑似雙重命中，票面未提；預設不處理（REQ-6 範圍外），human 如要處理須另行指示。

## 未決問題（非 human 裁決項）

- **Q3　`shared/ui/*`、`workspace.ts`、`config.ts`、`useActiveRuleSet.ts` 的歸屬線索**：analyst 不判，由 design（architect）提案（REQ-3）。
- **Q6　`docs/domains/auth-rbac.md` 第 9、31 行提到的 outbox spec 缺口所屬的另一張票**，與本票無相依；REQ 不改變其狀況。

---

## 修訂紀錄

REQ 定案後凍結。修訂＝**開新版**＋舊版標 `superseded_by`＋**重新核可**，不就地改寫
（`rules/doc-taxonomy.md` §1.9；誰可改見同檔 §1 總表 REQ 列）。形狀借 `templates/ACC.md` §5；
`依據` 欄記來源。

| 版本 | 日期 | 依據 | 核可 | 受影響項 |
|---|---|---|---|---|
| v1 | 2026-10-24 | 初版：`ticket.md` 現況／要做／範圍、BACKLOG 原條目、analyst 副本實跑查證 | reviewer(req) 第 1 輪 PASS 附條件（`review-req.md`）；human 核可視深度而定 | — |
| v1 修訂稿（仍為 Draft，未定案） | 2026-10-24 | `review-req.md` 建議 S1～S6；human 2026-10-24 對 Q1／Q2／H1 的答覆（「按你建議」）。定案由 orchestrator 依流程處理，本稿不宣稱定案 | 待 reviewer(req) 複審 | 開頭自述（S5）、證據 6／8／10 與重現指令（S5、S6）、REQ-3（S2、S4）、REQ-4（S1）、REQ-5（H5 併入）、REQ-6（S1）、REQ-7（S4）、新增 REQ-8（H4）、不立條（S1、S3、S4）、需要 human 決的點（H1、Q1、Q2 已答；H2、H3 併入 design；Q3 移出） |
| v1 修訂稿二（仍為 Draft，未定案） | 2026-10-24 | `review-req.md` 第 2 輪 PASS 的建議 R2-S1～R2-S5（逐項採納）；H1 前提註明為 REQ-5 既有條件。定案由 orchestrator 依流程處理 | 待 orchestrator／human 依流程 | REQ-5（R2-S3 新增領域邊界）、REQ-7（R2-S2 標題與說明、R2-S5 升 must）、REQ-8（R2-S1 依據改寫、R2-S2 殘留記一行）、需要 human 決的點（R2-S4 指路 log；H1 前提註） |
| v1 定案 | 2026-10-24 | reviewer(req) 兩輪審查結論（`review-req.md`：第 1 輪 PASS 附條件、第 2 輪 PASS 附條件，皆無阻擋項）；human 2026-10-24 對 Q1／Q2／H1 的答覆「按你建議」（原題與建議全文見 `state.yaml` log）；human 2026-10-24 手打「授權G2」。L1 的 requirement 階段由 reviewer(req) 把關，免 human 核可 REQ 本身（`rules/stage-table.md` §6） | 狀態由 Draft 改為已定案（`rules/doc-taxonomy.md` §1.8）；本列為唯一改動，條文內容未動；REQ 無 hash 欄位（hash 綁定只在 ACC ↔ DESIGN，`rules/stage-table.md` §8） | 僅檔頭狀態欄 |
