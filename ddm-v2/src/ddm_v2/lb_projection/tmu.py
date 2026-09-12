"""TmuDecomposer：把一個 motion 的 TMU 分解為 acquire / use_once / release（Spec §3.3）。

鐵則（實作書 §6#1）：投影層**不做 TMU 加減乘除以外的推導**；單次工時只能來自
- 引擎重算（`decompose_engine`：`compute_cycle(strip_repeats(slot_inputs, slots 3–5))`），或
- fixture 靜態值（`decompose_static`：Σslot_tmus[3..5] / N）。
兩路徑對同一 motion 必須相等（`test_lb_projection_engine_path.py`）。

守恆斷言（Spec §3.3、§7.1）：`acquire + N×use_once + release == total_tmu`（|Δ| ≤ 1e-6），
否則 `E_TMU_DECOMPOSITION`。M 格含伴隨維度（手度/腳步）且 N>1 → 不可線性拆，`E_REPEAT_NONLINEAR`。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from ddm_v2.lb_projection.errors import (
    E_REPEAT_MIXED,
    E_TMU_DECOMPOSITION,
    E_TOOL_ACQUIRE_REPEAT,
    ProjectionError,
)

# slot index：0–2 = acquire 段（A B G）；3–5 = use 段（GM: A B P／CM: M X I）；6 = release（返回 A）。
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
class Decomposed:
    acquire_tmu: float
    use_once_tmu: float
    release_tmu: float
    n: int
    total_tmu: float


def repeat_n(repeat_counts: dict[str, int], wi_row_id: str | None = None) -> int:
    """slot 3–5 非零格的共同 repeat 值；無 → 1。

    - slot 0–2（acquire 段）有 repeat → E_TOOL_ACQUIRE_REPEAT（取得只做一次，Spec §3.2）。
    - slot 3–5 非零格 repeat 不一致 → E_REPEAT_MIXED（Spec §3.2）。
    """
    for si in _ACQUIRE_SLOTS:
        if repeat_counts.get(str(si), 1) not in (None, 1):
            raise TmuDecompositionError(
                ProjectionError(E_TOOL_ACQUIRE_REPEAT, wi_row_id, f"slot {si}（取得段）不可帶 repeat_count")
            )
    use_reps = {repeat_counts[str(si)] for si in _USE_SLOTS if str(si) in repeat_counts and repeat_counts[str(si)] not in (None, 1)}
    if len(use_reps) > 1:
        raise TmuDecompositionError(
            ProjectionError(E_REPEAT_MIXED, wi_row_id, f"slot 3–5 的 repeat_count 不一致：{sorted(use_reps)}")
        )
    return next(iter(use_reps)) if use_reps else 1


def _assert_conservation(dec: Decomposed, wi_row_id: str | None) -> Decomposed:
    lhs = dec.acquire_tmu + dec.n * dec.use_once_tmu + dec.release_tmu
    if abs(lhs - dec.total_tmu) > _TMU_EPS:
        raise TmuDecompositionError(
            ProjectionError(
                E_TMU_DECOMPOSITION,
                wi_row_id,
                f"分解不守恆：{dec.acquire_tmu} + {dec.n}×{dec.use_once_tmu} + {dec.release_tmu} "
                f"= {lhs} != total {dec.total_tmu}",
            )
        )
    return dec


def decompose_static(slot_tmus: list[float], repeat_counts: dict[str, int], total_tmu: float, wi_row_id: str | None = None) -> Decomposed:
    """fixture 路徑：slot_tmus 已含 repeat（Σslot[3..5] 是 N 次的總和）→ use_once = Σslot[3..5] / N。"""
    n = repeat_n(repeat_counts, wi_row_id)
    acquire = sum(slot_tmus[i] for i in _ACQUIRE_SLOTS)
    use_total = sum(slot_tmus[i] for i in _USE_SLOTS)
    release = slot_tmus[_RELEASE_SLOT]
    use_once = use_total / n if n else use_total
    return _assert_conservation(Decomposed(acquire, use_once, release, n, total_tmu), wi_row_id)


def strip_repeats(slot_inputs: dict[str, Any], slots: tuple[int, ...] = _USE_SLOTS) -> dict[str, Any]:
    """把 slot_inputs 的指定格 repeat_count 歸 1（用於引擎重算單次工時，Spec §3.3）。

    slot_inputs 形狀＝`compute_cycle` 的 `{"seq":..., "slots": {i: {...}}}`。深拷貝，不改原輸入。
    """
    out = copy.deepcopy(slot_inputs)
    slot_map = out.get("slots") or {}
    for si in slots:
        # slots key 可能是 int 或 str（JSON）——兩種都清
        for key in (si, str(si)):
            if key in slot_map and isinstance(slot_map[key], dict) and "repeat_count" in slot_map[key]:
                slot_map[key]["repeat_count"] = 1
    return out


def decompose_engine(slot_inputs: dict[str, Any], total_tmu: float, rs: Any, wi_row_id: str | None = None) -> Decomposed:
    """權威路徑：以 repeat 歸 1 重算單次工時（Spec §3.3）。

    `compute_cycle(strip_repeats(slot_inputs))` 的 slot_tmus[3..5] 即單次；N 由原 slot_inputs 取。
    M 格伴隨維度＋N>1 由 compute_cycle 的 max 語義自然反映；守恆斷言會擋線性不成立的情形。
    """
    from ddm_v2.most_engine.calculate import compute_cycle

    repeat_counts = _repeat_counts_from_slot_inputs(slot_inputs)
    n = repeat_n(repeat_counts, wi_row_id)
    full = compute_cycle(slot_inputs, rs)
    once = compute_cycle(strip_repeats(slot_inputs), rs)
    acquire = sum(full.slot_tmus[i] for i in _ACQUIRE_SLOTS)
    use_once = sum(once.slot_tmus[i] for i in _USE_SLOTS)
    release = full.slot_tmus[_RELEASE_SLOT]
    return _assert_conservation(Decomposed(acquire, use_once, release, n, total_tmu), wi_row_id)


def _repeat_counts_from_slot_inputs(slot_inputs: dict[str, Any]) -> dict[str, int]:
    """從 slot_inputs.slots[i].repeat_count 取出 {str(i): N}。"""
    out: dict[str, int] = {}
    for key, slot in (slot_inputs.get("slots") or {}).items():
        if isinstance(slot, dict):
            rc = slot.get("repeat_count")
            if rc not in (None, 1):
                out[str(key)] = int(rc)
    return out


__all__ = ["Decomposed", "TmuDecompositionError", "decompose_static", "decompose_engine", "strip_repeats", "repeat_n"]
