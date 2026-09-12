"""TmuDecomposer：tool-held motion 的 TMU 分桶分解（Spec §3.3，2026-09-12 分桶裁決）。

七格分三桶，切點是 use 段（slot 3–5）的**重複區塊 R**，不是固定 slot 界線：
- `setup_pre`  = Σ slot_tmus[0..2] + R 之前的（非零）use 格            # 每 episode 一次
- `use_once`   = Σ_{s∈R} once_slot_tmu(s)                              # 每件一次
- `setup_post` = R 之後的（非零）use 格 + slot_tmus[6]                 # 每 episode 一次
斷言（Spec §3.3、§7.1）：setup_pre + N×use_once + setup_post == total_tmu（|Δ|≤1e-6），否則 E_TMU_DECOMPOSITION。

連續性只看**非零工時格**（零工時格夾在重複格間不算斷開）。R 內 repeat 不一致→E_REPEAT_MIXED；
R 不連續（夾心）→E_REPEAT_NONCONTIGUOUS；slot 0–2 有 repeat→E_TOOL_ACQUIRE_REPEAT。

單次工時只能來自引擎重算或 fixture 靜態值（實作書 §6#1）：
- 引擎路徑（有 slot_inputs 必走）：compute_cycle(strip_repeats(slot_inputs, slots=R)).slot_tmus[s]
- 靜態路徑（fixture）：slot_tmus[s] / N（逐格除，非 Σslot[3..5]/N）
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ddm_v2.lb_projection.errors import (
    E_REPEAT_MIXED,
    E_REPEAT_NONCONTIGUOUS,
    E_REPEAT_NONLINEAR,
    E_TMU_DECOMPOSITION,
    E_TOOL_ACQUIRE_REPEAT,
    ProjectionError,
)

_ACQUIRE_SLOTS = (0, 1, 2)
_USE_SLOTS = (3, 4, 5)
_RELEASE_SLOT = 6
_TMU_EPS = 1e-6


class TmuDecompositionError(Exception):
    """分解失敗，攜帶 ProjectionError。由 project.py 收集轉報告。"""

    def __init__(self, err: ProjectionError) -> None:
        super().__init__(err.message)
        self.err = err


@dataclass(frozen=True)
class RepeatBlock:
    """use 段的重複區塊 R：格 index tuple、N、R 前/後的（非零）use 格。R 空時 slots=()、n=1。"""

    slots: tuple[int, ...]
    n: int
    pre: tuple[int, ...]
    post: tuple[int, ...]


@dataclass(frozen=True)
class Decomposed:
    setup_pre_tmu: float
    use_once_tmu: float
    setup_post_tmu: float
    n: int
    total_tmu: float
    block: RepeatBlock


def repeat_block(slot_tmus: list[float], repeat_counts: dict[str, int], wi_row_id: str | None = None) -> RepeatBlock:
    """從 use 段（slot 3–5）解析重複區塊 R（Spec §3.3 分桶）。

    連續性只看非零工時格；零工時格不參與判定、不算斷開。
    """
    # slot 0–2 不得有 repeat
    for si in _ACQUIRE_SLOTS:
        if repeat_counts.get(str(si), 1) not in (None, 1):
            raise TmuDecompositionError(
                ProjectionError(E_TOOL_ACQUIRE_REPEAT, wi_row_id, f"slot {si}（取得段）不可帶 repeat_count")
            )
    # use 段非零格，依 slot 順序
    nonzero_use = [si for si in _USE_SLOTS if slot_tmus[si] not in (0, 0.0)]
    repeated = [si for si in nonzero_use if repeat_counts.get(str(si), 1) not in (None, 1)]
    if not repeated:
        return RepeatBlock(slots=(), n=1, pre=(), post=())
    # R 內 repeat 值一致
    reps = {repeat_counts[str(si)] for si in repeated}
    if len(reps) > 1:
        raise TmuDecompositionError(
            ProjectionError(E_REPEAT_MIXED, wi_row_id, f"重複區塊內 repeat_count 不一致：{sorted(reps)}")
        )
    n = next(iter(reps))
    # 連續性（只看非零格）：repeated 必須是 nonzero_use 中的連續一段
    first, last = nonzero_use.index(repeated[0]), nonzero_use.index(repeated[-1])
    if nonzero_use[first : last + 1] != repeated:
        raise TmuDecompositionError(
            ProjectionError(
                E_REPEAT_NONCONTIGUOUS,
                wi_row_id,
                f"重複格不連續（夾心）：非零 use 格 {nonzero_use}，重複格 {repeated}",
            )
        )
    pre = tuple(nonzero_use[:first])
    post = tuple(nonzero_use[last + 1 :])
    return RepeatBlock(slots=tuple(repeated), n=n, pre=pre, post=post)


def _assert_conservation(dec: Decomposed, wi_row_id: str | None) -> Decomposed:
    lhs = dec.setup_pre_tmu + dec.n * dec.use_once_tmu + dec.setup_post_tmu
    if abs(lhs - dec.total_tmu) > _TMU_EPS:
        raise TmuDecompositionError(
            ProjectionError(
                E_TMU_DECOMPOSITION,
                wi_row_id,
                f"分解不守恆：{dec.setup_pre_tmu} + {dec.n}×{dec.use_once_tmu} + {dec.setup_post_tmu} "
                f"= {lhs} != total {dec.total_tmu}",
            )
        )
    return dec


def _assemble(slot_tmus: list[float], block: RepeatBlock, once_use: dict[int, float], total_tmu: float, wi_row_id: str | None) -> Decomposed:
    """依分桶把 slot_tmus 組成 (setup_pre, use_once, setup_post)。once_use：R 內每格的單次工時。"""
    setup_pre = sum(slot_tmus[i] for i in _ACQUIRE_SLOTS) + sum(slot_tmus[i] for i in block.pre)
    use_once = sum(once_use[i] for i in block.slots)
    setup_post = sum(slot_tmus[i] for i in block.post) + slot_tmus[_RELEASE_SLOT]
    return _assert_conservation(Decomposed(setup_pre, use_once, setup_post, block.n, total_tmu, block), wi_row_id)


def decompose_static(slot_tmus: list[float], repeat_counts: dict[str, int], total_tmu: float, wi_row_id: str | None = None) -> Decomposed:
    """fixture 路徑：R 內每格 once = slot_tmus[s] / N（逐格除，Spec §3.3）。"""
    block = repeat_block(slot_tmus, repeat_counts, wi_row_id)
    if not block.slots:
        # R 空：無重複，use_once = Σ use 段（三列時 use 列 Q=1）
        setup_pre = sum(slot_tmus[i] for i in _ACQUIRE_SLOTS)
        use_once = sum(slot_tmus[i] for i in _USE_SLOTS)
        setup_post = slot_tmus[_RELEASE_SLOT]
        return _assert_conservation(Decomposed(setup_pre, use_once, setup_post, 1, total_tmu, block), wi_row_id)
    once_use = {s: slot_tmus[s] / block.n for s in block.slots}
    return _assemble(slot_tmus, block, once_use, total_tmu, wi_row_id)


def strip_repeats(slot_inputs: dict[str, Any], slots: tuple[int, ...]) -> dict[str, Any]:
    """把 slot_inputs 指定格的 repeat_count 歸 1（引擎重算單次工時用；Spec §3.3）。深拷貝。"""
    out = copy.deepcopy(slot_inputs)
    slot_map = out.get("slots") or {}
    for si in slots:
        for key in (si, str(si)):
            if key in slot_map and isinstance(slot_map[key], dict) and "repeat_count" in slot_map[key]:
                slot_map[key]["repeat_count"] = 1
    return out


def decompose_engine(slot_inputs: dict[str, Any], total_tmu: float, rs: Any, wi_row_id: str | None = None) -> Decomposed:
    """權威路徑：R 內每格 once = compute_cycle(strip_repeats(slot_inputs, slots=R)).slot_tmus[s]（Spec §3.3）。"""
    from ddm_v2.most_engine.calculate import compute_cycle

    full = compute_cycle(slot_inputs, rs)
    slot_tmus = list(full.slot_tmus)
    repeat_counts = _repeat_counts_from_slot_inputs(slot_inputs)
    block = repeat_block(slot_tmus, repeat_counts, wi_row_id)
    _assert_m_linear(slot_inputs, block, wi_row_id)
    if not block.slots:
        setup_pre = sum(slot_tmus[i] for i in _ACQUIRE_SLOTS)
        use_once = sum(slot_tmus[i] for i in _USE_SLOTS)
        setup_post = slot_tmus[_RELEASE_SLOT]
        return _assert_conservation(Decomposed(setup_pre, use_once, setup_post, 1, total_tmu, block), wi_row_id)
    once = compute_cycle(strip_repeats(slot_inputs, block.slots), rs)
    once_use = {s: once.slot_tmus[s] for s in block.slots}
    return _assemble(slot_tmus, block, once_use, total_tmu, wi_row_id)


def _assert_m_linear(slot_inputs: dict[str, Any], block: RepeatBlock, wi_row_id: str | None) -> None:
    """M（slot 3）∈ R 且 M 含伴隨維度（hand_cm／foot_cm）→ E_REPEAT_NONLINEAR（Spec §3.3）。

    M = max(verb×N, hand, foot) 非線性，不可逐格線性拆。
    """
    if 3 not in block.slots:
        return
    slots = slot_inputs.get("slots") or {}
    m = slots.get(3) or slots.get("3") or {}
    for comp in m.get("m_components") or []:
        if any(comp.get(k) for k in ("hand_cm", "foot_cm")):
            raise TmuDecompositionError(
                ProjectionError(E_REPEAT_NONLINEAR, wi_row_id, "M 含伴隨維度（手度／腳步）且 M∈R，不可線性拆")
            )


def _repeat_counts_from_slot_inputs(slot_inputs: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key, slot in (slot_inputs.get("slots") or {}).items():
        if isinstance(slot, dict):
            rc = slot.get("repeat_count")
            if rc not in (None, 1):
                out[str(key)] = int(rc)
    return out


__all__ = [
    "RepeatBlock",
    "Decomposed",
    "TmuDecompositionError",
    "repeat_block",
    "decompose_static",
    "decompose_engine",
    "strip_repeats",
]
