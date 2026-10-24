---
類別: "TEMPLATE → L3 轉接：入口檔"
狀態: "現況（TEMPLATE，不得被引為依據）"
票: "DW-9 / DESIGN-9"
---

# 模板：入口檔（entry file）

把團隊的**入口**轉成某工具的入口／設定檔：指路到該工具的 agent 定義集、
承載跨角色的委派深度設定（DESIGN-6）。位置依 `tools.yaml` 的
`<tool>.dirs.settings`／入口慣例決定。

渲染變數：`{{tool}}`、`{{agent_dir}}`（= `tools.yaml` 的 `<tool>.dirs` 指定）、
`{{roles}}`（七角色清單）、`{{generated_from_sha256}}`。

---

## 檔頭（DESIGN-9 第 1 項；DESIGN-5）

```
generated_by: dw gen
generated_from: roles/ + tools.yaml[{{tool}}] + manifest
generated_from_sha256: {{generated_from_sha256}}
tool: {{tool}}
```

## 角色集指路（DESIGN-9 第 2 項）

指向 `{{agent_dir}}` 下由本 `dw gen` 產出的七角色 agent 定義；
**不重述**角色契約（角色契約正本在 `roles/`，入口只指路，比照 `README.md` 採用方式第 3 條）。

```
{{roles_index}}          # 渲染：七角色 → 其 agent 定義路徑（去重後依 shared_dirs，TASK-DW9-3）
```

## 委派深度設定（DESIGN-6；TASK-DW9-5 已填實）

入口層承載「只有 orchestrator 可委派」（`rules/control-flow.md` §2.1 深度 1）的工具層設定：
`enforceable` 者對非 orchestrator 角色強制「不得再委派」（深度 1）；`partial`／`not_expressible` 者採保守基線
（不賦予再委派能力）＋可見缺口註記，**不放寬深度 1、不無聲放行**。

```
{{delegation_depth}}     # TASK-DW9-5 已填：enforceable → 深度上限 1；partial/not_expressible → 保守基線 + 缺口註記
```

## 能力映射與缺口（DESIGN-8；固定節；TASK-DW9-5 已填實）

逐條可見註記本工具無法（完全/宣告式）表達的 L1 面向（委派／讀取範圍／成本上限／權限丟棄），
每行標明 `<cap>=<枚舉值>`，`not_expressible` 集合 = 註記集合（無一靜默，ACC-1-18）：

```
{{capability_gaps}}      # TASK-DW9-5 已填：委派／讀取範圍／成本上限／權限丟棄逐條可見
```
