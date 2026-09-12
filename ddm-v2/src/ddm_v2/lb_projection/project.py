"""project：編排 adapter → level gate → tools → quantity → precedence → emit → report。

資料流不可重排（實作書 §1）。公開 project_rows(rows, vocab, rs=None)。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ddm_v2.lb_projection import mappers
from ddm_v2.lb_projection.emit import LbTask, write_csv
from ddm_v2.lb_projection.errors import (
    E_NARRATIVE_EN_MISSING,
    E_TOOL_CROSS_CHAIN,
    E_TOOL_NOT_RELEASED,
    ProjectionError,
)
from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab
from ddm_v2.lb_projection.precedence import build_motion_units, project_precedence
from ddm_v2.lb_projection.quantity import plan_quantity
from ddm_v2.lb_projection.tmu import decompose_static
from ddm_v2.lb_projection.tools import MotionPlan, resolve_chain


@dataclass
class ProjectionResult:
    csv_text: str
    tasks: list[LbTask]
    errors: list[ProjectionError] = field(default_factory=list)
    warnings: list[ProjectionError] = field(default_factory=list)


def _chain_key(r: ProjectionRow) -> str:
    cs = (r.level.countersignature or "").strip()
    # 巢狀 cub 併入其 parent sub 的 chain（held 狀態機 per top-level chain）
    parent = (r.level.parent_countersignature or "").strip()
    if cs.startswith("cub") and parent:
        return parent
    return cs or f"__standalone__{r.seq_no}"


def project_rows(
    rows: list[ProjectionRow],
    vocab: dict[str, ProjectionVocab],
    rs: Any = None,
    slot_inputs_by_row: dict[str, dict] | None = None,
) -> ProjectionResult:
    errors: list[ProjectionError] = []
    warnings: list[ProjectionError] = []
    slot_inputs_by_row = slot_inputs_by_row or {}

    # ── tools：per top-level chain 跑 held 狀態機 ──
    groups: dict[str, list[ProjectionRow]] = defaultdict(list)
    for r in rows:
        groups[_chain_key(r)].append(r)
    plans: list[MotionPlan] = []
    for _key, members in groups.items():
        members.sort(key=lambda m: (m.level.order or 0, m.seq_no))
        chain_plans, held = resolve_chain(members, vocab)
        if held:
            errors.append(ProjectionError(E_TOOL_NOT_RELEASED, None, f"chain 結束仍持有：{sorted(held)}"))
        plans.extend(chain_plans)
        for p in chain_plans:
            warnings.extend(p.warnings)
    plans.sort(key=lambda p: p.row.seq_no)

    # 跨 chain 持有偵測：同 tool 出現在多個 chain 的 acquire 但無同 chain release —— resolve_chain 已 per-chain，
    # 此處保守檢查（held 已在上面收）；跨 chain 由 held 非空體現，E_TOOL_CROSS_CHAIN 交由 validator（WP7）細分。
    _ = E_TOOL_CROSS_CHAIN

    # ── precedence：task_id 編號 ──
    task_id_map, prec_warns = project_precedence(rows, plans)
    warnings.extend(prec_warns)

    # ── 逐 motion 逐 part 組 LbTask ──
    units = build_motion_units(plans)
    tasks_by_id: dict[int, LbTask] = {}
    # 反查 predecessors：node_key(task_id) → preds。用 precedence 的 edge 重建。
    preds_by_task = _rebuild_predecessors(rows, plans, task_id_map)

    for p in plans:
        row = p.row
        dec = p.decomposed
        # tool motion 若 decomposed 未帶（general 等單列）→ None
        if dec is None and not row.lb_tags.is_general and p.tool_id is not None:
            dec = decompose_static(list(row.cycle.slot_tmus), row.cycle.repeat_counts, row.cycle.total_tmu, row.wi_row_id)

        qplan = plan_quantity(p, dec)
        warnings.extend(qplan.warnings)

        unit = units[row.wi_row_id]
        for node, pq in zip(unit.nodes, qplan.parts):
            tid = task_id_map[f"{node.wi_row_id}:{node.part}"]
            tool_action = node.part if p.tool_id is not None else None
            action = _action_for(row, node.part, p, errors)
            at, at_warns = mappers.action_type(row, tool_action, slot_inputs_by_row.get(row.wi_row_id))
            warnings.extend(at_warns)
            grp, g_warns = mappers.group_id(row, pq.quantity)
            warnings.extend(g_warns)
            tasks_by_id[tid] = LbTask(
                task_id=tid,
                action=action,
                source_wi_row_id=row.wi_row_id,
                action_type=at,
                adjustable=(1 if node.part in ("acquire", "release") and not row.lb_tags.merge_lock else 0),
                offline_flag=1 if row.lb_tags.offline else 0,
                divisible=1 if row.lb_tags.splittable else 0,
                quantity=pq.quantity,
                role_type=mappers.role_type(row),
                part_id=mappers.part_id(row),
                group=grp,
                atomic_group=mappers.atomic_id(row),
                duration=mappers.duration_ms(pq.duration_tmu),
                predecessors=sorted(preds_by_task.get(tid, set())),
                station_name=row.sub_activity,
                fixed_station=row.lb_tags.station_pin,
                tool_id=p.tool_id,
                tool_action=tool_action,
                segment=row.lb_tags.segment,
                qty_scope=pq.qty_scope,
                duration_basis=pq.duration_basis,
                general_role=row.lb_tags.general_role if row.lb_tags.is_general else None,
            )

    tasks = [tasks_by_id[t] for t in sorted(tasks_by_id)]
    csv_text = write_csv(tasks)
    return ProjectionResult(csv_text=csv_text, tasks=tasks, errors=errors, warnings=warnings)


def _action_for(row: ProjectionRow, part: str, plan: MotionPlan, errors: list[ProjectionError]) -> str:
    """acquire→'pick up {tool}'、release→'put down {tool}'、否則 narrative_en（缺→E_NARRATIVE_EN_MISSING）。"""
    if part == "acquire":
        return f"pick up {_tool_name(plan)}"
    if part == "release":
        return f"put down {_tool_name(plan)}"
    narr = row.cycle.narrative_en
    if not narr:
        errors.append(ProjectionError(E_NARRATIVE_EN_MISSING, row.wi_row_id, "缺 narrative_en，無法餵 LB"))
        return ""
    return narr


def _tool_name(plan: MotionPlan) -> str:
    """acquire/release 列的工具顯示名（tool_id 反 snake→空格）。"""
    return (plan.tool_id or "tool").replace("_", " ")


def _rebuild_predecessors(rows, plans, task_id_map) -> dict[int, set[int]]:
    from ddm_v2.lb_projection import precedence as P

    units = build_motion_units(plans)
    chains = P.build_chains(rows)
    edges = []
    for u in units.values():
        edges.extend(u.internal_edges)
    for ch in chains:
        for a, b in zip(ch.ordered_row_ids, ch.ordered_row_ids[1:]):
            edges.append((units[a].sink, units[b].source))
    for y, x in P._transitive_reduction(chains):
        edges.append((chains[y].sink_of(units), chains[x].source_of(units)))
    preds: dict[int, set[int]] = defaultdict(set)
    for a, b in edges:
        preds[task_id_map[f"{b.wi_row_id}:{b.part}"]].add(task_id_map[f"{a.wi_row_id}:{a.part}"])
    return preds


__all__ = ["ProjectionResult", "project_rows"]
