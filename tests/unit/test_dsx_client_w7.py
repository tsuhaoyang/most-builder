"""dsx_client 的物件清單與座標快照解析（ADR-038 W7a）：DSX 沒有認證，回應當不可信輸入。"""
from __future__ import annotations

import httpx
import pytest

from ddm_v2.services.v2 import dsx_client

pytestmark = pytest.mark.unit


def _install(monkeypatch, handler):
    monkeypatch.setattr(
        dsx_client, "_make_client",
        lambda timeout_s: httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=timeout_s),
    )


async def test_non_finite_coordinates_are_rejected(monkeypatch):
    body = b'{"ready": true, "station_id": "s", "placement_revision": 1, "placements": [{"object_id": "a", "anchor_cm": {"x": NaN, "y": 0, "z": 0}}]}'
    _install(monkeypatch, lambda req: httpx.Response(200, content=body, headers={"content-type": "application/json"}))
    with pytest.raises(dsx_client.DsxUnreachable):
        await dsx_client.get_placements(base_url="http://dsx", timeout_s=1)


async def test_connect_error_is_unreachable(monkeypatch):
    def boom(req):
        raise httpx.ConnectError("refused", request=req)

    _install(monkeypatch, boom)
    with pytest.raises(dsx_client.DsxUnreachable):
        await dsx_client.list_objects(base_url="http://dsx", timeout_s=1)


def _placements_body(placements, **extra):
    return {"ready": True, "station_id": "s", "placement_revision": 7, "placements": placements, **extra}


async def test_anchor_preferred_and_source_recorded(monkeypatch):
    placements = [
        {"object_id": "a", "station_local_cm": {"x": 1, "y": 1, "z": 1}, "anchor_cm": {"x": 2, "y": 3, "z": 4}},
        {"object_id": "b", "station_local_cm": {"x": 5, "y": 6, "z": 7}},
    ]
    _install(monkeypatch, lambda req: httpx.Response(200, json=_placements_body(placements)))
    got = await dsx_client.get_placements(base_url="http://dsx", timeout_s=1)
    assert [(p.x, p.y, p.z, p.point_source) for p in got.placements] == [(2, 3, 4, "anchor"), (5, 6, 7, "station_local")]
    assert got.placement_revision == 7 and got.station_id == "s"


@pytest.mark.parametrize("bad", [
    "too_many", "huge_coord", "duplicate_id", "no_station", "huge_revision", "negative_revision", "inf_literal",
])
async def test_untrusted_placements_are_rejected_whole(monkeypatch, bad):
    ok = {"object_id": "a", "anchor_cm": {"x": 1, "y": 1, "z": 1}}
    body: dict | bytes = _placements_body([ok])
    if bad == "too_many":
        body = _placements_body([{**ok, "object_id": f"o{i}"} for i in range(dsx_client.MAX_DSX_OBJECTS + 1)])
    elif bad == "huge_coord":
        body = _placements_body([{**ok, "anchor_cm": {"x": 1e12, "y": 0, "z": 0}}])
    elif bad == "duplicate_id":
        body = _placements_body([ok, ok])
    elif bad == "no_station":
        body = {**_placements_body([ok]), "station_id": None}
    elif bad == "huge_revision":
        body = _placements_body([ok], placement_revision=2**40)
    elif bad == "negative_revision":
        body = _placements_body([ok], placement_revision=-1)
    else:
        body = b'{"ready": true, "station_id": "s", "placement_revision": 1e999, "placements": []}'
    if isinstance(body, bytes):
        _install(monkeypatch, lambda req: httpx.Response(200, content=body))
    else:
        _install(monkeypatch, lambda req: httpx.Response(200, json=body))
    with pytest.raises(dsx_client.DsxUnreachable):
        await dsx_client.get_placements(base_url="http://dsx", timeout_s=1)


async def test_oversized_body_is_cut_off(monkeypatch):
    monkeypatch.setattr(dsx_client, "MAX_DSX_BODY_BYTES", 100)
    _install(monkeypatch, lambda req: httpx.Response(200, content=b"[" + b" " * 500 + b"]"))
    with pytest.raises(dsx_client.DsxUnreachable, match="bytes"):
        await dsx_client.list_objects(base_url="http://dsx", timeout_s=1)


async def test_object_list_over_cap_is_rejected(monkeypatch):
    objs = [{"id": f"o{i}"} for i in range(dsx_client.MAX_DSX_OBJECTS + 1)]
    _install(monkeypatch, lambda req: httpx.Response(200, json={"objects": objs}))
    with pytest.raises(dsx_client.DsxUnreachable):
        await dsx_client.list_objects(base_url="http://dsx", timeout_s=1)
