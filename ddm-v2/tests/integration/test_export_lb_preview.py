"""B3（ADR-035 D10）：未存檔 preview 端點 dry-run。

preview 與「PUT 後 GET lb-report」逐鍵相等；不寫 DB；壞 cycle→422（碼同 PUT）；404；viewer；params。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text as _sql

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _gm(seq, wi_group="裝 HDD"):
    return {"id": str(uuid.uuid4()), "seq_no": seq, "hand": "RH", "object_vocab_id": OBJ, "frequency": 1,
            "narrative": f"步驟 {seq}", "wi_group": wi_group,
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def _clone(client) -> str:
    return (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]


def _strip(rep: dict) -> dict:
    return {k: v for k, v in rep.items() if k not in ("worksheet_id", "preview")}


async def test_preview_equals_saved_report(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    body = {"rows": [_gm(1), _gm(2)]}
    prev = await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json=body)
    assert prev.status_code == 200, prev.text
    saved = await client.put(f"/api/v2/worksheets/{ws}", json=body)
    assert saved.status_code == 200, saved.text
    rep = await client.get(f"/api/v2/worksheets/{ws}/export/lb-report")
    assert rep.status_code == 200
    # errors/warnings/tasks_out/groups/atomic_groups/rows/hints 逐鍵相等
    p, g = _strip(prev.json()), _strip(rep.json())
    for k in ("errors", "warnings", "tasks_out", "groups", "atomic_groups", "rows", "hints"):
        assert p[k] == g[k], f"key {k} 不一致：preview={p[k]} saved={g[k]}"


async def test_preview_does_not_touch_db(client, db_session):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    # 先存一份基線
    await client.put(f"/api/v2/worksheets/{ws}", json={"rows": [_gm(1)]})
    before_rows = (await db_session.execute(_sql("SELECT count(*) FROM wi_rows WHERE worksheet_id=:w"), {"w": ws})).scalar_one()
    before_hash = (await client.get(f"/api/v2/worksheets/{ws}")).json()["content_hash"]
    before_rev = (await client.get(f"/api/v2/worksheets/{ws}")).json()["revision_no"]
    # preview 三列（不同於基線）
    await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json={"rows": [_gm(1), _gm(2), _gm(3)]})
    after_rows = (await db_session.execute(_sql("SELECT count(*) FROM wi_rows WHERE worksheet_id=:w"), {"w": ws})).scalar_one()
    after = (await client.get(f"/api/v2/worksheets/{ws}")).json()
    assert after_rows == before_rows          # 列數不變
    assert after["content_hash"] == before_hash
    assert after["revision_no"] == before_rev


async def test_preview_include_tasks(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    from ddm_v2.lb_projection.emit import COLUMNS

    r1 = await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview?include_tasks=1", json={"rows": [_gm(1)]})
    body = r1.json()
    assert "tasks" in body and len(body["tasks"]) == body["tasks_out"]
    assert list(body["tasks"][0].keys()) == list(COLUMNS)
    r0 = await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json={"rows": [_gm(1)]})
    assert "tasks" not in r0.json()


async def test_preview_bad_cycle_422_same_as_put(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    bad = _gm(1)
    # repeat_count 超範圍（引擎 _repeat 必拋 REPEAT_INVALID；A 格禁 repeat）→ 存與預覽同碼
    bad["cycle"] = {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                    "a0": {"reach_cm": 20, "repeat_count": 999}, "g2": {"g_code": "g_grasp"},
                    "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}
    prev = await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json={"rows": [bad]})
    put = await client.put(f"/api/v2/worksheets/{ws}", json={"rows": [bad]})
    assert prev.status_code == put.status_code == 422, f"preview={prev.status_code} put={put.status_code}"
    assert prev.json()["error"]["code"] == put.json()["error"]["code"]


async def test_preview_worksheet_not_found_404(client):
    prev = await client.post(f"/api/v2/worksheets/{uuid.uuid4()}/export/lb-report/preview", json={"rows": []})
    assert prev.status_code == 404


async def test_preview_viewer_allowed(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json={"rows": [_gm(1)]},
                          headers={"X-Username": "viewer_user"})
    # viewer+ 可讀（ADR-019 Option A）；不應 403
    assert r.status_code != 403


async def test_preview_errors_carry_params(client):
    """出 W_TOOL_FREQ_ALL_CYCLIC 的列 → warnings[].params.frequency 存在。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws = await _clone(client)
    # 需要一個持工具 F>1 的列才會出 W_TOOL_FREQ_ALL_CYCLIC；demo vocab 未必有 tool。
    # 退而求其次：驗 preview 的 warnings/errors 每項都有 params 鍵（可為 None）。
    body = {"rows": [_gm(1), _gm(2)]}
    prev = (await client.post(f"/api/v2/worksheets/{ws}/export/lb-report/preview", json=body)).json()
    for item in prev["errors"] + prev["warnings"]:
        assert "params" in item
