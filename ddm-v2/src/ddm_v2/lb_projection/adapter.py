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
        repeat_counts: dict[str, int] = {}
        # slot index 對映：g2→"1"?（依 Spec §3.1 的 g2/p5/m3/x4/i5，slot index 由引擎 breakdown 位置定）。
        # WP2 只做結構搬運；實際 slot index 對映與 x_seconds 取值在 WP3 tmu.py 依 Spec §3.3 精確處理。
        x4 = slot_inputs.get("x4") or {}
        x_seconds = float(x4.get("x_seconds", 0) or 0)
        lv = r.get("level") or {}
        out.append(
            ProjectionRow.model_validate(
                {
                    "wi_row_id": str(r.get("wi_row_id") or r.get("id") or ""),
                    "seq_no": r.get("seq_no"),
                    "sub_activity": r.get("sub_activity"),
                    "key_parts": r.get("key_parts"),
                    "hand": r.get("hand"),
                    "object_vocab": r.get("object_vocab_id") or r.get("object_vocab"),
                    "tool_vocab": r.get("tool_vocab_id") or r.get("tool_vocab"),
                    "frequency": float(r.get("frequency", 1) or 1),
                    "simo_group_id": r.get("simo_group_id"),
                    "cycle": {
                        "seq_kind": cyc.get("seq_kind", "GM"),
                        "slot_tmus": slot_tmus,
                        "repeat_counts": repeat_counts,
                        "x_seconds": x_seconds,
                        "total_tmu": float(cyc.get("total_tmu", 0) or 0),
                        "tech_line": cyc.get("tech_line"),
                        "narrative_en": cyc.get("narrative_en") or cyc.get("narrative"),
                        "narrative_zh": cyc.get("narrative_zh"),
                        "slot_inputs": slot_inputs or None,
                        "rule_set_code": cyc.get("rule_set_code"),
                    },
                    "level": {
                        "ascription": lv.get("ascription"),
                        "level": lv.get("level"),
                        "countersignature": lv.get("countersignature"),
                        "parent_countersignature": lv.get("parent_countersignature"),
                        "order": lv.get("order"),
                        "number": lv.get("number"),
                        "number_count": lv.get("number_count"),
                    },
                    "lb_tags": {
                        "is_general": bool(lv.get("is_general", False)),
                        "general_role": lv.get("general_role"),
                        "offline": bool(lv.get("offline", False)),
                        "worker_cub": lv.get("worker_cub"),
                        "segment": lv.get("segment"),
                        "station_pin": lv.get("station_pin"),
                        "merge_lock": bool(lv.get("merge_lock", False)),
                        "splittable": bool(lv.get("splittable", False)),
                    },
                }
            )
        )
    return out


__all__ = ["load_fixture", "rows_from_worksheet", "parse_vocab", "rows_from_fixture_dicts"]
