# ADR-014: v3 IE 認證字典為 MiniMOST 值權威

**狀態：** accepted（2026-07-05，User 核可）
**日期：** 2026-07-04
**關聯：** [../v3/v2-v3-core-logic-diff-and-integration.md](../v3/v2-v3-core-logic-diff-and-integration.md)、[../v3/impl/impl-01-rule-set-factory-v2.md](../v3/impl/impl-01-rule-set-factory-v2.md)、[../v3/impl/impl-02-engine-changes.md](../v3/impl/impl-02-engine-changes.md)、OQ-001、ADR-011

## 脈絡

ddm-v3 由 IE 工程師開發並經 IE 認證（資料與使用邏輯）。差異盤點發現 v2 與 v3 在 M 距離階梯單位（v2 誤把吋數存為 cm）、M 腳步值（v2 規格與程式本已互相矛盾）、X 捨入、G 修飾 gating、A3 返回格、I/X 檔位範圍上不一致。原「三來源分歧以工廠 Excel 為準」的裁決基準已被 v3 認證字典取代之必要性浮現。

## 決策

`docs/v3/reference/minimost_ai_dictionary_v1.json`（IE 認證）為 MiniMOST **值的唯一權威**；以新 rule-set 版本 `MINIMOST_FACTORY_V2`（converter 程式化轉換產生，禁手抄）進入系統；黃金測試依 v3 值語意重錨。

## 考慮過的選項

- **A. 逐項與 1205 Excel 再對帳後修 V1** — 曠日費時且 IE 已完成認證動作（v3 即其結論）；否決。
- **B. 直接改 V1 rule-set 數值** — 破壞既有 cycle 快照回放；違反 rule-set published 凍結原則；否決。
- **C. 新版本 V2＋黃金重錨（選定）** — 快照隔離、可回放、值有血緣；代價是雙版本並存期的心智負擔。

## 後果

- 好處：值層單一真相恢復；v2 內部「規格 vs 程式」的 M 腳步矛盾一併終結。
- 代價：黃金測試值語意重錨（CM=29 之「推 18」明確為 18 吋=45cm；X 10s→277.778；M 推 30cm→16）；core-logic spec §4/§8/§10、`ie-most-engineer` skill、驗證器全面改版（impl-02 E8 過帳表）。
- 邊界：X 捨入（ceil→half-up）屬引擎行為變更、全域生效，但歷史 `computed` 快取不重算，回放差異 ≤1 TMU 且有 V1 回放測試守護。
- **保留不變**：合計不乘 10、1 TMU=0.036s、GM=28/CM=29 黃金錨（OQ-001 未被推翻的部分）。
- published rule-set 唯一可後補資料＝同義詞（`rule_option_synonyms`，僅影響建議層不影響工時）。
- 舊裁決標記：spec §10 之 Q3（ceil）、Q6（Phase 2 檔位）由本 ADR superseded。

## 後續（2026-07-21，ADR-023）

本 ADR 立下「值只能從認證字典 JSON 經 converter 進入系統」，但**未回答「之後 IE 要調值怎麼辦」**——
實務上只剩「改 JSON→重跑 converter→重新部署」一條路，字典管理頁形同唯讀擺設。
[ADR-023](ADR-023-dictionary-governance-unification.md) 在**不鬆動本 ADR** 的前提下補上線上編輯路徑，
機制是把「不可變」從*版本層*下放到*血緣層*：

- `rule_sets.provenance` 記錄血緣：`certified_import`（converter 產物）／`cloned`／`manual`。
  **`certified_import` 的版本永遠不可寫**——由後端 `assert_editable` 強制，
  且是**資料庫可驗證**的事實（不是靠流程自律）。V1/V2 皆為 `certified_import`。
- 要調值 → **clone-on-write**：從認證版複製出 `draft`（provenance=`cloned`），
  改的是複本，認證版原封不動；draft 發布後才可能被啟用。
- 因此本 ADR 的「禁手改 `rule_set_seed_v2.py`」與「converter 是唯一入口」**完全維持**——
  ADR-023 新增的是*旁支*，不是後門。從 UI 或 `POST /rule-sets/import` 產生的版本
  一律 `status='draft'`＋`provenance='manual'`，**永遠不會被標成 `certified_import`**
  （import 端點硬編碼此值、不讀 payload）。

同時 ADR-023 補上本 ADR 隱含但未明說的兩件事：

1. **「哪一版在用」需要顯式旗標**。本 ADR 讓 V1/V2 同為 `published` 並存，
   卻沒有機制表達「V2 才是現行」，導致 `catalog_service`/`worksheet_service` 寫死 V1、
   而 `schemas/v2/most.py` 預設 V2 的分裂。ADR-023 加 `is_active`＋partial unique index
   （全系統恰好一個 active），寫死的預設值全數移除。
2. **回放鐵則**：治理狀態（`status`/`is_active`）只在**選版**時生效，
   **不得**進入 `load_rule_set_from_db` 的載入查詢。V1 被封存或停用後，
   引用它的歷史 cycle 仍須載得到並算出原值——這正是本 ADR「快照隔離、可回放」的
   兌現條件，有專測（`tests/integration/test_rule_set_replay_isolation.py`）守護。
