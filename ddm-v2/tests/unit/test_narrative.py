"""narrative E6（ADR-014）：P display_rule 三態、A_move 手度翻轉、repeat ×N（純函數，免 DB）。"""
from __future__ import annotations

import pytest

from ddm_v2.most_engine.narrative import build_narrative

pytestmark = pytest.mark.unit

LABELS = {
    "g": {"g_grasp": {"label": "抓握", "sentence": "抓握"}},
    "p_base": {"p_place_none": {"label": "放(無方向)", "sentence": "放"}},
    "p_addon": {
        "a_align": {"label": "對準(精度<4mm)", "sentence": "對準", "display_rule": "prefix_visible_term"},
        "a_insert": {"label": "插入", "sentence": "插入", "display_rule": "show_self"},
        "a_snap": {"label": "卡合", "sentence": "卡合", "display_rule": "show_self"},
        "a_hard": {"label": "較難處理", "sentence": "", "display_rule": "hidden"},
        "a_press": {"label": "施加壓力", "sentence": "", "display_rule": "hidden"},
    },
    "m_verb": {"m_push": {"label": "推", "sentence": "推"}},
    "x": {"x_press": {"label": "並壓合機台", "sentence": "並壓合機台"}},
    "i": {"i_check": {"label": "並檢查(正常視線範圍)", "sentence": "並檢查"}},
}
VOCAB = {"object": "主板", "from": "料架", "to": "治具", "hand": "右手"}


def _gm_cycle(p_addons=None, twist=0, p_repeat=None):
    p5 = {"p_base_code": "p_place_none", "p_addon_codes": p_addons or []}
    if p_repeat:
        p5["repeat_count"] = p_repeat
    return {"seq": "GM", "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
            "a3": {"reach_cm": 25, "twist_deg": twist}, "p5": p5}


def test_p_show_self_replaces_base():
    s = build_narrative(_gm_cycle(["a_insert"]), LABELS, VOCAB)
    assert "「插入」放置" in s and "「放」" not in s


def test_p_prefix_align():
    s = build_narrative(_gm_cycle(["a_align", "a_insert"]), LABELS, VOCAB)
    assert "「對準插入」放置" in s


def test_p_hidden_not_in_sentence():
    s = build_narrative(_gm_cycle(["a_hard"]), LABELS, VOCAB)
    assert "較難處理" not in s and "「放」放置" in s


def test_a_move_twist_inserts_flip():
    s = build_narrative(_gm_cycle(twist=90), LABELS, VOCAB)
    assert "翻轉「主板」" in s


def test_repeat_suffix():
    s = build_narrative(_gm_cycle(p_repeat=3), LABELS, VOCAB)
    assert "放置×3" in s


def test_cm_x_i_sentences_and_none_skipped():
    cm = {"seq": "CM", "a0": {"reach_cm": 25}, "g2": {"g_code": "g_grasp"},
          "m3": {"m_components": [{"verb_code": "m_push"}], "repeat_count": 16},
          "x4": {"x_code": "x_press"}, "i5": {"i_code": "i_check"}}
    s = build_narrative(cm, LABELS, VOCAB)
    assert "以推×16實施移動" in s and "並壓合機台" in s and "並檢查" in s
    cm_none = {**cm, "x4": {"x_code": "x_none"}, "i5": {"i_code": "i_none"}, "m3": {"m_components": []}}
    s2 = build_narrative(cm_none, LABELS, VOCAB)
    assert "並壓合機台" not in s2 and "並檢查" not in s2
