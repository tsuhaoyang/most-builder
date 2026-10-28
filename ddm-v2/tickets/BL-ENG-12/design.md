---
類別: DESIGN
狀態: 已定案
票: BL-ENG-12
上游: ["REQ-1", "REQ-2", "REQ-3", "REQ-4"]
凍結於: ACC 定案（rules/doc-taxonomy.md §1.9）
偏離: 無
hash取法: set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' ddm-v2/tickets/BL-ENG-12/design.md | tr -d '\r' | sed 's/[[:space:]]*$//' | sha256sum
---

# BL-ENG-12 設計

已定案：producer=orchestrator 代 architect 起草，經獨立 reviewer(design) R1 BLOCK→修訂→R2 PASS，並由 human 核可。ACC 與 implement task 仍須另行授權。
每節對應一個 REQ，標題固定。本檔只寫「要改成什麼、改哪一處、為什麼」，不實際改產品檔。

---

## DESIGN-1　外來結果另成一區並講明（對應 REQ-1）

`WritebackPanel` 依 `diff.unmatched`（`string[]`，後端 `sorted(agg_ids - most_ids)`）的**成員關係**把 `diff.motions` 分成兩組，
不以 id 外觀（前 8 碼、`00000000`）推斷分類：

- 正常組：id 不在 `diff.unmatched` 者，維持現有逐列渲染（行為不變）。
- 外來組：id 在 `diff.unmatched` 者，不再混入正常列表，改成緊接其後的獨立一區，
  區頭用使用者語言講明「以下 N 項來自 LB、不屬於這份工序表」，N 為該區項數。
  區內每列**不以「id 前 8 碼」當步驟名稱**，改用中性標示（如「LB 結果 1…N」序號）顯示，
  並保留站別／人數（現有 `station`／`stationsMulti` 文案）供對照；不顯示「第 n 步」。

呈現取捨（已選，待 reviewer 檢視）：**另成一區、預設展開**。
不採預設收合：原條目兩種方案皆可，但收合會把「整份結果全是外來」的情況藏起來，與 REQ-2「全部皆為 unmatched 時仍可辨識」相衝。
區頭帶件數，已足以避免與正常列混淆。

- **artifact：** `ddm-v2/src/frontend/src/features/level-system/WritebackPanel.tsx#每個 motion 的實際站別／人／件數` 該區塊
- 外來列的 `data-testid`：區容器 `writeback-external`、列 `writeback-external-motion-<id>`，
  供測試分辨；正常列既有 `writeback-motion-<id>` 與 `writeback-placements` 不改名。

## DESIGN-2　空集合不渲染（對應 REQ-2）

外來區只在「`diff.unmatched` 與 `diff.motions` 的 key 交集非空」時渲染；其餘（全部正常、unmatched 為空、無任何結果列）
不輸出外來區容器、區頭或空區塊，DOM 與現況一致。

- 判準取交集而非 `unmatched.length`：避免 `unmatched` 有 id 但 `motions` 無對應列時出現「0 項」空區。
  該情況不渲染也不另提示（見「設計決定」2）。
- 全部皆 unmatched 時，正常組為空、外來區仍渲染。
- 本票只新增外來區的提示；既有以 `unattached_units_degraded` 驅動的 `writeback-lb-degraded-unattached` 不改，由 DESIGN-4 保護。

- **artifact：** `ddm-v2/src/frontend/src/features/level-system/WritebackPanel.tsx#每個 motion 的實際站別／人／件數` 之條件渲染

## DESIGN-3　zh-TW／en 文案成對（對應 REQ-3）

新增使用者可見文字（區頭含件數、外來列中性標示）於兩個語系資源檔各補一組，語意一致。
key 沿用 `levelSystem.jobs.writeback.*` 命名空間；具體 key 名於實作時定，須在兩檔同時存在。
驗證判準是兩語系下渲染出的**可見字串**，不得出現 key 字串本身或另一語系文字（不以 key 對稱當判準）。

- **artifact：** `ddm-v2/src/frontend/src/shared/i18n/resources/zh-TW.ts#levelSystem.jobs.writeback`
- **artifact：** `ddm-v2/src/frontend/src/shared/i18n/resources/en.ts#levelSystem.jobs.writeback`

## DESIGN-4　既有行為不退化與可攜測試入口（對應 REQ-4）

不改後端／API／DB 契約與型別（`WbDiff`、`WbMotion` 不動）；不碰 `missing`、`offline_diffs`、套用流程、
units／降級／丟列提示的程式與文案。`label()` 的 id 前 8 碼 fallback 仍保留給 `propagated` 等其他呼叫處，本票不移除。

驗證入口採**隔離瀏覽器掛載原元件**，不啟動 Vite／後端、不載入 `playwright.config.ts` 或 `e2e/global-setup.ts`、不寫任何 DB：

- 以 in-memory bundle（`write:false`）掛載真實 `WritebackPanel`、真實 React／i18next 與兩語系資源；
  mock 僅限 query client、`APIError` 與 store／narrative／API hook 邊界；網路全攔截、請求計數與 pageerror 須為零。
- 可行性已在公版 `DW-41/DESIGN-3` 與 `tickets/DW-41/design-feasibility.md` 實測：原元件可於隔離 Chromium 掛載並重現原問題，
  且 editable 勾選→套用互動可在不寫真資料下驗證。**該 probe 是 scratch、路徑為本機絕對路徑，不是可攜正式測試。**
- 正式測試腳本須可攜（相對路徑、不依賴本機 session 目錄），落點見「設計決定」3，並須為「無實作即失敗」的負向控制。
- 必要情境（供 ACC 逐格展開）：混合（正常＋外來）、全部外來、全部正常、無結果列、與 `unattached_units_degraded` 並存、
  zh-TW／en 各一輪、editable 套用流程回歸。

- **artifact：** `ddm-v2/src/frontend/isolated-tests/writeback-external.mjs`（新增；不在 `e2e/` 既有會寫 DB 的套件內）

---

## 設計決定（原待決項，R1 後逐項定案）

1. **文案：** 區頭 zh-TW「以下 {{count}} 項來自 LB，不屬於這份工序表」、en「{{count}} result(s) from LB do not belong to this process sheet」；
   外來列標示 zh-TW「LB 結果 {{n}}」、en「LB result {{n}}」（n 為區內序號，從 1 起）。不擴大語意、不推測來源原因。
2. **有 unmatched id 但 motions 無對應列：** 不渲染、不另提示。後端 `motions` 由全部聚合結果序列化，該情況於現行契約下不會發生；
   以交集渲染已避免空區，防禦分支不另設提示。
3. **測試入口：** 於 `ddm-v2/src/frontend/isolated-tests/writeback-external.mjs` 新增獨立 Node 腳本（不在 `e2e/` 內、不載入 `playwright.config.ts`／`e2e/global-setup.ts`），
   以 `import.meta.url` 相對路徑定位專案、使用 frontend 既有 esbuild 與 Playwright Chromium，從 `ddm-v2/src/frontend` 執行 `node isolated-tests/writeback-external.mjs`。
   須含負向控制：對未修改元件（現況）執行應在「外來區存在」斷言失敗。
4. **預設展開：** 定案為預設展開（理由見 DESIGN-1）。

REQ-4 回歸檢查清單（供 ACC 逐格）：缺失提示（`writeback-missing`，含 `lb_dropped_possible` 標記）、件數與推算標示（`writeback-units-*`）、
降級提示（`writeback-units-degraded-*`）、丟列提示、`writeback-lb-degraded-unattached`、離線差異勾選與套用（含送出內容與成功訊息）。

## 跨 repo 偏離（如實記錄）

- 本票的規格由公版 `DW-41` 採用驗證流程代起草：producer 與 orchestrator 同一人；獨立性只來自 reviewer／verifier 的獨立 context。
- 公版在 MOST 現有 vendor 的 `dw.pyz` 為舊版（不含 DW-37 的 docsync 續作修正）；本票未同步 vendor，且 `stage` 為手改（見 `state.yaml` log）。

---

## L1 變更判定

本票不改 `rules/`、`roles/`、`templates/`、`adr/` 等治理三目錄，只規劃 MOST 產品前端檔；無受凍結項。

| `<檔案>#<anchor>` | 判定 | 為什麼 |
|---|---|---|
| （無治理檔改動） | 不適用 | 本票變更在產品 code／i18n，非公版 L1 |

---

## 外部依賴的失敗行為

- 隔離 Chromium 或 bundler 不可用：驗證**停下回報**，不降級為「看 code 通過」、不啟動會寫 DB 的 e2e 套件。
- 任一網路請求或 pageerror 非零：該輪驗證視為失敗，不當作通過。
- 舊快照欄位缺失：現有元件本就直接取用 `diff` 各欄位（如 `Object.entries(diff.motions)`），本票不新增也不改變此行為；
  `WbDiff` 型別視 `unmatched`／`motions` 為必有，本票沿用此假設，不擴大支援範圍。

---

## 違反既有 invariant

- 凍結條款、R1／R3、狀態詞彙、LOG 只追加：無（本檔只在票目錄內）。
- 不寫共享 DB、不改後端／API／DB 契約：無違反。
- reviewer 寫入權：未造 PASS；`review-design.md` 待收到獨立審查原文後才存。

---

## 定案紀錄

狀態：已定案（2026-10-28）。reviewer(design) R1 BLOCK→修訂→R2 PASS（原文見 review-design.md；建議：英文區頭單複數文案可於實作時優化，不阻擋）；human 2026-10-28 22:30 原話「都核可」核可 design 定案。正規化 hash 記於 `state.yaml` 的 `design_hash`。修訂須走 §1.9 開新版 + superseded_by + 重新核可。
