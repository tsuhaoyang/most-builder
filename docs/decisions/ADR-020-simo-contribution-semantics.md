# ADR-020：SIMO 貢獻語義 — 對齊 v3 認證版（標記列貢獻 0）

- **狀態**：Accepted（使用者/IE 裁決於 2026-07-13）
- **決策者**：Howard（IE）＋ 審查總召
- **關聯**：ADR-014（值權威）、[MiniMOST 核心規格](../core-logic/minimost-sequence-model-core-logic-spec.md) §6

## 背景

v3→v2 移植審查（核心邏輯對比）發現 SIMO（同時動作）的總工時計算語義雙邊不同，且 v2 內部三處實作互不一致：

| 位置 | 現行語義 |
|---|---|
| v3 認證版 `calculation_v2.py:261-266,286` | boolean `is_simo`——被標記列**貢獻 0**，時間由未標記的主列吸收 |
| v2 `most_engine/calculate.py:280-298`（compute_table） | `simo_group_id` 群組——群組內取 **max 另外計入**總計 |
| v2 `services/v2/worksheet_service.py:173-203` | 同 compute_table（群組 max） |
| v2 `services/v2/cases_service.py:31` | `SUM(total_tmu × frequency)`——**完全不處理 SIMO** |

具體分歧例：(a) 單獨一列帶 `simo_group_id` 無同組夥伴 → v2 全額計入、v3 語義應為 0；(b) 主列不在群組而平行列成組 → v2＝主列＋群組max（重複計），v3＝主列。

另查 v2 前端 WiWorkbench 的「納入 TMU」欄已按 v3 語義顯示（SIMO 列劃線顯示 0），與自家後端（群組 max）矛盾——使用者看到的與算出來的不一致。

## 決策

**採 v3 認證版語義：被標記 SIMO 的列貢獻 0。**

理由：v3 的 sequence model 與 UX 是使用者（IE）驗證過的權威；v2 的群組 max 更接近 v3 的舊層實作（`most_workbench.py:179-184`）而非現行認證版；且 v2 前端顯示已是 v3 語義。

## 實作要求

1. **`most_engine/calculate.py` `compute_table`**：帶 SIMO 標記（`simo_group_id` 非空）的列貢獻 0；移除群組取 max 邏輯。總計＝Σ（未標記列的 eff TMU）。
2. **`services/v2/worksheet_service.py`**：同步移除群組 max，與 engine 一致。
3. **`services/v2/cases_service.py`**：聚合改為 `SUM(total_tmu × frequency) WHERE simo_group_id IS NULL`。
4. **資料模型語義更新**：`simo_group_id` 的意義從「群組配對鍵」轉為「SIMO 標記（附配對資訊）」——**主列不得標記**，僅從屬列標記。前端 UX 提示需同步（勾 SIMO＝此列時間被主列吸收）。
5. **黃金測試**：新增 SIMO 案例鎖定（標記列貢獻 0、單獨標記列＝0、主列未標記全額計入），納入 `scripts/core_logic/run_all.py` 或 unit golden 測試。
6. **V1 回放隔離驗證（CI Gate 5）**：既存 worksheet 若含 SIMO 群組，重算總 TMU 會變——實作時必須先盤點存量資料；若 V1 快照測試被打破，採「stored total 不動、僅新計算用新語義」或資料遷移，由 ddm-validator 驗證後定案。
7. **ddm-validator 必跑**：GM=28／CM=29 黃金錨＋V1 回放＋新 SIMO 案例全綠才可 merge。

## 後果

- 同一份含 SIMO 的工時表，總 TMU 將比舊算法**變小**（群組 max 不再另計）。對下游 LB 匯出的工時標準有實質影響，需在 release note 明示。
- v2 前端「納入」欄顯示與後端計算自此一致。
- 與 v3 的 `is_simo`/`simo_with_row_id` 欄位對映（審查 §8.6 F-12）不再有語義落差，僅剩形狀差異。
