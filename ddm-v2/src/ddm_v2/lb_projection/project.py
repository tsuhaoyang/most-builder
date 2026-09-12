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


def _release_events_by_chain(groups: dict, vocab: dict) -> dict[str, set[str]]:
    """每個 chain 內的 Pattern A release 事件（GM 且 object_vocab 指向工具）對應的工具集合。"""
    out: dict[str, set[str]] = {}
    for key, members in groups.items():
        tools: set[str] = set()
        for r in members:
            obj = r.object_vocab
            if obj and obj in vocab and vocab[obj].kind == "tool" and r.cycle.seq_kind == "GM":
                tools.add(obj)
        out[key] = tools
    return out


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
    held_by_chain: dict[str, set[str]] = {}
    for key, members in groups.items():
        members.sort(key=lambda m: (m.level.order or 0, m.seq_no))
        chain_plans, held = resolve_chain(members, vocab)
        held_by_chain[key] = held
        plans.extend(chain_plans)
        for p in chain_plans:
            warnings.extend(p.warnings)
    plans.sort(key=lambda p: p.row.seq_no)

    # held-at-end 細分（Spec §4.2）：某 chain 持有的工具若在**別的 chain** 出現 release 事件 → E_TOOL_CROSS_CHAIN；
    # 否則（無處釋放）→ E_TOOL_NOT_RELEASED。release 事件＝GM 且 object_vocab 指向工具（Pattern A）。
    release_chains = _release_events_by_chain(groups, vocab)
    for key, held in held_by_chain.items():
        for tool in sorted(held):
            other = [c for c, tools in release_chains.items() if tool in tools and c != key]
            if other:
                errors.append(ProjectionError(E_TOOL_CROSS_CHAIN, None, f"工具 {tool} 於 chain {key} 取得、chain {other[0]} 釋放"))
            else:
                errors.append(ProjectionError(E_TOOL_NOT_RELEASED, None, f"chain {key} 結束仍持有 {tool}"))

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
            action = _action_for(row, node.part, p)
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

    # ── validator：Spec §7 跨列不變量 ＋ 無主碼（收齊全部，不早停；note#1/#4）──
    from ddm_v2.lb_projection.validator import validate as _validate

    v_errors, v_warnings = _validate(tasks, rows, plans)
    errors.extend(v_errors)
    warnings.extend(v_warnings)

    csv_text = write_csv(tasks)
    return ProjectionResult(csv_text=csv_text, tasks=tasks, errors=errors, warnings=warnings)


def _action_for(row: ProjectionRow, part: str, plan: MotionPlan) -> str:
    """acquire→'pick up {tool}'、release→'put down {tool}'、否則 narrative_en（缺→''，由 validator 報 E_NARRATIVE_EN_MISSING）。"""
    if part == "acquire":
        return f"pick up {_tool_name(plan)}"
    if part == "release":
        return f"put down {_tool_name(plan)}"
    return row.cycle.narrative_en or ""


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
