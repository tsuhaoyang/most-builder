"""入站防腐層 `nlp/inbound_guard.py` 的直接單元測試（ADR-033 D6；ADR-037 D3 的入站不變量）。

由舊 `test_llm_planner.py` 改寫：那份測試經 `LLMPlannerAdapter` ＋ FakeLLMClient 間接覆蓋
`_parse_sanitize_validate`。ADR-037 移除 adapter 後，同一批案例改為**直接**餵 JSON 給
`parse_sanitize_validate`——外部 ai_service 回應進 MOST 的唯一入口，S2 的 adapter 會建在它上面。

retry 次數、`PlannerError` 包裝、observer 發送屬於 adapter 層（S2 重做），不在本檔範圍；
本檔只驗邊界本身：哪些形狀整筆作廢、哪些逐項降級並記名、被剝的值只走 `details`。
"""
from __future__ import annotations

import json

import pytest

from ddm_v2.nlp.contracts import PlannerOutput
from ddm_v2.nlp.inbound_guard import parse_sanitize_validate, sequence_orders_contiguous
from ddm_v2.nlp.normalization import normalize

pytestmark = pytest.mark.unit

_NORM = "拿起dimm"


def _action_json(**over) -> dict:
    base = {
        "action_id": "a1",
        "action_type": "acquire",
        "sequence_order": 1,
        "roles": {},
        "evidence": [{"text": _NORM}],
    }
    base.update(over)
    return base


def _payload(actions: list[dict], **over) -> str:
    body = {"language": "zh", "actions": actions, "dependencies": [], "unresolved": []}
    body.update(over)
    return json.dumps(body, ensure_ascii=False)


# ── 正常路徑 ────────────────────────────────────────────────────────────


def test_single_acquire_passes_and_keeps_unresolved():
    norm = normalize("拿起DIMM")
    payload = _payload(
        [_action_json(roles={"object": {"text": "dimm"}}, evidence=[{"text": norm}])],
        unresolved=["next_operation"],
    )
    out, errors, _reasons, details = parse_sanitize_validate(payload, norm)
    assert errors == []
    assert isinstance(out, PlannerOutput)
    assert len(out.actions) == 1 and out.actions[0].action_type == "acquire"
    assert "next_operation" in out.unresolved
    assert details == []


def test_repairable_offset_is_repaired_not_fatal():
    """text 抄對、end 越界 → 由原文推導座標，記 `evidence_offset_repaired`，不作廢。"""
    norm = normalize("拿起DIMM")
    payload = _payload([_action_json(evidence=[{"start": 0, "end": len(norm) + 2, "text": norm}])])
    out, errors, reasons, _details = parse_sanitize_validate(payload, norm)
    assert errors == []
    assert out is not None
    ev = out.actions[0].evidence[0]
    assert (ev.start, ev.end) == (0, len(norm))
    assert any(r.startswith("evidence_offset_repaired:a1") for r in reasons), reasons


# ── D6：整筆失敗只剩三種（加上「全部被剔除」與防禦性斷言）──────────────


@pytest.mark.parametrize(
    "payload,code",
    [
        pytest.param("{not-json", "json_or_schema", id="fatal-1-json"),
        pytest.param(_payload([]), "actions_empty", id="fatal-2-actions-empty"),
        pytest.param(
            _payload(
                [
                    _action_json(action_id="a1", sequence_order=1),
                    _action_json(action_id="a2", sequence_order=3),
                ]
            ),
            "sequence_order_not_contiguous",
            id="fatal-3-sequence-gap",
        ),
    ],
)
def test_only_three_shapes_fail_the_whole_output(payload: str, code: str):
    out, errors, _reasons, _details = parse_sanitize_validate(payload, _NORM)
    assert out is None
    assert any(e.startswith(code) for e in errors), errors


def test_sequence_gap_is_judged_on_the_raw_output_not_after_renumbering():
    """sanitize 會重新編號；若判在它之後，這條規則永遠是綠的（等於失效）。"""
    payload = _payload(
        [
            _action_json(action_id="a1", sequence_order=2),
            _action_json(action_id="a2", sequence_order=3),
        ]
    )
    out, errors, _reasons, _details = parse_sanitize_validate(payload, _NORM)
    assert out is None and errors == ["sequence_order_not_contiguous"]


def test_unlocatable_text_still_fails_closed():
    """evidence text 在原文找不到 → 該 action 剔除；一個都不剩＝`all_actions_sanitized_away`。

    不得被洗成「合法證據」：猜一個看起來合理的 span 會把幻覺變成憑據。
    """
    payload = _payload([_action_json(evidence=[{"start": 0, "end": 6, "text": "拿起記憶體模組"}])])
    out, errors, reasons, _details = parse_sanitize_validate(payload, _NORM)
    assert out is None
    assert errors == ["all_actions_sanitized_away"]
    assert any(r.startswith("planner_invented_action:a1:evidence_text_not_found") for r in reasons), reasons


# ── D6：過去會整筆失敗、現在必須逐項降級並記名 ─────────────────────────


@pytest.mark.parametrize(
    "payload,reason",
    [
        pytest.param(
            _payload([_action_json(roles={"object_ref": {"action_ref": "a1"}})]),
            "role_key_dropped:a1:object_ref",
            id="unknown-role-key",
        ),
        pytest.param(
            _payload([_action_json(roles={"distance": {"value": 450, "unit": "cm"}})]),
            "role_numeric_stripped:a1:distance",
            id="numeric-role",
        ),
        pytest.param(
            _payload([_action_json(roles={"object": {"text": "記憶體模組"}})]),
            "role_text_not_in_source:a1:object",
            id="role-text-rewritten",
        ),
        pytest.param(
            _payload(
                [_action_json()],
                dependencies=[{"from_action": "a1", "to_action": "a1", "type": "same_hand"}],
            ),
            "dependency_dropped:0:illegal_type=",
            id="illegal-dependency-type",
        ),
        pytest.param(
            _payload([_action_json(evidence=[{"start": 0, "end": 99, "text": _NORM}])]),
            "evidence_offset_repaired:a1",
            id="wrong-offset",
        ),
    ],
)
def test_degradable_shapes_are_stripped_not_fatal(payload: str, reason: str):
    out, errors, reasons, _details = parse_sanitize_validate(payload, _NORM)
    assert errors == [], errors
    assert out is not None and len(out.actions) == 1, "降級不得丟掉切分"
    assert any(r.startswith(reason) for r in reasons), reasons


def test_degraded_reasons_reach_unresolved_so_routing_can_block_auto():
    """剝除 reason 必須經 `unresolved` 浮到 routing——看不見的降級等於靜默改寫。"""
    payload = _payload(
        [_action_json(roles={"distance": {"value": 450, "unit": "cm"}})],
        dependencies=[{"from_action": "a1", "to_action": "a1", "type": "same_hand"}],
    )
    out, errors, _reasons, _details = parse_sanitize_validate(payload, _NORM)
    assert errors == [] and out is not None
    assert "role_numeric_stripped" in out.unresolved
    assert "dependency_dropped" in out.unresolved


# ── 被剝的值只走 details，不進輸出 ─────────────────────────────────────

_DEGRADING_PAYLOAD = _payload(
    [
        _action_json(
            roles={
                "object": {"text": "記憶體模組"},
                "distance": {"value": 450, "unit": "cm"},
                "object_ref": {"text": "治具", "action_ref": "a1"},
            }
        )
    ]
)


def test_details_carry_the_stripped_values():
    """降級時被剝掉的**值本身**要回到 details——`by_code` 只答得出剝了幾次。"""
    out, errors, _reasons, details = parse_sanitize_validate(_DEGRADING_PAYLOAD, _NORM)
    assert errors == [] and out is not None and len(out.actions) == 1
    by_reason = {d.reason: d for d in details}
    assert by_reason["role_text_not_in_source"].text == "記憶體模組"
    assert (by_reason["role_numeric_stripped"].value, by_reason["role_numeric_stripped"].unit) == (450, "cm")
    assert by_reason["role_key_dropped"].role_key == "object_ref"


def test_stripped_values_do_not_leak_into_output_or_reasons():
    """輸出面（含 `unresolved`）與 reasons 都不得帶外部可控字串；它們只在 details。

    與 `test_contracts.py::test_stripped_values_never_reach_unresolved_or_routing` 互補：
    那條走到 `compute_routing`。
    """
    out, _errors, reasons, _details = parse_sanitize_validate(_DEGRADING_PAYLOAD, _NORM)
    assert out is not None
    dumped = json.dumps(out.model_dump(), ensure_ascii=False)
    joined_reasons = " ".join(reasons)
    for needle in ("記憶體模組", "治具", "450"):
        assert needle not in dumped, f"降級後的輸出仍帶著 {needle!r}：{dumped}"
        assert needle not in joined_reasons, f"reasons 帶著外部可控字串 {needle!r}：{reasons}"
    assert "role_text_not_in_source" in out.unresolved


def test_details_are_returned_even_when_the_whole_output_fails():
    """硬失敗那次也要交出已收集的明細——只在成功時給等於挑好看的樣本回報。"""
    payload = _payload([_action_json(evidence=[{"text": "拿起記憶體模組"}])])
    out, errors, _reasons, details = parse_sanitize_validate(payload, _NORM)
    assert out is None and errors == ["all_actions_sanitized_away"]
    assert [d.text for d in details] == ["拿起記憶體模組"]


def test_json_failure_returns_empty_reasons_and_details():
    out, errors, reasons, details = parse_sanitize_validate("{not-json", _NORM)
    assert out is None and errors and errors[0].startswith("json_or_schema")
    assert reasons == [] and details == []


# ── sequence_orders_contiguous ─────────────────────────────────────────


@pytest.mark.parametrize(
    "orders,expected",
    [([1], True), ([1, 2, 3], True), ([2], False), ([1, 3], False), ([2, 1], False)],
)
def test_sequence_orders_contiguous(orders: list[int], expected: bool):
    out = PlannerOutput.model_validate(
        {
            "language": "zh",
            "actions": [
                {"action_id": f"a{i}", "action_type": "acquire", "sequence_order": o, "roles": {}, "evidence": []}
                for i, o in enumerate(orders, start=1)
            ],
        }
    )
    assert sequence_orders_contiguous(out) is expected
