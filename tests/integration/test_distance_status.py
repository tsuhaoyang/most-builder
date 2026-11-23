"""每列距離狀態與完成檢查（ADR-038 D6，W2）：真 DB＋真 app。

鎖住的事：
- 草稿可帶距離狀態，寫入工時表時帶過去；寫入後該份工時表開啟檢查，之後不自動關閉。
- 整份存檔：沒帶欄位＝保留既有值；帶 null＝清除；帶值＝覆寫；不合法的值 → 422。
- 核准：開啟檢查時，任一列沒標狀態 → 409 DISTANCE_STATUS_MISSING 並列出缺的列；補齊後可核准。
- 未開啟檢查的工時表（既有資料）核准照舊，不需要狀態。
- clone 複製每列狀態與開關。
- migration v2_0052 的 CHECK 約束，以及 downgrade 拒絕條件用的計數。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0052_distance_status.py"
    spec = importlib.util.spec_from_file_location("_v2_0052", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()

GM_CYCLE = {
    "seq": "GM",
    "a0": {"reach_cm": 20},
    "g2": {"g_code": "g_grasp"},
    "a3": {"reach_cm": 25},
    "p5": {"p_base_code": "p_place_none"},
}


async def _seed_ws(db_session):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"W2-{uuid.uuid4().hex[:6]}", name_zh="W2")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"S-{uuid.uuid4().hex[:6]}", name_zh="S")
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku.id, version_no="v1", status="draft", created_by="IEC141289")
    ws = MostWorksheet(
        id=uuid.uuid4(), process_version_id=pv.id, status="draft", default_rule_set_id=rs.id,
        modeling_policy_version_id=MODELING_FACTORY_V1_ID, level_policy_version_id=LEVEL_FACTORY_V1_ID,
        revision_no=1,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()
    return ws, rs


def _save_row(row_id: str, seq_no: int, rs_code: str, **extra) -> dict:
    return {
        "id": row_id, "seq_no": seq_no, "hand": "RH", "frequency": 1, "narrative": f"w2-{seq_no}",
        "cycle": {**GM_CYCLE, "rule_set_code": rs_code},
        "level": {"ascription": "main", "level": str(seq_no)},
        **extra,
    }


async def _read(client, ws_id) -> dict:
    r = await client.get(f"/api/v2/worksheets/{ws_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def _save(client, ws_id, rows, base_revision):
    return await client.put(f"/api/v2/worksheets/{ws_id}", json={"rows": rows, "base_revision": base_revision})


async def _commit_two(client, ws_id) -> dict:
    """經編輯區寫入兩列：第一列帶 manual，第二列沒帶。回傳寫入後的讀取結果。"""
    items = [
        {"content": {"hand": "RH", "narrative": "a", "cycle": dict(GM_CYCLE),
                                         "distance_status": "manual"}},
        {"content": {"hand": "RH", "narrative": "b", "cycle": dict(GM_CYCLE)}},
    ]
    r = await client.post(f"/api/v2/worksheets/{ws_id}/drafts", json={"items": items})
    assert r.status_code == 201, r.text
    ids = [d["id"] for d in r.json()["items"]]
    r = await client.post(f"/api/v2/worksheets/{ws_id}/drafts/confirm", json={"draft_ids": ids})
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/v2/worksheets/{ws_id}/drafts/commit", json={"base_revision": 1})
    assert r.status_code == 200, r.text
    return await _read(client, ws_id)


def _error(r) -> dict:
    """ADR-034 信封：{error:{code,message,detail}}。"""
    return r.json()["error"]


async def _user(client, role: str | None) -> dict:
    emp = f"UT_W2_{(role or 'viewer').upper()}_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users",
                          json={"employee_no": emp, "display_name": emp, "roles": [role] if role else []})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}


async def _prepare_blocked(client, ws_id, rs_code) -> list[str]:
    """經編輯區寫入兩列（第二列沒狀態）、補 level、過驗證。回傳兩列 id。"""
    out = await _commit_two(client, ws_id)
    ids = [r["wi_row_id"] for r in out["rows"]]
    r = await _save(client, ws_id, [_save_row(ids[0], 1, rs_code), _save_row(ids[1], 2, rs_code)], out["revision_no"])
    assert r.status_code == 200, r.text
    v = await client.post(f"/api/v2/worksheets/{ws_id}/level/validate")
    assert v.status_code == 200 and v.json()["valid"] is True, v.text
    return ids


async def test_commit_carries_status_and_turns_check_on(client, db_session):
    ws, _ = await _seed_ws(db_session)
    before = await _read(client, ws.id)
    assert before["distance_check_required"] is False

    out = await _commit_two(client, ws.id)
    assert out["distance_check_required"] is True
    assert [r["distance_status"] for r in out["rows"]] == ["manual", None]


async def test_publish_blocked_until_every_row_has_status(client, db_session):
    ws, rs = await _seed_ws(db_session)
    out = await _commit_two(client, ws.id)
    ids = [r["wi_row_id"] for r in out["rows"]]

    # 補上 level（寫入時 level 留空，核准前要過 level 驗證）；不帶 distance_status → 保留既有值
    r = await _save(client, ws.id, [_save_row(ids[0], 1, rs.code), _save_row(ids[1], 2, rs.code)],
                    out["revision_no"])
    assert r.status_code == 200, r.text
    saved = await _read(client, ws.id)
    assert [x["distance_status"] for x in saved["rows"]] == ["manual", None]
    assert saved["distance_check_required"] is True

    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200 and v.json()["valid"] is True, v.text
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 409, p.text
    err = _error(p)
    assert err["code"] == "DISTANCE_STATUS_MISSING"
    assert err["detail"]["missing_count"] == 1
    assert err["detail"]["rows"] == [{"wi_row_id": ids[1], "seq_no": 2}]  # 只列出缺的那一列

    # 補齊：第二列標「此動作無距離」
    r = await _save(client, ws.id, [_save_row(ids[0], 1, rs.code),
                                    _save_row(ids[1], 2, rs.code, distance_status="not_applicable")],
                    saved["revision_no"])
    assert r.status_code == 200, r.text
    assert [x["distance_status"] for x in (await _read(client, ws.id))["rows"]] == ["manual", "not_applicable"]
    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200 and v.json()["valid"] is True, v.text
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 200, p.text


async def test_worksheet_without_check_publishes_without_status(client, db_session):
    """既有工時表（沒經編輯區寫入）不受影響。"""
    ws, rs = await _seed_ws(db_session)
    r = await _save(client, ws.id, [_save_row(str(uuid.uuid4()), 1, rs.code)], 1)
    assert r.status_code == 200, r.text
    out = await _read(client, ws.id)
    assert out["distance_check_required"] is False
    assert out["rows"][0]["distance_status"] is None
    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200 and v.json()["valid"] is True, v.text
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 200, p.text


async def test_save_explicit_null_clears_and_bad_value_422(client, db_session):
    ws, rs = await _seed_ws(db_session)
    rid = str(uuid.uuid4())
    r = await _save(client, ws.id, [_save_row(rid, 1, rs.code, distance_status="confirmed")], 1)
    assert r.status_code == 200, r.text
    out = await _read(client, ws.id)
    assert out["rows"][0]["distance_status"] == "confirmed"
    # 存檔不會打開檢查（只有經編輯區寫入才會）
    assert out["distance_check_required"] is False

    r = await _save(client, ws.id, [_save_row(rid, 1, rs.code, distance_status=None)], out["revision_no"])
    assert r.status_code == 200, r.text
    out = await _read(client, ws.id)
    assert out["rows"][0]["distance_status"] is None

    r = await _save(client, ws.id, [_save_row(rid, 1, rs.code, distance_status="guessed")], out["revision_no"])
    assert r.status_code == 422, r.text

    # 草稿也驗證
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [
        {"content": {"cycle": dict(GM_CYCLE), "distance_status": "guessed"}}]})
    assert r.status_code == 422, r.text


async def test_check_stays_on_after_full_save(client, db_session):
    ws, rs = await _seed_ws(db_session)
    out = await _commit_two(client, ws.id)
    r = await _save(client, ws.id, [_save_row(str(uuid.uuid4()), 1, rs.code)], out["revision_no"])
    assert r.status_code == 200, r.text
    assert (await _read(client, ws.id))["distance_check_required"] is True


async def test_clone_copies_status_and_check(client, db_session):
    ws, _ = await _seed_ws(db_session)
    await _commit_two(client, ws.id)
    r = await client.post(f"/api/v2/worksheets/{ws.id}/clone")
    assert r.status_code == 200, r.text
    cloned = await _read(client, r.json()["new_worksheet_id"])
    assert cloned["distance_check_required"] is True
    assert [x["distance_status"] for x in cloned["rows"]] == ["manual", None]


async def test_migration_constraint_and_downgrade_counts(client, db_session):
    ws, _ = await _seed_ws(db_session)
    await _commit_two(client, ws.id)
    # CHECK 約束擋掉不合法的值（繞過 API）
    with pytest.raises(Exception, match="ck_wi_rows_distance_status"):
        await db_session.execute(text(
            "UPDATE wi_rows SET distance_status = 'guessed' WHERE worksheet_id = :w"), {"w": ws.id})
    await db_session.rollback()
    # downgrade 依這兩個計數拒絕
    assert (await db_session.execute(text(MIG.SQL_COUNT_STATUSES))).scalar_one() >= 1
    assert (await db_session.execute(text(MIG.SQL_COUNT_REQUIRED))).scalar_one() >= 1


async def test_reported_rows_are_capped(client, db_session, monkeypatch):
    from ddm_v2.services.v2 import worksheet_service

    ws, rs = await _seed_ws(db_session)
    ids = await _prepare_blocked(client, ws.id, rs.code)
    # 兩列都清成沒狀態，上限調成 1：總數 2、只列 1 列（依 seq_no）
    r = await _save(client, ws.id, [_save_row(ids[0], 1, rs.code, distance_status=None),
                                    _save_row(ids[1], 2, rs.code)], (await _read(client, ws.id))["revision_no"])
    assert r.status_code == 200, r.text
    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200 and v.json()["valid"] is True, v.text
    monkeypatch.setattr(worksheet_service, "MAX_MISSING_ROWS_REPORTED", 1)
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 409, p.text
    detail = _error(p)["detail"]
    assert detail["missing_count"] == 2
    assert detail["rows"] == [{"wi_row_id": ids[0], "seq_no": 1}]


async def test_rows_added_by_other_paths_also_block(client, db_session):
    """已開啟檢查的工時表，經其他路徑（匯入 submit、模組實體化）直接建立的列沒有狀態，一樣擋核准。"""
    from ddm_v2.models.v2.worksheet import WiRow

    ws, rs = await _seed_ws(db_session)
    ids = await _prepare_blocked(client, ws.id, rs.code)
    r = await _save(client, ws.id, [_save_row(ids[0], 1, rs.code),
                                    _save_row(ids[1], 2, rs.code, distance_status="not_applicable")],
                    (await _read(client, ws.id))["revision_no"])
    assert r.status_code == 200, r.text
    extra = WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=3, hand="RH", frequency=1, provenance="imported")
    db_session.add(extra)
    await db_session.commit()
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 409, p.text
    assert _error(p)["code"] == "DISTANCE_STATUS_MISSING"
    assert _error(p)["detail"]["rows"] == [{"wi_row_id": str(extra.id), "seq_no": 3}]


async def test_roles(client, db_session):
    ws, rs = await _seed_ws(db_session)
    await _prepare_blocked(client, ws.id, rs.code)
    viewer = await _user(client, None)
    analyst = await _user(client, "analyst")
    r = await client.put(f"/api/v2/worksheets/{ws.id}",
                         json={"rows": [_save_row(str(uuid.uuid4()), 1, rs.code, distance_status="manual")]},
                         headers=viewer)
    assert r.status_code == 403, r.text
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish", headers=analyst)
    assert p.status_code == 403, p.text
