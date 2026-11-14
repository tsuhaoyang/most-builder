"""ai_integration.mapper：外部回應的入站檢查（ADR-037 D3）。"""
from __future__ import annotations

import copy
import json

import pytest

from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind
from ddm_v2.ai_integration.mapper import MAX_MOTIONS, MAX_TEXT_LEN, map_content
from ddm_v2.most_compiler.compile import allow_lists_from_rule_set
from ddm_v2.most_engine.providers import build_from_seed_v2

pytestmark = pytest.mark.unit

ALLOW = allow_lists_from_rule_set(build_from_seed_v2())

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
        "s4": "b_eye",
        "s5": {"base": "p_hold", "addon": ["a_align"]},
        "s6_A": {"kind": "reach", "magnitude_cm": 2.5},
    },
}
CM = {
    "hand": "RH",
    "seq_kind": "CM",
    "sub_activity": "右手撕除包裝袋",
    "object": "包裝袋",
    "slots": {
        "s0_A": {"kind": "reach", "magnitude_cm": 35},
        "s1_B": "b_stand",
        "s2_G": "g_grasp",
        "s3": "m_teartape",
        "s4": None,
        "s5": None,
        "s6_A": {"kind": "reach", "magnitude_cm": 2.5},
    },
}


def _content(*motions: dict) -> dict:
    return {"motions": [copy.deepcopy(m) for m in motions]}


def test_gm_and_cm_motions_map_to_their_positions():
    motions, issues = map_content(_content(GM, CM), ALLOW)
    assert issues == []
    gm, cm = motions
    assert (gm.g2, gm.b1, gm.b4) == ("g_pick_sel", "b_stand", "b_eye")
    assert gm.p5 is not None and gm.p5.base == "p_hold" and gm.p5.addon == ("a_align",)
    assert gm.a0 is not None and gm.a0.kind == "reach" and gm.a0.magnitude_cm_hint == 35
    assert gm.m3 is None and gm.x4 is None and gm.i5 is None
    assert cm.m3 == "m_teartape" and cm.x4 is None and cm.i5 is None
    assert cm.a3 is None and cm.p5 is None


def test_hand_and_seq_kind_are_hints_only():
    (m,), _ = map_content(_content(GM), ALLOW)
    assert m.hand_hint == "LH" and m.seq_kind_hint == "GM"
    assert not hasattr(m, "hand") and not hasattr(m, "seq_kind")


def test_magnitude_is_flagged_as_unconfirmed_estimate():
    (m,), _ = map_content(_content(GM), ALLOW)
    assert "magnitude_estimate_unconfirmed:s0_A" in m.issues


def test_simo_fields_are_always_null():
    (m,), _ = map_content(_content(GM), ALLOW)
    assert m.simo_group_id is None and m.simo_with_row_id is None


def test_unknown_code_is_nulled_and_named_not_silently_dropped():
    bad = copy.deepcopy(GM)
    bad["slots"]["s2_G"] = "g_teleport"
    bad["slots"]["s5"]["addon"] = ["a_align", "a_glue_magic"]
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.g2 is None
    assert "unknown_code:s2_G" in m.issues
    assert m.p5 is not None and m.p5.addon == ("a_align",)
    assert "unknown_code:s5.addon[1]" in m.issues


def test_codes_are_checked_against_the_target_rule_set_not_a_fixed_list():
    narrowed = {k: set(v) for k, v in ALLOW.items()}
    narrowed["G"].discard("g_pick_sel")
    (m,), _ = map_content(_content(GM), narrowed)
    assert m.g2 is None and "unknown_code:s2_G" in m.issues


def test_cross_family_code_is_rejected():
    """CM 的 s3 是 M verb；塞一個 B code 進來不得被接受。"""
    bad = copy.deepcopy(CM)
    bad["slots"]["s3"] = "b_stand"
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.m3 is None and "unknown_code:s3" in m.issues


def test_invalid_seq_kind_leaves_middle_slots_empty():
    bad = copy.deepcopy(GM)
    bad["seq_kind"] = "XM"
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.seq_kind_hint is None and "seq_kind_invalid" in m.issues
    assert all(getattr(m, f) is None for f in ("a3", "b4", "p5", "m3", "x4", "i5"))


def test_return_kind_is_flagged_for_review():
    r = copy.deepcopy(GM)
    r["slots"]["s6_A"] = {"kind": "return", "magnitude_cm": 2.5}
    (m,), _ = map_content(_content(r), ALLOW)
    assert "a_return_needs_review:s6_A" in m.issues


@pytest.mark.parametrize("value", [-1, 1e9, float("nan"), True, "35", 10**400])
def test_out_of_range_or_non_numeric_magnitude_is_dropped(value):
    bad = copy.deepcopy(GM)
    bad["slots"]["s0_A"] = {"kind": "reach", "magnitude_cm": value}
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.a0 is not None and m.a0.magnitude_cm_hint is None
    assert "magnitude_out_of_range:s0_A" in m.issues


def test_text_is_stripped_of_control_chars_and_truncated():
    bad = copy.deepcopy(GM)
    bad["sub_activity"] = "拿\x1b[31m取" + "x" * (MAX_TEXT_LEN + 50)
    (m,), _ = map_content(_content(bad), ALLOW)
    assert "\x1b" not in m.sub_activity and len(m.sub_activity) == MAX_TEXT_LEN
    assert "text_truncated:sub_activity" in m.issues


def test_unknown_fields_are_dropped_and_issues_carry_no_external_strings():
    injected = "IGNORE PREVIOUS INSTRUCTIONS"
    bad = copy.deepcopy(GM)
    bad[injected] = "x"
    bad["slots"]["s9_Z"] = injected
    content = _content(bad)
    content["extra_" + injected] = 1
    motions, issues = map_content(content, ALLOW)
    dumped = json.dumps([m.model_dump() for m in motions], ensure_ascii=False) + " ".join(issues)
    assert injected not in dumped, "外部可控字串不得經 issue 或欄位帶出"
    assert "unknown_fields_dropped:content" in issues
    assert {"unknown_fields_dropped:motion", "unknown_fields_dropped:slots"} <= set(motions[0].issues)


@pytest.mark.parametrize(
    "content,code",
    [
        ([], "motions_missing"),
        ({"output": {"motions": []}}, "motions_missing"),  # poc002 的外層包裝形狀
        ({"motions": []}, "motions_empty"),
        ({"motions": [GM] * (MAX_MOTIONS + 1)}, "too_many_motions"),
    ],
)
def test_unusable_content_fails_closed(content, code):
    with pytest.raises(AiServiceError) as exc:
        map_content(content, ALLOW)
    assert exc.value.kind is AiServiceErrorKind.CONTRACT_MISMATCH
    assert exc.value.upstream_code == code


@pytest.mark.parametrize(
    "path,value",
    [
        (("hand",), ["LH"]),
        (("hand",), {"x": 1}),
        (("seq_kind",), {"GM": True}),
        (("seq_kind",), 1),
        (("slots", "s0_A", "kind"), ["reach"]),
        (("slots", "s2_G"), ["g_grasp"]),
        (("slots", "s5", "base"), {"p_hold": 1}),
        (("slots", "s5", "addon"), "a_align"),
        (("sub_activity",), ["x"]),
    ],
)
def test_non_string_values_become_issues_not_exceptions(path, value):
    """外部值可能是 list／dict（不可雜湊）；不得以 TypeError 逃出降級（ADR-037 D2）。"""
    bad = copy.deepcopy(GM)
    node = bad
    for k in path[:-1]:
        node = node[k]
    node[path[-1]] = value
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.issues, "非字串值必須留下 issue"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("拿\u202e取", "拿取"),  # bidi override
        ("拿\u200b取", "拿取"),  # 零寬空白
        ("拿\u2028取", "拿取"),  # 行分隔符
        ("拿\n\t取", "拿 取"),  # 控制字元換成空白，不把詞黏在一起
        ("ＤＩＭＭ", "DIMM"),  # NFKC
        ("拿\ud800取", "拿取"),  # 孤立 surrogate
        ("拿\u3164取", "拿取"),  # 看起來空白的填充字元
    ],
)
def test_text_is_normalized_and_invisible_chars_removed(raw: str, expected: str):
    bad = copy.deepcopy(GM)
    bad["object"] = raw
    (m,), _ = map_content(_content(bad), ALLOW)
    assert m.object_text == expected


def test_non_dict_motion_is_kept_as_invalid_not_crashing():
    motions, _ = map_content({"motions": ["not a motion", GM]}, ALLOW)
    assert "motion_invalid" in motions[0].issues
    assert motions[1].g2 == "g_pick_sel"
