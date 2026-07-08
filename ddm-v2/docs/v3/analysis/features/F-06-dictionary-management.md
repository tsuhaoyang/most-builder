# F-06：字典（rule-set）管理——版本、匯入、選項與同義詞（可執行功能規格）

> 分類：功能 ｜ 相依：CL-03、[impl-01](../../impl/impl-01-rule-set-factory-v2.md)、[impl-05 §2](../../impl/impl-05-nlp-and-synonyms.md) ｜ 證據：api-inventory-dictionary-workflow §DICTIONARIES、frontend-usage-flows §B7
> 使用者故事：admin（值治理者）匯入/複製字典成 draft、逐選項編修與維護同義詞、驗證後發佈；分析永遠綁定值版本。

## 1. 使用邏輯（保真）

版本清單（標示 active/draft）→ 操作：**匯入 Excel**（產 draft＋warnings 報告）／**clone**（既有版本深拷貝成 draft）／**編輯器**（按參數 A~I 分頁、選項依 control_key 分組、CRUD＋duplicate＋同義詞編修＋**code 建議器**）／**publish**（驗完整性後切換生效）。

## 2. 行為規則

1. **只有 draft 可改值**；published 不可變（v3 實況 active 可改——DISC-05 不移植），唯同義詞可對 published 增補（僅影響建議層，寫入即失效快取——v3 僅 publish 失效，修正）。
2. **publish 前置驗證**：每參數（A~I）至少 1 個 active 選項（沿用 v3）＋ v2 加強：值表完整性（各帶無縫隙、必要 zero 檔存在）與黃金試算（28/29 過才可發）。
3. **匯入**：Excel → draft 版本＋逐 cell 正規化（ambiguous 產 warning 含位置）＋**逐值對照驗證**（v3 的 `\(\d+\)` regex 抓值不移植——DISC-14）＋計數與衝突報告。
4. **選項刪除**：draft 硬刪；published 不允許（v3 active 軟刪的語意由「發新版」取代）。
5. **code 建議器**（沿用 v3 UX）：由參數＋中文顯示字產唯一 option code＋替代清單。
6. 匯出：版本全量 JSON（與 AI 字典 JSON 同構，作交換格式）。

## 3. API 合約（v2 落地）

| Method | Path | 權限 | 目的 |
|---|---|---|---|
| GET | /api/v2/rule-sets | user | 版本清單（含 status） |
| POST | /api/v2/rule-sets/import | approver/admin | Excel→draft＋報告 |
| POST | /api/v2/rule-sets/{code}/clone | approver/admin | 深拷貝成 draft |
| GET/POST/PUT/DELETE | /api/v2/rule-sets/{code}/options… | 讀 user／寫 approver/admin（限 draft） | 選項 CRUD＋duplicate＋suggest-code |
| GET/POST/DELETE | /api/v2/rule-sets/{code}/synonyms | 讀 user／寫 approver/admin | 同義詞（409=歧義衝突，回既有映射） |
| POST | /api/v2/rule-sets/{code}/publish | approver/admin | 驗證＋發佈（凍結） |
| GET | /api/v2/rule-sets/{code}/export | user | 全量 JSON |

（v3 實況對照：/dictionaries 系列 18 個 endpoints；activate 與 publish 在 v2 合一——rule-set 無全域唯一 active 概念，worksheet 各自綁版本。）

## 4. 驗收條件

- Given draft 缺 I 參數選項，When publish，Then 422 並列缺項。
- Given published 版本，When 改任一 TMU，Then 409。
- Given published 版本，When 增同義詞「黏膠→x_glue」，Then 200 且 nl-draft 立即可命中。
- Given 增同義詞與既有同參數映射衝突，Then 409＋回傳既有映射。
- Given Excel 匯入含簡體詞，Then 正規化為繁體且 warning 記錄原文與位置。
- Given publish 成功，Then 黃金試算 28/29 於該版本成立（發佈報告附值）。
