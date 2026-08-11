# DDM v2 Frontend (React + TypeScript)

模組化前端。依 v2 UX spec 與 ADR-021/022：**MVC 分離、邏輯後端權威、features 結構、typed API、Playwright e2e**。

## 技術棧

React 19 · TypeScript · Vite 6 · **TanStack Query**(伺服器狀態) · **Zustand**(編輯器本地狀態) · openapi-typescript(型別) · Playwright(e2e)。

## 結構

```
src/
├─ shared/
│  ├─ api/client.ts      唯一 API 入口（注入 dev 身分 header、統一錯誤）
│  ├─ auth/useMe.ts      身分 + RBAC gating（canEdit/canPublish/isAdmin）
│  ├─ ui/                可重用元件（Hint…；之後加 Combo/Tabs/Modal）
│  └─ types/api.d.ts     由後端 OpenAPI 產（npm run gen:api）
├─ features/<feature>/   每個 tab：api.ts(Query/mutation) + store.ts(Zustand Model) + <Feature>.tsx(View/Controller)
│  └─ wi-workbench/      ✅ 已遷移（垂直切片：快速編輯→計算→列表）
└─ App.tsx               分頁殼
```

**MVC**：Model = Zustand store + Query；View = components；Controller = hooks/handlers。**邏輯後端權威**：TMU/Level 一律打 `/api/v2`，前端不自算。

## 開發

```bash
# 1. 後端（提供 /api/v2，含 AUTH_DEV_USER）
cd ddm-v2 && PYTHONPATH=src DATABASE_URL=... python scripts/preview_server.py   # :8099

# 2. 前端 dev（Vite proxy /api → 8099）
cd ddm-v2/src/frontend
npm install
npm run dev            # http://localhost:5173
```

## 指令

- `npm run dev` — Vite dev server（proxy /api → 8099）
- `npm run build` — 產出 dist/
- `npm run typecheck` — tsc --noEmit
- `npm run gen:api` — 由 `openapi.json` 產 `src/shared/types/api.d.ts`
  （先 `cd ddm-v2 && PYTHONPATH=src python -c "import json;from ddm_v2.main import create_app;open('src/frontend/openapi.json','w').write(json.dumps(create_app().openapi()))"`）
- `npm run test:e2e` — Playwright（需 dev server + 後端在跑）

## 現行功能區

UX 權威＝`docs/architecture/frontend-ux-spec.md`＋ADR-021/022；`docs/html_con/` 僅封存。現行功能：

| 功能 | 實作位置 |
|------|----------|
| 儀表板 | `features/dashboard/` |
| MOST 工作台（動作→WI 大綱） | `features/workbench-v3/` |
| WI 專案建立 | `features/wi-project/` |
| Level System | `features/level-system/` |
| 分析案件＋工時表編輯＋匯出 | `features/cases/`、`features/wi-workbench/`、`features/export/` |
| 主數據／MOST 字典 | `features/dictionaries/`、`features/dictionary/` |
| 使用者與 RBAC | `features/users/` |
| Excel 匯入 | `features/import/` |

角色以後端 `/api/v2/me` 為準：`viewer < analyst < approver < admin`。TMU、Level 驗證與正式敘事一律使用後端權威結果。

## 部署

dev 用 Vite proxy；prod `npm run build` → dist/ 由靜態主機或 FastAPI static 提供（main.py 目前純 API）。`src/frontend` 已加入 `.dockerignore`（後端映像不含前端）。
