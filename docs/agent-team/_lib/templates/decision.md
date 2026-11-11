---
類別: TEMPLATE → PROCESS-RECORD
狀態: 權威
層級: L1
---

# <一句話：這次 human 裁定／問題檔的主題>

> 本檔是 human 裁定檔／問題檔的通用模板（承接 ADR-0004 D12.4＋D14.1）。
> 複製整檔到 `runs/<日期>-<slug>/` 或票目錄後，把檔頭 frontmatter 的 `類別`
> 改成 `PROCESS-RECORD`（九類之一，`rules/doc-taxonomy.md` §1.4），填下列各節。
> **類別歸屬明示為 PROCESS-RECORD**：它記「某次 human 怎麼問、怎麼裁」，凍結、
> 不得引為實作依據、歸檔前暫放。**模板本身宣告 `TEMPLATE → PROCESS-RECORD`。**
> 一檔兩段：先「問題」、後「裁定」；既有散在 runs／state.yaml 的裁定不因本模板回頭變違規。

複製後的檔頭 frontmatter 形狀（示範）：

```yaml
---
類別: PROCESS-RECORD
狀態: <依 PROCESS-RECORD 的時態，凍結的當時紀錄>
票: <所涉票；可為清單>
---
```

---

## 問題　← D14.1 問題檔固定格式即此節欄位

- **背景：** <為什麼要問 human；現況與約束。>
- **選項：** <列出可選方案，各一句。>
- **建議：** <提問者的傾向與理由（不拍板，等 human 裁）。>

---

## 裁定

- **human 答覆原文：** <逐字；不轉述、不壓縮。>
- **日期：** <YYYY-MM-DD>
- **所涉票與 anchor：** <指到哪張票的哪一處（`<票號>/<ID>` 或 `<檔案>#<anchor>`）。>

---

## 追溯

<指回所折的票／ADR：這次裁定落進哪張票、記進哪個 ADR 的哪一項。>
