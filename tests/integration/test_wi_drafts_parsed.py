"""解析結果寫進編輯區（ADR-038 D2／D3，W3）：真 DB＋真 app；外部 AI 用假的 port，不需要真 ai_service。

鎖住的事：
- 單句 `drafts/from-sentence`：同一句的 motion 同一組、`wi_group` 預設原句；外部 AI 成功＝ai_service（帶候選），
  沒試或降級＝rule_based；規則版本用工時表的；viewer 403；不能寫的工時表先擋，不花 AI 額度。
- 寫入檢查（取代 W1 的「AI 草稿一律不能寫入」）：解析不完整且 cycle 沒被補過 → 確認與寫入都 409 DRAFT_INCOMPLETE；
  補過就可以；外部 AI 草稿寫入後標 ai_external。
- 過期：規則版本基準不同、Excel 列輸入變了 → 寫入 409 DRAFT_STALE、整筆不寫、草稿退回待確認並記原因；重新確認後可寫入。
- 整份上傳：匯入綁了工時表時，parse job 每列解析完就寫進編輯區（帶 import_row_id，寫入後 provenance=imported）；
  重新解析取代沒人動過的草稿，有人動過的不動。
- migration v2_0053 的約束與 downgrade 拒絕條件用的計數。
"""
from __future__ import annotations

import copy
import importlib.util
import pathlib
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text

from ddm_v2.ai_integration import runtime as rt
from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.mapper import map_content
from ddm_v2.ai_integration.ports import WiParseResult
from ddm_v2.models.v2.wi_draft import WiDraftRow
from ddm_v2.models.v2.worksheet import WiRow
from ddm_v2.nlp.contracts import CycleDraft, ParseRunResult

pytestmark = pytest.mark.integration


def _load_migration():
    p = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions_v2" / "v2_0053_wi_draft_parse_meta.py"
    spec = importlib.util.spec_from_file_location("_v2_0053", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()

BUNDLE = "most-wi-motion-parse-poc003"
GM_CYCLE = {
    "seq": "GM",
    "a0": {"reach_cm": 20},
    "g2": {"g_code": "g_grasp"},
    "a3": {"reach_cm": 25},
    "p5": {"p_base_code": "p_place_none"},
}
AI_MOTION = {
    "hand": "LH",
    "seq_kind": "GM",
    "sub_activity": "左手拿取假DIMM",
    "object": "假DIMM",
    "slots": {
        "s0_A": {"kind": "reach", "magnitude_cm": 35},
        "s1_B": "b_stand",
        "s2_G": "g_pick_sel",
        "s3": {"kind": "reach", "magnitude_cm": 2.5},
        "s4": None,
        "s5": {"base": "p_hold", "addon": ["a_align"]},
        "s6_A": {"kind": "reach", "magnitude_cm": 2.5},
    },
}


class _Port:
    def __init__(self, *, fail: AiServiceErrorKind | None = None):
        self.fail = fail
        self.requests: list = []

    async def parse(self, requests, *, allow_lists, lane):
        (req,) = requests
        self.requests.append(req)
        if self.fail is not None:
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=self.fail,
                                  provenance={"request_id": "req-fail", "upstream_code": "UPSTREAM_500"})]
        motions, issues = map_content({"motions": [copy.deepcopy(AI_MOTION)]}, allow_lists)
        return [WiParseResult(item_id=req.item_id, status="ok", motions=tuple(motions), issues=tuple(issues),
                              provenance={"request_id": "req-ok", "run_id": "run-up", "bundle_code": BUNDLE,
                                          "model_served": "model-x", "prompt_version": "pv-3"})]


def _install(port):
    rt.reset_for_tests(rt.AiRuntime(parser=port, enabled=True, available=True, service_bundle_code=BUNDLE))


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch):
    import os

    for k in list(os.environ):
        if k.startswith("DDM_AI_SERVICE_"):
            monkeypatch.delenv(k, raising=False)
    rt.reset_for_tests()
    yield
    rt.reset_for_tests()


async def _seed_ws(db_session, *, status: str = "draft"):
    from ddm_v2.models.v2.org import Product, Site, Sku
    from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion
    from ddm_v2.services.v2.policy_service import LEVEL_FACTORY_V1_ID, MODELING_FACTORY_V1_ID
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set

    site = Site(id=uuid.uuid4(), external_code=f"W3-{uuid.uuid4().hex[:6]}", name_zh="W3")
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
        revision_no=1,
    )
    db_session.add(pv)
    db_session.add(ws)
    await db_session.commit()
    return ws, rs


async def _user(client, role: str | None) -> dict:
    emp = f"UT_W3_{(role or 'viewer').upper()}_{uuid.uuid4().hex[:6]}"
    r = await client.post("/api/v2/admin/users",
                          json={"employee_no": emp, "display_name": emp, "roles": [role] if role else []})
    assert r.status_code == 200, r.text
    return {"X-Username": emp}


def _error(r) -> dict:
    return r.json()["error"]


async def _from_sentence(client, ws_id, **body):
    return await client.post(f"/api/v2/worksheets/{ws_id}/drafts/from-sentence",
                             json={"text": f"拿起假DIMM放到主板座上{uuid.uuid4().hex[:4]}", **body})


async def _drafts(client, ws_id) -> list[dict]:
    r = await client.get(f"/api/v2/worksheets/{ws_id}/drafts")
    assert r.status_code == 200, r.text
    return r.json()["items"]


async def _confirm(client, ws_id, ids):
    return await client.post(f"/api/v2/worksheets/{ws_id}/drafts/confirm", json={"draft_ids": ids})


async def _commit(client, ws_id, base_revision=1):
    return await client.post(f"/api/v2/worksheets/{ws_id}/drafts/commit", json={"base_revision": base_revision})


def _result(drafts: list[CycleDraft], *, provenance: dict | None = None) -> ParseRunResult:
    """測試用的解析結果（只填 drafts_from_parse 會讀的欄位）。"""
    return ParseRunResult.model_construct(
        run_id="", plan=SimpleNamespace(actions=[]), slot_candidates=[], drafts=drafts,
        routing_status="review", routing_reasons=[], provenance=provenance or {}, source_revision=None,
    )


COMPLETE = CycleDraft(action_id="a1", cycle=dict(GM_CYCLE), complete=True,
                      engine_result={"total_tmu": 1}, narrative="完整")
INCOMPLETE = CycleDraft(action_id="a2", cycle={"seq": "GM", "a0": {"reach_cm": 20}}, complete=False,
                        issues=["missing_core_g"])


async def _backend_parsed(db_session, ws_id, drafts, *, ai_status="ai_service", import_row=None):
    from ddm_v2.services.v2 import wi_draft_service as svc

    out = await svc.add_parsed_drafts(
        db_session, ws_id, _result(drafts), text="拿起零件放到治具", hand="RH", wi_group=None,
        ai_status=ai_status, actor="IEC141289", import_row=import_row,
    )
    await db_session.commit()
    return out


# ═════════ 單句 from-sentence ═════════

async def test_sentence_without_ai_goes_in_as_one_rule_based_group(client, db_session):
    ws, _ = await _seed_ws(db_session)
    r = await _from_sentence(client, ws.id, hand="RH")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ai"]["status"] == "rule_based"
    items = body["items"]
    assert items and {d["group_key"] for d in items} == {body["group_key"]}
    assert [d["order_in_group"] for d in items] == list(range(len(items)))
    assert all(d["source"] == "rule_based" and d["status"] == "pending" for d in items)
    assert all(d["parse_snapshot"] is not None and d["content"]["hand"] == "RH" for d in items)
    sentence = items[0]["content"]["wi_group"]
    assert sentence.startswith("拿起假DIMM放到主板座上"), "wi_group 預設原句"
    assert all(d["source_rule_set_id"] is not None for d in items)


async def test_sentence_with_ai_is_ai_service_with_candidates(client, db_session):
    port = _Port()
    _install(port)
    ws, _ = await _seed_ws(db_session)
    r = await _from_sentence(client, ws.id, hand="LH", wi_group="  裝 DIMM  ")
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(port.requests) == 1
    assert body["ai"]["status"] == "ai_service" and body["ai"]["run_id"]
    items = body["items"]
    assert all(d["source"] == "ai_service" for d in items)
    assert all(d["content"]["wi_group"] == "裝 DIMM" for d in items)
    assert any(d["ai_candidates"] for d in items), "AI 候選存著，畫面才標得出哪些格是 AI 填的"
    assert all(d["ai_parse_run_id"] == body["ai"]["run_id"] for d in items)


async def test_sentence_ai_failure_degrades_to_rule_based(client, db_session):
    port = _Port(fail=AiServiceErrorKind.UNREACHABLE)
    _install(port)
    ws, _ = await _seed_ws(db_session)
    r = await _from_sentence(client, ws.id)
    assert r.status_code == 201, r.text
    assert r.json()["ai"]["status"] == "degraded"
    assert {d["source"] for d in r.json()["items"]} == {"rule_based"}


async def test_sentence_needs_analyst_and_an_editable_worksheet(client, db_session):
    port = _Port()
    _install(port)
    ws, _ = await _seed_ws(db_session)
    viewer = await _user(client, None)
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/from-sentence", json={"text": "拿起"}, headers=viewer)
    assert r.status_code == 403, r.text
    approved, _ = await _seed_ws(db_session, status="approved")
    r = await _from_sentence(client, approved.id)
    assert r.status_code == 409, r.text
    assert port.requests == [], "不能寫的工時表先擋，不花 AI 額度"
    assert (await _from_sentence(client, uuid.uuid4())).status_code == 404
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/from-sentence", json={"text": "拿起", "rule_set_code": "X"})
    assert r.status_code == 422, "規則版本取工時表的，不接受前端指定"


# ═════════ 寫入檢查 ═════════

async def test_incomplete_parse_cannot_be_confirmed_until_filled(client, db_session):
    ws, _ = await _seed_ws(db_session)
    complete, incomplete = await _backend_parsed(db_session, ws.id, [COMPLETE, INCOMPLETE])
    assert complete.parse_snapshot["complete"] is True and incomplete.parse_snapshot["complete"] is False

    r = await _confirm(client, ws.id, [str(complete.id), str(incomplete.id)])
    assert r.status_code == 409, r.text
    assert _error(r)["code"] == "DRAFT_INCOMPLETE"
    assert _error(r)["detail"]["draft_ids"] == [str(incomplete.id)]
    assert _error(r)["detail"]["incomplete_count"] == 1
    assert {d["status"] for d in await _drafts(client, ws.id)} == {"pending"}, "整筆不確認"
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/confirm", json={"group_key": complete.group_key})
    assert r.status_code == 409 and _error(r)["code"] == "DRAFT_INCOMPLETE", "整組確認也擋"

    # 只改敘述不算補齊
    content = dict(incomplete.content, narrative="改了敘述")
    assert (await client.patch(f"/api/v2/worksheet-drafts/{incomplete.id}", json={"content": content})).status_code == 200
    assert (await _confirm(client, ws.id, [str(incomplete.id)])).status_code == 409

    # 補齊 cycle → 可確認、可寫入；外部 AI 草稿寫入後標 ai_external
    content = dict(incomplete.content, cycle=dict(GM_CYCLE))
    assert (await client.patch(f"/api/v2/worksheet-drafts/{incomplete.id}", json={"content": content})).status_code == 200
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/confirm", json={"group_key": complete.group_key})
    assert r.status_code == 200, r.text
    r = await _commit(client, ws.id)
    assert r.status_code == 200, r.text
    rows = (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalars().all()
    assert len(rows) == 2 and {x.provenance for x in rows} == {"ai_external"}


async def test_commit_rechecks_incomplete_drafts(client, db_session):
    """確認的檢查被繞過（例：直接改 DB）時，寫入當下仍擋。"""
    ws, _ = await _seed_ws(db_session)
    (d,) = await _backend_parsed(db_session, ws.id, [INCOMPLETE])
    await db_session.execute(text(
        "UPDATE wi_draft_rows SET status='confirmed', confirmed_by='X', confirmed_at=NOW() WHERE id=:i"), {"i": d.id})
    await db_session.commit()
    r = await _commit(client, ws.id)
    assert r.status_code == 409 and _error(r)["code"] == "DRAFT_INCOMPLETE", r.text
    assert (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalars().all() == []


async def test_nothing_parsed_still_leaves_a_placeholder_row(db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _backend_parsed(db_session, ws.id, [], ai_status="degraded")
    assert d.source == "rule_based" and d.parse_snapshot["complete"] is False
    assert "no_motion_parsed" in d.parse_snapshot["issues"]


def test_engine_reject_counts_as_incomplete():
    from ddm_v2.services.v2.wi_draft_service import drafts_from_parse

    rejected = CycleDraft(action_id="a", cycle=dict(GM_CYCLE), complete=True, engine_result=None,
                          issues=["engine_reject_E1"])
    (p,) = drafts_from_parse(_result([rejected]), text="t", hand=None, wi_group=None, ai_status="ai_service")
    assert p.snapshot["complete"] is False


def test_long_sentence_is_truncated_for_wi_group():
    from ddm_v2.services.v2.wi_draft_service import drafts_from_parse

    (p,) = drafts_from_parse(_result([COMPLETE]), text="字" * 300, hand=None, wi_group=None, ai_status="rule_based")
    assert len(p.item.content.wi_group) == 200 and p.snapshot["wi_group_truncated"] is True


# ═════════ 過期 ═════════

async def test_rule_set_baseline_change_makes_confirmed_drafts_stale(client, db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _backend_parsed(db_session, ws.id, [COMPLETE])
    assert (await _confirm(client, ws.id, [str(d.id)])).status_code == 200
    # 模擬工時表改綁規則版本：草稿的基準與工時表不同
    await db_session.execute(text("UPDATE wi_draft_rows SET source_rule_set_id = NULL WHERE id=:i"), {"i": d.id})
    await db_session.commit()

    r = await _commit(client, ws.id)
    assert r.status_code == 409, r.text
    assert _error(r)["code"] == "DRAFT_STALE"
    assert _error(r)["detail"]["drafts"] == [{"draft_id": str(d.id), "reason": "rule_set_changed"}]
    (after,) = await _drafts(client, ws.id)
    assert after["status"] == "pending" and after["stale_reason"] == "rule_set_changed"
    assert (await client.get(f"/api/v2/worksheets/{ws.id}")).json()["revision_no"] == 1, "這次寫入整筆作廢"

    # 重新確認＝以現在的規則版本為基準 → 可寫入
    assert (await _confirm(client, ws.id, [str(d.id)])).status_code == 200
    (again,) = await _drafts(client, ws.id)
    assert again["stale_reason"] is None and again["source_rule_set_id"] == str(ws.default_rule_set_id)
    assert (await _commit(client, ws.id)).status_code == 200


async def _import_row(db_session, ws_id=None, *, description="拿起零件放到治具", hand="RH"):
    from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow

    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=ws_id, source_name="w3.xlsx", status="mapped",
                      raw_payload={"sheets": []}, sheet="Sheet1", header_row=0, column_map={"description": 0},
                      time_unit="sec", staged_rows=[{"_row": 1, "description": description, "hand": hand}],
                      imported_by="TEST")
    db_session.add(rec)
    await db_session.flush()
    row = ImportRow(id=uuid.uuid4(), import_id=rec.id, source_row_no=1,
                    normalized_data={"description": description, "hand": hand}, input_hash="h-1")
    db_session.add(row)
    await db_session.commit()
    return rec, row


async def test_changed_import_row_makes_drafts_stale_and_imported_provenance(client, db_session):
    ws, _ = await _seed_ws(db_session)
    rec, row = await _import_row(db_session)
    (d,) = await _backend_parsed(db_session, ws.id, [COMPLETE], ai_status="rule_based", import_row=row)
    assert d.import_row_id == row.id and d.parse_snapshot["import_input_hash"] == "h-1"
    assert (await _confirm(client, ws.id, [str(d.id)])).status_code == 200
    await db_session.execute(text("UPDATE import_rows SET input_hash='h-2' WHERE id=:i"), {"i": row.id})
    await db_session.commit()

    r = await _commit(client, ws.id)
    assert r.status_code == 409 and _error(r)["detail"]["drafts"][0]["reason"] == "import_row_changed", r.text
    assert (await _confirm(client, ws.id, [str(d.id)])).status_code == 200
    assert (await _commit(client, ws.id)).status_code == 200
    wr = (await db_session.execute(select(WiRow).where(WiRow.worksheet_id == ws.id))).scalar_one()
    assert wr.provenance == "imported" and wr.source_import_id == rec.id


# ═════════ 整份上傳 ═════════

async def _tick_all(client, import_id, code) -> dict:
    r = await client.post(f"/api/v2/imports/{import_id}/parse-jobs",
                          json={"rule_set_code": code, "idempotency_key": f"w3-{uuid.uuid4().hex}"})
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    body: dict = {}
    for _ in range(10):
        body = (await client.post(f"/api/v2/imports/{import_id}/parse-jobs/{job_id}/tick", json={"limit": 4})).json()
        if body["job"]["status"] in {"completed", "partial", "failed", "cancelled"}:
            break
    return body


async def test_parse_job_writes_into_the_bound_worksheet_drafts(client, db_session):
    from ddm_v2.models.v2.import_staging import ExcelImport

    ws, rs = await _seed_ws(db_session)
    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=ws.id, source_name="w3.xlsx", status="mapped",
                      raw_payload={"sheets": []}, sheet="Sheet1", header_row=0, column_map={"description": 0},
                      time_unit="sec", imported_by="TEST",
                      staged_rows=[{"_row": 1, "description": f"拿起零件{uuid.uuid4().hex[:4]}", "hand": "LH",
                                    "wi_group": "上料"},
                                   {"_row": 2, "description": f"放下零件{uuid.uuid4().hex[:4]}", "hand": "左手"}])
    db_session.add(rec)
    await db_session.commit()
    body = await _tick_all(client, rec.id, rs.code)
    assert body["job"]["processed"] == 2, body

    drafts = await _drafts(client, ws.id)
    assert drafts and all(d["import_row_id"] for d in drafts)
    assert {d["source"] for d in drafts} == {"rule_based"}, "批次的外部 AI 在 W3b"
    by_row: dict[str, list[dict]] = {}
    for d in drafts:
        by_row.setdefault(d["import_row_id"], []).append(d)
    assert len(by_row) == 2 and all(len({d["group_key"] for d in v}) == 1 for v in by_row.values())
    hands = {d["content"]["hand"] for d in drafts}
    assert hands <= {"LH", None}, "手別只收 LH／RH／BH"
    assert any(d["content"]["wi_group"] == "上料" for d in drafts), "Excel 的作業名稱欄優先"
    assert all(d["parse_snapshot"]["import_input_hash"] for d in drafts)


async def test_reparse_replaces_untouched_drafts_and_keeps_touched_ones(client, db_session):
    from ddm_v2.models.v2.import_staging import ExcelImport

    ws, rs = await _seed_ws(db_session)
    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=ws.id, source_name="w3.xlsx", status="mapped",
                      raw_payload={"sheets": []}, sheet="Sheet1", header_row=0, column_map={"description": 0},
                      time_unit="sec", imported_by="TEST",
                      staged_rows=[{"_row": 1, "description": f"拿起零件{uuid.uuid4().hex[:4]}"},
                                   {"_row": 2, "description": f"放下零件{uuid.uuid4().hex[:4]}"}])
    db_session.add(rec)
    await db_session.commit()
    await _tick_all(client, rec.id, rs.code)
    first = await _drafts(client, ws.id)
    row_ids = sorted({d["import_row_id"] for d in first})
    touched = next(d for d in first if d["import_row_id"] == row_ids[0])
    content = dict(touched["content"], narrative="人改過")
    assert (await client.patch(f"/api/v2/worksheet-drafts/{touched['id']}", json={"content": content})).status_code == 200

    # 再解析一次同一列（直接呼叫服務，模擬重新解析）
    from ddm_v2.models.v2.import_staging import ImportRow
    from ddm_v2.services.v2 import wi_draft_service as svc

    for rid in row_ids:
        row = await db_session.get(ImportRow, uuid.UUID(rid))
        await svc.add_parsed_drafts(db_session, ws.id, _result([COMPLETE]), text="x", hand=None, wi_group=None,
                                    ai_status="rule_based", actor="IEC141289", import_row=row)
    await db_session.commit()
    second = await _drafts(client, ws.id)
    kept = [d for d in second if d["import_row_id"] == row_ids[0]]
    assert {d["id"] for d in kept} == {d["id"] for d in first if d["import_row_id"] == row_ids[0]}, "人動過的不動"
    replaced = [d for d in second if d["import_row_id"] == row_ids[1]]
    assert len(replaced) == 1 and replaced[0]["content"]["narrative"] == "完整", "沒人動過的被新結果取代"


async def test_parse_job_into_approved_worksheet_notes_it_and_still_finishes(client, db_session):
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.models.v2.import_staging import ExcelImport

    ws, rs = await _seed_ws(db_session, status="approved")
    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=ws.id, source_name="w3.xlsx", status="mapped",
                      raw_payload={"sheets": []}, sheet="Sheet1", header_row=0, column_map={"description": 0},
                      time_unit="sec", imported_by="TEST",
                      staged_rows=[{"_row": 1, "description": f"拿起零件{uuid.uuid4().hex[:4]}"}])
    db_session.add(rec)
    await db_session.commit()
    body = await _tick_all(client, rec.id, rs.code)
    assert body["job"]["processed"] == 1 and body["job"]["failed"] == 0, body
    assert (await db_session.execute(select(WiDraftRow).where(WiDraftRow.worksheet_id == ws.id))).scalars().all() == []
    items = (await db_session.execute(
        select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(body["job"]["id"])))).scalars().all()
    assert items[0].last_error["drafts"] == {"written": 0, "reason": "NotEditable"}


# ═════════ migration ═════════

async def test_migration_constraint_and_downgrade_count(db_session):
    ws, _ = await _seed_ws(db_session)
    (d,) = await _backend_parsed(db_session, ws.id, [COMPLETE])
    with pytest.raises(Exception, match="ck_wi_draft_rows_stale_reason"):
        await db_session.execute(text("UPDATE wi_draft_rows SET stale_reason='bogus' WHERE id=:i"), {"i": d.id})
    await db_session.rollback()
    assert (await db_session.execute(text(MIG.SQL_COUNT_META))).scalar_one() >= 1


async def test_full_workspace_is_refused_before_spending_ai_quota(client, db_session, monkeypatch):
    from ddm_v2.services.v2 import wi_draft_service as svc

    port = _Port()
    _install(port)
    ws, _ = await _seed_ws(db_session)
    monkeypatch.setattr(svc, "MAX_DRAFTS_PER_WORKSHEET", 0)
    r = await _from_sentence(client, ws.id)
    assert r.status_code == 422, r.text
    assert port.requests == [], "編輯區滿了先擋，不花 AI 額度"


async def test_parse_job_with_another_rule_set_does_not_write_drafts(client, db_session):
    from ddm_v2.models.v2.ai_ops import AiParseJobItem
    from ddm_v2.models.v2.import_staging import ExcelImport
    from ddm_v2.models.v2.rule_set import RuleSet

    ws, rs = await _seed_ws(db_session)
    other = (await db_session.execute(select(RuleSet).where(RuleSet.id != rs.id).limit(1))).scalar_one_or_none()
    if other is None:
        pytest.skip("DB 只有一個 rule_set")
    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=ws.id, source_name="w3.xlsx", status="mapped",
                      raw_payload={"sheets": []}, sheet="Sheet1", header_row=0, column_map={"description": 0},
                      time_unit="sec", imported_by="TEST",
                      staged_rows=[{"_row": 1, "description": f"拿起零件{uuid.uuid4().hex[:4]}"}])
    db_session.add(rec)
    await db_session.commit()
    body = await _tick_all(client, rec.id, other.code)
    if body.get("job") is None:
        pytest.skip(f"另一個 rule_set 不能建 job：{body}")
    assert (await db_session.execute(select(WiDraftRow).where(WiDraftRow.worksheet_id == ws.id))).scalars().all() == []
    items = (await db_session.execute(
        select(AiParseJobItem).where(AiParseJobItem.job_id == uuid.UUID(body["job"]["id"])))).scalars().all()
    assert items[0].last_error["drafts"]["reason"] == "rule_set_mismatch"


# ═════════ 降級原因與快取規則（2026-11-24 真實量測後） ═════════

class _VersionedPort(_Port):
    """可切換 prompt_version 與是否回空 motions 的假 port。"""

    def __init__(self):
        super().__init__()
        self.prompt_version = "pv-3"
        self.empty = False

    async def parse(self, requests, *, allow_lists, lane):
        (req,) = requests
        self.requests.append(req)
        raw = {"motions": []} if self.empty else {"motions": [copy.deepcopy(AI_MOTION)]}
        try:
            motions, issues = map_content(raw, allow_lists)
        except Exception as exc:  # noqa: BLE001  同 adapter：mapper 的 AiServiceError 轉成 failed
            from ddm_v2.ai_integration.errors import AiServiceError

            assert isinstance(exc, AiServiceError)
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=exc.kind,
                                  provenance={"request_id": "req-x", "upstream_code": exc.upstream_code})]
        return [WiParseResult(item_id=req.item_id, status="ok", motions=tuple(motions), issues=tuple(issues),
                              provenance={"request_id": "req-ok", "run_id": f"run-{uuid.uuid4().hex[:6]}",
                                          "bundle_code": BUNDLE, "model_served": "model-x",
                                          "prompt_version": self.prompt_version})]


async def test_no_motion_degrades_with_a_readable_reason(client, db_session):
    port = _VersionedPort()
    port.empty = True
    _install(port)
    ws, _ = await _seed_ws(db_session)
    r = await client.post(f"/api/v2/worksheets/{ws.id}/drafts/from-sentence", json={"text": "依照SOP完成其餘作業"})
    assert r.status_code == 201, r.text
    ai = r.json()["ai"]
    assert ai["status"] == "degraded"
    assert ai["reason"] == {"error_kind": "no_motion", "upstream_code": "NO_MOTION"}
    assert r.json()["items"], "降級的結果照樣進編輯區"


async def test_cache_misses_after_ai_service_changes_prompt_version(client, db_session):
    port = _VersionedPort()
    _install(port)
    ws, _ = await _seed_ws(db_session)
    url = f"/api/v2/worksheets/{ws.id}/drafts/from-sentence"
    a, b = f"左手拿起螺絲{uuid.uuid4().hex[:4]}", f"右手放下螺絲{uuid.uuid4().hex[:4]}"
    assert (await client.post(url, json={"text": a})).status_code == 201
    assert (await client.post(url, json={"text": a})).status_code == 201
    assert len(port.requests) == 1, "同一版本：第二次命中快取"
    port.prompt_version = "pv-4"
    assert (await client.post(url, json={"text": b})).status_code == 201  # 新句子外送，得知版本變了
    assert len(port.requests) == 2
    assert (await client.post(url, json={"text": a})).status_code == 201
    assert len(port.requests) == 3, "版本變了之後舊快取不再命中"
    assert (await client.post(url, json={"text": a})).status_code == 201
    assert len(port.requests) == 3, "新版本的結果又會被快取"


async def test_operational_degrade_reasons_hide_the_code(client, db_session):
    """維運類分類（例：回應形狀不符）回前端只有分類，不帶內部代碼。"""
    from ddm_v2.ai_integration.errors import AiServiceErrorKind

    class _Broken(_Port):
        async def parse(self, requests, *, allow_lists, lane):
            (req,) = requests
            self.requests.append(req)
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=AiServiceErrorKind.CONTRACT_MISMATCH,
                                  provenance={"request_id": "req-b", "upstream_code": "MAPPER_REJECTED"})]

    _install(_Broken())
    ws, _ = await _seed_ws(db_session)
    r = await _from_sentence(client, ws.id)
    assert r.status_code == 201, r.text
    assert r.json()["ai"]["reason"] == {"error_kind": "contract_mismatch", "upstream_code": None}


async def test_no_reason_when_not_degraded(client, db_session):
    ws, _ = await _seed_ws(db_session)
    r = await _from_sentence(client, ws.id)
    assert r.json()["ai"]["status"] == "rule_based" and r.json()["ai"]["reason"] is None
