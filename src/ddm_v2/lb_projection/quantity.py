"""QuantityProjector：兩乘數投影矩陣（Spec §3.2，唯一權威）。

frequency＝整 motion 乘數；repeat_count＝持工具 use 段 cyclic 乘數（分桶 R）。
每個 part（acquire/use/release/單列）產出 (quantity, qty_scope, duration_basis, duration_tmu)。
持工具×兩乘數多為拒絕（E_TOOL_FREQ_AND_REPEAT / E_TOOL_FRACTIONAL_FREQUENCY）。
"""
from __future__ import annotations

from dataclasses import dataclass

from ddm_v2.lb_projection.errors import (
    E_TOOL_FRACTIONAL_FREQUENCY,
    E_TOOL_FREQ_AND_REPEAT,
    W_FRACTIONAL_FREQUENCY_BAKED,
    W_TOOL_FREQ_ALL_CYCLIC,
    ProjectionError,
)
from ddm_v2.lb_projection.tmu import Decomposed
from ddm_v2.lb_projection.tools import MotionPlan


class QuantityError(Exception):
    def __init__(self, err: ProjectionError) -> None:
        super().__init__(err.message)
        self.err = err


@dataclass(frozen=True)
class PartQuantity:
    """一個輸出列的量化欄位。"""

    part: str  # acquire/use/release/single
    quantity: int
    qty_scope: str | None  # setup/cyclic/None(Q=1)
    duration_basis: str | None  # once/None
    duration_tmu: float


@dataclass(frozen=True)
class QuantityPlan:
    parts: list[PartQuantity]
    warnings: list[ProjectionError]


def _is_int(f: float) -> bool:
    return abs(f - round(f)) < 1e-9


def plan_quantity(plan: MotionPlan, dec: Decomposed | None) -> QuantityPlan:
    """依 §3.2 矩陣產每列量化。dec 為 None 表非工具單列（general 等），Q=1。"""
    row = plan.row
    freq = row.frequency or 1.0
    warns: list[ProjectionError] = []
    is_tool = plan.tool_id is not None  # 有 tool_id 即持工具列組

    # 非工具單列（含 general、非 tool motion）
    if not is_tool:
        return _plan_non_tool(plan, dec, freq, warns)
    return _plan_tool(plan, dec, freq, warns)


def _plan_non_tool(plan: MotionPlan, dec: Decomposed | None, freq: float, warns: list[ProjectionError]) -> QuantityPlan:
    row = plan.row
    total = row.cycle.total_tmu
    # 非整數 frequency → 燙進 duration，Q=1
    if not _is_int(freq):
        warns.append(ProjectionError(W_FRACTIONAL_FREQUENCY_BAKED, row.wi_row_id, f"非整數 frequency {freq} 燙進 duration", params={"frequency": freq}))
        return QuantityPlan([PartQuantity("single", 1, None, None, total * freq)], warns)
    f = int(round(freq))
    if f > 1:
        # Q=F cyclic，duration=單次（含 repeat 已燙進 total）
        return QuantityPlan([PartQuantity("single", f, "cyclic", "once", total)], warns)
    # F==1：Q=1，repeat 已燙進 duration（total）
    return QuantityPlan([PartQuantity("single", 1, None, None, total)], warns)


def _plan_tool(plan: MotionPlan, dec: Decomposed | None, freq: float, warns: list[ProjectionError]) -> QuantityPlan:
    row = plan.row
    assert dec is not None, "tool-held motion 必有 Decomposed"
    n = dec.n
    # 非整數 frequency 拒絕
    if not _is_int(freq):
        raise QuantityError(ProjectionError(E_TOOL_FRACTIONAL_FREQUENCY, row.wi_row_id, f"持工具非整數 frequency {freq}", params={"frequency": freq}))
    f = int(round(freq))
    # F>1 且 N>1 拒絕
    if f > 1 and n > 1:
        raise QuantityError(ProjectionError(E_TOOL_FREQ_AND_REPEAT, row.wi_row_id, f"持工具 F={f} 且 N={n}"))

    # 決定 Q 與 scope 語意
    if n > 1:
        # repeat：acquire/release=setup、use=cyclic；三列 Q=N、once
        return _tool_parts(plan, dec, q=n, use_scope="cyclic", basis="once", warns=warns)
    if f > 1:
        # frequency F>1：三列全 cyclic（字面拿 F 次），Q=F、once ＋ W
        warns.append(ProjectionError(W_TOOL_FREQ_ALL_CYCLIC, row.wi_row_id, f"持工具 frequency F={f}，三列全 cyclic", params={"frequency": f}))
        return _tool_parts(plan, dec, q=f, use_scope="cyclic", basis="once", all_cyclic=True, warns=warns)
    # N=1、F=1：Q=1
    return _tool_parts(plan, dec, q=1, use_scope=None, basis=None, warns=warns)


def _tool_parts(
    plan: MotionPlan,
    dec: Decomposed,
    *,
    q: int,
    use_scope: str | None,
    basis: str | None,
    all_cyclic: bool = False,
    warns: list[ProjectionError],
) -> QuantityPlan:
    """依 plan.parts（含 §4.3 2 列 setup_post 歸屬）配 setup_pre/use_once/setup_post。"""
    tmu = {"acquire": dec.setup_pre_tmu, "use": dec.use_once_tmu, "release": dec.setup_post_tmu}
    # 2 列（acquire+use）：§4.3 setup_post 歸屬
    if plan.parts == ["acquire", "use"]:
        into = plan.two_row_setup_post_into or ("acquire" if q > 1 else "use")
        tmu = dict(tmu)
        tmu[into] = tmu[into] + dec.setup_post_tmu

    parts: list[PartQuantity] = []
    for part in plan.parts:
        if q == 1:
            parts.append(PartQuantity(part, 1, None, None, tmu[part]))
        else:
            scope = "cyclic" if (all_cyclic or part == "use") else "setup"
            parts.append(PartQuantity(part, q, scope, basis, tmu[part]))
    return QuantityPlan(parts, warns)


__all__ = ["PartQuantity", "QuantityPlan", "QuantityError", "plan_quantity"]
