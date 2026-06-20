# DDM v2

工業工程 **MOST**（Maynard Operation Sequence Technique）工時量測平台，scope = **MiniMOST**。
純 v2 FastAPI 後端（API 前綴 `/api/v2`）＋ 單頁多分頁前端（`docs/html_con/`）＋ PostgreSQL。
（legacy Phase 1 程式碼已於 2026-06 移除。）

## 功能範圍

- **WI 工時表**：以「句子填空」描述 GM/CM cycle，由單一權威引擎算 TMU（1 TMU = 0.036 秒）。
- **Level System**：標註工序關係（main/sub/cub/nb、變動主序 `~`/`/`、巢狀 sub⊃cub）→ 供線平衡 (LB) 演算法用的完整約束模型。
- **動作範本庫**：常用 cycle 範本（標準/草稿治理）＋關鍵字比對（建表加速、匯入自動建 MOST 的地基）。
- **Rule-set 管理**：TMU 計算規則為版本化資料，單一引擎讀取（clone→改→發布）。
- **SOP 版本**：draft/published 凍結、另存新檔。
- **匯出**：工序單 Excel（含 Level 關係欄）／LB CSV／LB API 接口。
- **RBAC**：聯邦認證（Traefik ForwardAuth）＋本地角色 viewer < IE < manager < admin。

## 技術棧

FastAPI · SQLAlchemy 2.0 (async) · PostgreSQL · Alembic · Pydantic v2 · pytest。

## 先決條件

- Python **3.11+**（見 `pyproject.toml`）
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
PYTHONPATH=src .venv/bin/python scripts/preview_server.py      # 前端 → http://localhost:8099
```

或用 Docker：`docker compose up`（自動跑 migration + 種 admin app_users + 起 API on :8000）。

## 測試

```bash
PYTHONPATH=src pytest                 # 無 DB：unit 通過、integration 自動 skip
PYTHONPATH=src DATABASE_URL=... pytest # 有 DB：unit + integration 全跑
PYTHONPATH=src python scripts/core_logic/run_all.py  # 核心邏輯黃金/反例
```

## 文件

- 核心邏輯：`docs/specs/minimost-sequence-model-core-logic-spec.md`、`level-system-core-logic-spec.md`
- 架構：`docs/specs/system-architecture-v2-spec.md`、`data-model-and-storage-spec.md`、`rbac-spec.md`
- 文件索引：`docs/DOC_REGISTRY.md`
