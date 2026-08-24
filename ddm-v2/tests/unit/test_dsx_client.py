"""DSX data-service client（POST /api/v1/distance）——成功／404／409／逾時／連線失敗。

比照 test_planner_eval.py 的慣例：起一個真的本機 HTTP server 測 httpx 客戶端的實際行為，
而不是 monkeypatch `httpx.AsyncClient`——後者測的是我們自己 stub 的行為，不是 httpx 真的
怎麼處理逾時/連線失敗。
"""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ddm_v2.services.v2.dsx_client import (
    DsxObjectNotFound,
    DsxUnreachable,
    query_distance,
)


def _start_server(status: int, body: dict | None, *, delay_s: float = 0.0):
    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            server.received_path = self.path
            server.received_body = json.loads(raw) if raw else None
            if delay_s:
                time.sleep(delay_s)
            payload = json.dumps(body or {}).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.received_path = None
    server.received_body = None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_DISTANCE_RESULT = {
    "from_id": "tool_01",
    "to_id": "bin_white",
    "distance_cm": 42.5,
    "horizontal_cm": 40.0,
    "vertical_cm": 12.0,
    "method": "straight_line_3d",
    "station_id": "most-single-station",
    "placement_revision": 1,
    "measure_from_mode": "shoulder",
    "provisional": True,
    "warnings": ["P4 未定：量測端點為 bbox 中心，非取放錨點"],
}


@pytest.mark.asyncio
async def test_success_preserves_raw_response_untouched():
    server = _start_server(200, _DISTANCE_RESULT)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = await query_distance(
            base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
        )
    finally:
        server.shutdown()

    assert result.distance_cm == 42.5
    assert result.horizontal_cm == 40.0
    assert result.vertical_cm == 12.0
    assert result.provisional is True
    assert result.measure_from_mode == "shoulder"
    assert result.warnings == _DISTANCE_RESULT["warnings"]
    # I1：不做任何轉換或取整——raw 必須是 DSX 回應原樣（含 station_id/placement_revision 等
    # I4 出處欄位，即使 DsxDistanceResult 沒有為它們個別開欄位）。
    assert result.raw == _DISTANCE_RESULT
    # 之前 7 條測試全部沒發現 URL 打錯或 from_id/to_id 對調——實際比對送出的 request。
    assert server.received_path == "/api/v1/distance"
    assert server.received_body == {"from_id": "tool_01", "to_id": "bin_white"}


@pytest.mark.asyncio
async def test_404_raises_object_not_found():
    server = _start_server(404, {"detail": "找不到 unknown_id 或 bin_white 的擺放座標"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(DsxObjectNotFound):
            await query_distance(
                base_url=base_url, from_id="unknown_id", to_id="bin_white", timeout_s=5.0
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_409_placements_not_ready_also_raises_object_not_found():
    """已知契約落差：DSX 409（場景座標未就緒）併入 DsxObjectNotFound——見 dsx_client 模組 docstring。"""
    server = _start_server(409, {"detail": "尚未取得場景座標"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(DsxObjectNotFound):
            await query_distance(
                base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_500_raises_unreachable_not_object_not_found():
    server = _start_server(500, {"detail": "internal error"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(DsxUnreachable):
            await query_distance(
                base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_timeout_raises_unreachable():
    server = _start_server(200, _DISTANCE_RESULT, delay_s=1.0)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(DsxUnreachable):
            await query_distance(
                base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=0.1
            )
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_connection_refused_raises_unreachable():
    # port 1：特權埠、本機幾乎必定沒有服務在聽，連線立即被拒。
    with pytest.raises(DsxUnreachable):
        await query_distance(
            base_url="http://127.0.0.1:1", from_id="tool_01", to_id="bin_white", timeout_s=1.0
        )


@pytest.mark.asyncio
async def test_missing_horizontal_vertical_defaults_to_none_not_swallowed_error():
    """舊版 DSX 或這組物件沒有分量資料——不得炸掉，horizontal_cm/vertical_cm 應為 None。"""
    body = {k: v for k, v in _DISTANCE_RESULT.items() if k not in ("horizontal_cm", "vertical_cm")}
    server = _start_server(200, body)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = await query_distance(
            base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
        )
    finally:
        server.shutdown()

    assert result.distance_cm == 42.5
    assert result.horizontal_cm is None
    assert result.vertical_cm is None


@pytest.mark.asyncio
async def test_explicit_null_horizontal_vertical_returns_none():
    """DSX 若照 Pydantic 慣例序列化為顯式 null（而非省略 key），行為應與缺 key 相同。"""
    body = {**_DISTANCE_RESULT, "horizontal_cm": None, "vertical_cm": None}
    server = _start_server(200, body)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = await query_distance(
            base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
        )
    finally:
        server.shutdown()

    assert result.distance_cm == 42.5
    assert result.horizontal_cm is None
    assert result.vertical_cm is None


@pytest.mark.asyncio
async def test_non_numeric_horizontal_does_not_fail_whole_query():
    """horizontal_cm 是附屬分量欄位——格式異常不得拖垮本來能成功的 distance_cm。"""
    body = {**_DISTANCE_RESULT, "horizontal_cm": "N/A"}
    server = _start_server(200, body)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        result = await query_distance(
            base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
        )
    finally:
        server.shutdown()

    assert result.distance_cm == 42.5
    assert result.horizontal_cm is None
    assert result.vertical_cm == 12.0


@pytest.mark.asyncio
async def test_malformed_success_body_raises_key_error_not_swallowed():
    """DSX 回應缺 distance_cm——不得靜默塞 0，讓 KeyError 冒出去（No error bypass）。"""
    server = _start_server(200, {"from_id": "tool_01", "to_id": "bin_white"})
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        with pytest.raises(KeyError):
            await query_distance(
                base_url=base_url, from_id="tool_01", to_id="bin_white", timeout_s=5.0
            )
    finally:
        server.shutdown()
