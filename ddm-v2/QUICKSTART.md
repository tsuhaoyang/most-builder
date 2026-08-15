# DDM v2 Quick Start

讓新進的人最短時間把系統跑起來、知道從哪裡看、怎麼驗證。

## 1. 這是什麼

純 v2 的 MOST（MiniMOST）工時量測平台：FastAPI 後端（`/api/v2`）＋ **React 前端**（`src/frontend`，模組化、API 驅動）＋ PostgreSQL。
七大分頁：① WI 工時表 / ② Level System / ③ 主數據 / ④ Rule-set / ⑤ SOP 版本 / ⑥ 匯出 / ⑦ 使用者，＋「📥 匯入 Excel」精靈。

## 2. 本機啟動

```bash
cd ddm-v2

# 2.1 虛擬環境 + 安裝（一律從鎖檔裝，見 ADR-029）
#     不要用 `pip install -e ".[dev]"`：那會解析到當下最新版，裝出與 CI／Docker 不同的一組依賴。
#     Python 用 3.11，對齊 CI 與 Dockerfile 的 python:3.11-slim。
python3.11 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements-build.lock
.venv/bin/pip install --require-hashes --no-build-isolation -r requirements-dev.lock
.venv/bin/pip install --no-deps --no-build-isolation -e .

# 2.2 PostgreSQL（任選）
#   A) 自己的 PG：建好 DB，設 DATABASE_URL
#   B) 用 compose 只起 DB（需主機存取 → 疊 dev override 才會發佈 port）：
#      docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
#      （主機 5432 被佔用時：POSTGRES_HOST_PORT=15432 ... 並改下面 URL 的 port）
#      帳密以 compose 的 db 服務為準：docker compose exec db sh -c 'echo $POSTGRES_USER/$POSTGRES_DB'
export DATABASE_URL="postgresql+asyncpg://USER:PASS@localhost:5432/ddm_v2_most"

# 2.3 遷移 + 種子
PYTHONPATH=src .venv/bin/alembic upgrade head
PYTHONPATH=src .venv/bin/python scripts/dev_seed_v2.py         # 階層 + worksheet + admin(IEC141289)
PYTHONPATH=src .venv/bin/python scripts/dev_seed_templates.py   # 動作範本庫
PYTHONPATH=src .venv/bin/python scripts/dev_seed_30rows.py      # （可選）30 筆示範工序

# 2.4 建置前端（一次）
( cd src/frontend && npm install && npm run build )

# 2.5 跑單一伺服器（前端 + API 同源）
PYTHONPATH=src .venv/bin/python scripts/preview_server.py       # http://localhost:8099
```

**前端熱重載開發**（改 UI 時用）：保持 preview_server 在跑當 API 後端，另開一個終端
`cd src/frontend && npm run dev` → http://localhost:5173（Vite proxy `/api` → :8099）。

純 API（不含前端）：`PYTHONPATH=src .venv/bin/uvicorn ddm_v2.main:app --app-dir src` → `/docs`。

## 3. Docker 一鍵

```bash
docker compose up -d --build   # 起 db + app；entrypoint 自動 alembic upgrade + 種 admin app_users
```

- API/前端在 `:8877`（預設；用 `DDM_PORT` 可改成其他空閒 port）。
- **DB 預設不對外發佈**：app 走容器內部網路（service name `db`），所以**不會跟主機既有的 Postgres（5432）衝突**。要主機 psql/alembic 才疊 `docker-compose.dev.yml`。
- bootstrap admin 員工編號＝`DDM_ADMIN_EMPLOYEE_NO`（設成你真實員編）。
- 容器名固定為 `ddm-v2` / `ddm-v2-db`；若同主機要跑多套，請設 `COMPOSE_PROJECT_NAME` 避免撞名。

## 4. 身分（RBAC）

正式環境身分由閘道（Traefik ForwardAuth）注入 `X-Username`（員工編號）。
本機開發可用 `AUTH_DEV_USER=IEC141289`（preview_server 已預設）。角色：viewer < IE < manager < admin。

## 5. 驗證

```bash
# 後端
PYTHONPATH=src pytest                                  # unit（免 DB）+ integration（需 DATABASE_URL，否則 skip）
PYTHONPATH=src python scripts/core_logic/run_all.py    # 核心邏輯黃金/反例（GM=28 / CM=29 等）

# 前端（型別/建置/瀏覽器 e2e）
cd src/frontend && npm run typecheck && npm run build
E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test  # 需 preview_server(:8099) 在跑
```

## 6. 從哪裡看

- 前端：`src/frontend/`（`features/<tab>/` 各分頁；`shared/` 共用；UX 見 `docs/architecture/frontend-ux-spec.md`）
- 後端 API：`src/ddm_v2/api/routes/v2/`、引擎 `src/ddm_v2/most_engine/`
- 規格：`docs/core-logic/`、`docs/architecture/`；索引 `docs/DOC_REGISTRY.md`
