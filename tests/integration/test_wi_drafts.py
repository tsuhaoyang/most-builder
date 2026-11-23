"""工作區編輯區（ADR-038 D2／D3，W1）：真 DB＋真 app。

鎖住的事：
- 新增／列出／修改（回 pending）／刪除／確認（單列與整組）的狀態機；已寫入的草稿不能改、不能刪、不能再確認。
- 寫入工時表：只寫已確認的列、追加到表尾、TMU 由引擎以目標規則版本重算（不沿用任何預覽值）、level 留空、
  依來源標 provenance、同交易把草稿標 committed 並記寫入的列 id、版本鎖不符 → 409 且什麼都不寫。
- 只在草稿版本的工序上可以寫；viewer 一律 403。
- 修正：整份存檔不再把既有列的來源抹成 manual（imported／ai_external 保留）。
- migration v2_0051 的約束與 downgrade 拒絕條件。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid

import pytest
from sqlalchemy import select, text

from ddm_v2.models.v2.wi_draft import WiDraftRow
from ddm_v2.models.v2.worksheet import MostCycle, WiRow

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0051_wi_draft_rows.py"
    spec = importlib.util.spec_from_file_location("_v2_0051", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()

# 引擎 GM 錨（與 test_worksheet_revision_api._gm_row 相同的 cycle）
GM_CYCLE = {
    "seq": "GM",
    "a0": {"reach_cm": 20},
    "g2": {"g_code": "g_grasp"},
    "a3": {"reach_cm": 25},
    "p5": {"p_base_code": "p_place_none"},
}


def _content(**extra) -> dict:
    return {"hand": "RH", "frequency": 1, "narrative": "w1", "cycle": dict(GM_CYCLE), **extra}


async def _seed_ws(db_session, *, status: str = "draft", revision_no: int = 1):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"W1-{uuid.uuid4().hex[:6]}", name_zh="W1")
    db_session.add(site)
    await db_session.flush()
    product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"S-{uuid.uuid4().hex[:6]}", name_zh="S")
    db_session.add(sku)
    await db_session.flush()
    rs = await get_active_rule_set(db_session)
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku.id, version_no="v1", status=status, created_by="IEC141289")
    ws = MostWorksheet(
        id=uuid.uuid4(), process_version_id=pv.id, status="draft", default_rule_set_id=rs.id,
        modeling_policy_version_id=MODELING_FACTORY_V1_ID, level_policy_version_id=LEVEL_FACTORY_V1_ID,
        revision_no=revision_no,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()
    return ws, rs


async def _viewer(client) -> dict:
    emp = f"UT_W1_VIEWER_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users", json={"employee_no": emp, "display_name": emp, "roles": []})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}


async def _create(client, ws_id, items) -> list[dict]:
    r = await client.post(f"/api/v2/worksheets/{ws_id}/drafts", json={"items": items})
    assert r.status_code == 201, r.text
    return r.json()["items"]


async def _confirm(client, ws_id, **body):
    return await client.post(f"/api/v2/worksheets/{ws_id}/drafts/confirm", json=body)


async def _commit(client, ws_id, base_revision):
    return await client.post(f"/api/v2/worksheets/{ws_id}/drafts/commit", json={"base_revision": base_revision})


def _code(r) -> str | None:
    body = r.json()
    return (body.get("error") or {}).get("code")


# ═════════ 新增／列出／修改／刪除／確認 ═════════

async def test_create_and_list_keeps_order_and_groups(client, db_session):
    ws, _ = await _seed_ws(db_session)
    a = await _create(client, ws.id, [
        {"content": _content(sub_activity="拿起子"), "group_key": "wi-1", "order_in_group": 0},
        {"content": _content(sub_activity="鎖第一顆"), "group_key": "wi-1", "order_in_group": 1},
        {"content": _content(sub_activity="單獨一列")},
    ])
    assert [d["status"] for d in a] == ["pending"] * 3 and {d["source"] for d in a} == {"manual"}
    assert a[0]["group_key"] == a[1]["group_key"] == "wi-1" and a[2]["group_key"] not in {"wi-1", ""}
    assert a[0]["source_revision"] == 1 and a[0]["created_by"] == "IEC141289"
    listed = (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]
    assert [d["content"]["sub_activity"] for d in listed] == ["拿起子", "鎖第一顆", "單獨一列"]


async def test_patch_puts_a_confirmed_draft_back_to_pending(client, db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    assert (await _confirm(client, ws.id, draft_ids=[d["id"]])).json()["items"][0]["status"] == "confirmed"
    r = await client.patch(f"/api/v2/worksheet-drafts/{d['id']}", json={"content": _content(sub_activity="改過")})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending" and r.json()["confirmed_by"] is None
    assert r.json()["content"]["sub_activity"] == "改過"


async def test_confirm_a_whole_group(client, db_session):
    ws, _ = await _seed_ws(db_session)
    await _create(client, ws.id, [
        {"content": _content(), "group_key": "g", "order_in_group": 0},
        {"content": _content(), "group_key": "g", "order_in_group": 1},
        {"content": _content(), "group_key": "other"},
    ])
    r = await _confirm(client, ws.id, group_key="g")
    assert r.status_code == 200 and [d["status"] for d in r.json()["items"]] == ["confirmed", "confirmed"]
    listed = (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]
    assert [d["status"] for d in listed] == ["confirmed", "confirmed", "pending"]


async def test_confirm_requires_exactly_one_selector_and_existing_ids(client, db_session):
    ws, _ = await _seed_ws(db_session)
    assert (await _confirm(client, ws.id)).status_code == 422
    assert (await _confirm(client, ws.id, draft_ids=[str(uuid.uuid4())], group_key="g")).status_code == 422
    assert (await _confirm(client, ws.id, draft_ids=[str(uuid.uuid4())])).status_code == 404
    assert (await _confirm(client, ws.id, group_key="nope")).status_code == 404


async def test_delete_removes_a_pending_draft(client, db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    assert (await client.delete(f"/api/v2/worksheet-drafts/{d['id']}")).status_code == 204
    assert (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"] == []
    assert (await client.delete(f"/api/v2/worksheet-drafts/{d['id']}")).status_code == 404


async def test_invalid_content_is_rejected(client, db_session):
    ws, _ = await _seed_ws(db_session)
    for bad in (
        {"content": _content(hand="XX")},
        {"content": _content(frequency=0)},
        {"content": {**_content(), "unknown_field": 1}},
        {"content": {"hand": "RH"}},  # 沒有 cycle
    ):
        r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [bad]})
        assert r.status_code == 422, bad


# ═════════ 寫入工時表 ═════════

async def test_commit_appends_confirmed_rows_to_the_end_and_recomputes_tmu(client, db_session):
    ws, rs = await _seed_ws(db_session)
    existing_id = str(uuid.uuid4())
    r = await client.put(f"/api/v2/worksheets/{ws.id}", json={"base_revision": 1, "rows": [{
        "id": existing_id, "seq_no": 1, "hand": "RH", "frequency": 1, "narrative": "既有",
        "cycle": {**GM_CYCLE, "rule_set_code": rs.code}, "level": {"ascription": "main", "level": "1"},
    }]})
    assert r.status_code == 200, r.text
    expected_tmu = r.json()["rows"][0]["cycle"]["total_tmu"]

    a, b, c = await _create(client, ws.id, [
        {"content": _content(sub_activity="A", wi_group="作業一"), "group_key": "g1", "order_in_group": 0},
        {"content": _content(sub_activity="B", wi_group="作業一"), "group_key": "g1", "order_in_group": 1},
        {"content": _content(sub_activity="C 不確認")},
    ])
    await _confirm(client, ws.id, group_key="g1")

    r = await _commit(client, ws.id, base_revision=2)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["revision_no"] == 3 and [d["id"] for d in out["committed"]] == [a["id"], b["id"]]
    assert all(d["status"] == "committed" and d["committed_by"] == "IEC141289" for d in out["committed"])

    sheet = (await client.get(f"/api/v2/worksheets/{ws.id}")).json()
    assert [row["seq_no"] for row in sheet["rows"]] == [1, 2, 3]
    assert sheet["rows"][0]["wi_row_id"] == existing_id, "既有列不動"
    assert [row["sub_activity"] for row in sheet["rows"][1:]] == ["A", "B"]
    assert all(row["wi_group"] == "作業一" for row in sheet["rows"][1:])
    assert all(row["cycle"]["total_tmu"] == expected_tmu for row in sheet["rows"]), "TMU 由引擎重算"
    assert all(row["cycle"]["rule_set_id"] == str(rs.id) for row in sheet["rows"][1:])
    assert all(row["level"]["ascription"] is None and row["level"]["level"] is None for row in sheet["rows"][1:]), "level 留空"
    committed_ids = {d["committed_wi_row_id"] for d in out["committed"]}
    assert committed_ids == {row["wi_row_id"] for row in sheet["rows"][1:]}

    left = (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]
    assert [d["status"] for d in left] == ["committed", "committed", "pending"], "未確認的列留在編輯區"
    assert c["id"] in {d["id"] for d in left}


async def test_commit_uses_the_worksheet_rule_set_not_the_one_in_the_draft(client, db_session):
    ws, rs = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content(cycle={**GM_CYCLE, "rule_set_code": "SOMETHING_ELSE"})}])
    await _confirm(client, ws.id, draft_ids=[d["id"]])
    assert (await _commit(client, ws.id, base_revision=1)).status_code == 200
    cyc = (await db_session.execute(
        select(MostCycle).join(WiRow, WiRow.id == MostCycle.wi_row_id).where(WiRow.worksheet_id == ws.id)
    )).scalar_one()
    assert cyc.rule_set_id == rs.id and cyc.slot_inputs["rule_set_code"] == rs.code


async def test_commit_with_a_stale_revision_is_409_and_writes_nothing(client, db_session):
    ws, _ = await _seed_ws(db_session, revision_no=5)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    await _confirm(client, ws.id, draft_ids=[d["id"]])
    r = await _commit(client, ws.id, base_revision=4)
    assert r.status_code == 409, r.text
    assert (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalars().all() == []
    left = (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]
    assert left[0]["status"] == "confirmed", "草稿維持已確認，重新載入後可再寫入"
    assert (await _commit(client, ws.id, base_revision=5)).status_code == 200


async def test_commit_without_confirmed_drafts_is_422(client, db_session):
    ws, _ = await _seed_ws(db_session)
    await _create(client, ws.id, [{"content": _content()}])
    r = await _commit(client, ws.id, base_revision=1)
    assert r.status_code == 422 and _code(r) == "VALIDATION_ERROR"


async def test_commit_requires_base_revision(client, db_session):
    ws, _ = await _seed_ws(db_session)
    assert (await client.post(f"/api/v2/worksheets/{ws.id}/drafts/commit", json={})).status_code == 422


async def test_an_engine_error_rolls_back_the_whole_commit(client, db_session):
    ws, _ = await _seed_ws(db_session)
    bad = _content(cycle={"seq": "CM", "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 999}]}})
    ok, broken = await _create(client, ws.id, [{"content": _content()}, {"content": bad}])
    await _confirm(client, ws.id, draft_ids=[ok["id"], broken["id"]])
    r = await _commit(client, ws.id, base_revision=1)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["detail"]["draft_id"] == broken["id"], "錯誤指得出是哪一個草稿"
    assert r.json()["error"]["detail"]["code"] != "VALIDATION_ERROR", "引擎的錯誤碼原樣帶出"
    assert (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalars().all() == []
    left = (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]
    assert {d["status"] for d in left} == {"confirmed"} and all(d["committed_wi_row_id"] is None for d in left)


async def _backend_draft(db_session, ws_id, source: str):
    from ddm_v2.schemas.v2.wi_draft import WiDraftContent, WiDraftCreateItem
    from ddm_v2.services.v2 import wi_draft_service as svc

    (d,) = await svc.add_drafts(
        db_session, ws_id, [WiDraftCreateItem(content=WiDraftContent.model_validate(_content()))],
        source=source, actor="IEC141289",
    )
    await db_session.commit()
    return d


@pytest.mark.parametrize(("source", "provenance"), [("rule_based", "manual"), ("manual", "manual")])
async def test_provenance_follows_the_draft_source(client, db_session, source, provenance):
    ws, _ = await _seed_ws(db_session)
    d = await _backend_draft(db_session, ws.id, source)
    await _confirm(client, ws.id, draft_ids=[str(d.id)])
    assert (await _commit(client, ws.id, base_revision=1)).status_code == 200
    row = (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalar_one()
    assert row.provenance == provenance


async def test_external_ai_drafts_cannot_be_committed_before_w3(client, db_session):
    """Fail-Fast：AI 草稿還要過 engine_gate（ADR-037 D3），寫入路徑 W3 才補；在那之前一列都不寫。"""
    ws, _ = await _seed_ws(db_session)
    (manual,) = await _create(client, ws.id, [{"content": _content()}])
    ai = await _backend_draft(db_session, ws.id, "ai_service")
    await _confirm(client, ws.id, draft_ids=[manual["id"], str(ai.id)])
    r = await _commit(client, ws.id, base_revision=1)
    assert r.status_code == 409 and r.json()["error"]["detail"]["field"] == "source"
    assert (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalars().all() == []


# ═════════ 已寫入的草稿是紀錄 ═════════

async def test_committed_drafts_cannot_be_patched_deleted_or_reconfirmed(client, db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    await _confirm(client, ws.id, draft_ids=[d["id"]])
    assert (await _commit(client, ws.id, base_revision=1)).status_code == 200
    assert (await client.patch(f"/api/v2/worksheet-drafts/{d['id']}", json={"content": _content()})).status_code == 409
    assert (await client.delete(f"/api/v2/worksheet-drafts/{d['id']}")).status_code == 409
    assert (await _confirm(client, ws.id, draft_ids=[d["id"]])).status_code == 409
    r = await _commit(client, ws.id, base_revision=2)
    assert r.status_code == 422, "已寫入的不會被寫第二次"


# ═════════ 權限與版本狀態 ═════════

async def test_frozen_process_version_rejects_every_write(client, db_session):
    ws, _ = await _seed_ws(db_session, status="approved")
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [{"content": _content()}]})
    assert r.status_code == 409 and _code(r) == "CONFLICT"
    assert (await _commit(client, ws.id, base_revision=1)).status_code == 409
    assert (await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).status_code == 200, "讀取不限"


async def test_viewers_are_refused_on_every_endpoint(client, db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    h = await _viewer(client)
    calls = [
        client.get(f"/api/v2/worksheets/{ws.id}/drafts", headers=h),
        client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [{"content": _content()}]}, headers=h),
        client.patch(f"/api/v2/worksheet-drafts/{d['id']}", json={"content": _content()}, headers=h),
        client.delete(f"/api/v2/worksheet-drafts/{d['id']}", headers=h),
        client.post(f"/api/v2/worksheets/{ws.id}/drafts/confirm", json={"draft_ids": [d["id"]]}, headers=h),
        client.post(f"/api/v2/worksheets/{ws.id}/drafts/commit", json={"base_revision": 1}, headers=h),
    ]
    for call in calls:
        assert (await call).status_code == 403


async def test_unknown_worksheet_is_404(client):
    ghost = uuid.uuid4()
    assert (await client.get(f"/api/v2/worksheets/{ghost}/drafts")).status_code == 404
    assert (await _commit(client, ghost, base_revision=1)).status_code == 404


async def test_deleting_the_worksheet_deletes_its_drafts(client, db_session):
    ws, _ = await _seed_ws(db_session)
    await _create(client, ws.id, [{"content": _content()}])
    await db_session.execute(text("DELETE FROM most_worksheets WHERE id = :i"), {"i": ws.id})
    n = (await db_session.execute(select(WiDraftRow).where(WiDraftRow.worksheet_id == ws.id))).scalars().all()
    assert n == []


# ═════════ 修正：整份存檔不再抹掉來源 ═════════

async def test_a_full_save_keeps_the_origin_of_existing_rows(client, db_session):
    ws, rs = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    await _confirm(client, ws.id, draft_ids=[d["id"]])
    assert (await _commit(client, ws.id, base_revision=1)).status_code == 200
    sheet = (await client.get(f"/api/v2/worksheets/{ws.id}")).json()
    ai_row_id = sheet["rows"][0]["wi_row_id"]
    await db_session.execute(text("UPDATE wi_rows SET provenance='ai_external' WHERE id=:i"), {"i": ai_row_id})
    await db_session.commit()
    new_id = str(uuid.uuid4())
    rows = [
        {"id": ai_row_id, "seq_no": 1, "hand": "RH", "frequency": 1, "cycle": {**GM_CYCLE, "rule_set_code": rs.code}},
        {"id": new_id, "seq_no": 2, "hand": "LH", "frequency": 1, "cycle": {**GM_CYCLE, "rule_set_code": rs.code}},
    ]
    assert (await client.put(f"/api/v2/worksheets/{ws.id}", json={"base_revision": 2, "rows": rows})).status_code == 200
    prov = dict((await db_session.execute(
        select(WiRow.id, WiRow.provenance).where(WiRow.worksheet_id == ws.id)
    )).all())
    assert prov[uuid.UUID(ai_row_id)] == "ai_external", "沿用 id 的列保留來源"
    assert prov[uuid.UUID(new_id)] == "manual"


async def test_a_full_save_keeps_the_import_link_of_imported_rows(client, db_session):
    ws, rs = await _seed_ws(db_session)
    imp = uuid.uuid4()
    await db_session.execute(text(
        "INSERT INTO excel_imports (id, source_name, status, raw_payload, imported_by) "
        "VALUES (:i, 'w1.xlsx', 'mapped', '{}'::jsonb, 't')"), {"i": imp})
    rid = str(uuid.uuid4())
    assert (await client.put(f"/api/v2/worksheets/{ws.id}", json={"base_revision": 1, "rows": [
        {"id": rid, "seq_no": 1, "hand": "RH", "frequency": 1, "cycle": {**GM_CYCLE, "rule_set_code": rs.code}},
    ]})).status_code == 200
    await db_session.execute(text(
        "UPDATE wi_rows SET provenance='imported', source_import_id=:imp WHERE id=:i"), {"imp": imp, "i": rid})
    await db_session.commit()
    assert (await client.put(f"/api/v2/worksheets/{ws.id}", json={"base_revision": 2, "rows": [
        {"id": rid, "seq_no": 1, "hand": "RH", "frequency": 2, "cycle": {**GM_CYCLE, "rule_set_code": rs.code}},
    ]})).status_code == 200
    row = (await db_session.execute(select(WiRow).where(WiRow.id == uuid.UUID(rid)))).scalar_one()
    assert (row.provenance, row.source_import_id, float(row.frequency)) == ("imported", imp, 2.0)


# ═════════ migration v2_0051 ═════════

async def test_provenance_check_has_exactly_one_constraint_and_accepts_ai_external(db_session):
    rows = (await db_session.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid = 'wi_rows'::regclass AND conname LIKE '%provenance%'"
    ))).scalars().all()
    assert rows == ["ck_wi_rows_provenance"], "舊的雙前綴約束若還在，會把 ai_external 擋掉"


async def test_draft_state_constraints_hold_at_the_database(db_session):
    from sqlalchemy.exc import IntegrityError

    ws, _ = await _seed_ws(db_session)
    with pytest.raises(IntegrityError):
        await db_session.execute(text(
            "INSERT INTO wi_draft_rows (id, worksheet_id, group_key, sort_order, source, status, content, created_by) "
            "VALUES (gen_random_uuid(), :w, 'g', 1, 'manual', 'committed', '{}'::jsonb, 't')"), {"w": ws.id})
    await db_session.rollback()


async def test_downgrade_check_sql_counts_drafts_and_ai_external_rows(client, db_session):
    base_d = (await db_session.execute(text(MIG.SQL_COUNT_DRAFTS))).scalar_one()
    base_a = (await db_session.execute(text(MIG.SQL_COUNT_AI_EXTERNAL_ROWS))).scalar_one()
    ws, _ = await _seed_ws(db_session)
    (d,) = await _create(client, ws.id, [{"content": _content()}])
    await _confirm(client, ws.id, draft_ids=[d["id"]])
    await _commit(client, ws.id, base_revision=1)
    await db_session.execute(text("UPDATE wi_rows SET provenance='ai_external' WHERE worksheet_id=:w"), {"w": ws.id})
    await db_session.commit()
    assert (await db_session.execute(text(MIG.SQL_COUNT_DRAFTS))).scalar_one() == base_d + 1
    assert (await db_session.execute(text(MIG.SQL_COUNT_AI_EXTERNAL_ROWS))).scalar_one() == base_a + 1


# ═════════ 審查後補強 ═════════

@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
async def test_non_finite_numbers_are_rejected(client, db_session, value):
    ws, _ = await _seed_ws(db_session)
    raw = (
        '{"items":[{"content":{"hand":"RH","cycle":{"seq":"GM","a0":{"reach_cm":%s},'
        '"g2":{"g_code":"g_grasp"},"a3":{"reach_cm":25},"p5":{"p_base_code":"p_place_none"}}}}]}' % value
    )
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", content=raw,
                          headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text


async def test_oversized_content_is_rejected(client, db_session):
    ws, _ = await _seed_ws(db_session)
    huge = _content(cycle={**GM_CYCLE, "g2": {"g_code": "g_grasp", "modifiers": {f"k{i}": "x" * 50 for i in range(400)}}})
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [{"content": huge}]})
    assert r.status_code == 422


async def test_the_per_worksheet_draft_cap_is_enforced(client, db_session, monkeypatch):
    from ddm_v2.services.v2 import wi_draft_service as svc

    monkeypatch.setattr(svc, "MAX_DRAFTS_PER_WORKSHEET", 3)
    ws, _ = await _seed_ws(db_session)
    await _create(client, ws.id, [{"content": _content()}, {"content": _content()}])
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [{"content": _content()}] * 2})
    assert r.status_code == 422 and r.json()["error"]["detail"]["max"] == 3
    assert len((await client.get(f"/api/v2/worksheets/{ws.id}/drafts")).json()["items"]) == 2


async def test_a_stale_commit_with_nothing_confirmed_is_still_a_revision_conflict(client, db_session):
    """版本鎖先檢查：兩個人同時按寫入，第二個拿到 409（重新載入），不是「沒有可寫入的列」。"""
    ws, _ = await _seed_ws(db_session, revision_no=3)
    r = await _commit(client, ws.id, base_revision=2)
    assert r.status_code == 409
    r = await _commit(client, ws.id, base_revision=3)
    assert r.status_code == 422, "版本對、但沒有已確認的列"
    from ddm_v2.models.v2.worksheet import MostWorksheet
    await db_session.refresh(ws)
    assert (await db_session.get(MostWorksheet, ws.id)).revision_no == 3, "失敗的寫入不會讓版本號增加"


async def test_the_edit_area_is_shared_between_analysts(client, db_session):
    """Howard 2026-11-23：編輯區共用；任一 analyst 可改、確認、寫入別人建的草稿，各欄位記下是誰。"""
    ws, _ = await _seed_ws(db_session)
    a = await _analyst(client, "analyst")
    b = await _analyst(client, "approver")
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts", json={"items": [
        {"content": _content()}, {"content": _content()}]}, headers=a)
    first, second = r.json()["items"]
    r = await client.patch(f"/api/v2/worksheet-drafts/{first['id']}", json={"content": _content(sub_activity="B 改")}, headers=b)
    assert r.status_code == 200 and r.json()["created_by"] == a["X-Username"] and r.json()["updated_by"] == b["X-Username"]
    assert (await client.delete(f"/api/v2/worksheet-drafts/{second['id']}", headers=b)).status_code == 204
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/confirm", json={"draft_ids": [first["id"]]}, headers=a)
    assert r.json()["items"][0]["confirmed_by"] == a["X-Username"]
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/commit", json={"base_revision": 1}, headers=b)
    assert r.status_code == 200 and r.json()["committed"][0]["committed_by"] == b["X-Username"]


async def _analyst(client, role: str) -> dict:
    emp = f"UT_W1_{role.upper()}_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users", json={"employee_no": emp, "display_name": emp, "roles": [role]})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}
