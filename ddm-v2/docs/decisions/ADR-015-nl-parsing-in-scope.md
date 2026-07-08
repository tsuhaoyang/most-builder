# ADR-015: NL 解析納入 scope（DraftParserPort，建議層隔離）

**狀態：** accepted（2026-07-05，User 核可；**supersedes ADR-010**）
**日期：** 2026-07-04
**關聯：** [ADR-010-nl-to-most-backlog.md](ADR-010-nl-to-most-backlog.md)、[../v3/impl/impl-05-nlp-and-synonyms.md](../v3/impl/impl-05-nlp-and-synonyms.md)、[../v3/reference/wi-parser-upgrade/](../v3/reference/wi-parser-upgrade/)、ADR-014

## 脈絡

ADR-010 曾裁決 NL→MOST 暫緩。情勢變更：IE 已在 ddm-v3 自行開發規則式 NL 解析並認證其使用方式（口語 WI → slot 預填建議），且留下完整升級路線圖（wi-parser-upgrade 01–09）。整合 v3 時此功能為 IE 明確要求。

## 決策

NL 解析納入 v2 scope，以 hexagonal `DraftParserPort` 接入（`src/ddm_v2/nlp/`，引擎外）；第一版為字典驅動 rule-based adapter（修正 v3 五項已知缺陷後重寫，不照搬現碼）；**輸出永遠是建議**，經 IE 確認才進 `slot_inputs`。

## 考慮過的選項

- **A. 照搬 v3 `nl_draft_parser.py`** — 五項結構缺陷（先命中先贏、詞表遮蔽、零正規化、脆弱 context regex、信心反置）為其自家文件所自承；否決。
- **B. 直接做 LLM 解析** — 不可離線、不確定性高、成本；v3 路線圖將其列為 Stage 1 Profile A 選項而非第一步；否決（保留為升級路徑）。
- **C. 字典驅動 rule-based 重寫＋port 預留升級（選定）** — 確定性、可黃金測試、同義詞由 DB 治理；Stage 2/3（語意檢索＋信心分流）之後以新 adapter 加入，合約不變。

## 後果

- 好處：IE 錄入效率；v3 治具防護測試全數移植為驗收案例；升級不換合約。
- 代價：新增 `opencc` 依賴；同義詞治理成本（由 impl-05 的 UNIQUE 約束與衝突報告吸收）。
- 邊界（核心）：`most_engine` 不 import `nlp`；nl-draft API 無副作用；建議值進 save 流程時仍過引擎全套驗證——AI 層任何失效都不影響工時正確性。
