"""CsvContractValidator：Spec §7 跨列不變量 ＋ 尚未有人擁有的 §8.1 碼（單一權威）。

擁有範圍（不重實作 tools/tmu/precedence 已拋的碼）：
- §7.1 TMU 守恆（TMU 域）＋ ms 域容忍
- §7.6 取放等長（ms 域，LB C4 比 duration 欄）→ E_TOOL_ACQUIRE/RELEASE_DURATION_MISMATCH
- §7.7 E_TOOL_ID_SHARED_ACROSS_LOT
- §7.4/§7.5 組內傳染與互斥：E_SEGMENT_CROSS_GROUP、E_ATOMIC_*、E_OFFLINE_INCONSISTENT、E_SPLITTABLE_CONFLICT
- general：E_GENERAL_IN_GROUP、E_GENERAL_ROLE_MISSING、E_GENERAL_ROLE_ACTION_MISMATCH
- E_NARRATIVE_EN_MISSING、W_FLOATING_TASK、W_NB_UNSUPPORTED、W_SIMO_COLLAPSED

收齊再擋：一次回傳全部 E 與 W（不拋第一個就停）；每筆帶 wi_row_id（Spec §8）。
"""
from __future__ import annotations

from collections import defaultdict

from ddm_v2.lb_projection.emit import LbTask
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
    E_TMU_DECOMPOSITION,
    E_TOOL_ACQUIRE_DURATION_MISMATCH,
    E_TOOL_ID_SHARED_ACROSS_LOT,
    E_TOOL_RELEASE_DURATION_MISMATCH,
    W_FLOATING_TASK,
    W_NB_UNSUPPORTED,
    W_SIMO_COLLAPSED,
    ProjectionError,
)
from ddm_v2.lb_projection.models import ProjectionRow
from ddm_v2.lb_projection.tools import MotionPlan

_GENERAL_ROLE_KEYWORDS = {
    "take_unit": ("transport", "transfer", "scan"),  # 不得含
    "transport": ("transport",),  # 必含
    "scanner": ("scan",),  # 必含
}


def validate(
    tasks: list[LbTask],
    rows: list[ProjectionRow],
    plans: list[MotionPlan],
) -> tuple[list[ProjectionError], list[ProjectionError]]:
    """回 (errors, warnings)。收齊全部，不早停。"""
    errors: list[ProjectionError] = []
    warnings: list[ProjectionError] = []
    row_by_id = {r.wi_row_id: r for r in rows}

    _check_tmu_conservation(rows, plans, tasks, errors)
    _check_tool_equal_duration(tasks, errors)
    _check_tool_shared_across_lot(tasks, errors)
    _check_segment_atomic_offline(tasks, row_by_id, errors)
    _check_general(rows, tasks, errors)
    _check_narrative(rows, errors)
    _check_floating(tasks, row_by_id, warnings)
    _check_nb_simo(rows, warnings)

    return errors, warnings


def _check_tmu_conservation(rows, plans, tasks, errors) -> None:
    """§7.1（TMU 域）：Σ_motions(total_tmu×freq) == Σ_tasks(once_tmu × (quantity if cyclic else 1))。

    RHS 為 task 側：cyclic 列乘 quantity、setup/Q=1 列乘 1（Spec §7.1）。以 QuantityProjector 每列
    (duration_tmu, quantity, qty_scope) 重算，避免 ms 捨入。general 單列 total×1 兩側相等；SIMO 略過。
    """
    from ddm_v2.lb_projection.quantity import plan_quantity

    lhs = 0.0
    for r in rows:
        if r.simo_group_id:
            continue  # SIMO 從屬列不進 DAG
        freq = r.frequency or 1.0
        lhs += r.cycle.total_tmu * freq

    rhs = 0.0
    for p in plans:
        qplan = plan_quantity(p, p.decomposed)
        for pq in qplan.parts:
            mult = pq.quantity if pq.qty_scope == "cyclic" else 1
            rhs += pq.duration_tmu * mult

    if abs(lhs - rhs) > 1e-6:
        errors.append(ProjectionError(E_TMU_DECOMPOSITION, None, f"TMU 守恆失敗（TMU 域）：motions {lhs} != tasks {rhs}"))


def _check_tool_equal_duration(tasks, errors) -> None:
    """§7.6（ms 域，LB C4）：同 tool_id 所有 acquire 列 duration 相等；release 相等。"""
    acq: dict[str, set[int]] = defaultdict(set)
    rel: dict[str, set[int]] = defaultdict(set)
    for t in tasks:
        if t.tool_action == "acquire" and t.tool_id:
            acq[t.tool_id].add(t.duration)
        elif t.tool_action == "release" and t.tool_id:
            rel[t.tool_id].add(t.duration)
    for tid, durs in acq.items():
        if len(durs) > 1:
            errors.append(ProjectionError(E_TOOL_ACQUIRE_DURATION_MISMATCH, None, f"{tid} acquire duration 不一致：{sorted(durs)} ms", params={"tool_id": tid}))
    for tid, durs in rel.items():
        if len(durs) > 1:
            errors.append(ProjectionError(E_TOOL_RELEASE_DURATION_MISMATCH, None, f"{tid} release duration 不一致：{sorted(durs)} ms", params={"tool_id": tid}))


def _check_tool_shared_across_lot(tasks, errors) -> None:
    """§7.7：同 tool_id 不得同時出現在 Q>1 episode 與 Q=1 episode。"""
    q_gt1: dict[str, bool] = defaultdict(bool)
    q_eq1: dict[str, bool] = defaultdict(bool)
    for t in tasks:
        if not t.tool_id:
            continue
        if t.quantity > 1:
            q_gt1[t.tool_id] = True
        else:
            q_eq1[t.tool_id] = True
    for tid in set(q_gt1) & set(q_eq1):
        if q_gt1[tid] and q_eq1[tid]:
            errors.append(ProjectionError(E_TOOL_ID_SHARED_ACROSS_LOT, None, f"{tid} 同時用於 Q>1 與 Q=1 episode", params={"tool_id": tid}))


def _check_segment_atomic_offline(tasks, row_by_id, errors) -> None:
    """§7.4/§7.5：segment 依附 cub、wcub 互斥、offline 組內一致。"""
    # segment 跨 cub：同 segment 必同 group
    seg_groups: dict[str, set] = defaultdict(set)
    # cub offline 一致
    cub_offline: dict[int, set[int]] = defaultdict(set)
    # wcub 成員
    wcub_members: dict[int, list[LbTask]] = defaultdict(list)
    wcub_groups: dict[int, set] = defaultdict(set)
    wcub_offline: dict[int, set[int]] = defaultdict(set)

    for t in tasks:
        if t.segment:
            seg_groups[t.segment].add(t.group)
        if t.group is not None:
            cub_offline[t.group].add(t.offline_flag)
        if t.atomic_group is not None:
            wcub_members[t.atomic_group].append(t)
            wcub_groups[t.atomic_group].add(t.group)
            wcub_offline[t.atomic_group].add(t.offline_flag)
        # splittable ⊥ tool / Q>1
        if t.divisible and (t.tool_id is not None or t.quantity > 1):
            errors.append(ProjectionError(E_SPLITTABLE_CONFLICT, t.source_wi_row_id, "splittable 標在工具／批量 motion"))

    for seg, groups in seg_groups.items():
        if len(groups) > 1:
            errors.append(ProjectionError(E_SEGMENT_CROSS_GROUP, None, f"segment {seg} 跨 cub：{sorted(g for g in groups if g is not None)}"))
    for g, offs in cub_offline.items():
        if len(offs) > 1:
            errors.append(ProjectionError(E_OFFLINE_INCONSISTENT, None, f"cub {g} 內 offline 不一致"))
    for wc, members in wcub_members.items():
        for t in members:
            if t.tool_id is not None:
                errors.append(ProjectionError(E_ATOMIC_ON_TOOL_MOTION, t.source_wi_row_id, f"wcub {wc} 標在 tool-held motion"))
            if t.quantity > 1:
                errors.append(ProjectionError(E_ATOMIC_QUANTITY, t.source_wi_row_id, f"wcub {wc} 成員 Q>1"))
        if len(wcub_groups[wc]) > 1:
            errors.append(ProjectionError(E_ATOMIC_CROSS_GROUP, None, f"wcub {wc} 跨多個 cub：{sorted(x for x in wcub_groups[wc] if x is not None)}"))
        if len(wcub_offline[wc]) > 1:
            errors.append(ProjectionError(E_OFFLINE_INCONSISTENT, None, f"wcub {wc} 內 offline 不一致"))


def _check_general(rows, tasks, errors) -> None:
    """general：不帶 cub/wcub、必有 general_role、action 與 role 相容（§5.7）。"""
    action_by_row: dict[str, str] = {}
    for t in tasks:
        if t.general_role:
            action_by_row[t.source_wi_row_id] = t.action.lower()
    for r in rows:
        if not r.lb_tags.is_general:
            continue
        if (r.level.countersignature or "").strip() or (r.lb_tags.worker_cub or "").strip():
            errors.append(ProjectionError(E_GENERAL_IN_GROUP, r.wi_row_id, "general motion 帶 cub／wcub"))
        role = r.lb_tags.general_role
        if not role:
            errors.append(ProjectionError(E_GENERAL_ROLE_MISSING, r.wi_row_id, "is_general 但無 general_role"))
            continue
        action = action_by_row.get(r.wi_row_id, "")
        _check_role_action(role, action, r.wi_row_id, errors)


def _check_role_action(role: str, action: str, wi_row_id: str, errors) -> None:
    if role == "take_unit":
        if any(k in action for k in ("transport", "transfer", "scan")):
            errors.append(ProjectionError(E_GENERAL_ROLE_ACTION_MISMATCH, wi_row_id, f"take_unit action 含禁詞：{action!r}"))
    elif role == "transport":
        if "transport" not in action:
            errors.append(ProjectionError(E_GENERAL_ROLE_ACTION_MISMATCH, wi_row_id, f"transport action 未含 transport：{action!r}"))
    elif role == "scanner":
        if "scan" not in action:
            errors.append(ProjectionError(E_GENERAL_ROLE_ACTION_MISMATCH, wi_row_id, f"scanner action 未含 scan：{action!r}"))


def _check_narrative(rows, errors) -> None:
    """§6：要匯出的（非 general、非 SIMO 從屬）motion 缺 narrative_en → E_NARRATIVE_EN_MISSING。"""
    for r in rows:
        if r.lb_tags.is_general or r.simo_group_id:
            continue
        if not r.cycle.narrative_en:
            errors.append(ProjectionError(E_NARRATIVE_EN_MISSING, r.wi_row_id, "要匯出的 motion 無英文敘事"))


def _check_floating(tasks, row_by_id, warnings) -> None:
    """§5.10：非 general、無前置且無後繼 → W_FLOATING_TASK。"""
    has_succ: set[int] = set()
    for t in tasks:
        for p in t.predecessors:
            has_succ.add(p)
    for t in tasks:
        r = row_by_id.get(t.source_wi_row_id)
        if r and r.lb_tags.is_general:
            continue
        if not t.predecessors and t.task_id not in has_succ:
            warnings.append(ProjectionError(W_FLOATING_TASK, t.source_wi_row_id, f"task {t.task_id} 無前後約束"))


def _check_nb_simo(rows, warnings) -> None:
    """nb 標記丟棄 → W_NB_UNSUPPORTED；SIMO 從屬列略過 → W_SIMO_COLLAPSED。"""
    for r in rows:
        if (r.level.ascription or "") == "nb":
            warnings.append(ProjectionError(W_NB_UNSUPPORTED, r.wi_row_id, "nb 標記被丟棄"))
        if r.simo_group_id:
            warnings.append(ProjectionError(W_SIMO_COLLAPSED, r.wi_row_id, "SIMO 從屬列被略過"))


__all__ = ["validate"]
