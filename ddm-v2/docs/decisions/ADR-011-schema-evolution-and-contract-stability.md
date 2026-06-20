# ADR-011: Schema 演進與契約穩定政策（避免整合問題）

**Status:** Accepted
**Date:** 2026-06-18
**關聯：** [system-architecture-v2-spec.md](../specs/system-architecture-v2-spec.md)、[data-model-and-storage-spec.md](../specs/data-model-and-storage-spec.md)、[frontend-data-flow-spec.md](../specs/frontend-data-flow-spec.md)

## Context

v2 定點重建中，DB schema（25 表）已 migrate 上線、核心路徑（rule_set / wi_rows / most_cycles / level_entries / vocab / org）已存讀驗證。但 schema **並未凍結**：

- 部分為「先畫好、未真用」的鷹架（bom、audit、code_prefix_registry）。
- 數處明知會再長欄位：待 IE 確認項 **C1**（機台/人力分攤）、**C2**（level 巢狀>2 編碼）、**C4**（B 選用規則）、**C5**（SIMO 群組指派），以及前端缺口 **FE-1**（rule-set options 讀 DB）、**FE-2**（敘事儲存）。

問題：實作期該「先把 schema 全部定死」還是「邊做邊調」？哪個較不會出整合問題？

## Decision

採 **「契約穩定 + schema 以加法演進，由 migration 治理」** 的混合策略，**不凍結 schema、也不放任契約漂移**。

核心認知：**整合穩定靠的是「契約穩」，不是「表凍結」。** 架構已內建的解耦層即為「讓 schema 安全演進」的防火牆：DTO 契約、Repository/Service、`RuleSetData` 值物件、`slot_inputs` JSONB、Alembic migration、rule_set 版本快照、89 黃金測試。整合點（前端 / LB / 外部系統）依賴**契約**，不依賴**表**。

### 政策（實作期共同準則）

1. **契約優先穩定**：API DTO（`CycleIn`、calculate / worksheet 回應、Level 驗證、LB 輸出合約）盡量定下、少動；必須變更時**版本化**（如 v2 → v2.1），不就地破壞既有整合。
2. **schema 以「加法」演進**：加欄位 / 加表為安全變更（舊查詢不壞）。**改名 / 刪欄**為破壞性 → 避免；必要時走三步：**加新欄 → 雙寫過渡 → 廢舊欄**（跨 release）。
3. **一切 schema 變更走 Alembic migration**：版本化、可審、可回滾、各環境一致；禁止手改 DB。
4. **鷹架表延後投資**：bom / audit 等先留草圖，待該功能真正實作再補細節，不提前猜欄位。
5. **待確認項先軟承接**：C1–C5 等回覆前，以可空欄 / JSONB 承接，回來後再用加法 migration 收斂為正式欄位/表。
6. **變更後跑黃金測試**：任何引擎 / rule-set / 計算相關 schema 變更，須維持 `validate-core-logic`（122 檢查）全綠。

## Consequences

**正面：**
- 可在 IE 規則（C1–C5）尚未全數定案時持續推進，不被卡住，也不浪費力氣猜死。
- 前端 / LB / 外部對接點穩定，schema 內部演進不外溢。
- 每次變更小、可回滾、可審計。

**代價 / 注意：**
- 需紀律維持：破壞性變更（改名/刪欄）必須走三步過渡，不可圖快就地改。
- 契約版本化需要時治理（v2.1 與 v2 並存期）。
- JSONB / 可空欄承接待確認項，短期型別較鬆，待收斂為正式欄位。

## 預期的加法變更（known unknowns）

- `level_entries`：巢狀>2 編碼（C2）→ 可能加欄。
- B 選用、SIMO 群組（C4/C5）→ 可能加欄或小表。
- 敘事儲存（FE-2）、options 讀 DB labels（FE-1 正式版）。
- 機台/人力分攤語意（C1）。

以上一律以**加法 migration** 落地，藏在契約/服務之後，不影響既有整合。
