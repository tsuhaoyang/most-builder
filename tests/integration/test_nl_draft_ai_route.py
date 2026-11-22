"""nl-draft 路由接上外部 ai_service（ADR-037 S3）＋ GET /wi-ai/status：真 DB＋真 app＋假 port。

鎖住的事（RBAC 矩陣）：
- viewer：永遠 rule_based、不外送；/wi-ai/status 看得到。
- analyst 以上＋整合可用：走外部；`ai.status` 依結果是 ai_service／degraded。
- 整合關閉或設定不合格：任何角色都 rule_based、不外送。
- `scope`＝worksheet 所屬站點（沒 worksheet＝"none"）；`hand` 傳進 known_hand。
- 失敗外送的 request_id 寫進 run.error，**不**出現在回應裡。
- status 只回 enabled／available。
"""
from __future__ import annotations

import copy
import uuid

import pytest
from sqlalchemy import select, text

from ddm_v2.ai_integration import runtime as rt
from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.mapper import map_content
from ddm_v2.ai_integration.ports import WiParseResult
from ddm_v2.models.v2.ai_ops import AiParseRun

pytestmark = pytest.mark.integration

BUNDLE = "most-wi-motion-parse-poc003"
GM = {
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
    def __init__(self, *, fail: AiServiceErrorKind | None = None, request_id: str = "req-fail-1"):
        self.fail, self.request_id = fail, request_id
        self.requests: list = []

    async def parse(self, requests, *, allow_lists, lane):
        (req,) = requests
        self.requests.append(req)
        if self.fail is not None:
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=self.fail,
                                  provenance={"request_id": self.request_id, "upstream_code": "UPSTREAM_500"})]
        motions, issues = map_content({"motions": [copy.deepcopy(GM)]}, allow_lists)
        return [WiParseResult(item_id=req.item_id, status="ok", motions=tuple(motions), issues=tuple(issues),
                              provenance={"request_id": "req-ok-1", "run_id": "run-up-1", "bundle_code": BUNDLE,
                                          "model_served": "model-x", "prompt_version": "pv-3"})]


def _install(port, *, enabled=True, available=True):
    rt.reset_for_tests(rt.AiRuntime(parser=port, enabled=enabled, available=available,
                                    service_bundle_code=BUNDLE if available else None))


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch):
    # 不依賴開發機／CI 的環境：清掉 DDM_AI_SERVICE_*，沒明確安裝 runtime 的測試就是「整合關閉」
    import os

    for k in list(os.environ):
        if k.startswith("DDM_AI_SERVICE_"):
            monkeypatch.delenv(k, raising=False)
    rt.reset_for_tests()
    yield
    rt.reset_for_tests()


async def _rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set")
    return r.json()[0]["code"]


async def _user(client, role: str | None) -> dict:
    """role=None：第一次出現的人（JIT 建帳成 viewer）。role="viewer"：admin 建好、但沒有任何角色（＝viewer）。"""
    emp = f"UT_WIAI_{(role or 'jit').upper()}_{uuid.uuid4().hex[:6]}"
    if role is not None:
        roles = [] if role == "viewer" else [role]
        r = await client.post("/api/v2/admin/users", json={"employee_no": emp, "display_name": emp, "roles": roles})
        assert r.status_code == 200, r.text
    return {"X-Username": emp}


def _text() -> str:
    return f"拿起假DIMM放到主板座上{uuid.uuid4().hex[:6]}"


async def _draft(client, headers, **extra):
    body = {"text": _text(), "rule_set_code": await _rs_code(client), **extra}
    r = await client.post("/api/v2/worksheets/nl-draft", json=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _a_worksheet_and_its_site(db_session) -> tuple[str, str]:
    row = (
        await db_session.execute(
            text(
                "SELECT w.id, p.site_id FROM most_worksheets w "
                "JOIN process_versions v ON v.id = w.process_version_id "
                "JOIN skus s ON s.id = v.sku_id JOIN products p ON p.id = s.product_id LIMIT 1"
            )
        )
    ).first()
    if row is None:
        pytest.skip("DB 無 worksheet")
    return str(row.id), str(row.site_id)


# ═════════ RBAC 矩陣 ═════════

@pytest.mark.parametrize("role", [None, "viewer"])
async def test_a_viewer_never_triggers_a_send(client, role):
    port = _Port()
    _install(port)
    body = await _draft(client, await _user(client, role))
    assert port.requests == [], "viewer 只走 rule_based，不外送"
    assert body["ai"]["status"] == "rule_based" and "ai_error" not in body["ai"]["provenance"]


@pytest.mark.parametrize("role", ["analyst", "approver", "admin"])
async def test_analyst_and_above_go_through_ai_service(client, role):
    port = _Port()
    _install(port)
    body = await _draft(client, await _user(client, role))
    assert len(port.requests) == 1
    assert body["ai"]["status"] == "ai_service" and body["ai"]["provenance"]["planner"] == "ai_service"
    assert all(c["chosen"] is None for c in body["ai"]["slot_candidates"])
    assert body["ai"]["routing_status"] == "review"


@pytest.mark.parametrize(("enabled", "available"), [(False, False), (True, False)])
async def test_nobody_sends_when_the_integration_is_off_or_misconfigured(client, enabled, available):
    port = _Port()
    _install(port, enabled=enabled, available=available)
    for role in ("analyst", "admin"):
        body = await _draft(client, await _user(client, role))
        assert body["ai"]["status"] == "rule_based"
    assert port.requests == []


async def test_default_environment_has_ai_off_and_the_rule_path_unchanged(client):
    body = await _draft(client, await _user(client, "analyst"))  # 沒有安裝 runtime：讀測試環境（未設 DDM_AI_SERVICE_*）
    assert body["ai"]["status"] == "rule_based" and body["ai"]["provenance"]["planner"] == "rule_based_v1"
    assert "slots" in body and "multi_action_warning" in body, "舊回應形狀不變"


# ═════════ 降級與 request_id ═════════

async def test_a_failed_send_degrades_and_keeps_the_request_id_only_in_the_run(client, db_session):
    _install(_Port(fail=AiServiceErrorKind.UPSTREAM, request_id="req-fail-xyz"))
    body = await _draft(client, await _user(client, "analyst"))
    assert body["ai"]["status"] == "degraded"
    assert body["ai"]["provenance"]["ai_error"]["error_kind"] == "upstream"
    assert "req-fail-xyz" not in str(body), "request_id 不回前端"
    run = (await db_session.execute(select(AiParseRun).where(AiParseRun.id == uuid.UUID(body["ai"]["run_id"])))).scalar_one()
    assert run.error["ai_service"]["request_id"] == "req-fail-xyz", "v1 外送紀錄：失敗也能和 ai_service 對帳"
    assert run.created_by.startswith("UT_WIAI_ANALYST_")


async def test_a_successful_send_is_recorded_in_ai_parse_runs(client, db_session):
    _install(_Port())
    headers = await _user(client, "analyst")
    body = await _draft(client, headers)
    run = (await db_session.execute(select(AiParseRun).where(AiParseRun.id == uuid.UUID(body["ai"]["run_id"])))).scalar_one()
    assert run.created_by == headers["X-Username"] and run.upstream_run_id == "run-up-1"
    assert run.provenance["request_id"] == "req-ok-1" and run.provenance["bundle_code"] == BUNDLE


# ═════════ scope 與 hand ═════════

async def test_scope_is_the_worksheet_site_and_none_without_a_worksheet(client, db_session):
    ws_id, site_id = await _a_worksheet_and_its_site(db_session)
    port = _Port()
    _install(port)
    headers = await _user(client, "analyst")
    await _draft(client, headers, worksheet_id=ws_id)
    await _draft(client, headers)
    assert [r.scope for r in port.requests] == [site_id, "none"]
    assert all(r.actor == headers["X-Username"] for r in port.requests)


async def test_an_unknown_worksheet_does_not_fail_and_uses_no_scope(client):
    port = _Port()
    _install(port)
    await _draft(client, await _user(client, "analyst"), worksheet_id=str(uuid.uuid4()))
    assert port.requests[0].scope == "none"


async def test_hand_is_passed_as_the_known_hand(client):
    _install(_Port())
    headers = await _user(client, "analyst")
    mismatch = await _draft(client, headers, hand="RH")  # ai_service 給的是 LH
    no_hand = await _draft(client, headers)
    assert "ai_hand_hint_mismatch" in mismatch["ai"]["routing_reasons"]
    assert "ai_hand_hint_mismatch" not in no_hand["ai"]["routing_reasons"]


async def test_an_invalid_hand_is_rejected_with_the_error_envelope(client):
    r = await client.post("/api/v2/worksheets/nl-draft",
                          json={"text": _text(), "rule_set_code": await _rs_code(client), "hand": "XX"})
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"error"} and body["error"]["code"] == "VALIDATION_ERROR", "ADR-034 錯誤信封"


# ═════════ GET /wi-ai/status ═════════

@pytest.mark.parametrize(("enabled", "available"), [(True, True), (True, False), (False, False)])
async def test_status_reports_enabled_and_available_only(client, enabled, available):
    _install(_Port(), enabled=enabled, available=available)
    r = await client.get("/api/v2/wi-ai/status", headers=await _user(client, None))
    assert r.status_code == 200
    assert r.json() == {"enabled": enabled, "available": available}


async def test_status_does_not_send_anything(client):
    port = _Port()
    _install(port)
    for _ in range(3):
        await client.get("/api/v2/wi-ai/status")
    assert port.requests == []


async def test_status_requires_a_logged_in_user(client):
    import os

    from httpx import ASGITransport, AsyncClient

    from ddm_v2.main import create_app
    saved = os.environ.pop("AUTH_DEV_USER", None)
    try:
        async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as anon:
            r = await anon.get("/api/v2/wi-ai/status")
            assert r.status_code == 401
            # ADR-034 §測試契約：auth 層的 401／403 走 FastAPI 原生 HTTPException（頂層 `detail`），不是 DomainError 信封
            assert set(r.json()) == {"detail"}
    finally:
        if saved is not None:
            os.environ["AUTH_DEV_USER"] = saved


# ═════════ 審查後補強 ═════════

@pytest.mark.parametrize("kind", ["empty", "bundle", "plan"])
async def test_failures_after_the_call_also_keep_the_request_id(client, db_session, monkeypatch, kind):
    """ai_service 已回應（已計費）才降級的三條路徑，也要能和 ai_service 對帳。"""
    from ddm_v2.services.v2 import wi_ai_service as svc

    class _After(_Port):
        async def parse(self, requests, *, allow_lists, lane):
            (req,) = requests
            self.requests.append(req)
            prov = {"request_id": "req-after-1", "run_id": "run-x", "bundle_code": "other" if kind == "bundle" else BUNDLE}
            if kind == "empty":
                return [WiParseResult(item_id=req.item_id, status="ok", provenance=prov)]
            motions, issues = map_content({"motions": [copy.deepcopy(GM)]}, allow_lists)
            return [WiParseResult(item_id=req.item_id, status="ok", motions=tuple(motions), provenance=prov)]

    if kind == "plan":
        monkeypatch.setattr(svc, "validate_provenance", lambda _p: (_ for _ in ()).throw(ValueError("bad")))
    _install(_After())
    body = await _draft(client, await _user(client, "analyst"))
    assert body["ai"]["status"] == "degraded" and "req-after-1" not in str(body)
    run = (await db_session.execute(select(AiParseRun).where(AiParseRun.id == uuid.UUID(body["ai"]["run_id"])))).scalar_one()
    assert run.error["ai_service"]["request_id"] == "req-after-1"


async def test_a_viewer_does_not_even_build_the_runtime(client, monkeypatch):
    built = {"n": 0}
    real = rt._build

    def counting():
        built["n"] += 1
        return real()

    monkeypatch.setattr(rt, "_build", counting)
    await _draft(client, await _user(client, None))
    assert built["n"] == 0, "viewer 連 runtime 都不碰（不會觸發 DNS）"
