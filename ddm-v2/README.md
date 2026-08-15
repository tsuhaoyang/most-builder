# DDM v2

工業工程 **MOST**（Maynard Operation Sequence Technique）工時量測平台，scope = **MiniMOST**。
純 v2 FastAPI 後端（API 前綴 `/api/v2`）＋ **React 前端**（`src/frontend`，模組化、API 驅動）＋ PostgreSQL。
（legacy Phase 1 程式碼已於 2026-06 移除；`docs/html_con/` 僅為封存原型，不作 UI 權威。）

## 功能範圍

- **WI 工時表**：以「句子填空」描述 GM/CM cycle，由單一權威引擎算 TMU（1 TMU = 0.036 秒）。
- **Level System**：標註工序關係（main/sub/cub/nb、變動主序 `~`/`/`、巢狀 sub⊃cub）→ 供線平衡 (LB) 演算法用的完整約束模型。
- **動作範本庫**：常用 cycle 範本（標準/草稿治理）＋關鍵字比對（建表加速、匯入自動建 MOST 的地基）。
- **Rule-set 管理**：TMU 計算規則為版本化資料，單一引擎讀取（clone→改→發布）。
- **SOP 版本**：draft/published 凍結、另存新檔。
- **匯出**：工序單 Excel（含 Level 關係欄）／LB CSV／LB API 接口。
- **RBAC**：聯邦認證（Traefik ForwardAuth）＋本地角色 viewer < IE < manager < admin。

## 技術棧

**後端**：FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Alembic · Pydantic v2 · pytest。
**前端**：React 19 · TypeScript · Vite 6 · TanStack Query · Zustand · Playwright（e2e）。詳見 [src/frontend/README.md](src/frontend/README.md)。

## 先決條件

- Python **3.11**（對齊 CI 與 Dockerfile 的 `python:3.11-slim`；`pyproject.toml` 的下界是 3.11）
- Node **20+**（前端建置）
- PostgreSQL（本機或 `docker compose up db`）

## 快速開始

見 [QUICKSTART.md](QUICKSTART.md)。最短路徑：

```bash
cd ddm-v2
# 一律從鎖檔裝（ADR-029）；`pip install -e ".[dev]"` 會解析到當下最新版，裝出與 CI／Docker 不同的依賴
python3.11 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-build.lock
.venv/bin/pip install --require-hashes --no-build-isolation -r requirements-dev.lock
.venv/bin/pip install --no-deps --no-build-isolation -e .
export DATABASE_URL="postgresql+asyncpg://USER:PASS@localhost:5432/ddm_v2_most"
PYTHONPATH=src .venv/bin/alembic upgrade head
PYTHONPATH=src .venv/bin/python scripts/dev_seed_v2.py        # site/product/sku/worksheet + admin
PYTHONPATH=src .venv/bin/python scripts/dev_seed_templates.py  # 動作範本庫

# 建置前端（一次），再起單一伺服器（前端 + API 同源）
( cd src/frontend && npm install && npm run build )
PYTHONPATH=src .venv/bin/python scripts/preview_server.py      # http://localhost:8099
```

前端開發（熱重載）改用：`cd src/frontend && npm run dev`（:5173，proxy `/api` → :8099）。
或用 Docker（建議）：`make up`（等同啟動 db + app；容器內會自動 migration）。

## Make 指令入口（建議）

本專案已提供 [Makefile](Makefile)；日常操作建議一律走 `make`，避免誤下危險 docker 指令。

```bash
cd ddm-v2
make help
```

常用：

- `make up`：啟動 db + app（保留資料）
- `make rebuild-app`：重建 app image 並啟動
- `make down`：移除 containers（保留 volume）
- `make logs`：追蹤 app + db logs
- `make db-backup`：備份 DB 到 `data/backups/`
- `make db-restore BACKUP=... CONFIRM=YES`：還原 SQL dump
- `make db-reset CONFIRM=YES`：清空 schema（危險）
- `make destroy-safe CONFIRM=YES`：先自動備份，再 `down -v`（會刪 DB volume，極危險）
- `make destroy CONFIRM=YES`：同 `destroy-safe`（保留相容別名）

進階：

- 正式環境若不要 dev overlay，可改：
	`COMPOSE_FILES='-f docker-compose.yml' make up`
- 破壞性指令在非 dev overlay 會被阻擋；必要時可加：
	`ALLOW_PROD_DESTRUCTIVE=YES make destroy-safe CONFIRM=YES`

## Docker 重啟與資料保留

### 先看結論

- 只刪除 container（或重新 build image），**資料通常會保留**。
- 只有刪到 Docker volume，資料庫才會清空。
- 是否需要重新匯入 v3 資料，取決於 volume 是否還在。
- 容器啟動時會自動跑 migration；若 `DDM_SEED_DEMO=true` 也會自動跑 demo seed（idempotent）。

### 為什麼資料會保留

`docker-compose.yml` 的 db 服務把 PostgreSQL 資料目錄掛在 named volume `ddm-v2-pgdata`。
只要這個 volume 還在，重建 container 後資料會自動回來。

### 什麼操作會清掉 DB

- `make destroy-safe CONFIRM=YES`（會先自動備份，再 `docker compose down -v`）
- `docker volume rm ddm-v2-pgdata`
- `docker system prune --volumes`（可能清到未使用 volume）

### 什麼時候需要再做 v3 匯入

- **不用重匯入**：volume 還在，只是重建 container / image。
- **要重匯入**：volume 被刪除、資料庫是全新空庫。

v3 匯入腳本：`scripts/migrate_v3_user_data.py`

### 建議重啟指令（Make）

保留資料、重啟服務：`make up`

保留資料、重建 app image：`make rebuild-app`

全清空重建（資料會消失）：`make destroy-safe CONFIRM=YES && make up`

### 常見陷阱

- 單跑 `docker compose -f docker-compose.yml up -d` 時，DB 不會對 host 發佈 port。
- 若你需要從主機 `psql` / `alembic` 連 DB，請疊加 `docker-compose.dev.yml`。
- 若主機 5432 被占用，可改 `POSTGRES_HOST_PORT`（見 `docker-compose.dev.yml`）。

## 測試

```bash
PYTHONPATH=src pytest                 # 無 DB：unit 通過、integration 自動 skip
PYTHONPATH=src DATABASE_URL=... pytest # 有 DB：unit + integration 全跑
PYTHONPATH=src python scripts/core_logic/run_all.py  # 核心邏輯黃金/反例

# 前端
( cd src/frontend && npm run typecheck && npm run build )      # 型別 + 建置
E2E_BASE_URL=http://127.0.0.1:8099 ( cd src/frontend && npx playwright test )  # e2e（需 preview_server 在跑）
```

## 文件

- 核心邏輯：`docs/core-logic/`（MiniMOST sequence / Level System / 驗證目錄）
- 架構：`docs/architecture/`（系統、資料、前端 UX/資料流、RBAC、WI AI）
- 前端：[src/frontend/README.md](src/frontend/README.md)（模組化結構、遷移狀態、開發/e2e 指令）
- 文件索引：`docs/DOC_REGISTRY.md`
