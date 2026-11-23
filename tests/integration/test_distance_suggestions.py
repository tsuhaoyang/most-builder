"""距離建議、套用與距離設定（ADR-038 D5.6 修訂，W7b）：真 DB＋真 app；區域座標直接寫進 DB（等同同步過），不需要 DSX。

鎖住的事：
- 計算：a0＝人→從哪裡（沒有 from 用 object）、a3／m3＝從→到、a6＝到→人；人＝站位＋人端偏移；門檻內 reach、
  超過 foot；a6 超過門檻、m3 超過 75 cm 需 IE 裁決；沒歸區或區域沒同步 → 算不出來並給原因；記錄快照、出處、門檻。
- 套用：只套全部格位都是 suggested 的列，否則 409 DISTANCE_NOT_APPLICABLE；重算結果和存著的不同 → 409
  DISTANCE_SUGGESTION_CHANGED；成功時走整份存檔，cycle 寫入距離、距離狀態 confirmed、TMU 由引擎重算、revision +1；
  revision 不符 409。
- 已 confirmed 的列，之後整份存檔改了從哪裡／到哪裡或距離欄位 → 退回未標示；沒改的維持 confirmed；manual 不動。
- 原樣重組整份存檔（套用用的）不改內容雜湊。
- 距離設定：預設 70 cm／肩高 140 cm；admin 發布新版本後，新工時表用新版本、既有工時表不變。
- 權限、只在草稿版本可算與套用、migration 約束與 downgrade 計數。
"""
from __future__ import annotations

import importlib.util
import pathlib
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0055_distance_suggestions.py"
    spec = importlib.util.spec_from_file_location("_v2_0055", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


class Station:
    """一個 SKU、一份草稿工時表、三個區域（座標已同步）與歸區好的物件。"""

    async def build(self, db_session, *, status: str = "draft"):
        from ddm_v2.models.v2.org import Product, Site, Sku
        from ddm_v2.models.v2.vocab import WorkVocabItem
        from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
        from ddm_v2.models.v2.zone import SkuObjectZone, SkuPlacementSnapshot, SkuZone, ZoneCategory
        from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
        from ddm_v2.services.v2.rule_set_service import get_active_rule_set

        site = Site(id=uuid.uuid4(), external_code=f"W7B-{uuid.uuid4().hex[:6]}", name_zh="W7B")
        db_session.add(site)
        await db_session.flush()
        product = Product(id=uuid.uuid4(), site_id=site.id, name_zh="P")
        db_session.add(product)
        await db_session.flush()
        self.sku = Sku(id=uuid.uuid4(), product_id=product.id, sku_code=f"S-{uuid.uuid4().hex[:6]}", name_zh="S")
        db_session.add(self.sku)
        await db_session.flush()
        self.rs = await get_active_rule_set(db_session)
        pv = ProcessVersion(id=uuid.uuid4(), sku_id=self.sku.id, version_no="v1", status=status, created_by="IEC141289")
        self.ws = MostWorksheet(
            id=uuid.uuid4(), process_version_id=pv.id, status="draft", default_rule_set_id=self.rs.id,
            modeling_policy_version_id=MODELING_FACTORY_V1_ID, level_policy_version_id=LEVEL_FACTORY_V1_ID,
            revision_no=1,
        )
        db_session.add_all([pv, self.ws])
        await db_session.flush()
        self.snap = SkuPlacementSnapshot(
            id=uuid.uuid4(), sku_id=self.sku.id, dsx_station_id="st", placement_revision=1, placement_count=3,
            placements=[{"object_id": "bin", "x": 0, "y": 40, "z": 110, "point_source": "anchor"},
                        {"object_id": "fixture", "x": 0, "y": 20, "z": 100, "point_source": "anchor"},
                        {"object_id": "cart", "x": 0, "y": 150, "z": 100, "point_source": "station_local"}],
            synced_by="t",
        )
        db_session.add(self.snap)
        await db_session.flush()
        cat = (await db_session.execute(select(ZoneCategory).where(ZoneCategory.code == "incoming"))).scalar_one()

        def zone(name, obj, xyz):
            return SkuZone(id=uuid.uuid4(), sku_id=self.sku.id, category_id=cat.id, name=name, dsx_object_id=obj,
                           center_x=Decimal(str(xyz[0])), center_y=Decimal(str(xyz[1])), center_z=Decimal(str(xyz[2])),
                           center_snapshot_id=self.snap.id, created_by="t")

        self.z_bin = zone("料盒", "bin", (0, 40, 110))
        self.z_fixture = zone("治具", "fixture", (0, 20, 100))
        self.z_cart = zone("料車", "cart", (0, 150, 100))
        self.z_unsynced = SkuZone(id=uuid.uuid4(), sku_id=self.sku.id, category_id=cat.id, name="沒同步", created_by="t")
        db_session.add_all([self.z_bin, self.z_fixture, self.z_cart, self.z_unsynced])
        await db_session.flush()

        def vocab(kind, name):
            return WorkVocabItem(id=uuid.uuid4(), kind=kind, name_zh=f"{name}{uuid.uuid4().hex[:4]}")

        self.v_bin, self.v_fixture, self.v_cart = vocab("from", "料盒"), vocab("to", "治具"), vocab("to", "料車")
        self.v_part, self.v_loose, self.v_unsynced = vocab("object", "零件"), vocab("to", "沒歸區"), vocab("to", "沒同步")
        db_session.add_all([self.v_bin, self.v_fixture, self.v_cart, self.v_part, self.v_loose, self.v_unsynced])
        await db_session.flush()
        for v, z in ((self.v_bin, self.z_bin), (self.v_fixture, self.z_fixture), (self.v_cart, self.z_cart),
                     (self.v_part, self.z_bin), (self.v_unsynced, self.z_unsynced)):
            db_session.add(SkuObjectZone(sku_id=self.sku.id, vocab_item_id=v.id, zone_id=z.id, assigned_by="t"))
        await db_session.commit()
        return self

    def gm(self, seq, *, frm=None, to=None, obj=None, **extra) -> dict:
        return {
            "id": str(uuid.uuid4()), "seq_no": seq, "hand": "RH", "frequency": 1, "narrative": f"r{seq}",
            "from_vocab_id": str(frm.id) if frm else None, "to_vocab_id": str(to.id) if to else None,
            "object_vocab_id": str(obj.id) if obj else None,
            "cycle": {"seq": "GM", "rule_set_code": self.rs.code, "a0": {"reach_cm": 5}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 5}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": str(seq)}, **extra,
        }

    def cm(self, seq, *, frm, to) -> dict:
        r = self.gm(seq, frm=frm, to=to)
        r["cycle"] = {"seq": "CM", "rule_set_code": self.rs.code, "a0": {"reach_cm": 5}, "g2": {"g_code": "g_grasp"},
                      "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 5}]}}
        return r


async def _save(client, ws_id, rows, base_revision):
    r = await client.put(f"/api/v2/worksheets/{ws_id}", json={"rows": rows, "base_revision": base_revision})
    assert r.status_code == 200, r.text
    return r.json()


async def _compute(client, ws_id) -> dict[tuple[str, str], dict]:
    r = await client.post(f"/api/v2/worksheets/{ws_id}/distance-suggestions/compute")
    assert r.status_code == 200, r.text
    return {(s["wi_row_id"], s["slot"]): s for s in r.json()["items"]}


async def _seen(client, ws_id) -> str:
    """使用者看到的那一次計算（建議的 computed_at）。"""
    items = (await client.get(f"/api/v2/worksheets/{ws_id}/distance-suggestions")).json()["items"]
    (at,) = {x["computed_at"] for x in items}
    return at


async def _apply(client, ws_id, row_ids, base_revision, computed_at=None):
    return await client.post(f"/api/v2/worksheets/{ws_id}/distance-suggestions/apply", json={
        "base_revision": base_revision, "wi_row_ids": row_ids,
        "computed_at": computed_at or await _seen(client, ws_id)})


def _err(r) -> dict:
    return r.json()["error"]


async def _user(client, role: str | None) -> dict:
    emp = f"UT_W7B_{(role or 'viewer').upper()}_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users",
                          json={"employee_no": emp, "display_name": emp, "roles": [role] if role else []})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}


# ═════════ 計算 ═════════

async def test_compute_endpoints_fields_and_provenance(client, db_session):
    st = await Station().build(db_session)
    near = st.gm(1, frm=st.v_bin, to=st.v_fixture)        # 人→料盒 50；料盒→治具 22.4；治具→人 44.7
    far = st.gm(2, frm=st.v_bin, to=st.v_cart)            # 料盒→料車 110.5 → foot；料車→人 158.1 → a6 需 IE
    by_obj = st.gm(3, obj=st.v_part, to=st.v_fixture)     # 沒有 from → a0 用 object（也在料盒）
    loose = st.gm(4, frm=st.v_bin, to=st.v_loose)         # 到哪裡沒歸區
    unsynced = st.gm(5, frm=st.v_bin, to=st.v_unsynced)   # 區域沒同步
    cm = st.cm(6, frm=st.v_bin, to=st.v_fixture)
    await _save(client, st.ws.id, [near, far, by_obj, loose, unsynced, cm], 1)
    s = await _compute(client, st.ws.id)

    a0 = s[(near["id"], "a0")]
    assert (a0["status"], a0["field"], a0["distance_cm"]) == ("suggested", "reach_cm", 50.0)
    assert a0["endpoints"]["from"]["source"] == "person_offset"
    assert a0["endpoints"]["to"]["source"] == "zone_center" and a0["endpoints"]["to"]["point_source"] == "anchor"
    assert a0["endpoints"]["to"]["zone_id"] == str(st.z_bin.id)
    assert a0["snapshot_id"] == str(st.snap.id) and a0["threshold_cm"] == 70.0
    assert a0["person_offset_cm"] == [0.0, 0.0, 140.0]
    assert s[(near["id"], "a3")]["distance_cm"] == 22.4 and s[(near["id"], "a6")]["distance_cm"] == 44.7

    assert (s[(far["id"], "a3")]["field"], s[(far["id"], "a3")]["distance_cm"]) == ("foot_cm", 110.5)
    assert (s[(far["id"], "a6")]["status"], s[(far["id"], "a6")]["reason"]) == ("needs_ie", "a6_over_threshold")

    assert s[(by_obj["id"], "a0")]["endpoints"]["to"]["role"] == "object"
    assert s[(by_obj["id"], "a0")]["distance_cm"] == 50.0

    assert (s[(loose["id"], "a3")]["status"], s[(loose["id"], "a3")]["reason"]) == ("unavailable", "not_assigned")
    assert s[(unsynced["id"], "a6")]["reason"] == "zone_not_synced"

    assert (s[(cm["id"], "m3")]["field"], s[(cm["id"], "m3")]["distance_cm"]) == ("distance_cm", 22.4)
    assert (cm["id"], "a3") not in s

    listed = (await client.get(f"/api/v2/worksheets/{st.ws.id}/distance-suggestions")).json()["items"]
    assert len(listed) == 18


# ═════════ 套用 ═════════

async def test_apply_writes_distances_confirms_and_recomputes_tmu(client, db_session):
    st = await Station().build(db_session)
    near, cm, far = st.gm(1, frm=st.v_bin, to=st.v_fixture), st.cm(2, frm=st.v_bin, to=st.v_fixture), \
        st.gm(3, frm=st.v_bin, to=st.v_cart)
    saved = await _save(client, st.ws.id, [near, cm, far], 1)
    await _compute(client, st.ws.id)

    r = await _apply(client, st.ws.id, [near["id"], far["id"]], saved["revision_no"])
    assert r.status_code == 409 and _err(r)["code"] == "DISTANCE_NOT_APPLICABLE", r.text
    assert _err(r)["detail"]["rows"] == [{"wi_row_id": far["id"], "reason": "a6_over_threshold"}]

    r = await _apply(client, st.ws.id, [near["id"], cm["id"]], saved["revision_no"] + 5)
    assert r.status_code == 409 and _err(r)["code"] == "WORKSHEET_REVISION_CONFLICT", r.text

    r = await _apply(client, st.ws.id, [near["id"], cm["id"]], saved["revision_no"])
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["revision_no"] == saved["revision_no"] + 1
    rows = {x["wi_row_id"]: x for x in out["rows"]}
    assert rows[near["id"]]["distance_status"] == "confirmed" and rows[far["id"]]["distance_status"] is None
    si = rows[near["id"]]["cycle"]["slot_inputs"]
    assert si["a0"]["reach_cm"] == 50.0 and si["a3"]["reach_cm"] == 22.4 and si["a6"]["reach_cm"] == 44.7
    assert rows[cm["id"]]["cycle"]["slot_inputs"]["m3"]["m_components"][0]["distance_cm"] == 22.4
    assert rows[near["id"]]["cycle"]["total_tmu"] != saved["rows"][0]["cycle"]["total_tmu"], "TMU 由引擎重算"
    applied = (await client.get(f"/api/v2/worksheets/{st.ws.id}/distance-suggestions")).json()["items"]
    assert {x["applied_by"] is not None for x in applied if x["wi_row_id"] == near["id"]} == {True}


async def test_apply_refuses_when_inputs_changed_since_compute(client, db_session):
    st = await Station().build(db_session)
    near = st.gm(1, frm=st.v_bin, to=st.v_fixture)
    saved = await _save(client, st.ws.id, [near], 1)
    await _compute(client, st.ws.id)
    await db_session.execute(text("UPDATE sku_zones SET center_y = 45 WHERE id = :i"), {"i": st.z_bin.id})
    await db_session.commit()
    r = await _apply(client, st.ws.id, [near["id"]], saved["revision_no"])
    assert r.status_code == 409 and _err(r)["code"] == "DISTANCE_SUGGESTION_CHANGED", r.text
    assert _err(r)["detail"]["wi_row_ids"] == [near["id"]]
    await _compute(client, st.ws.id)
    assert (await _apply(client, st.ws.id, [near["id"]], saved["revision_no"])).status_code == 200


async def test_confirmed_resets_when_distance_inputs_change(client, db_session):
    st = await Station().build(db_session)
    a, b, c = st.gm(1, frm=st.v_bin, to=st.v_fixture), st.gm(2, frm=st.v_bin, to=st.v_fixture), \
        st.gm(3, frm=st.v_bin, to=st.v_fixture, distance_status="manual")
    saved = await _save(client, st.ws.id, [a, b, c], 1)
    await _compute(client, st.ws.id)
    out = (await _apply(client, st.ws.id, [a["id"], b["id"]], saved["revision_no"])).json()
    rows = {x["wi_row_id"]: x for x in out["rows"]}

    def resend(rid, **changes):
        x = rows[rid]
        body = {"id": rid, "seq_no": x["seq_no"], "hand": x["hand"], "frequency": x["frequency"],
                "narrative": x["cycle"]["narrative"], "from_vocab_id": x["from_vocab_id"],
                "to_vocab_id": x["to_vocab_id"], "object_vocab_id": x["object_vocab_id"],
                "cycle": dict(x["cycle"]["slot_inputs"]), "level": {"ascription": "main", "level": str(x["seq_no"])}}
        body.update(changes)
        return body

    changed_cycle = dict(rows[c["id"]]["cycle"]["slot_inputs"], a0={"reach_cm": 30})
    after = await _save(client, st.ws.id, [
        resend(a["id"]),                                   # 沒改 → 維持 confirmed
        resend(b["id"], to_vocab_id=str(st.v_cart.id)),    # 改了到哪裡 → 退回
        resend(c["id"], cycle=changed_cycle),              # manual 改了距離 → 仍是 manual
    ], out["revision_no"])
    status = {x["wi_row_id"]: x["distance_status"] for x in after["rows"]}
    assert status == {a["id"]: "confirmed", b["id"]: None, c["id"]: "manual"}


async def test_rebuilt_save_payload_round_trips(client, db_session):
    from ddm_v2.services.v2 import distance_service
    from ddm_v2.services.v2.worksheet_service import save_worksheet

    st = await Station().build(db_session)
    saved = await _save(client, st.ws.id, [st.gm(1, frm=st.v_bin, to=st.v_fixture), st.cm(2, frm=st.v_bin, to=st.v_cart)], 1)
    payload = await distance_service.save_payload_from_db(db_session, st.ws.id)
    out = await save_worksheet(db_session, st.ws.id, payload.model_copy(update={"base_revision": saved["revision_no"]}),
                               edited_by="IEC141289")
    await db_session.commit()
    assert out["content_hash"] == saved["content_hash"], "原樣重組再存，內容不變"


async def test_only_draft_versions_and_roles(client, db_session):
    st = await Station().build(db_session, status="approved")
    r = await client.post(f"/api/v2/worksheets/{st.ws.id}/distance-suggestions/compute")
    assert r.status_code == 409, r.text
    st2 = await Station().build(db_session)
    viewer, analyst = await _user(client, None), await _user(client, "analyst")
    url = f"/api/v2/worksheets/{st2.ws.id}/distance-suggestions"
    assert (await client.get(url, headers=viewer)).status_code == 200
    assert (await client.post(f"{url}/compute", headers=viewer)).status_code == 403
    assert (await client.post(f"{url}/apply", json={"base_revision": 1, "wi_row_ids": [str(uuid.uuid4())]},
                              headers=viewer)).status_code == 403
    assert (await client.post(f"{url}/compute", headers=analyst)).status_code == 200
    body = {"reach_foot_threshold_cm": 60, "person_offset_cm": [0, 0, 130]}
    assert (await client.post("/api/v2/modeling-policy/distance-settings", json=body, headers=analyst)).status_code == 403
    assert (await client.get(f"/api/v2/worksheets/{uuid.uuid4()}/distance-suggestions")).status_code == 404


# ═════════ 距離設定 ═════════

async def test_publishing_settings_affects_new_worksheets_only(client, db_session):
    from ddm_v2.models.v2.distance import ModelingPolicyDefault
    from ddm_v2.services.v2.policy_service import MODELING_FACTORY_CODE, MODELING_FACTORY_V1_ID

    st = await Station().build(db_session)
    near = st.gm(1, frm=st.v_bin, to=st.v_fixture)
    await _save(client, st.ws.id, [near], 1)
    before = (await client.get("/api/v2/modeling-policy/distance-settings")).json()
    assert before["source"] in {"default", "policy"}
    try:
        r = await client.post("/api/v2/modeling-policy/distance-settings",
                              json={"reach_foot_threshold_cm": 40, "person_offset_cm": [0, 0, 120]})
        assert r.status_code == 201, r.text
        now = r.json()
        assert (now["reach_foot_threshold_cm"], now["person_offset_cm"], now["source"]) == (40.0, [0.0, 0.0, 120.0], "policy")
        assert now["version_no"] > before["version_no"]
        # 既有工時表記住 V1：門檻仍 70，a0＝50 仍是 reach
        a0 = (await _compute(client, st.ws.id))[(near["id"], "a0")]
        assert (a0["threshold_cm"], a0["field"]) == (70.0, "reach_cm")
        # 新建工時表用新版本
        from ddm_v2.services.v2.policy_service import get_default_modeling_policy

        assert (await get_default_modeling_policy(db_session)).id == uuid.UUID(now["modeling_policy_version_id"])
        bad = {"reach_foot_threshold_cm": 0, "person_offset_cm": [0, 0, 120]}
        assert (await client.post("/api/v2/modeling-policy/distance-settings", json=bad)).status_code == 422
        for bad in ({"reach_foot_threshold_cm": 70, "person_offset_cm": [0, 0]},
                    {"reach_foot_threshold_cm": 70.55, "person_offset_cm": [0, 0, 140]}):
            assert (await client.post("/api/v2/modeling-policy/distance-settings", json=bad)).status_code == 422
    finally:
        # 還原預設，別影響其他測試建立的工時表
        pinned = await db_session.get(ModelingPolicyDefault, MODELING_FACTORY_CODE)
        pinned.version_id = MODELING_FACTORY_V1_ID
        await db_session.commit()


# ═════════ migration ═════════

async def test_migration_constraints_and_downgrade_count(client, db_session):
    st = await Station().build(db_session)
    near = st.gm(1, frm=st.v_bin, to=st.v_fixture)
    await _save(client, st.ws.id, [near], 1)
    await _compute(client, st.ws.id)
    with pytest.raises(Exception, match="ck_wi_row_distance_suggestions_suggested_has_value"):
        await db_session.execute(text(
            "UPDATE wi_row_distance_suggestions SET field = NULL WHERE wi_row_id = :i AND status = 'suggested'"),
            {"i": near["id"]})
    await db_session.rollback()
    names = set((await db_session.execute(text(
        "SELECT conname FROM pg_constraint WHERE conrelid::regclass::text IN "
        "('zone_categories','sku_zones','sku_object_zones','wi_row_distance_suggestions')"))).scalars())
    assert {"ck_zone_categories_code_format", "ck_sku_zones_center_complete", "ck_sku_object_zones_object_complete",
            "ck_wi_row_distance_suggestions_slot"} <= names, "約束名與 ORM 一致（v2_0055 修正 v2_0054）"
    n = (await db_session.execute(text(MIG.SQL_COUNT_BLOCKERS), {"v1": MIG.MODELING_FACTORY_V1_ID})).scalar_one()
    assert n >= 1


async def test_apply_refuses_values_the_user_has_not_seen(client, db_session):
    """甲看到建議後，有人重新算過（座標也改了）：甲用舊的 computed_at 套用 → 409，不套用沒看過的值。"""
    st = await Station().build(db_session)
    near = st.gm(1, frm=st.v_bin, to=st.v_fixture)
    saved = await _save(client, st.ws.id, [near], 1)
    await _compute(client, st.ws.id)
    seen = await _seen(client, st.ws.id)
    await db_session.execute(text("UPDATE sku_zones SET center_y = 45 WHERE id = :i"), {"i": st.z_bin.id})
    await db_session.commit()
    await _compute(client, st.ws.id)
    r = await _apply(client, st.ws.id, [near["id"]], saved["revision_no"], computed_at=seen)
    assert r.status_code == 409 and _err(r)["code"] == "DISTANCE_SUGGESTION_CHANGED", r.text


async def test_apply_blocks_uncomputed_and_not_applicable_rows(client, db_session):
    st = await Station().build(db_session)
    a, b = st.gm(1, frm=st.v_bin, to=st.v_fixture), st.gm(2, frm=st.v_bin, to=st.v_fixture, distance_status="not_applicable")
    saved = await _save(client, st.ws.id, [a, b], 1)
    await _compute(client, st.ws.id)
    r = await _apply(client, st.ws.id, [b["id"], str(uuid.uuid4())], saved["revision_no"])
    assert r.status_code == 409, r.text
    reasons = {x["reason"] for x in _err(r)["detail"]["rows"]}
    assert reasons == {"marked_not_applicable", "no_suggestion"}


async def test_full_field_round_trip_and_non_target_rows_untouched(client, db_session):
    """套用會重寫整份表：SIMO、level、LB 標記、wi_group、來源、非目標列的 TMU 與距離狀態都要原樣保留。"""
    from ddm_v2.models.v2.worksheet import WiRow

    st = await Station().build(db_session)
    main = st.gm(1, frm=st.v_bin, to=st.v_fixture, wi_group="上料", tool_vocab_id=None, sub_activity="拿",
                 key_parts="K", frequency=2)
    main["level"] = {"ascription": "main", "level": "1", "coefficient": 1.5, "worker_cub": "W1", "offline": True,
                     "segment": "S1", "station_pin": 2, "is_general": True, "merge_lock": True,
                     "machine_unattended": False, "action_type": "place"}
    simo = st.gm(2, frm=st.v_bin, to=st.v_fixture, simo_with_row_id=main["id"])
    other = st.gm(3, frm=st.v_bin, to=st.v_cart, distance_status="manual")
    saved = await _save(client, st.ws.id, [main, simo, other], 1)
    await db_session.execute(text("UPDATE wi_rows SET provenance='imported' WHERE id = :i"), {"i": other["id"]})
    await db_session.commit()
    before = {x["wi_row_id"]: x for x in (await client.get(f"/api/v2/worksheets/{st.ws.id}")).json()["rows"]}
    await _compute(client, st.ws.id)
    out = (await _apply(client, st.ws.id, [main["id"]], saved["revision_no"])).json()
    after = {x["wi_row_id"]: x for x in out["rows"]}
    for rid in (main["id"], simo["id"], other["id"]):
        for k in ("seq_no", "hand", "sub_activity", "key_parts", "frequency", "simo_group_id", "wi_group",
                  "from_vocab_id", "to_vocab_id", "object_vocab_id", "tool_vocab_id", "level", "lb_tags"):
            got, want = after[rid][k], before[rid][k]
            if k == "level" and rid == main["id"]:
                # 目標列距離變了，引擎秒數（level.second）跟著變；其餘 level 欄位要原樣
                got, want = {**got, "second": None}, {**want, "second": None}
            assert got == want, (rid, k)
    assert after[simo["id"]]["simo_group_id"] is not None
    for rid in (simo["id"], other["id"]):
        assert after[rid]["cycle"]["total_tmu"] == before[rid]["cycle"]["total_tmu"]
        assert after[rid]["cycle"]["slot_inputs"] == before[rid]["cycle"]["slot_inputs"]
    assert after[other["id"]]["distance_status"] == "manual"
    row = await db_session.get(WiRow, uuid.UUID(other["id"]))
    await db_session.refresh(row)
    assert row.provenance == "imported"


async def test_reset_only_on_distance_inputs(client, db_session):
    st = await Station().build(db_session)
    a, b, c = (st.gm(i, frm=st.v_bin, to=st.v_fixture) for i in (1, 2, 3))
    saved = await _save(client, st.ws.id, [a, b, c], 1)
    await _compute(client, st.ws.id)
    out = (await _apply(client, st.ws.id, [a["id"], b["id"], c["id"]], saved["revision_no"])).json()
    rows = {x["wi_row_id"]: x for x in out["rows"]}

    def resend(rid, cycle=None, **changes):
        x = rows[rid]
        return {"id": rid, "seq_no": x["seq_no"], "hand": x["hand"], "frequency": x["frequency"],
                "narrative": x["cycle"]["narrative"], "from_vocab_id": x["from_vocab_id"],
                "to_vocab_id": x["to_vocab_id"], "object_vocab_id": x["object_vocab_id"],
                "cycle": cycle or dict(x["cycle"]["slot_inputs"]),
                "level": {"ascription": "main", "level": str(x["seq_no"])}, **changes}

    a0_changed = dict(rows[a["id"]]["cycle"]["slot_inputs"], a0={"reach_cm": 12})
    after = await _save(client, st.ws.id, [
        resend(a["id"], cycle=a0_changed),            # 只改 a0 距離 → 退回
        resend(b["id"], frequency=3, narrative="x"),  # 只改非距離欄位 → 維持
        resend(c["id"], distance_status="confirmed", to_vocab_id=str(st.v_cart.id)),  # 明確帶值 → 以帶的為準
    ], out["revision_no"])
    status = {x["wi_row_id"]: x["distance_status"] for x in after["rows"]}
    assert status == {a["id"]: None, b["id"]: "confirmed", c["id"]: "confirmed"}


def test_default_distance_settings_are_frozen():
    """沒有距離段的政策版本（含 V1）靠這組常數；改它會悄悄改變既有工時表。"""
    from ddm_v2.services.v2.policy_service import DEFAULT_DISTANCE_SETTINGS

    assert DEFAULT_DISTANCE_SETTINGS == {"reach_foot_threshold_cm": 70.0, "person_offset_cm": [0.0, 0.0, 140.0]}
