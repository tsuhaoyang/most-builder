"""LB 座標格式驗證（安全修正）：三個座標直接成為 LB URL 的路徑段，必須擋住路徑改寫。

`lb_project_id="x/../../../admin/users?"` 原本會讓 MOST 帶著身分 header 對 LB 主機的
`/api/admin/users` 發 GET。修正：路由層 `FetchIn` 以 `LB_ID_PATTERN` 回 422；`lb_client.fetch_writeback`
再以同一規則擋一次（縱深防線），不合格就不發任何請求。
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from pydantic import ValidationError

from ddm_v2.api.routes.v2.lb_writeback import FetchIn
from ddm_v2.services.v2.lb_client import fetch_writeback

VALID_IDS = [
    "ba0dba3c1b6a4674a330ba56cda38cc7",          # LB project id（32 位 hex）
    "cb43da21-98fd-4fad-a799-148eea42b778",      # UUID
    "original",
    "v_1a2b3c",
    "demo-result",
    "a" * 64,                                    # 上限
]

BAD_IDS = [
    "x/../../../admin/users?",                   # 實測可改寫路徑的 payload
    "../admin",
    "..",
    ".",
    "a/b",
    "a\\b",
    "a%2Fb",                                     # 預先編碼的斜線
    "a?b=1",
    "a#frag",
    "a b",
    " a",
    "a\tb",
    "abc\n",                                     # 結尾換行（Python re 的 `$` 會放過）
    "a\x00b",
    "a\x7fb",
    "ａｂｃ",                                     # 全形
    "\u212a",                                   # Kelvin 符號 K（同形字）
    "a\u200bb",                                 # 零寬空白
    "",
    "a" * 65,                                    # 超長
]

FIELDS = ["lb_project_id", "lb_version_id", "lb_result_id"]


def _body(**override: str) -> dict:
    return {"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R", **override}


@pytest.mark.parametrize("value", VALID_IDS)
def test_fetchin_accepts_lb_id_formats(value):
    for f in FIELDS:
        assert getattr(FetchIn(**_body(**{f: value})), f) == value


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", BAD_IDS)
def test_fetchin_rejects_unsafe_ids(field, value):
    with pytest.raises(ValidationError):
        FetchIn(**_body(**{field: value}))


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [123, 1.5, ["a"], {"a": 1}, None, True])
def test_fetchin_rejects_non_string_json(field, value):
    """JSON 送非字串不得被強制轉型成字串後放行。"""
    import json
    with pytest.raises(ValidationError):
        FetchIn.model_validate_json(json.dumps(_body(**{field: value})))


def _recording_server():
    hits: list[str] = []

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, hits


@pytest.mark.parametrize("field", ["project_id", "version_id", "result_id"])
@pytest.mark.parametrize("value", ["x/../../../admin/users?", "a/b", "..", "abc\n", "a" * 65, ""])
async def test_client_refuses_unsafe_ids_without_request(field, value):
    """縱深防線：就算呼叫端漏驗，client 也不發請求。"""
    server, hits = _recording_server()
    try:
        ids = {"project_id": "P", "version_id": "V", "result_id": "R", field: value}
        with pytest.raises(ValueError, match=field):
            await fetch_writeback(base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout_s=2.0, **ids)
        assert hits == []
    finally:
        server.shutdown()


async def test_client_valid_ids_still_reach_lb():
    """對照組：合法座標照常送出，路徑就是預期的 writeback 路徑。"""
    server, hits = _recording_server()
    try:
        await fetch_writeback(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout_s=2.0,
            project_id="ba0dba3c1b6a4674a330ba56cda38cc7", version_id="original",
            result_id="cb43da21-98fd-4fad-a799-148eea42b778",
        )
        assert hits == ["/api/v3/projects/ba0dba3c1b6a4674a330ba56cda38cc7/versions/original"
                        "/results/cb43da21-98fd-4fad-a799-148eea42b778/writeback"]
    finally:
        server.shutdown()
