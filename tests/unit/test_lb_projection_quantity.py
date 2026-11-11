"""WP6 補：QuantityProjector §3.2 矩陣的碼反例（quantity.py 擁有）。"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import (
    E_TOOL_FRACTIONAL_FREQUENCY,
    E_TOOL_FREQ_AND_REPEAT,
    W_FRACTIONAL_FREQUENCY_BAKED,
    W_TOOL_FREQ_ALL_CYCLIC,
)
from ddm_v2.lb_projection.models import ProjectionRow
from ddm_v2.lb_projection.quantity import QuantityError, plan_quantity
from ddm_v2.lb_projection.tmu import Decomposed, RepeatBlock
from ddm_v2.lb_projection.tools import MotionPlan

pytestmark = pytest.mark.unit


def _row(seq=2, frequency=1.0, total=100):
    return ProjectionRow.model_validate({
        "wi_row_id": f"00000000-0000-4000-8000-{seq:012d}",
        "seq_no": seq,
        "frequency": frequency,
        "cycle": {"seq_kind": "CM", "slot_tmus": [0, 0, 0, 0, 0, 0, 0], "total_tmu": total},
        "level": {"ascription": "main", "level": "1"},
        "lb_tags": {},
    })


def _dec(n=1, pre=16, once=19, post=16):
    block = RepeatBlock(slots=(3, 4, 5) if n > 1 else (), n=n, pre=(), post=())
    return Decomposed(pre, once, post, n, pre + n * once + post, block)


def _tool_plan(row, dec, parts=("acquire", "use", "release")):
    return MotionPlan(row=row, parts=list(parts), tool_id="scanner", tool_vocab_key="scanner", decomposed=dec)


def test_non_tool_fractional_frequency_baked_warn() -> None:
    r = _row(frequency=1.5, total=100)
    qp = plan_quantity(MotionPlan(row=r, parts=["use"], decomposed=_dec(n=1)), _dec(n=1))
    assert W_FRACTIONAL_FREQUENCY_BAKED in {w.code for w in qp.warnings}
    assert qp.parts[0].quantity == 1
    assert qp.parts[0].duration_tmu == 150  # 100 × 1.5 燙進


def test_non_tool_integer_frequency_cyclic() -> None:
    r = _row(frequency=8, total=66)
    qp = plan_quantity(MotionPlan(row=r, parts=["use"], decomposed=_dec(n=1)), _dec(n=1))
    assert qp.parts[0].quantity == 8
    assert qp.parts[0].qty_scope == "cyclic"
    assert qp.parts[0].duration_basis == "once"


def test_tool_freq_and_repeat_rejected() -> None:
    r = _row(frequency=3, total=190)
    with pytest.raises(QuantityError) as ei:
        plan_quantity(_tool_plan(r, _dec(n=8)), _dec(n=8))
    assert ei.value.err.code == E_TOOL_FREQ_AND_REPEAT


def test_tool_fractional_frequency_rejected() -> None:
    r = _row(frequency=1.5, total=48)
    with pytest.raises(QuantityError) as ei:
        plan_quantity(_tool_plan(r, _dec(n=1)), _dec(n=1))
    assert ei.value.err.code == E_TOOL_FRACTIONAL_FREQUENCY


def test_tool_freq_all_cyclic_warn() -> None:
    r = _row(frequency=3, total=48)
    qp = plan_quantity(_tool_plan(r, _dec(n=1)), _dec(n=1))
    assert W_TOOL_FREQ_ALL_CYCLIC in {w.code for w in qp.warnings}
    # 三列全 cyclic、Q=3
    assert all(p.quantity == 3 and p.qty_scope == "cyclic" for p in qp.parts)


def test_tool_repeat_use_cyclic_setup_pre_post() -> None:
    r = _row(frequency=1, total=190)
    qp = plan_quantity(_tool_plan(r, _dec(n=8)), _dec(n=8))
    scopes = {p.part: p.qty_scope for p in qp.parts}
    assert scopes == {"acquire": "setup", "use": "cyclic", "release": "setup"}
    assert all(p.quantity == 8 for p in qp.parts)
