"""WP3 關卡：TmuDecomposer 靜態路徑（Spec §3.3）。

WI-I（190 = 22 + 8×19 + 16）＝唯一有 repeat 的持工具 motion；WI-D（48 = 16+22+10）＝無 repeat Pattern B。
反例：E_REPEAT_MIXED、E_TOOL_ACQUIRE_REPEAT。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import E_REPEAT_MIXED, E_TOOL_ACQUIRE_REPEAT
from ddm_v2.lb_projection.tmu import (
    TmuDecompositionError,
    decompose_static,
    repeat_n,
)

pytestmark = pytest.mark.unit


def test_wi_i_repeat_decomposition() -> None:
    """WI-I：slot_tmus=[16,0,6,24,48,80,16]（use 段已含 ×8）、repeat 8、total 190。
    use_total = 24+48+80 = 152；use_once = 152/8 = 19；acquire = 16+0+6 = 22；release = 16。
    190 = 22 + 8×19 + 16 ✓（Spec §9）。"""
    dec = decompose_static([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 8, "5": 8}, total_tmu=190)
    assert dec.acquire_tmu == 22
    assert dec.use_once_tmu == 19
    assert dec.release_tmu == 16
    assert dec.n == 8
    assert dec.acquire_tmu + dec.n * dec.use_once_tmu + dec.release_tmu == 190


def test_wi_d_no_repeat() -> None:
    """WI-D（scanner Pattern B, n=1）：acquire 16 / use 22 / release 10；total 48（Spec §9）。"""
    dec = decompose_static([16, 0, 0, 22, 0, 0, 10], {}, total_tmu=48)
    assert (dec.acquire_tmu, dec.use_once_tmu, dec.release_tmu, dec.n) == (16, 22, 10, 1)


def test_repeat_n_mixed_rejected() -> None:
    with pytest.raises(TmuDecompositionError) as ei:
        repeat_n({"3": 8, "4": 4, "5": 8})
    assert ei.value.err.code == E_REPEAT_MIXED


def test_repeat_on_acquire_slot_rejected() -> None:
    with pytest.raises(TmuDecompositionError) as ei:
        repeat_n({"2": 3})  # slot 2 (G, acquire 段) 帶 repeat
    assert ei.value.err.code == E_TOOL_ACQUIRE_REPEAT


def test_conservation_failure_raises() -> None:
    """人為構造不守恆（total 對不上）→ E_TMU_DECOMPOSITION。"""
    from ddm_v2.lb_projection.errors import E_TMU_DECOMPOSITION
    with pytest.raises(TmuDecompositionError) as ei:
        decompose_static([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 8, "5": 8}, total_tmu=999)
    assert ei.value.err.code == E_TMU_DECOMPOSITION
