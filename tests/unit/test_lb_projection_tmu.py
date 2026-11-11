"""WP3 關卡：TmuDecomposer 分桶靜態路徑（Spec §3.3，2026-09-12 分桶裁決）。

WI-I（R={M,X,I}，190=22+8×19+16）、WI-D（無 repeat）、M 一次＋X×8/I×8（M 進 setup_pre）、
夾心（E_REPEAT_NONCONTIGUOUS）、mixed（E_REPEAT_MIXED）、acquire repeat（E_TOOL_ACQUIRE_REPEAT）。
"""
from __future__ import annotations

import pytest

from ddm_v2.lb_projection.errors import (
    E_REPEAT_MIXED,
    E_REPEAT_NONCONTIGUOUS,
    E_TMU_DECOMPOSITION,
    E_TOOL_ACQUIRE_REPEAT,
)
from ddm_v2.lb_projection.tmu import TmuDecompositionError, decompose_static, repeat_block

pytestmark = pytest.mark.unit


def test_wi_i_block_all_use_slots() -> None:
    """WI-I：slot_tmus=[16,0,6,24,48,80,16]，R={3,4,5} repeat 8，total 190。
    setup_pre = 16+0+6 = 22；use_once = (24+48+80)/8 = 19；setup_post = 16。190 = 22+8×19+16。"""
    dec = decompose_static([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 8, "5": 8}, total_tmu=190)
    assert dec.setup_pre_tmu == 22
    assert dec.use_once_tmu == 19
    assert dec.setup_post_tmu == 16
    assert dec.n == 8
    assert dec.block.slots == (3, 4, 5)
    assert dec.setup_pre_tmu + dec.n * dec.use_once_tmu + dec.setup_post_tmu == 190


def test_m_once_then_repeat_x_i() -> None:
    """「移一次（M3）、掃 8 次（X、I ×8）」：R={4,5}，M 進 setup_pre。
    slot_tmus=[16,0,6,3,48,80,16]（M=3 一次；X=48 已含×8；I=80 已含×8），repeat {4:8,5:8}，total?
    setup_pre = 16+0+6 + M3 = 25；use_once = (48+80)/8 = 16；setup_post = 16；n=8。
    total = 25 + 8×16 + 16 = 169。"""
    dec = decompose_static([16, 0, 6, 3, 48, 80, 16], {"4": 8, "5": 8}, total_tmu=169)
    assert dec.block.slots == (4, 5)
    assert dec.block.pre == (3,)  # M 在 R 前
    assert dec.setup_pre_tmu == 25  # 22 + M3
    assert dec.use_once_tmu == 16
    assert dec.setup_post_tmu == 16
    assert dec.n == 8


def test_wi_d_no_repeat() -> None:
    """WI-D（scanner Pattern B, R 空）：setup_pre 16 / use 22 / setup_post 10；total 48。"""
    dec = decompose_static([16, 0, 0, 22, 0, 0, 10], {}, total_tmu=48)
    assert (dec.setup_pre_tmu, dec.use_once_tmu, dec.setup_post_tmu, dec.n) == (16, 22, 10, 1)
    assert dec.block.slots == ()


def test_zero_slot_not_breaking_contiguity() -> None:
    """零工時格夾在重複格間不算斷開：X=0（zero）、M×8、I×8 → R={3,5}（4 是零，不參與）。"""
    # nonzero use = [3,5]（slot4=0 跳過）；both repeat 8 → R=(3,5) 連續
    # total = setup_pre(22) + 8×use_once((24+80)/8=13) + setup_post(16) = 22 + 104 + 16 = 142
    dec = decompose_static([16, 0, 6, 24, 0, 80, 16], {"3": 8, "5": 8}, total_tmu=142)
    assert dec.block.slots == (3, 5)
    assert dec.use_once_tmu == (24 + 80) / 8  # 13


def test_sandwich_noncontiguous_rejected() -> None:
    """夾心：M×8、X 一次(非零)、I×8 → 重複格 {3,5} 中間夾非零非重複的 4 → E_REPEAT_NONCONTIGUOUS。"""
    with pytest.raises(TmuDecompositionError) as ei:
        repeat_block([16, 0, 6, 24, 48, 80, 16], {"3": 8, "5": 8})
    assert ei.value.err.code == E_REPEAT_NONCONTIGUOUS


def test_mixed_repeat_rejected() -> None:
    with pytest.raises(TmuDecompositionError) as ei:
        repeat_block([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 4, "5": 8})
    assert ei.value.err.code == E_REPEAT_MIXED


def test_acquire_repeat_rejected() -> None:
    with pytest.raises(TmuDecompositionError) as ei:
        repeat_block([16, 0, 6, 24, 48, 80, 16], {"2": 3})
    assert ei.value.err.code == E_TOOL_ACQUIRE_REPEAT


def test_conservation_failure_raises() -> None:
    with pytest.raises(TmuDecompositionError) as ei:
        decompose_static([16, 0, 6, 24, 48, 80, 16], {"3": 8, "4": 8, "5": 8}, total_tmu=999)
    assert ei.value.err.code == E_TMU_DECOMPOSITION
