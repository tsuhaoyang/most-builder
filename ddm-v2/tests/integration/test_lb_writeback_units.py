"""LB 回寫件數語意（Howard 2026-09-18 裁：C＋退路）。需 DB。

- 件數取 qty_scope=="cyclic" 那列；payload 沒有 qty_scope（舊快照／LB 尚未加欄）→ 各列取最大值、標為推算。
  setup 列的 units 是 used（經手次數）不是件數，不可跨列加總（LB ADR-008 D3）。
- 比對基準是 MOST 自己投影出的 quantity Q（契約 §3.2），不是 frequency：持工具 frequency F>1 投影成三列
  皆 cyclic、Q=F，LB 每列 Σunits=F；舊做法加總成 3F 又拿 frequency 比，會誤報。

worksheet 用隨機 id（wi_rows.id 是全域主鍵，測試不佔固定 id）；整段在外層 transaction 內，結束 rollback。
"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"
RS = "MINIMOST_FACTORY_V2"
GM = {"seq": "GM", "rule_set_code": RS, "a0": {"reach_cm": 20}, "g2": {"g_code": "g_tap"},
      "a3": {"reach_cm": 20}, "p5": {"p_base_code": "p_place_none"}, "a6": {"reach_cm": 20}}
CM = {"seq": "CM", "rule_set_code": RS, "a0": {"reach_cm": 16}, "g2": {"g_code": "g_tap"},
      "m3": {"m_components": [{"verb_code": "m_screw"}]}, "x4": {"x_code": "x_none"},
      "i5": {"i_code": "i_check"}, "a6": {"reach_cm": 16}}


def _cm_repeat(n: int) -> dict:
    """持工具「拿一次做 n 次」：M／X／I 三格同步 repeat n（投影 → acquire／use／release、Q=n）。"""
    return {**CM, "m3": {**CM["m3"], "repeat_count": n}, "x4": {**CM["x4"], "repeat_count": n},
            "i5": {**CM["i5"], "repeat_count": n}}


async def _worksheet(client, *, tool_freq: float = 3, tool_cycle: dict | None = None) -> tuple[str, str, str]:
    """持工具 CM（預設 frequency 3）＋非工具 GM（frequency 8）。回 (worksheet_id, tool_row_id, lot_row_id)。"""
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    tool = await client.post("/api/v2/vocab", json={"kind": "tool", "name_zh": "測試起子", "name_en": f"it driver {uuid.uuid4().hex[:6]}"})
    assert tool.status_code == 201, tool.text
    ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    tool_row, lot_row = str(uuid.uuid4()), str(uuid.uuid4())
    rows = [
        {"id": tool_row, "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ, "tool_vocab_id": tool.json()["id"],
         "frequency": tool_freq, "cycle": tool_cycle or CM, "level": {"ascription": "main", "level": "1"}},
        {"id": lot_row, "seq_no": 2, "hand": "RH", "object_vocab_id": OBJ, "frequency": 8,
         "cycle": GM, "level": {"ascription": "main", "level": "2"}},
    ]
    r = await client.put(f"/api/v2/worksheets/{ws}", json={"rows": rows})
    assert r.status_code == 200, r.text
    return ws, tool_row, lot_row


async def _projected(client, ws: str) -> dict[str, list[tuple[int, str | None]]]:
    rep = (await client.get(f"/api/v2/worksheets/{ws}/export/lb-report", params={"include_tasks": "true"})).json()
    out: dict[str, list[tuple[int, str | None]]] = {}
    for t in rep["tasks"]:  # lb-report 的 tasks 為 CSV 字串值
        out.setdefault(t["source_wi_row_id"], []).append((int(t["quantity"]), t["qty_scope"] or None))
    return out


def _payload(tool_row: str, lot_row: str, *, tool_units: int | list[int | None], lot_units: int | None,
             scopes: list) -> dict:
    per_row = tool_units if isinstance(tool_units, list) else [tool_units] * len(scopes)

    def _units(worker: str, n: int | None):
        return None if n is None else [{"worker": worker, "units": n}]

    rows = [{"source_wi_row_id": tool_row, "task_id": 1 + i, "offline_flag": False, "line_index": 0,
             "station_index": 0, "workers": ["W-0-0"], "units": _units("W-0-0", n),
             **({"qty_scope": s} if s is not None else {})}
            for i, (s, n) in enumerate(zip(scopes, per_row))]
    rows.append({"source_wi_row_id": lot_row, "task_id": 4, "offline_flag": False, "line_index": 0,
                 "station_index": 1, "workers": ["W-1-0"], "units": _units("W-1-0", lot_units)})
    return {"contract_version": "lb-most-writeback-v1", "project_id": "p", "version_id": "original",
            "result_id": "r", "unattended_machine_policy": "free", "unattended_machine_policy_source": "persisted",
            "rows": rows}


async def test_projection_is_the_baseline(client):
    """前提：投影把持工具 F=3 拆成三列、皆 cyclic、Q=3；非工具 F=8 → 單列 cyclic Q=8。"""
    ws, tool_row, lot_row = await _worksheet(client)
    proj = await _projected(client, ws)
    assert sorted(proj[tool_row]) == [(3, "cyclic")] * 3
    assert proj[lot_row] == [(8, "cyclic")]


@pytest.mark.parametrize("scopes, source", [
    ([None, None, None], "inferred_max"),          # 舊快照／LB 尚未加 qty_scope → 推算
    (["cyclic", "cyclic", "cyclic"], "cyclic"),    # LB 加欄後
])
async def test_tool_frequency_gt1_no_false_mismatch(client, scopes, source):
    ws, tool_row, lot_row = await _worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                          json=_payload(tool_row, lot_row, tool_units=3, lot_units=8, scopes=scopes))
    assert r.status_code == 200, r.text
    motions = r.json()["diff"]["motions"]
    assert (motions[tool_row]["units_total"], motions[tool_row]["units_source"]) == (3, source)  # 不是 9
    assert r.json()["diff"]["unit_mismatches"] == []
    assert r.json()["summary"]["units_baseline"] == {"status": "ok", "reasons": []}


async def test_mismatch_compares_against_projected_quantity(client):
    """LB 件數與投影 Q 不符才報；比對基準是投影 Q（此列 8）。"""
    ws, tool_row, lot_row = await _worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                          json=_payload(tool_row, lot_row, tool_units=3, lot_units=7, scopes=[None] * 3))
    assert r.status_code == 200, r.text
    assert r.json()["diff"]["unit_mismatches"] == [
        {"wi_row_id": lot_row, "expected_n": 8, "units_total": 7, "units_source": "inferred_max"}
    ]
    latest = (await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")).json()
    assert latest["diff"]["unit_mismatches"] == r.json()["diff"]["unit_mismatches"]


async def test_repeat_row_compares_against_projected_q_not_frequency(client):
    """持工具 repeat 4、frequency 1：投影 Q=4（三列 Q=4）。LB 1/3/1 → mismatch expected_n=4——拿 frequency 當基準
    （1）會完全不比，這個案例分得出比對基準是投影 Q。"""
    ws, tool_row, lot_row = await _worksheet(client, tool_freq=1, tool_cycle=_cm_repeat(4))
    assert sorted((await _projected(client, ws))[tool_row]) == [(4, "cyclic"), (4, "setup"), (4, "setup")]
    ok = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                           json=_payload(tool_row, lot_row, tool_units=[1, 4, 1], lot_units=8, scopes=[None] * 3))
    assert ok.status_code == 200, ok.text
    assert ok.json()["diff"]["motions"][tool_row]["units_total"] == 4
    assert ok.json()["diff"]["unit_mismatches"] == []
    bad = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                            json=_payload(tool_row, lot_row, tool_units=[1, 3, 1], lot_units=8, scopes=[None] * 3))
    assert bad.json()["diff"]["unit_mismatches"] == [
        {"wi_row_id": tool_row, "expected_n": 4, "units_total": 3, "units_source": "inferred_max"}
    ]


async def test_projection_failure_marks_baseline_unavailable_not_500(client):
    """MOST 端工序暫時投影不出來（持工具 F=3 且 N=3 → 投影拋 E_TOOL_FREQ_AND_REPEAT）：import／latest 照常 200，
    件數不比、但 summary.units_baseline 明確標 unavailable＋E 碼（不是靜默當成一致）。"""
    ws, tool_row, lot_row = await _worksheet(client, tool_freq=3, tool_cycle=_cm_repeat(3))
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                          json=_payload(tool_row, lot_row, tool_units=3, lot_units=7, scopes=[None] * 3))
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["units_baseline"] == {"status": "unavailable", "reasons": ["E_TOOL_FREQ_AND_REPEAT"]}
    assert r.json()["diff"]["unit_mismatches"] == []
    latest = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")
    assert latest.status_code == 200, latest.text
    assert latest.json()["summary"]["units_baseline"]["status"] == "unavailable"


async def test_no_units_in_payload_lists_uncomparable(client):
    ws, tool_row, lot_row = await _worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                          json=_payload(tool_row, lot_row, tool_units=[None] * 3, lot_units=None, scopes=[None] * 3))
    assert r.status_code == 200, r.text
    # 「不必比」只由 MOST 投影判斷（不從 LB 缺值推論全為 Q=1）：MOST 有 Q>1、LB 整份沒給件數 → 基準 ok，
    # 兩個動作都明列為沒得比，而不是靜默當成一致
    assert r.json()["summary"]["units_baseline"] == {"status": "ok", "reasons": []}
    assert sorted(r.json()["diff"]["units_uncomparable"], key=lambda x: x["expected_n"]) == [
        {"wi_row_id": tool_row, "expected_n": 3, "reason": "no_units"},
        {"wi_row_id": lot_row, "expected_n": 8, "reason": "no_units"},
    ]


@pytest.mark.parametrize("scope", ["Cyclic", "auto", ""])
async def test_import_rejects_unknown_qty_scope_422(client, scope):
    ws, tool_row, lot_row = await _worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import",
                          json=_payload(tool_row, lot_row, tool_units=3, lot_units=8, scopes=[scope] * 3))
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_all_q1_worksheet_baseline_not_needed(client):
    """MOST 投影沒有任何 Q>1 → not_needed（由 MOST 端判斷）。"""
    ws, tool_row, lot_row = await _worksheet(client, tool_freq=1)
    body = {"rows": [
        {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ, "frequency": 1,
         "cycle": GM, "level": {"ascription": "main", "level": "1"}},
    ]}
    assert (await client.put(f"/api/v2/worksheets/{ws}", json=body)).status_code == 200
    only = body["rows"][0]["id"]
    payload = _payload(only, only, tool_units=[None], lot_units=None, scopes=[None])
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["summary"]["units_baseline"] == {"status": "not_needed", "reasons": []}


async def test_latest_with_stale_snapshot_is_422_not_500(client, db_session):
    """早期寬鬆匯入存下、現行驗證讀不回來的快照（units 為 8.0）：latest 回 422（請重新取得），不是無信封 500。"""
    from datetime import datetime, timezone

    from ddm_v2.models.v2.lb_writeback import LbWritebackSnapshot

    ws, tool_row, lot_row = await _worksheet(client)
    payload = _payload(tool_row, lot_row, tool_units=3, lot_units=8, scopes=[None] * 3)
    payload["rows"][-1]["units"] = [{"worker": "W-1-0", "units": 8.0}]
    db_session.add(LbWritebackSnapshot(
        id=uuid.uuid4(), worksheet_id=uuid.UUID(ws), contract_version=payload["contract_version"],
        lb_project_id="p", lb_version_id="original", lb_result_id="r", generated_at=datetime.now(timezone.utc),
        unattended_machine_policy="free", unattended_machine_policy_source="persisted",
        source_url=None, payload=payload, created_by="IEC141289",
    ))
    await db_session.flush()
    r = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "請重新取得" in r.json()["error"]["message"]
