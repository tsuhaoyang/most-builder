# BL-ENG-12 design 審查原文

> 獨立 reviewer(design) 原文，orchestrator 逐字代存、不潤飾。

## R1（2026-10-28，BLOCK）

## type／範圍
- review_type: design；範圍：`ddm-v2/tickets/BL-ENG-12/design.md` 對照已定案 REQ-1..4；核對 WritebackPanel、`WbDiff`、後端 unmatched/motions 實作及 reviewer(design) 規範。

## 阻擋級
- `design.md`「待決」— 尚列 4 項未決事項，包含文案、孤立 unmatched 的處置、正式測試入口及預設展開／收合。reviewer(design) 規範要求設計無未決項；照此稿定案，下游仍須自行決策。
- `design.md`「外部依賴的失敗行為」—「`diff.motions` 欄位缺失（舊快照）視為空集合，行為與現況一致」與程式不符。`WritebackPanel.tsx` 直接執行 `Object.entries(diff.motions)`，缺欄位會出錯；且其他 `diff` 欄位亦直接取用。若要支援此情境，須明確說明範圍與行為，不能宣稱與現況一致。

## 建議
- `design.md` DESIGN-4 — ACC 情境已涵蓋主要分類與套用流程；建議明列 REQ-4 的缺失提示、件數／降級、丟列提示等回歸檢查，並先定下可攜測試入口。
- `design.md` DESIGN-1／「待決」第 4 項 — 預設展開已明示為暫選並待 reviewer／human 檢視，並非隱藏決定；但須在定案前消除該待決項。

## 誤報
- 「依 `diff.unmatched` 成員關係分組」可行：`WbDiff` 定義 `unmatched: string[]`、`motions: Record<string, WbMotion>`；後端以 `sorted(agg_ids - most_ids)` 產生 unmatched，並由 `agg.items()` 序列化所有 motions，故 unmatched id 也會是 motions key。依 membership 分組不需改 API／後端／DB。
- REQ-2 空集合處理與既有降級提示分離的設計方向，未見違反需求；未提出為阻擋。

## 測試結果
- 未跑（依唯讀審查限制）。

BLOCK

## R2（2026-10-28，窄複核；獨立 context，與 R1 不同實例）

## type／範圍
review_type: design；R2 窄審 `design.md`，對照 R1、REQ-1..4、`WritebackPanel.tsx`，並檢視隔離測試路徑及依賴是否可行。

## 阻擋級
無。原 4 項待決事項均已明確定案：文案、無對應 motion 的 unmatched 處置、測試入口、預設展開。未見其他尚待下游自行決定的設計事項，也未見與 REQ-1..4 衝突。

## 建議
英文區頭的 `{{count}} result(s)` 可考慮改用自然的單複數文案；非阻擋。`isolated-tests/` 尚不存在，但設計將其列為新增路徑；frontend 的 `esbuild`、`playwright` 與 `@playwright/test` 依賴均存在，入口設計合理。

## 誤報
R1 指出的舊快照缺欄宣稱已修正：設計現在明確說明 `diff.motions`／`unmatched` 為必有欄位，且元件直接取用 `diff.motions`，不宣稱缺欄會被當作空集合或與現況一致。

## 測試結果 (未跑)
未執行測試或腳本，符合唯讀審查限制。

PASS
