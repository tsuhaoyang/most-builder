---
類別: "TEMPLATE → L3 工具轉接（agent 定義／入口檔／hook 設定）"
狀態: "現況（TEMPLATE 只寫形狀，不得被引為實作依據）"
層級: "L3 轉接層的產出物形狀（由 L1 角色正本 + L2／L3 `tools.yaml` + manifest 產生）"
票: "DW-9 / TASK-DW9-2 / DESIGN-9"
---

# L3 轉接模板集

這一組模板是 `dw gen`（`tickets/DW-9/design.md#design-2-dw-gen由角色正本manifesttoolsyaml-產四工具轉接`）
渲染四工具（Claude／Cursor／Copilot／Kiro）**L3 轉接檔**時的樣板，宣告產出物的**形狀**。

> **這是 TEMPLATE，不是規則本體。** 依 `rules/doc-taxonomy.md` §1.0「模板的類別寫法」，
> 本目錄各檔宣告 `TEMPLATE → <L3 轉接類別>`，**不得被引為實作依據**；
> 權威永遠在角色正本（`roles/`，L1）與 `tools.yaml`（L2／L3 工具事實），L3 轉接檔是**派生物**。

## 三類轉接檔（DESIGN-2 票面「要做」第 2 句）

| 類別 | 模板 | 一句話 |
|---|---|---|
| agent 定義 | [`agent_definition.md`](agent_definition.md) | 把一份角色正本轉成某工具的 agent 定義（frontmatter／JSON／markdown body） |
| 入口檔 | [`entry.md`](entry.md) | 把團隊的入口（指路到角色集、委派深度設定）轉成某工具的入口檔 |
| hook 設定 | [`hook.md`](hook.md) | 把阻擋類守則（如 reviewer 無寫入、不該讀路徑）轉成某工具的 hook 設定 |

## 模板承載的共同節（DESIGN-9，跨四工具）

每一類模板都承載下列節（實際渲染時依工具事實 `tools.yaml` 填入該工具語彙）：

1. **檔頭** — 產出檔檔頭含 `generated_from_sha256:`（來源 hash，DESIGN-5，TASK-DW9-4 填實）、
   `generated_by: dw gen`、來源角色正本的指路。此檔頭是 L3 轉接檔的檔頭，
   **不是** `rules/doc-taxonomy.md` §1.0 的九類類別宣告（L3 轉接檔非九類文件）。
2. **角色契約轉接** — 由角色正本的「邊界／禁止／必讀不該讀／輸出格式」渲染成該工具的 agent 定義語彙——
   **換格式，不改語意**（DESIGN-9，TASK-DW9-9 填實：四區塊逐字搬進該工具語彙、逐條對應 baseline-roles.md）。
3. **權限映射** — 最低公分母映射的結果（DESIGN-4，TASK-DW9-3 填實）。
4. **能力映射與缺口** — 丟棄欄位與 `not_expressible` 面向的可見註記，固定節（DESIGN-8，TASK-DW9-5 填實）。
5. **委派設定** — 深度 1 強制或缺口註記（DESIGN-6，TASK-DW9-5 填實）。

## 本 task（TASK-DW9-2）做到哪裡

本 task 交付**骨架 + 模板形狀 + 四工具三類轉接能被 `dw gen --dry-run` 列出**。
下列深入邏輯留給後續 task，模板已留好固定節當接點（渲染時填入）：

- 去重、權限最低公分母映射 → `TASK-DW9-3`（已實作）
- 來源 hash（`generated_from_sha256:` 填實值）、`gen --check` → `TASK-DW9-4`（已實作）
- 委派深度 1 強制、Kiro V2／V3、能力缺口逐條可見註記 → `TASK-DW9-5`（已實作）
- 角色契約轉接（邊界／禁止／必讀不該讀／輸出格式四區塊換格式不改語意）→ `TASK-DW9-9`（已實作）

接點以 `{{…}}` 佔位符標示（渲染時由 `dw gen` 以 `tools.yaml` 事實與角色正本填入）。
