---
類別: "ACC"
狀態: "已取代"
superseded_by: "acc/ACC-1-v2.md"
版本: "v1"
票: "BL-ENG-12"
上游: "REQ-1 至 REQ-4 / DESIGN-1 至 DESIGN-4"
核可: "human 2026-10-28 22:34 +08:00 原話「核可 ACC-1 並照上列四項」：核可 ACC-1 v1 內容、寫入本檔、實作前取回歸基線、MOST git 暫存／提交範圍（BL-ENG-12 tickets 與三個 vendor 檔）、implement 開工"
---

# ACC-1 — 回寫面板把不屬於工序表的 LB 結果另成一區並講明

## 1. DESIGN 綁定

```yaml
design:
  artifact: ddm-v2/tickets/BL-ENG-12/design.md#BL-ENG-12 設計
  normalized_sha256: 389b43472a4a670693dfd6c7e8e052aff3349b64ed968495684293514a33e819
  normalization: >
    set -o pipefail; awk 'f; /^---$/ && ++c==2 {f=1}' ddm-v2/tickets/BL-ENG-12/design.md |
    tr -d '\r' | sed 's/[[:space:]]*$//' | sha256sum
```

## 2. 外部前提

| # | 前提 | 來源 | 怎麼重驗 | 現況 |
|---|---|---|---|---|
| PRE-1 | `ddm-v2/src/frontend/node_modules` 內 esbuild 與 playwright 可用，且 Chromium 可啟動關閉 | design-feasibility（DW-41）已實測 | 腳本開頭檢查 esbuild 可匯入、`chromium.launch()` 成功，否則停止並 FAIL（不 SKIP） | 設計期成立 |
| PRE-2 | 測試只在隔離瀏覽器內掛載，無網路請求、無 DB 寫入 | design DESIGN-4 | 腳本斷言請求計數與 pageerror 為 0 | 待實作時驗 |

## 3. 環境矩陣

```yaml
source: "ddm-v2/src/frontend/src/shared/i18n/resources/ 下的語系檔（zh-TW.ts、en.ts）"
dimensions:
  - { id: E1, 值: zh-TW, 可用: yes }
  - { id: E2, 值: en, 可用: yes }
```

## 4. 驗收項（每項 × E1、E2 各一格）

### ACC-1-1 — `NEW` 混合結果時外來項另成一區並標明件數
| 來源 | REQ-1 / DESIGN-1 |
| 條件 | 結果含 1 個正常 motion 與 2 個 `diff.unmatched` 內的 motion |
| 怎麼驗 | 隔離掛載原元件；斷言 `writeback-external` 存在、區頭可見字串含件數 2、外來列不含 id 前 8 碼與「第 n 步」，正常列仍在 `writeback-placements` 且顯示「第 1 步」 |
| 證據放哪 | `ddm-v2/tickets/BL-ENG-12/evidence/` |
| 判定／門檻 | 二元；全斷言成立 |
| 驗證者 | agent；允許 SKIP：否 |

### ACC-1-2 — `NEW` 全部外來仍可辨識
| 來源 | REQ-2 / DESIGN-2 |
| 條件 | 結果只有 unmatched motion |
| 怎麼驗 | 外來區存在、件數等於全部、正常組無列 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

### ACC-1-3 — `NEGATIVE` 全部正常或無結果列時不出現外來區
| 來源 | REQ-2 / DESIGN-2 |
| 條件 | 情境 A：只有正常 motion；情境 B：unmatched 為空；情境 C：無任何結果列 |
| 怎麼驗 | 三情境皆無 `writeback-external`、無區頭文字、DOM 與基線相同（不含 `unattached_units_degraded` 提示） |
| 對照組 | 同一腳本對未修改元件跑「外來區存在」斷言，必須失敗（證明斷言有效）；另以含外來項的輸入確認有區 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

### ACC-1-4 — `NEW` 兩語系文字成對且不外露 key
| 來源 | REQ-3 / DESIGN-3 |
| 條件 | 同一混合情境在 E1、E2 各渲染 |
| 怎麼驗 | 可見字串存在、語言正確、不含 `levelSystem.jobs.writeback.` 字樣、無另一語系文字 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

### ACC-1-5 — `REGRESSION` 既有顯示與提示不變
| 來源 | REQ-4 / DESIGN-4 |
| 條件 | 對 `writeback-missing`（含 `lb_dropped_possible` 標記）、`writeback-units-*`、`writeback-units-degraded-*`、丟列提示、`writeback-lb-degraded-unattached` 的輸入 |
| 基線證據 | **implement 開始前**對未修改元件取各元素 DOM 文字，存 `evidence/baseline-*.json`；修改後逐元素比對相等 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

### ACC-1-6 — `REGRESSION` 離線差異勾選與套用
| 來源 | REQ-4 / DESIGN-4 |
| 條件 | editable 狀態、勾選一列後套用 |
| 基線證據 | implement 前對未修改元件記錄：送出內容恰一筆 `{snapshot_id, wi_row_ids:[…]}`、成功訊息、選取清除、按鈕恢復 disabled |
| 怎麼驗 | 修改後同一流程結果相等；fetch 一律被攔，實際 HTTP 請求為 0 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

### ACC-1-7 — `REGRESSION` 契約與範圍不外溢
| 來源 | REQ-4 |
| 怎麼驗 | `git diff --name-only` 只含 `WritebackPanel.tsx`、兩個語系檔、`isolated-tests/writeback-external.mjs`；`api.ts`、後端、`openapi.json`、DB 遷移皆無變更 |
| 判定／門檻 | 二元；驗證者 agent；不可 SKIP |

## 5. 修訂紀錄
| 版本 | 日期 | 理由 | 核可 | 受影響項 |
|---|---|---|---|---|
| v1 | 2026-10-28 | 初版 | human 2026-10-28 22:34 | — |

## 6. 定案前自檢
- [x] 覆蓋：REQ-1→1-1；REQ-2→1-2、1-3；REQ-3→1-4；REQ-4→1-5、1-6、1-7
- [x] REGRESSION 基線證據於 implement 前取得（1-5、1-6）：`evidence/baseline-2026-10-28.json`（8 筆；對未修改元件取得，同日 `--regress` 重跑自身通過；產品檔當時無變更）
- [x] NEGATIVE 對照組確實失敗過（1-3）：`evidence/negative-control-pre-implement.log`（未修改元件跑 `--new`，rc=1、24 項失敗）
- [x] 無 SKIP；無 human 驗證項（human 實機操作 0 次）
