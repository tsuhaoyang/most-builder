---
類別: "TEMPLATE → L3 轉接：hook 設定"
狀態: "現況（TEMPLATE，不得被引為依據）"
票: "DW-9 / DESIGN-9"
---

# 模板：hook 設定（hook configuration）

把**阻擋類守則**轉成某工具的 hook 設定（PreToolUse 等），在工具層強制 L1 的
禁止與權限邊界——尤其 reviewer 無寫入權（`roles/_common.md` §7）、
不該讀路徑（§3）、委派深度 1（`rules/control-flow.md` §2.1）。
位置依 `tools.yaml` 的 `<tool>.dirs`／hook 慣例決定；
該工具能否以 hook 阻擋依 `tools.yaml` 的 `<tool>.capabilities.hook_can_block`。

渲染變數：`{{tool}}`、`{{generated_from_sha256}}`、`{{hook_can_block}}`。

---

## 檔頭（DESIGN-9 第 1 項；DESIGN-5）

```
generated_by: dw gen
generated_from: roles/_common.md + tools.yaml[{{tool}}] + manifest
generated_from_sha256: {{generated_from_sha256}}
tool: {{tool}}
```

## 阻擋規則（DESIGN-9 第 2 項：換格式，不改語意）

依 `tools.yaml` 的 `<tool>.capabilities.hook_can_block`：

- `enforceable` → 產出 PreToolUse hook：
  - reviewer 的寫入工具呼叫 → 阻擋（§7 無寫入權的最強可表達形式）。
  - 角色「不該讀」路徑的讀取 → 阻擋（§3，能以 hook 表達者）。
  - 非 orchestrator 的委派／spawn → 阻擋（§2.1 深度 1 的補強）。
- 非 `enforceable` → 此類阻擋改走權限／設定層，或記為缺口（見下）。

```
{{hook_rules}}           # 渲染：上列阻擋規則的該工具語彙（TASK-DW9-3/5 填實）
```

## 權限映射（DESIGN-4；TASK-DW9-3 填實）

```
{{permission_mapping}}
```

## 能力映射與缺口（DESIGN-8；固定節；TASK-DW9-5 已填實）

逐條可見註記 hook／本工具無法（完全/宣告式）表達的 L1 面向（委派／讀取範圍／成本上限／權限丟棄），
每行標 `<cap>=<枚舉值>`，`not_expressible` 集合 = 註記集合、無一靜默（ACC-1-18）：

```
{{capability_gaps}}      # TASK-DW9-5 已填：委派／讀取範圍／成本上限／權限丟棄逐條可見
```

## 委派設定（DESIGN-6；TASK-DW9-5 已填實）

`enforceable` 者對非 orchestrator 角色強制「不得再委派」（深度 1）；`partial`／`not_expressible` 者保守基線
（不賦予再委派能力）＋缺口註記。**絕不產出讓非 orchestrator 可再委派的設定。**

```
{{delegation_setting}}   # TASK-DW9-5 已填：enforceable → 深度 1 強制；partial/not_expressible → 保守基線 + 缺口註記
```
