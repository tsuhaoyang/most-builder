# ADR-015: NL 解析納入 scope（DraftParserPort，建議層隔離）

**狀態：** accepted（2026-07-05，User 核可；取代早期 NL backlog 決策）
**日期：** 2026-07-04
**關聯：** [WI AI Parser 系統規格](../architecture/wi-ai-parser-system-spec.md)、[ADR-014](ADR-014-v3-dictionary-as-value-authority.md)

## 脈絡

早期曾裁決 NL→MOST 暫緩。情勢變更：IE 已驗證規則式 NL 解析的使用方式（口語 WI → slot 預填建議），此功能因此納入 v2 scope。

## 決策

NL 解析納入 v2 scope，以 hexagonal `DraftParserPort` 接入（`src/ddm_v2/nlp/`，引擎外）；第一版為字典驅動 rule-based adapter（修正 v3 五項已知缺陷後重寫，不照搬現碼）；**輸出永遠是建議**，經 IE 確認才進 `slot_inputs`。

## 考慮過的選項

- **A. 照搬 v3 `nl_draft_parser.py`** — 五項結構缺陷（先命中先贏、詞表遮蔽、零正規化、脆弱 context regex、信心反置）為其自家文件所自承；否決。
- **B. 直接做 LLM 解析** — 不可離線、不確定性高、成本；v3 路線圖將其列為 Stage 1 Profile A 選項而非第一步；否決（保留為升級路徑）。
- **C. 字典驅動 rule-based 重寫＋port 預留升級（選定）** — 確定性、可黃金測試、同義詞由 DB 治理；Stage 2/3（語意檢索＋信心分流）之後以新 adapter 加入，合約不變。

## 後果

- 好處：IE 錄入效率；v3 治具防護測試全數移植為驗收案例；升級不換合約。
- 代價：新增 `opencc` 依賴；同義詞治理成本由 DB UNIQUE 約束與衝突報告吸收。
- 邊界（核心）：`most_engine` 不 import `nlp`；nl-draft API 無副作用；建議值進 save 流程時仍過引擎全套驗證——AI 層任何失效都不影響工時正確性。
