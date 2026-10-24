---
類別: "ACC"
狀態: "已定案（v2；human 2026-10-24 核可，依據見核可欄；Draft 階段曾依 reviewer 第 1 輪 BLOCK、第 2 輪 PASS 修訂為 v2，見 §5）"
版本: "v2"
票: "`BL-ENG-13`"
上游: "REQ-1 至 REQ-8（`tickets/BL-ENG-13/requirements.md`，定案 2026-10-24）／ DESIGN-1 至 DESIGN-8（`tickets/BL-ENG-13/design.md`，定案 2026-10-24，`design_hash` 見 §1）"
核可: "`human`，`2026-10-24`　← 核可依據（逐字）：human（Howard）2026-10-24 手打「(a) 簽」，回應的是 orchestrator 提出的簽核清單（兩項：ACC-1-16 答 (a)；簽 BL-ENG-13 的 ACC-1，共 16 項、agent 15、human 1、SKIP 全否，並知悉 §0 的 A、B、C 三組事項），清單內 orchestrator 的建議即上述兩項；(a) 的內容依 §0 為「兩件都核可」，即 no_domain_allowlist 新增 7 條（shared/config.ts、shared/workspace.ts、shared/ui/ 下 5 檔）與 domains.yaml 檔頭 updated 更新。human 沒有說其他話"
偏離: "① §4 每項一張表（照模板），表後附指令塊；每張表在模板欄位之外多一列 `何時能驗`（本票的驗收橫跨 implement、review、verify 三個時點，時點是判準的一部分；沿 DW-38 ACC 的先例）。② 機械核對輔助 `bl13_checks.py` 與對照組情境產生器放在公版側 `dev-workflow/tickets/DW-38/acc/evidence/bl13-acc-draft/`（只讀 MOST；不屬 dw、不改 `_lib/` 任何檔）；理由：本票授權寫入 MOST 的路徑只有 `acc/ACC-1.md` 與 `acc/evidence/baseline/` 六檔，輔助程式不能放進 MOST；它的 sha256 綁在 PRE-3。③ 基線六檔不另取，是公版 DW-38 基線同名檔的位元組複本（DW-38 ACC-1-21 (c) 與其 §4.0.2『一次兩用』的要求）；本票需要的『變更前』資料（271 檔以上的逐檔命中、docs_check 輸出）由不可變的 `BASE` 提交（`most-head.txt` 記的 `dce80fac…`）以 `git archive` 重算，不進 MOST。④ 本票的 review 階段與 human 項的記錄格式（§4.0.2）是本 ACC 新訂，DESIGN 只寫了派誰、沒寫記在哪；其中報告檔名 `review-implement.md` 亦為本 ACC 新訂（DESIGN 未訂此檔名），orchestrator 須把它列入 review 階段的 A1 授權路徑（見 §4.0.2 第 3 點）。"
---

# ACC-1 — BL-ENG-13 怎樣算做到了：auth-rbac 不再誤命中 `shared/i18n/`、收窄不製造無主業務檔、outbox 兩個測試與 ADR-027 被守衛覆蓋，且兩條 invariants、i18n 領域、其餘 10 個領域、docs_check、`auth-rbac.md` 與授權邊界都不被動

> **Draft v2**（依 `review-acc-r1.md` 的 B1／B2／S1～S8 修訂，見 §5）。給 human 的一頁在 §0；「不做、不預設」的事在 §7；ACC 起草時發現的問題在 §8。本檔所有指令都在 repo 外的暫存樹與本地複製上試跑過（試跑記錄與對照組在 `dev-workflow/tickets/DW-38/acc/evidence/bl13-acc-draft/trial/`），**對真實 most-builder 只做了唯讀動作**（`git archive`／`git show`／`git log`／`git status --no-optional-locks`；MOST 腳本一律在暫存樹上以 `python3 -I -B` 跑）。核可欄未填、`acc_hash` 未填。

---

## 0. 給 human 的一頁

**要你做的只有一次 sitting（ACC 定案本來就必到的關卡），裡面一個答案要你下：**

| sitting | 內容 | 你要看什麼、怎麼看 |
|---|---|---|
| **S1　ACC 定案** | ①答 **ACC-1-16**（白名單新增 7 條與檔頭 `updated` 更新，**不在你對 H1 答覆的字面內**，見下）；②簽本 ACC（共 16 項：agent 15、human 1；SKIP 全否）；③知悉下列 A、B、C（含 C(5) 的 design 揭露） | ①見下『ACC-1-16 怎麼看』；②讀 §4.0、§4 各表的『通過門檻』列；③見下 |

**ACC-1-16（唯一的 human 項）：核可 design 的兩件小事。** 你對 H1 的答覆是『只動 `domains.yaml` 的 `paths` 與文件登記，不算邏輯變更』。design 另含兩件**不在這句字面內**的編輯（design 已如實揭露、依規則字面也不屬邏輯變更，但不以『已獲授權』處理，所以交你核可）：

1. `no_domain_allowlist` 新增 7 條：`shared/config.ts`、`shared/workspace.ts`、`shared/ui/` 下 5 檔，各附理由。白名單的意思是『這個檔被改時**不派任何 logic reviewer**』。
2. `domains.yaml` 檔頭 `updated:` 改為實作日（登記表自己的維護日期，非語意欄位）。

| 選項 | 內容 | 後果 |
|---|---|---|
| **(a)（建議）** | 兩件都核可 | 照 design 主案進 implement |
| (b) | 不核可 `config.ts` 進白名單，其餘照準 | design 的替代方案 (b)：`config.ts` 以精確路徑留在 auth-rbac。**該部分回 design**（design 修訂、`design_hash` 變、依 `rules/stage-table.md` §8.3 重核受影響的 ACC-1-1、1-4、1-7、1-8、1-12 後 ACC 升版）。副本實跑過此變體：`16 ok, 0 warn, 0 error`（design DESIGN-3 否決方案 (b)） |
| (c) | 其他不核可（整批或部分） | 該部分回 design，同上 |

**為什麼建議 (a)：** 7 檔的 reason 都可對照白名單判準（`domains.yaml` 檔頭：純結構／框架接線／設定／通用基底，無業務邏輯）；唯一有張力的是 `config.ts`，它含 `TMU_SEC = 0.036`（TMU 換秒的顯示係數，5 行、兩個 `export const`、無函式與分支），進白名單後**它被改時不會有 logic reviewer 比對後端權威常數 `TMU_TO_SEC`**（design 殘留 R3，被接受）。若你不接受這個殘留，答 (b)。
**怎麼看（約 5 分鐘）：**
```bash
M=$HOME/workspace/most-builder ; P=$M/ddm-v2
sed -n '/^## 實作內容/,/^## 實作授權路徑上限提案/p' $P/tickets/BL-ENG-13/design.md      # 完整差異：7 條白名單與各自的 reason、updated 那一行
sed -n '/^## DESIGN-3/,/^## DESIGN-4/p' $P/tickets/BL-ENG-13/design.md                  # 7 檔逐檔的判準檢視，與 config.ts 的張力、被否決方案
cat -n $P/src/frontend/src/shared/config.ts                                              # 5 行
```
你的答覆由 orchestrator 以你的原話寫進 `state.yaml` log（格式見 §4.0.2 第 2 點），ACC-1-16 的判定就是該條存在且選項為 (a)。

**不需要你決定、但你簽 ACC 即知悉的三組事項：**

**A　本 ACC 與 REQ／DESIGN 字面不同之處：**

| 編號 | 差異 | 理由 |
|---|---|---|
| 判法 | design 『驗收對照』的預期值（`16 ok, 0 warn, 0 error`、命中差異 18 檔、`4 ok, 13 warn, 0 error`）在 ACC 不全當門檻：命中差異用**規則**判（見 ACC-1-8），不寫死筆數；`docs_check` 不比真實工作樹而比 `git archive` 暫存樹 | 真實工作樹的 `docs_check` 含 graphify 落後的提示（`落後 N commit（門檻 5）`），隨本票每多一筆提交就漂；design 自己用的也是不含圖的副本（§8 發現 5） |
| 基線 | 基線六檔是公版 DW-38 基線的複本，不是本票新取；它們的內容有四處與今日實跑不同（HEAD、AGENTS.md 引用數、graphify 行、domain-map 僅 22 路徑），ACC 逐項處理 | §8 發現 1；DW-38 已定案的 ACC 要求複本、要求輸入雜湊相等即視為有效 |
| 記錄格式 | review 階段、human 答覆、基線有效性在 `state.yaml` log 的記法與報告檔名 `review-implement.md` 是本 ACC 新訂（§4.0.2）；orchestrator 在各階段須照做，否則 ACC-1-14、1-15、1-16 無從 PASS | DESIGN 只寫了派誰，沒寫記在哪 |

**B　下列事**『不做、不預設』，本 ACC **不替你決定**，也沒有任何 ACC 項驗它們（細節 §7）：備案 B（新增 outbox 領域，連帶新增 invariants 與兩個文件）、`docs/domains/auth-rbac.md` 同步、其他測試與 migration 的領域覆蓋（Q1／Q2 你已答不納入）、`e2e/i18n-review.spec.ts` 的雙重命中（Q5）。ACC 只守『這些事**沒有被順手做掉**』（ACC-1-9、1-11、1-13）。

**C　你要知悉：** (1) 本票 verify 階段**沒有 human 判定項**；(2) 本票的 human 項只有 ACC-1-16 一項，不另增 sitting；(3) `docsync` 關卡（L1 本來就有）不由本 ACC 增減：design 判主案不進 docsync 的文件翻轉；(4) 本 ACC 的 `bl13_checks.py` 等輔助程式在公版側，定案前須由 orchestrator 入庫並把 sha256 記進 PRE-3；(5) design 內有『待決 1（備案 B）』與白名單揭露，design 已聲明**主案不依賴**它們，這是 orchestrator 的進入判斷（進入 implement 不以它們為前提），簽核時一併知悉；ACC 不替你決定備案 B（§7）。

---

## 1. DESIGN 綁定

```yaml
design:
  artifact: ddm-v2/tickets/BL-ENG-13/design.md          # 整檔；anchor = 各節標題 DESIGN-1 … DESIGN-8（anchor 用標題，不用行號）
  normalized_sha256: 792aa34f6057bfcb1301447ad4f56ff6c1636b1420e8866e06ae377114b85c6d
  normalization: dev-workflow/rules/stage-table.md#82-正規化規則
```

`normalized_sha256` 的值取自 `tickets/BL-ENG-13/state.yaml` 的 `design_hash`（DESIGN 定案值）。取法為 `design.md` 檔頭『hash取法』的 §8.2 正本法 `awk 'f; /^---$/ && ++c==2 {f=1}'`（取第二個獨立成行 `---` 之後的正文，整個 frontmatter 排除）：於 `ddm-v2/` 執行 `set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' tickets/BL-ENG-13/design.md | tr -d '\r' | sed 's/[[:space:]]*$//' | sha256sum`。verifier 於 Draft 當下重算得 `792aa34f…4b85c6d`，與 `state.yaml` 的 `design_hash` 一致。

hash 不符時**不是自動擋**，走 `rules/stage-table.md` §8.3：verifier 逐條標示受影響的驗收項 → human 重新核可 → ACC 版本遞增。

---

## 2. 外部前提

驗收通過所依賴、但本票不控制的事實。每條是可執行斷言；Draft 階段已核者標『已核』，其餘 verify 重驗。**前提失效的處理等同 ACC 修訂（§5）。**

```bash
M=$HOME/workspace/most-builder ; P=$M/ddm-v2 ; DW=$HOME/workspace/dev-workflow
HLP=$DW/tickets/DW-38/acc/evidence/bl13-acc-draft ; H=$HLP/bl13_checks.py ; BL=$P/tickets/BL-ENG-13/acc/evidence/baseline
```

| # | 前提 | 版本 / 來源 | 怎麼重驗 | 現況 |
|---|---|---|---|---|
| PRE-1 | DESIGN 綁定未漂：`design.md` 以 §1 取法重算 = §1 所綁值（不符依 §8.3 處置，不是自動擋） | `ddm-v2/tickets/BL-ENG-13/design.md`（定案 2026-10-24） | 見下方指令塊 `PRE-1`，得 `792aa34f6057bfcb1301447ad4f56ff6c1636b1420e8866e06ae377114b85c6d` | 已核（Draft 當下重算相等） |
| PRE-2 | 系統 `python3` ≥ 3.10 且有 PyYAML（MOST 檢查腳本與 `bl13_checks.py` 都用系統 `python3`；缺 PyYAML 時 check_8 只印 warn 略過，ACC-1-3 會因『無 WARN』判 FAIL） | `/usr/bin/python3`（3.10.12）、PyYAML 5.4.1 | `python3 -c 'import sys,yaml; assert sys.version_info>=(3,10); print(sys.version.split()[0], yaml.__version__)'` | 已核（3.10.12／5.4.1） |
| PRE-3 | 輔助程式未被改：`bl13_checks.py` 的 sha256 = `afb216afee0c6a1e0c588297aa3f251481a7f1fcfce256bdb28b1493448602d5` | 公版側 `tickets/DW-38/acc/evidence/bl13-acc-draft/bl13_checks.py`（定案前由 orchestrator 入庫；若 Draft 後因審查而修改，此值隨之更新並重跑 §4.0.3 的對照組） | `sha256sum $H` | 已核（Draft 當下） |
| PRE-4 | 基線輸入檔的雜湊在目前 HEAD 下仍與 DW-38 基線記錄一致（domain_guard.py、兩支檢查腳本、checkpoint.md、`auth-rbac.md`、`domains.yaml` 等 18 檔；這是『複本仍有效』的判準，DW-38 ACC §4.0.2）。**`premise` 的完整 18/18 比 HEAD 只在 T0（implement 前）有效**：IMPL 之後 HEAD 的 `domains.yaml` 本來就會變。helper 的 `premise` 在 BASE..HEAD 內已有改動 `domains.yaml` 的提交時，該檔改比 BASE（其餘 17 檔仍比 HEAD），所以 VERIFY 跑它仍應 PASS；但 VERIFY 的**判準**以 ACC-1-15 ⑤（BASE 全相符、HEAD 除 `domains.yaml` 外全相符）為正本，`premise` 只作 T0 的複驗 | 公版 `tickets/DW-38/acc/evidence/baseline/sha256-inputs.txt` | `python3 -I -B $H premise --repo $M --work $(mktemp -d)`（印 `PASS … 18/18`） | 已核（HEAD `38b1af4`：18/18；`trial/premise.log`。IMPL 後情境：暫存樹 `good`（implement 已提交）實跑 PASS 18/18，註明 domains.yaml 改比 BASE，留存於 `trial/premise-impl.log`，檔內附一行 T0 輸出作對照） |
| PRE-5 | 本票目錄不引用 `BL-ENG-13` 以外的 `BL-ENG-<n>`（否則公版 `dw check` 的 C25 會對本票目錄報錯；DW-38 ACC-1-3 的前提） | `ddm-v2/tickets/BL-ENG-13/` | 見下方指令塊 `PRE-5`，得 0 | 已核（0） |
| PRE-6 | `check_agent_config.py` 需要被 git 忽略的環境檔：`ddm-v2/.claude/agents/` 三個轉接檔在位（暫存樹自真實工作樹複製 `.claude`，不複製其他 ignore 物） | 工作樹（`.gitignore` 的 `.claude/`） | 見下方指令塊 `PRE-6`，得 3 | 已核（3） |

各前提的重驗指令（上表『怎麼重驗』欄的正本；變數見 §4.0.1，此處沿用本節開頭那組）：

```bash
# PRE-1
cd $P && set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' tickets/BL-ENG-13/design.md | tr -d '\r' | sed 's/[[:space:]]*$//' | sha256sum
# PRE-2
python3 -c 'import sys,yaml; assert sys.version_info>=(3,10); print(sys.version.split()[0], yaml.__version__)'
# PRE-3
sha256sum $H
# PRE-4
python3 -I -B $H premise --repo $M --work $(mktemp -d)
# PRE-5
/usr/bin/grep -rnoE 'BL-ENG-[0-9]+' $P/tickets/BL-ENG-13 | /usr/bin/grep -v 'BL-ENG-13' | wc -l
# PRE-6
ls $P/.claude/agents/*.md | wc -l
```

---

## 3. 環境矩陣

```yaml
source: git -C ~/workspace/most-builder rev-parse --show-toplevel（專案根 ddm-v2；分支 feature/lb-writeback）
dimensions:
  - { id: E1, 值: "MOST（most-builder，專案根 ddm-v2）；判定以該 repo 的 committed 內容（HEAD 與 BASE 兩個提交）為準，MOST 腳本在 git archive 暫存樹上執行；每份證據記當時 MOST HEAD", 可用: yes, 不可用的理由: — }
```

本票只有一個環境格：MOST 沒有 compose／ingress 之類的環境矩陣來源，環境清單指向上面的 `git rev-parse`，不在本檔抄別份。公版 DW-38 基線與 `bl13_checks.py` 是**唯讀輸入**，不是驗收對象的環境。每項一格 `E1`，各自獨立判定。

---

## 4. 驗收項

### 4.0 指令約定、時點與記錄格式（全部驗收項共用，定案後凍結）

**4.0.1　變數與約定**（所有指令塊先 `export` 這組；`~` 一律展開成 `$HOME`）：

```bash
M=$HOME/workspace/most-builder ; P=$M/ddm-v2 ; DW=$HOME/workspace/dev-workflow
HLP=$DW/tickets/DW-38/acc/evidence/bl13-acc-draft ; H=$HLP/bl13_checks.py ; BL=$P/tickets/BL-ENG-13/acc/evidence/baseline
export PYTHONDONTWRITEBYTECODE=1
W=$(mktemp -d)                                   # 暫存，不在 $M 與 $DW 之內
chk() { python3 -I -B $H "$1" --repo $M --env $M --work $W/$1 ; }   # 每條核對印 PASS|FAIL <名稱>: <細節>；退出碼 0=全 PASS、1=有 FAIL、2=輸入錯誤
```

- **`BASE`＝`most-head.txt` 記的 `HEAD=`（`dce80fac65480c94b4e93cbcabb488a17caf20ff`）**，由 `bl13_checks.py` 自動讀出。『變更前』一律由 `git archive BASE` 展開成暫存樹重算；『變更後』由 `git archive HEAD` 展開。**MOST 腳本從不在真實 most-builder 內執行**（`check_agent_config.py`、`docs_check.py`、`domain_guard.py map` 都在暫存樹上以 `python3 -I -B` 跑，`TMPDIR` 指到暫存目錄）。
- 為什麼 `BASE` 是 `dce80fac…` 而不是目前 HEAD `38b1af4`：基線六檔是 DW-38 於該提交取得的複本；兩提交之間 MOST 只增加了 W0 的 vendor／指路提交與本票 requirement、design 兩階段提交，**不含任何影響領域守衛的輸入**（PRE-4：18 個輸入檔雜湊一致；business 檔與兩支檢查腳本零差異）。
- **證據檔**：每項在 verify 時把『指令＋實際輸出』貼進 `ddm-v2/tickets/BL-ENG-13/acc/evidence/ACC-1-<n>-<YYYY-MM-DD>.md`，檔頭記 `MOST HEAD`、`BASE`、日期、`sha256sum $H`；不是回報裡的一段文字。
- `bl13_checks.py` 的子命令 `c1`…`c16` 與 ACC 項一一對應（`ACC-1-n` ↔ `c<n>`）；`premise` 對應 PRE-4（僅 T0 有完整意義，VERIFY 以 ACC-1-15 ⑤ 為準，見 PRE-4）。
- 輸入集合的規則（ACC-1-8、1-9 共用，由程式列舉，不寫死檔名清單）：『業務檔』＝`ddm-v2/` 下 `src/ddm_v2/**/*.py`、`src/frontend/src/**/*.ts`、`src/frontend/src/**/*.tsx`（排除 `__pycache__`；與 check_8 同一個 glob，現況 264 檔）＋7 個點名檔（design DESIGN-6：兩個 outbox 測試、`tests/integration/test_admin_users.py`、兩支 outbox migration、ADR-027、`src/frontend/e2e/i18n-review.spec.ts`）＝271（§4.0.1 的『271』）；ACC-1-9 的輸入＝**271 另加 `tests/**/*.py` 與 `migrations/versions_v2/*.py` 的其餘部分**：這兩個 glob 共 192 檔，其中 5 檔（3 個點名測試、2 支 migration）已在 271 內，故新增 187 檔，458＝264＋7＋187。（ACC-1-9 條件裡的 192、190 是這兩個 glob 自己的檔數，不是 458 的組成。）

**4.0.2　記錄格式（orchestrator 在各階段須遵守；定案時由 human 一併接受）：**

1. **基線有效性（acceptance 階段）**：`state.yaml` log 追加一條含『基線仍有效』的記錄（DW-38 ACC-1-21 (e) 同要求），表示 `sha256-inputs.txt` 各檔雜湊與當下相等、沿用 DW-38 基線複本、未重取。基線六檔（§4.0.5）與本 ACC **同在 acceptance 階段的那一筆 MOST 提交**入庫，必須早於 implement 提交（ACC-1-15）。
2. **human 答覆（acceptance 階段）**：`state.yaml` log 追加一條，格式 `<日期> human 答覆[ACC-1-16]：<human 手打原話，逐字>；選項=<a|b|c>`。每個 log 條只放 ACC-1-16 一題。**比對前綴（`chk c16` 的唯一認定方式）**：該條須以 ISO 日期（`YYYY-MM-DD`）開頭，且含字串 `human 答覆[ACC-1-16]：`；`選項=` 取自該條。其他條（例如 orchestrator 的階段轉移條，即使提到 `ACC-1-16` 與 `human`）不計。**提醒：** 選項只認小寫 `a|b|c`、冒號只認全形 `：`；完整前綴 `human 答覆[ACC-1-16]：` 只能出現在那一條答覆條，orchestrator 的轉移條與其他條目不得原文引用，否則會被算成第 2 條答覆而 FAIL。有且僅有一條且 `選項=a`，ACC-1-16 才 PASS；選 b 或 c 時本項**未 PASS、ACC 不得定案**（不稱 FAIL；該部分回 design，見 §0）。
3. **review 階段（review）**：三條 log，格式 `<日期> review-implement[<種類>]：producer=<implement 的 agent 識別>；reviewer=<審查者識別>；role-source=<角色正本路徑>[；domain_id=<id>]`，種類固定為 `mechanical`、`domain`、`security`，**每種恰一條**（一條 log 只放一組 producer／reviewer）：
   - `mechanical`：`reviewer=most-code-reviewer`，`role-source` 含 `agents/most-code-reviewer.md`；
   - `domain`：`reviewer=most-logic-reviewer`，`domain_id=auth-rbac`，`role-source` 含 `agents/most-logic-reviewer.md`；整份 log 內出現的 `domain_id=` 只可有 `auth-rbac`（**i18n 不派**，design『與既有流程的銜接』）；
   - `security`：`reviewer` 與 `role-source` 非空（MOST 沒有具名的資安 agent，`checkpoint.md` 步驟 2 只要求『做資安審查』，`role-source` 指到執行資安審的依據，例如 `docs/agent-team/checkpoint.md`）；
   - 三條的 `producer` 與 `reviewer` 都不同（不自審）。
   報告原文由 scribe 原樣代存於 `ddm-v2/tickets/BL-ENG-13/review-implement.md`（**檔名是本 ACC 新訂**，DESIGN 與 `checkpoint.md` 都沒訂；orchestrator 須把此路徑列入 review 階段的 A1 授權路徑，否則 scribe 無權寫入而 ACC-1-14 無從 PASS；合成一份，章節照 `checkpoint.md` 步驟 3：`## 阻擋級`、`## 建議`、`## 資安`、`## 測試結果`、`## 邏輯變更提案`），其中 `domain_id: <id>` 行（行首）只可有 `auth-rbac`。
4. **implement 階段**：`domains.yaml` 與 `decisions.log` 在**同一筆**提交（design：『整個 implement 階段只有 1 筆 MOST 提交』）；提交標題以 `docs:` 開頭；`decisions.log` 追加的那一行格式依 design『與既有流程的銜接』：五個以 Tab 分隔的欄位——日期、`auth-rbac`、含 `docs/agent-team/domains.yaml` 的檔案欄、說明、末欄 `<分支名> blob:<40 碼雜湊>`，其中雜湊＝該提交內 `domains.yaml` 的 blob 雜湊（implementer 於 commit 前以 `git hash-object` 算出）。

**4.0.3　時點代號**（各項『何時能驗』用）：

| 代號 | 意思 | 依賴 |
|---|---|---|
| **T0** | 現在到 human 簽 ACC；只有唯讀動作。基線六檔與本 ACC 在此入庫 | 無 |
| **S1** | acceptance 關卡：human 簽 ACC 的同場（ACC-1-16 在此判定） | human |
| **IMPL** | implement 的那一筆提交完成之後（`domains.yaml` 與 `decisions.log` 已在 HEAD） | ACC 已核可；implement 授權 |
| **REVIEW** | review 階段完成、`review-implement.md` 與三條 log 已寫入之後 | IMPL |
| **VERIFY** | 本票 `verify` 階段：所有 agent 項最終重跑（HEAD 為準），結果進證據檔 | 以上全部已發生 |

除 ACC-1-16（S1）與 ACC-1-14（REVIEW 起）外，**所有 agent 項最早可驗的時點都是 IMPL**（在此之前只有基線，沒有『變更後』）；VERIFY 全部重跑一次，以那一次為準。

**4.0.4　對照組與 SKIP**：`NEGATIVE` 與 `REGRESSION` 項的對照組（同一核對在『故意做錯』的輸入上必須判 FAIL）已在本地複本構造並確認失敗；**59 次對照組執行全部確實失敗**，記錄在 `$HLP/trial/controls-all-fail.log`；『全部做對』的情境（log 另帶一條 orchestrator 轉移條，驗證 c16 不誤判）87 條 PASS、0 FAIL 記在 `$HLP/trial/good-scenario-all-pass.log`；對真實 MOST 在**未實作**的現況跑一遍（預期多項 FAIL，證明核對不是空轉）記在 `$HLP/trial/real-most-pre-implement.log`。重跑對照組：

```bash
S=$(mktemp -d)
python3 -I -B $HLP/make_scenarios.py $M $S/repos $DW/tickets/DW-38/acc/evidence/baseline      # 只 git clone $M 到 $S，不寫 $M
$HLP/run_all.sh $S/repos/good $M $S/work/good --trial          # 『全部做對』的情境：16 項核對全 PASS
$HLP/run_controls.sh $S/repos $M $S/work                         # 27 個故意做錯的情境（含 v2 新增的 two_human、wide_glob），每個指定的核對都必須 FAIL
```

`--trial` 只用於本地複本（略過『其他分支與遠端 ref 不變』，因為 clone 的 remotes 與真實 repo 不同）；**verify 對真實 MOST 跑不得帶 `--trial`**。**所有項 `允許 SKIP: 否`；本 ACC 不授權任何 SKIP**，殘留風險因此無人承擔也無需承擔；verify 不得新增。

**4.0.5　基線（REGRESSION 的基線證據，只能在 implement 之前取得）**

| 項 | 規定 |
|---|---|
| 內容 | `ddm-v2/tickets/BL-ENG-13/acc/evidence/baseline/` 六檔：`domain-map.txt`、`check-agent-config.txt`、`docs-check.txt`、`dw-check-baseline.txt`、`most-head.txt`、`sha256-inputs.txt`，**為公版 `tickets/DW-38/acc/evidence/baseline/` 同名檔的位元組複本**（取得時 MOST HEAD `dce80fac…`、分支 `feature/lb-writeback`、前後 `git status --porcelain` 相同） |
| 有效性 | 複本仍有效的判準＝`sha256-inputs.txt` 的 18 個輸入檔雜湊在目前 HEAD 下一致（PRE-4、ACC-1-15）；Draft 當下 `38b1af4` 下 18/18 一致，故**不重取**（DW-38 ACC §4.0.2：不等＝基線失效＝停下回報 human，不重取） |
| 怎麼用 | `most-head.txt` 供 `BASE`；`sha256-inputs.txt` 供 ACC-1-15 的雜湊比對與 ACC-1-11 的 `auth-rbac.md` 值；`check-agent-config.txt` 供 ACC-1-3 的逐行比對與 check_8 業務檔數；`docs-check.txt` 供 ACC-1-10 的逐行比對；`domain-map.txt`（22 路徑）供 ACC-1-8 交叉驗證 `BASE` 重算；`dw-check-baseline.txt` 是 DW-38 的 vendor 前 `dw check` 記錄，**本票的驗收項不引用它**，只因 DW-38 ACC-1-21 (c) 要求六檔齊備而同入庫 |
| 不寫進六檔的資料 | 271／458 檔的逐檔『變更前』命中、`BASE` 的 `docs_check` 輸出：**由 `BASE` 提交重算**（不可變的 git 物件，比存檔更難漂），不進 MOST |
| 時序 | 六檔在 acceptance 階段與本 ACC 同一筆 MOST 提交入庫，早於第一次改 `domains.yaml`（ACC-1-15 用 git 歷史判） |

### REQ-1　auth-rbac 的前端範圍不得含與認證／RBAC 無關的檔

### ACC-1-1 — `NEW` `shared/` 的有關檔仍歸 auth-rbac、`shared/**` 已換成三條子目錄 glob

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-1（statement：有關檔仍須觸發 auth-rbac；驗收意圖：三個有關檔命中不得消失）；DESIGN-1、DESIGN-3（`useActiveRuleSet.ts` 留在 auth-rbac） |
| 條件 | 對 HEAD 暫存樹，`shared/` 下全部檔（現況 20 個）逐檔以 `domain_guard.py map` 取命中：① `shared/api/client.ts`、`shared/auth/useMe.ts`、`shared/types/api.d.ts` 每個都含 `auth-rbac`；② `shared/api/useActiveRuleSet.ts` 含 `auth-rbac`；③ `shared/i18n/` 下任一檔都不含 `auth-rbac`；④ auth-rbac `paths` 中以 `src/frontend/src/shared/` 開頭者恰為 `shared/api/**`、`shared/types/**`、`shared/auth/**` 三條（無 `shared/**`） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ddm-v2/tickets/BL-ENG-13/acc/evidence/ACC-1-1-<日期>.md`（IMPL 與 VERIFY 各一份，檔名加 `-impl`、`-final`）；試跑：`trial/good-scenario-all-pass.log` 的 `# c1` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c1` 退出碼 0（5 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：『基線樹當作變更後』（`baseline_as_after`）c1 FAIL 2 行（i18n 仍命中 auth-rbac、仍是 `shared/**`）；『只加白名單不收窄』（`allow_only`）FAIL 2 行；『收窄過頭，漏 `shared/auth/**`』（`over_narrow`）FAIL 2 行（`useMe.ts` 失去 auth-rbac）。見 `trial/controls-all-fail.log` |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c1
```

### REQ-2　`shared/i18n/` 全部檔的領域歸屬是 i18n，且只有 i18n

### ACC-1-2 — `NEGATIVE` `shared/i18n/` 每個檔的命中集合恰為 `{i18n}`（auth-rbac 不再誤命中）

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-2（statement：每檔命中集合恰為 `{i18n}`；失敗：命中 0 或多命中）；票面 (a)；DESIGN-2 |
| 條件 | 對 HEAD 暫存樹，`shared/i18n/` 下每個檔（含 `resources/` 四檔；現況 9 檔，檔數與 BASE 相同）的 `map` 命中集合**等於** `{i18n}`（不是『含 i18n』：命中 0、`auth-rbac,i18n` 都算 FAIL） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-2-<日期>.md`（同上命名）；試跑：`trial/good-scenario-all-pass.log` 的 `# c2` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c2` 退出碼 0 |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：變更前的樹（BASE，即票面抱怨的現況）9 檔皆為 `auth-rbac,i18n` → `baseline_as_after` 與 `allow_only` 兩個情境 c2 皆 FAIL（`不符 {…: 'auth-rbac,i18n'}`）。對照組同時證明核對抓得到『多命中』 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c2
```

### REQ-3　收窄不得製造無主業務檔

### ACC-1-3 — `NEGATIVE` `check_agent_config.py` 在變更後 0 error、0 warn，check_8 的業務檔數與基線相同

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-3（不能壞：check_8 全部業務檔維持通過，整體退出碼 0、0 error、0 warn；失敗：出現任何 ERR）；DESIGN-3 的副本實跑、design『失敗與回滾』第 1 條（含缺 pyyaml 不算通過） |
| 條件 | 在 HEAD 暫存樹（`git archive HEAD`＋自工作樹複製 `.claude`）以 `python3 -I -B scripts/agent_team/check_agent_config.py` 執行：① 退出碼 0；② 摘要行 `-- 16 ok, 0 warn, 0 error --`；③ `所有業務檔（N 檔）都命中領域或在白名單` 這一行與基線檔 `check-agent-config.txt` 的同一行**逐字相同**（現況 264 檔；用基線而不寫死數字）；④ 輸出沒有任何 `WARN`／`ERR` 開頭的行，也沒有『check_8 略過』；⑤ 其餘各行與基線檔逐行相同，**唯一允許不同的是 `AGENTS.md 引用的 N 個路徑都存在` 這一行**（W0 在 AGENTS.md 加了指路，基線時 8、今日 11，與本票無關） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-3-<日期>.md`；試跑：`trial/good-scenario-all-pass.log` 的 `# c3` 段、`trial/real-most-pre-implement.log`（現況 5 行全 PASS） |
| 判定方式 | `二元` |
| 通過門檻 | `chk c3` 退出碼 0（5 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：**只收窄、不加白名單**（`narrow_only`）→ `15 ok, 0 warn, 7 error`，c3 FAIL 5 行（與 REQ 證據 7、design 對照組一致）；**少加一檔白名單**（`allow6`，缺 `config.ts`）→ `15 ok, 0 warn, 1 error`，c3 FAIL 5 行；**收窄過頭**（`over_narrow`，漏了 `shared/auth/**`，`useMe.ts` 失去領域）→ 1 error，c3 FAIL 5 行。見 `trial/controls-all-fail.log` |
| 基線證據 | `$BL/check-agent-config.txt`（`16 ok, 0 warn, 0 error`，check_8 為 264 檔；DW-38 於 `dce80fac…` 取得，複本） |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c3
```

### ACC-1-4 — `NEW` 白名單新增恰為 design 列的 7 條，附理由，且與領域命中不並存

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-3（每個被移出的檔都有明確去處、靠合乎判準的理由過關）；DESIGN-3；design『實作授權路徑上限提案』（只收窄不加白名單會 check_8 報錯；只加白名單不收窄則並存而守衛失效） |
| 條件 | 比對 BASE 與 HEAD 的 `no_domain_allowlist`：① 既有條目逐條不變、且排在前面（現況 24 條）；② 新增的路徑集合**恰等於** `shared/config.ts`、`shared/workspace.ts`、`shared/ui/{ComboBox,ErrorBoundary,Hint,RuleSetUnavailable,WorksheetRequiredNotice}.tsx` 七個；③ 每條新增有非空 `reason`；④ 七個路徑在 HEAD 樹中真實存在；⑤ 七檔逐檔 `map` 命中 0 領域（**白名單與領域命中不並存**）；⑥ `shared/api/useActiveRuleSet.ts` 不在白名單。**『7 條的理由是否合乎白名單判準』不由機械判，由 ACC-1-16（human）判** |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-4-<日期>.md`；試跑：`trial/good-scenario-all-pass.log` 的 `# c4` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c4` 退出碼 0（6 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：`narrow_only`（新增 0 條）、`allow6`（新增只有 6 條）、`baseline_as_after`（新增 0 條且七檔仍被 auth-rbac 命中）皆 c4 FAIL |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c4
```

### REQ-4　outbox 相關的測試與決策文件必須被領域守衛覆蓋

### ACC-1-5 — `NEW` 兩個 outbox 測試被某領域命中、ADR-027 登記為某領域 docs、outbox 程式路徑命中不消失

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-4（statement；失敗：任一測試命中 0、ADR-027 不在任何領域 `docs`、outbox 程式路徑命中變 0）；DESIGN-4 |
| 條件 | ① 基線（BASE 樹）兩個測試 `tests/integration/test_outbox_api.py`、`tests/unit/test_outbox.py` 命中 0（對照）；HEAD 樹兩者都命中至少一領域；② `src/ddm_v2/services/v2/outbox_service.py`、`src/ddm_v2/models/v2/outbox.py` 在 HEAD 的命中**包含**其在 BASE 的命中且非空；③ BASE 的任何領域 `docs` 都不含 ADR-027（對照），HEAD 至少一個領域的 `docs` 含 `docs/decisions/ADR-027-domain-evolution-versioning-and-ai-readiness.md`；④ `domain_guard.py map tests/unit/test_outbox.py` 的第三欄（docs）含 ADR-027（`map` 比對 `paths` 不比 `docs`，所以 ADR-027 的登記以 `docs` 清單與 `map` 第三欄驗，design DESIGN-4）；⑤ ADR-027 檔存在。（本項只判 REQ-4 的『至少一領域』；歸屬恰為哪個領域由 ACC-1-9 依 design 主案釘死） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-5-<日期>.md`；試跑：`# c5` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c5` 退出碼 0（7 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：`no_outbox`（沒加測試與 ADR）c5 FAIL 3 行；`no_adr`（沒登記 ADR-027）FAIL 2 行；`baseline_as_after` FAIL 3 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c5
```

### REQ-5　兩條 invariants 與 i18n 領域的規則文字不得被動

### ACC-1-6 — `REGRESSION` 逐領域逐欄比對：差異只有 `auth-rbac` 的 `paths` 與 `docs`；兩條 invariants 與 i18n 全欄逐字不變

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-5（兩條 invariants 與 i18n 全欄逐字不變；動它們是邏輯變更，不在 H1 答覆內）；REQ-6（其餘 10 個領域全欄不變）；REQ-3（`updated` 為檔頭維護日期）；DESIGN-5 |
| 條件 | 以 PyYAML 載入 BASE 與 HEAD 的 `domains.yaml`，對**每個領域的每個欄位**比對：① 領域 id 與順序不變（11 個）；② 欄位差異（`DIFF <領域> <欄>`）**恰為** `DIFF auth-rbac docs`、`DIFF auth-rbac paths` 兩行（design 的預期輸出，故 `anchors`、`keywords`、`invariants`、`title` 任一被動都 FAIL）；③ auth-rbac 的 `invariants` 兩條逐字不變；④ i18n 領域全欄逐字不變，且其 `invariants` 非空（防載入失敗誤判）；⑤ 其餘 10 個領域全欄不變；⑥ 頂層其他鍵（如 `version`）不變；⑦ 檔頭 `updated` 已更新為 2026-10-24 以後的日期（design 寫 2026-10-24，若實作日更晚亦可；其合理性由 ACC-1-16 判）。**動到 auth-rbac 的 `invariants` 或 i18n 領域的任何欄位（含 `invariants`、`keywords`、`anchors`）一律判 FAIL**；若 human 之後核可該動作，走 ACC 修訂（理由類別『DESIGN 變更』：design 先改、`design_hash` 變、§8.3 重核），不是 verifier 在驗收現場判過 |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-6-<日期>.md`；試跑：`# c6` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c6` 退出碼 0（7 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | BASE 的 `domains.yaml`（`$BL/sha256-inputs.txt` 的 `7e910a65…` 即其雜湊；ACC-1-15 證明 BASE 的 blob 與之相等） |
| 對照組 | 已構造並確實失敗：**動到 invariants**（`inv_changed`，把『唯一 API 入口』改成『主要 API 入口』）c6 FAIL 2 行（出現 `DIFF auth-rbac invariants`）；**動到 i18n 的 keywords**（`i18n_changed`）FAIL 3 行（`DIFF i18n keywords`）；**新增領域**（`new_domain`）FAIL（領域數 12）；**沒更新 `updated`**（`no_updated`）FAIL；基線樹當變更後（無任何編輯）FAIL 2 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c6
```

### ACC-1-7 — `REGRESSION` `domains.yaml` 的增刪行恰等於 design『實作內容』的差異（無多、無少、無順手改）

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-5（不得順手動規則文字）、REQ-6（其餘領域 `paths` 不得被改）；DESIGN-5『所有編輯限於…』、design『實作內容』（implement 階段只能做這些）、design『失敗與回滾』第 4 條 |
| 條件 | 自 design.md 的『實作內容』節機械擷取那個 diff 塊，取其 `+`／`-` 行（略過 hunk 標頭與上下文），與 `git diff -U0 BASE HEAD -- ddm-v2/docs/agent-team/domains.yaml` 的 `+`／`-` 行比對，**多重集合相等**（`updated:` 那一行的日期值正規化為同一記號，日期本身由 ACC-1-6 ⑦判）；且 BASE..HEAD 內至少有一筆改動 `domains.yaml` 的提交 |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-7-<日期>.md`；試跑：`# c7` 段（design 24 行、實際 24 行） |
| 判定方式 | `二元` |
| 通過門檻 | `chk c7` 退出碼 0 |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | BASE 的 `domains.yaml`（同 ACC-1-6）；design.md（hash 綁定，PRE-1） |
| 對照組 | 已構造並確實失敗：少一條白名單（`allow6`）、完全沒加白名單（`narrow_only`）、沒收窄（`allow_only`）、收窄過頭（`over_narrow`）、沒登記測試與 ADR（`no_outbox`、`no_adr`）、動 invariants（`inv_changed`）、動 i18n（`i18n_changed`）、沒改 `updated`（`no_updated`）、多登記一個測試（`wide_tests`）、**把兩個 outbox 測試路徑寫成一條寬 glob `tests/**/*outbox*`**（`wide_glob`）——每個情境 c7 皆 FAIL 且細節列出『只在 design／只在實際』的行。註：`wide_glob` 只有 c7 擋得住（實跑 c5、c8、c9 皆 0 FAIL，因為該 glob 在現況恰好只命中那兩檔），這是 c7 逐行比對 design 的存在理由，不得放寬 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c7
```

### REQ-6　範圍外的領域命中維持不變

### ACC-1-8 — `REGRESSION` 全量命中比對（基線 vs 變更後）：差集恰為規則涵蓋的檔，且逐檔變更後命中＝依規則由基線推得的預期

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-6（命中差異只能落在 REQ-1～REQ-4 明列的檔）；REQ-1、REQ-2、REQ-4（差異內容）；DESIGN-6（輸入 271、差異檔集）。**不寫死『18 檔』**：以規則判，筆數只記錄 |
| 條件 | 輸入＝『業務檔＋7 個點名檔』（§4.0.1；現況 264＋7＝271）。對 BASE 樹與 HEAD 樹各自逐檔 `domain_guard.py map` 得命中集合，以**規則**由 BASE 命中推得預期：(i) 七個白名單檔與 `shared/i18n/` 下的檔 → 預期＝基線命中**減去** `auth-rbac`；(ii) 兩個 outbox 測試 → 預期＝基線命中**加上** `auth-rbac`；(iii) 其餘每一檔 → 預期＝基線命中不變。判：① 輸入集合在 BASE 與 HEAD 相同且為 264＋7（無漂移，等於基線 check_8 的業務檔數）；② BASE 重算的命中與基線檔 `domain-map.txt` 的 22 條逐路徑相同（交叉驗證重算正確）；③ **每一個**輸入的 HEAD 命中＝預期；④ 實際差集（BASE≠HEAD 的檔）＝規則涵蓋且確實改變的檔集（逐檔相等，無多無少）；⑤ 差集組成為『七個白名單檔＋九個 i18n 檔＋兩個 outbox 測試』。重算指令見下，輸出列出每個差異檔的 `前 -> 後` |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-8-<日期>.md`；試跑：`# c8` 段（差集 18 檔，與 design 預期逐檔相符） |
| 判定方式 | `二元` |
| 通過門檻 | `chk c8` 退出碼 0（6 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | BASE 提交（`dce80fac…`，不可變）重算；基線檔 `$BL/domain-map.txt`（22 路徑）作交叉驗證（ACC-1-15 證明複本有效） |
| 對照組 | 已構造並確實失敗：`allow_only`（沒收窄）c8 FAIL 3 行；`over_narrow`（`useMe.ts` 失去 auth-rbac，多出規則外的差異）FAIL 3 行；`no_outbox`（缺兩個測試的差異）FAIL 3 行；`wide_tests`（多登記 `test_admin_users.py`，規則外多一個差異）FAIL 3 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑（約 20 秒；271 次子行程）。**輸入集合漂移的預定處理路徑：** 若 BASE..HEAD 之間有與本票無關的提交使輸入集合（①）或命中改變，verifier 不得現場放寬；由 human 先確認該提交與本票無關，再以 ACC 修訂（理由類別『驗證方式無效』）更新輸入集合的起算點或排除清單，human 重新核可後重驗 |

```bash
chk c8
```

### ACC-1-9 — `REGRESSION` 『不做』的檔（其他測試、兩支 migration）與 Q5 的雙重命中維持現狀；outbox 兩測試恰歸 auth-rbac

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-6（『不做』的檔命中集合維持變更前）；human 的 Q1、Q2 答覆（other tests、migration 不納入）；REQ「需要 human 決的點」Q5（`e2e/i18n-review.spec.ts` 預設不處理）；DESIGN-4（用精確檔名，不用萬用字元）、DESIGN-6 |
| 條件 | 輸入＝§4.0.1 的 271 另加 `tests/**/*.py` 與 `migrations/versions_v2/*.py` 的其餘部分（現況 264＋7＋187＝458 檔；兩個 glob 共 192 檔，其中 5 檔已在 271 內）：① 輸入集合在 BASE 與 HEAD 相同；② 除兩個 outbox 測試外，其餘 tests／migrations（現況 192 檔扣 2＝190 檔）加 ADR-027 加 `i18n-review.spec.ts` 的命中 BASE 與 HEAD **逐檔相同**；③ 兩支 outbox migration、`tests/integration/test_admin_users.py`、ADR-027 的命中仍為 0（`map` 看 `paths`）；④ `i18n-review.spec.ts` 仍為 `auth-rbac,i18n`；⑤ 兩個 outbox 測試的命中**恰為** `{auth-rbac}`（design 主案，故備案 B 的 `outbox` 領域不會在不被察覺下混入）；⑥ 其餘 tests（現況 141 檔）仍全為 0 命中 |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-9-<日期>.md`；試跑：`# c9` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c9` 退出碼 0（6 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | BASE 提交重算（同 ACC-1-8）；基線檔 `domain-map.txt` 內 `test_lb_writeback_endpoints.py` 為 0 命中的那一行可作旁證 |
| 對照組 | 已構造並確實失敗：`wide_tests`（順手把 `test_admin_users.py` 納入）c9 FAIL 3 行；`no_outbox`（兩測試命中 0）FAIL 1 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑（約 30 秒）。輸入集合漂移（①）的處理路徑同 ACC-1-8：human 確認該提交無關後，以 ACC 修訂（『驗證方式無效』）更新起算點或排除清單，verifier 不得現場放寬 |

```bash
chk c9
```

### REQ-7　領域索引檢查不得新增 error／警告

### ACC-1-10 — `REGRESSION` `docs_check.py` 的 error 與 warning 不新增（隔離樹輸出逐行同基線；HEAD 全樹無新增 WARN）

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-7（`docs_check.py` 的『領域索引檔名』與『程式入口』維持通過，不新增 error／warning）；DESIGN-7（改前改後完整輸出 `diff` 為空） |
| 條件 | 兩個暫存樹，皆不含 `graphify-out`（所以 graphify 行永遠是同一個狀態，不隨提交數漂移）：**(i) 隔離樹**＝`git archive BASE`＋把 HEAD 的 `domains.yaml` 與 `decisions.log` 覆蓋進去（只隔離本票的編輯效果）；**(ii) 全樹**＝`git archive HEAD`。判：① 隔離樹 `docs_check.py` 退出碼 0；② 隔離樹輸出（去掉 `graphify` 行、`-- N ok…` 摘要與 `exit=` 行）與基線檔 `docs-check.txt`（同樣去掉那幾類行）**逐行相同**；③ 隔離樹 WARN 行數＝基線 12、ERR 0；④ 全樹退出碼 0 且無 `ERR`；⑤ 全樹沒有基線所沒有的 `WARN` 行（若 verify 時票目錄內的證據檔造成新 WARN，這是真實的『本票造成新增警告』，FAIL） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-10-<日期>.md`；試跑：`# c10` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c10` 退出碼 0（5 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | `$BL/docs-check.txt`（DW-38 取得：`5 ok, 12 warn, 0 error`，含 graphify 一行；去 graphify 後為 4 ok、12 WARN）。**為何不比真實工作樹：** 今日真實工作樹跑 `docs_check.py` 的 graphify 行是 `落後 4 commit（未超門檻 5）`，每多一筆提交就加一，超過 5 即變 WARN，與本票編輯無關（§8 發現 5） |
| 對照組 | 已構造並確實失敗：`new_domain`（新增領域而無索引檔）c10 FAIL 3 行（多一條『缺索引 outbox』的 WARN，隔離樹 warn 13）；`baseline_tamper`（基線檔被改一行）FAIL 1 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑 |

```bash
chk c10
```

### REQ-8　auth-rbac 領域索引的同步與否須有理由

### ACC-1-11 — `REGRESSION` `docs/domains/*.md`、`DOC_REGISTRY.md` 未被動；`auth-rbac.md` 內容不變；design 對同步與否有表態

| 欄位 | 內容 |
|---|---|
| 來源 | REQ-8（`auth-rbac.md` 在未取得核可前內容不變；design 須對同步與否表態並記殘留一行）；DESIGN-8；human 對 H1 的答覆**未涵蓋**修改領域索引 |
| 條件 | ① BASE..HEAD 沒有任何改動 `ddm-v2/docs/domains/*` 或 `ddm-v2/docs/DOC_REGISTRY.md` 的提交；② `auth-rbac.md` 在 HEAD 的 sha256 ＝ 基線 `sha256-inputs.txt` 記的值（現況 `ffd4e30c…`）；③ design.md 含『**表態：不同步。**』與『**殘留（被接受的已知落差，一行）：**』（design 已定案，PRE-1 綁其 hash；此條確認 REQ-8 的『design 未表態』失敗條件不成立） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-11-<日期>.md`；試跑：`# c11` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c11` 退出碼 0（3 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | `$BL/sha256-inputs.txt` 中 `docs/domains/auth-rbac.md` 一行 |
| 對照組 | 已構造並確實失敗：`docs_touch`（implement 提交順手改了 `auth-rbac.md` 第 15 行）c11 FAIL 2 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑。**備註：** 若日後 human 另行核可同步 `auth-rbac.md`（design DESIGN-8 的『若 human 之後要同步』），那是另一個授權與 ACC 修訂，不在本 ACC |

```bash
chk c11
```

### 流程（MOST 側閉環）

### ACC-1-12 — `NEW` implement 階段單一提交：收窄與白名單同提交、`decisions.log` 恰追加一行且雜湊相符

| 欄位 | 內容 |
|---|---|
| 來源 | DESIGN『實作授權路徑上限提案』（`domains.yaml` 單一 commit；收窄與白名單必須同一 commit）、『與既有流程的銜接』（單一 commit 含 `domains.yaml` 與 `decisions.log`、標題用 `docs:`、`decisions.log` 追加一行、末欄 `<分支> blob:<雜湊>`、不記 commit hash）；`rules/stage-table.md` §1 第 7 列（一階段一次 implement）；REQ-5 |
| 條件 | ① BASE..HEAD 內**恰 1 筆**提交改動 `domains.yaml`（記為 `IMPL`）；② `decisions.log` 只在這同一筆提交內被改；③ `IMPL` 的檔案集合含 `domains.yaml` 與 `decisions.log`，其餘只可在 `ddm-v2/tickets/BL-ENG-13/` 下；④ 標題以 `docs:` 開頭；⑤ `IMPL` 內：移除 `src/frontend/src/shared/**` 一行（收窄）與新增七條白名單路徑行同在；⑥ `decisions.log` 在 `IMPL` 中相對其父提交**僅在檔尾追加恰一行**（舊列逐字不變）；⑦ 該行為五個 Tab 欄位：ISO 日期、`auth-rbac`、含 `docs/agent-team/domains.yaml`、非空說明、末欄 `<分支名> blob:<hash>`；⑧ 末欄的 `<hash>` ＝ `git rev-parse IMPL:ddm-v2/docs/agent-team/domains.yaml`（該提交內 `domains.yaml` 的實際 blob 雜湊） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-12-<日期>.md`；試跑：`# c12` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c12` 退出碼 0（8 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：`two_commits`（`domains.yaml` 與 `decisions.log` 分兩筆提交）c12 FAIL 3 行；`allow_only`／`narrow_only`（收窄與白名單不同提交）FAIL 1 行；`log_rewrite`（改了舊列）FAIL 1 行；`no_blob`（末欄沒有 blob）FAIL 1 行；`no_logline`（沒追加）FAIL 3 行；`docs_touch`、`stray_src`（提交夾帶授權外的檔）FAIL 1 行 |
| 何時能驗 | **IMPL** 起；VERIFY 重跑。**review 後需修正的出路：** 若 reviewer 於 IMPL 提交之後提出阻擋級問題而需要再改 `domains.yaml`，修正**不得**以第 2 筆改動 `domains.yaml` 的提交默默放過（條件①會 FAIL，且不得以放寬①處理）。唯一出路是 **ACC 修訂**（§5；理由類別『驗證方式無效』或『DESIGN 變更』，依該問題是否牽動 design 判），由 human 核可新版後重驗；判法不由 verifier 現場決定 |

```bash
chk c12
```

### ACC-1-13 — `NEGATIVE` 對 most-builder 的寫入不越出授權上限；9 個 untracked 檔、其他分支與遠端 ref 不動；無 amend／reset／checkout

| 欄位 | 內容 |
|---|---|
| 來源 | DESIGN『實作授權路徑上限提案』（上限：`domains.yaml`、`state.yaml`、`decisions.log` 追加；不在上限內須 human 另行核可：`docs/domains/auth-rbac.md`、`outbox.md`、`DOC_REGISTRY.md`）；REQ-8；本票各階段授權（human 2026-10-24 「授權G2／G3／G4」）的邊界：不 fetch／push／checkout／stash／reset、不動 untracked 檔 |
| 條件 | 起算點＝ACC 起草時的 MOST HEAD `38b1af44f7e19065c71189f09bdd81c9a1fac334`（design 定案提交；須為 HEAD 的祖先）。起算點之後：① 每一筆提交只改 `domains.yaml`、`decisions.log` 與 `ddm-v2/tickets/BL-ENG-13/` 下的檔；② `decisions.log` 相對起算點僅追加至多一行；③ 工作樹沒有票目錄外的已追蹤檔修改；④ 公版 DW-38 基線所記的 9 個 untracked 檔仍為 untracked 且 sha256 與基線相同；⑤ 本地與遠端 ref 與 DW-38 基線 `most-refs.txt` 相同（`feature/lb-writeback` 除外，它只前進）、仍在 `feature/lb-writeback`、無 stash；⑥ 起算點之後 HEAD 的 reflog 全為 `commit:`（無 amend、reset、checkout、pull、merge） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-13-<日期>.md`；試跑：`# c13` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c13` 退出碼 0（8 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：`docs_touch`（提交夾帶 `auth-rbac.md`）c13 FAIL 1 行；`stray_src`（夾帶 `config.ts`）FAIL 1 行；`log_rewrite`（改舊列）FAIL 1 行；`amended`（用 `--amend` 改寫）FAIL 1 行 |
| 基線證據 | 公版 `tickets/DW-38/acc/evidence/baseline/untracked-sha256.txt` 與 `most-refs.txt`（DW-38 於 `dce80fac…` 取得、已入公版庫；本項引用其絕對路徑，不複本進 MOST）；現況 9 個 untracked 檔 sha256 仍相同（Draft 當下 `sha256sum -c` 全 OK） |
| 何時能驗 | **IMPL** 起；VERIFY 重跑。**限制：** 若 Howard 在此期間於本分支上提交了與本票無關的內容，本項會 FAIL 並列出越界檔；這是『要歸因』的 FAIL，先查那筆提交的作者與範圍，不得以放寬本項處理。**預定處理路徑：** 經 human 確認該提交與本票無關後，以 ACC 修訂（理由類別『驗證方式無效』）更新起算點或排除清單，human 重新核可後重驗；同一提交若使 ACC-1-8、ACC-1-9 的輸入集合漂移，一併於該次修訂處理 |

```bash
chk c13
```

### ACC-1-14 — `NEW` review 階段派工符合 design：mechanical＋domain（auth-rbac）＋security，i18n 不派，不自審

| 欄位 | 內容 |
|---|---|
| 來源 | DESIGN『與既有流程的銜接』（review 階段：一個 `most-code-reviewer`、一個 `most-logic-reviewer` 且 `domain_id: auth-rbac`、資安固定一員；i18n 不派；`domains.yaml` 等變動檔 `map` 命中 0 領域故由 orchestrator 手動指定）；`checkpoint.md` 步驟 1～3；`roles/_common.md` §1 第 3 條（不審查自己的產出）；`rules/stage-table.md` §1 第 8 列 |
| 條件 | `state.yaml` log 與 `review-implement.md` 符合 §4.0.2 第 3 點：① review 階段 log 恰三條（`mechanical`、`domain`、`security` 各一）；② mechanical 的 `reviewer=most-code-reviewer` 且 `role-source` 指其正本；③ domain 的 `reviewer=most-logic-reviewer`、`domain_id=auth-rbac`、`role-source` 指其正本；④ security 有 `reviewer` 與 `role-source`；⑤ 每條 `producer≠reviewer`；⑥ 整份 log 內出現的 `domain_id=` 只有 `auth-rbac`；⑦ `review-implement.md` 存在、含 checkpoint 步驟 3 的五個固定章節；⑧ 報告內行首 `domain_id: <id>` 只有 `auth-rbac`。（reviewer 的『各發現都有結論』由 `rules/stage-table.md` 第 8 列離開條件與 orchestrator 管，不由本項機械判） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-14-<日期>.md`；試跑：`# c14` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c14` 退出碼 0（8 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 對照組 | 已構造並確實失敗：`review_i18n`（多派了 i18n 的 domain reviewer）c14 FAIL 2 行；`review_self`（機械審由 implementer 自己擔任）FAIL 2 行；`review_nodomain`（漏派 domain reviewer）FAIL 3 行 |
| 何時能驗 | **REVIEW** 起；VERIFY 重跑 |

```bash
chk c14
```

### ACC-1-15 — `REGRESSION` 基線有效且先於第一次改 `domains.yaml` 入庫

| 欄位 | 內容 |
|---|---|
| 來源 | stage-table §1 第 5 列與 §1.2（`REGRESSION` 基線證據須在 implement 之前取得）；`roles/verifier.md`『基線有時效』；DW-38 ACC §4.0.2『一次兩用』與其 ACC-1-21 (c)(e) |
| 條件 | ① `$BL` 六檔齊備；② 六檔與公版 `tickets/DW-38/acc/evidence/baseline/` 同名檔**位元組相同**；③ `most-head.txt` 含 `STATUS_UNCHANGED=yes` 且 `HEAD=BASE`；④ BASE 是 HEAD 的祖先；⑤ `sha256-inputs.txt` 的 18 行：BASE 提交內的檔雜湊**全部**相符，HEAD 內除 `domains.yaml`（本票要改的）外**全部**相符（含 `domain_guard.py`、`check_agent_config.py`、`docs_check.py`、`checkpoint.md`、三份 agent 正本與 `auth-rbac.md`——證明比較用的工具沒被動）；⑥ 首次把 `acc/evidence/baseline/sha256-inputs.txt` 加入 git 的提交，是 `domains.yaml` 提交（`IMPL`）的**真祖先**且時間不晚於它；⑦ `acc/ACC-1.md` 引用 `acc/evidence/baseline`；⑧ `state.yaml` log 有『基線仍有效』（§4.0.2 第 1 點） |
| 怎麼驗 | 見指令塊 |
| 證據放哪 | `ACC-1-15-<日期>.md`；試跑：`# c15` 段 |
| 判定方式 | `二元` |
| 通過門檻 | `chk c15` 退出碼 0（8 行全 PASS） |
| 環境 | `E1` |
| 驗證者 | `agent` |
| 允許 SKIP | `否` |
| 基線證據 | 本項檢查的就是基線本身（DW-38 於 2026-10-24 在 `dce80fac…` 取得、公版提交 `2e371a7`） |
| 對照組 | 已構造並確實失敗：`baseline_tamper`（基線複本被改一行，與 DW-38 的同名檔不再位元組相同）c15 FAIL 1 行 |
| 何時能驗 | **IMPL** 起（⑥ 需要 IMPL 提交存在）；VERIFY 重跑。**T0（acceptance 提交後、implement 前）可先跑 PRE-4 的 `premise`** 確認複本仍有效 |

```bash
chk c15
```

### human 項

### ACC-1-16 — `NEW` human 核可：白名單新增 7 條與檔頭 `updated` 更新（不在 H1 答覆字面內；不核可則該部分回 design）

| 欄位 | 內容 |
|---|---|
| 來源 | design『實作授權路徑上限提案』末段與『定案紀錄』待 human 事項；`state.yaml` open_questions 第 2 條；REQ-3（白名單須合乎判準）；REQ-5 邊界與 H1 答覆的字面（只涵蓋 `paths` 與文件登記） |
| 條件 | human 在 S1 對 §0 的選項 (a)／(b)／(c) 擇一作答；本項 PASS ＝ `state.yaml` log 有且僅有一條**以 ISO 日期開頭、含 `human 答覆[ACC-1-16]：` 的條目**（比對前綴；§4.0.2 第 2 點），且該條 `選項=a`。其他條（如 orchestrator 的階段轉移條，即使含 `ACC-1-16` 與 `human`）不計。選 (b) 或 (c) 時本項**未 PASS、ACC 不得定案**（不稱 FAIL）：該部分回 design，需 design 修訂後 ACC 升版；受影響項 ACC-1-1、1-4、1-7、1-8、1-12。**備案 B 與 `auth-rbac.md` 同步不在本題**（§7） |
| 怎麼驗 | human 照 §0 的三個指令看 design 的差異、DESIGN-3 與 `config.ts`，以手打文字答覆；orchestrator 逐字記入 log；agent 以指令塊判該條存在且為 (a) |
| 證據放哪 | `ddm-v2/tickets/BL-ENG-13/state.yaml` 的 log（human 原話）；`ACC-1-16-<日期>.md` 貼 `chk c16` 輸出 |
| 判定方式 | `二元`（由 human 判定，`chk c16` 只確認答覆已入檔；agent 不代判） |
| 通過門檻 | `chk c16` 退出碼 0，且 log 條的原話是 human 手打 |
| 環境 | `E1` |
| 驗證者 | `human` |
| 允許 SKIP | `否` |
| 對照組 | 已構造：`no_human`（沒有答覆條，只有一條 orchestrator 轉移條含 `ACC-1-16` 與 `human` 字樣）、`human_b`（答 (b)）、`two_human`（兩條答覆條）三者 `chk c16` 皆退出碼 1，即本項未 PASS（選 (b) 的語意是『未 PASS、ACC 不得定案』，不是驗收失敗）；反向對照：做對情境（log 另帶那條 orchestrator 轉移條）`chk c16` PASS，證明不誤判。見 `trial/controls-all-fail.log`、`trial/good-scenario-all-pass.log` |
| 何時能驗 | **S1**（ACC 定案同場）；VERIFY 重跑 `chk c16` 確認條目仍在 |

```bash
chk c16
```

---

## 5. 修訂紀錄

ACC 定案後凍結。修訂＝**開新版**，舊版保留原文並標 `superseded_by`，**human 重新核可**。

正當理由只有三類：`DESIGN 變更` / `門檻不可達` / `驗證方式無效`。

> **「結果不如預期」不是正當理由。**
> 改 ACC 讓它通過，是整套流程裡最便宜、也最毀滅性的一個動作——
> 它讓驗收失去意義，而且不會報錯。

| 版本 | 日期 | 理由（三類之一） | 核可 | 受影響項 |
|---|---|---|---|---|
| v1 | 2026-10-24 | 初版（Draft，由 verifier 起草，未核可） | （未核可） | — |
| v2 | 2026-10-24 | Draft 內修訂（尚未核可，故非 ACC 定案後修訂）：依 `review-acc-r1.md` 第 1 輪 BLOCK 的 B1（PRE-4 `premise` 僅 T0 有效，helper 在 IMPL 後改比 BASE，VERIFY 以 ACC-1-15 ⑤ 為準）、B2（`c16` 只認日期開頭且含 `human 答覆[ACC-1-16]：` 的條，取該條 `選項=`）、S1（ACC-1-12 review 後修正走 ACC 修訂）、S2（ACC-1-6 動 invariants／i18n 判 FAIL 與出路）、S3（ACC-1-16 用語統一為『未 PASS、ACC 不得定案』）、S4（ACC-1-16 選 (b) 受影響項補 ACC-1-1）、S5（458 的組成寫準）、S6（ACC-1-8／1-9／1-13 輸入集合漂移的預定處理路徑）、S7（`review-implement.md` 為新訂檔名，列入 A1 授權路徑）、S8（§0 C(5) 知悉 design 的待決 1 與白名單揭露）；另補 ACC-1-7 對照組 `wide_glob`；另依 `review-acc-r2.md` 第 2 輪 N1／N2／N3（PRE-4 補留存記錄 `trial/premise-impl.log`；§4.0.2 第 2 點補選項與前綴的書寫提醒，皆為措辭補充，不改判準、指令、計數）| `human`，`2026-10-24`（依據見檔頭核可欄：手打「(a) 簽」，回應 orchestrator 簽核清單；ACC-1-16 答 (a)） | PRE-3、PRE-4、§0、§4.0.1、§4.0.2、§4.0.4、1-6、1-7、1-8、1-9、1-12、1-13、1-16 |

---

## 6. 定案前自檢

- [x] 票裡每條驗收意圖都至少對應一條 ACC 項（**覆蓋檢查**）：REQ-1→1-1（＋1-8）；REQ-2→1-2（＋1-6）；REQ-3→1-3、1-4、1-16；REQ-4→1-5（＋1-8、1-9）；REQ-5→1-6、1-7；REQ-6→1-6、1-8、1-9；REQ-7→1-10；REQ-8→1-11（＋1-13）；design 流程銜接→1-12、1-14；授權上限→1-13；基線→1-15；human 揭露→1-16。**REQ-1～8 共 8/8**
- [x] 每條 `REGRESSION` 的基線證據**已取得**（不是『待補』）：六檔複本已入 `acc/evidence/baseline/`，BASE 提交為不可變的重算來源
- [x] 每條 `NEGATIVE` 有對照組，且對照組**確實失敗過**：1-2、1-3、1-13（另 REGRESSION 與 NEW 項亦附對照組）；59 次對照組執行全部確實失敗
- [x] 每條驗收項的環境格數已展開，沒有『所有環境』這種寫法：本票單一環境 `E1`
- [x] 所有 SKIP 已在此刻授權：**全部 `否`，不授權任何 SKIP**；`verify` 不得新增
- [x] 外部前提都是可執行斷言：PRE-1～PRE-6
- [ ] `驗證者: human` 的項數你本人接受：**1 項（ACC-1-16）**，並入 ACC 定案同一次 sitting，不增加 sitting（待 human）

## 定案前自檢（acceptance）輸出

- 覆蓋檢查: REQ-1～REQ-8 每條 → 對應 ACC 項（見上）　8/8
- 基線已取得: REGRESSION 各項（1-6、1-7、1-8、1-9、1-10、1-11、1-15）→ `acc/evidence/baseline/` 六檔複本＋`BASE` 提交重算
- 對照組已失敗過: NEGATIVE 1-2、1-3、1-13；另 1-1、1-4～1-12、1-14～1-16 的對照組亦已失敗過
- human 驗證項數: 1　← 這是 human 的關卡預算
- 項數統計: 共 16 項；`agent` 15（1-1 至 1-15）、`human` 1（1-16）；型別分布見下表

| 型別 | 項 | 數 |
|---|---|---|
| `NEW` | 1-1、1-4、1-5、1-12、1-14、1-16 | 6 |
| `NEGATIVE` | 1-2、1-3、1-13 | 3 |
| `REGRESSION` | 1-6、1-7、1-8、1-9、1-10、1-11、1-15 | 7 |
| 合計 | | 16 |

SKIP 授權：0 項。

---

## 7. 待 human 區：『不做、不預設』（本 ACC 不替 human 決定，也沒有 ACC 項驗它們成立）

| 事項 | 現況 | ACC 怎麼處理 |
|---|---|---|
| **備案 B：新增 `outbox` 領域**（連帶新增 `invariants` 區塊、`docs/domains/outbox.md`、`DOC_REGISTRY.md` 的列與計數） | design『待決 1』，建議 A（主案）並建議 B 另開票；不在 H1 答覆內 | 不預設。ACC-1-9⑤（兩測試恰為 `{auth-rbac}`）、ACC-1-6②（領域數與欄位差異）、ACC-1-11（`docs/domains/`、`DOC_REGISTRY.md` 不被動）會在 B 被不經核可地做進來時 FAIL；若 human 之後決定採 B，那是 design 與 ACC 的修訂，不是本 ACC 的某項 |
| **`docs/domains/auth-rbac.md` 同步**（第 15 行路徑、ADR-027 一條） | design『DESIGN-8』表態不同步，殘留 R1 | 不預設。ACC-1-11 守『未經核可內容不變』；human 若要同步，另行核可（design『若 human 之後要同步』） |
| outbox 以外的測試、兩支 migration 的領域覆蓋 | Q1、Q2 human 已答不納入 | 不做。ACC-1-9 守『維持現狀』 |
| `e2e/i18n-review.spec.ts` 同時命中 `i18n` 與 `auth-rbac`（Q5）、Q4（check_8 是否涵蓋 tests／migrations） | REQ 明列不處理 | 不做。ACC-1-9④ 只守它維持現狀 |

---

## 8. ACC 起草時發現（verifier 只回報，沒有改 REQ／design）

1. **基線複本與今日實跑有四處不同，但輸入雜湊 18/18 一致。** DW-38 基線取於 `dce80fac…`；今日 HEAD `38b1af4` 下：`check-agent-config.txt` 的 `AGENTS.md 引用的 N 個路徑` 由 8 變 11（W0-C2 在 AGENTS.md 加了指路）；`docs-check.txt` 的 graphify 行由『為最新（HEAD dce80fa）』變『落後 4 commit（未超門檻 5）』；`most-head.txt` 的 HEAD 是 `dce80fac…` 不是 `38b1af4`；`domain-map.txt` 只含 22 個路徑，不夠 REQ-6 的 271 檔。DW-38 的 ACC（§4.0.2 與 ACC-1-21 (c)）要求複本位元組相同、以輸入雜湊相等判有效、不等才停下，故**不重取、複本入庫**；本 ACC 以 `BASE` 提交重算補足（ACC-1-3 容許 AGENTS.md 行不同；ACC-1-10 去 graphify 行比；ACC-1-8、1-9 用重算）。若 orchestrator 認為應另取一份新基線，須先處理 DW-38 ACC-1-21 (c) 與它的衝突。
2. **派工描述『MOST HEAD 只增加了 BL-ENG-13 自己的票目錄提交』不完全成立：** `dce80fac…..38b1af4` 之間還有 W0 兩筆提交（`3aed163` vendor `_lib/`、三個別名與 `tools.yaml`；`3e1d048` 改 `AGENTS.md`、`docs/BACKLOG.md`）。它們不含任何領域守衛的輸入（PRE-4：18/18；`src/`、兩支檢查腳本、`domains.yaml`、`decisions.log` 零差異）。
3. **design『實作內容』的 diff 塊不能直接 `patch`／`git apply`：** 第一個 hunk 標頭寫 `-17,3 +17,3`，但塊內缺了最後一行上下文（空白行），`patch` 回 `malformed patch`（`trial/design-block-as-patch-REJECTED.txt`）。對 ACC 無影響（ACC-1-7 比的是 `+`／`-` 行多重集合，不套用 diff），但 implementer 不能把那一塊當 patch 機械套用，須依文字編輯；ACC-1-7 會抓到任何偏離。
4. **`docs_check.py` 在真實工作樹的結果會隨提交漂移：** graphify 落後門檻是 5 個提交（`落後 4 commit（未超門檻 5）`）；本票 acceptance、planning、implement、review 等階段的提交一多，真實工作樹的 `docs_check.py` 會多出一條 graphify WARN，與本票編輯無關。design 的『與改前輸出逐行相同』在**不含 graphify-out 的副本**成立，ACC-1-10 沿用此法（暫存樹）。提醒 orchestrator／implementer：`checkpoint.md` 步驟 6 若在真實工作樹跑出 13 warn（多一條 graphify），先看是不是這條，**不是本票造成的新增警告**，但不得因此放寬 ACC-1-10。
5. **資安審查沒有具名 agent：** MOST `agents/` 只有 `most-code-reviewer`、`most-doc-sync`、`most-logic-reviewer`；design 與 `checkpoint.md` 只說『資安：做資安審查』。ACC-1-14 對 security 只要求 `reviewer` 與 `role-source` 非空、且不自審；若 human 希望資安審查有固定的角色正本，那是另一個決定。
6. **`review-implement[<種類>]` 的 log 記法與檔名 `review-implement.md` 是本 ACC 新訂**（design 沒寫記在哪）；orchestrator 若用別的格式，ACC-1-14 會 FAIL，應依 §4.0.2 記或走 ACC 修訂。
7. **`decisions.log` 末欄形狀與既有列不同：** 既有列末欄是 commit 雜湊（例：`4b89bca, 942e268（feature/lb-writeback）`），design 選定本列記『分支 blob:雜湊』。ACC-1-12⑦⑧ 驗 design 選定的形狀；這是 design 已接受的代價（design『decisions.log』段）。
8. **輸入集合固定於基線：** ACC-1-8 要求業務檔 264＋點名檔 7＝271，ACC-1-9 要求 tests／migrations 集合在 BASE 與 HEAD 相同。若在 BASE 之後有其他票往 `src/` 或 `tests/` 新增檔，這兩項會 FAIL『輸入集合漂移』，屬 PRE 失效（等同 ACC 修訂，§2）。這是刻意的：命中比對的分母不能無聲改變。
9. **REQ-3 的『不得靠不合白名單判準的理由過關』無法機械判：** 判準是語意（無業務邏輯）。機械面只能守『恰好那 7 條、有理由、不與領域命中並存』（ACC-1-4）；理由是否合判準由 human 在 ACC-1-16 看。
10. **ACC-1-13 的起算點是常數 `38b1af4`**（design 定案提交）。ACC 與基線複本入庫之後才有 acceptance 提交，它們都在起算點之後且只動票目錄，符合條件①。
11. **本票目錄內不得有 `BL-ENG-13` 以外的 `BL-ENG-<n>`**（PRE-5）：已核為 0；本 ACC 與基線六檔都遵守（基線複本內無任何 `BL-ENG` 字樣）。`BL-DOC-4`（design 殘留 R4 提及）不屬 `BL-ENG` 系列，不觸發 C25。
12. **（v2 新增）PRE-4 的 `premise` 在 IMPL 後本來就不能比 HEAD 的 `domains.yaml`**：18 個輸入檔含本票要改的 `domains.yaml`，原版 `premise` 在 implement 後必 FAIL（`review-acc-r1.md` B1）。v2 讓 helper 在 IMPL 後改比 BASE，並明定 VERIFY 以 ACC-1-15 ⑤ 為準。
