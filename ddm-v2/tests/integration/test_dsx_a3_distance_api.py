"""POST /api/v2/dsx/a3-distance——DSX 整合 API 契約 v2 §3.1／§6。

DSX 本身不上線（mock 邊界在 dsx_client 層，比照 test_wi_ai_l2.py 的
`monkeypatch.setattr(wi_ai_service, "_try_llm_plan", ...)` 慣例）；DB 走真的 migration
（wi_row_dsx_suggestions 的 upsert 語意需要真的表存在）。
"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"


def _gm_row(row_id: str) -> dict:
    return {
        "id": row_id,
        "seq_no": 1,
        "hand": "RH",
        "frequency": 1,
        "narrative": "dsx a3 distance",
        "cycle": {
            "seq": "GM",
            "rule_set_code": "MINIMOST_FACTORY_V1",
            "a0": {"reach_cm": 20},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25},
            "p5": {"p_base_code": "p_place_none"},
        },
        "level": {"ascription": "main", "level": "1"},
    }


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def _clone_with_row(client) -> tuple[str, str]:
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    rev = (await client.get(f"/api/v2/worksheets/{new}")).json()["revision_no"]
    row_id = str(uuid.uuid4())
    row = _gm_row(row_id)
    s = await client.put(
        f"/api/v2/worksheets/{new}",
        json={"base_revision": rev, "rows": [row]},
    )
    assert s.status_code == 200, s.text
    return new, row_id


async def _make_vocab(db_session, external_code: str | None, kind: str = "tool") -> str:
    from ddm_v2.models.v2.vocab import WorkVocabItem

    vid = uuid.uuid4()
    db_session.add(
        WorkVocabItem(id=vid, external_code=external_code, kind=kind, name_zh=f"vocab-{vid}")
    )
    await db_session.flush()
    return str(vid)


async def test_integration_disabled_by_default(client, db_session, monkeypatch):
    """feature flag 檢查排在 wi_row_id 有效性檢查之前——不需要真的 WiRow 也能過。"""
    monkeypatch.delenv("DDM_DSX_INTEGRATION_ENABLED", raising=False)
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        resp = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {
            "available": False,
            "distance_cm": None,
            "horizontal_cm": None,
            "vertical_cm": None,
            "provisional": None,
            "measure_from_mode": None,
            "warnings": [],
            "queried_at": None,
            "reason": "integration_disabled",
        }
    finally:
        get_settings.cache_clear()


async def test_wi_row_id_omitted_succeeds_without_writing_snapshot(
    client, db_session, monkeypatch
):
    """契約 §6（User 2026-08-24 裁決）：`WiWorkbench.tsx` 的建立器面板組新列、尚未存檔
    時沒有真實 `wi_row_id` 可帶——省略它查詢仍要成功，只是不留出處快照。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("DDM_DSX_API_BASE_URL", "http://127.0.0.1:1")
    from ddm_v2.services.v2 import dsx_client
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        async def _fake_query(**_kw):
            return dsx_client.DsxDistanceResult(
                distance_cm=17.0,
                provisional=True,
                measure_from_mode="shoulder",
                warnings=[],
                raw={"distance_cm": 17.0},
                horizontal_cm=15.0,
                vertical_cm=8.5,
            )

        monkeypatch.setattr(dsx_client, "query_distance", _fake_query)
        resp = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["available"] is True
        assert body["distance_cm"] == 17.0
        assert body["horizontal_cm"] == 15.0
        assert body["vertical_cm"] == 8.5

        from sqlalchemy import select

        from ddm_v2.models.v2.dsx_suggestion import WiRowDsxSuggestion

        rows = (
            await db_session.execute(
                select(WiRowDsxSuggestion).where(
                    WiRowDsxSuggestion.from_vocab_id == uuid.UUID(from_id)
                )
            )
        ).scalars().all()
        assert rows == [], "wi_row_id 缺席時不得寫入 suggestion 快照（用查詢確認，不能只看回應）"
    finally:
        get_settings.cache_clear()


async def test_vocab_not_mapped_when_external_code_missing(client, db_session, monkeypatch):
    """省略 wi_row_id（純查詢）——不需要真的 WiRow 也能測到 vocab_not_mapped。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        from_id = await _make_vocab(db_session, external_code=None)
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        resp = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["available"] is False
        assert resp.json()["reason"] == "vocab_not_mapped"
    finally:
        get_settings.cache_clear()


async def test_dsx_object_not_found_and_dsx_unreachable_are_distinct(
    client, db_session, monkeypatch
):
    """省略 wi_row_id——這條只測 query_distance 例外→reason 映射，不需要真的 WiRow。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("DDM_DSX_API_BASE_URL", "http://127.0.0.1:1")
    from ddm_v2.services.v2 import dsx_client
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        async def _raise_not_found(**_kw):
            raise dsx_client.DsxObjectNotFound("boom")

        monkeypatch.setattr(dsx_client, "query_distance", _raise_not_found)
        r1 = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert r1.json()["reason"] == "dsx_object_not_found"

        async def _raise_unreachable(**_kw):
            raise dsx_client.DsxUnreachable("boom")

        monkeypatch.setattr(dsx_client, "query_distance", _raise_unreachable)
        r2 = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert r2.json()["reason"] == "dsx_unreachable"
        assert r1.json()["reason"] != r2.json()["reason"], "I5：兩種失效不得混為一談"
    finally:
        get_settings.cache_clear()


async def test_success_upserts_single_suggestion_row_on_repeat_query(
    client, db_session, monkeypatch
):
    """同一 (wi_row_id, a_slot_key) 第二次查詢覆蓋舊筆，不新增一列（契約 §2.2 upsert 語意）。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("DDM_DSX_API_BASE_URL", "http://127.0.0.1:1")
    from ddm_v2.services.v2 import dsx_client
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        if not await _seeded(client):
            pytest.skip("demo worksheet 未種")
        _ws, row_id = await _clone_with_row(client)
        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        async def _fake_first(**_kw):
            return dsx_client.DsxDistanceResult(
                distance_cm=30.0,
                provisional=True,
                measure_from_mode="shoulder",
                warnings=["first"],
                raw={"distance_cm": 30.0, "call": 1},
                horizontal_cm=28.0,
                vertical_cm=10.0,
            )

        monkeypatch.setattr(dsx_client, "query_distance", _fake_first)
        r1 = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"wi_row_id": row_id, "from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert r1.status_code == 200, r1.text
        body1 = r1.json()
        assert body1["available"] is True
        assert body1["distance_cm"] == 30.0
        assert body1["horizontal_cm"] == 28.0
        assert body1["vertical_cm"] == 10.0
        # I1：DSX 回應原樣保留，不轉換／不取整——契約 §2.2。
        assert body1["warnings"] == ["first"]

        async def _fake_second(**_kw):
            return dsx_client.DsxDistanceResult(
                distance_cm=55.5,
                provisional=False,
                measure_from_mode="shoulder",
                warnings=["second"],
                raw={"distance_cm": 55.5, "call": 2},
            )

        monkeypatch.setattr(dsx_client, "query_distance", _fake_second)
        r2 = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"wi_row_id": row_id, "from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert r2.status_code == 200, r2.text
        body2 = r2.json()
        assert body2["distance_cm"] == 55.5

        from sqlalchemy import select

        from ddm_v2.models.v2.dsx_suggestion import WiRowDsxSuggestion

        rows = (
            (
                await db_session.execute(
                    select(WiRowDsxSuggestion).where(
                        WiRowDsxSuggestion.wi_row_id == uuid.UUID(row_id)
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1, "同鍵第二次查詢必須覆蓋，不是新增一列"
        assert float(rows[0].raw_distance_cm) == 55.5
        assert rows[0].dsx_response == {"distance_cm": 55.5, "call": 2}
        # created_by 只在第一次寫入時記，updated_by 每次查詢都更新為當次 actor。
        assert rows[0].created_by == "IEC141289"
        assert rows[0].updated_by == "IEC141289"
    finally:
        get_settings.cache_clear()


async def test_requires_authentication(client, monkeypatch):
    """RBAC：`require_role("analyst")`，匿名（不帶認證）→ 401（照抄 test_calculate_v2.py:175）。"""
    import httpx

    from ddm_v2.main import create_app

    monkeypatch.delenv("AUTH_DEV_USER", raising=False)
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        r = await anon.post(
            "/api/v2/dsx/a3-distance",
            json={
                "from_vocab_id": str(uuid.uuid4()),
                "to_vocab_id": str(uuid.uuid4()),
            },
        )
    assert r.status_code == 401, r.text


async def test_wi_row_id_not_found_returns_404(client, db_session, monkeypatch):
    """wi_row_id 有值但指向不存在的列——先前完全沒有存在性檢查，flush() 才炸 500。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        resp = await client.post(
            "/api/v2/dsx/a3-distance",
            json={
                "wi_row_id": str(uuid.uuid4()),
                "from_vocab_id": from_id,
                "to_vocab_id": to_id,
            },
        )
        assert resp.status_code == 404, resp.text
    finally:
        get_settings.cache_clear()


async def test_wi_row_id_on_published_version_returns_409(client, db_session, monkeypatch):
    """wi_row_id 指向的版本已發布（非 draft）——拒絕寫入 DSX 建議快照。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    try:
        if not await _seeded(client):
            pytest.skip("demo worksheet 未種")
        new_ws, row_id = await _clone_with_row(client)
        pub = await client.post(f"/api/v2/worksheets/{new_ws}/publish")
        assert pub.status_code == 200, pub.text

        from_id = await _make_vocab(db_session, f"tool_01-{uuid.uuid4()}")
        to_id = await _make_vocab(db_session, f"bin_white-{uuid.uuid4()}")

        resp = await client.post(
            "/api/v2/dsx/a3-distance",
            json={"wi_row_id": row_id, "from_vocab_id": from_id, "to_vocab_id": to_id},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "VERSION_PUBLISHED"
    finally:
        get_settings.cache_clear()
