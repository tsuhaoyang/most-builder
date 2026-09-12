"""B4（ADR-035 D10）：§4 B4-4 表每碼反例的 params 非空且鍵正確。

以 project_rows 邊界或直接觸發，斷言對應 ProjectionError.params 的鍵。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import (
    E_REPEAT_MIXED,
    E_REPEAT_NONCONTIGUOUS,
    E_TOOL_ACQUIRE_DURATION_MISMATCH,
    E_TOOL_FRACTIONAL_FREQUENCY,
    E_TOOL_ID_SHARED_ACROSS_LOT,
    E_TOOL_RELEASE_DURATION_MISMATCH,
    W_FRACTIONAL_FREQUENCY_BAKED,
    W_TOOL_FREQ_ALL_CYCLIC,
    W_TOOL_NAME_EN_MISSING,
)

pytestmark = pytest.mark.unit


def test_tool_id_params_validator():
    from ddm_v2.lb_projection.emit import LbTask
    from ddm_v2.lb_projection.validator import validate

    tasks = [
        LbTask(task_id=1, action="a", source_wi_row_id="a", action_type="pick", tool_id="scanner", tool_action="acquire", duration=576),
        LbTask(task_id=2, action="b", source_wi_row_id="b", action_type="pick", tool_id="scanner", tool_action="acquire", duration=792),
        LbTask(task_id=3, action="c", source_wi_row_id="c", action_type="put", tool_id="scanner", tool_action="release", duration=360),
        LbTask(task_id=4, action="d", source_wi_row_id="d", action_type="put", tool_id="scanner", tool_action="release", duration=576),
        LbTask(task_id=5, action="e", source_wi_row_id="e", action_type="fasten", tool_id="ed", tool_action="use", quantity=8, qty_scope="cyclic"),
        LbTask(task_id=6, action="f", source_wi_row_id="f", action_type="fasten", tool_id="ed", tool_action="use", quantity=1),
    ]
    errors, _w = validate(tasks, [], [])
    by = {e.code: e for e in errors}
    assert by[E_TOOL_ACQUIRE_DURATION_MISMATCH].params == {"tool_id": "scanner"}
    assert by[E_TOOL_RELEASE_DURATION_MISMATCH].params == {"tool_id": "scanner"}
    assert by[E_TOOL_ID_SHARED_ACROSS_LOT].params == {"tool_id": "ed"}


def test_frequency_params_quantity():
    from ddm_v2.lb_projection.models import ProjectionRow
    from ddm_v2.lb_projection.quantity import QuantityError, plan_quantity
    from ddm_v2.lb_projection.tmu import Decomposed, RepeatBlock
    from ddm_v2.lb_projection.tools import MotionPlan

    def _row(freq):
        return ProjectionRow.model_validate({
            "wi_row_id": "00000000-0000-4000-8000-000000000002", "seq_no": 2, "frequency": freq,
            "cycle": {"seq_kind": "CM", "slot_tmus": [0, 0, 0, 0, 0, 0, 0], "total_tmu": 100},
            "level": {"ascription": "main", "level": "1"}, "lb_tags": {}})

    dec1 = Decomposed(16, 19, 16, 1, 51, RepeatBlock((), 1, (), ()))
    # W_FRACTIONAL_FREQUENCY_BAKED（非工具、非整數 freq）
    qp = plan_quantity(MotionPlan(row=_row(1.5), parts=["use"], decomposed=dec1), dec1)
    assert next(w for w in qp.warnings if w.code == W_FRACTIONAL_FREQUENCY_BAKED).params == {"frequency": 1.5}
    # W_TOOL_FREQ_ALL_CYCLIC（工具、整數 F>1）
    tp = MotionPlan(row=_row(3), parts=["acquire", "use", "release"], tool_id="t", decomposed=dec1)
    qp2 = plan_quantity(tp, dec1)
    assert next(w for w in qp2.warnings if w.code == W_TOOL_FREQ_ALL_CYCLIC).params == {"frequency": 3}
    # E_TOOL_FRACTIONAL_FREQUENCY（工具、非整數）
    with pytest.raises(QuantityError) as ei:
        plan_quantity(MotionPlan(row=_row(1.5), parts=["acquire", "use", "release"], tool_id="t", decomposed=dec1), dec1)
    assert ei.value.err.code == E_TOOL_FRACTIONAL_FREQUENCY
    assert ei.value.err.params == {"frequency": 1.5}


def test_counts_params_tmu():
    from ddm_v2.lb_projection.tmu import TmuDecompositionError, repeat_block

    with pytest.raises(TmuDecompositionError) as ei:
        repeat_block([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 4, "5": 8})
    assert ei.value.err.code == E_REPEAT_MIXED
    assert "counts" in (ei.value.err.params or {})

    with pytest.raises(TmuDecompositionError) as ei2:
        repeat_block([16, 0, 6, 24, 48, 80, 16], {"3": 8, "5": 8})  # 夾心
    assert ei2.value.err.code == E_REPEAT_NONCONTIGUOUS
    assert "counts" in (ei2.value.err.params or {})


def test_tool_name_missing_params():
    from ddm_v2.lb_projection.models import ProjectionVocab
    from ddm_v2.lb_projection.tools import tool_id_of

    _tid, warns = tool_id_of(ProjectionVocab(kind="tool", name_en=None), "abcdef12ghij")
    assert warns[0].code == W_TOOL_NAME_EN_MISSING
    assert warns[0].params == {"tool_id": "tool_abcdef12"}
