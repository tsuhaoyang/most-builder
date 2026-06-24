"""v2 本機預覽伺服器：掛全部 v2 API router + 提供已建置的 React 前端（同源、免 CORS）。

兩種前端開發/預覽方式：
  A) 單一伺服器（推薦預覽）：先 `cd src/frontend && npm install && npm run build`，
     再 `PYTHONPATH=src python scripts/preview_server.py` → http://localhost:8099 （前端 + API 同源）。
  B) 前端熱重載開發：本檔當 API 後端(:8099)，另開 `cd src/frontend && npm run dev`
     （Vite :5173，proxy /api → :8099）。

需 PostgreSQL：設 DATABASE_URL（worksheet/vocab/版本/使用者等需 DB；純計算不需）。
本地預設以 admin 身分（AUTH_DEV_USER=IEC141289）。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("AUTH_DEV_USER", "IEC141289")  # 本地預覽預設以 admin 身分（dev override）

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.calculate import router as v2_router  # 含 /api/v2/me
from ddm_v2.api.routes.v2.catalog import router as v2_catalog_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router

DIST = Path(__file__).resolve().parent.parent / "src" / "frontend" / "dist"

app = FastAPI(title="v2 MOST Workbench 預覽")

# 全部 v2 router（須與 main.py 一致）
app.include_router(v2_router)
app.include_router(v2_worksheet_router)
app.include_router(v2_vocab_router)
app.include_router(v2_motion_template_router)
app.include_router(v2_export_router)
app.include_router(v2_import_router)
app.include_router(v2_ruleset_router)
app.include_router(v2_admin_router)
app.include_router(v2_catalog_router)

# 已建置的前端靜態資源（Vite 產物在 dist/assets）
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/", response_model=None)
def index():
    idx = DIST / "index.html"
    if idx.exists():
        return FileResponse(idx)
    return HTMLResponse(
        "<h1>前端尚未建置</h1>"
        "<p>請先 <code>cd src/frontend &amp;&amp; npm install &amp;&amp; npm run build</code>，"
        "或改用熱重載開發：<code>npm run dev</code>（:5173，proxy /api → :8099）。</p>",
        status_code=503,
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099, log_level="info")
