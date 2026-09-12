"""B3-2（ADR-035 D10）：rows_from_worksheet 與 rows_from_save_payload 對同一份資料產出相等 ProjectionRow。

存一份含工具列、Q>1 列、general 列、巢狀 cub 的 worksheet → 兩路徑逐鍵相等（letter 可忽略）。
"""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"


def _row(seq, **kw):
    base = {"id": str(uuid.uuid4()), "seq_no": seq, "hand": "RH", "object_vocab_id": OBJ, "frequency": kw.get("freq", 1),
            "narrative": f"步驟 {seq}", "wi_group": kw.get("wi_group"),
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": kw.get("level", {"ascription": "main", "level": "1"})}
    return base


async def test_two_paths_equivalent(client, db_session):
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    from ddm_v2.lb_projection.adapter import rows_from_save_payload, rows_from_worksheet
    from ddm_v2.models.v2.worksheet import MostWorksheet
    from ddm_v2.schemas.v2.worksheet import WorksheetSaveIn
    from ddm_v2.services.v2.worksheet_service import compute_rows_for_save, read_worksheet

    ws_id = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    rows = [
        _row(1, wi_group="通用", level={"ascription": "main", "level": "1", "is_general": True, "general_role": "take_unit"}),
        _row(2, freq=8, wi_group="批量", level={"ascription": "main", "level": "1", "segment": "batch"}),
        _row(3, wi_group="子組", level={"ascription": "main", "level": "2", "countersignature": "cub5", "order": 1}),
        _row(4, wi_group="子組", level={"ascription": None, "level": None, "countersignature": "cub5", "order": 2, "worker_cub": "wcub3"}),
    ]
    body = {"rows": rows}
    assert (await client.put(f"/api/v2/worksheets/{ws_id}", json=body)).status_code == 200

    # 路徑 A：read_worksheet → rows_from_worksheet（需要 vocab；用空 vocab 表即可比對結構）
    from ddm_v2.services.v2.export_service import _load_vocab

    vocab = await _load_vocab(db_session)
    data = await read_worksheet(db_session, uuid.UUID(ws_id))
    a = rows_from_worksheet(data, vocab)

    # 路徑 B：compute_rows_for_save → rows_from_save_payload
    ws = await db_session.get(MostWorksheet, uuid.UUID(ws_id))
    computed, _ctx = await compute_rows_for_save(db_session, ws, WorksheetSaveIn.model_validate(body))
    b = rows_from_save_payload(computed, vocab)

    assert len(a) == len(b) == 4
    a_by = {r.wi_row_id: r for r in a}
    b_by = {r.wi_row_id: r for r in b}
    assert set(a_by) == set(b_by)

    # 排除 narrative_zh／rule_set_code：投影層不消費（rs 另以 slot_inputs_by_row 的 rs 傳入、rule_set_code
    # 由 rs_by_row 承載），兩來源（read_worksheet vs save payload）在這兩欄本就不同，不影響投影。
    # slot_inputs **是**投影消費欄（driver decompose_engine／strip_repeats）→ 納入比對，但先正規化：
    # 遞迴丟掉值為 None 的鍵、sort_keys（兩來源鍵序不同但語意相同）。正規化後仍不等＝真差異。
    def _norm(v):
        if isinstance(v, dict):
            return {k: _norm(x) for k, x in sorted(v.items()) if x is not None}
        if isinstance(v, list):
            return [_norm(x) for x in v]
        return v

    def _proj_view(r):
        c = r.cycle
        return {
            "seq_no": r.seq_no, "hand": r.hand, "object_vocab": r.object_vocab, "tool_vocab": r.tool_vocab,
            "frequency": r.frequency, "simo_group_id": r.simo_group_id,
            "cycle": {"seq_kind": c.seq_kind, "slot_tmus": c.slot_tmus, "repeat_counts": c.repeat_counts,
                      "x_seconds": c.x_seconds, "total_tmu": c.total_tmu, "narrative_en": c.narrative_en,
                      "slot_inputs": _norm(c.slot_inputs)},
            "level": r.level.model_dump(), "lb_tags": r.lb_tags.model_dump(),
        }
    for wid in a_by:
        assert _proj_view(a_by[wid]) == _proj_view(b_by[wid]), f"row {wid} 投影相關欄位不一致（含正規化 slot_inputs）"
