# v3 使用者資料來源與搬遷紀錄

**狀態：** 受保護資料來源
**更新日期：** 2026-08-04
**來源用途：** 已建立的 WI／MI statements、動作、WI templates 與 WI Set 專案

## 1. 兩份 v3 資料不可混淆

| 資料 | 路徑 | 用途 |
|------|------|------|
| v3 使用者 SQLite | `../../ddm-v3/apps/api/minimost.db` | 已建立 WI/WI 大綱/actions/templates/WI Set；由 `scripts/migrate_v3_user_data.py` 唯讀搬遷 |
| IE 認證字典 JSON | `../v3/reference/minimost_ai_dictionary_v1.json` | MiniMOST A～I 值權威；由 `scripts/import_v3_dictionary.py` 產生 V2 seed |

SQLite 是 gitignored 的外部資料，JSON 是版本控制內的值權威。兩者都禁止刪除或互相替代。

## 2. SQLite 保護規則

- 禁止刪除、clean、truncate 或覆寫 `ddm-v3/apps/api/minimost.db`。
- 搬遷腳本必須使用 SQLite URI `mode=ro`。
- 搬遷前先跑 dry-run 與 TMU 對帳；`FAIL=0`、`DIFF=0` 才可 `--execute`。
- 寫入 v2 前先建立 PostgreSQL `pg_dump`。
- 原始 SQLite 在搬遷後仍保留，不以 v2 PostgreSQL 取代。

## 3. 來源資料盤點

2026-08-04 integrity check：`ok`。

| v3 table | 筆數 |
|----------|------|
| `most_mi_statements` | 13 |
| `most_mi_statement_items` | 29 |
| `most_sequence_items` | 29 |
| `action_module_templates` | 3（搬遷時去重為 2） |
| `wi_templates` | 2 |
| `wi_template_items` | 5 |
| `wi_set_projects` | 1 |
| `wi_set_project_items` | 13 |

Workspace SQLite：

```text
path: ddm-v3/apps/api/minimost.db
size: 667648 bytes
sha256: 547864e1c26dd28ab1adc3f0c7c4737fed43f488d51ac2548e91e829e4b26cf4
```

獨立備份來源：

```text
/mnt/c/Users/IEC141289/OneDrive - Inventec Corp/文件/mini_most/
  minimost_from_Avery/minimost/apps/api/minimost.db
```

2026-08-04 比對時兩份 SHA-256 相同。

## 4. v2 搬遷結果

目標：目前 Docker PostgreSQL `ddm-v2-db` 的 `$POSTGRES_DB`。

Dry-run：

- v3 盤點：13 MI statements、29 items、29 actions、2 去重 action modules、2 WI templates、1 WI Set。
- 列級對帳：`65/65 OK`。
- `DIFF=0`、`FAIL=0`。
- WI Set：13 items，v3/v2 total 都為約 `3739.67 TMU`。

正式執行後 PostgreSQL：

| v2 資料 | 筆數 |
|---------|------|
| `motion_modules category='action'` | 29 |
| `motion_modules category='wi-template'` | 15（13 WI 大綱 + 2 WI templates） |
| current versions with rows/computed | 44 / 44 |
| `wi_set_projects` | 1 |
| WI Set items | 13 |
| WI Set TMU（DB 精度） | 3739.666 |

重跑 `--execute` 的結果：建立模組 0、跳過 44；建立專案 0、跳過 1，確認冪等。

## 5. v2 API 驗證

以 admin 身分直連 API（localhost 必須繞過企業 HTTP proxy）：

- `/api/v2/motion-modules?category=action` → 29。
- `/api/v2/motion-modules?category=wi-template` → 15。
- `/api/v2/wi-set-projects` → 1，items=13。

## 6. 備份與恢復

搬遷前 v2 PostgreSQL 備份位於 gitignored `ddm-v2/data/backups/`：

```text
pre_v3_user_migration_20260804_201205.sql
sha256: 0f1993bc48542f5e70405a3df91fd6c0edbdaca3a6d8e161b3bf2bcadf6bd746
```

若 workspace SQLite 遺失，先由 OneDrive 備份複製回原路徑，驗證 SHA-256 與 `PRAGMA integrity_check`，不可用空 DB 取代。
