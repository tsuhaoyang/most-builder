"""v2 本機預覽伺服器：掛全部 v2 API router + 提供已建置的 React 前端（同源、免 CORS）。

兩種前端開發/預覽方式：
  A) 單一伺服器（推薦預覽）：先 `cd src/frontend && npm install && npm run build`，
     再 `PYTHONPATH=src python scripts/preview_server.py` → http://localhost:8099 （前端 + API 同源）。
  B) 前端熱重載開發：本檔當 API 後端(:8099)，另開 `cd src/frontend && npm run dev`
     （Vite :5173，proxy /api → :8099）。

需 PostgreSQL：設 DATABASE_URL（worksheet/vocab/版本/使用者等需 DB；純計算不需）。

⚠️ **預設只綁 loopback（127.0.0.1），因為本服務以 admin 身分免認證運作**：
`AUTH_DEV_USER=IEC141289` 會讓 `auth/identity.py` 把**每一個**請求都當成該員編，
連 `X-Username` header 都不必偽造——綁 0.0.0.0 等同把零憑證 admin 開給整個網段。
確實需要對外（例如給同事看 demo）才顯式設 `DDM_PREVIEW_HOST=0.0.0.0`，並自行承擔。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("AUTH_DEV_USER", "IEC141289")  # 本地預覽預設以 admin 身分（dev override）

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.audit_log import router as v2_audit_log_router
from ddm_v2.api.routes.v2.calculate import router as v2_router  # 含 /api/v2/me
from ddm_v2.api.routes.v2.cases import router as v2_cases_router
from ddm_v2.api.routes.v2.catalog import router as v2_catalog_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.motion_module import router as v2_motion_module_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.nl_draft import router as v2_nl_draft_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.search import router as v2_search_router
from ddm_v2.api.routes.v2.synonyms import router as v2_synonyms_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.wi_set import router as v2_wi_set_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router
from ddm_v2.auth.startup_checks import warn_if_identity_config_insecure

DIST = Path(__file__).resolve().parent.parent / "src" / "frontend" / "dist"

# 本檔刻意不走 `create_app()`（見上方 B 模式），所以啟動期安全告警必須自己叫一次。
# 不要把它搬進 `if __name__ == "__main__"`：以 `uvicorn scripts.preview_server:app` 之類
# 方式載入本模組時同樣要看得到警告。
# basicConfig 先於它：uvicorn 要到 run() 才設定 logging，沒有 handler 的話這兩筆警告
# 只會走 lastResort、看起來像雜訊。
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
warn_if_identity_config_insecure()

app = FastAPI(title="v2 MOST Workbench 預覽")

# 全部 v2 router（須與 main.py 一致）
app.include_router(v2_router)
app.include_router(v2_worksheet_router)
app.include_router(v2_vocab_router)
app.include_router(v2_motion_template_router)
app.include_router(v2_motion_module_router)
app.include_router(v2_export_router)
app.include_router(v2_import_router)
app.include_router(v2_ruleset_router)
app.include_router(v2_admin_router)
app.include_router(v2_catalog_router)
app.include_router(v2_search_router)
app.include_router(v2_synonyms_router)
app.include_router(v2_nl_draft_router)
app.include_router(v2_audit_log_router)
app.include_router(v2_cases_router)
app.include_router(v2_wi_set_router)

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


PREVIEW_HOST_ENV = "DDM_PREVIEW_HOST"
PREVIEW_PORT_ENV = "DDM_PREVIEW_PORT"


def resolve_bind_host() -> str:
    """綁定位址：**預設 loopback**，要對外必須顯式設 `DDM_PREVIEW_HOST`（D7b · C-1）。

    原本寫死 `0.0.0.0`：compose 剛關掉的那扇門在這裡是開的，而本檔又以 admin 身分
    免認證運作（見模組 docstring）。不寫死 loopback 是因為「同事要連進來看 demo」
    是真實需求——但那必須是一個顯式的、留得下痕跡的決定。
    """
    return os.getenv(PREVIEW_HOST_ENV, "127.0.0.1").strip() or "127.0.0.1"


def resolve_bind_port() -> int:
    return int(os.getenv(PREVIEW_PORT_ENV, "8099"))


if __name__ == "__main__":
    uvicorn.run(app, host=resolve_bind_host(), port=resolve_bind_port(), log_level="info")
