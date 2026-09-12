"""adapter：read_worksheet() dict / fixture → list[ProjectionRow]（＋ vocab 表）。

adapter **只吃 dict**，不 import SQLAlchemy／FastAPI（實作書 §1）。DB 存取（load_vocab）
留在 `services/v2/export_service.py`——adapter 收到的是已查好的 vocab dict。

出處：Spec §1；實作書 WP2。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any

from ddm_v2.lb_projection.models import ProjectionRow, ProjectionVocab


def parse_vocab(raw: dict[str, dict[str, Any]]) -> dict[str, ProjectionVocab]:
    """vocab dict（key → {kind, name_en}）→ {key: ProjectionVocab}。"""
    return {key: ProjectionVocab.model_validate(v) for key, v in raw.items()}


def rows_from_fixture_dicts(raw_rows: list[dict[str, Any]]) -> list[ProjectionRow]:
    """fixture `rows[]`（已是 ProjectionRow 形狀）→ list[ProjectionRow]。"""
    return [ProjectionRow.model_validate(r) for r in raw_rows]


def load_fixture(
    path: str | pathlib.Path,
) -> tuple[list[ProjectionRow], dict[str, ProjectionVocab], dict[str, Any]]:
    """讀黃金 fixture → (rows, vocab, meta)。

    meta 保留 fixture 頂層（contract_version/rule_set_code/tmu_to_ms/worksheet…）供測試對照。
    """
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    rows = rows_from_fixture_dicts(data["rows"])
    vocab = parse_vocab(data.get("vocab", {}))
    meta = {k: v for k, v in data.items() if k not in ("rows", "vocab")}
    return rows, vocab, meta


def rows_from_worksheet(data: dict[str, Any], vocab: dict[str, ProjectionVocab]) -> list[ProjectionRow]:
    """`read_worksheet()` 回傳 dict → list[ProjectionRow]（DB 路徑）。

    對映（實作書 WP2）：
    - `cycle.slot_tmus` ← `cycle.computed.breakdown[].tmu`（read_worksheet 需加法輸出 `breakdown`，WP1/WP2）。
    - `repeat_counts` ← `slot_inputs` 的 `g2/p5/m3/x4/i5.repeat_count`。
    - `x_seconds` ← `slot_inputs.x4.x_seconds`。
    - level 六欄 ← `data.rows[].level`；lb_tags ← level 的 LB 標記欄（WP1 加）。
    vocab 在此僅隨行傳遞（kind/name_en 查表在 tools/mappers 用）；本函式不碰 DB。
    """
    out: list[ProjectionRow] = []
    for r in data.get("rows", []):
        cyc = r.get("cycle") or {}
        # breakdown 位置：read_worksheet 加法擴充在 cycle 頂層加 "breakdown"（實作書 WP2）；
        # 現況 most_cycles.computed 內本就有 breakdown。兩處都支援，頂層優先。
        breakdown = cyc.get("breakdown") or (cyc.get("computed") or {}).get("breakdown") or []
        slot_tmus = [float(b.get("tmu", 0) or 0) for b in breakdown] if breakdown else [0.0] * 7
        slot_inputs = cyc.get("slot_inputs") or {}
        x4 = slot_inputs.get("x4") or {}
        x_seconds = float(x4.get("x_seconds", 0) or 0)
        lv = r.get("level") or {}
        tags = r.get("lb_tags") or {}
        out.append(_build_projection_row(
            wi_row_id=str(r.get("wi_row_id") or r.get("id") or ""),
            seq_no=r.get("seq_no"),
            sub_activity=r.get("sub_activity"), key_parts=r.get("key_parts"), hand=r.get("hand"),
            object_vocab=r.get("object_vocab_id") or r.get("object_vocab"),
            tool_vocab=r.get("tool_vocab_id") or r.get("tool_vocab"),
            frequency=float(r.get("frequency", 1) or 1),
            simo_group_id=r.get("simo_group_id"),
            seq_kind=cyc.get("seq_kind", "GM"), slot_tmus=slot_tmus, x_seconds=x_seconds,
            total_tmu=float(cyc.get("total_tmu", 0) or 0), tech_line=cyc.get("tech_line"),
            narrative_en=cyc.get("narrative_en"), narrative_zh=cyc.get("narrative_zh"),
            slot_inputs=slot_inputs or None, rule_set_code=cyc.get("rule_set_code"),
            level=lv, lb_tags=tags,
        ))
    return out


def _build_projection_row(
    *, wi_row_id: str, seq_no: Any, sub_activity: Any, key_parts: Any, hand: Any,
    object_vocab: Any, tool_vocab: Any, frequency: float, simo_group_id: Any,
    seq_kind: str, slot_tmus: list[float], x_seconds: float, total_tmu: float,
    tech_line: Any, narrative_en: Any, narrative_zh: Any, slot_inputs: Any, rule_set_code: Any,
    level: dict[str, Any], lb_tags: dict[str, Any],
) -> ProjectionRow:
    """唯一對映規則（read_worksheet 與 save payload 兩路徑共用；避免兩份漂移）。

    level 六欄 ← level dict；lb_tags ← 頂層 lb_tags（缺 key 時 fallback 到 level dict，相容舊資料）。
    repeat_counts ← slot_inputs 的 g2/m3/x4/i5/p5 的 repeat_count（鍵＝slot index，對齊 tmu.py §3.3）。
    """
    def _tag(key: str, default: Any = None) -> Any:
        return lb_tags.get(key, level.get(key, default))

    # slot_inputs（CycleIn dump）→ repeat_counts（slot index → N）；tmu.repeat_block 依此找 R。
    # slot 對映：g2→2、m3→3、x4→4、i5→5、p5→5（GM）。
    repeat_counts: dict[str, int] = {}
    si = slot_inputs if isinstance(slot_inputs, dict) else {}
    for slot_key, idx in (("g2", "2"), ("m3", "3"), ("x4", "4"), ("i5", "5"), ("p5", "5")):
        slot = si.get(slot_key)
        if isinstance(slot, dict):
            rc = slot.get("repeat_count")
            if rc not in (None, 1):
                repeat_counts[idx] = int(rc)

    return ProjectionRow.model_validate({
        "wi_row_id": wi_row_id, "seq_no": seq_no,
        "sub_activity": sub_activity, "key_parts": key_parts, "hand": hand,
        "object_vocab": object_vocab, "tool_vocab": tool_vocab,
        "frequency": frequency, "simo_group_id": simo_group_id,
        "cycle": {
            "seq_kind": seq_kind, "slot_tmus": slot_tmus, "repeat_counts": repeat_counts,
            "x_seconds": x_seconds, "total_tmu": total_tmu, "tech_line": tech_line,
            "narrative_en": narrative_en, "narrative_zh": narrative_zh,
            "slot_inputs": slot_inputs, "rule_set_code": rule_set_code,
        },
        "level": {
            "ascription": level.get("ascription"), "level": level.get("level"),
            "countersignature": level.get("countersignature"),
            "parent_countersignature": level.get("parent_countersignature"),
            "order": level.get("order"), "number": level.get("number"),
            "number_count": level.get("number_count"),
        },
        "lb_tags": {
            "is_general": bool(_tag("is_general", False)),
            "general_role": _tag("general_role"),
            "action_type": _tag("action_type"),
            "offline": bool(_tag("offline", False)),
            "worker_cub": _tag("worker_cub"),
            "segment": _tag("segment"),
            "station_pin": _tag("station_pin"),
            "merge_lock": bool(_tag("merge_lock", False)),
            "splittable": bool(_tag("splittable", False)),
            "machine_unattended": _tag("machine_unattended"),  # 三態：保留 None/True/False，不 bool() 強制
        },
    })


def rows_from_save_payload(computed: list[Any], vocab: dict[str, ProjectionVocab]) -> list[ProjectionRow]:
    """WorksheetSaveIn 的 ComputedRow（worksheet_service.compute_rows_for_save）→ list[ProjectionRow]（dry-run）。

    與 rows_from_worksheet 共用 _build_projection_row（同一對映規則）。slot_tmus 直接取引擎回傳
    （非經 DB breakdown）；slot_inputs=row_in.cycle.model_dump；level/lb_tags 來自 row_in.level。
    """
    out: list[ProjectionRow] = []
    for cr in computed:
        r = cr.row_in           # WiRowSaveIn
        res = cr.result         # compute_cycle 回傳
        lv = r.level
        lb = {
            "is_general": lv.is_general, "general_role": lv.general_role, "action_type": lv.action_type,
            "offline": lv.offline, "worker_cub": lv.worker_cub, "segment": lv.segment,
            "station_pin": lv.station_pin, "merge_lock": lv.merge_lock,
            "machine_unattended": lv.machine_unattended,
        }
        level_d = {
            "ascription": lv.ascription, "level": lv.level, "countersignature": lv.countersignature,
            "parent_countersignature": lv.parent_countersignature, "order": lv.order,
            "number": lv.number, "number_count": lv.number_count,
        }
        out.append(_build_projection_row(
            wi_row_id=str(r.id), seq_no=r.seq_no,
            sub_activity=r.sub_activity, key_parts=r.key_parts, hand=r.hand,
            object_vocab=str(r.object_vocab_id) if r.object_vocab_id else None,
            tool_vocab=str(r.tool_vocab_id) if r.tool_vocab_id else None,
            frequency=float(r.frequency or 1), simo_group_id=cr.simo_group_id,
            seq_kind=res.seq, slot_tmus=list(res.slot_tmus), x_seconds=float(getattr(r.cycle, "x_seconds", 0) or 0),
            total_tmu=float(res.total_tmu), tech_line=res.tech_line,
            narrative_en=cr.narrative_en, narrative_zh=cr.narrative_zh,
            slot_inputs=cr.cycle_json, rule_set_code=r.cycle.rule_set_code,
            level=level_d, lb_tags=lb,
        ))
    return out


__all__ = ["load_fixture", "rows_from_worksheet", "rows_from_save_payload", "parse_vocab", "rows_from_fixture_dicts"]
