"""ai_review_service.derive_candidates 單元測試。"""
from __future__ import annotations

from types import SimpleNamespace

from ddm_v2.services.v2.ai_review_service import derive_candidates


def _run(**kw):
    base = {
        "id": "00000000-0000-0000-0000-000000000001",
        "raw_text": "拿起DIMM重抓",
        "normalized_text": "拿起dimm重抓",
        "plan": {"actions": []},
    }
    base.update(kw)
    return SimpleNamespace(**base)


def test_replace_candidate_creates_synonym_when_missing_before():
    cands = derive_candidates(
        event_type="replace_candidate",
        target={"action_id": "a1", "parameter": "G", "surface_text": "重抓"},
        before={"option_code": None, "review_reason": "no_candidate"},
        after={"option_code": "g_regrasp", "surface_text": "重抓"},
        run=_run(),
    )
    assert len(cands) == 1
    assert cands[0]["kind"] == "synonym"
    assert cands[0]["payload"]["option_code"] == "g_regrasp"
    assert cands[0]["status"] == "candidate"


def test_replace_candidate_skips_when_surface_not_in_text():
    cands = derive_candidates(
        event_type="replace_candidate",
        target={"parameter": "G"},
        before={"review_reason": "no_candidate"},
        after={"option_code": "g_regrasp", "surface_text": "不存在的詞"},
        run=_run(),
    )
    assert cands == []


def test_split_action_few_shot():
    cands = derive_candidates(
        event_type="split_action",
        target={"action_id": "a1"},
        before=None,
        after={"actions": ["a1", "a2"]},
        run=_run(),
    )
    assert len(cands) == 1
    assert cands[0]["kind"] == "few_shot"


def test_accept_all_gold():
    cands = derive_candidates(
        event_type="accept_all",
        target=None,
        before=None,
        after=None,
        run=_run(),
    )
    assert len(cands) == 1
    assert cands[0]["kind"] == "gold"


def test_accept_plan_no_candidate():
    assert (
        derive_candidates(
            event_type="accept_plan",
            target=None,
            before=None,
            after=None,
            run=_run(),
        )
        == []
    )
