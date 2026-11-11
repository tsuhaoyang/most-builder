---
類別: "TEMPLATE → L3 轉接：agent 定義"
狀態: "現況（TEMPLATE，不得被引為依據）"
票: "DW-9 / DESIGN-9"
---

# 模板：agent 定義（agent definition）

把**一份角色正本**（`roles/<role>.md`，含兩參數化角色 reviewer／implementer）轉成某工具的
agent 定義。檔頭格式（frontmatter／JSON／markdown body）依 `tools.yaml` 的
`<tool>.file_conventions.agent_definition` 決定。

渲染變數（`dw gen` 以角色正本 + `tools.yaml` 事實填入）：
`{{tool}}`、`{{role}}`、`{{role_stack}}`（參數化角色才有）、`{{source_role_path}}`、
`{{generated_from_sha256}}`（TASK-DW9-4 填實；本 task 骨架以佔位符產出）。

---

## 檔頭（DESIGN-9 第 1 項；DESIGN-5）

```
generated_by: dw gen
generated_from: {{source_role_path}}        # 來源角色正本的指路（L1 單一真相）
generated_from_sha256: {{generated_from_sha256}}   # 來源 hash（TASK-DW9-4 填實；此檔頭非 doc-taxonomy §1.0 九類宣告）
tool: {{tool}}
```

> 這是 L3 轉接檔的檔頭，**不是**九類文件的類別宣告（L3 轉接檔非九類文件）。

## 角色契約轉接（DESIGN-9 第 2 項：換格式，不改語意）

- **name / description** — 來自角色正本標題與第一段（`{{role}}`）。
- **邊界（移交對象）** — 逐條轉自角色正本「邊界」表；移交對象保留具名（不得改成「上報」）。
- **禁止** — 逐條轉自角色正本「禁止」節；**一條不得省略**（ACC-1-4 語意不變）。
- **必讀 / 不該讀** — 轉自角色正本「必讀 / 不該讀」；「不該讀」映為工具層讀取 deny（能表達者，見下權限映射）。
- **輸出格式** — 轉自角色正本「輸出格式」與長度上限。

> system prompt（body）承載角色正本的職責全文；frontmatter 承載機械可讀的欄位。

## 權限映射（DESIGN-4；TASK-DW9-3 填實）

把 `roles/_common.md` §7 的讀／寫／執行矩陣，以**最低公分母**映射到
`tools.yaml` 的 `<tool>.fields` / `<tool>.capabilities` 能表達的權限語彙。**只收窄不放大。**

```
{{permission_mapping}}   # TASK-DW9-3 渲染：§7 的 ✅ → 該工具許可、❌ → 不授予；reviewer 一律無寫入權
```

## 能力映射與缺口（DESIGN-8；固定節；TASK-DW9-5 已填實）

逐條列該工具標 `not_expressible` 或被丟棄／`partial`（弱化）的 L1 面向，**無一靜默**；
每行以「`<面向>（<cap>=<枚舉值>）：…`」標明其 `capabilities` 值，使 `not_expressible` 集合可自註記精確取出
（ACC-1-18：`not_expressible` 集合 = 註記集合）。收集順序固定（委派 → 讀取範圍 → 成本上限 → 權限丟棄），
同一類「無法表達」在所有工具處理一致。成本上限四工具皆 `not_expressible` → 四工具皆有此註記
（DESIGN-8 方向題 a 記為已知缺口，不對 `roles/` 新增義務）。

```
{{capability_gaps}}      # TASK-DW9-5 已填：委派(partial/not_expressible)／讀取範圍(partial/not_expressible)／成本上限(not_expressible)／權限丟棄逐條可見
```

## 委派設定（DESIGN-6；TASK-DW9-5 已填實）

依 `tools.yaml` 的 `<tool>.capabilities.delegation`：

- `enforceable`（claude／kiro）→ 非 orchestrator 角色以該工具機制強制「不得再委派」（深度 1）：
  claude `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` ＋ `disallowedTools: Agent`；kiro `permissions.rules` deny `subagent` capability。
- `partial`／`not_expressible`（cursor／copilot）→ 保守基線（不賦予再委派能力）＋在「能力映射與缺口」節可見註記
  「此工具無法（完全/宣告式）強制委派深度 1」。**絕不產出讓非 orchestrator 可再委派的設定；不放寬深度 1、不無聲放行。**
- orchestrator（§2.1 唯一可委派角色）→ 保留委派能力（深度 1 由非 orchestrator 角色端強制）。

```
{{delegation_setting}}   # TASK-DW9-5 已填：enforceable → 深度 1 強制；partial/not_expressible → 保守基線 + 缺口註記
```

## Kiro 新舊格式（DESIGN-7；僅 Kiro agent 定義；TASK-DW9-5 已填實）

依 `tools.yaml` 的 `kiro.formats`：V3（`permissions.rules`／capability 標籤）與 V2（舊工具名）並存、無終止日。
`kiro.formats.universal = not_verified`（當前 `/upgrade-agent` 文件未逐字確認單檔 universal 具名作法），
故**不假定單檔 universal**——同一產出檔內同時承載 **V3 區塊**與 **V2 區塊**（雙區塊、不只相容其一、
兩格式載入語意皆不破壞，ACC-1-16），並明記 universal 具名作法為 not_verified、以當前查證事實為準。
