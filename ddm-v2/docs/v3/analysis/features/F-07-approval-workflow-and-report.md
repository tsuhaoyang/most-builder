# F-07：審核工作流與報表匯出（可執行功能規格）

> 分類：功能 ｜ 相依：CL-04、[impl-06](../../impl/impl-06-workflow-rbac.md)（v2 實作規格） ｜ 證據：api-inventory-dictionary-workflow §ANALYSIS/§REPORTS
> ⚠️ **聚合修正（DISC-04）**：v3 把工作流/audit/報表掛在獨立的 AnalysisCase（inline 手算系統），IE 真正的產出（WI/途程）反而無治理。v2 規格：**工作流掛 ProcessVersion、報表從 worksheet 出**；v3 的狀態機與報表格式（IE 認證的部分）保真移植。

## 1. 狀態機（v3 驗證可行，保真）

```
draft → submitted → reviewed → approved(=published) → retired(v3: archived)
          ↘ changes_requested → draft
```
- 非法遷移→409（v3 為 400；v2 統一 409 WORKFLOW_TRANSITION_INVALID）；每次遷移記時間戳＋audit（who/from/to/comment）。
- 角色：submit=analyst；review/request-changes=reviewer；approve=approver；retire=admin（admin 皆可）。
- `WORKFLOW_MODE=simple|full`（預設 simple＝現行 draft→published，零行為變更——impl-06）。
- 編輯權：僅 draft/changes_requested 可改內容；analyst 限本人（admin 除外）。

## 2. 使用邏輯（保真）

案件（v2＝ProcessVersion+worksheet）列表按狀態篩選 → 編輯器顯示狀態徽章與**依角色/狀態浮現的動作按鈕** → 送審/審核/退回（附意見）→ 簽核時間軸（audit）→ 隨時可匯出報表。

## 3. 報表匯出（xlsx 三 sheet，欄位保真自 v3、資料源改 worksheet）

| Sheet | 欄位 | v2 資料源 |
|---|---|---|
| 案件資訊 | 編號/產品/機種/站別/作業/廠區/線別/值版本/寬放率/狀態/時間戳＋步驟總數/總TMU(2位)/總正常秒(3位)/總標準秒(3位) | Site/Product/SKU/ProcessVersion/worksheet＋CL-04 合計 |
| 動作明細 | 步驟/說明(句子)/序列模型/頻率/**插槽明細（`A1(A)=6 | B1(B)=0 | …` tech_line 展開）**/步驟TMU/正常秒(4位)/標準秒(4位) | WiRow＋MostCycle（含 SIMO 組標示） |
| 簽核歷程 | 時間/動作(from→to)/從狀態/至狀態/執行者/備註 | workflow_audit_log |

狀態中文標籤沿用 v3：草稿/已送審/已審核/退回修改/已核准/已封存(=退役)。

## 4. API 合約（v2 落地）

`POST /api/v2/worksheets/{id}/submit|review|request-changes|approve|retire`（body: comment?）；`GET /api/v2/worksheets/{id}/audit-log`；`GET /api/v2/worksheets/{id}/export.xlsx`。編號產生用 DB sequence（v3 count+1 產號不移植——DISC-08）。

## 5. 驗收條件

- Given draft，When approve，Then 409（跳關擋）。
- Given submitted，When reviewer 退回附意見，Then 狀態=changes_requested、audit 含意見、analyst 可再編輯。
- Given approved，Then 內容凍結（PUT 409）、可 clone 新 draft。
- Given 匯出，Then 三 sheet 齊、含 SIMO 標示列的合計與 CL-04 一致、標準秒=正常秒×(1+寬放%)。
- Given simple 模式，Then 僅 draft/approved 兩態且既有 publish 流程回歸測試全綠。
