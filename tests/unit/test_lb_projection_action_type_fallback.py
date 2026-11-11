"""WP6 補：action_type 五級優先序（ruling B）——附錄 A 路徑用真 slot_inputs 覆蓋（不進 golden）。"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import W_ACTION_TYPE_FALLBACK
from ddm_v2.lb_projection.mappers import action_type
from ddm_v2.lb_projection.models import ProjectionRow

pytestmark = pytest.mark.unit


def _row(*, seq="CM", general=False, general_role=None, lb_action_type=None, x_seconds=0.0):
    return ProjectionRow.model_validate({
        "wi_row_id": "00000000-0000-4000-8000-000000000099",
        "seq_no": 99,
        "cycle": {"seq_kind": seq, "slot_tmus": [0, 0, 0, 0, 0, 0, 0], "total_tmu": 0, "x_seconds": x_seconds},
        "level": {"ascription": "main", "level": "1"},
        "lb_tags": {"is_general": general, "general_role": general_role, "action_type": lb_action_type},
    })


def test_tier1_acquire_release_constant() -> None:
    assert action_type(_row(), "acquire")[0] == "pick"
    assert action_type(_row(), "release")[0] == "put"


def test_tier2_general_role() -> None:
    assert action_type(_row(general=True, general_role="take_unit"), None)[0] == "take"
    assert action_type(_row(general=True, general_role="scanner"), None)[0] == "scan"
    assert action_type(_row(general=True, general_role="transport"), None)[0] == "transport"


def test_tier3_lb_tags_action_type_wins_over_appendix() -> None:
    """③ lb_tags.action_type 優先於 ④ 附錄 A（golden 走這級）。"""
    r = _row(lb_action_type="latch")
    si = {"seq": "GM", "slots": {5: {"p_addon_codes": ["insert"]}}}  # 附錄 A 會判 insert
    assert action_type(r, None, si)[0] == "latch"


def test_tier4_appendix_a_cm_scan() -> None:
    r = _row(seq="CM")
    si = {"seq": "CM", "slots": {4: {"x_code": "x_scan"}}}
    assert action_type(r, None, si)[0] == "scan"


def test_tier4_appendix_a_cm_press_by_seconds() -> None:
    r = _row(seq="CM", x_seconds=3.0)
    si = {"seq": "CM", "slots": {4: {"x_code": "x_press", "x_seconds": 3.0}}}
    assert action_type(r, None, si)[0] == "press"


def test_tier4_appendix_a_gm_insert() -> None:
    r = _row(seq="GM")
    si = {"seq": "GM", "slots": {5: {"p_addon_codes": ["insert_align"]}}}
    assert action_type(r, None, si)[0] == "insert"


def test_tier4_appendix_a_cm_m_verb() -> None:
    r = _row(seq="CM")
    si = {"seq": "CM", "slots": {3: {"m_components": [{"verb_code": "m_rotate"}]}, 5: {"i_code": "i_none"}}}
    assert action_type(r, None, si)[0] == "rotate"


def test_tier5_fallback_op_with_warning() -> None:
    r = _row(seq="GM")  # 無 lb_action_type、無 slot_inputs
    at, warns = action_type(r, None, None)
    assert at == "op"
    assert warns and warns[0].code == W_ACTION_TYPE_FALLBACK
