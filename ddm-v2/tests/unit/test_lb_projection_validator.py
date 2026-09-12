"""WP7 關卡：CsvContractValidator（Spec §7 不變量 + 無主碼）。

「每碼一個反例」以 project_rows() 邊界為準（note#1）；validator 只擁有跨列不變量與尚未有人擁有的碼。
tools/tmu/precedence 已拋的碼（E_TOOL_NOT_RELEASED、E_REPEAT_*、E_LEVEL_*…）不在此重測。
收齊再擋：project_rows 一次回全部 E/W（note#4）。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import (
    E_ATOMIC_CROSS_GROUP,
    E_ATOMIC_ON_TOOL_MOTION,
    E_ATOMIC_QUANTITY,
    E_GENERAL_IN_GROUP,
    E_GENERAL_ROLE_ACTION_MISMATCH,
    E_GENERAL_ROLE_MISSING,
    E_NARRATIVE_EN_MISSING,
    E_OFFLINE_INCONSISTENT,
    E_SEGMENT_CROSS_GROUP,
    E_SPLITTABLE_CONFLICT,
    E_TOOL_ACQUIRE_DURATION_MISMATCH,
    E_TOOL_ID_SHARED_ACROSS_LOT,
    E_TOOL_RELEASE_DURATION_MISMATCH,
    W_FLOATING_TASK,
    W_NB_UNSUPPORTED,
)
from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab
from ddm_v2.lb_projection.project import project_rows
from ddm_v2.lb_projection.validator import validate

pytestmark = pytest.mark.unit

_VOCAB = {"scanner": ProjectionVocab(kind="tool", name_en="scanner")}


def _row(seq, **kw):
    base = {
        "wi_row_id": f"00000000-0000-4000-8000-{seq:012d}",
        "seq_no": seq,
        "key_parts": "P",
        "sub_activity": "S",
        "object_vocab": None,
        "tool_vocab": None,
        "frequency": kw.pop("frequency", 1),
        "cycle": {
            "seq_kind": kw.pop("seq", "GM"),
            "slot_tmus": kw.pop("slot_tmus", [10, 0, 6, 0, 0, 6, 0]),
            "repeat_counts": kw.pop("repeat", {}),
            "x_seconds": kw.pop("x_seconds", 0),
            "total_tmu": kw.pop("total", 22),
            "narrative_en": kw.pop("narrative_en", "do something"),
        },
        "level": {"ascription": "main", "level": "1", **kw.pop("level", {})},
        "lb_tags": kw.pop("lb_tags", {}),
    }
    return ProjectionRow.model_validate(base)


def _codes(result):
    return {e.code for e in result.errors}, {w.code for w in result.warnings}


def test_narrative_missing() -> None:
    r = _row(2, narrative_en=None)
    result = project_rows([r], _VOCAB)
    e, _w = _codes(result)
    assert E_NARRATIVE_EN_MISSING in e
    # note#4：每筆帶 wi_row_id
    assert any(x.wi_row_id == r.wi_row_id for x in result.errors)


def test_general_role_missing_and_in_group() -> None:
    r = _row(1, lb_tags={"is_general": True, "general_role": None, "worker_cub": "wcub9"})
    result = project_rows([r], _VOCAB)
    e, _w = _codes(result)
    assert E_GENERAL_ROLE_MISSING in e
    assert E_GENERAL_IN_GROUP in e


def test_general_role_action_mismatch() -> None:
    # take_unit 但 action 含 scan
    r = _row(1, lb_tags={"is_general": True, "general_role": "take_unit", "action_type": "take"},
             narrative_en="scan the unit label")
    result = project_rows([r], _VOCAB)
    e, _w = _codes(result)
    assert E_GENERAL_ROLE_ACTION_MISMATCH in e


def test_splittable_conflict_on_lot() -> None:
    r = _row(2, frequency=8, lb_tags={"splittable": True}, total=22)
    result = project_rows([r], _VOCAB)
    e, _w = _codes(result)
    assert E_SPLITTABLE_CONFLICT in e


def test_atomic_quantity_and_on_tool() -> None:
    # wcub 成員 Q>1（frequency=8）→ E_ATOMIC_QUANTITY
    r = _row(2, frequency=8, lb_tags={"worker_cub": "wcub5"}, total=22)
    result = project_rows([r], _VOCAB)
    e, _w = _codes(result)
    assert E_ATOMIC_QUANTITY in e


def test_offline_inconsistent_in_cub() -> None:
    """同 cub（group）內 offline 不一致（直接測 validator，避開 level gate）。"""
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="a", source_wi_row_id="a", action_type="op", group=7, offline_flag=1),
        LbTask(task_id=2, action="b", source_wi_row_id="b", action_type="op", group=7, offline_flag=0),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_OFFLINE_INCONSISTENT in {e.code for e in errors}


def test_nb_unsupported_warning() -> None:
    """nb ascription 丟棄 → W_NB_UNSUPPORTED（直接測 validator，避開 level gate）。"""
    r = _row(2, level={"ascription": "nb", "level": "1"})
    _e, w = validate([], [r], [])
    assert W_NB_UNSUPPORTED in {x.code for x in w}


def test_collect_all_not_stop_at_first() -> None:
    """note#4：一次回傳多個 E，不拋第一個就停。"""
    r = _row(1, lb_tags={"is_general": True, "general_role": None, "worker_cub": "wcub9"})
    result = project_rows([r], _VOCAB)
    assert len(result.errors) >= 2  # ROLE_MISSING + IN_GROUP 同時回


def test_floating_task_warning() -> None:
    """單一非 general standalone motion，無前後 → W_FLOATING_TASK。"""
    r = _row(2)
    result = project_rows([r], _VOCAB)
    _e, w = _codes(result)
    assert W_FLOATING_TASK in w


def test_tool_release_duration_mismatch_direct() -> None:
    """§7.6 release 側等長（ms）：同 tool_id 兩個不同 release duration。"""
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="put down scanner", source_wi_row_id="a", action_type="put",
               tool_id="scanner", tool_action="release", duration=360),
        LbTask(task_id=2, action="put down scanner", source_wi_row_id="b", action_type="put",
               tool_id="scanner", tool_action="release", duration=576),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_TOOL_RELEASE_DURATION_MISMATCH in {e.code for e in errors}


def test_tool_id_shared_across_lot_direct() -> None:
    """§7.7 過渡守衛：同 tool_id 同時出現在 Q>1 與 Q=1 episode。"""
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="use", source_wi_row_id="a", action_type="fasten",
               tool_id="electric_driver", tool_action="use", quantity=8, qty_scope="cyclic"),
        LbTask(task_id=2, action="use", source_wi_row_id="b", action_type="fasten",
               tool_id="electric_driver", tool_action="use", quantity=1),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_TOOL_ID_SHARED_ACROSS_LOT in {e.code for e in errors}


def test_tool_acquire_duration_mismatch_direct() -> None:
    """取放等長比 ms（直接測 validator：同 tool_id 兩個不同 acquire duration）。"""
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="pick up scanner", source_wi_row_id="a", action_type="pick",
               tool_id="scanner", tool_action="acquire", duration=576),
        LbTask(task_id=2, action="pick up scanner", source_wi_row_id="b", action_type="pick",
               tool_id="scanner", tool_action="acquire", duration=792),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_TOOL_ACQUIRE_DURATION_MISMATCH in {e.code for e in errors}


def test_segment_cross_group_direct() -> None:
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="a", source_wi_row_id="a", action_type="op", segment="s1", group=30),
        LbTask(task_id=2, action="b", source_wi_row_id="b", action_type="op", segment="s1", group=40),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_SEGMENT_CROSS_GROUP in {e.code for e in errors}


def test_atomic_cross_group_direct() -> None:
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="a", source_wi_row_id="a", action_type="op", atomic_group=20, group=30),
        LbTask(task_id=2, action="b", source_wi_row_id="b", action_type="op", atomic_group=20, group=40),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_ATOMIC_CROSS_GROUP in {e.code for e in errors}


def test_atomic_on_tool_direct() -> None:
    from ddm_v2.lb_projection.emit import LbTask

    tasks = [
        LbTask(task_id=1, action="use", source_wi_row_id="a", action_type="fasten",
               atomic_group=20, tool_id="driver", tool_action="use"),
    ]
    errors, _w = validate(tasks, [], [])
    assert E_ATOMIC_ON_TOOL_MOTION in {e.code for e in errors}


def test_auto_group_for_lot_warning() -> None:
    """Q>1（frequency=8）無 cub → W_AUTO_GROUP_FOR_LOT（mappers 擁有；project_rows 邊界）。"""
    from ddm_v2.lb_projection.errors import W_AUTO_GROUP_FOR_LOT

    r = _row(2, frequency=8, total=22)
    result = project_rows([r], _VOCAB)
    _e, w = _codes(result)
    assert W_AUTO_GROUP_FOR_LOT in w
    # 合成 group = 9000 + seq_no
    assert result.tasks[0].group == 9002


def test_level_invalid_gate() -> None:
    """level.validate 有 issue → E_LEVEL_INVALID（precedence gate 擁有；project_rows 邊界）。"""
    from ddm_v2.lb_projection.errors import E_LEVEL_INVALID
    from ddm_v2.lb_projection.precedence import PrecedenceError

    # cub 群組但成員 ascription 結構不合 R 規則 → level 引擎報 issue
    a = _row(5, level={"countersignature": "cub7", "order": 1, "level": "1", "ascription": "sub"})
    with pytest.raises(PrecedenceError) as ei:
        project_rows([a], _VOCAB)
    assert ei.value.err.code == E_LEVEL_INVALID


def test_simo_collapsed_warning() -> None:
    """SIMO 從屬列略過 → W_SIMO_COLLAPSED（validator 擁有）。"""
    from ddm_v2.lb_projection.errors import W_SIMO_COLLAPSED

    r = _row(2)
    r2 = r.model_copy(update={"simo_group_id": "simo1"})
    _e, w = validate([], [r2], [])
    assert W_SIMO_COLLAPSED in {x.code for x in w}


def test_cross_chain_hold() -> None:
    """工具於 chain A（sub2）取得、chain B（sub3）釋放 → E_TOOL_CROSS_CHAIN。"""
    from ddm_v2.lb_projection.errors import E_TOOL_CROSS_CHAIN

    # sub2：GM 取 scanner（object=scanner），不放 → held
    acq = _row(5, level={"countersignature": "sub2", "order": 1, "level": "2"})
    acq = acq.model_copy(update={"object_vocab": "scanner", "cycle": acq.cycle.model_copy(update={"seq_kind": "GM"})})
    # sub3：GM 放 scanner（object=scanner）
    rel = _row(6, level={"countersignature": "sub3", "order": 1, "level": "2"})
    rel = rel.model_copy(update={"object_vocab": "scanner", "cycle": rel.cycle.model_copy(update={"seq_kind": "GM"})})
    result = project_rows([acq, rel], _VOCAB)
    e, _w = _codes(result)
    assert E_TOOL_CROSS_CHAIN in e
