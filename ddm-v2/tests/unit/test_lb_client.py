"""LB 回寫 client（GET …/results/{r}/writeback）——成功／4xx／5xx／逾時／連線失敗。

比照 test_dsx_client.py：起真的本機 HTTP server 測 httpx 客戶端的實際行為，不 monkeypatch httpx。
成功案用 LB 實跑 fixture（writeback_sample.json）當回應 body。
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ddm_v2.services.v2.lb_client import LbRequestFailed, LbUnreachable, fetch_writeback

FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _start_server(status: int, body: dict | None, *, delay_s: float = 0.0):
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            server.received_path = self.path
            server.received_headers = dict(self.headers)
            if delay_s:
                time.sleep(delay_s)
            raw = json.dumps(body or {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.received_path = None
    server.received_headers = {}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.mark.asyncio
async def test_success_returns_payload_and_correct_url():
    server = _start_server(200, _payload())
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        out = await fetch_writeback(
            base_url=base_url, project_id="P1", version_id="V1", result_id="R1", timeout_s=5.0
        )
    finally:
        server.shutdown()
    assert out["contract_version"] == "lb-most-writeback-v1"
    assert len(out["rows"]) == 33
    assert server.received_path == "/api/v3/projects/P1/versions/V1/results/R1/writeback"


@pytest.mark.asyncio
async def test_auth_header_passed_through_when_set():
    server = _start_server(200, _payload())
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        await fetch_writeback(
            base_url=base_url, project_id="P1", version_id="V1", result_id="R1", timeout_s=5.0,
            auth_header=("X-Username", "IEC141289"),
        )
    finally:
        server.shutdown()
    assert server.received_headers.get("X-Username") == "IEC141289"


@pytest.mark.asyncio
async def test_4xx_raises_request_failed_with_status():
    server = _start_server(404, {"detail": "result not found"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(LbRequestFailed) as ei:
            await fetch_writeback(
                base_url=base_url, project_id="P1", version_id="V1", result_id="R1", timeout_s=5.0
            )
        assert ei.value.status_code == 404
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_5xx_raises_unreachable():
    server = _start_server(500, {"detail": "boom"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(LbUnreachable):
            await fetch_writeback(
                base_url=base_url, project_id="P1", version_id="V1", result_id="R1", timeout_s=5.0
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_timeout_raises_unreachable():
    server = _start_server(200, _payload(), delay_s=1.0)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(LbUnreachable):
            await fetch_writeback(
                base_url=base_url, project_id="P1", version_id="V1", result_id="R1", timeout_s=0.1
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_connection_refused_raises_unreachable():
    with pytest.raises(LbUnreachable):
        await fetch_writeback(
            base_url="http://127.0.0.1:1", project_id="P1", version_id="V1", result_id="R1", timeout_s=1.0
        )
