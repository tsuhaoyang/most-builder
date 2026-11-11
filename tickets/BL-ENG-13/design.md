---
類別: DESIGN
狀態: 已定案
票: BL-ENG-13
上游: ["REQ-1", "REQ-2", "REQ-3", "REQ-4", "REQ-5", "REQ-6", "REQ-7", "REQ-8"]
凍結於: ACC 定案（rules/doc-taxonomy.md §1.9）
偏離: 無
hash取法: "於 repo 根（ddm-v2/）執行：set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' tickets/BL-ENG-13/design.md | tr -d '\\r' | sed 's/[[:space:]]*$//' | sha256sum"
---

# BL-ENG-13 設計

本檔只寫「要改成什麼、改哪一處、為什麼」。每節對應一條 REQ，標題固定（`DESIGN-<n>`），anchor 用標題。
本票只動 MOST 的領域登記（`docs/agent-team/domains.yaml`），不動程式、不動兩條 invariants、不動 i18n 領域任何欄位、不立 ADR。
所有事實標出處：`檔案:行號`（行號指 HEAD 加工作樹，僅供讀者定位，anchor 不用行號）或「副本實跑」。
**副本實跑**＝在 repo 外的暫存副本（rsync 重建，含 repo 根 `CLAUDE.md`、`AGENTS.md`，再 `git init`）上執行，真實 most-builder 內未執行任何 MOST 腳本；完整清單見末節「副本實跑紀錄」。

**設計結論（主案）：**

1. auth-rbac 的 `shared/**` 換成 `shared/api/**`、`shared/types/**`、`shared/auth/**`（DESIGN-1）。
2. 被移出的 7 檔全部進 `no_domain_allowlist`，各附理由；`useActiveRuleSet.ts` 留在 auth-rbac（DESIGN-3）。
3. outbox 的兩個測試併入 auth-rbac 的 `paths`，ADR-027 併入 auth-rbac 的 `docs`；不新增領域、不新增 invariants（DESIGN-4）。
4. `docs/domains/auth-rbac.md` 本票不同步，記殘留一行（DESIGN-8）。
5. 「新增 outbox 領域」是備案，因為它必然新增 invariants 與領域索引檔，不在 human 對 H1 的答覆內，列於「待決（升 human）」，主案不依賴它。

---

## DESIGN-1　auth-rbac 的前端範圍收窄為 api／types／auth 三個子目錄（對應 REQ-1）

把 auth-rbac 區塊 `paths` 的單條 `"src/frontend/src/shared/**"`（`domains.yaml:368`）換成三條：

| 位置 | 前 | 後 |
|---|---|---|
| auth-rbac `paths`（`domains.yaml:368`） | `- "src/frontend/src/shared/**"` | `- "src/frontend/src/shared/api/**"`<br>`- "src/frontend/src/shared/types/**"`<br>`- "src/frontend/src/shared/auth/**"` |

為什麼是這三條（用票面「要做」的原樣）：auth-rbac 的第 2 條 invariant（`domains.yaml:378`）的對象是 `shared/api/client.ts` 與 `shared/types/api.d.ts`，這兩個子目錄正是該 invariant 的主體；`shared/auth/useMe.ts` 是認證的前端入口（REQ-1 點名）。用子目錄 glob 而不用逐檔路徑，是因為 invariant 2 講的是「API 入口」這一類，日後 `shared/api/` 底下新增檔仍應被守。

結果（副本實跑，`domain_guard` 逐檔對全部 `shared/` 20 檔）：`client.ts`、`useActiveRuleSet.ts`、`useMe.ts`、`api.d.ts` 仍命中 `auth-rbac`；`shared/i18n/` 九檔由 `auth-rbac,i18n` 變為只剩 `i18n`。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#auth-rbac`（`paths` 欄）

## DESIGN-2　`shared/i18n/` 的歸屬由收窄自然達成，不改 i18n 領域（對應 REQ-2）

不新增任何針對 i18n 的編輯。i18n 領域已有 `"src/frontend/src/shared/i18n/**"`（`domains.yaml:307`）；DESIGN-1 移除了 auth-rbac 對這九檔的多餘命中後，九檔的命中集合恰為 `{i18n}`（副本實跑：9 檔皆輸出 `i18n`）。i18n 領域的 `paths`、`invariants`、`docs`、`keywords`、`anchors` 全欄逐字不動（副本逐欄比對：`i18n all fields identical: True`）。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#i18n`（唯讀，不編輯）

## DESIGN-3　被移出的 7 檔進白名單；`useActiveRuleSet.ts` 留在 auth-rbac（對應 REQ-3）

**判準**（`domains.yaml:20-21` 註解）：純結構／框架接線／設定／通用基底，無業務邏輯，每條附理由。`check_agent_config.py` 的 check_8 對白名單只做精確路徑比對（`rel in allow`），不認 glob，所以逐檔列。

為什麼不歸入既有領域：REQ-6 的驗收意圖要求其餘 10 個領域的全欄位不變，把這 7 檔加進 `wi-workbench`、`most-engine` 等任一領域的 `paths` 都會違反它。要走那條路，須由 human 另行裁決，本設計不採（記於下表 `config.ts` 列的否決方案）。

| 檔（`src/frontend/src/shared/` 下） | 去處 | 理由（寫進白名單的 `reason`） | 對判準的檢視 |
|---|---|---|---|
| `ui/ComboBox.tsx` | 白名單 | 通用可搜尋下拉元件，純呈現 | 讀碼：props 驅動的 UI 元件，無領域資料處理；符合「通用基底」 |
| `ui/ErrorBoundary.tsx` | 白名單 | React 錯誤邊界，框架接線 | 讀碼：React class 錯誤邊界；符合「框架接線」 |
| `ui/Hint.tsx` | 白名單 | ⓘ 提示元件，純呈現 | 9 行，單一 span；符合 |
| `ui/RuleSetUnavailable.tsx` | 白名單 | 錯誤態呈現元件，僅顯示傳入的 error 與 i18n 文案，無 rule-set 判斷邏輯 | 讀碼（22 行）：只組字串與 `t()`；名稱帶 rule-set 但無判斷；符合 |
| `ui/WorksheetRequiredNotice.tsx` | 白名單 | 無 worksheet 時的空狀態提示與跳轉按鈕（僅派送 tab 切換事件），介面接線 | 讀碼（33 行）：`goToCases` 只 `dispatchEvent`；符合 |
| `workspace.ts` | 白名單 | 跨領域共用的前端狀態容器（zustand store，僅 setter，無分支邏輯） | 讀碼（29 行）：兩個 setter、無條件式；被 `wi-workbench`、`level-system`、`import` 等多個領域的檔共同引用（grep `shared/workspace`），無單一領域歸屬，與 `exceptions.py`「跨領域共用，無單一領域歸屬」同型 |
| `config.ts` | 白名單 | 前端共用常數（作用中 worksheet 初始值、TMU→秒的顯示換算係數）；檔僅 5 行、兩個 `export const`，無函式與分支 | 見下 |

**`config.ts` 的 `TMU_SEC = 0.036`（`config.ts:3`）與「無業務邏輯」的張力，本設計的判斷：**

- 該檔共 5 行，兩個 `export const`，無函式、無分支、無計算。`TMU_SEC` 在前端只作「TMU 乘以係數得秒」的顯示換算（grep：`WiWorkbench.tsx`、`WiOutline.tsx`、`CasesPage.tsx` 等皆為 `x * TMU_SEC` 顯示）；前端不算 TMU 本身（`wi-workbench` 第 3 條 invariant，`domains.yaml:177`）。所以它是「常數」不是「邏輯」，符合「設定」。本設計不以其他白名單條目作類比，結論只依這份檔自身的事實。
- 但它是 MOST 方法的定義常數（1 TMU = 0.036 秒；後端 `models/v2/rule_set_tables.py:217` 的 docstring 也寫死 `ceil(sec/0.036)`），改它會讓全部畫面的秒數同時偏移。進白名單意味著它被改時**沒有任何 logic reviewer 被派**。後端權威常數是 `most_engine/rule_set_data.py:14` 的 `TMU_TO_SEC`，前端這份是重複常數，改動時沒有 logic reviewer 比對兩者。這是被接受的殘留（見「殘留項」R3），不是已被消除。
- 被否決的方案：(b) 把 `config.ts` 以精確路徑留在 auth-rbac——副本實跑 0 error，但等於為了一個無關的常數保留一條 auth-rbac 的誤命中，違背本票 (a) 的意圖，且 auth-rbac 的 reviewer 對 `0.036` 無任何 invariant 可核，只會回「無關」；(c) 加進 `most-engine` 或 `wi-workbench` 的 `paths`——違反 REQ-6，且需 human 另行裁決。

**`shared/api/useActiveRuleSet.ts` 的去留：留在 auth-rbac，不改任何設定。** 它位於 `shared/api/**` 之內，DESIGN-1 的 glob 自然覆蓋。理由：它經 `apiGet`（`client.ts`）取資料（讀碼：該檔 import `apiGet` 並以它發請求），正是 auth-rbac 第 2 條 invariant（`client.ts` 是唯一 API 入口）要守的那一類檔；移到 `rule-set` 領域違反 REQ-6，進白名單則違反判準（它帶有「不提供預設 code、未載入時回 `undefined` 讓呼叫端 gate 住計算」的契約，見該檔註解，不是純接線）。

白名單新增 7 條的位置：緊接現有最後一條 `src/frontend/src/App.tsx`（`domains.yaml:69-70`）之後。逐字內容見「實作內容」節。
副本實跑：改動後 `check_agent_config.py` 為 `16 ok, 0 warn, 0 error`，check_8 為「所有業務檔（264 檔）都命中領域或在白名單」；對照組（只收窄、不加白名單）為 `15 ok, 0 warn, 7 error`，與 REQ 證據 7 一致。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#no_domain_allowlist`；`ddm-v2/docs/agent-team/domains.yaml#auth-rbac`

## DESIGN-4　outbox 的測試與 ADR-027 併入 auth-rbac（對應 REQ-4）

**主案（併入 auth-rbac，不新增領域）：**

| 位置 | 前 | 後 |
|---|---|---|
| auth-rbac `paths`，接在 `i18n-review.spec.ts`（`domains.yaml:371`）之後 | （無） | `# tests：outbox 的整合與單元測試（其餘 auth-rbac 測試不在此列）`<br>`- "tests/integration/test_outbox_api.py"`<br>`- "tests/unit/test_outbox.py"` |
| auth-rbac `docs`，接在 `rbac-spec.md`（`domains.yaml:374`）之後 | （無） | `- docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md` |

用精確檔名而不用 `tests/**/*outbox*`：REQ 的「不做」排除了其他測試與兩支 migration，萬用字元會把 `tests/` 的其他 outbox 字樣檔、日後新檔帶進來；精確檔名使「不做」的檔命中維持 0（副本實跑：兩支 migration、`test_admin_users.py` 仍為 `-`）。

**兩案比較**（B＝新增 `outbox` 領域，副本也實跑過）：

| 面向 | 主案 A（併入 auth-rbac） | 備案 B（新增 outbox 領域） |
|---|---|---|
| `check_agent_config.py` | 0 error | 0 error |
| `docs_check.py` | 與改前輸出逐行相同（`4 ok, 13 warn, 0 error`） | 只加領域區塊：+1 WARN（缺索引 `outbox`）；補 `docs/domains/outbox.md`：再 +1 WARN（孤兒）；再補 `docs/DOC_REGISTRY.md` 一列與兩處「11」→「12」：回到與改前相同的 warn 數 |
| 必須新增的檔／區塊 | 無 | `outbox` 領域區塊（含 `invariants`）、`docs/domains/outbox.md`（新檔）、`docs/DOC_REGISTRY.md` 的列與計數 |
| logic reviewer 觸發 | 兩個測試被改 → 派 auth-rbac；該領域 invariants 沒有任何一條講 outbox，reviewer 對 outbox 測試多半只能回「無關」 | 兩個測試被改 → 派 `outbox`，有 3 條可核對的 invariant；outbox 程式檔會雙命中 `auth-rbac,outbox`（為滿足 REQ-4 與 REQ-6，不從 auth-rbac 移除） |
| REQ-4 / REQ-6 | 滿足；變動的命中只有 2 個測試檔（全量比對見 DESIGN-6） | 滿足 |
| REQ-5 邊界 | 在 H1 範圍內（只動 `paths` 與 `docs`） | **不在**：新增 invariants 區塊與領域索引檔，必須 human 另行裁決 |
| REQ-7 | 無新增 warn | 須多做兩處文件才能無新增 warn |

**推薦 A。** 理由：兩案在機械檢查上後果相近（皆 0 error），差別在 B 多出新規則內容（invariants）與兩個文件編輯，這些都超出 human 對 H1 的答覆；依邊界規則，兩案後果相近時選不需新增 invariants 的主案。B 的真實好處（outbox 有自己的檢查表）要用新 invariants 換，應由 human 決定，不由本票順手帶入。A 的代價記為殘留 R4。

**ADR-027 登記的後果（A）：** ADR-027 範圍比 outbox 寬（revision、policy、AI readiness 等），登記後 auth-rbac 的 reviewer 依 `most-logic-reviewer.md` 須讀該文件；`most-doc-sync` 日後只能在 human 核可後改該檔（`checkpoint.md` 步驟 4），而 ADR 本身永不改寫只追記。這是登記的固有後果，記為殘留 R5。`domain_guard.py map` 比對的是 `paths` 不是 `docs`，所以 ADR-027 的登記以讀 `docs` 清單與 `map` 輸出第三欄驗證（副本實跑：`map tests/unit/test_outbox.py` 的第三欄含 ADR-027）。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#auth-rbac`（`paths`、`docs` 欄）

## DESIGN-5　兩條 invariants 與 i18n 領域欄位逐字不動（對應 REQ-5）

- 不編輯 `domains.yaml:377-378`（auth-rbac 兩條 invariants）與 i18n 區塊（`:296-324` 一帶）。所有編輯限於：檔頭 `updated`、白名單新增、auth-rbac 的 `paths` 與 `docs`。
- 做法的保證不靠自律：implement 完成後以逐領域逐欄的程式比對（見「副本實跑紀錄」第 5 項的腳本形狀）核對，輸出必須只有 `DIFF auth-rbac docs`、`DIFF auth-rbac paths` 兩行。
- 停止條件：implement 中若發現必須動 invariants、i18n 任一欄、auth-rbac 的 `anchors`／`keywords`，或新增領域，implementer 停下回報，由 orchestrator 升 human；不得自行決定。
- 注意：auth-rbac 的 `keywords` 含 `outbox`（`:375`）、`anchors` 含 `outbox_service`（`:351`），本設計不動它們。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#auth-rbac`、`#i18n`

## DESIGN-6　範圍外命中維持不變（對應 REQ-6）

只編輯 DESIGN-1、3、4 列出的行；其餘 10 個領域的區塊不碰。驗證法：以全部業務檔加點名檔，改前改後各算一次命中集合並全量比對。輸入共 271 個＝業務檔 264（`src/ddm_v2/**/*.py`、`src/frontend/src/**/*.ts`、`src/frontend/src/**/*.tsx`）＋7 個點名檔：`tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py`、`tests/integration/test_admin_users.py`、`migrations/versions_v2/v2_0032_outbox_events.py`、`migrations/versions_v2/v2_0033_outbox_event_no_unique.py`、`docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md`、`src/frontend/e2e/i18n-review.spec.ts`（第 7 個；它不在 264 之內，因 e2e 不在 check_8 掃描範圍）。

預期差異恰為 18 檔，不多不少：`config.ts`、`workspace.ts`、`ui/` 5 檔（`auth-rbac` → 無），`shared/i18n/` 9 檔（`auth-rbac,i18n` → `i18n`），兩個 outbox 測試（無 → `auth-rbac`）。副本實跑：271 檔中恰 18 檔不同，與預期逐檔相符。其他：兩支 migration、`test_admin_users.py`、ADR-027（`map` 看 `paths`，不在 `paths`）皆維持 `-`；`e2e/i18n-review.spec.ts` 維持 `auth-rbac,i18n`（REQ 的 Q5 不處理）。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#domains`（其餘 10 個領域區塊唯讀）

## DESIGN-7　領域索引檢查不新增 error／warning（對應 REQ-7）

主案不新增、不改名任何 `docs/domains/*.md`，領域 id 清單不變，所以 `docs_check.py` 的「領域索引檔名」與「程式入口」兩項不受影響。「程式入口」檢查只要求有交集（`scripts/docs_check.py:219-236`），`auth-rbac.md` 第 15 行的 `src/frontend/src/shared/**` 與新 `paths` 仍有交集（`shared/api/` 等以它為前綴）。

副本實跑：改前改後 `docs_check.py` 完整輸出 `diff` 為空，皆 `4 ok, 13 warn, 0 error`。

- **artifact：** `ddm-v2/docs/agent-team/domains.yaml#auth-rbac`；檢查腳本 `ddm-v2/scripts/docs_check.py`（唯讀）

## DESIGN-8　auth-rbac.md 本票不同步，記殘留一行（對應 REQ-8）

**表態：不同步。** 本票不編輯 `docs/domains/auth-rbac.md`。理由：

1. REQ-7 只要求 docs_check 的 error／warning 數不變，不要求索引全文與 `paths` 逐字相同；主案已實跑證明不變（DESIGN-7）。
2. human 對 H1 的答覆只涵蓋 `domains.yaml` 的 `paths` 與文件登記，沒有授權修改領域索引（REQ「需要 human 決的點」H1 末段）。
3. `most-doc-sync` 的目標文件來自 `domains.yaml` 的 `docs`；`auth-rbac.md` 不在任何領域的 `docs` 清單，不會被自動帶入。
4. 同步屬額外的文件編輯，其必要性不足以讓本票擴大授權範圍。

**殘留（被接受的已知落差，一行）：** `docs/domains/auth-rbac.md` 第 15 行「程式入口」仍寫 `src/frontend/src/shared/**`，與 `domains.yaml` 改後的 `paths`（`shared/{api,types,auth}/**`）字面不一致；該索引的「權威文件」「決策」兩節亦未列 ADR-027。第 30 行的測試清單含 `test_outbox_api.py`，與新 `paths` 相符，無落差。

**若 human 之後要同步**（屬另一個需 human 明確核可的文件編輯，不在本票 implement 範圍）：第 15 行把 `src/frontend/src/shared/**` 改為 `src/frontend/src/shared/{api,types,auth}/**`，並在「權威文件」節加 ADR-027 一條。這兩處是全部所需編輯，改後 docs_check 預期仍無新增。

- **artifact：** `ddm-v2/docs/domains/auth-rbac.md`（唯讀）；殘留見本檔「殘留項」R1

---

## 實作內容（implement 階段只能做這些）

`ddm-v2/docs/agent-team/domains.yaml` 的完整差異（副本 `git diff -U1` 結果）：

```
@@ -17,3 +17,3 @@
 version: 1
-updated: 2026-09-21
+updated: 2026-10-24
@@ -70,2 +70,16 @@ no_domain_allowlist:
     reason: "頂層 tab 路由外殼，無單一領域業務邏輯"
+  - path: "src/frontend/src/shared/config.ts"
+    reason: "前端共用常數（作用中 worksheet 初始值、TMU→秒的顯示換算係數）；檔僅 5 行、兩個 export const，無函式與分支"
+  - path: "src/frontend/src/shared/workspace.ts"
+    reason: "跨領域共用的前端狀態容器（zustand store，僅 setter，無分支邏輯）"
+  - path: "src/frontend/src/shared/ui/ComboBox.tsx"
+    reason: "通用可搜尋下拉元件，純呈現"
+  - path: "src/frontend/src/shared/ui/ErrorBoundary.tsx"
+    reason: "React 錯誤邊界，框架接線"
+  - path: "src/frontend/src/shared/ui/Hint.tsx"
+    reason: "ⓘ 提示元件，純呈現"
+  - path: "src/frontend/src/shared/ui/RuleSetUnavailable.tsx"
+    reason: "錯誤態呈現元件，僅顯示傳入的 error 與 i18n 文案，無 rule-set 判斷邏輯"
+  - path: "src/frontend/src/shared/ui/WorksheetRequiredNotice.tsx"
+    reason: "無 worksheet 時的空狀態提示與跳轉按鈕（僅派送 tab 切換事件），介面接線"
 
@@ -367,3 +381,5 @@ domains:
       - "src/frontend/src/features/dashboard/**"
-      - "src/frontend/src/shared/**"
+      - "src/frontend/src/shared/api/**"
+      - "src/frontend/src/shared/types/**"
+      - "src/frontend/src/shared/auth/**"
       # e2e：角色可見性斷言（viewer 看不到使用者管理／DSX 入口、覆核頁權限）
@@ -371,2 +387,5 @@ domains:
       - "src/frontend/e2e/i18n-review.spec.ts"
+      # tests：outbox 的整合與單元測試（其餘 auth-rbac 測試不在此列）
+      - "tests/integration/test_outbox_api.py"
+      - "tests/unit/test_outbox.py"
     docs:
@@ -374,2 +393,3 @@ domains:
       - docs/architecture/rbac-spec.md
+      - docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md
     keywords: [auth, rbac, 權限, role, viewer, ie, manager, admin, x-username, forwardauth, audit, 稽核, outbox]
```

檔頭 `updated` 是登記表自己的維護日期，非語意欄位，沿用該檔既有慣例隨編輯更新。

## 實作授權路徑上限提案

只列本票 implement 階段可寫的 MOST 檔（上限，不是預設全寫）：

| 路徑 | 寫入內容 | 由誰寫 |
|---|---|---|
| `ddm-v2/docs/agent-team/domains.yaml` | 上節差異，單一 commit | implementer |
| `ddm-v2/tickets/BL-ENG-13/state.yaml` | 轉移與紀錄（依流程） | orchestrator |
| `ddm-v2/docs/agent-team/decisions.log` | 追加一行（見「與既有流程的銜接」），與 `domains.yaml` 同一 commit | orchestrator（該檔「只由主 context 追加」） |

`domains.yaml` 的收窄（auth-rbac `paths`）與白名單新增必須在同一 commit：只收窄不加白名單，check_8 會對被移出的 7 檔報 error；只加白名單不收窄，白名單與 auth-rbac 對同檔的命中並存，守衛失效（該 7 檔仍被 auth-rbac 守）而白名單條目形同虛設。缺任一半都不可入庫。

不在上限內，需另行取得 human 明確核可才可寫：`docs/domains/auth-rbac.md`（DESIGN-8）；備案 B 才需要的 `docs/domains/outbox.md`（新檔）與 `docs/DOC_REGISTRY.md`。票目錄下的 ACC 與證據由各自階段的授權涵蓋，不屬本表。

**須 human 裁決的變動，分兩組**（依 human 對 H1 的答覆：只動 `paths` 與文件登記不算邏輯變更）：

(i) 邏輯變更（動規則語意，擋它的是邏輯變更的定義與 REQ-5）：

- 任何對 auth-rbac 兩條 invariants 或 i18n 任一欄的編輯（REQ-5）。
- 新增領域所連帶的 `invariants` 區塊（REQ-5 邊界；備案 B）。
- auth-rbac 的 `anchors`、`keywords` 的編輯：這兩欄是 `domain_guard.py` 判定任務屬於哪個領域的線索，編輯可能改變守衛對任務的判定，是否影響守衛語意須由 design 逐項說明；本設計不編輯它們，故不觸及。

(ii) 超出授權範圍，須 human 另行核可（不是邏輯變更，擋它的是 REQ-6／REQ-8 與 human 對 H1 答覆的字面範圍）：

- 編輯任一其他領域的 `paths`、`docs`（REQ-6：其餘 10 個領域全欄不變）。
- 編輯 `docs/domains/*.md`（REQ-8）或任何 ADR 內容（H1 答覆未涵蓋）。
- 新增領域本身與其領域索引檔（備案 B）。

不在上列者為本設計的實作內容。其中白名單新增與檔頭 `updated` 不是 `paths` 也不是文件登記的字面。本設計的依據：依規則字面不屬邏輯變更（invariants 語意未動），且屬 REQ-3 合格路徑之一；但它們不屬 human 對 H1 答覆的字面，將在 BL-ENG-13 的 ACC 定案時向 human 揭露，不以「已獲授權」處理。REQ「對應文件」表把「必要時 `no_domain_allowlist`」列為本票可改，僅作為範圍參照。

## 與既有流程的銜接

- **commit 與檢查：** 單一 commit（含 `domains.yaml` 與 `decisions.log` 兩檔，見下「decisions.log」條），標題用 `docs: …`（agent 設定屬 `commit-convention.md` 的 `docs:` 類）。`checkpoint.md` 步驟 5（動到 `docs/agent-team/`）必跑 `check_agent_config.py`，非零阻擋；步驟 6（動到 `docs/`）跑 `docs_check.py`；未動程式，不跑 `graphify update`、不跑測試套件。
- **review 階段誰審什麼：** (1) `most-code-reviewer` 一個：YAML 結構、glob 字面、白名單路徑真實存在；(2) `most-logic-reviewer` 一個，`domain_id: auth-rbac`（本票變動 `paths`／`docs` 的唯一領域）：核對兩條 invariants 逐字不變、`shared/{api,types,auth}` 與 invariant 2 的對象一致、outbox 兩測試與 ADR-027 的登記合理；(3) 資安：`checkpoint.md` 步驟 2 將資安列為固定一員，照辦；本票未動程式與權限邏輯，預期無發現。
- **為什麼 domain_id 要手動指定：** `checkpoint.md` 步驟 1 以 `domain_guard.py map` 算受影響領域；本票變動的 `domains.yaml`、`decisions.log`、票目錄檔，副本實跑 `map` 皆命中 0 個領域，自動算不出要派誰。所以由 orchestrator 依本節指定 `auth-rbac`。i18n 不派：它的欄位零差異，由逐欄程式比對證明，且它的 `paths` 命中的檔本票沒有改。
- **邏輯變更裁決與 docsync：** 主案不含邏輯變更（H1），review 階段無 human 裁決關卡；不進 `docsync` 的文件翻轉。若 reviewer(domain) 回報「變更提案」，依 `checkpoint.md` 步驟 4 逐項問 human，不自行決定。
- **decisions.log：追加，一行。** 理由：該檔記「改了哪些檔與節」的 agent 團隊決策，先例包括 2026-09-22 的測試基礎建設列與 2026-09-21 的 `domains.yaml` 口徑列；本票改變了誰會被哪個 reviewer 守護，屬同類。形狀：`日期 \t auth-rbac \t docs/agent-team/domains.yaml（auth-rbac paths／docs、no_domain_allowlist +7） \t 一句話：auth-rbac 的 shared/** 收窄為 api／types／auth，i18n 九檔只歸 i18n，7 檔進白名單，outbox 兩測試與 ADR-027 登記；兩條 invariants 與 i18n 欄位不動 \t 該 commit`。commit 欄的處理（選定：log 條不記 commit hash）：`domains.yaml` 單一 commit 完成後 hash 才存在，若 log 條要記 hash，就必須在該 commit 之後再寫一次。本設計選擇 log 條**不記 hash**，改記分支名與該次變動的 `domains.yaml` 內容指紋（commit 前 `git hash-object` 所得的 blob 雜湊，可由 implementer 在 commit 前算出並交 orchestrator），形狀末欄改為 `<分支> blob:<雜湊>`。因 log 內容不依賴 commit 之後才有的資訊，log 的追加可與 `domains.yaml` 的編輯在同一 commit 內完成（orchestrator 在 implementer 交出前、commit 前追加，兩檔一起暫存），所以整個 implement 階段只有 1 筆 MOST 提交，不違反「一階段恰 1 筆 MOST 提交」。
  - 代價：log 條無法由 hash 直接回查 commit，須由分支與日期、或 blob 雜湊反查；本設計接受。
  - 若 orchestrator 或 human 認為 log 一定要記 commit hash，則必然是第二筆提交，這與一階段 1 筆衝突，須由 orchestrator 與 human 另行決定，不由本設計自行裁定。

## 失敗與回滾

**算失敗的情況（任一即失敗；其中的輸出與數字皆為預期值，ACC 另定）：**

1. `check_agent_config.py` 非零退出，或輸出不是 `16 ok, 0 warn, 0 error`，或 check_8 那行不是「所有業務檔（264 檔）都命中領域或在白名單」。注意：環境無 pyyaml 時 check_8 只印 warn 並略過，這種輸出不算通過。
2. `docs_check.py` 輸出與改前有任何一行不同（error 或 warning 數增加）。
3. 命中全量比對的差異檔集與 DESIGN-6 列出的預期檔集不符（多或少皆算）。
4. 逐欄比對出現 `DIFF auth-rbac docs`、`DIFF auth-rbac paths` 以外的行（尤其 invariants 或 i18n）。
5. `domains.yaml` 不是合法 YAML。

**回復：** 本票只動設定檔，回復即對該 commit 做 `git revert`（log 條隨同一 commit 一併還原，舊列不改）（新增一個還原 commit，走一般的核可流程）；白名單新增與 `paths` 收窄必須在同一 commit 內，故還原是整筆還原，不存在只還原一半。若失敗發生在 commit 之前，修正後重跑檢查即可，不得以放寬白名單理由或跳過檢查過關（`roles/_common.md` §1）。回復後 `domain_guard.py map` 的結果應與改前基線相同（可用本檔的全量比對確認）。

## L1 變更判定

MOST 自己的分類以 `docs/agent-team/_lib.manifest.yaml` 為準：`_lib/` 下的 `rules/`、`roles/`、`templates/` 是 vendor 進來的公版規則層（受 manifest 記錄的雜湊與 `local_deviations` 管），`project_facts` 列出的檔（含 `domains.yaml`、`decisions.log`）是專案事實層。本票不碰 `_lib/` 任何檔，也不新增 `local_deviations`。

| `<檔案>#<anchor>` | 判定 | 為什麼 |
|---|---|---|
| `docs/agent-team/domains.yaml#auth-rbac`、`#no_domain_allowlist`、檔頭 | 非 L1（專案事實） | 為 manifest 的 `project_facts.domains`，不在 `_lib/` |
| `docs/agent-team/decisions.log` | 非 L1（專案事實） | 為 manifest 的 `project_facts.decisions_log` |
| `docs/domains/auth-rbac.md`、`docs/domains/outbox.md`、`docs/DOC_REGISTRY.md` | 非 L1，且本票主案不改 | 專案文件 |

限制：判定法正本 `adr/0001-l1-freeze-and-executable-layer.md` §2.2 不在 MOST 倉庫內（`docs/agent-team/_lib/` 內的模板只引用它），因此本節依 MOST 自己的 manifest 分類判定，沒有逐條套 ADR-0001 §2.1(a) 的判定法；結論（無檔落入 `_lib/` 三目錄）不依賴該判定法。

## 外部依賴的失敗行為

- `python3` 加 `pyyaml`：缺 pyyaml 時 `check_agent_config.py` 的 check_8 只印 warn 並略過（`check_agent_config.py:check_8` 起始的 `ModuleNotFoundError` 分支）。行為：視為檢查未跑，停下回報，不算通過。
- `scripts/agent_team/domain_guard.py map`：docstring 稱任何錯誤靜默退出 0。行為：驗證輸出必須同時核對「處理的檔數」（本票為 271 行，組成見 DESIGN-6），輸出為空或行數不符時視為檢查失敗，不得當作「命中 0 領域」。
- `scripts/docs_check.py`：斷鏈 error 阻擋 commit（`checkpoint.md` 步驟 6）。行為：非零即停，回報，不半套用。
- `git`：只用於 commit 與 revert。commit 失敗則整筆不入庫，不留半套編輯。
- human 核可是關卡，不是外部依賴，不在此列。

## 違反既有 invariant

- auth-rbac 兩條 invariants（`domains.yaml:377-378`）：無。逐字不動；第 2 條的對象檔 `client.ts`、`api.d.ts` 仍命中 auth-rbac。
- i18n 的四條 invariants（`:320-324`）：無。整個區塊不動。
- 其餘 9 個領域的 invariants：無。區塊不動。
- `check_8` 的「每個業務檔至少命中一領域或在白名單」：無違反（副本實跑 0 error）。
- LOG 只追加：`decisions.log` 僅追加一行，不改舊列。ADR 只追記：不改 ADR-027。reviewer 無寫入權：本設計不賦予 reviewer 任何寫入。
- 公版規則層凍結條款：無檔落入 `_lib/`（見「L1 變更判定」）。

## 待決（升 human）

**待決 1：是否採用備案 B（新增 `outbox` 領域）。待 human 裁決。** 主案 A 不依賴此決定，human 不裁決也能照 A 繼續。

- 為什麼要 human 裁決：B 新增 `invariants` 區塊（新的規則內容）與領域索引檔，超出 human 對 H1 的答覆（REQ-5 邊界）。
- 選項：A 維持主案；B 採備案並由 human 核可其 invariants 文字與兩個新增文件。
- 建議：A。若 human 想要 outbox 有自己的檢查表，建議在本票結案後另開一張票做 B，而不是在本票 implement 階段加入，因為 B 的 invariants 需要 human 逐條認可。
- **備案 B 的完整設計**（副本實跑過，結果見比較表與「副本實跑紀錄」）：
  1. `domains.yaml`：auth-rbac 區塊**不**加兩個測試路徑與 ADR-027（其餘主案編輯照做：收窄、白名單、`updated`）；在檔尾 auth-rbac 之後新增：

     ```
       - id: outbox
         title: Transactional outbox 事件發布
         anchors: [outbox_service, OutboxEvent]
         paths:
           - "src/ddm_v2/services/v2/outbox_service.py"
           - "src/ddm_v2/models/v2/outbox.py"
           - "tests/integration/test_outbox_api.py"
           - "tests/unit/test_outbox.py"
         docs:
           - docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md
         keywords: [outbox, 事件發布, transactional outbox, at-least-once, event id]
         invariants:
           - 正式 worksheet save 與 review/outbox 在同一 DDM transaction（ADR-027 §5 第 1 點）
           - AI consumer at-least-once，以 event id 去重（ADR-027 §5 第 2 點）
           - AI service 不參與 distributed transaction，不直接寫 DDM 正式表（ADR-027 §5 第 3 點，兩個子句都在）
           - workflow_audit_log 保持低頻 workflow transition，不承載高頻 AI feedback（ADR-027 §5 第 4 點）
     ```

     四條 invariants 取自 ADR-027 §5（`ADR-027-…md` 第 64 行起的四個要點）：第 1 條取自第 1 點、第 2 條取自第 2 點、第 3 條取自第 3 點（前一版把第 2、3 點合併為一條並截掉「不直接寫 DDM 正式表」，本版拆回兩條）、第 4 條取自第 4 點；現無任何一條為合併。四條皆待 human 逐條認可，是否逐字、是否再加或刪，由 human 認可；`anchors`、`keywords` 是草擬。
  2. 新檔 `docs/domains/outbox.md`：沿用其他領域索引的段落形狀（一句話、權威文件、決策、程式入口、不變量指路、測試與缺口），內容限於上述路徑與 ADR-027 §5，不編規格。
  3. `docs/DOC_REGISTRY.md`：領域索引表加一列 `outbox`，「11 個業務領域」「11 領域 paths」兩處改 12。
  4. auth-rbac 的 outbox 程式路徑、`anchors`、`keywords` 不動，因此 outbox 程式檔雙命中 `auth-rbac,outbox`；之後要不要移出是另一個決定。
  5. 授權路徑上限額外加：`docs/domains/outbox.md`（新）、`docs/DOC_REGISTRY.md`。review 階段 `most-logic-reviewer` 額外派 `domain_id: outbox`。
  6. 副本實跑結果：`check_agent_config.py` `16 ok, 0 warn, 0 error`；`docs_check.py` 三檔都補後，與改前輸出只差「領域索引檔名…（12 個）」一行的數字；全量比對：差異限於 outbox 兩測試（無 → `outbox`）與兩個 outbox 程式檔（`auth-rbac` → `auth-rbac,outbox`）加主案相同的 16 檔。
  7. 失敗與回滾同主案，還原範圍多兩個檔。

除待決 1 之外，本設計無其他未決項。

## 殘留項（已知、被接受）

| # | 內容 | 來源 |
|---|---|---|
| R1 | `docs/domains/auth-rbac.md` 第 15 行與新 `paths` 字面不一致；索引未列 ADR-027 | DESIGN-8 |
| R2 | `shared/` 根層或新子目錄日後新增的檔不再自動命中任何領域，check_8 會對它報 ERR，迫使建檔者歸類；這是預期的守門行為，不是缺陷 | DESIGN-1 |
| R3 | `config.ts` 進白名單後，`TMU_SEC` 被改時沒有任何 logic reviewer 被派；後端權威常數是 `most_engine/rule_set_data.py:14` 的 `TMU_TO_SEC`，前端這份是重複常數，改動時沒有 logic reviewer 比對兩者；前端此常數也不在 `core_logic/run_all.py` 的引擎黃金值檢查範圍（該檢查針對引擎） | DESIGN-3 |
| R4 | outbox 兩測試被改時會派 auth-rbac，但該領域 invariants 沒有講 outbox 的條目，reviewer 多半回「無關」；outbox 無專屬 spec 的缺口屬另一張票（`auth-rbac.md` 的 BL-DOC-4） | DESIGN-4 |
| R5 | ADR-027 範圍寬於 outbox，登記後 auth-rbac 的 reviewer 必讀該文件，doc-sync 日後可（經核可）改它 | DESIGN-4 |
| R6 | `domains.yaml` 自身不屬任何領域，checkpoint 無法自動算出該派誰，須手動指定 `auth-rbac` | 銜接節 |
| R7 | 精確檔名登記的 outbox 測試若日後改名，覆蓋會無聲消失；check_8 不掃 `tests/`，只有 `map` 看得出來（REQ 證據 6） | DESIGN-4 |
| R8 | `e2e/i18n-review.spec.ts` 雙命中、`api.d.ts` 的 check_8 docstring 與程式不一致、`tests/` 全面無領域：皆 REQ 明列不處理 | REQ 不立條、Q4、Q5 |

## 驗收對照（供 verifier 擬 ACC 時參考，非 ACC）

本節的結果欄皆為**預期值，ACC 另定**，不構成驗收門檻。

| REQ | 驗收意圖 | 對應設計 | 副本實跑的對應結果 |
|---|---|---|---|
| REQ-1 | 三個有關檔仍命中 auth-rbac；i18n 九檔不再命中；其餘 auth-rbac 路徑命中不變 | DESIGN-1 | `client.ts`、`useMe.ts`、`api.d.ts` 皆 `auth-rbac`；i18n 九檔皆 `i18n`；auth-rbac 命中集合的變動＝移出 DESIGN-6 列的檔、加入 2 測試 |
| REQ-2 | 九檔集合恰為 `{i18n}`；i18n 全欄不變 | DESIGN-2 | 九檔輸出皆 `i18n`；`i18n all fields identical: True` |
| REQ-3 | check_8 通過，整體 0 error、0 warn；無靠不合判準過關 | DESIGN-3 | `16 ok, 0 warn, 0 error`；對照組僅收窄為 `7 error` |
| REQ-4 | 兩測試命中至少一領域；ADR-027 在某領域 `docs`；outbox 程式命中不消失 | DESIGN-4 | 兩測試 `auth-rbac`；`map` 第三欄含 ADR-027；`outbox_service.py`、`models/v2/outbox.py` 仍 `auth-rbac` |
| REQ-5 | 兩 invariants 與 i18n 全欄逐字不變 | DESIGN-5 | `auth-rbac invariants identical: True`；欄位差異只有 `auth-rbac docs`、`auth-rbac paths` |
| REQ-6 | 命中差異只落在明列檔；其餘領域全欄不變；「不做」的檔維持現狀 | DESIGN-6 | 差異檔集與 DESIGN-6 預期逐檔相符；兩 migration、`test_admin_users.py` 仍 `-` |
| REQ-7 | docs_check error／warning 數不變 | DESIGN-7 | 完整輸出 `diff` 為空；`4 ok, 13 warn, 0 error` |
| REQ-8 | `auth-rbac.md` 未獲核可前不變；對同步與否有表態；REQ-7 成立 | DESIGN-8 | 本票不編輯該檔；殘留 R1 已記；REQ-7 如上 |

## 副本實跑紀錄

副本位置（repo 外）：`/tmp/claude-1000/-home-howard-workspace-dev-workflow/8a1f69a5-911b-4e2d-95de-9b7ade958d01/scratchpad/bl13-design/`。建法：自 `most-builder` 根 `rsync -a --exclude .venv --exclude node_modules --exclude graphify-out --exclude __pycache__ --exclude .git`，含根 `CLAUDE.md`、`AGENTS.md`，再 `git init` 並提交基線；所有指令帶 `PYTHONDONTWRITEBYTECODE=1` 與 `python3 -B`。真實 most-builder 內未執行任何 MOST 腳本。

| # | 跑了什麼 | 結果 |
|---|---|---|
| 1 | 基線 `check_agent_config.py` | `16 ok, 0 warn, 0 error`，check_8 為 264 檔 |
| 2 | 基線 `docs_check.py` | `4 ok, 13 warn, 0 error`（存為比對基準） |
| 3 | 基線全量命中（自寫探測腳本，以 `importlib` 載入副本的 `domain_guard.py`，對 264 業務檔加 7 個點名檔共 271 檔逐檔算命中集合） | 與 REQ 證據 2、3、4、5 一致；`map` CLI 對 `config.ts` 與 `test_outbox_api.py` 亦驗證輸出與探測腳本一致 |
| 4 | 對照組：只把 `shared/**` 換成三條子目錄 | `15 ok, 0 warn, 7 error`（與 REQ 證據 7 相符） |
| 5 | 主案 A（上文完整差異）：`check_agent_config.py`；`docs_check.py` 與基準 `diff`；全量命中與基準 `diff`；逐領域逐欄比對（`yaml.safe_load` 後比各領域各欄）；`map` 對 `client.ts`／`useMe.ts`／`api.d.ts`／`i18n.ts`／`test_outbox.py` | `16 ok, 0 warn, 0 error`；docs `diff` 為空；271 檔中 18 檔不同；欄位差異僅 `auth-rbac docs`、`auth-rbac paths`，白名單 24 → 31，兩 invariants 與 i18n 全欄相同；`map` 結果如各節所述 |
| 6 | 主案變體 (b)：`config.ts` 不進白名單，改以精確路徑加入 auth-rbac `paths` | `16 ok, 0 warn, 0 error`（可行但不採，見 DESIGN-3） |
| 7 | 備案 B：`check_agent_config.py`；`docs_check.py` 三階段（僅領域區塊／加 `outbox.md`／再加 `DOC_REGISTRY` 列與計數）；全量命中 | `16 ok, 0 warn, 0 error`；docs 依序 `3 ok, 14 warn`、`3 ok, 14 warn`、與基準只差一行計數文字；命中差異如待決 1 第 6 點 |
| 8 | 對 `domains.yaml`、`decisions.log`、票目錄檔、`auth-rbac.md` 跑 `domain_guard.py map` | 輸出 0 行（命中 0 領域） |

未跑：`tests/unit/agent_team` 的 pytest（副本環境無 pytest 模組）；前端型別檢查與建置（本票不動程式）。

## 修訂紀錄

| 版 | 日期 | 內容 | 依據 |
|---|---|---|---|
| 1 | 2026-10-24 | 初稿 | requirements.md（REQ-1～REQ-8） |
| 2 | 2026-10-24 | config.ts 白名單理由與論證只留事實並補 R3；DESIGN-6 列出 271 個輸入的組成；邏輯變更清單拆為兩組；失敗與回滾、驗收對照標明預期值；decisions.log 追加做法選定；備案 B 的 invariants 拆回四條；授權路徑表補同 commit 理由；白名單與 `updated` 的授權依據改寫 | review-design.md 第 1 輪 S1～S7 |
| 3 | 2026-10-24 | 定案：狀態欄 Draft 改為已定案，定案紀錄節改寫；設計內容零改動 | reviewer(design) 第 1 輪 PASS（S1～S7 已於第 2 版折入） |

## 定案紀錄

- **狀態：已定案**（2026-10-24）。本票 L1，design 關卡核可者為 reviewer(design)，免 human 關卡（`rules/stage-table.md` §1 第 4 列、§6.1）。
- **reviewer(design) 審查結論：** 第 1 輪 PASS（阻擋 0、建議 7：S1～S7），全文見 `tickets/BL-ENG-13/review-design.md`。S1～S7 已由 architect 折入第 2 版（見修訂紀錄），依 L1 規則不跑第 2 輪。
- **正規化 hash：** 依本檔檔頭 `hash取法`（`rules/stage-table.md` §8.2 的 `++c==2` 取法，排除整個 frontmatter）於 repo 根（`ddm-v2/`）算，值只記於 `tickets/BL-ENG-13/state.yaml` 的 `design_hash`（`rules/doc-taxonomy.md` §1.9）。**值不寫在本節**：本節在 hash 涵蓋的正文內，寫入值會使值改變（自指）。
- **待 human 的事項（不影響主案定案）：** 待決 1（備案 B 新增 outbox 領域，連帶 `docs/domains/auth-rbac.md` 同步）維持待 human，不在本票預設範圍；白名單新增 7 條與 `domains.yaml` 檔頭 `updated` 更新依規則字面不屬邏輯變更，但不在 human 對 H1 答覆的字面內，須於 BL-ENG-13 的 ACC 定案時向 human 揭露。
- 修訂須走 `rules/doc-taxonomy.md` §1.9：開新版、舊版標 `superseded_by`、重新核可。
