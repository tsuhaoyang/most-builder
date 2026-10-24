# BL-ENG-13 reviewer(req) 第 1 輪審查報告
審查對象：ddm-v2/tickets/BL-ENG-13/requirements.md（Draft v1，未 commit）
代存說明：reviewer 無寫入權限，以下為其回報原文，由 scribe 原樣代存，未改動。

## type / 範圍
- review_type: req　diff 範圍: /home/howard/workspace/most-builder/ddm-v2/tickets/BL-ENG-13/requirements.md（Draft v1，未 commit）
- 副本：/tmp/claude-1000/-home-howard-workspace-dev-workflow/8a1f69a5-911b-4e2d-95de-9b7ade958d01/scratchpad/rv_req/（我自己從真實 most-builder 重建：rsync 排除 .venv／node_modules／graphify-out／各 cache／.git 後 git init）。所有探測都在副本做，用 python3 -B 並設 PYTHONDONTWRITEBYTECODE=1。真實 most-builder 只讀，沒有寫入。

## 結論：PASS（附條件，無阻擋項）
REQ 的事實全數查證相符，REQ-1 到 REQ-7 都可變成機械 ACC，沒有越界做 design 決定，沒有預先替 human 決定。
有幾項「design 結案前必須先收斂」的範圍與歸類問題，列在建議項 S1 到 S3。它們不阻擋 design 開始，但依 stage-table §1.2（design 不得留未決項），人沒答之前 design 不能定案。

## 阻擋項
無。
逐項核對阻擋判準：不可驗證（無）、含實作決定（無，見下）、越票範圍未標待 human（無，Q1／Q2／Q4／Q5 都標了）、懸空引用（無）、條目互斥（無）、出現 BL-ENG-13 以外的 BL-ENG 編號（無）。

## 建議項
- **S1（Q1、Q2 是範圍題，REQ 階段就該收斂，不宜帶進 design）。**
  - Q1：票面「現況 (b)」原文是「test_outbox_api.py 等 outbox／RBAC 的整合測試沒有任何 glob 覆蓋」，字面包含 RBAC 測試。
  - 「要做」只寫 outbox 的對應整合測試。REQ 把 RBAC 測試排除（理由：全面缺口、範圍較大），這是對票面現況的縮小，REQ 已誠實標成 Q1，方向對。
  - 但這是「做／不做」，屬 REQ 該收斂的範圍，不是 design 輸入。
  - Q2（migration 0032／0033）同理。
  - 建議由 orchestrator 在 REQ 定案前取得 human 答覆。
  - 我的推薦：Q1 不納入，另開票；Q2 不納入，migration 是一次性腳本，票面未提。
  - 若 human 要納入，就加一條 REQ（建議 should）。
- **S2（H2 與 Q3 的語意循環）。**
  - Q3 說「由 design 判斷各檔屬哪個領域，再交 human 裁決（H2）」。REQ-3 又寫「去處由 human 裁決後在 design 落實」，順序互相矛盾。
  - 分類建議：把 7 個無主檔放哪，實質上是 design 輸入，由 architect 提案。
  - human 只在 H1 判定「改變歸屬／觸發的 reviewer 算邏輯變更」時才需裁決。
  - 建議把 REQ-3 的「由 human 裁決」改成「由 design 提案；是否需 human 裁決取決於 H1」。
  - 同理，H4（是否同步 auth-rbac.md）是 H1 的下游：most-doc-sync.md 前置條件第 1 點確實是「邏輯變更核可後才改文件」，所以 H4 可併入 H1。
  - H5 與 REQ-5 重複，可併入 REQ-5。
- **S3（票面「範圍」欄寫「是否另需 ADR 待 requirement／design 階段定」，REQ 沒有直接答）。**
  - 建議在「不立條」補一句：本票是 agent 設定登記，不新增架構決定，不立 ADR。ADR-027 只被登記、不被改寫。
  - 或明說交 design。
- **S4（REQ-3、REQ-4 的措辭帶微量解法）。**
  - REQ-3 的「命中某領域，或進 no_domain_allowlist」等於列舉解法選項。
  - REQ-7 的括號舉了「新增領域會缺索引警告」。
  - 兩者都只是限制條件或失敗例，不構成決定，不擋。
  - 若要更純，可把括號例移到「不立條」。
- **S5（REQ 內容與自述有輕微不一致）。**
  - 開頭宣稱「本 REQ 未讀 MOST 的實作邏輯」，Q3 也說 analyst「刻意不讀實作」。
  - 但證據 8 引了 `shared/config.ts` 第 3 行的 `TMU_SEC = 0.036`，那是讀了實作檔內容（我查證該行屬實）。
  - 建議改成「只讀了登記與檢查腳本的匹配段，另點讀 config.ts 一行作為白名單判準的反例」。
  - REQ 開頭引的 scratchpad 路徑在重開機後會消失，不是 durable 證據。建議補上可重跑的指令（見本報告「重現」）。
- **S6（小）。** 證據 6 說 check_8 掃 ts／tsx 沒提 `api.d.ts`。check_8 的 docstring 說排除產生檔 api.d.ts，但實際程式的 glob 沒排除，且它命中 auth-rbac。不影響結論。

## 移交
- 留給 design（不裁決）：outbox 併入 auth-rbac 還是新增領域；7 檔去處；ADR-027 登記到哪個領域；具體 glob 寫法。REQ 都沒預決，正確。
- 升 human：H1（見分類）；Q1、Q2 的做／不做（S1）。

## 誤報（附證據）
- 疑慮：REQ 把 H1 引的「邏輯變更」定義寫成來自 `domain_guard.py render`，是否有出處？
  - 證據：`scripts/agent_team/domain_guard.py` 第 141 行確有「若這次改動或討論會**改變**上述任一條規則的語意，先問使用者要不要更新邏輯」。
  - checkpoint.md 步驟 4 與 most-logic-reviewer.md 第三步「變更提案」一致，出處成立。
  - AGENTS.md 本身沒有「邏輯變更」定義字樣，我已 grep 確認，並不矛盾。
- 疑慮：REQ-5 說 i18n 領域全欄不動，會不會被 shared/** 收窄牽動？
  - 證據：見重現 (d)，收窄前後逐欄比對只有 auth-rbac.paths 不同。

## 我重現的指令與結果（副本：.../scratchpad/rv_req/ddm-v2；原檔備份 .../rv_req/domains.orig.yaml）
- **(a) shared/ 清單與命中。**
  - `find src/frontend/src/shared -type f` 得 20 檔，分佈與 REQ 證據 2 一致。
  - 對每檔跑 `domain_guard.py map`：`shared/i18n/` 9 檔命中 `i18n,auth-rbac`；其餘 11 檔（api 2、auth 1、types 1、ui 5、config.ts、workspace.ts）只命中 `auth-rbac`。與 REQ 證據 3 完全相符。
  - 基線 `check_agent_config.py`：`所有業務檔（264 檔）都命中領域或在白名單`，`16 ok, 0 warn, 0 error`。
- **(b) 收窄後 check_agent_config.py。**
  - 我把 `domains.yaml` 的 `shared/**` 換成 `shared/api/**`、`shared/types/**`、`shared/auth/**`。
  - 結果 `-- 15 ok, 0 warn, 7 error --`。
  - 7 條 ERR 恰為：config.ts、workspace.ts、ui/ComboBox、ErrorBoundary、Hint、RuleSetUnavailable、WorksheetRequiredNotice。與 REQ 證據 7 逐檔相符。
  - 收窄後 `shared/i18n/` 9 檔只命中 `i18n`；client.ts、useActiveRuleSet.ts、useMe.ts、api.d.ts 仍命中 `auth-rbac`。
- **(c) outbox 登記現況。**
  - `outbox_service.py`、`models/v2/outbox.py`：命中 auth-rbac。
  - `tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py`、`migrations/versions_v2/v2_0032_outbox_events.py`、`v2_0033_outbox_event_no_unique.py`、ADR-027：全部命中 0 領域。
  - `domains.yaml` 內 `ADR-027` 無命中；整檔 `grep -c "tests/"` 為 0；`tests/integration/test_admin_users.py` 命中 0。
  - 另試「併入」：把兩個 outbox 測試檔加進 auth-rbac.paths，`map tests/unit/test_outbox.py` 命中 auth-rbac，docs_check 警告數仍是 13（不變）。
  - 已用 git checkout 還原副本，沒有留下改動。
- **(d) invariants 與 i18n 欄位。**
  - 用 yaml 載入原檔與收窄後檔，逐領域逐鍵比對：只有 `auth-rbac.paths` 不同。
  - `auth-rbac.invariants` 相等 True；`i18n` 整個區塊相等 True；`no_domain_allowlist` 相等 True。
- **docs_check。** 收窄前後「領域索引檔名」「程式入口」兩項皆 OK，總 WARN 數都是 13（副本無 graphify 圖，圖那條 warn 在其中）。
- **硬規則 grep。**
  - 用 `/usr/bin/grep -rn "BL-ENG-[0-9]*"` 掃 `tickets/BL-ENG-13/`，沒有任何 BL-ENG-13 以外的編號。
  - REQ 內 state／stage／depth 字樣只有一處：第 127 行「`state.yaml` 的 log」，是檔名指路，不是寫入狀態，OK。
  - `ls` 該目錄只有 requirements.md、state.yaml、ticket.md。

## 抽查的事實（共 14 處）
1. BACKLOG 原條目在 289–296 行：相符（289 標題、296 公版票形）。
2. auth-rbac 區塊 349–378 行：相符（349 `- id: auth-rbac`，376 `invariants:`，377、378 為兩條）。
3. `shared/**` 在第 368 行：相符。
4. `outbox_service.py` 在 355 行、`models/v2/outbox.py` 在 361 行：相符。
5. anchors 含 `outbox_service`（351 行）、keywords 含 `outbox`（375 行）：相符。
6. i18n 領域 `shared/i18n/**` 在 307 行、invariants 在 320–324 行：相符。我只用 sed 看到 300–326 行，且 320 行是 `invariants:`、其下 4 條；i18n 的 `paths` 列從本次輸出看不出 307 行的絕對行號，未逐行核。
7. shared 20 檔的分佈與檔名：相符。
8. 7 條 ERR 的檔名與 `15 ok, 0 warn, 7 error`：相符。
9. 264 個業務檔、基線 16 ok：相符。
10. `shared/config.ts` 第 3 行 `export const TMU_SEC = 0.036`：相符。
11. ADR-027 第 64 行 `### 5. DDM 採用事實以 review event + transactional outbox 發布`：相符。
12. `docs/domains/auth-rbac.md` 第 15 行（shared/** 在程式入口）、第 30 行（四類測試）、第 9、31 行（BL-DOC-4 缺口）：相符。
13. check_8 在 275 起、只掃 `src/ddm_v2/**/*.py` 與 `src/frontend/src/**/*.ts(x)`、tests／migrations 不掃、有 ERR 退出碼 1：相符。我確認了 `return 1 if errors else 0`；REQ 說在 372 行，我只看到 368–374 區段含該句，未逐行核到 372。
14. docs_check 程式入口檢查規則是「有交集」（約 219–236 行）、`e2e/i18n-review.spec.ts` 同時命中 `i18n` 與 `auth-rbac`、11 個領域（REQ-6 的「其餘 10 個」名單與實際一致）：相符。
- 另：decisions.log 的 `2026-09-22 （測試基礎建設）` 一列記到過 `tests/integration/test_outbox_api.py`，與「改了它沒人把關」互相印證。

## 對 H1 到 H5、Q1 到 Q6 的分類判斷
| 項 | 我的分類 | 理由 |
|---|---|---|
| H1 本票是否構成邏輯變更 | 真的只能 human 決 | 定義在 domain_guard 與 checkpoint 步驟 4，是 invariants 語意，paths 登記是否算由 human 判。REQ 寫「可能不算」並標為 analyst 讀法，沒有預先定案，正確。它也是 H2、H4 的上游。 |
| H2 7 檔去處 | 主要是 design 輸入；human 僅在 H1=是 時才需 | 見 S2。目前 REQ-3 與 Q3 順序矛盾。 |
| H3 useActiveRuleSet.ts 去留 | design 輸入，併入 H2／Q3 | analyst 不判是合理的。 |
| H4 是否同步改 auth-rbac.md | 依賴 H1，可併入 H1 | most-doc-sync 前置條件是核可後才動；預設只改 domains.yaml 合理。 |
| H5 動 invariants 要回報 human | 與 REQ-5 重複，應併入 REQ-5 | 內容本身正確：invariants 被動就是邏輯變更，必須 human 裁決。 |
| Q1 其他測試 | 應在 REQ 階段由 human 收斂（範圍） | 見 S1，注意它與票面現況字面有落差。 |
| Q2 migration | 同 Q1 | 同上。 |
| Q3 ui／workspace／config 歸屬 | design 輸入 | 見 S2。 |
| Q4 另開票擴大 check_8 | 正確：不在本票，只是供 human 決定要不要另開票 | 這是新能力，REQ 切出去正確。 |
| Q5 i18n-review.spec.ts 雙重命中 | 範圍外決定，預設不處理 | REQ-6 已鎖死範圍；我確認它確實雙重命中。 |
| Q6 outbox spec 缺口 | 純資訊，無相依 | BL-DOC-4 在 auth-rbac.md 第 9、31 行屬實。 |
- 有沒有漏掉應交 human 的邏輯變更：沒有。
  - 本票預設只動 `paths`／`docs` 登記，invariants 與 i18n 全欄逐字不變（重現 (d)）。
  - 唯一灰色地帶是「改變哪個 reviewer 被觸發」算不算邏輯變更，已列為 H1。
  - 可能影響 reviewer 覆蓋的變動（移出 auth-rbac 的 7 檔、ADR-027 登記）已被 H1／H2 涵蓋。
- 有沒有把 human 決定預寫成已決：沒有。REQ-3 與 H2 的措辭問題見 S2，屬順序矛盾，不是預決。

## 對 REQ 的整體評價
- 完整涵蓋票面「現況」「要做」「範圍」，補上了「影響」與「對應文件」。
- 對票面與現況出入的處置合理：
  - 「outbox 領域登記不全」實為程式已登記、漏的是測試／migration／ADR；
  - 票面建議的收窄確實會讓 check_8 出 7 條 ERR，我重現屬實。
  這是原票未提的重要發現，REQ 把它轉成 REQ-3，並把 7 檔去處明列。
- 範圍切分得當：沒有夾帶讓 check_8 涵蓋 tests／migrations，那被切為 Q4。
- 驗收意圖大多已具體到可轉成機械 ACC，例如收窄後 `map` 命中、check_agent_config 0 error、invariants 逐字比對、docs_check 警告數不變。
- 足以讓 architect 開始設計。
- design 能否定案取決於 H1，以及 Q1／Q2 的範圍答覆（S1）。建議 orchestrator 在 REQ 核可前先向 human 取得這三項的答覆。
- 依 `reviewer.md`，REQ 審查 PASS 後 L1 不需要 human 核可 REQ 本身，但 H1／Q1／Q2 是獨立的 human 問題。

## 第 2 輪（審查對象：requirements.md 修訂稿，Draft，未 commit）
代存說明：reviewer 無寫入權限，以下為其第 2 輪回報原文，由 orchestrator 代存；其中兩處字樣有縮短（重現指令節的 sed 指令寫法、抽查節的編號 grep 指令寫法），其餘未改動。

## type ／ 範圍
- review_type: req（第 2 輪）　diff 範圍: /home/howard/workspace/most-builder/ddm-v2/tickets/BL-ENG-13/requirements.md（修訂稿，Draft，未 commit，237 行）
- 副本：/tmp/claude-1000/-home-howard-workspace-dev-workflow/8a1f69a5-911b-4e2d-95de-9b7ade958d01/scratchpad/rv_req2/（按 REQ 的 rsync 指令自建）。真實 most-builder 只讀，沒有寫入。用 python3 -B 並設 PYTHONDONTWRITEBYTECODE=1。

## 結論：PASS（附條件，無阻擋項）
S1～S6 都實質落地。REQ-8 沒有越出票面範圍，但它第 (2) 條的依據有一半站不住（見專項判斷）。human 的三個答覆沒有被加料成他沒說過的話。修訂後的 REQ 足以讓 architect 開始設計。

## 阻擋項
無。逐項核對：不可驗證、含實作決定、越範圍未標、懸空引用、條目互斥，都沒有。出現 BL-ENG-13 以外的 BL 編號：無。

## 建議項
- **R2-S1（REQ-8 (2) 的依據措辭，建議改）。** 現寫「`agents/most-doc-sync.md` 前置條件 1：無明確核可訊號不動作」。
  - 前置條件 1 規範的是「呼叫 most-doc-sync 前要有核可訊號」。該角色的描述是「核可某項邏輯變更後」才寫文件，目標檔只能來自 `domains.yaml` 的 `docs`（前置條件 3）。
  - `docs/domains/auth-rbac.md` 是領域索引，不在任何領域的 `docs` 清單。我 grep `domains.yaml` 找不到 `docs/domains`。所以這條前置條件並不直接管到它。
  - H1 又已說本票不算邏輯變更。照字面，most-doc-sync 的核可前提和本票是脫鉤的。
  - 結論：(2)「須帶到 human 核可才可動 auth-rbac.md」是 analyst 的保守限制，方向安全（多問而不是少問），但不是 most-doc-sync 規則推出來的，也不是 human 說的。
  - 建議改寫成：「本票預設不動 auth-rbac.md。human 對 H1 的答覆沒有提到領域索引文件，因此 REQ 保守要求同步前先取得 human 明確核可」。依據改引 `docs/agent-team/checkpoint.md` 步驟 4 加 most-doc-sync 前置條件 1、3 作旁證，並標明這是 analyst 的讀法。
- **R2-S2（REQ-7 標題與 REQ-8 允許的結果有張力）。**
  - REQ-7 標題是「領域索引與登記表不得互相矛盾」。
  - 但 REQ-8 允許 design 選「不同步」，此時 auth-rbac.md 第 15 行仍寫 `shared/**`，與收窄後的 `paths` 在字面上不一致。docs_check 只查「有交集」，所以仍 OK。
  - 驗收只看 docs_check，標題卻說「不矛盾」，會讓 verifier 以為要比對全文。
  - 建議標題改成「領域索引檢查不得新增 error／warning」，或在 REQ-8 明講「不同步時，索引第 15 行與 `paths` 的字面落差是被接受的已知殘留，需在 design 記一行」。
- **R2-S3（新領域時 H1 前提的適用性未講）。**
  - 不立條已說「outbox 併入或新領域」留給 design。若 design 選新領域，就要新增一個領域區塊，裡面必然有 `invariants`，還要新增領域索引檔，否則 docs_check 多一條警告。
  - REQ-4 驗收寫「被選為歸屬的領域其 invariants 文字不變」，對新領域無意義。H1 的前提只涵蓋 `paths` 與文件登記，不涵蓋新增 invariants。
  - 建議 REQ-5 或 REQ-4 補一句：若 design 要新增領域（需新增 `invariants` 與索引檔），該部分不在 H1 答覆內，須回報 human。這是補規則邊界，不是預決解法。
- **R2-S4（human 答覆的原問題與建議沒有 durable 記錄）。**
  - REQ 說 orchestrator 的建議即其答案，但 REQ 與 `state.yaml`（`open_questions: []`、log 無 Q1／Q2／H1 條）都沒有 orchestrator 當時的原題與建議全文。
  - 現在 Q1／Q2／H1 的內容只能由 REQ 轉述。H1 的措辭尤其關鍵，因為它決定 L1 要不要升 human。
  - 建議 orchestrator 在 `state.yaml` log 逐字記：原題、建議、human 原話「按你建議」。這是 orchestrator 的工作，不是 REQ 的缺陷。
- **R2-S5（小）。** REQ-7 為 should，但 REQ-3、REQ-8 (1) 都以它為硬前提。建議升 must，或說明 should 的理由。

## 第 1 輪各項複核（逐處回檔核對）
- **S1（Q1／Q2 收斂）：落地，正確。**
  - 「不立條」之「不做」列出非 outbox 測試與兩支 migration。REQ-4 括號、REQ-6 末句、「判讀清單」都一致引用。
  - 票面「要做」只寫「outbox 登記領域並把對應整合測試納入」。「現況 (b)」的 RBAC 測試字面確被縮小，但 REQ 在「票面與現況出入」第 5 點如實標出，並引 human 答覆。不與「要做」衝突。
- **S2（H2／Q3 循環）：落地，正確。**
  - REQ-3 改為「去處由 design 提案」，不再寫「human 裁決」。Q3 移到「未決問題（非 human 裁決項）」。H2、H3 併入 design 輸入。
  - 順序矛盾已消。REQ-3 引 H1 說不需另走 human，並註明前提是 REQ-5。
- **S3（不立 ADR）：落地。** 「不立條」有「不立 ADR…ADR-027 只被登記，不被改寫；design 若發現需新架構決定須回報」。
- **S4（解法措辭）：部分落地，可接受。**
  - REQ-7 的括號例移到「不立條」末條。REQ-3 仍留「命中某領域，或在 no_domain_allowlist 且合白名單判準」。
  - 這是引用 check_8 既有合格條件，不是選解法，不擋。
- **S5（自述一致）：落地。**
  - 開頭改成「讀了什麼…少數點讀的行（`shared/config.ts` 第 3 行…）；未讀各業務檔的實作邏輯」。與證據 8 一致。
  - scratchpad 路徑已移除，改為「重現指令」節（可重跑，見下）。
- **S6（api.d.ts）：落地且查證屬實。**
  - 證據 6 新增 docstring（276–278 行）與實際 glob 不一致的說明。我確認 check_8 的 glob 為 `**/*.ts`，只排除 `__pycache__`，沒有排除 api.d.ts。
  - 該檔在 264 檔內，因 `shared/**` 命中 auth-rbac。
- 順帶：H4 併入 REQ-8、H5 併入 REQ-5、H2／H3 併入 design，與修訂紀錄表一致。

## 我重現的指令與結果
照 REQ「重現指令」節，在 rv_req2 副本逐行執行。
- 基線 check_agent_config.py 最後一行：`-- 16 ok, 0 warn, 0 error --`。與聲稱相符。
- 對 shared 下 20 檔逐檔跑 domain_guard.py map：`shared/i18n/` 9 檔命中 `i18n,auth-rbac`；其餘 11 檔只命中 `auth-rbac`。與證據 2、3 相符。
- 六個 outbox／測試／ADR 檔（`test_outbox_api.py`、`test_outbox.py`、`test_admin_users.py`、`v2_0032`、`v2_0033`、ADR-027）：皆 `[]`。與證據 4、5 相符。
- 把 368 行換成 api／types／auth 三條後：`-- 15 ok, 0 warn, 7 error --`。7 條 ERR 為 `config.ts`、`workspace.ts`、`ui/` 下 ComboBox、ErrorBoundary、Hint、RuleSetUnavailable、WorksheetRequiredNotice。與聲稱完全相符。
- docs_check.py 最後三行：改前、改後皆 `-- 4 ok, 13 warn, 0 error --`。證據 10 屬實。
- 指令可重跑，不寫真實 repo。副本確實需要 repo 根的 `CLAUDE.md`、`AGENTS.md`，rsync 已含，REQ 括號說明正確。
- 真實 repo `git status`：只有既有的 `M state.yaml` 與未追蹤檔，探測沒有留痕。

## 抽查的事實與結果（共 12 處，皆相符）
1. `domains.yaml` 368 行為 `"src/frontend/src/shared/**"`，auth-rbac 區塊 349 起；`invariants` 兩條在 377、378 行（我 sed 349–378 看到）。
2. `outbox_service.py`、`models/v2/outbox.py` 在 auth-rbac 的 `paths`。anchors 含 `outbox_service`，keywords 含 `outbox`。
3. `domains.yaml` 307 行 `shared/i18n/**`，311 行 `e2e/i18n-*.spec.ts`，371 行 `e2e/i18n-review.spec.ts`（在 auth-rbac）。i18n `invariants` 320–324 行。
4. 整檔無 `ADR-027`、無 `tests/` 字樣（grep ADR-027 無命中）。
5. `checkpoint.md` 第 18 行 `domain_guard.py map $FILES`；第 28 行「每個命中領域一個 most-logic-reviewer」；步驟 4 為邏輯變更詢問，步驟 5 為設定一致性。
6. `check_agent_config.py`：`check_8` 起於 275 行，`return 1 if errors else 0` 在 372 行。docstring 276–278 行寫排除 api.d.ts，實際 glob 未排除。
7. `docs_check.py`：`check_domain_index_matches` 起於 204 行，程式入口比對（有交集）在其內約 219–236 行，檔名比對在 216–218 行。
8. `shared/config.ts` 第 3 行 `export const TMU_SEC = 0.036`。
9. ADR-027 第 64 行 `### 5. DDM 採用事實以 review event + transactional outbox 發布`。
10. `docs/domains/auth-rbac.md`：第 9、31 行提 BL-DOC-4 缺口，第 15 行程式入口含 `shared/**`，第 30 行測試清單含 `test_outbox_api.py`。
11. `agents/most-doc-sync.md`（正本在 `docs/agent-team/agents/`）：前置條件 1 為明確核可訊號，3 為目標路徑來自 `domains.yaml` 的 `docs`；「改任何 docs/ 後必先跑 docs_check」屬實。REQ-8 的引用位置準確，但解讀見專項判斷。
12. `domains.yaml` 21 行起白名單判準註解「純結構／框架接線／設定／通用基底，無業務邏輯」與證據 8 引述相符。
- 編號 grep：REQ 內只出現 BL-ENG-13（第 4 行），無其他 BL-ENG、無 BL-DOC。BL-DOC-4 只在 auth-rbac.md，REQ 以「另一張票」帶過。
- 預決 design 檢查：REQ 沒有寫具體 glob、沒有選 outbox 併入或新領域、沒有決定 7 檔去處、沒有指定 ADR-027 登記到哪個領域。

## 對 REQ-8 的專項判斷
- **是新需求還是改寫？** 是改寫。原 H4（是否同步 auth-rbac.md）是第 1 輪就有的待決題。ticket.md 的「權威文件」欄本就列了 `docs/domains/auth-rbac.md`，所以沒超出票面範圍。改變的是形狀：由「待 human 決」變成「design 提建議，執行前取 human 核可」。
- **限制 (1)（REQ-7 一律適用）：成立。** 與 REQ-7 一致，docs_check 可機械驗證。
- **限制 (2)：方向安全，依據只有一半。**
  - 依據：(a) most-doc-sync 前置條件 1 要明確核可；(b) H1 的答覆只涵蓋 paths 與文件登記。
  - (a) 僅在呼叫 doc-sync 時直接適用，且該角色的目標檔必須來自 `domains.yaml` 的 `docs`。auth-rbac.md 不在其中，也就是 doc-sync 的前置條件 3 本來就不成立。所以 (a) 不能說是「規則要求」。
  - (b) 是 REQ 對 H1 範圍的讀法，而 human 實際只說了「按你建議」。把 H1 範圍標為「只涵蓋 paths 與文件登記」，與 orchestrator 提問時的內容一致，但 human 本人沒有說過「不涵蓋領域索引」。
  - 結論：這句話沒有把 human 的答覆延伸成 human 沒說過的授權。它反而是在 human 沒涵蓋的地方保守地多設一道門。但它被寫成似乎有規則與 human 雙重依據，措辭應修成「analyst 的保守讀法」（見 R2-S1）。屬建議，不阻擋。
- **有沒有與 stage-table 的「design 不得留未決項」衝突？** 沒有。(2) 約束的是「執行」，不是 design 定案。design 可以寫「建議同步，執行須 human 核可」，這是 human 關卡，不是未決的設計問題。唯 design 必須對同步與否「表態」，REQ 已要求。
- **可驗證性：** 文件層面可驗。
  - 「`auth-rbac.md` 在核可前內容不變」可用 `git diff` 驗。
  - 「design 對同步與否表態且有理由」可用文件檢查驗。
  - 「取得 human 核可」可由 `state.yaml` log 的記載驗，非機械但可追。
  - 唯一缺口：失敗條件的「在沒有 design 理由與 human 核可的情況下被改」是組合句，ACC 階段建議拆成兩項。

## 其他審查重點結論
- **human 三答覆的記法（重點 3）：**
  - 原話「按你建議」逐字引用，且明講是回應 orchestrator 的三題與建議，沒有擴寫成其他話，也沒有 human 說過別的話的暗示。
  - 「orchestrator 的建議即其答案」是對「按你建議」的合理讀法，但要靠 orchestrator 原題才能回查（R2-S4）。
  - H1 的前提（invariants 與 i18n 全欄不動）：第 1 輪審查時 REQ-5 已存在，第 1 輪報告的誤報節即引「REQ-5 說 i18n 領域全欄不動」。所以前提不是修訂時新增的，修訂只把 H5 併入並加上「超出需另裁」的句子。成立。
  - 第 210 行把前提寫在「H1（已答）」下，讀者可能以為前提是 human 說的；其實 human 沒有講前提。建議在該行補「（前提為 REQ-5 既有條件，非 human 補述）」。
  - Q4、Q5 維持待 human 合理：Q4 是新能力、Q5 是範圍外，且標明「可選」，不阻擋 design。
- **「不做」範圍（重點 4）：** 與票面「要做」不衝突。與「現況 (b)」字面的落差已如實標出。
  - REQ-6 新增「命中集合須維持現狀」可驗（對 migration 兩檔與 outbox 以外的測試跑 `map` 都應為 0 領域），也合理，因為它防止 design 用 `*outbox*` 之類寬 glob 順帶納入。
  - 一個小提醒：REQ-6 的比對範圍是「264 業務檔加點名檔」，不含 e2e 以外的 tests，所以「不做」的測試檔須另列在比對輸入，REQ-6 已寫「本票『不做』的檔命中集合也須維持」，可行。
- **自相矛盾／懸空引用（重點 5）：** 沒發現互斥條目。REQ-2 與 REQ-5 一致。REQ-6 的「其餘 10 個領域」與 domains.yaml 的 11 個領域扣掉 auth-rbac 相符。引用的 REQ、證據編號、Q 編號都能解析。

## 對 design 的就緒度
- 足以讓 architect 開始設計。
- design 定案前不缺 human 答覆，僅須處理：
  - 若 design 選新領域，新領域的 invariants 與索引檔要不要新增，需 human 裁決（R2-S3）。
  - 若建議同步 auth-rbac.md，需 human 核可（REQ-8）。
- Q4、Q5 為可選。
- orchestrator 建議在 REQ 定案前補 R2-S4 的記錄。
