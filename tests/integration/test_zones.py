"""區域、DSX 座標同步、物件歸區（ADR-038 D5，W7a）：真 DB＋真 app；DSX 是測試內的假 ASGI app，不需要真 DSX。

鎖住的事：
- 類別：內建清單、admin 才能新增、代碼唯一與格式。
- 區域：同 SKU 名稱唯一；換綁 DSX 物件會清掉中心座標；還有物件歸區時不能刪（409 ZONE_IN_USE）。
- 同步：拉 DSX placements、存快照；綁定的區域取該物件的量測點當中心；快照裡沒有的物件 → 中心清空並回報；
  沒綁的區域列出。DSX 未開 503 DSX_DISABLED、連不到 502 DSX_UNREACHABLE、未就緒 409 DSX_NOT_READY；
  失敗時什麼都不寫。同步後 DSX 座標再變，已存的中心不變（要再按同步）。
- DSX 物件清單：連不到回 available=false＋原因，不回空清單；回應裡的壞資料不會變成 500。
- 物件歸區：按 SKU 記住、取消歸區、不能指到別的 SKU 的區域、物件不存在 404。
- 這份 WI 用到的物件：去重、列出角色與列數、附目前歸區。
- 權限：讀 viewer、寫 analyst、新增類別 admin。
- migration v2_0054 的約束與 downgrade 拒絕條件用的計數。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from ddm_v2.services.v2 import dsx_client
from ddm_v2.settings import get_settings

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0054_sku_zones.py"
    spec = importlib.util.spec_from_file_location("_v2_0054", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


class FakeDsx:
    """可設定回應的假 DSX data-service。"""

    def __init__(self) -> None:
        self.ready = True
        self.status = 200
        self.objects: list[dict] = [
            {"id": "bin_white", "label_zh": "白料盒", "vocab_code": "BIN-W", "visible": True},
            {"id": "fixture", "label_zh": "治具", "vocab_code": None, "visible": True},
        ]
        self.placements: dict[str, tuple[float, float, float]] = {
            "operator": (0.0, 0.0, 0.0), "bin_white": (40.0, 10.0, 90.0), "fixture": (0.0, 35.0, 95.0),
        }
        self.revision = 3
        self.calls: list[str] = []
        self.app = FastAPI()

        @self.app.get("/api/v1/objects")
        def objects():
            self.calls.append("objects")
            if self.status != 200:
                return JSONResponse({"detail": "boom"}, status_code=self.status)
            return {"station_id": "st-1", "objects": self.objects}

        @self.app.get("/api/v1/placements")
        def placements():
            self.calls.append("placements")
            if self.status != 200:
                return JSONResponse({"detail": "boom"}, status_code=self.status)
            return {
                "station_id": "st-1", "placement_revision": self.revision, "ready": self.ready,
                "placements": [
                    {"object_id": k, "station_local_cm": {"x": 0, "y": 0, "z": 0},
                     "anchor_cm": {"x": x, "y": y, "z": z}}
                    for k, (x, y, z) in self.placements.items()
                ],
            }


@pytest.fixture
def dsx(monkeypatch):
    fake = FakeDsx()
    monkeypatch.setattr(
        dsx_client, "_make_client",
        lambda timeout_s: httpx.AsyncClient(transport=httpx.ASGITransport(app=fake.app), timeout=timeout_s),
    )
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("DDM_DSX_API_BASE_URL", "http://dsx.test")
    get_settings.cache_clear()
    yield fake
    get_settings.cache_clear()


async def _sku(db_session):
    from ddm_v2.models.v2.org import Product, Site, Sku

    site = Site(id=uuid.uuid4(), external_code=f"W7-{uuid.uuid4().hex[:6]}", name_zh="W7")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"S-{uuid.uuid4().hex[:6]}", name_zh="S")
    db_session.add(sku)
    await db_session.commit()
    return sku


async def _vocab(db_session, kind="from", name=None):
    from ddm_v2.models.v2.vocab import WorkVocabItem

    v = WorkVocabItem(id=uuid.uuid4(), kind=kind, name_zh=name or f"物件{uuid.uuid4().hex[:4]}")
    db_session.add(v)
    await db_session.commit()
    return v


async def _user(client, role: str | None) -> dict:
    emp = f"UT_W7_{(role or 'viewer').upper()}_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users",
                          json={"employee_no": emp, "display_name": emp, "roles": [role] if role else []})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}


async def _category_id(client, code="incoming") -> str:
    r = await client.get("/api/v2/zone-categories")
    assert r.status_code == 200, r.text
    return next(c["id"] for c in r.json() if c["code"] == code)


async def _zone(client, sku_id, name, dsx_object_id=None, code="incoming") -> dict:
    body = {"category_id": await _category_id(client, code), "name": name}
    if dsx_object_id:
        body["dsx_object_id"] = dsx_object_id
    r = await client.post(f"/api/v2/skus/{sku_id}/zones", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _code(r) -> str:
    return r.json()["error"]["code"]


# ═════════ 類別 ═════════

async def test_builtin_categories_and_admin_can_add(client):
    r = await client.get("/api/v2/zone-categories")
    codes = {c["code"] for c in r.json() if c["builtin"]}
    assert {"incoming", "outgoing", "tool", "work_surface"} <= codes
    code = f"c_{uuid.uuid4().hex[:6]}"
    analyst = await _user(client, "analyst")
    body = {"code": code, "name_zh": "測試區", "name_en": "Test"}
    assert (await client.post("/api/v2/zone-categories", json=body, headers=analyst)).status_code == 403
    r = await client.post("/api/v2/zone-categories", json=body)
    assert r.status_code == 201 and r.json()["builtin"] is False, r.text
    assert (await client.post("/api/v2/zone-categories", json=body)).status_code == 409
    bad = {**body, "code": "Bad Code"}
    assert (await client.post("/api/v2/zone-categories", json=bad)).status_code == 422


# ═════════ 區域 ═════════

async def test_zone_crud_and_name_unique(client, db_session):
    sku = await _sku(db_session)
    z = await _zone(client, sku.id, "  來料盒  ", "bin_white")
    assert z["name"] == "來料盒" and z["center"] is None
    r = await client.post(f"/api/v2/skus/{sku.id}/zones",
                          json={"category_id": await _category_id(client), "name": "來料盒"})
    assert r.status_code == 409 and r.json()["error"]["detail"]["field"] == "name"
    r = await client.patch(f"/api/v2/zones/{z['id']}", json={"name": "白料盒"})
    assert r.status_code == 200 and r.json()["name"] == "白料盒" and r.json()["dsx_object_id"] == "bin_white"
    r = await client.patch(f"/api/v2/zones/{z['id']}", json={"name": None})
    assert r.status_code == 422
    r = await client.post(f"/api/v2/skus/{uuid.uuid4()}/zones", json={"category_id": await _category_id(client), "name": "x"})
    assert r.status_code == 404
    assert (await client.delete(f"/api/v2/zones/{z['id']}")).status_code == 204
    assert (await client.get(f"/api/v2/skus/{sku.id}/zones")).json()["zones"] == []


# ═════════ 同步 ═════════

async def test_sync_stores_snapshot_and_updates_bound_zones(client, db_session, dsx):
    sku = await _sku(db_session)
    bound = await _zone(client, sku.id, "白料盒", "bin_white")
    gone = await _zone(client, sku.id, "舊料架", "rack_removed")
    loose = await _zone(client, sku.id, "沒綁的")
    r = await client.post(f"/api/v2/skus/{sku.id}/zones/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["snapshot"]["placement_revision"] == 3 and body["snapshot"]["placement_count"] == 3
    assert body["missing_zone_ids"] == [gone["id"]] and body["unbound_zone_ids"] == [loose["id"]]
    zones = {z["id"]: z for z in body["zones"]}
    assert zones[bound["id"]]["center"] == {"x": 40.0, "y": 10.0, "z": 90.0}
    assert zones[bound["id"]]["center_snapshot_id"] == body["snapshot"]["id"]
    assert zones[gone["id"]]["center"] is None

    # DSX 裡物件被拖動，沒按同步 → 已存的中心不變（I6）
    dsx.placements["bin_white"] = (99.0, 99.0, 99.0)
    listed = (await client.get(f"/api/v2/skus/{sku.id}/zones")).json()
    assert next(z for z in listed["zones"] if z["id"] == bound["id"])["center"]["x"] == 40.0
    assert listed["last_snapshot"]["id"] == body["snapshot"]["id"]

    # 第二次同步帶出前一份快照（畫面據此提示 DSX 站別或版本是否不同）
    dsx.revision = 4
    again = (await client.post(f"/api/v2/skus/{sku.id}/zones/sync")).json()
    assert again["previous_snapshot"]["id"] == body["snapshot"]["id"]
    assert again["snapshot"]["placement_revision"] == 4 and body["previous_snapshot"] is None
    from ddm_v2.models.v2.zone import SkuPlacementSnapshot

    stored = await db_session.get(SkuPlacementSnapshot, uuid.UUID(body["snapshot"]["id"]))
    assert {p["point_source"] for p in stored.placements} == {"anchor"}

    # 換綁物件 → 中心清空，要重新同步
    r = await client.patch(f"/api/v2/zones/{bound['id']}", json={"dsx_object_id": "fixture"})
    assert r.json()["center"] is None and r.json()["center_snapshot_id"] is None


@pytest.mark.parametrize(("setup", "status", "code"), [
    ("not_ready", 409, "DSX_NOT_READY"),
    ("http_409", 409, "DSX_NOT_READY"),
    ("http_500", 502, "DSX_UNREACHABLE"),
    ("bad_coord", 502, "DSX_UNREACHABLE"),
])
async def test_sync_failures_are_distinct_and_write_nothing(client, db_session, dsx, setup, status, code):
    sku = await _sku(db_session)
    await _zone(client, sku.id, "白料盒", "bin_white")
    if setup == "not_ready":
        dsx.ready = False
    elif setup == "http_409":
        dsx.status = 409
    elif setup == "http_500":
        dsx.status = 500
    else:
        dsx.placements["bin_white"] = ("not-a-number", 0.0, 0.0)  # type: ignore[assignment]
    r = await client.post(f"/api/v2/skus/{sku.id}/zones/sync")
    assert r.status_code == status and _code(r) == code, r.text
    listed = (await client.get(f"/api/v2/skus/{sku.id}/zones")).json()
    assert listed["last_snapshot"] is None and listed["zones"][0]["center"] is None


async def test_old_snapshots_are_pruned(client, db_session, dsx, monkeypatch):
    from sqlalchemy import func, select

    from ddm_v2.models.v2.zone import SkuPlacementSnapshot
    from ddm_v2.services.v2 import zone_service

    monkeypatch.setattr(zone_service, "KEEP_SNAPSHOTS_PER_SKU", 2)
    sku = await _sku(db_session)
    z = await _zone(client, sku.id, "白料盒", "bin_white")
    ids = [(await client.post(f"/api/v2/skus/{sku.id}/zones/sync")).json()["snapshot"]["id"] for _ in range(3)]
    n = (await db_session.execute(select(func.count()).select_from(SkuPlacementSnapshot)
                                  .where(SkuPlacementSnapshot.sku_id == sku.id))).scalar_one()
    assert n == 2
    listed = (await client.get(f"/api/v2/skus/{sku.id}/zones")).json()
    assert listed["last_snapshot"]["id"] == ids[-1]
    assert next(x for x in listed["zones"] if x["id"] == z["id"])["center_snapshot_id"] == ids[-1]


async def test_sync_when_dsx_is_off(client, db_session, monkeypatch):
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "0")
    get_settings.cache_clear()
    try:
        sku = await _sku(db_session)
        r = await client.post(f"/api/v2/skus/{sku.id}/zones/sync")
        assert r.status_code == 503 and _code(r) == "DSX_DISABLED", r.text
        r = await client.get("/api/v2/dsx/objects")
        assert r.json() == {"available": False, "reason": "integration_disabled", "objects": []}
    finally:
        get_settings.cache_clear()


async def test_dsx_object_list_proxy(client, dsx):
    r = await client.get("/api/v2/dsx/objects")
    assert r.status_code == 200 and r.json()["available"] is True
    assert [o["id"] for o in r.json()["objects"]] == ["bin_white", "fixture"]
    dsx.objects = [{"id": "x" * 500}, {"label_zh": "沒 id"}]
    r = await client.get("/api/v2/dsx/objects")
    assert r.json() == {"available": False, "reason": "dsx_unreachable", "objects": []}, "壞資料不變成 500 也不假裝空清單"
    dsx.status = 500
    assert (await client.get("/api/v2/dsx/objects")).json()["reason"] == "dsx_unreachable"


# ═════════ 物件歸區 ═════════

async def test_object_zone_assignment(client, db_session):
    sku = await _sku(db_session)
    other = await _sku(db_session)
    z1 = await _zone(client, sku.id, "來料")
    z2 = await _zone(client, sku.id, "放料", code="outgoing")
    foreign = await _zone(client, other.id, "別人的")
    v1, v2 = await _vocab(db_session), await _vocab(db_session, kind="to")
    url = f"/api/v2/skus/{sku.id}/object-zones"
    r = await client.put(url, json={"items": [{"vocab_item_id": str(v1.id), "zone_id": z1["id"]},
                                              {"vocab_item_id": str(v2.id), "zone_id": z1["id"]},
                                              {"vocab_item_id": str(v2.id), "zone_id": z2["id"]}]})
    assert r.status_code == 200, r.text
    got = {i["vocab_item_id"]: i["zone_id"] for i in r.json()["items"]}
    assert got == {str(v1.id): z1["id"], str(v2.id): z2["id"]}, "同一請求同一物件以最後一筆為準"

    r = await client.put(url, json={"items": [{"vocab_item_id": str(v1.id), "zone_id": foreign["id"]}]})
    assert r.status_code == 404 and r.json()["error"]["detail"]["resource"] == "zone"
    r = await client.put(url, json={"items": [{"vocab_item_id": str(uuid.uuid4()), "zone_id": z1["id"]}]})
    assert r.status_code == 404 and r.json()["error"]["detail"]["resource"] == "vocab_item"
    retired = await _vocab(db_session)
    retired.is_active = False
    await db_session.commit()
    r = await client.put(url, json={"items": [{"vocab_item_id": str(retired.id), "zone_id": z1["id"]}]})
    assert r.status_code == 404, "停用的物件不能再歸區"

    r = await client.delete(f"/api/v2/zones/{z1['id']}")
    assert r.status_code == 409 and _code(r) == "ZONE_IN_USE" and r.json()["error"]["detail"]["object_count"] == 1
    r = await client.put(url, json={"items": [{"vocab_item_id": str(v1.id), "zone_id": None}]})
    assert [i["vocab_item_id"] for i in r.json()["items"]] == [str(v2.id)]
    assert (await client.delete(f"/api/v2/zones/{z1['id']}")).status_code == 204
    # 按 SKU 記住：另一個 SKU 看不到
    assert (await client.get(f"/api/v2/skus/{other.id}/object-zones")).json()["items"] == []


async def test_worksheet_objects_are_deduplicated_with_assignment(client, db_session):
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow

    sku = await _sku(db_session)
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku.id, version_no="v1", status="draft", created_by="IEC141289")
    ws = MostWorksheet(id=uuid.uuid4(), process_version_id=pv.id, status="draft", revision_no=1)
    db_session.add_all([pv, ws])
    await db_session.flush()
    bin_, fixture, part = (await _vocab(db_session, "from", "白料盒"), await _vocab(db_session, "to", "治具"),
                           await _vocab(db_session, "object", "零件"))
    db_session.add_all([
        WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=1, frequency=1, from_vocab_id=bin_.id,
              to_vocab_id=fixture.id, object_vocab_id=part.id),
        WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=2, frequency=1, from_vocab_id=fixture.id),
        WiRow(id=uuid.uuid4(), worksheet_id=ws.id, seq_no=3, frequency=1),
    ])
    await db_session.commit()
    z = await _zone(client, sku.id, "治具區", code="fixture")
    await client.put(f"/api/v2/skus/{sku.id}/object-zones",
                     json={"items": [{"vocab_item_id": str(fixture.id), "zone_id": z["id"]}]})
    r = await client.get(f"/api/v2/worksheets/{ws.id}/objects")
    assert r.status_code == 200, r.text
    objs = {o["name_zh"]: o for o in r.json()["objects"]}
    assert set(objs) == {"白料盒", "治具", "零件"}
    assert objs["治具"]["roles"] == ["from", "to"] and objs["治具"]["row_count"] == 2
    assert objs["治具"]["zone_id"] == z["id"] and objs["白料盒"]["zone_id"] is None
    assert r.json()["objects"][-1]["name_zh"] == "治具", "還沒歸區的排前面"
    assert (await client.get(f"/api/v2/worksheets/{uuid.uuid4()}/objects")).status_code == 404


# ═════════ 權限 ═════════

async def test_roles(client, db_session, dsx):
    sku = await _sku(db_session)
    viewer = await _user(client, None)
    z = await _zone(client, sku.id, "來料")
    assert (await client.get(f"/api/v2/skus/{sku.id}/zones", headers=viewer)).status_code == 200
    assert (await client.get(f"/api/v2/skus/{sku.id}/object-zones", headers=viewer)).status_code == 200
    for method, url, body in [
        ("post", f"/api/v2/skus/{sku.id}/zones", {"category_id": await _category_id(client), "name": "x"}),
        ("patch", f"/api/v2/zones/{z['id']}", {"name": "y"}),
        ("delete", f"/api/v2/zones/{z['id']}", None),
        ("post", f"/api/v2/skus/{sku.id}/zones/sync", None),
        ("put", f"/api/v2/skus/{sku.id}/object-zones", {"items": [{"vocab_item_id": str(uuid.uuid4()), "zone_id": None}]}),
        ("get", "/api/v2/dsx/objects", None),
    ]:
        kw = {"headers": viewer} | ({"json": body} if body is not None else {})
        r = await getattr(client, method)(url, **kw)
        assert r.status_code == 403, (method, url, r.text)
    assert dsx.calls == [], "viewer 不會觸發 DSX 呼叫"


# ═════════ migration ═════════

async def test_migration_constraints_and_downgrade_count(client, db_session):
    sku = await _sku(db_session)
    z = await _zone(client, sku.id, "來料")
    with pytest.raises(Exception, match="ck_sku_zones_center_complete"):
        await db_session.execute(text("UPDATE sku_zones SET center_x = 1 WHERE id = :i"), {"i": z["id"]})
    await db_session.rollback()
    with pytest.raises(Exception, match="ck_zone_categories_code_format"):
        await db_session.execute(text(
            "INSERT INTO zone_categories (id, code, name_zh, name_en, created_by) "
            "VALUES (gen_random_uuid(), 'Bad', 'x', 'x', 't')"))
    await db_session.rollback()
    assert (await db_session.execute(text(MIG.SQL_COUNT_USER_DATA))).scalar_one() >= 1
