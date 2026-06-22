"""v2 前端設計預覽伺服器（最小）：只掛 v2 引擎 router + 提供預覽頁。

不依賴 legacy app / DB（v2 calculate 用 seed rule-set）。同源，免 CORS。
跑：  PYTHONPATH=src python scripts/preview_server.py
開：  http://localhost:8099/
"""
from __future__ import annotations

from pathlib import Path

import os
os.environ.setdefault('AUTH_DEV_USER','IEC141289')  # 本地預覽預設以 admin 身分（dev override）
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

from ddm_v2.api.routes.v2.calculate import router as v2_router
from ddm_v2.api.routes.v2.export import router as v2_export_router
from ddm_v2.api.routes.v2.import_excel import router as v2_import_router
from ddm_v2.api.routes.v2.rule_set import router as v2_ruleset_router
from ddm_v2.api.routes.v2.admin_users import router as v2_admin_router
from ddm_v2.api.routes.v2.motion_template import router as v2_motion_template_router
from ddm_v2.api.routes.v2.vocab import router as v2_vocab_router
from ddm_v2.api.routes.v2.worksheet import router as v2_worksheet_router

HTML_DIR = Path(__file__).resolve().parent.parent / "docs" / "html_con"

app = FastAPI(title="v2 MOST Workbench 預覽")
app.include_router(v2_router)
app.include_router(v2_worksheet_router)
app.include_router(v2_vocab_router)
app.include_router(v2_motion_template_router)
app.include_router(v2_export_router)
app.include_router(v2_import_router)
app.include_router(v2_ruleset_router)
app.include_router(v2_admin_router)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(HTML_DIR / "v2-workbench.html")  # 多分頁 workbench


@app.get("/single")
def single() -> FileResponse:
    return FileResponse(HTML_DIR / "v2-wi-preview.html")  # 單列句子填空（聚焦版）


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8099, log_level="info")
