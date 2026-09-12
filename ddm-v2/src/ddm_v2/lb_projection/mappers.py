"""mappers：group / atomic / duration_ms / action_type / role_type / part_id（Spec §6、附錄 A）。

action_type 五級優先序（ruling B, 2026-09-12；Spec §6）：
 ① acquire→`pick`、release→`put`（恆值）
 ② general → general_role 映射（take_unit→take／scanner→scan／transport→transport）
 ③ `lb_tags.action_type`（IE 標定；golden 走這級）
 ④ 附錄 A（只在有 slot_inputs 時可跑）
 ⑤ `op` ＋ W_ACTION_TYPE_FALLBACK
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from ddm_v2.lb_projection.errors import W_ACTION_TYPE_FALLBACK, W_AUTO_GROUP_FOR_LOT, ProjectionError
from ddm_v2.lb_projection.models import ProjectionRow

_GENERAL_ROLE_ACTION = {"take_unit": "take", "scanner": "scan", "transport": "transport"}
_CS_NUM = re.compile(r"(\d+)")


def duration_ms(tmu: float) -> int:
    """round_half_up(tmu × 36)（Spec §6 duration；1 TMU = 0.036 s = 36 ms）。"""
    return int((Decimal(str(tmu)) * 36).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def part_id(row: ProjectionRow) -> str | None:
    """general → 字面 'General'；否則 key_parts（Spec §6）。"""
    if row.lb_tags.is_general:
        return "General"
    return row.key_parts


def group_id(row: ProjectionRow, quantity: int) -> tuple[int | None, list[ProjectionError]]:
    """cub\\d+ → 數字；Q>1 且無 cub → 9000+seq_no ＋ W_AUTO_GROUP_FOR_LOT；否則空（Spec §6）。"""
    warns: list[ProjectionError] = []
    cs = (row.level.countersignature or "").strip()
    if cs.startswith("cub"):
        m = _CS_NUM.search(cs)
        if m:
            return int(m.group(1)), warns
    if quantity > 1:
        warns.append(ProjectionError(W_AUTO_GROUP_FOR_LOT, row.wi_row_id, f"Q>1 無 cub，合成 group {9000 + row.seq_no}"))
        return 9000 + row.seq_no, warns
    return None, warns


def atomic_id(row: ProjectionRow) -> int | None:
    """wcub\\d+ → 數字（Spec §6 atomic_group）。"""
    w = (row.lb_tags.worker_cub or "").strip()
    if w.startswith("wcub"):
        m = _CS_NUM.search(w)
        if m:
            return int(m.group(1))
    return None


def role_type(row: ProjectionRow) -> str:
    """CM 且 x_seconds ≥ 1 → machine；否則 human（Spec §6、D17）。"""
    if row.cycle.seq_kind == "CM" and (row.cycle.x_seconds or 0) >= 1:
        return "machine"
    return "human"


def action_type(
    row: ProjectionRow,
    tool_action: str | None,
    slot_inputs: dict[str, Any] | None = None,
) -> tuple[str, list[ProjectionError]]:
    """五級優先序（ruling B；Spec §6、附錄 A）。"""
    warns: list[ProjectionError] = []
    # ① acquire/release 恆值
    if tool_action == "acquire":
        return "pick", warns
    if tool_action == "release":
        return "put", warns
    # ② general
    if row.lb_tags.is_general:
        gr = row.lb_tags.general_role
        if gr and gr in _GENERAL_ROLE_ACTION:
            return _GENERAL_ROLE_ACTION[gr], warns
    # ③ lb_tags.action_type（IE 標定）
    if row.lb_tags.action_type:
        return row.lb_tags.action_type, warns
    # ④ 附錄 A（只在有 slot_inputs 時）
    if slot_inputs is not None:
        derived = _appendix_a(row, slot_inputs)
        if derived:
            return derived, warns
    # ⑤ fallback
    warns.append(ProjectionError(W_ACTION_TYPE_FALLBACK, row.wi_row_id, "無 action_type 來源，回退 op"))
    return "op", warns


def _appendix_a(row: ProjectionRow, slot_inputs: dict[str, Any]) -> str | None:
    """附錄 A 結構推導（需 slot codes）。golden 不走此路徑；fallback 測試以真 slot_inputs 覆蓋。"""
    slots = slot_inputs.get("slots") or {}

    def s(i: int) -> dict:
        return slots.get(i) or slots.get(str(i)) or {}

    if row.cycle.seq_kind == "CM":
        x = s(4)
        i = s(5)
        m = s(3)
        x_code = (x.get("x_code") or "")
        if "scan" in x_code:
            return "scan"
        if "fasten" in x_code or "screw" in x_code:
            return "fasten"
        if (row.cycle.x_seconds or 0) >= 1 or any(k in x_code for k in ("press", "stake", "glue")):
            return "press"
        if not x_code and i.get("i_code") and not m.get("m_components"):
            return "inspect"
        # CM other → M verb English
        comps = m.get("m_components") or []
        if comps:
            verb = (comps[0].get("verb_code") or "").replace("m_", "")
            return verb or "move"
        return "move"
    # GM
    p = s(5)
    g = s(2)
    addons = p.get("p_addon_codes") or []
    if any("insert" in a for a in addons):
        return "insert"
    if any(k in a for a in addons for k in ("snap", "pressure")):
        return "latch"
    if (g.get("g_code") or "") == "g_collect":
        return "collect"
    p_base = p.get("p_base_code") or ""
    return "pick" if p_base == "p_hold" else "place"


__all__ = ["duration_ms", "part_id", "group_id", "atomic_id", "role_type", "action_type"]
