# TICKET: test_outbox_api::test_claim_pending_and_mark_published 失敗（既有、與 D10 無關）

- **狀態**：**open**（回報，未修——不在 ADR-035 D10 範圍）
- **回報者**：MOST agent（ADR-035 D10 收尾總驗發現）
- **嚴重度**：低（測試層；outbox event 領取/發布流程，未涉及任何對外 API 行為的既有測試）

## 現象（可重現，隔離也紅）

```
PYTHONPATH=src DATABASE_URL=... pytest \
  tests/integration/test_outbox_api.py::test_claim_pending_and_mark_published -q
→ 1 failed, 2 passed
```

同檔另兩案（`test_post_review_enqueues_outbox`、`test_save_enqueues_worksheet_saved`）綠。

## 與 D10 無關（已證）

- **在 D10 之前的 base commit（`2321f5e`，即 B1 的父）以完全相同方式失敗**（本輪 `git stash`＋
  `checkout 2321f5e` 實測），故非本線任何改動造成。
- 失敗路徑（`outbox_service.claim_pending`／`mark_published`）**不觸及** `lb_projection`／
  `worksheet_service` 的投影／存檔路徑、也不觸及 Level System。與作業版（D10）零交集。

## 疑似方向（供後續排查，未定論）

`test_claim_pending_and_mark_published` 先 `claim_pending(limit=50)` 領取本 run 的 review 事件、
`mark_published` 後再 `claim_pending` 應不再出現。`claimed2` 仍含該 id 的可能因：
- `claim_pending` 的可見性／`FOR UPDATE SKIP LOCKED` 與 `mark_published` 的 flush 時序；或
- 測試 DB 內既有 pending 事件量 > limit=50 導致該 id 落在第二次領取窗（環境相依，本機累積資料多時更易觸發）。

建議：獨立於乾淨 DB 重跑確認；若是 limit/可見性窗問題，於測試改用該 run 專屬過濾或提高 limit，
或於 `claim_pending` 明確排除已 published。**不阻擋 D10 合併。**
