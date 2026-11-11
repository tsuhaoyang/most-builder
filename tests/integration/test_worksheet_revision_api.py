"""R1 worksheet revision optimistic locking（integration）。"""
from __future__ import annotations

import io
import os
import uuid

import pytest
from sqlalchemy import select, text

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


def _err_code(payload: dict) -> str | None:
    """例外 handler 回 {"error": {...}}；部分路由用 FastAPI 原生 {"detail": {...}}。"""
    return (payload.get("error") or {}).get("code") or (payload.get("detail") or {}).get("code")


def _err_detail(payload: dict) -> dict:
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("detail") or {}
    detail = payload.get("detail")
    return detail if isinstance(detail, dict) else {}


def _gm_row(row_id: str, rule_set_code: str) -> dict:
    # 對齊 test_worksheet._gm_row 的 CycleIn 形狀（引擎 GM=28 錨）
    return {
        "id": row_id,
        "seq_no": 1,
        "hand": "RH",
        "frequency": 1,
        "narrative": "r1 revision",
        "cycle": {
            "seq": "GM",
            "rule_set_code": rule_set_code,
            "a0": {"reach_cm": 20},
            "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25},
            "p5": {"p_base_code": "p_place_none"},
        },
        "level": {"ascription": "main", "level": "1"},
    }


async def _seed_ws(db_session, *, revision_no: int = 1):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"R1-{uuid.uuid4().hex[:6]}", name_zh="R1")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(
        id=uuid.uuid4(),
        product_id=product.id,
        sku_code=f"S-{uuid.uuid4().hex[:6]}",
        name_zh="S",
    )
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(
        id=uuid.uuid4(),
        sku_id=sku.id,
        version_no="v1",
        status="draft",
        created_by="IEC141289",
    )
    ws = MostWorksheet(
        id=uuid.uuid4(),
        process_version_id=pv.id,
        status="draft",
        default_rule_set_id=rs.id,
        modeling_policy_version_id=MODELING_FACTORY_V1_ID,
        level_policy_version_id=LEVEL_FACTORY_V1_ID,
        revision_no=revision_no,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()
    return ws, rs


@pytest.mark.asyncio
async def test_revision_conflict_second_save_409(client, db_session):
    """兩 client 同 base_revision：一成功、一 409；舊 rows 保留。"""
    from ddm_v2.models.v2.worksheet import WiRow

    ws, rs = await _seed_ws(db_session, revision_no=1)
    rid = str(uuid.uuid4())
    body1 = {"base_revision": 1, "rows": [_gm_row(rid, rs.code)]}
    r1 = await client.put(f"/api/v2/worksheets/{ws.id}", json=body1)
    assert r1.status_code == 200, r1.text
    assert r1.json()["revision_no"] == 2
    assert r1.json()["content_hash"]

    body_stale = {"base_revision": 1, "rows": []}
    r2 = await client.put(f"/api/v2/worksheets/{ws.id}", json=body_stale)
    assert r2.status_code == 409, r2.text
    err = r2.json()
    code = (err.get("error") or {}).get("code") or (err.get("detail") or {}).get("code")
    assert code == "WORKSHEET_REVISION_CONFLICT"

    await db_session.refresh(ws)
    assert int(ws.revision_no) == 2
    n_rows = (
        await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))
    ).scalars().all()
    assert len(n_rows) == 1

    r3 = await client.put(
        f"/api/v2/worksheets/{ws.id}",
        json={"base_revision": 2, "rows": []},
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["revision_no"] == 3
    assert r3.json()["rows"] == []


@pytest.mark.asyncio
async def test_clone_resets_revision_to_1(client, db_session):
    ws, _rs = await _seed_ws(db_session, revision_no=5)
    c = await client.post(f"/api/v2/worksheets/{ws.id}/clone")
    assert c.status_code == 200, c.text
    assert c.json()["revision_no"] == 1
    new_id = c.json()["new_worksheet_id"]
    g = await client.get(f"/api/v2/worksheets/{new_id}")
    assert g.status_code == 200
    assert g.json()["revision_no"] == 1


@pytest.mark.asyncio
async def test_publish_does_not_bump_revision(client, db_session):
    ws, _rs = await _seed_ws(db_session, revision_no=3)
    v = await client.post(f"/api/v2/worksheets/{ws.id}/level/validate")
    assert v.status_code == 200, v.text
    assert v.json()["valid"] is True
    p = await client.post(f"/api/v2/worksheets/{ws.id}/publish")
    assert p.status_code == 200, p.text
    await db_session.refresh(ws)
    assert int(ws.revision_no) == 3


# ── bump 的 session 快取語意（P0 迴歸）────────────────────────────────────────
# bump 走 Core/raw UPDATE，ORM identity map 不會自己知道。修法（_resync_worksheet）
# 必須同時滿足三條，各由下面一個測試獨立釘住：
#   (A) 對齊：目標 worksheet 的 ORM 副本要即時等於 DB 真值（identity map 可能握著舊值）。
#       → test_bump_refreshes_target_without_expiring_other_objects
#         / test_bump_conflict_reports_true_current_revision（stale 版本）
#   (B) 不誤傷別人：session 裡其他物件不得被失效（session.expire_all() 就是踩這條）。
#       → test_bump_refreshes_target_without_expiring_other_objects 的旁觀者斷言
#   (C) 不誤傷自己的 relationship：refresh 必須用 attribute_names= 窄化到純量欄位，
#       整顆 refresh()／get(populate_existing=True) 會把已 eager-load 的 rows/
#       process_version 一起 expire，等於把 MissingGreenlet 換個欄位重埋。
#       → test_bump_keeps_eagerly_loaded_relationships_loaded
#
# ⚠️ 刻意不寫「bump 後把同一顆物件弄 dirty 再 flush，revision_no 不得被蓋回」這型測試：
#    全 repo 沒有任何一處對 .revision_no 做 ORM 賦值，SQLAlchemy 的 unit of work 只
#    UPDATE 有 net history 差異的欄位——「蓋回」在結構上不可能發生，那種測試在把
#    _resync_worksheet 整個拿掉（即真 bug）時仍是綠的。真正的 stale 情境請看
#    test_bump_conflict_reports_true_current_revision（identity map 1 / DB 9）。


@pytest.mark.asyncio
async def test_bump_refreshes_target_without_expiring_other_objects(db_session):
    """(A)+(B)：bump 後目標物件即時是新值，且同 session 其他物件仍可直接存取。"""
    from ddm_v2.models.v2.worksheet import ProcessVersion
    from ddm_v2.services.v2.worksheet_revision import bump_worksheet_revision

    target, _rs = await _seed_ws(db_session, revision_no=1)
    bystander, _rs2 = await _seed_ws(db_session, revision_no=7)
    pv = await db_session.get(ProcessVersion, target.process_version_id)
    assert pv is not None

    new_rev = await bump_worksheet_revision(
        db_session, worksheet_id=target.id, base_revision=1, edited_by="IEC141289"
    )
    assert new_rev == 2

    # (A) 不需要任何額外 IO 就能讀到新值。
    #     - 修法被拿掉 → 這裡還是 1；
    #     - 改成 session.expire(target) → 這行變成 async lazy load → MissingGreenlet。
    assert int(target.revision_no) == 2
    assert target.last_edited_by == "IEC141289"
    assert target.last_edited_at is not None

    # (B) 旁觀者（同型別的另一顆、以及關聯的 ProcessVersion）不得被失效。
    #     expire_all() 會讓下面兩行變成 async lazy load → MissingGreenlet。
    assert int(bystander.revision_no) == 7
    assert pv.status == "draft"


@pytest.mark.asyncio
async def test_bump_keeps_eagerly_loaded_relationships_loaded(db_session):
    """(C) 釘住 ``_resync_worksheet`` 的 ``refresh(..., attribute_names=)`` 窄化。

    ``_resync_worksheet`` 只重讀被 Core UPDATE 動到的**純量欄位**。若有人以「簡化」
    為名改成整顆 ``session.refresh(ws)``（或 ``get(..., populate_existing=True)``），
    已 eager-load 的 relationship 會被一併 expire；呼叫端（wi_set 迴圈、from-module、
    import submit）下一次存取 ``ws.rows``／``ws.process_version`` 就變成 async lazy
    load → ``MissingGreenlet``。也就是把同一顆雷換個欄位重埋。

    本測試在 bump **之前**把 rows/process_version load 起來，bump 後直接存取。

    ⚠️ setup 必須照真實呼叫端的形狀來（先 ``session.get()`` 進 identity map，之後才由
    別的查詢把 relationship 載進來），這不是為了方便：SQLAlchemy 2.0 會把「載入這顆
    物件的那個 query 的 loader options」記在 ``InstanceState.load_options`` 上，整顆
    ``refresh()`` 會重放它們。若 setup 改成一開始就用帶 ``selectinload`` 的 select 載入，
    整顆 refresh 會把 eager loader 重放一遍、relationship 又變 loaded，這條測試就**驗不出來**
    （已實測）。而 ``save_worksheet``/``append_rows_from_module``/``submit_import`` 一律是
    ``await session.get(MostWorksheet, worksheet_id)`` → ``load_options`` 為空 → 沒有東西
    可重放 → 整顆 refresh 之下 relationship 就是掉。
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.orm import joinedload, selectinload

    from ddm_v2.models.v2.worksheet import MostWorksheet, WiRow
    from ddm_v2.services.v2.worksheet_revision import bump_worksheet_revision

    seeded, _rs = await _seed_ws(db_session, revision_no=1)
    ws_id = seeded.id
    db_session.add(WiRow(id=uuid.uuid4(), worksheet_id=ws_id, seq_no=1, hand="RH"))
    await db_session.commit()
    db_session.expunge_all()  # 確保下面真的走 DB，拿到乾淨的載入狀態

    ws = await db_session.get(MostWorksheet, ws_id)  # ← 真實呼叫端的入口寫法
    assert ws is not None
    same = (
        await db_session.execute(
            select(MostWorksheet)
            .where(MostWorksheet.id == ws_id)
            .options(
                selectinload(MostWorksheet.rows),
                joinedload(MostWorksheet.process_version),
            )
        )
    ).scalar_one()
    assert same is ws  # identity map：同一顆
    assert sa_inspect(ws).unloaded.isdisjoint({"rows", "process_version"}), "前置條件：兩個 relationship 必須先是 loaded"

    assert await bump_worksheet_revision(
        db_session, worksheet_id=ws_id, base_revision=1, edited_by="IEC141289"
    ) == 2

    unloaded = sa_inspect(ws).unloaded
    assert "rows" not in unloaded, (
        "bump 把已 eager-load 的 rows expire 掉了——refresh 沒有用 attribute_names= 窄化，"
        "呼叫端下次存取 ws.rows 會炸 MissingGreenlet"
    )
    assert "process_version" not in unloaded, (
        "bump 把已 eager-load 的 process_version expire 掉了（同上）"
    )

    # 真正的雷：呼叫端不做任何額外 await 就直接存取。整顆 refresh 之下這兩行 = async
    # lazy load → sqlalchemy.exc.MissingGreenlet。
    assert len(ws.rows) == 1
    assert ws.process_version.status == "draft"

    # 窄化不得以「少同步」為代價：被 UPDATE 的欄位仍必須是 DB 真值（(A) 不可回退）。
    assert int(ws.revision_no) == 2
    assert ws.last_edited_by == "IEC141289"


@pytest.mark.asyncio
async def test_bump_conflict_reports_true_current_revision(db_session):
    """衝突路徑：即使 identity map 還握著舊值，409 的 current_revision 必須是 DB 真值。"""
    from ddm_v2.services.v2.worksheet_revision import (
        WorksheetRevisionConflict,
        bump_worksheet_revision,
    )

    ws, _rs = await _seed_ws(db_session, revision_no=1)
    # 別人（另一條連線／另一個請求）先 bump 過了，這個 session 的副本仍是 1
    await db_session.execute(
        text("UPDATE most_worksheets SET revision_no = 9 WHERE id = :i"), {"i": ws.id}
    )
    assert int(ws.revision_no) == 1

    with pytest.raises(WorksheetRevisionConflict) as exc:
        await bump_worksheet_revision(
            db_session, worksheet_id=ws.id, base_revision=1, edited_by="IEC141289"
        )
    assert exc.value.detail["current_revision"] == "9"
    assert int(ws.revision_no) == 9


@pytest.mark.asyncio
async def test_set_content_hash_syncs_identity_map(db_session):
    """set_content_hash 也是 Core UPDATE：identity map 必須跟上，否則 read_worksheet 回舊 hash。"""
    from ddm_v2.services.v2.worksheet_revision import set_content_hash

    ws, _rs = await _seed_ws(db_session, revision_no=1)
    assert ws.content_hash is None

    await set_content_hash(db_session, worksheet_id=ws.id, content_hash="a" * 64)
    # 不需要任何額外 IO：拿掉 _resync_worksheet → 這裡還是 None。
    assert ws.content_hash == "a" * 64
    # 同一個 Core UPDATE 也必須真的落到 DB（繞過 identity map 直接問）。
    real = (await db_session.execute(
        text("SELECT content_hash FROM most_worksheets WHERE id = :i"), {"i": ws.id}
    )).scalar_one()
    assert real == "a" * 64


# ── 帶 base_revision 的其他 mutation 端點（P0：這些路徑原本 500）──────────────


async def _make_published_module(client, rule_set_id: str) -> str:
    """建一個 wi-template 模組並發布一版（GM 單列），回 module_id。"""
    sfx = uuid.uuid4().hex[:6]
    r = await client.post("/api/v2/motion-modules", json={
        "name_zh": f"UT-R1-模組-{sfx}",
        "category": "wi-template",
        "scope": "global",
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": rule_set_id,
        "rows": [{
            "hand": "RH",
            "frequency": 1,
            "vocab_refs": {},
            "cycle": {
                "seq": "GM",
                "rule_set_code": "MINIMOST_FACTORY_V2",
                "a0": {"reach_cm": 20},
                "g2": {"g_code": "g_grasp"},
                "a3": {"reach_cm": 25},
                "p5": {"p_base_code": "p_place_none"},
            },
        }],
    })
    assert pub.status_code == 201, pub.text
    return mid


@pytest.mark.asyncio
async def test_from_module_with_base_revision_bumps_and_conflicts(client, db_session):
    """POST /worksheets/{id}/rows/from-module 帶 base_revision：成功 → 2；重放 → 409。"""
    ws, rs = await _seed_ws(db_session, revision_no=1)
    module_id = await _make_published_module(client, str(rs.id))

    ok = await client.post(
        f"/api/v2/worksheets/{ws.id}/rows/from-module",
        json={"module_id": module_id, "base_revision": 1},
    )
    assert ok.status_code == 201, ok.text
    body = ok.json()
    assert body["revision_no"] == 2
    assert body["content_hash"]
    assert len(body["new_rows"]) == 1

    await db_session.refresh(ws)
    assert int(ws.revision_no) == 2
    assert ws.content_hash == body["content_hash"]

    stale = await client.post(
        f"/api/v2/worksheets/{ws.id}/rows/from-module",
        json={"module_id": module_id, "base_revision": 1},
    )
    assert stale.status_code == 409, stale.text
    assert _err_code(stale.json()) == "WORKSHEET_REVISION_CONFLICT"
    assert _err_detail(stale.json()).get("current_revision") == "2"

    # 衝突不得留下半套：rows 仍只有第一次那 1 列
    from ddm_v2.models.v2.worksheet import WiRow

    rows = (await db_session.execute(
        select(WiRow).where(WiRow.worksheet_id == ws.id)
    )).scalars().all()
    assert len(rows) == 1


def _import_xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    sh = wb.active
    sh.title = "Assembly"
    sh.append(["No.", "Element Description", "Average TT"])
    sh.append([1, "take out chassis", 5.9])
    sh.append([2, "stick label", 4.85])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


async def _staged_import(client) -> str:
    files = {"file": ("R1.xlsx", _import_xlsx(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    up = await client.post("/api/v2/imports/upload", files=files)
    assert up.status_code == 200, up.text
    iid = up.json()["import_id"]
    mp = await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 0,
        "column_map": {"description": 1, "seconds": 2}, "time_unit": "sec",
    })
    assert mp.status_code == 200, mp.text
    return iid


@pytest.mark.asyncio
async def test_import_submit_with_base_revision_bumps_and_conflicts(client, db_session):
    """POST /imports/{id}/submit 帶 base_revision（前端 ImportModal 實際送法）：成功 → 2；stale → 409。"""
    ws, _rs = await _seed_ws(db_session, revision_no=1)

    iid = await _staged_import(client)
    ok = await client.post(f"/api/v2/imports/{iid}/submit", json={
        "worksheet_id": str(ws.id), "base_revision": 1,
    })
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["n_rows"] == 2
    assert body["revision_no"] == 2
    assert body["content_hash"]

    await db_session.refresh(ws)
    assert int(ws.revision_no) == 2
    assert ws.content_hash == body["content_hash"]

    # 另一批匯入，拿已過期的 base_revision → 409，且不得寫入任何列
    iid2 = await _staged_import(client)
    stale = await client.post(f"/api/v2/imports/{iid2}/submit", json={
        "worksheet_id": str(ws.id), "base_revision": 1,
    })
    assert stale.status_code == 409, stale.text
    assert _err_code(stale.json()) == "WORKSHEET_REVISION_CONFLICT"
    assert _err_detail(stale.json()).get("current_revision") == "2"

    from ddm_v2.models.v2.worksheet import WiRow

    rows = (await db_session.execute(
        select(WiRow).where(WiRow.worksheet_id == ws.id)
    )).scalars().all()
    assert len(rows) == 2
