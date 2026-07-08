# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 品質關卡（不可跳過）

- 每完成一個功能段落或準備 commit 前，必須執行 /dev-team:checkpoint。
- 主對話不得自行完成 code review 或資安檢查——必須委派對應席位。
- 重大架構決策必須有 ADR 紀錄（本 repo 的 ADR 在 `ddm-v2/docs/decisions/`），沒有就先跑對應的 /arch-decisions skill。

## 跨專案整合

本專案與 LineBalance（`/home/howard/workspace/line-balance_stream-weaver_v2`，Stream Weaver）強關聯：MOST 匯出 → LB 匯入（MOST 是工時標準來源，LB 是消費方做產線平衡）、auth 整合（本 repo 的 `LB/` 即共享登入基礎設施）、部署拓撲。跨兩專案的決策用 unified-arch agent 協調；共享契約以單一文件為準，不要兩邊各寫一份。

**處理 line-balance 檔案前，必須先讀它的 CLAUDE.md**（`/home/howard/workspace/line-balance_stream-weaver_v2/CLAUDE.md`）——它的測試環境、時間單位契約（內部 `_ms` vs API 秒）與 commit 規範都定義在那裡。

## Repository Structure

Monorepo with four top-level directories:

- **`ddm-v2/`** — Active development. MiniMOST work-measurement platform (FastAPI + React). All new work goes here.
- **`ddm-v3/`** — Reference only. Source of `minimost_ai_dictionary_v1.json` (IE-certified value authority per ADR-014). Do not develop here.
- **`ddm-legacy/`** — Archived Phase 1 code (single HTML + Python). Do not modify.
- **`LB/`** — LineBalance auth service + Traefik config (shared login infrastructure).

All commands below assume `cd ddm-v2` first.

## Commands

### Backend

```bash
# Setup (one-time)
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# DB migration + seed
export DATABASE_URL="postgresql+asyncpg://USER:PASS@localhost:5432/ddm_v2"
PYTHONPATH=src .venv/bin/alembic upgrade head
PYTHONPATH=src .venv/bin/python scripts/dev_seed_v2.py         # hierarchy + worksheet + admin
PYTHONPATH=src .venv/bin/python scripts/dev_seed_templates.py  # motion template library
PYTHONPATH=src .venv/bin/python scripts/dev_seed_30rows.py     # (optional) 30 sample rows

# Run (single server, frontend + API same origin)
PYTHONPATH=src .venv/bin/python scripts/preview_server.py      # http://localhost:8099

# Tests
PYTHONPATH=src pytest                          # unit only (no DB needed)
PYTHONPATH=src DATABASE_URL=... pytest         # unit + integration
PYTHONPATH=src pytest tests/unit/test_most_engine.py::test_name  # single test
PYTHONPATH=src python scripts/core_logic/run_all.py             # golden-value validation

# Lint / type check
ruff check src/
mypy src/
```

### Frontend (`cd src/frontend`)

```bash
npm install
npm run dev        # hot-reload dev server :5173 (Vite proxy /api → :8099; keep preview_server running)
npm run build      # build to dist/
npm run typecheck  # tsc --noEmit
npm run gen:api    # regenerate src/shared/types/api.d.ts from OpenAPI (run after changing API schemas)
E2E_BASE_URL=http://127.0.0.1:8099 npx playwright test   # e2e (needs preview_server running)
```

### Docker

```bash
docker compose up -d --build  # starts db + app on :8877; entrypoint auto-runs alembic + seeds admin
# To expose DB to host (for psql/alembic locally):
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

## Architecture

### Backend (hexagonal: routes → services → repositories)

```
src/ddm_v2/
├── main.py              FastAPI app factory; mounts routers; exception→HTTP mapping
├── api/routes/v2/       One file per feature group (calculate, worksheet, catalog, export, …)
├── most_engine/         ★ THE ONLY CALCULATION ENGINE
│   ├── calculate.py     compute_cycle() / compute_table() — GM/CM TMU logic
│   ├── level.py         Level System R1–R9 validator + LB output contract builder
│   ├── narrative.py     METHOD sentence generation
│   ├── rule_set_data.py RuleSetData value object (no DB, no framework)
│   └── providers.py     Adapters: build_from_seed() (tests) / load_rule_set_from_db() (runtime)
├── services/v2/         Business logic (worksheet_service, export_service, catalog_service, …)
├── models/v2/           SQLAlchemy 2.0 async ORM models
├── schemas/v2/          Pydantic v2 request/response schemas
├── auth/                Identity resolution (gateway header / verify-mode session cookie)
└── database.py          Async engine + session factory
```

**Critical design invariant**: `most_engine/` is the single authority for all TMU calculation and level validation. The frontend never calculates — every TMU value comes from `POST /api/v2/minimost/calculate`. Rule-set tables in the DB are the value source; the engine reads them at runtime.

### Data Hierarchy

```
Site → Product → SKU → ProcessVersion → MostWorksheet → WiRow
                                                       ├── MostCycle (slot_inputs JSONB, total_tmu)
                                                       └── LevelEntry (main/sub/cub/nb relationships)
```

### Frontend (`src/frontend/src/`)

```
shared/
├── api/client.ts      Single API entry point (injects AUTH_DEV_USER header in dev, unified errors)
├── auth/useMe.ts      Identity + RBAC gating (canEdit / canPublish / isAdmin)
├── workspace.ts       Zustand: activeWs shared across WI / Export / SOP tabs
└── types/api.d.ts     Generated from backend OpenAPI (do not hand-edit)

features/<tab>/        Vertical slices: api.ts (TanStack Query) + store.ts (Zustand) + <Tab>.tsx
```

Nine feature tabs: `wi-workbench`, `level-system`, `catalog`, `master-data`, `rule-set`, `sop`, `export`, `import`, `users`.

`docs/html_con/v2-workbench.html` — UI reference prototype; keep but do not modify.

### Auth / RBAC

- Production: Traefik ForwardAuth injects `X-Username` (employee number). Role hierarchy: `viewer < IE < manager < admin`.
- Local dev: `AUTH_DEV_USER=IEC141289` (preview_server sets this automatically).
- Two auth modes switchable via `DDM_AUTH_MODE`: `gateway` (default, header-based) and `verify` (session-cookie bridge to LB).

## CI Gates (must pass before merging)

1. **Runtime deps**: Every `import` in `src/` must be declared in `pyproject.toml` `[dependencies]` (not just `[dev]`).
2. **Integration test coverage**: Every feature endpoint group needs at minimum one integration test covering happy path + one boundary/RBAC case.
3. **Golden values**: Any change touching `most_engine/`, rule-set seeds, level rules, or `schemas/v2/most.py` must pass `scripts/core_logic/run_all.py`. Anchors: **GM=28** (A6 B0 G6 A10 B0 P6 A0) and **CM=29** (A10 B0 G3 M16 X0 I0 A0 @ 45cm push).
4. **Value authority (ADR-014)**: The active rule-set is `MINIMOST_FACTORY_V2`. `src/ddm_v2/seed/v2/rule_set_seed_v2.py` is a **generated file** — never hand-edit it. To change values: edit `ddm-v2/docs/v3/reference/minimost_ai_dictionary_v1.json`, then re-run `scripts/import_v3_dictionary.py`.
5. **V1 replay isolation**: `MINIMOST_FACTORY_V1` snapshot tests must stay green (stored worksheet TMU must not change).
6. **Frontend**: `npm run typecheck && npm run build` + Playwright smoke must pass.

## Hard Rules (from `.cursor/rules/`)

- **No error bypass**: Never silence errors with bare `except: pass`, coerce types to avoid exceptions, or set fake defaults to pass validation. Find and fix the root cause.
- **DB changes are bilateral**: When fixing an Alembic/PostgreSQL error, always check both the SQLAlchemy model (`src/ddm_v2/models/`) **and** the migration (`migrations/versions_v2/`). Never fix only one side.
- **Agent delegation**: The main Claude instance coordinates and commits. Implementation and validation are delegated to specialized agents (`ddm-backend`, `ddm-frontend`, `ddm-validator`, `ddm-testing`). The coordinator does not write feature code directly.

## Key Docs

| What | Where |
|---|---|
| Sequence model spec (MiniMOST GM/CM rules) | `docs/core-logic/minimost-sequence-model-core-logic-spec.md` |
| Level System spec (R1–R9 filling rules) | `docs/core-logic/level-system-core-logic-spec.md` |
| Golden-value test catalog | `docs/core-logic/core-logic-validation-test-catalog.md` |
| System architecture | `docs/architecture/system-architecture-v2-spec.md` |
| Data model + storage | `docs/architecture/data-model-and-storage-spec.md` |
| RBAC spec | `docs/architecture/rbac-spec.md` |
| CI verification gates | `docs/CI_GATES.md` |
| v2↔v3 integration analysis + ADR-014 ruling | `docs/v3/v2-v3-core-logic-diff-and-integration.md` |
| All docs index | `docs/DOC_REGISTRY.md` |
| All ADRs | `docs/decisions/` |
