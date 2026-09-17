# docs BACKLOG — 文件缺口票（WP-D1 盤點 → WP-D2 開票）

> **性質**：有程式、缺單一權威規格的區域。**不得現場編規格**（WP-D2 只開票、領域索引誠實標「現況以程式為準」）；
> 補 spec 需另行排程並經核准。優先序由 Howard 裁定（2026-09-17）。
> 每票：領域、現況、影響、建議補的 spec 範圍。

## BL-DOC-1（最高）— rule-set 生命週期規格
- 領域：`rule-set`
- 現況：`rule_set_service.py`（clone→改→發布→retired）、`synonym_service.py`（同義詞治理）、per-cycle `rule_set_id` 回放**只存在於程式與對話**；ADR-023 偏「詞彙治理」，無單一「rule-set 生命週期」spec。
- 影響：**「回放鐵則」（舊 worksheet 以釘版 rule_set_id 維持原值）沒有 spec＝那條鐵則只在程式與對話裡**；改到版本狀態機、synonym 唯一性、published 凍結時無權威可比對。
- 建議 spec 範圍：版本狀態機（draft/published/certified/retired）、clone provenance、`version_no` 配號序列化（advisory lock）、回放語義、synonym 正規化與唯一性（EN_LABEL_NOT_UNIQUE）、retired 閘門。

## BL-DOC-2（次之）— nlp/ lexicon／linking／routing 行為規格
- 領域：`nlp-compiler`（`nlp/**` 部分）
- 現況：`most_compiler`（policies/compile）有 ADR-033；但 `nlp/**` 20 檔（`lexicon.py`、`linking.py`、`routing.py`、`rule_based.py`、`normalization.py`、`quantities.py`…）**只有程式可讀**，AI 路徑行為無文件。
- 影響：AI 解析路徑（詞彙比對、連結、路由、規則式 planner）的行為與邊界只在程式，難審語意漂移。
- 建議 spec 範圍：lexicon 來源與正規化、linking 決策、routing（rule_based vs llm）門檻、quantities 解析與 QuantityPolicy 對接、與 engine_gate 的關係。

## BL-DOC-3（第三級）— motion-module／wi-set 規格
- 領域：`motion-module`
- 現況：`motion_module_service.py`（WI 大綱、實體化 from-module、reorder、range）、`wi_set_service.py`、`wi_context_service.py` **無專屬權威文件**（ADR-025 只談範本比對）。
- 影響：WI 兩層結構（WI⊃motion）在 worksheet 情境的實體化與版本語義無 spec。
- 建議 spec 範圍：module category（wi-template/action）、實體化與 wi_group 帶入、reorder/delete 的 SIMO 約束、版本與 TMU drift。

## BL-DOC-4（第三級）— auth-rbac 的 outbox／search 規格
- 領域：`auth-rbac`
- 現況：RBAC 有 `rbac-spec.md`＋ADR-019；但 `outbox_service.py`（R3b 事件與 review／save 同交易）、`search/**`（bge-m3 向量檢索）**無專屬文件**。
- 影響：outbox event 契約（claim/publish、payload schema version）與 search provider 邊界只在程式。
- 建議 spec 範圍：outbox event 型別與交易保證、claim_pending/mark_published 可見性、search port/adapter 契約與正規化。

## BL-DOC-5（第三級）— excel-import 流程細節規格
- 領域：`excel-import`
- 現況：ADR-013 僅骨架（2KB）；staging→submit、column_map、TARGET_FIELDS、profile 重用的細節散在 `import_service.py`。
- 影響：匯入兩階段流程與欄位對應規則無完整 spec。
- 建議 spec 範圍：staging schema、column_map 驗證（缺 description 擋）、TARGET_FIELDS（含 wi_group）、rule-set 缺庫時 fallback 的報告義務、profile 重用。
