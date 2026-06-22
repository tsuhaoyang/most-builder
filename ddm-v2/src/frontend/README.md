# DDM v2 Frontend (React + TypeScript)

模組化前端（取代 `docs/html_con/` 參考原型）。依 `frontend-workbench` skill 規範：**MVC 分離、邏輯後端權威、features 結構、typed API、Playwright e2e**。

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

## 遷移計畫（逐 tab）

藍本＝`docs/html_con/v2-workbench.html`（**保留為參考，不刪**）。已遷 WI（快速切片）；待遷：Level System(巢狀群組盒)、主數據、Rule-set、SOP、匯出、匯入、使用者。WI 的精確七格編輯亦待補。

## 部署

dev 用 Vite proxy；prod `npm run build` → dist/ 由靜態主機或 FastAPI static 提供（main.py 目前純 API）。`src/frontend` 已加入 `.dockerignore`（後端映像不含前端）。
