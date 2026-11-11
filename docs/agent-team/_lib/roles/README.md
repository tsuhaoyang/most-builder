---
類別: "DOMAIN-INDEX"
狀態: "現況"
層級: "L1"
---

# 角色索引 (Roles)

7 個角色。**共同規則在 [`_common.md`](_common.md)**——各角色檔只寫自己特有的部分。

| 角色 | 階段 | 一句話 | 寫入權 |
|---|---|---|---|
| [`orchestrator`](orchestrator.md) | `intake` `planning` `observe` | 路由與切分 | 票與 task |
| [`analyst`](analyst.md) | `inventory` `requirement` | 模糊 → 可驗證條目 | 票與 REQ |
| [`architect`](architect.md) | `design` | DESIGN + ADR | DESIGN 與 ADR |
| [`verifier`](verifier.md) | `acceptance` `verify` | 定義「怎樣算做到了」並驗它 | ACC 與證據 |
| [`implementer`](implementer.md) | `implement` `release` | 照 DESIGN 寫程式 | 程式與測試 |
| [`reviewer`](reviewer.md) | `requirement` `design` `review` | 審 diff 或 REQ／DESIGN，只回報 | ❌ **無** |
| [`doc-sync`](doc-sync.md) | `docsync` | 已核可的變更 → 權威文件 | 文件 |

**2 個角色是參數化的**，不是靠增加角色數來覆蓋變化：

| 角色 | 參數 | 值從哪來 |
|---|---|---|
| `implementer` | `stack` | L2（專案的技術棧清單） |
| `reviewer` | `review_type` | L1 固定五種：`mechanical` / `domain` / `security` / `req` / `design` |

> 參數化而非拆成更多角色的理由：職責相同、禁止事項相同、輸出格式相同，
> 只有「看什麼」不同。拆開會讓同一條紀律出現在多份檔案裡，直接破 R3。

---

## 新增角色

用 [`templates/role.md`](../templates/role.md)。四個必填區塊：
`邊界（含移交對象）` / `必讀・不該讀` / `禁止` / `輸出格式（含長度上限）`。

**先問一次：這是新角色，還是既有角色的一個參數？**
多數情況是後者。

---

## 既有專案的角色歸併

> **試行。** 已用 LB 實跑 4 次，對映結論穩定，但仍有 3 個已知缺口（`tickets/DW-4/`），
> 遇到時依下方「無法判定時」處理，並回報給公版維護者。
>
> 適用於專案已有一批自己的 agent 正本、納管時走 `inventory`。
> 「新增角色」是從零建；本節是反向歸併。

逐個舊 agent 走五步。結果記成票，走 `inventory` 的批次核可，**不現場改舊檔**。

**紀錄格式：** 每個舊 agent 一節，固定五小節（對應五步）；末尾彙總四張清單：
對映表、缺角色、過載、拆層待辦。

**無法判定時：** 任何一步因資訊不足而判不出來（讀不到專案現況、判不出票庫是否合規、
stack 值不在專案 L2 清單…），一律記「待確認」並列出需要讀哪個檔，
**不得臆造**，也不得自行新增 stack 值或角色。下面各步的分支遇到判不出來時，都適用這一條。

1. **角色，還是參數？** 沿用上面「先問一次」。職責、禁止事項、輸出格式都相同，
   只有「看什麼」不同 → 參數（`implementer` 的 `stack`、`reviewer` 的 `review_type`）。
   否則對映到最接近的角色。「最接近」的判斷先讀本檔上方的角色索引表（7 角色的階段與一句話），
   選定候選後再讀該角色檔的「參數」節：
   參數的值域由專案的 L2 定義（`implementer.md`），判準仍是上面那三個「相同」；
   參數可以再帶 L2 的查詢鍵（`reviewer(domain)` 須指定領域 id，見 `reviewer.md`），那不是新角色。
   兩個舊 agent 看的東西重疊時，**不合併**：以輸出動作區分——輸出是 gate 判定（不過不准前進）
   → `verifier`；輸出是審查回報（不 gate，語意漂移升 human）→ `reviewer`（見 `verifier.md` 的「邊界」表）；
   輸出是測試 artifact 本身（測試程式、fixture）→ `implementer`（測試在其寫入權內，見 `_common.md` §7），
   其中「定義覆蓋標準並 gate」的部分仍屬 `verifier`。
2. **拆層。** 舊檔逐段標 L1（角色紀律）／L2（領域事實）／L3（工具轉接）。
   L2 搬到專案自己的 `docs/`，舊檔留一行指路。原文留在版本歷史，不整份刪。
3. **標類別。** 角色正本宣告 `SPEC（CORE）`（與本 repo 的 `roles/` 相同），不新增類別。
4. **查缺與過載。** 7 角色中無對映者 = 缺角色，寫明由誰暫代，記入 manifest 的
   `local_deviations`。單一舊 agent 同時做生產與審查（例如 design + review）
   = 違反生產者不自審，要剝離。剝離後該 agent 的**主對映**依它的首要產出物決定
   （產出設計文件 → `architect`、產出程式 → `implementer`…），其餘職責記為剝離項、歸對應角色。
   - 舊 agent 只覆蓋角色的部分階段（例如只做 verify、不做 acceptance）→ 仍對映該角色，
     未覆蓋的階段記為缺。專案沒有該階段的中介物（例如沒有 ACC）→ 記缺階段，並寫明現行的替代物；
     **歸併不替專案自造那個中介物**——那是該階段本身的工作，走該階段，不在這裡做。
   - 舊 agent 的權限對照 `_common.md` §7：超出該角色的寫入權 = 過載；
     在範圍內不算，但實際用途待人工確認。
5. **入帳。** 對映表（舊 agent → 角色(參數)）、缺角色、過載、拆層待辦，各自成票。
   專案的票庫尚未符合 `rules/doc-taxonomy.md` §1.5（例如單檔多票）→ 先列成清單、不現場開票，
   待票制轉換後再入帳。

---

## 這些角色定義不包含什麼

**L2（專案事實）不寫進角色檔：**
技術棧契約、領域 invariants、KPI 公式、時間單位規則、
測試指令、檔案所有權、具體腳本路徑。

> **實跑觀察：** 某專案 8 份成熟角色正本中最長的兩份（205 行、167 行），
> 絕大部分內容是領域事實與公式。那些是 L2——
> 混進角色定義是它們過長的原因，也讓它們無法搬到別的專案。
> 本 repo 的 7 份篇幅相近且全無領域事實，上限與其推導見 `templates/role.md`。

**L3（工具轉接）也不寫進來：** 工具名、frontmatter 格式、呼叫方式。
`_common.md` §7 只講**權限**（讀／寫／執行），不講工具名。

---

## 呼叫關係

**深度 1：只有 orchestrator（與 human）可以委派角色。**
其他角色只能指名移交 + 停下來回報。
正本與逐條禁止的呼叫：`rules/control-flow.md` §2（v0.4.0 成文）。
