# TICKET: clone_worksheet 併發產生 process_versions 唯一鍵衝突（500）

- **狀態**：open（不在 ADR-035 D10 作業版 WP 內修；B4 取證分類為 (a) 後端問題）
- **回報者**：MOST agent（ADR-035 D10 F1 收尾取證，Howard 要求）
- **嚴重度**：中（正常單人操作不觸發；併發 clone 同一 worksheet 時 500）

## 現象（可重現）

```
cd src/frontend
E2E_BASE_URL=http://127.0.0.1:5173 npx playwright test \
  e2e/wp12-lb-tags.spec.ts e2e/level-hydrate-tags.spec.ts --workers=2 --repeat-each=3
```
偶發（時序相依）一個 `POST /api/v2/worksheets/{demo}/clone` 回 **500**，其餘 11 綠。

## 根因（server log 實證）

```
asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint
"uq_process_versions_sku_id_version_no"
  → SQLAlchemy IntegrityError → error_handlers.integrity_error_handler
```

`clone_worksheet` 為同一 `sku_id` 建新 `ProcessVersion`，`version_no = max(version_no)+1`。
兩個併發交易讀到相同的 `max`，各自 insert 相同 `(sku_id, version_no)` → 撞 partial/複合 unique
`uq_process_versions_sku_id_version_no`。這是 **read-modify-write 的競態**，非測試隔離問題
（兩 spec 各自 clone、不共享前端 state；證據＝失敗發生在 clone HTTP 呼叫，早於任何前端互動）。

## 建議修法（擇一，另 WP 評估）

1. `version_no` 改由 DB 序列 / `INSERT ... SELECT COALESCE(max,0)+1 ... ON CONFLICT DO NOTHING` 重試；或
2. clone 交易對 `(sku_id)` 取 advisory lock（`pg_advisory_xact_lock`）序列化同 SKU 的版本配號；或
3. 捕捉 `UniqueViolation` → 重讀 max、重試一次（bounded retry）。

## 對測試的暫行處置（本 WP 已做）

E2E 預設 `workers=1`（`playwright.config.ts`）序列跑時不觸發；併發僅在顯式 `--workers=2` 才現形。
本 WP 不改 clone（超出 D10 作業版範圍）；待此票排程。
