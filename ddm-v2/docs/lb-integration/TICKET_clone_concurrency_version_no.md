# TICKET: clone_worksheet 併發產生 process_versions 唯一鍵衝突（500）

- **狀態**：**closed**（fix commit：見 `fix(worksheet): serialize version_no allocation per SKU with advisory lock`）
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

## 修法（已落地：方案 2 advisory lock）

`services/v2/process_version_service.py::next_version_no(session, sku_id)`：同交易
`SELECT pg_advisory_xact_lock(hashtext(sku_id))` → `COUNT(version_no)+1`；鎖到 commit 釋放，
與 insert 同交易。`clone_worksheet`、`catalog_service.create_worksheet` 兩處配號改走它。
測試 `tests/integration/test_process_version_concurrency.py`：兩獨立 session `asyncio.gather`
同時 clone → 皆 200、`{v2, v3}` 相異連續、DB 三版無重複。

## 對測試的處置（已修）

E2E 預設 `workers=1`（不動）；併發 `--workers=2` 現已不觸發（advisory lock 序列化配號）。
