"""ADR-023 §3.2/§3.4：rule-set 生命週期（activate/retire）與回放安全。

**回放鐵則**（§3.4）：`load_rule_set_from_db` 只依 code 查表，永不看 status/is_active。
治理狀態只在「選擇」時生效（`?selectable=true`／`GET /rule-sets/active`），不在「載入」時生效。
本檔以可機械驗證的斷言把該鐵則釘死：inactive／retired 版本必須仍能載入、仍算出原值。

黃金錨（V1 語意）：GM=28、CM=29（推 18cm＋contact，V1 階梯門檻 18→16）。
V2 語意的 CM=29 是推 45cm，兩者不可混用——本檔測的是 V1 回放。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

V1 = "MINIMOST_FACTORY_V1"
V2 = "MINIMOST_FACTORY_V2"
WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"

# V1 語意的黃金 cycle（引擎層對應 tests/unit/test_most_engine.py::test_v1_replay_goldens）
GM_V1 = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
         "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}
CM_V1 = {"seq": "CM", "a0": {"reach_cm": 25},
         "g2": {"g_code": "g_touch", "modifiers": {"contact": True}},
         "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 18}]},
         "x4": {"x_code": "x_none"}, "i5": {"i_code": "i_none"}}


async def _compute(session, code: str, cycle: dict) -> int:
    """繞過 API，直接走引擎的回放路徑：load_rule_set_from_db → compute_cycle。"""
    from ddm_v2.most_engine import compute_cycle, load_rule_set_from_db
    from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

    rsdata = await load_rule_set_from_db(session, code)
    rsdata.validate_complete()
    return compute_cycle(cycle_in_to_engine(CycleIn(**cycle)), rsdata).total_tmu


async def _rule_set(session, code: str):
    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet

    return (await session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one_or_none()


async def _seeded(session) -> bool:
    return await _rule_set(session, V1) is not None and await _rule_set(session, V2) is not None


# ── (1)(2)(3) inactive／retired 的 V1 仍可載入且值不變 ────────────────────


async def test_inactive_v1_still_loads_and_replays_goldens(db_session):
    """(1)(2)：V1 為 inactive（migration 後的既定狀態）時，仍可載入並算出 GM=28 / CM=29。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種（先跑 dev_seed_v2.py）")
    v1 = await _rule_set(db_session, V1)
    assert v1.is_active is False, "V1 應為 inactive（回放版本，不再被選中）"
    assert v1.provenance == "certified_import", "V1 應標記為認證匯入版本（ADR-023 規則 3）"

    assert await _compute(db_session, V1, GM_V1) == 28
    assert await _compute(db_session, V1, CM_V1) == 29


async def test_retired_v1_still_loads_and_replays_goldens(db_session):
    """(1)(2)：把 V1 retire 後，load_rule_set_from_db 仍成功、TMU 仍是 28/29。

    這是 §3.4 鐵則的核心斷言——治理狀態不得滲進載入路徑。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.services.v2 import rule_set_service as svc

    await svc.retire(db_session, V1, actor="UT_REPLAY")
    await db_session.commit()
    assert (await _rule_set(db_session, V1)).status == "retired"

    assert await _compute(db_session, V1, GM_V1) == 28, "retired 版本回放值不得漂移"
    assert await _compute(db_session, V1, CM_V1) == 29


async def test_activate_v2_does_not_change_v1_replay(db_session):
    """(3)：切換 active 到 V2 後重跑 (1)(2)，V1 回放結果完全不變。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.services.v2 import rule_set_service as svc

    before_gm = await _compute(db_session, V1, GM_V1)
    before_cm = await _compute(db_session, V1, CM_V1)

    await svc.activate(db_session, V2, actor="UT_REPLAY")
    await db_session.commit()
    assert (await svc.get_active_rule_set_code(db_session)) == V2

    assert await _compute(db_session, V1, GM_V1) == before_gm == 28
    assert await _compute(db_session, V1, CM_V1) == before_cm == 29


async def test_cycle_referencing_retired_rule_set_recomputes_same_tmu(client, db_session):
    """(4)：建立引用某版本的 cycle → retire 該版本 → 重算 → TMU 不變（§3.4 第 3 條）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")

    # 專用版本（clone V1 → publish），避免污染 V1/V2 這兩個回放基準版本
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_REPLAY_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, V1, code, "回放測試版")
    await svc.publish(db_session, code, actor="UT_REPLAY")
    await db_session.commit()

    row = {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
           "frequency": 1, "cycle": dict(GM_V1, rule_set_code=code),
           "level": {"ascription": "main", "level": "1"}}
    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    saved = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": [row]})
    assert saved.status_code == 200, saved.text
    tmu_before = saved.json()["total_tmu"]
    assert tmu_before == 28

    # 下架該版本（非 active，可直接 retire）
    await svc.retire(db_session, code, actor="UT_REPLAY")
    await db_session.commit()
    assert (await _rule_set(db_session, code)).status == "retired"

    # 重算：以同樣 rows 重新存檔（走完整 compute 路徑）→ TMU 不得漂移
    resaved = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": [row]})
    assert resaved.status_code == 200, resaved.text
    assert resaved.json()["total_tmu"] == tmu_before == 28
    # 讀回也一致
    read = (await client.get(f"/api/v2/worksheets/{new_ws}")).json()
    assert read["rows"][0]["cycle"]["total_tmu"] == 28


# ── 生命週期邊界 ────────────────────────────────────────────────────────


async def test_get_active_endpoint_returns_v2(client, db_session):
    """GET /rule-sets/active → 目前啟用版本（前端取代寫死常數的來源）。

    ⚠️ skip 條件必須是**資料前置條件**（rule-set 有沒有種），不得用被測端點自己的狀態碼。
    無 active 時本端點正是回 500——拿 500 當 skip 條件會讓「activate 壞掉」這個回歸靜靜溜過。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    r = await client.get("/api/v2/rule-sets/active")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == V2
    assert set(body) == {"id", "code", "name_zh"}


async def test_list_selectable_returns_only_published_active(client, db_session):
    """?selectable=true → 只回 published+active（ADR-023 §3.4 規則 2）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    r = await client.get("/api/v2/rule-sets?selectable=true")
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1, "恆有且僅有一個 active 版本"
    assert items[0]["code"] == V2 and items[0]["is_active"] is True
    # 全清單則含 V1（inactive）
    all_items = (await client.get("/api/v2/rule-sets")).json()
    assert any(i["code"] == V1 and i["is_active"] is False for i in all_items)
    assert all({"is_active", "provenance", "created_at", "notes"} <= set(i) for i in all_items)


async def test_retired_version_disappears_from_selectable(client, db_session):
    """retired 版本必須從 ?selectable=true 消失（治理狀態在「選擇」時生效，§3.4 規則 2）。

    但它仍留在完整清單、且仍可載入回放——兩者不可混為一談。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_SEL_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, V2, code, "下架可見性測試版")
    await svc.publish(db_session, code, actor="UT_SEL")
    await svc.activate(db_session, code, actor="UT_SEL")
    await db_session.commit()

    sel = (await client.get("/api/v2/rule-sets?selectable=true")).json()
    assert [i["code"] for i in sel] == [code], "active+published 應出現在可選清單"

    # 換回 V2 為 active，再把測試版下架
    await svc.activate(db_session, V2, actor="UT_SEL")
    await svc.retire(db_session, code, actor="UT_SEL")
    await db_session.commit()

    sel_after = (await client.get("/api/v2/rule-sets?selectable=true")).json()
    assert code not in [i["code"] for i in sel_after], "retired 版本不得再出現在可選清單"
    assert [i["code"] for i in sel_after] == [V2]
    # 但完整清單仍看得到，且仍可載入回放（§3.4 鐵則）
    all_codes = [i["code"] for i in (await client.get("/api/v2/rule-sets")).json()]
    assert code in all_codes, "retired 版本仍應留在完整清單（不是刪除）"
    assert await _compute(db_session, code, GM_V1) == 28, "retired 版本仍可載入計算"


async def test_activate_draft_returns_400(client, db_session):
    """邊界：draft 版本不可 activate（須先 publish）→ 400。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_DRAFT_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, V1, code, None)
    await db_session.commit()

    r = await client.post(f"/api/v2/rule-sets/{code}/activate")
    assert r.status_code == 400, r.text


async def test_publish_incomplete_draft_returns_409(client, db_session):
    """邊界：無子表的 draft publish → 409（validate_complete 擋在發布前，不等 runtime 才炸）。"""
    from ddm_v2.models.v2.rule_set import RuleSet

    code = f"UT_EMPTY_{uuid.uuid4().hex[:8]}"
    db_session.add(RuleSet(id=uuid.uuid4(), code=code, name_zh="空草稿", status="draft",
                           system_tmu_multiplier=1, is_active=False, provenance="manual"))
    await db_session.commit()

    r = await client.post(f"/api/v2/rule-sets/{code}/publish")
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "RULE_SET_INCOMPLETE"
    assert (await _rule_set(db_session, code)).status == "draft", "驗證失敗不得留下半發布狀態"


async def test_retire_active_returns_400(client, db_session):
    """邊界：啟用中版本不可 retire（須先啟用其他版本）→ 400。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    r = await client.post(f"/api/v2/rule-sets/{V2}/retire")
    assert r.status_code == 400, r.text
    assert (await _rule_set(db_session, V2)).status == "published"


async def test_double_activate_hits_partial_unique_index(db_session):
    """邊界：DB 層 partial unique index 擋雙 active（併發兩筆 activate → 一成功一失敗）。

    測試用單一 connection 無法真併發，故直接對 DB 下第二筆 is_active=true 的寫入，
    斷言它撞 uq_rule_sets_single_active 而非靜默造成雙 active。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError) as e:
        await db_session.execute(
            text("UPDATE rule_sets SET is_active = true WHERE code = :c").bindparams(c=V1)
        )
        await db_session.flush()
    assert "uq_rule_sets_single_active" in str(e.value)
    await db_session.rollback()

    # 回滾後仍恰好一個 active
    from sqlalchemy import func, select

    from ddm_v2.models.v2.rule_set import RuleSet
    n = (await db_session.execute(select(func.count()).select_from(RuleSet).where(RuleSet.is_active.is_(True)))).scalar_one()
    assert n == 1


async def test_activate_conflict_maps_to_409_not_bare_500(client, db_session):
    """併發 activate 的敗方撞 uq_rule_sets_single_active → 409 可重試，不是裸 500（L6）。

    以「DB 已有另一筆 active、且 activate 的 deactivate 步驟被繞過」模擬敗方：
    直接觸發 UPDATE 撞 index，驗 main.py 的 IntegrityError handler 有把它翻成 409。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_RACE_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, V2, code, "併發測試版")
    await svc.publish(db_session, code, actor="UT_RACE")
    await db_session.commit()

    # 模擬 race 的敗方視角：deactivate 與 set-true 之間，另一交易已搶先啟用，
    # 於是敗方的 set-true 撞上 partial unique index。以「跳過 deactivate 步驟」等價重現。
    from sqlalchemy import select

    async def _racing_activate(session, target_code, actor=None):
        rs = (await session.execute(select(RuleSet).where(RuleSet.code == target_code))).scalar_one()
        rs.is_active = True          # 故意不先 deactivate
        await session.flush()
        return {"code": target_code}

    monkeypatched = svc.activate
    svc.activate = _racing_activate
    try:
        r = await client.post(f"/api/v2/rule-sets/{code}/activate")
    finally:
        svc.activate = monkeypatched

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "RULE_SET_ACTIVATE_CONFLICT"


async def test_activate_switches_single_active_and_writes_audit(client, db_session):
    """activate 序列切換：舊 active 自動 deactivate，全庫仍恰好一個；並留 audit log。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from sqlalchemy import func, select

    from ddm_v2.models.v2.audit import WorkflowAuditLog
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.services.v2 import rule_set_service as svc

    code = f"UT_ACT_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, V2, code, "啟用測試版")
    await svc.publish(db_session, code, actor="UT_ACT")
    await db_session.commit()

    r = await client.post(f"/api/v2/rule-sets/{code}/activate")
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True

    actives = (await db_session.execute(select(RuleSet.code).where(RuleSet.is_active.is_(True)))).scalars().all()
    assert actives == [code], "activate 後應恰好一個 active，且為目標版本"
    assert (await _rule_set(db_session, V2)).is_active is False, "舊 active 應被同交易 deactivate"

    target = await _rule_set(db_session, code)
    n = (await db_session.execute(
        select(func.count()).select_from(WorkflowAuditLog).where(
            WorkflowAuditLog.entity_type == "rule_set",
            WorkflowAuditLog.entity_id == target.id,
            WorkflowAuditLog.action == "activate",
        )
    )).scalar_one()
    assert n == 1, "activate 必留 audit log（ADR-023 規則 4）"


async def test_clone_draft_without_new_code_autonames_and_dedups(client, db_session):
    """clone-draft 的 new_code 選填：缺省自動命名；同分鐘連按兩次不得撞 UNIQUE（500）。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    r1 = await client.post(f"/api/v2/rule-sets/{V2}/clone-draft", json={})
    assert r1.status_code == 200, r1.text
    c1 = r1.json()["code"]
    assert c1.startswith(f"{V2}_DRAFT_")
    assert r1.json()["provenance"] == "cloned"

    r2 = await client.post(f"/api/v2/rule-sets/{V2}/clone-draft", json={})
    assert r2.status_code == 200, r2.text
    c2 = r2.json()["code"]
    assert c2 != c1, "同分鐘第二次 clone 應附序號，不得撞 UNIQUE"

    assert (await _rule_set(db_session, c1)).provenance == "cloned"


# ── V1/V2 分裂修正（ADR-023 §3.5）────────────────────────────────────────


async def test_new_worksheet_default_rule_set_is_active_not_v1(client, db_session):
    """§3.5：新建 worksheet 的 default_rule_set_id ＝ active（V2），不再寫死 V1。"""
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet

    tag = uuid.uuid4().hex[:8]
    site = Site(name_zh=f"RSTEST_SITE_{tag}")
    db_session.add(site)
    await db_session.flush()
    product = Product(site_id=site.id, name_zh=f"RSTEST_PROD_{tag}")
    db_session.add(product)
    await db_session.flush()
    sku = Sku(product_id=product.id, sku_code=f"RSTEST_SKU_{tag}", name_zh=f"規則版本測試 {tag}")
    db_session.add(sku)
    await db_session.commit()

    r = await client.post(f"/api/v2/skus/{sku.id}/worksheets",
                          json={"model_label": "RSTEST", "analyst": "UT"})
    assert r.status_code in (200, 201), r.text
    ws_id = r.json()["worksheet_id"]

    ws = await db_session.get(MostWorksheet, uuid.UUID(ws_id))
    await db_session.refresh(ws)
    active = await _rule_set(db_session, V2)
    assert ws.default_rule_set_id == active.id, "新 worksheet 預設應為 active 版本（V2）"
    assert ws.default_rule_set_id != (await _rule_set(db_session, V1)).id


async def test_save_without_rule_set_code_persists_active_version(client, db_session):
    """§3.5：cycle 未帶 rule_set_code → 存檔解析為 active，並**實際落盤**成 active 版本。

    鑑別力：斷言 most_cycles.rule_set_id 與 slot_inputs.rule_set_code 皆為 V2。
    把 worksheet_service 的解析改回寫死 V1，這兩條斷言都會紅。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    from sqlalchemy import select

    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    row_id = str(uuid.uuid4())
    row = {"id": row_id, "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ, "frequency": 1,
           "cycle": dict(GM_V1),  # 刻意不帶 rule_set_code
           "level": {"ascription": "main", "level": "1"}}
    assert "rule_set_code" not in row["cycle"]

    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    r = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": [row]})
    assert r.status_code == 200, r.text

    active = await _rule_set(db_session, V2)
    v1 = await _rule_set(db_session, V1)
    cyc = (await db_session.execute(
        select(MostCycle).join(WiRow, MostCycle.wi_row_id == WiRow.id)
        .where(WiRow.worksheet_id == uuid.UUID(new_ws))
    )).scalar_one()
    assert cyc.rule_set_id == active.id, "未指定版本應落盤為 active（V2）"
    assert cyc.rule_set_id != v1.id, "不得回退成寫死的 V1"
    # §3.4：slot_inputs 是回放權威原始輸入 → 必須自帶版本代碼，不可留 None
    assert cyc.slot_inputs["rule_set_code"] == V2


async def test_module_publish_and_instantiate_persist_rule_set_code(client, db_session):
    """M1：模組路徑與 WI 路徑同契約——版本快照與實體化的 cycle JSON 都不得留 rule_set_code=null。

    §3.4：slot_inputs／rows[].cycle 是回放的權威原始輸入。TMU 靠 rule_set_id 另存是安全的，
    但 JSON 缺版本代碼會讓兩條持久化路徑的契約不一致。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    from sqlalchemy import select

    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    active = await _rule_set(db_session, V2)
    sfx = uuid.uuid4().hex[:6]
    mid = (await client.post("/api/v2/motion-modules",
                             json={"name_zh": f"UT-RSCode-{sfx}", "category": "action",
                                   "scope": "global"})).json()["id"]

    # cycle 刻意不帶 rule_set_code
    cycle = dict(GM_V1)
    assert "rule_set_code" not in cycle
    pub = await client.post(f"/api/v2/motion-modules/{mid}/publish", json={
        "rule_set_id": str(active.id),
        "rows": [{"hand": "RH", "frequency": 1, "vocab_refs": {}, "cycle": cycle}],
    })
    assert pub.status_code == 201, pub.text

    # (a) 版本快照 rows[].cycle 已回填
    ver = (await client.get(f"/api/v2/motion-modules/{mid}/versions")).json()[0]
    detail = (await client.get(f"/api/v2/motion-modules/{mid}")).json()["current_version_detail"]
    snapshot_rows = detail.get("rows") or ver.get("rows")
    assert snapshot_rows[0]["cycle"]["rule_set_code"] == V2, "模組版本快照不得留 rule_set_code=null"

    # (b) 實體化後 most_cycles.slot_inputs 也已回填。
    # 注意：實體化用的是**目的工序表**凍結的 default_rule_set_id（§3.4 第 4 條，
    # 不回溯改寫），不是模組發布時的版本——所以斷言對象是該工序表自己的版本代碼。
    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.models.v2.worksheet import MostWorksheet

    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    inst = await client.post(f"/api/v2/worksheets/{new_ws}/rows/from-module", json={"module_id": mid})
    assert inst.status_code == 201, inst.text

    ws_obj = await db_session.get(MostWorksheet, uuid.UUID(new_ws))
    await db_session.refresh(ws_obj)
    ws_rs_code = (await db_session.get(RuleSet, ws_obj.default_rule_set_id)).code

    cyc = (await db_session.execute(
        select(MostCycle).join(WiRow, MostCycle.wi_row_id == WiRow.id)
        .where(WiRow.worksheet_id == uuid.UUID(new_ws))
    )).scalars().all()
    assert cyc, "實體化應建立 most_cycles"
    for c in cyc:
        assert c.slot_inputs.get("rule_set_code") is not None, \
            "實體化的 slot_inputs 不得留 rule_set_code=null（M1）"
        assert c.slot_inputs["rule_set_code"] == ws_rs_code, \
            "應回填為該工序表實際使用的版本（rule_set_id 同源）"
        assert c.rule_set_id == ws_obj.default_rule_set_id


async def test_empty_rows_save_consults_active_rule_set(client, db_session):
    """§3.5：空 rows 存檔的 fallback 確實**查詢 active**（不是寫死 V1）。

    鑑別力：把 active 全部關掉後，空 rows 存檔必須炸 NO_ACTIVE_RULE_SET；
    若 fallback 仍寫死 V1，這裡會回 200 而測試變紅。
    （空 rows 不寫任何 most_cycles，無法用落盤資料鑑別，故以「無 active 時的行為」反證。）
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    from sqlalchemy import text

    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    # 正常情況（有 active）：空 rows 存檔成功
    ok = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": []})
    assert ok.status_code == 200, ok.text
    assert ok.json()["rows"] == []

    # 拔掉 active（隔離 transaction 內，測後 rollback）→ 同一次呼叫必須明確失敗
    await db_session.execute(text("UPDATE rule_sets SET is_active = false WHERE is_active"))
    await db_session.commit()
    r = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": []})
    assert r.status_code == 500, r.text
    assert r.json()["error"]["code"] == "NO_ACTIVE_RULE_SET"


async def test_cycle_without_rule_set_code_resolves_to_active(client, db_session):
    """§3.5：schema 層不再有 DEFAULT_RULE_SET；calculate 未帶 rule_set_code → 由服務層填 active。

    ⚠️ 原本 skip on 404/409/500 恰好涵蓋了本測試要防的全部回歸模式
    （版本解析錯 → 404、不完整 → 409、無 active → 500），等於自我豁免。改為只看資料前置條件。
    """
    if not await _seeded(db_session):
        pytest.skip("rule-set 未種")
    r = await client.post("/api/v2/minimost/calculate", json=GM_V1)
    assert r.status_code == 200, r.text
    assert r.json()["rule_set_code"] == V2, "未指定版本應解析為 active（V2）"
    assert r.json()["total_tmu"] == 28
