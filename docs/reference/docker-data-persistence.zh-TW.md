# Docker：映像檔刪除與資料庫資料

## 重點結論

- **刪除 image（映像檔）** 不會刪掉 PostgreSQL 裡的資料。資料在 **named volume** 裡。
- **資料會不見** 通常是：刪了 **volume**、或執行 **`docker compose down -v`**、或 **`docker volume rm`**、或整顆磁碟被 prune 時勾到 volumes。

## 本專案 `docker-compose.yml` 的 volume

| Volume 名稱 | 用途 |
|-------------|------|
| `ddm-v2-pgdata` | **PostgreSQL 資料目錄**（表、列、使用者、廠區等） |

只要 **`ddm-v2-pgdata` 這個 volume 還在**，換新 image、重建 container，DB 資料都還在。

## 常見「我以為只刪 image」卻丟資料的情況

1. `docker compose down -v`：`-v` 會移除 compose 專案建立的 **volumes**（含 `ddm-v2-pgdata`）→ **DB 清空**。
2. `docker system prune --volumes`：會刪未使用 volume → 若當時沒有 container 掛載，可能被刪。
3. 在 Docker Desktop 手動刪 volume。
4. 換電腦 / 新環境沒有把舊 volume 匯入。

## 建議操作

- 日常重建後端：`docker compose build ddm-v2 && docker compose up -d`（**不要**加 `-v`）。
- 備份 DB：`docker exec ddm-v2-db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql`（實際帳密/DB 名以部署環境為準）。

## 與 IE 廠區下拉空白無關

IE 看不到廠區是因 **`user_sites` 未指派**，與刪 image 無關；請管理員在「使用者管理」勾選可存取廠區。
