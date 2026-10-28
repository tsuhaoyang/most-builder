---
類別: "TICKET"
開票: "2026-10-28；原條目 2026-09-22 由 job-ux reviewer 記入 docs/BACKLOG.md；human 2026-10-28 20:54 原話「好 按你建議」承接選 BL-ENG-12、L1 進需求與設計；MOST 規格寫入包經 human 2026-10-28 22:19 原話「都授權」核可（範圍僅 tickets/BL-ENG-12/ 六檔，不含任何 git 寫入）。"
---

# BL-ENG-12 — 回寫產線視角把「不屬於這份工序表的 LB 列」畫得跟正常列一樣（標籤 `00000000`）

| 欄位 | 內容 |
|---|---|
| **領域** | `job-ux`（`WritebackPanel.tsx`）；相關 i18n（`levelSystem.jobs.writeback.*`） |
| **現況** | 原條目：`docs/BACKLOG.md#BL-ENG-12`——`diff.motions` 含 unmatched 的 motion（LB 有、MOST 沒有），步驟標籤查不到時以 id 前 8 碼當標籤，合成 id 即一整排 `00000000`，旁邊照常顯示「排到第 N 站，1 個人做」，與正常步驟看起來一樣。 |
| **影響** | 作業者會以為那是這份工序表的步驟；與 BL-ENG-3 同一類（顯示層沒有分辨資料的語意）。 |
| **要做** | 讓不屬於本工序表的結果可辨識，不與正常步驟混淆；確切呈現方式待 design 階段定（原條目建議：另成一區並講明、或預設收合）。 |
| **範圍** | `WritebackPanel.tsx` 的顯示分類、zh-TW／en 文案、有界的行為測試。確切路徑待 design 定。 |
| **不包含** | 不改後端／API／DB 契約，不寫共享 DB，不修 BL-ENG-1／3／9／14，不改公版規則／vendor；不含 merge／push／發版。 |
| **權威文件** | `docs/BACKLOG.md#BL-ENG-12`；`docs/lb-integration/LB_WRITEBACK_CONSUMPTION_IMPLEMENTATION_SPEC.md` F2；`docs/agent-team/domains.yaml` 的 job-ux／i18n |
| **assignee** | `orchestrator` |
| **depends_on** | 無 |

---

## 與既有票的關係

本票是公版 `DW-41`（採用驗證票）所執行的 MOST 產品真票。公版只保存採用過程與證據引用；
**狀態以同目錄 `state.yaml` 為準**，BACKLOG 條目不同步狀態（過渡形，同 BL-ENG-13）。
與 BL-ENG-3 同一類問題但範圍不同，本票不處理其 (d)(e) 兩項。

## 結果

<!-- 結案時追記。 -->

尚在規格階段。
