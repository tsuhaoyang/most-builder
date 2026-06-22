# DDM v2

工業工程 **MOST**（Maynard Operation Sequence Technique）工時量測平台，scope = **MiniMOST**。
純 v2 FastAPI 後端（API 前綴 `/api/v2`）＋ **React 前端**（`src/frontend`，模組化、API 驅動）＋ PostgreSQL。
（legacy Phase 1 程式碼已於 2026-06 移除；舊 `docs/html_con/` 僅留作 UI 藍本參考。）

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

- Python **3.11+**（見 `pyproject.toml`）
- Node **20+**（前端建置）
- PostgreSQL（本機或 `docker compose up db`）

## 快速開始

見 [QUICKSTART.md](QUICKSTART.md)。最短路徑：

```bash
cd ddm-v2
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export DATABASE_URL="postgresql+asyncpg://USER:PASS@localhost:5432/ddm_v2"
PYTHONPATH=src .venv/bin/alembic upgrade head
PYTHONPATH=src .venv/bin/python scripts/dev_seed_v2.py        # site/product/sku/worksheet + admin
PYTHONPATH=src .venv/bin/python scripts/dev_seed_templates.py  # 動作範本庫

# 建置前端（一次），再起單一伺服器（前端 + API 同源）
( cd src/frontend && npm install && npm run build )
PYTHONPATH=src .venv/bin/python scripts/preview_server.py      # http://localhost:8099
```

前端開發（熱重載）改用：`cd src/frontend && npm run dev`（:5173，proxy `/api` → :8099）。
或用 Docker：`docker compose up`（自動跑 migration + 種 admin app_users + 起 API on :8000）。

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

- 核心邏輯：`docs/core-logic/`（minimost-sequence / level-system / 驗證目錄 / MOST 核心算法）
- 架構：`docs/architecture/`（system-architecture-v2 / data-model-and-storage / frontend-data-flow / rbac）
- 前端：[src/frontend/README.md](src/frontend/README.md)（模組化結構、遷移狀態、開發/e2e 指令）
- 文件索引：`docs/DOC_REGISTRY.md`
