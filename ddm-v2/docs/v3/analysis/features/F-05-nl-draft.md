# F-05：自然語言快速預填（NL Draft）（可執行功能規格）

> 分類：功能 ｜ 相依：CL-01/03、[impl-05](../../impl/impl-05-nlp-and-synonyms.md)（v2 實作規格——本文件為使用面） ｜ 證據：api-inventory-workbench §nl-draft、frontend-usage-flows §B2、verification-code-audit §1.2
> 使用者故事：IE 貼一句口語動作描述，系統預填模型/語境/各格選項並標明把握度；IE 確認後才成為輸入。

## 1. 使用邏輯（保真，v3 驗證過的 UX）

1. 輸入文字 →「AI 預填」→ 回：建議模型＋整體信心、context_fields（hand/from/object/to…）、每格建議（option＋TMU＋信心＋來源 badge）、缺漏欄位、警告。
2. 編輯區已有內容時詢問模式：**覆蓋全部** 或 **只填空白**。
3. badge 四態渲染把握度：明確（explicit）／推斷（inferred）／預設值（default）／待確認（missing）；低信心欄位高亮＋top-K 下拉（v2 新增，v3 無 top-K）。
4. 套用後照常走 F-01 試算迴圈；**建議永不直接落庫**（採用即普通輸入，過引擎全套驗證）。

## 2. 行為規則（v2 落地＝impl-05；此處列使用面不變量）

1. 無副作用：nl-draft 唯讀。
2. 信心序固定：exact > longest_match > retrieval > default（v3 的 default=1.0 反置 bug 不移植——查證 C-8/§1.2）。
3. 判型規則（v3 認證、測試移植）：「並壓合機台／進行壓合／執行壓合」→CM；「壓合治具／站／位置」等名詞→GM。
4. 一句多動作：v1 不拆列（同 v3），偵測到多動詞時出 warning 提示 IE 分句。
5. 輸入先正規化（NFKC/繁簡——v3 實況未接線，DISC/C-6 修正）。

## 3. API 合約

`POST /api/v2/worksheets/nl-draft` → `NLDraftResult`（raw/normalized text、suggested_seq、context、slots[]（chosen＋top_k＋needs_review）、overall_confidence、provenance）——完整 schema 見 impl-05 §3。

## 4. 驗收條件

- Given「雙手抓握主板放到DIMM壓合治具」，Then 建議 GM（治具防護）且 G=抓握、P 有建議。
- Given「推壓合治具內主板並壓合機台10秒」，Then 建議 CM 且 X=壓合機台＋秒數 10。
- Given 簡體/全形輸入，Then 命中率與繁體等價（正規化）。
- Given 任何建議，Then 其 source=default 的信心 < inferred（反置回歸測試）。
- Given 使用者未按採用，Then 資料庫零寫入。
