"""build_report：投影結果 → 報告 dict（ADR-035 D10 B4）。

`lb_export_report`（已存檔）與 `lb_preview_report`（dry-run）都呼叫本函式；既有鍵與值不變（回歸），
加法欄位 `rows[]`（每列摘要）、`hints[]`（確定性提示，§7.2）、`params`（errors/warnings 內）、
`tasks[]`（include_tasks 時）。只用投影資料，不看敘述文字。
"""
from __future__ import annotations

from typing import Any

from ddm_v2.lb_projection.emit import CONTRACT_VERSION, to_row
from ddm_v2.lb_projection.errors import ProjectionError
from ddm_v2.lb_projection.hints import hints as _hints
from ddm_v2.lb_projection.models import ProjectionRow


def _err_dict(e: ProjectionError) -> dict[str, Any]:
    return {"code": e.code, "wi_row_id": e.wi_row_id, "message": e.message, "params": e.params}


def _row_summaries(result: Any, rows: list[ProjectionRow]) -> list[dict[str, Any]]:
    """每個 motion（wi_row）一筆摘要：拆幾列、tool、repeat_n、Q、qty_scope、x_seconds、總 ms。"""
    # task 依 source_wi_row_id 分組
    tasks_by_wi: dict[str, list] = {}
    for t in result.tasks:
        tasks_by_wi.setdefault(t.source_wi_row_id, []).append(t)
    plan_by_wi = {p.row.wi_row_id: p for p in result.plans}

    out: list[dict[str, Any]] = []
    for r in rows:
        wid = r.wi_row_id
        p = plan_by_wi.get(wid)
        ts = tasks_by_wi.get(wid, [])
        parts = list(p.parts) if p is not None else ["use"]
        repeat_n = None
        if p is not None and p.tool_id is not None and p.decomposed is not None:
            repeat_n = p.decomposed.n
        # use task（單列＝該 task）取 quantity/qty_scope
        use_task = next((t for t in ts if t.tool_action == "use"), None) or (ts[0] if ts else None)
        quantity = use_task.quantity if use_task else 1
        qty_scope = use_task.qty_scope if use_task else None
        # 該列所有 task 的 effective ms 總和（cyclic 乘 quantity）
        dur_total = sum(
            t.duration * (t.quantity if t.qty_scope == "cyclic" else 1) for t in ts
        )
        out.append({
            "wi_row_id": wid,
            "task_ids": sorted(t.task_id for t in ts),
            "tool_id": p.tool_id if p is not None else None,
            "parts": parts,
            "repeat_n": repeat_n,
            "frequency": r.frequency,
            "quantity": quantity,
            "qty_scope": qty_scope,
            "x_seconds": r.cycle.x_seconds,
            "is_general": r.lb_tags.is_general,
            "general_role": r.lb_tags.general_role,
            "duration_ms_total": dur_total,
        })
    return out


def build_report(result: Any, rows: list[ProjectionRow], *, include_tasks: bool = False) -> dict[str, Any]:
    groups: dict[str, list[int]] = {}
    atomic: dict[str, list[int]] = {}
    for t in result.tasks:
        if t.group is not None:
            groups.setdefault(str(t.group), []).append(t.task_id)
        if t.atomic_group is not None:
            atomic.setdefault(str(t.atomic_group), []).append(t.task_id)

    report: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "tasks_out": len(result.tasks),
        "groups": groups,
        "atomic_groups": atomic,
        "tool_episodes": [],  # 維持 []（既有形狀）
        "errors": [_err_dict(e) for e in result.errors],
        "warnings": [_err_dict(w) for w in result.warnings],
        "rows": _row_summaries(result, rows),
        "hints": [h.as_dict() for h in _hints(result, rows)],
    }
    if include_tasks:
        report["tasks"] = [to_row(t) for t in result.tasks]
    return report


__all__ = ["build_report"]
