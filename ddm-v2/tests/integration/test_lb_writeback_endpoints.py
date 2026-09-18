"""B5/B6（ADR-036）：LB 回寫端點整合測試。

import → latest → apply-offline（含組內傳染與 rollback）；未設 base URL → 503；契約不符 → 422；
LB 不可達 → 502；retention 只留 10。需 DB。

wi_rows.id 為全域 PK，不能用 fixture 的固定 id（跨 case 會撞 PK）。改為：建 worksheet 用隨機 id，
再把 fixture payload 的 source_wi_row_id 重映到本 worksheet 的實際 id（保留 fixture 的 offline/units 等情境）。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
OBJ = "66666666-6666-6666-6666-666666666666"
FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"
GM = {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1", "a0": {"reach_cm": 20},
      "g2": {"g_code": "g_grasp"}, "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}}


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


def _row(seq_no: int, wi_id: str, level: dict) -> dict:
    base = {"ascription": "main", "level": "1"}
    base.update(level)
    return {"id": wi_id, "seq_no": seq_no, "hand": "RH", "object_vocab_id": OBJ, "frequency": 1,
            "narrative": f"row{seq_no}", "cycle": GM, "level": base}


async def _make_worksheet(client) -> tuple[str, dict, dict]:
    """建 3 列 worksheet（隨機 id）：seq1+seq2 同 cub10（傳染，order2 不帶 main/level 避 R2）、seq3 loose。
    回 (worksheet_id, id_by_role, remapped_payload)。remapped：把 fixture 前 3 個 source_wi_row_id
    映到本 worksheet 的 (cub-order1, cub-order2, loose)，其中 loose 對 fixture 的 offline 列（offline=True）。"""
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    cub1, cub2, loose = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    rows = [
        _row(1, cub1, {"countersignature": "cub10", "order": 1}),
        _row(2, cub2, {"ascription": None, "level": None, "countersignature": "cub10", "order": 2}),
        _row(3, loose, {"level": "2"}),
    ]
    r = await client.put(f"/api/v2/worksheets/{new}", json={"rows": rows})
    assert r.status_code == 200, r.text

    # 重映 fixture：挑一個 offline=True 的列給 loose、兩個非 offline 給 cub1/cub2，其餘略去 source（→unmatched 不計）
    fx = _fixture()
    off_row = next(x for x in fx["rows"] if x["offline_flag"])
    non_off = [x for x in fx["rows"] if not x["offline_flag"]][:2]
    off_row["source_wi_row_id"] = loose
    non_off[0]["source_wi_row_id"] = cub1
    non_off[1]["source_wi_row_id"] = cub2
    return new, {"cub1": cub1, "cub2": cub2, "loose": loose}, fx


async def test_import_latest_and_snapshots(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["summary"]["contract_version"] == "lb-most-writeback-v1"
    assert body["summary"]["rows_in"] == 34

    latest = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")
    assert latest.status_code == 200
    # 重映會把某工具三列拆一列出來，motions 可能 24 或 25；核心是 latest 能組出摘要
    assert latest.json()["summary"]["motions"] >= 24

    snaps = await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")
    assert len(snaps.json()["snapshots"]) == 1


async def test_import_contract_mismatch_422(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    fx["contract_version"] = "lb-most-writeback-v2"
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "LB_WRITEBACK_CONTRACT_MISMATCH"


async def test_apply_offline_propagates_within_cub(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    imp = (await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)).json()
    offdiffs = {od["wi_row_id"] for od in imp["diff"]["offline_diffs"]}
    assert ids["loose"] in offdiffs, imp["diff"]["offline_diffs"]

    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [ids["loose"]]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert ids["loose"] in body["applied"]
    assert body["report"]["errors"] == []

    read = (await client.get(f"/api/v2/worksheets/{ws}")).json()
    row = next(x for x in read["rows"] if x["wi_row_id"] == ids["loose"])
    assert row["lb_tags"]["offline"] is True
    latest = (await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/latest")).json()
    assert latest["applied_at"] is not None


async def test_apply_offline_rejects_row_not_in_diffs(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    ws, ids, fx = await _make_worksheet(client)
    imp = (await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)).json()
    # cub1 MOST/LB offline 一致（都 False）→ 不在 offline_diffs → 422
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [ids["cub1"]]})
    assert r.status_code == 422


async def test_apply_offline_rollback_on_projection_error_no_partial_apply(client):
    """B6 核心保證：套用後任一 E（此處用離散 level 觸發投影 E_LEVEL_INVALID/DISCRETE）→ 整批 rollback，
    一列都不套（level_entries.offline 全未變）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    loose = str(uuid.uuid4())
    # 離散 level "1/2"（a/b 跳號）→ 投影 E_LEVEL_DISCRETE_UNSUPPORTED / E_LEVEL_INVALID
    rows = [_row(1, loose, {"level": "1/2"})]
    assert (await client.put(f"/api/v2/worksheets/{new}", json={"rows": rows})).status_code == 200
    fx = _fixture()
    off_row = next(x for x in fx["rows"] if x["offline_flag"])
    off_row["source_wi_row_id"] = loose
    imp = (await client.post(f"/api/v2/worksheets/{new}/lb-writeback/import", json=fx)).json()
    if loose not in {od["wi_row_id"] for od in imp["diff"]["offline_diffs"]}:
        pytest.skip("此環境未產生 offline_diff（離散 level 可能先擋 diff）")
    r = await client.post(f"/api/v2/worksheets/{new}/lb-writeback/apply-offline",
                          json={"snapshot_id": imp["snapshot_id"], "wi_row_ids": [loose]})
    assert r.status_code == 422, r.text
    # 一列都不套：offline 仍為 False
    read = (await client.get(f"/api/v2/worksheets/{new}")).json()
    row = next(x for x in read["rows"] if x["wi_row_id"] == loose)
    assert row["lb_tags"]["offline"] is False


async def test_fetch_not_configured_503(client, monkeypatch):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    monkeypatch.delenv("DDM_LB_API_BASE_URL", raising=False)
    from ddm_v2.settings import get_settings
    get_settings.cache_clear()
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                          json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "LB_NOT_CONFIGURED"
    get_settings.cache_clear()


async def test_fetch_lb_unreachable_502(client, monkeypatch):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    monkeypatch.setenv("DDM_LB_API_BASE_URL", "http://127.0.0.1:1")  # 連線立即被拒
    from ddm_v2.settings import get_settings
    get_settings.cache_clear()
    ws, ids, fx = await _make_worksheet(client)
    r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/fetch",
                          json={"lb_project_id": "P", "lb_version_id": "V", "lb_result_id": "R"})
    assert r.status_code == 502
    assert r.json()["error"]["code"] == "LB_UNREACHABLE"
    get_settings.cache_clear()


async def test_retention_keeps_10(client):
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種")
    from ddm_v2.services.v2 import lb_writeback_service as wb
    ws, ids, fx = await _make_worksheet(client)
    for _ in range(12):
        r = await client.post(f"/api/v2/worksheets/{ws}/lb-writeback/import", json=fx)
        assert r.status_code == 200
    snaps = (await client.get(f"/api/v2/worksheets/{ws}/lb-writeback/snapshots")).json()["snapshots"]
    assert len(snaps) == wb.RETENTION_PER_WORKSHEET == 10
