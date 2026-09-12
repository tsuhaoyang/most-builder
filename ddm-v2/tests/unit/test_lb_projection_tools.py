"""WP4 關卡：ToolLifecycleResolver（Spec §4）。

Pattern B 3 列 / 2 列（§4.3）、Pattern A 三 motion（acquire/use/release）、held 未清、兩工具、tool_id snake_case。
判準看 vocab kind、不看敘事（提醒#1）；2 列同 chain 向後看（提醒#2）。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import E_TOOL_TWO_TOOLS
from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab
from ddm_v2.lb_projection.tools import ToolResolveError, resolve_chain, tool_id_of

pytestmark = pytest.mark.unit

_VOCAB = {
    "scanner": ProjectionVocab(kind="tool", name_en="scanner"),
    "electric_driver": ProjectionVocab(kind="tool", name_en="electric driver"),
    "torque_driver": ProjectionVocab(kind="tool", name_en="torque driver"),
    "motherboard": ProjectionVocab(kind="object", name_en="motherboard"),
    "screw": ProjectionVocab(kind="component", name_en="screw"),
}


def _row(seq_no, *, seq="CM", obj=None, tool=None, slot_tmus=None, total=None, repeat=None, general=False, freq=1.0):
    slot_tmus = slot_tmus or [16, 0, 6, 24, 0, 0, 10]
    total = total if total is not None else sum(slot_tmus)
    return ProjectionRow.model_validate({
        "wi_row_id": f"00000000-0000-4000-8000-{seq_no:012d}",
        "seq_no": seq_no,
        "object_vocab": obj,
        "tool_vocab": tool,
        "frequency": freq,
        "cycle": {"seq_kind": seq, "slot_tmus": slot_tmus, "repeat_counts": repeat or {}, "total_tmu": total},
        "level": {"ascription": "main", "level": "1"},
        "lb_tags": {"is_general": general},
    })


def test_pattern_b_three_rows() -> None:
    """tool_vocab=scanner，本 motion 內取用放（後面無同工具）→ 3 列 acquire/use/release。"""
    chain = [_row(1, tool="scanner", slot_tmus=[16, 0, 0, 22, 0, 0, 10], total=48)]
    plans, held = resolve_chain(chain, _VOCAB)
    assert len(plans) == 1
    assert plans[0].parts == ["acquire", "use", "release"]
    assert plans[0].tool_id == "scanner"
    assert held == set()  # 3 列 episode 在本 motion 內收掉


def test_pattern_b_two_rows_release_later() -> None:
    """tool_vocab=scanner（CM 用），後面同 chain 有 GM object=scanner 的 RELEASE → 本 motion 2 列。"""
    chain = [
        _row(1, seq="CM", tool="scanner", slot_tmus=[16, 0, 0, 22, 0, 0, 10], total=48),
        _row(2, seq="GM", obj="scanner", slot_tmus=[6, 0, 0, 0, 0, 0, 6], total=12),  # RELEASE
    ]
    plans, held = resolve_chain(chain, _VOCAB)
    assert plans[0].parts == ["acquire", "use"]  # 2 列
    assert plans[1].parts == ["release"]  # Pattern A release
    assert held == set()


def test_pattern_a_three_motions() -> None:
    """Pattern A：GM 拿(object=scanner) / CM 用(object=scanner held) / GM 放(object=scanner) → acquire/use/release。"""
    chain = [
        _row(1, seq="GM", obj="scanner", slot_tmus=[16, 0, 6, 0, 0, 6, 0], total=28),  # ACQUIRE
        _row(2, seq="CM", obj="scanner", slot_tmus=[0, 0, 0, 0, 22, 0, 0], total=22),  # held CM → USE
        _row(3, seq="GM", obj="scanner", slot_tmus=[6, 0, 0, 0, 0, 6, 0], total=12),  # RELEASE
    ]
    plans, held = resolve_chain(chain, _VOCAB)
    assert [p.parts[0] for p in plans] == ["acquire", "use", "release"]
    assert held == set()


def test_held_not_released_at_chain_end() -> None:
    """拿了沒放：chain 結束 held 非空（由 project.py 轉 E_TOOL_NOT_RELEASED；此處驗 held 回傳）。"""
    chain = [_row(1, seq="GM", obj="scanner", slot_tmus=[16, 0, 6, 0, 0, 6, 0], total=28)]  # 只 ACQUIRE
    _plans, held = resolve_chain(chain, _VOCAB)
    assert held == {"scanner"}


def test_two_tools_rejected() -> None:
    chain = [_row(1, obj="scanner", tool="electric_driver", slot_tmus=[16, 0, 6, 24, 0, 0, 10], total=56)]
    with pytest.raises(ToolResolveError) as ei:
        resolve_chain(chain, _VOCAB)
    assert ei.value.err.code == E_TOOL_TWO_TOOLS


def test_tool_id_snake_case() -> None:
    tid, warns = tool_id_of(_VOCAB["electric_driver"], "electric_driver")
    assert tid == "electric_driver"
    assert warns == []


def test_tool_id_missing_name_en() -> None:
    tid, warns = tool_id_of(ProjectionVocab(kind="tool", name_en=None), "abcdef12ghij")
    assert tid == "tool_abcdef12"
    assert warns and warns[0].code == "W_TOOL_NAME_EN_MISSING"
