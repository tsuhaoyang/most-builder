---
類別: "SPEC（CORE）"
狀態: "權威"
層級: "L1（方法論，專案中立）"
適用: "所有採用 dev-workflow 的專案"
---

# 控制流 (Control Flow)

## 0. 這份文件回答什麼

`stage-table.md` 回答「現在在做哪一種工作」。本檔回答它**不**回答的兩件事：

| § | 問題 |
|---|---|
| §1 | 這張票現在**卡在誰身上**，以及它能不能被放下 |
| §2 | **誰可以叫誰** |

為什麼不併進階段主表：**階段是工作的種類，狀態是責任的歸屬。**
如果票的狀態與它所處的階段一對一，那狀態欄就是階段欄的副本，直接破 R3。
所以本檔第一條設計規則就是「狀態不得等於階段」（§1.0）。

---

## 1. 票級狀態機

### 1.0 一個狀態值得存在的條件

必須**同時**回答兩題：

1. 下一個動作該由誰做
2. 這張票現在能不能被放下（context 可否清，`context-budget.md` §1）

兩個候選狀態若這兩題答案相同，它們就是同一個狀態——合併。
這條判準把狀態數從「每階段一個」（12 個，等於階段的副本）壓到 8 個。

### 1.1 八個狀態

| 狀態 | 下一步由誰 | 可清 context | 進入條件 |
|---|---|:--:|---|
| `backlog` | **human**（排不排） | ✅ | `intake` 判為 new / revision 且已評級 |
| `speccing` | agent（analyst → architect），每階段產出經 reviewer 把關（requirement 經 reviewer(req)、design 經 reviewer(design)，L2 另加 human；核可者正本見 `stage-table.md` §1 第 3、4 列） | gate 後 | human 決定要做 |
| `awaiting_human(gate)` | **human** | ✅ **必清** | 走到該關卡（§1.2） |
| `ready` | implementer | ✅ | ACC 已定案 **且** task 已切分 **且** 依賴全完成；L0 直通路徑另計：`depth: L0` 且 `backlog → ready` 轉移經 human「做不做」核可（§6.1），無 ACC、無 task（跳過 `speccing` 與 `awaiting_human(acceptance)`），依據見 §1.3「L0 票的直通路徑」一節 |
| `active` | agent（implement → review → verify → docsync → release） | task 邊界 | implementer 開工 |
| `blocked` | **外部**（必填 `blocked_on`） | ✅ | 依賴不可用（§1.4 第 2 條） |
| `closed` | — | ✅ **必清** | 所有 task 完成 **且** ACC 每條有證據；L0 直通路徑另計：無 task、無 ACC，結案依據為 `verify` 判定（§6 L0 走 1→7→8→9，第 9 階段即 `verify`／`docsync`）通過 **且** 文件同步完成；L2 票另計：`release`（第 11 階段）對 L2 標必走（`stage-table.md` §1 第 11 列深度欄 `✔`），故對外服務的 L2 以「所有 task 完成且 ACC 每條有證據 **且** release 的部署後驗證證據已取得」為結案依據；非對外服務的 L2 不觸發 release，退回「task＋ACC」的一般結案 |
| `killed` | — | ✅ | human 下 kill 決定 |

`closed` 與 `killed` 是終態，但**仍然可定址**——票保留、票號永不重用
（`stage-table.md` §7 第 4 條）。理由見 §1.5。

### 1.2 `awaiting_human` 是單一狀態，但帶 `gate` 參數

四種關卡共用一個狀態：

```
awaiting_human(acceptance)     ← ACC 定案
awaiting_human(logic_change)   ← reviewer 發現語意漂移
awaiting_human(docsync)        ← 更新權威文件前的核可
awaiting_human(release)        ← 上線決定（對外服務）
```

在上述四個參數值之外，另有兩個承載 `speccing`／`verify` 期間 human 決定點的參數值
（DW-17 補；gate 參數值 ≠ 新增 gate，八態數不變、C24 以 `state == awaiting_human` 計數不分參數值）：

```
awaiting_human(spec_approval)  ← speccing 期間 reviewer+L2 human 對 REQ／DESIGN 的核可與 design 待決升 human
awaiting_human(verify)         ← verify 的 human 判定項
```

- `awaiting_human(spec_approval)`：承載 `speccing` 期間的 requirement 審、design PASS、
  design 待決升 human（即 reviewer+L2 human 對 REQ／DESIGN 的核可與拍板）；由 `speccing` 轉入，
  屬 §1.1 `speccing` 列「gate 後可清 context」。核可者正本見 `stage-table.md` §1 主表第 3、4 列
  （reviewer(req)／reviewer(design)＋L2 human）與 §6.1。
- `awaiting_human(verify)`：承載 `verify` 的 human 判定項（ACC 中 `驗證者: human` 的項目）；
  verify 票由 `active` 轉入 `awaiting_human(verify)`（必清），屬「gate 後可清 context」。
  核可者正本見 `stage-table.md` §1 主表第 9 列（由 ACC 決定）與 §7.1（真機／實體環境驗證）。
  不把 verify 的「依標準判結果」硬塞進定標準的 `acceptance`——方向相反。

> **「到上限」不是 gate。** WIP／關卡預算到頂（`stage-table.md` §5、§6.1）是
> C24（`count(state == awaiting_human) ≤ 1`）／WIP（`count(state in {speccing, ready, active}) ≤ 3`）
> 的計數結果，不產出 durable artifact，不另設 `awaiting_human` 參數值。
>
> **上限值可由票庫設定檔覆寫，計數對象不變（DW-7）。** 上述兩個上限（C24 的 `1`、WIP 的 `3`）
> 是**預設值**，可由票庫根的設定檔（`dw.toml` 的 `[wip] awaiting_human_max`／`in_flight_max`）覆寫；
> 設定檔缺則回落本處寫死的預設。**只有上限的數值可設定，計數對象不變**——C24 仍數
> `state == awaiting_human`、WIP 仍數 `{speccing, ready, active}`，不新增狀態、不新增 gate。
> 設定檔是 L2 專案事實（各專案自調），不進本 L1 條文；本處只定「上限可設定、來源可機械讀、缺省用預設」。
>
> **修正迴圈有可設定的輪數上限（DW-7）。** review→修→再 review、ACC FAIL→修訂→再驗 這類修正迴圈，
> 其輪數上限可由設定檔（`dw.toml` 的 `[loop] max_rounds`）設定；**缺省＝無上限**（與參數化前的現況一致，
> 不施加限制）。**到上限的去向是升 human，映射既有 gate**：屬 review／design 迴圈時升
> `awaiting_human(spec_approval)`、屬 verify 迴圈時升 `awaiting_human(verify)`——維持本節六個 gate 參數值，
> 不新增第七種。到上限本身是計數結果、不產 durable artifact、不是新 gate（同上「到上限不是 gate」）；
> 它只是**觸發**一次用既有 gate 的升 human。

> **`awaiting_human(docsync)` 的一個特例：產物本身即受管文件的票。** docsync 的更新對象與票的
> 產物重疊時（如 revert／規則修補票），其 docsync 放行以**逐票宣告偏離**承載（在該票宣告 docsync
> 併入 implement 或由 doc-sync 承接並記 log），不另設可機械判讀的放行條件；偏離的記錄比照
> `README.md` 的 `local_deviations` 原則——不防止偏離，而讓偏離成為被記錄的決定。

合併的理由就是 §1.0：四者的「下一步由誰」相同（human），
「能不能放下」相同（能，而且必須放下）。
差別只在**在等什麼**，那是參數，不是狀態。

> 這個做法與 `reviewer(review_type)`、`implementer(stack)` 的參數化同形：
> 職責與處置方式相同 → 參數；不同 → 另一個狀態。

**合併換來一個可機械檢查的 WIP 規則。**
`stage-table.md` §5 的「不得有兩張票同時卡在 human 關卡」原本只是散文，
現在等於：

```
count(tickets where state == awaiting_human) ≤ 1     ← C24
```

同理「同時在飛的票上限 3 張」= `count(state in {speccing, ready, active}) ≤ 3`。

### 1.3 轉移表

| 從 | 到 | 觸發 | 誰可觸發 |
|---|---|---|---|
| `backlog` | `speccing` | 決定要做 | **human** |
| `backlog` | `killed` | kill 決定 | **human** |
| `speccing` | `awaiting_human(acceptance)` | DESIGN 已定案、無未決項 | verifier |
| `awaiting_human(acceptance)` | `ready` | ACC 定案 + task 已切分 | **human** 核可後 orchestrator |
| `ready` | `active` | 開工 | implementer |
| `active` | `awaiting_human(…)` | 走到關卡 | 該階段主責角色 |
| `active` | `closed` | 結案條件成立 | orchestrator |
| `active` | `speccing` | **回頭**：`verify` FAIL 且屬 L-契約 / L-設計 | **human** 裁決後 orchestrator |
| 任何活躍狀態 | `blocked` | 依賴不可用 | 任何角色 |
| `blocked` | 原狀態 | 阻擋解除 | 任何角色 |

**L0 票的直通路徑**：`backlog` → `ready`，跳過 `speccing` 與
`awaiting_human(acceptance)`。依據是 `stage-table.md` §6（L0 走 1→7→8→9）。
**只有 L0 可以**，而且票上必須有 `depth: L0`。

> **`stage` 與 `assignee` 隨轉移附隨更新，不另立轉移。** 狀態轉移時，`stage` 隨主責角色移交
> 更新（由觸發該轉移的角色於交棒檔記，欄位正本見 `context-budget.md` §2），`assignee` 隨之改為
> 下一步的主責角色；兩欄的更新附隨於狀態轉移發生，不是獨立的轉移，故上表不另列。

### 1.4 硬規則

**1. L1 / L2 票不得從 `speccing` 直接進 `ready`。**
必經 `awaiting_human(acceptance)`——那是全流程唯一的必到人工關卡。

> **降低深度是跳關卡最便宜的手段。** L2 → L1 少兩道關卡，L1 → L0 少掉 ACC。
> 所以 **`depth` 只有 human 可以改**，而且下調必須有核可紀錄（C23）。
>
> 這與 `_common.md` §1 第一條同形：「不得修改規則來解除自己的阻擋」。
> 改深度不改任何規則的字，但效果一樣——**而且它看起來像在分類，不像在規避。**

**2. `blocked` 必須記 `blocked_on` 與 `blocked_since`。**
缺任一 → 擋（C21）。

> 沒有這兩欄，票會**無聲躺著**：沒有人在等它，但它也沒結案。
> `blocked_since` 是必填的理由是它讓「躺了多久」可機械查詢——
> 一個沒有日期的 `blocked` 與一個被遺忘的票無法區分。

**3. 回頭轉移是正當的，但不得無聲。**
`active` → `speccing` 必須記**原因**與**分級**（`stage-table.md` §3 的四層分流級別）。
不記 → 警告（C26）。回頭本身不是失敗，**沒有紀錄的回頭才是**。

**4. 終態的票保留，不刪除；票號永不重用。**

**5. 票的狀態只有 orchestrator 可以改**（`doc-taxonomy.md` §1 的 TICKET 列：
「誰可改 = orchestrator」），例外是 `depth`、`kill`、以及
所有 `awaiting_human` 的放行——那些是 human 的；另 `ready` → `active`（開工）由 implementer 觸發
（§1.3 轉移表、§1.1 `ready` 列「下一步由誰」），這是狀態機既有慣例「轉移由該步主責角色觸發」的一例，
不改「狀態的治理權屬 orchestrator」這條原則——implementer 觸發開工等同回報進度，非自行變更票的治理狀態。

### 1.5 實測：兩個成熟專案的票制各缺什麼

本批的狀態詞彙不是憑空設計的。兩個未採用公版的成熟專案，三個票源：

| 票源 | 狀態詞彙 | 能回答「卡在誰身上」 |
|---|---|:--:|
| 專案 A 的 backlog（現存 36 張） | **無狀態欄位** | ❌ |
| 專案 B 的 backlog（兩種前綴 + 優先序） | **無狀態欄位** | ❌ |
| 專案 B 的獨立票檔 | `open` / `closed`（兩態） | ❌ |

**0 / 3 能回答。** 兩個 backlog 根本沒有狀態欄位——它們是缺口清單，
不是票；而兩態的那個能回答「做完了沒」，不能回答「現在誰該動」。

#### 刪除已結案的票會留下懸空引用（可驗證）

專案 A 的 backlog 檔頭自己寫明「做完一項就從這裡刪除」。實測：

```
票號最大值      B44
現存票數        36
檔案裡找不到的  B11 B12 B13 B14 B15 B16 B18 B20   （8 個）
```

而那 8 個號碼**每一個都還被 1–4 份其他文件引用**。

> agent 讀到「本節解決 B16」，去票庫找不到 B16，
> **無法判斷它是做完了、被 kill 了、還是從未存在。**
> `doc-taxonomy.md` §1.5 的「結案後保留」與 §1.5 的「雙向連結強制」兩條，
> 被同一條刪除規則同時破掉。
>
> 那些票在 git 歷史裡找得回來（`git log -S`），
> 但**那需要先知道要去找**——讀文件的 agent 不會。

所以 `closed` / `killed` 是**狀態**，不是「從清單上消失」。
這也是 C25 存在的理由：擋的不是刪除這個動作，是**懸空的票號引用**。

---

## 2. 角色呼叫關係

### 2.1 深度 1：只有 orchestrator 可以委派

```
human        → 任何角色
orchestrator → 任何角色
其他角色     → 不得委派任何角色（只能指名移交 + 停下來回報）
```

「指名移交」的寫法在 `_common.md` §4。本節補的是後半段：
**指名之後，去叫人的是 orchestrator，不是你。**

三個理由，第一個最難察覺：

**① 委派鏈每多一層，回報就多一次轉述。**
被委派者說「這項未跑」，中間人回報時會壓縮成「大致完成」。
誠實回報（`_common.md` §2）的鏈在轉述處斷掉，
**而且斷掉的地方看不出來**——上層只看到一份看起來正常的回報。

**② 誰挑審查者，決定了審查結果。**
implementer 若能叫 reviewer，就是生產者挑自己的審查者。
這是 `_common.md` §7「reviewer 無寫入權」同一條原則的呼叫端版本。

**③ context 成本相乘。** 與 `context-budget.md` §1 的 WIP = 1 同理。

### 2.2 禁止的呼叫，逐條寫出會發生什麼

| 禁止 | 若允許 |
|---|---|
| implementer → reviewer | 生產者挑自己的審查者 |
| implementer → verifier | 驗收變成協商 |
| verifier → implementer | 驗收者要求修改 = 它對產出有了利害關係，不再中立 |
| reviewer → implementer | 審查者間接取得寫入權（繞過 `_common.md` §7） |
| architect → verifier | ACC 的擁有權回到生產者手上（`doc-taxonomy.md` §1.7 剛修掉的那個錯） |
| 任何角色 → doc-sync | 繞過 human 核可（doc-sync 的前置條件第 1 條） |
| 任何角色 → 自己 | 遞迴委派，**無終止條件** |

### 2.3 「角色委派」與「檢索子代理」的界線

不是所有子代理都是角色。判準一句話：

> **它的產出會不會變成 artifact，或影響關卡判定？**

- **會** → 是角色委派，§2.1 的深度 1 適用
- **不會**（唯讀檢索、找檔案、列舉設定、跑一條查詢）→ 是工具，任何角色都可以用

理由：沒有決定權的東西不會造成職責混淆。
一個「列出所有 handler 檔案」的子代理，不管誰叫它，答案都一樣。

> **但唯讀不等於無影響。** 若檢索結果被直接當成結論寫進產出，
> 而不是被呼叫者自己驗證過，它就成了 artifact 的來源——回到角色委派。
> 界線在**誰為那句話負責**，不在那個子代理能不能寫檔。

### 2.4 回報鏈不得被轉述壓縮

orchestrator 轉述子代理的回報時，以下三類內容**必須原樣帶回**：

1. 「未跑」
2. 「被阻擋」+ 已做的替代驗證
3. 「仍需人工確認」

（三者的定義在 `_common.md` §2。）

orchestrator 可以排序、可以合併重複項，**不得代為判定**——
不能把「未跑」寫成「無發現」。

> **這是整份控制流裡最容易無聲失效的一條。**
> 壓縮回報看起來像在做摘要，而摘要正是 orchestrator 的正當工作。
> 與 `doc-taxonomy.md` §1.7 的「偷偷改 ACC 到它會過」同一個形狀：
> 最便宜、最毀滅性、而且不會報錯。

---

## 3. 機械檢查

接續 `doc-taxonomy.md` §5 的 C1–C20 與 C28–C31。

> **C21–C27 的輸入全部是票庫**，而票庫本身的結構檢查在
> `doc-taxonomy.md` §5（C30 / C31）——那裡才是文件結構的正本。
> v0.4.0 時票庫結構在 L1 根本沒有定義，等於本節七條建在無人檢查的地基上
> （實跑紀錄：`runs/2026-10-05-dw-control-flow/` FG-19、FG-22）。

| # | 檢查 | 等級 |
|---|---|---|
| C21 | 票處於 `blocked` 但缺 `blocked_on` 或 `blocked_since` | **擋** |
| C22 | L1 / L2 票進入 `ready`，但無 `awaiting_human(acceptance)` 的放行紀錄 | **擋** |
| C23 | 票的 `depth` 被下調，但無 human 核可紀錄 | **擋** |
| C24 | 同時有兩張以上的票處於 `awaiting_human` | **擋** |
| C25 | 其他文件引用的票號在票庫裡找不到（**懸空票號引用**） | **擋** |
| C26 | 回頭轉移（`active` → `speccing`）無原因與分級紀錄 | 警告 |
| C27 | 非 orchestrator 的角色出現委派紀錄 | **擋** |

**C23 與 C18 同形**（`doc-taxonomy.md` §5）：兩者守的都是
「用一個看起來像分類／整理的動作，讓前面所有關卡同時失效」。
C18 是改 ACC，C23 是改深度。

**C25 是 C1（連結斷掉）的票號版本。** 既有的 C14 警告「已結案 TICKET 被刪除」
守的是動作；C25 守的是**後果**，所以它是擋。兩條不重複：
刪掉一張沒人引用的結案票是證據損失（警告），
刪掉一張**被引用**的票是斷鏈（擋）。

---

## 4. 已知缺口（未修）

**狀態機的後半段（`ready` 之後）仍未實跑過。**
根因是 v0.5.0 的實跑（`runs/2026-10-05-dw-control-flow/`）讓票正確地停在
`awaiting_human(acceptance)`——**停下來等人是流程對的樣子，不是壓測完成的樣子。**
實際跑過 3 態（`backlog` / `blocked` / `awaiting_human`），
C21–C27 實際被執行到 2 條（C21 的欄位被填、C24 被計算）。
影響範圍：`ready` → `active` → `closed`、回頭轉移（C26）、`killed` 三者
目前仍是**反推**而非實跑；前半段的實跑撞出 7 個缺口，後半段應預期同量級。
併入下一次實跑：等 `DW-1` 放行後，它會自然走過 `ready` → `active` → `closed`。

> v0.4.0 原本記的是「本檔完全沒被 dogfooding 驗過」，根因是本 repo 沒有票制。
> **票制已於 v0.5.0 建立**（`tickets/`，規則見 `doc-taxonomy.md` §1.5），
> 所以那條缺口不再是「沒有東西可以套」，而是「只套到前半段」。

**回報鏈的壓縮（§2.4）無機械檢查。**
根因是它需要比對「子代理原始回報」與「上層轉述」兩份文字，
而前者是否留存屬於 L3（工具轉接層）的能力，L1 不能假設它存在。
影響範圍：§2.4 目前只能靠角色紀律 + human 抽查覆蓋，
而它恰好是本檔自己標為「最容易無聲失效」的那一條。
併入 L3 轉接檔產出時處理——若該工具會留存子代理回報，這條就變成可檢查的。

---

## 5. 相關文件

- `rules/stage-table.md` — 階段、深度階梯、WIP 限制、incident 四層分流
- `rules/doc-taxonomy.md` — TICKET 的類別規則（§1.5）、機械檢查 C1–C20
- `rules/context-budget.md` — 交棒檔的 `state` / `stage` / `depth` 欄位（§2）
- `roles/_common.md` — 移交必須指名（§4）、誠實回報三類（§2）、權限表（§7）
- `roles/orchestrator.md` — 唯一可以改票狀態、唯一可以委派的角色
