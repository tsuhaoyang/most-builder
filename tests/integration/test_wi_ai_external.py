"""wi_ai_service 外部 ai_service 路徑（ADR-037 S3 PR-B）：真 DB＋假 port。

鎖住的事：
- 成功：run 綁佔位 bundle、provenance 過 allow-list、`chosen` 為空、預覽 draft 帶旗標、一律 review。
- 快取鍵含設定的 ai_service bundle code：命中不呼叫 port；換 bundle 就 miss。
- 任何失敗都降級回 rule_based，不拋給呼叫端，且留下原因。
- 呼叫 port 之前已結束交易（ADR-037 D8：不占用 DB 連線）。
- `external=None` 與先前行為相同（既有測試涵蓋；這裡只確認它不被影響）。
"""
from __future__ import annotations

import copy
import logging
import uuid

import pytest
from sqlalchemy import select, text

from ddm_v2.ai_integration.adapter import DisabledWiParser
from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.guard import GuardedWiParser
from ddm_v2.ai_integration.mapper import map_content
from ddm_v2.ai_integration.ports import WiParseResult
from ddm_v2.models.v2.ai_ops import AiParseRun
from ddm_v2.services.v2 import wi_ai_service as svc
from ddm_v2.services.v2.wi_ai_service import EXTERNAL_BUNDLE_CODE, ExternalAi

pytestmark = pytest.mark.integration

RULE_SET = "MINIMOST_FACTORY_V2"
CFG_BUNDLE = "most-wi-motion-parse-poc003"

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
GOOD_PROVENANCE = {
    "request_id": "req-1",
    "run_id": "run-up-1",
    "bundle_code": CFG_BUNDLE,
    "bundle_status": "shadow",
    "model_served": "model-x",
    "prompt_variant": "zh",
    "prompt_version": "pv-3",
    "retry_count": 0,
    "attempts": 1,
    "latency_ms": 120,
}


def _unique_text(tag: str = "") -> str:
    return f"拿起假DIMM放到主板座上{tag}{uuid.uuid4().hex[:6]}"


class _Port:
    """假 port：回真的 `map_content` 結果；可注入失敗、例外、額外（不該被存的）出處鍵。"""

    def __init__(self, *, content=None, fail=None, exc=None, empty=False, provenance=None, probe=None):
        self.content = content if content is not None else {"motions": [copy.deepcopy(GM)]}
        self.fail, self.exc, self.empty = fail, exc, empty
        self.provenance = dict(provenance if provenance is not None else GOOD_PROVENANCE)
        self.probe = probe
        self.calls: list = []
        self.in_txn: list[bool] = []

    async def parse(self, requests, *, allow_lists, lane):
        self.calls.append((requests, lane))
        if self.probe is not None:
            self.in_txn.append(self.probe())
        if self.exc is not None:
            raise self.exc
        (req,) = requests
        if self.fail is not None:
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=self.fail,
                                  provenance={"upstream_code": "QUOTA_X"})]
        if self.empty:
            return [WiParseResult(item_id=req.item_id, status="ok", provenance=self.provenance)]
        motions, issues = map_content(self.content, allow_lists)
        return [WiParseResult(item_id=req.item_id, status="ok", motions=tuple(motions), issues=tuple(issues),
                              provenance=self.provenance)]


def _ext(port, *, bundle=CFG_BUNDLE, known_hand=None, scope="site-1") -> ExternalAi:
    return ExternalAi(port=port, service_bundle_code=bundle, actor="IEC141289", scope=scope, known_hand=known_hand)


async def _parse(db_session, text_in, external, **kw):
    return await svc.parse_interactive(
        db_session, text=text_in, rule_set_code=RULE_SET, created_by="IEC141289", external=external, **kw
    )


async def _external_runs(db_session) -> list[AiParseRun]:
    q = await db_session.execute(select(AiParseRun).where(AiParseRun.upstream_run_id.is_not(None)))
    return list(q.scalars())


# ═════════ 成功 ═════════

async def test_success_stores_an_external_run_with_candidates_only(db_session):
    port = _Port()
    result, legacy = await _parse(db_session, _unique_text(), _ext(port))
    assert result.provenance["planner"] == "ai_service" and result.provenance["fallback"] is False
    assert result.provenance["deployment_bundle_code"] == CFG_BUNDLE
    assert result.provenance["model"] == "model-x" and result.provenance["prompt_version"] == "pv-3"
    assert result.provenance["ai_run_id"] == "run-up-1" and result.provenance["cached"] is False
    assert all(c.chosen is None for c in result.slot_candidates), "AI 的 code 只是候選"
    assert {t.source for c in result.slot_candidates for t in c.top_k} == {"ai_service"}
    assert result.drafts and all("ai_candidate_preview" in d.issues for d in result.drafts)
    assert result.routing_status == "review" and "ai_source_no_evidence" in result.routing_reasons
    assert port.calls[0][1] == "interactive"
    assert legacy["provenance"]["parser"] == "ai_service" and legacy["provenance"]["slots_parser"] == "rule_based_v1"

    (run,) = await _external_runs(db_session)
    assert run.upstream_run_id == "run-up-1" and run.fallback is False and run.llm_raw_response is None
    bundle = (await db_session.execute(text("SELECT code, kind FROM ai_deployment_bundles WHERE id = :i"), {"i": run.bundle_id})).one()
    assert (bundle.code, bundle.kind) == (EXTERNAL_BUNDLE_CODE, "external")


async def test_engine_gate_runs_on_the_preview_drafts(db_session):
    result, _ = await _parse(db_session, _unique_text(), _ext(_Port()))
    complete = [d for d in result.drafts if d.complete]
    assert complete and all(d.engine_result is not None for d in complete), "TMU 只來自引擎，且確實算過"


async def test_the_request_to_the_port_carries_no_identity_beyond_the_sentence(db_session):
    port = _Port()
    await _parse(db_session, _unique_text(), _ext(port))
    (req,) = port.calls[0][0]
    assert req.context == {} and req.actor == "IEC141289" and req.scope == "site-1"
    # actor／scope 只給 MOST 端的配額與合併用，由 adapter 保證不外送（見 test_ai_adapter）；這裡確認 context 空


# ═════════ provenance allow-list ═════════

async def test_only_allow_listed_provenance_keys_are_stored(db_session):
    dirty = {**GOOD_PROVENANCE, "api_key": "SECRET-KEY", "employee_no": "E123", "raw_text": "原文", "error_message": "boom"}
    await _parse(db_session, _unique_text(), _ext(_Port(provenance=dirty)))
    (run,) = await _external_runs(db_session)
    stored = set(run.provenance)
    assert {"api_key", "employee_no", "raw_text", "error_message"}.isdisjoint(stored)
    assert stored <= {"request_id", "run_id", "bundle_code", "bundle_status", "model_served", "prompt_variant",
                      "prompt_version", "retry_count", "attempts", "latency_ms", "motion_labels", "dropped"}
    assert "SECRET-KEY" not in str(run.provenance)


async def test_oversized_provenance_values_are_dropped(db_session):
    # 非純量值連 `WiParseResult` 的型別都過不了；過長字串型別上合法，所以由 allow-list 這層擋
    dirty = {**GOOD_PROVENANCE, "model_served": "x" * 500}
    await _parse(db_session, _unique_text(), _ext(_Port(provenance=dirty)))
    (run,) = await _external_runs(db_session)
    assert "model_served" not in run.provenance and run.provenance["prompt_version"] == "pv-3"


async def test_motion_labels_and_dropped_are_stored_for_the_review_screen(db_session):
    motion = copy.deepcopy(GM)
    motion["slots"]["s4"] = "b_eye"  # b4：compile 放不下
    result, _ = await _parse(db_session, _unique_text(), _ext(_Port(content={"motions": [motion]})))
    (run,) = await _external_runs(db_session)
    assert run.provenance["motion_labels"] == [
        {"action_id": "a1", "sub_activity": "左手拿取假DIMM", "object_text": "假DIMM", "hand_hint": "LH"}
    ]
    assert "a1:b4" in run.provenance["dropped"] and "a1:a0.magnitude_hint" in run.provenance["dropped"]
    assert result.provenance["dropped"] == run.provenance["dropped"]


# ═════════ 快取鍵與重播 ═════════

async def test_same_request_is_served_from_the_run_without_calling_the_port(db_session):
    port = _Port()
    t = _unique_text()
    first, _ = await _parse(db_session, t, _ext(port))
    second, legacy2 = await _parse(db_session, t, _ext(port))
    assert len(port.calls) == 1, "命中快取不呼叫 ai_service（也不扣額度）"
    assert second.run_id == first.run_id and second.provenance["cached"] is True
    assert second.provenance["planner"] == "ai_service" and second.provenance["ai_run_id"] == "run-up-1"
    assert second.provenance["model"] == "model-x" and second.provenance["motion_labels"] == first.provenance["motion_labels"]
    assert [d.model_dump() for d in second.drafts] == [d.model_dump() for d in first.drafts]
    assert legacy2["provenance"]["slots_parser"] == "ai_candidates"


async def test_a_different_configured_bundle_code_misses_the_cache(db_session):
    t = _unique_text()
    p1, p2 = _Port(), _Port(provenance={**GOOD_PROVENANCE, "run_id": "run-up-2", "bundle_code": "bundle-v2"})
    r1, _ = await _parse(db_session, t, _ext(p1, bundle=CFG_BUNDLE))
    r2, _ = await _parse(db_session, t, _ext(p2, bundle="bundle-v2"))
    assert len(p1.calls) == 1 and len(p2.calls) == 1, "換 ai_service bundle（換 prompt）要重新呼叫"
    assert r1.run_id != r2.run_id and r2.provenance["deployment_bundle_code"] == "bundle-v2"


async def test_worksheet_revision_is_part_of_the_key_like_the_rule_path(db_session):
    port = _Port()
    t = _unique_text()
    await _parse(db_session, t, _ext(port))
    await _parse(db_session, t, _ext(port), worksheet_id=uuid.uuid4())  # 不存在的 worksheet：key 不同
    assert len(port.calls) == 2


# ═════════ 降級 ═════════

async def _assert_degraded(db_session, result, legacy, *, kind, code=None):
    """回應只帶粗粒度的 ai_error（維運類分類不帶 upstream_code）；完整代碼在 `run.error`。"""
    assert result.provenance["planner"] == "rule_based_v1" and result.provenance["fallback"] is True
    assert result.provenance["ai_error"]["error_kind"] == kind
    assert legacy["provenance"]["ai_error"] == result.provenance["ai_error"]
    assert await _external_runs(db_session) == [], "失敗不留外部 run"
    run = (await db_session.execute(select(AiParseRun).where(AiParseRun.id == uuid.UUID(result.run_id)))).scalar_one()
    assert run.fallback is True and run.error["ai_service"]["error_kind"] == kind
    if code is not None:
        assert run.error["ai_service"]["upstream_code"] == code


async def test_a_failed_result_degrades_to_rule_based_and_records_why(db_session):
    result, legacy = await _parse(db_session, _unique_text(), _ext(_Port(fail=AiServiceErrorKind.QUOTA_EXCEEDED)))
    await _assert_degraded(db_session, result, legacy, kind="quota_exceeded")
    assert result.provenance["ai_error"]["upstream_code"] == "QUOTA_X"


@pytest.mark.parametrize("exc", [ValueError("actor missing"), RuntimeError("schema hash mismatch")])
async def test_value_and_runtime_errors_from_the_guard_degrade_and_log_an_error(db_session, caplog, exc):
    with caplog.at_level(logging.ERROR):
        result, legacy = await _parse(db_session, _unique_text(), _ext(_Port(exc=exc)))
    await _assert_degraded(db_session, result, legacy, kind="misconfigured", code=type(exc).__name__.upper())
    assert result.provenance["ai_error"]["upstream_code"] is None, "維運類分類：完整代碼不回前端"
    assert any(r.levelno == logging.ERROR for r in caplog.records), "對使用者降級，對維運大聲"


async def test_an_unexpected_exception_from_the_port_still_degrades(db_session):
    result, legacy = await _parse(db_session, _unique_text(), _ext(_Port(exc=KeyError("boom"))))
    await _assert_degraded(db_session, result, legacy, kind="internal_error")


async def test_an_ok_result_without_motions_degrades(db_session):
    result, legacy = await _parse(db_session, _unique_text(), _ext(_Port(empty=True)))
    await _assert_degraded(db_session, result, legacy, kind="empty_result")


async def test_a_disabled_integration_degrades_quietly(db_session, caplog):
    with caplog.at_level(logging.WARNING):
        result, legacy = await _parse(db_session, _unique_text(), _ext(DisabledWiParser()))
    await _assert_degraded(db_session, result, legacy, kind="disabled")
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING and "external" in r.getMessage()]


async def test_the_real_guard_with_a_missing_actor_degrades_instead_of_raising(db_session):
    guard = GuardedWiParser(_Port(), bundle_code=CFG_BUNDLE, concurrency={"interactive": 2, "batch": 1},
                            per_user_per_minute=30, daily_budget=2000)
    ext = ExternalAi(port=guard, service_bundle_code=CFG_BUNDLE, actor="", scope="site-1")
    result, legacy = await _parse(db_session, _unique_text(), ext)
    await _assert_degraded(db_session, result, legacy, kind="misconfigured")


async def test_a_missing_external_bundle_degrades_as_misconfigured(db_session, caplog):
    await db_session.execute(text("DELETE FROM ai_deployment_bundles WHERE code = :c"), {"c": EXTERNAL_BUNDLE_CODE})
    with caplog.at_level(logging.ERROR):
        result, legacy = await _parse(db_session, _unique_text(), _ext(_Port()))
    await _assert_degraded(db_session, result, legacy, kind="misconfigured", code="EXTERNAL_BUNDLE_MISSING")


async def test_a_degraded_request_is_not_cached_so_the_next_one_tries_ai_again(db_session):
    t = _unique_text()
    bad, good = _Port(fail=AiServiceErrorKind.TIMEOUT), _Port()
    await _parse(db_session, t, _ext(bad))
    result, _ = await _parse(db_session, t, _ext(good))
    assert len(good.calls) == 1 and result.provenance["planner"] == "ai_service"


# ═════════ 連線、手別、界線 ═════════

async def test_the_transaction_is_closed_before_the_port_is_called(db_session):
    port = _Port(probe=db_session.in_transaction)
    await _parse(db_session, _unique_text(), _ext(port))
    assert port.in_txn == [False], "ADR-037 D8：呼叫 ai_service 期間不占用 DB 連線"


async def test_hand_hint_is_compared_only_when_the_known_hand_is_given(db_session):
    mismatch, _ = await _parse(db_session, _unique_text(), _ext(_Port(), known_hand="RH"))
    assert "ai_hand_hint_mismatch" in mismatch.routing_reasons
    no_source, _ = await _parse(db_session, _unique_text(), _ext(_Port(), known_hand=None))
    assert "ai_hand_hint_mismatch" not in no_source.routing_reasons
    assert no_source.provenance["motion_labels"][0]["hand_hint"] == "LH", "沒有來源可比對時只留提示，不標"


async def test_an_ai_result_is_never_auto_even_when_the_auto_flag_is_on(db_session, monkeypatch):
    import dataclasses

    from ddm_v2.nlp import routing
    from ddm_v2.settings import get_settings

    on = dataclasses.replace(get_settings(), wi_ai_auto_enabled=True)  # Settings 是 frozen：換掉整份
    monkeypatch.setattr(svc, "get_settings", lambda: on)
    monkeypatch.setattr(routing, "get_settings", lambda: on)
    result, _ = await _parse(db_session, _unique_text(), _ext(_Port()))
    assert result.routing_status == "review"


async def test_external_path_supports_interactive_only_and_respects_the_length_limit(db_session):
    with pytest.raises(ValueError, match="interactive"):
        await _parse(db_session, _unique_text(), _ext(_Port()), source_kind="import_row")
    with pytest.raises(svc.TextTooLong):
        await _parse(db_session, "長" * 2001, _ext(_Port()))


async def test_without_external_the_rule_path_is_untouched(db_session):
    result, legacy = await svc.parse_interactive(
        db_session, text=_unique_text(), rule_set_code=RULE_SET, created_by="IEC141289"
    )
    assert result.provenance["planner"] == "rule_based_v1" and "ai_error" not in result.provenance
    assert "ai_error" not in legacy["provenance"]
    assert await _external_runs(db_session) == []


# ═════════ 審查後補強 ═════════

async def test_a_user_facing_failure_keeps_its_code_but_an_ops_failure_does_not(db_session):
    quota, _ = await _parse(db_session, _unique_text(), _ext(_Port(fail=AiServiceErrorKind.QUOTA_EXCEEDED)))
    assert quota.provenance["ai_error"] == {"error_kind": "quota_exceeded", "upstream_code": "QUOTA_X"}


async def test_an_upstream_code_that_is_not_a_code_is_never_stored_or_returned(db_session):
    class _BadCode(_Port):
        async def parse(self, requests, *, allow_lists, lane):
            (req,) = requests
            return [WiParseResult(item_id=req.item_id, status="failed", error_kind=AiServiceErrorKind.TIMEOUT,
                                  provenance={"upstream_code": "<script>alert(1)</script>"})]

    result, legacy = await _parse(db_session, _unique_text(), _ext(_BadCode()))
    await _assert_degraded(db_session, result, legacy, kind="timeout")
    run = (await db_session.execute(select(AiParseRun).where(AiParseRun.id == uuid.UUID(result.run_id)))).scalar_one()
    assert run.error["ai_service"]["upstream_code"] is None


async def test_invalid_provenance_degrades_instead_of_failing_the_request(db_session, monkeypatch):
    def boom(_prov):
        raise ValueError("provenance keys not in allow-list: ['x']")

    monkeypatch.setattr(svc, "validate_provenance", boom)
    result, legacy = await _parse(db_session, _unique_text(), _ext(_Port()))
    await _assert_degraded(db_session, result, legacy, kind="contract_mismatch", code="PLAN_BUILD_FAILED")


async def test_a_response_from_another_bundle_than_configured_is_not_stored_under_this_key(db_session):
    other = _Port(provenance={**GOOD_PROVENANCE, "bundle_code": "some-other-bundle"})
    result, legacy = await _parse(db_session, _unique_text(), _ext(other, bundle=CFG_BUNDLE))
    await _assert_degraded(db_session, result, legacy, kind="contract_mismatch", code="BUNDLE_MISMATCH")


async def test_known_hand_is_part_of_the_cache_key(db_session):
    t = _unique_text()
    port = _Port()
    await _parse(db_session, t, _ext(port, known_hand="RH"))
    await _parse(db_session, t, _ext(port, known_hand="RH"))
    assert len(port.calls) == 1
    other, _ = await _parse(db_session, t, _ext(port, known_hand="LH"))
    assert len(port.calls) == 2, "手別不同＝不同請求，不共用旗標"
    assert "ai_hand_hint_mismatch" not in other.routing_reasons


async def test_pending_writes_before_the_call_are_refused(db_session):
    from ddm_v2.models.v2.ai_ops import AiDeploymentBundle

    port = _Port()
    db_session.add(AiDeploymentBundle(id=uuid.uuid4(), code=f"pending-{uuid.uuid4().hex[:6]}", kind="llm", created_by="t"))
    with pytest.raises(RuntimeError, match="pending writes"):
        await _parse(db_session, _unique_text(), _ext(port))
    assert port.calls == [], "沒有任何外送"


async def test_an_unknown_rule_set_still_raises_before_anything_is_sent(db_session):
    from ddm_v2.services.v2.synonym_service import RuleSetNotFound

    port = _Port()
    with pytest.raises(RuleSetNotFound):
        await svc.parse_interactive(db_session, text=_unique_text(), rule_set_code="NO_SUCH_RULE_SET",
                                    created_by="IEC141289", external=_ext(port))
    assert port.calls == []


async def test_a_failing_legacy_rule_parser_does_not_fail_an_ai_result_that_was_already_paid_for(db_session, monkeypatch):
    from ddm_v2.nlp.rule_based import RuleBasedParser

    def boom(self, *a, **k):
        raise TimeoutError("cpu budget")

    monkeypatch.setattr(RuleBasedParser, "parse", boom)
    result, legacy = await _parse(db_session, _unique_text(), _ext(_Port()))
    assert result.provenance["planner"] == "ai_service" and result.run_id
    assert legacy["provenance"]["slots_parser"] == "ai_candidates"
    assert len(await _external_runs(db_session)) == 1


async def test_losing_the_insert_race_replays_the_winner_instead_of_failing(db_session, monkeypatch):
    t = _unique_text()
    port = _Port()
    first, _ = await _parse(db_session, t, _ext(port))
    real = svc._find_cached_run
    seen = {"n": 0}

    async def miss_once(session, **kw):
        seen["n"] += 1
        return None if seen["n"] == 1 else await real(session, **kw)

    monkeypatch.setattr(svc, "_find_cached_run", miss_once)
    second, legacy = await _parse(db_session, t, _ext(port))
    assert len(port.calls) == 2, "第一次查快取時（模擬另一個請求還沒寫完）沒命中，所以又呼叫了一次"
    assert second.run_id == first.run_id and second.provenance["cached"] is True
    assert legacy["provenance"]["raced"] is True
    assert len(await _external_runs(db_session)) == 1
