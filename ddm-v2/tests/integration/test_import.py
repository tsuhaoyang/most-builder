"""Excel 匯入 2a 整合測試（ADR-013）：upload → map(preview) → profile；含邊界。"""
from __future__ import annotations

import io

import pytest

pytestmark = pytest.mark.integration


def _xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Assembly"
    ws.append(["Model:", "DL360", None, None, None])      # metadata
    ws.append([None, None, None, None, None])             # blank
    ws.append(["No.", "Element Description", "Average TT", "Quantity", "IEC PN"])  # header @ idx 2
    ws.append([1, "take out chassis", 5.9, 1, "PN1"])
    ws.append([2, "stick label", 4.85, 1, None])
    ws.append([None, None, None, None, None])             # empty row → skip
    ws.append([3, "screw bolt", "bad", 1, "PN3"])         # bad time → warn
    wb.create_sheet("Tests").append(["x"])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _files():
    return {"file": ("Touchtime.xlsx", _xlsx(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def test_upload_detects_sheets_and_header(client):
    r = await client.post("/api/v2/imports/upload", files=_files())
    assert r.status_code == 200
    j = r.json()
    assert [s["name"] for s in j["sheets"]] == ["Assembly", "Tests"]
    assert j["suggested_header_row"] == 2          # 啟發式抓到真表頭
    assert "description" in j["target_fields"]


async def test_map_normalizes_and_warns(client):
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2, "quantity": 3, "part_no": 4}, "time_unit": "sec"})
    assert r.status_code == 200
    j = r.json()
    assert j["n"] == 3                              # 空列被跳過
    assert j["rows"][0]["description"] == "take out chassis"
    assert j["rows"][0]["seconds"] == 5.9
    assert j["rows"][2]["seconds"] is None          # 壞工時 → None
    assert any("工時無法解析" in w for w in j["warnings"])


async def test_map_time_unit_minutes(client):
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    j = (await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2}, "time_unit": "min"})).json()
    assert j["rows"][0]["seconds"] == round(5.9 * 60, 4)   # 分→秒換算


async def test_profile_crud(client):
    p = await client.post("/api/v2/imports/profiles", json={
        "name": "ut-profile", "header_row": 2, "column_map": {"description": 1}, "time_unit": "sec"})
    assert p.status_code == 201
    pid = p.json()["id"]
    assert any(x["name"] == "ut-profile" for x in (await client.get("/api/v2/imports/profiles/list")).json())
    assert (await client.delete(f"/api/v2/imports/profiles/{pid}")).status_code == 204


async def test_rbac_viewer_cannot_upload(client):
    r = await client.post("/api/v2/imports/upload", files=_files(), headers={"X-Username": "ZZZUTVIEW2"})
    assert r.status_code == 403


# ───────────────────────────────────────────────────────────────
# Phase 2b submit tests（ADR-013 §2b；對應 F 規格驗收）
# ───────────────────────────────────────────────────────────────

# dev_seed_v2.py WORKSHEET = uuid.UUID("55555555-5555-5555-5555-555555555555")
_WS_SEEDED = "55555555-5555-5555-5555-555555555555"


async def test_submit_creates_wi_rows(client):
    """Happy path：staged rows → WiRow/MostCycle/LevelEntry 建立。
    同時驗 Fix-H2 迴歸：重複提交同一 import_id → 409。
    """
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1, "seconds": 2, "quantity": 3},
        "time_unit": "sec",
    })
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": _WS_SEEDED},
    )
    assert r.status_code == 200
    j = r.json()
    assert j["n_rows"] == 3          # _xlsx() 有 3 筆非空列（空列被 apply_mapping 跳過）
    assert isinstance(j["n_with_analysis"], int)
    assert isinstance(j["n_need_review"], int)

    # Fix-H2 迴歸：status 已變為 "submitted"，再 submit 同一 import_id → 409
    r2 = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": _WS_SEEDED},
    )
    assert r2.status_code == 409


async def test_submit_not_mapped_returns_409(client):
    """upload 後（status=uploaded）直接 submit → 409（尚未欄位對應）。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 409


async def test_submit_worksheet_not_found_returns_404(client):
    """map 完成後，submit 給不存在的 worksheet_id → 404。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "Assembly", "header_row": 2,
        "column_map": {"description": 1},
        "time_unit": "sec",
    })
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert r.status_code == 404


async def test_submit_viewer_returns_403(client):
    """viewer 身分無法 submit（require_role("analyst") 守門）。"""
    iid = (await client.post("/api/v2/imports/upload", files=_files())).json()["import_id"]
    r = await client.post(
        f"/api/v2/imports/{iid}/submit",
        json={"worksheet_id": "00000000-0000-0000-0000-000000000001"},
        headers={"X-Username": "ZZZUTVIEW2"},
    )
    assert r.status_code == 403


# ───────────────────────────────────────────────────────────────
# ADR-025 D10：匯入自動建模（range template match → 採用落地）
# ───────────────────────────────────────────────────────────────

# CM=29 黃金錨（A10 B0 G3 M16 X0 I0 A0，推 45cm＝18 吋檔）；active V2 下＝29。
_CM29 = {"seq": "CM", "a0": {"reach_cm": 25}, "g2": {"g_code": "g_touch"},
         "m3": {"m_components": [{"verb_code": "m_push", "distance_cm": 45}]},
         "x4": {"x_code": "x_none"}, "i5": {"i_code": "i_none"}, "a6": {}}
# GM=28 黃金錨（A6 B0 G6 A10 B0 P6 A0）。
_GM28 = {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
         "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}, "a6": {}}


def _xlsx_zh() -> bytes:
    """三筆列，用**唯一 token** 避免與 DB 既有種子範本庫的中文關鍵字碰撞：
    0 含 zzzutscrew、1 含 zzzutgrab、2 無任何範本關鍵字。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "工序"
    ws.append(["項次", "動作描述", "工時", "數量"])          # header @ idx 0
    ws.append([1, "zzzutscrew 鎖附", 3.2, 1])
    ws.append([2, "zzzutgrab 拿取", 5.0, 1])
    ws.append([3, "zzznomatchxx", 4.0, 1])
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


def _zh_files():
    return {"file": ("zh.xlsx", _xlsx_zh(),
                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


async def _make_standard_template(client, name_zh, keywords, cycle, seq_kind):
    """建草稿 → 提升為 standard（match 只比 standard 庫）。回傳 template dict。"""
    r = await client.post("/api/v2/motion-templates", json={
        "name_zh": name_zh, "seq_kind": seq_kind, "keywords": keywords, "cycle_template": cycle})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    p = await client.post(f"/api/v2/motion-templates/{tid}/promote")
    assert p.status_code == 200 and p.json()["status"] == "standard"
    return p.json()


async def _map_zh(client):
    """upload + map _xlsx_zh，回傳 (import_id, preview_json)。"""
    iid = (await client.post("/api/v2/imports/upload", files=_zh_files())).json()["import_id"]
    r = await client.post(f"/api/v2/imports/{iid}/map", json={
        "sheet": "工序", "header_row": 0,
        "column_map": {"description": 1, "seconds": 2, "quantity": 3}, "time_unit": "sec"})
    assert r.status_code == 200, r.text
    return iid, r.json()


async def test_preview_match_hits_screw_template(client):
    """含唯一 token 的暫存列 → 命中「鎖附螺絲」且 computed_tmu 為具體正值（CM 黃金＝29）。"""
    await _make_standard_template(client, "鎖附螺絲", ["zzzutscrew"], _CM29, "CM")
    _iid, j = await _map_zh(client)
    m0 = j["rows"][0]["match"]
    assert m0 is not None
    assert m0["template_name_zh"] == "鎖附螺絲"
    assert m0["seq_kind"] == "CM"
    assert "zzzutscrew" in m0["matched_keywords"]
    assert m0["error"] is None
    assert m0["computed_tmu"] == 29        # 具體值（不是只斷言非 null）
    assert m0["computed_seconds"] == round(29 * 0.036, 4)


async def test_preview_match_tmu_recomputed_via_active(client):
    """match.computed_tmu 等於直接呼叫 calculate 同結構（active）的結果——證明走同一引擎、
    沒有第二套計算、也沒有用範本裡殘留的舊值。"""
    await _make_standard_template(client, "拿取外殼", ["zzzutgrab"], _GM28, "GM")
    # 直接走唯一計算引擎（未帶 rule_set_code → active）
    calc = await client.post("/api/v2/minimost/calculate", json=_GM28)
    assert calc.status_code == 200, calc.text
    expected = calc.json()["total_tmu"]
    assert expected == 28                    # active V2 黃金
    _iid, j = await _map_zh(client)
    m1 = j["rows"][1]["match"]               # 「zzzutgrab 拿取」
    assert m1 is not None and m1["template_name_zh"] == "拿取外殼"
    assert m1["computed_tmu"] == expected


async def test_preview_no_match_is_null_and_submits_as_stub(client, db_session):
    """描述不含任何關鍵字 → match 為 null；submit（未採用）後該行仍是 stub（total_tmu==0）。"""
    import uuid as _uuid

    from sqlalchemy import select

    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    await _make_standard_template(client, "鎖附螺絲", ["螺絲"], _CM29, "CM")
    iid, j = await _map_zh(client)
    assert j["rows"][2]["match"] is None      # 「無關字樣ZZZ」無命中

    r = await client.post(f"/api/v2/imports/{iid}/submit", json={"worksheet_id": _WS_SEEDED})
    assert r.status_code == 200

    wr2 = (await db_session.execute(
        select(WiRow).where(WiRow.source_import_id == _uuid.UUID(iid)).order_by(WiRow.seq_no)
    )).scalars().all()[2]
    cyc = (await db_session.execute(
        select(MostCycle).where(MostCycle.wi_row_id == wr2.id))).scalar_one()
    assert float(cyc.total_tmu) == 0.0        # 未採用 → 維持 stub


async def test_submit_adopts_only_listed_rows_backend_computes_tmu(client, db_session):
    """三行兩採用：只有兩行有實 cycle、第三行 stub；落地 TMU 由後端算（假 TMU 被忽略）。"""
    import uuid as _uuid

    from sqlalchemy import select

    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    t = await _make_standard_template(client, "鎖附螺絲", ["螺絲"], _CM29, "CM")
    iid, _j = await _map_zh(client)

    # row 0、1 採用同一 standard 範本；row 1 夾帶假 TMU（契約只收 template_id，應被忽略）
    r = await client.post(f"/api/v2/imports/{iid}/submit", json={
        "worksheet_id": _WS_SEEDED,
        "row_adoptions": [
            {"row_index": 0, "template_id": t["id"]},
            {"row_index": 1, "template_id": t["id"], "tmu": 99999},  # 假 TMU
        ],
    })
    assert r.status_code == 200, r.text
    assert r.json()["n_with_analysis"] >= 2

    wrs = (await db_session.execute(
        select(WiRow).where(WiRow.source_import_id == _uuid.UUID(iid)).order_by(WiRow.seq_no)
    )).scalars().all()
    assert len(wrs) == 3
    tmus = []
    for wr in wrs:
        cyc = (await db_session.execute(
            select(MostCycle).where(MostCycle.wi_row_id == wr.id))).scalar_one()
        tmus.append(float(cyc.total_tmu))
    assert tmus[0] == 29 and tmus[1] == 29    # 後端算（29），不是前端夾帶的 99999
    assert tmus[2] == 0.0                       # 未採用 → stub


async def test_submit_rejects_non_standard_template_422(client):
    """row_adoptions 指向 draft 範本／不存在 id → 422（斷言 detail）。"""
    import uuid as _uuid

    # draft（未 promote）
    draft = (await client.post("/api/v2/motion-templates", json={
        "name_zh": "草稿範本", "seq_kind": "CM", "keywords": ["x"], "cycle_template": _CM29})).json()
    iid, _j = await _map_zh(client)

    r = await client.post(f"/api/v2/imports/{iid}/submit", json={
        "worksheet_id": _WS_SEEDED,
        "row_adoptions": [{"row_index": 0, "template_id": draft["id"]}]})
    assert r.status_code == 422
    assert "非啟用中的標準範本" in r.json()["detail"]

    # 不存在的 id
    iid2, _ = await _map_zh(client)
    r2 = await client.post(f"/api/v2/imports/{iid2}/submit", json={
        "worksheet_id": _WS_SEEDED,
        "row_adoptions": [{"row_index": 0, "template_id": str(_uuid.uuid4())}]})
    assert r2.status_code == 422
    assert "非啟用中的標準範本" in r2.json()["detail"]


async def test_submit_rejects_row_index_out_of_range_422(client):
    """row_index 越界 → 422（斷言 detail）。"""
    t = await _make_standard_template(client, "鎖附螺絲", ["螺絲"], _CM29, "CM")
    iid, _j = await _map_zh(client)   # 只有 3 列（index 0..2）
    r = await client.post(f"/api/v2/imports/{iid}/submit", json={
        "worksheet_id": _WS_SEEDED,
        "row_adoptions": [{"row_index": 9, "template_id": t["id"]}]})
    assert r.status_code == 422
    assert "超出暫存列範圍" in r.json()["detail"]


async def test_submit_adopted_cycle_records_active_rule_set_code(client, db_session):
    """回放鐵則：採用落地的 cycle 其 rule_set_code == 當下 active code。"""
    import uuid as _uuid

    from sqlalchemy import select

    from ddm_v2.models.v2.rule_set import RuleSet
    from ddm_v2.models.v2.worksheet import MostCycle, WiRow

    active = (await db_session.execute(
        select(RuleSet).where(RuleSet.is_active.is_(True)))).scalar_one()

    t = await _make_standard_template(client, "鎖附螺絲", ["螺絲"], _CM29, "CM")
    iid, _j = await _map_zh(client)
    r = await client.post(f"/api/v2/imports/{iid}/submit", json={
        "worksheet_id": _WS_SEEDED,
        "row_adoptions": [{"row_index": 0, "template_id": t["id"]}]})
    assert r.status_code == 200, r.text

    wr = (await db_session.execute(
        select(WiRow).where(WiRow.source_import_id == _uuid.UUID(iid)).order_by(WiRow.seq_no)
    )).scalars().first()
    cyc = (await db_session.execute(
        select(MostCycle).where(MostCycle.wi_row_id == wr.id))).scalar_one()
    assert cyc.rule_set_id == active.id
    assert cyc.slot_inputs["rule_set_code"] == active.code


async def test_preview_no_active_rule_set_yields_null_tmu_no_fallback(client, db_session):
    """無 active rule-set 時：命中列 computed_tmu 為 null 帶錯誤，**不得** fallback 成某預設版本的值。"""
    from sqlalchemy import update

    from ddm_v2.models.v2.rule_set import RuleSet

    await _make_standard_template(client, "鎖附螺絲", ["螺絲"], _CM29, "CM")
    # 全庫停用 active（隔離交易內，測後 rollback）
    await db_session.execute(update(RuleSet).values(is_active=False))
    await db_session.commit()

    _iid, j = await _map_zh(client)
    m0 = j["rows"][0]["match"]
    assert m0 is not None                     # 仍命中範本（比對不依賴 active）
    assert m0["template_name_zh"] == "鎖附螺絲"
    assert m0["computed_tmu"] is None         # 不猜版本、不 fallback（≠29）
    assert m0["computed_seconds"] is None
    assert m0["error"] is not None            # 帶可辨識錯誤
