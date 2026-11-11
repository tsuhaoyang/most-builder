---
類別: TEMPLATE → DESIGN
狀態: 權威
層級: L1
---

# <票 ID> 設計　← 複製後改成實際票號

> 本檔是 DESIGN 模板。複製整檔到票目錄（`<票庫>/<ID>/design.md`）後，
> 把檔頭 frontmatter 的 `類別` 改成 `DESIGN`、`狀態` 改成 `Draft`，填下列各節。
> DESIGN 的時態／可否引為依據（implement 唯一依據）／可定址見 `rules/doc-taxonomy.md` §1.9、
> `roles/architect.md`。**模板本身宣告 `TEMPLATE → DESIGN`，不得被引為實作依據。**

複製後的檔頭 frontmatter 形狀（示範）：

```yaml
---
類別: DESIGN
狀態: <Draft → 已定案 → 已取代；§1.9>
票: <prefix>-NN
上游: <REQ-1 至 REQ-n 的清單；可為字串清單>
凍結於: ACC 定案（rules/doc-taxonomy.md §1.9）
偏離: <一句話指路；沒有就寫「無」>
hash取法: <於 repo 根執行的指令，形狀如下>
---
```

**hash 取法（於 repo 根執行，`<路徑>` 換成本檔路徑）：**
`set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' <路徑> | tr -d '\r' | sed 's/[[:space:]]*$//' | sha256sum`
（取第二個獨立成行 `---` 之後的正文、排除整個檔頭 frontmatter 區塊；界線與正本見 `rules/stage-table.md` §8.2；空輸入的 hash `e3b0c442…` 不得採用）

---

<一句話：可定址單位的約定——每節一個 REQ、標題固定、anchor 用標題不用行號
（`rules/stage-table.md` §8.1）。三目錄的寫入者依 `roles/_common.md` §7 為 doc-sync。
本檔只寫「要改成什麼、改哪一處、為什麼」，不實際改三目錄。>

---

## DESIGN-<n>　<一句話標題，對應 REQ-<n>>

<設計一句話：這一處要做成什麼。>

- **artifact：** `<路徑>#<anchor>`　← anchor 用標題，不用行號

<每節一個 REQ，標題固定。ID 形狀 `DESIGN-<n>`，票內唯一，全域定址 `<票號>/DESIGN-<n>`。>

---

## L1 變更判定　← 改三目錄時必填；形狀票亦須逐條判定

> 正本：`adr/0001-l1-freeze-and-executable-layer.md` §2.2 步驟 1。
> **此節只指路到正本的判定法，不在模板複寫判定法。**
> 逐條列本票改動的 `<檔案>#<anchor>` 並標「形狀」或「受凍結」；
> 判為受凍結者須走 §2.2 例外路徑（擴列＋ACC 例外條目）；
> 核對無受凍結漏判（形狀與受凍結不得混判）。

| `<檔案>#<anchor>` | 判定 | 為什麼（對照 ADR-0001 §2.1 (a) 判定法） |
|---|---|---|
| <路徑>#<標題> | 形狀 ｜ 受凍結 | <一句話> |

---

## 外部依賴的失敗行為

<逐條列本票產物所依賴的外部件（腳本、git、服務），以及其失敗時的行為
（停下回報／不半套用／升 human）。human 核可是關卡，不是外部依賴。>

---

## 違反既有 invariant

<逐條核對本票是否違反既有不變量（凍結條款、R1／R3、九類數量與語意、狀態詞彙、
C1–C31 等級、LOG 只追加、ADR 只追記、reviewer 寫入權……），各附「無」或處置。>

---

## 定案紀錄

<狀態；reviewer(design) 審查結論（阻擋／建議）；human 核可（若核可鏈含 human，§6.1）；
正規化 hash 記於 `state.yaml` 的 `design_hash`（§1.9、C29）；
修訂須走 §1.9 開新版 + superseded_by + 重新核可。>
