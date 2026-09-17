"""B1（ADR-036）：lb_writeback_snapshots + lb_row_placements 資料模型 roundtrip。

用 LB 實跑 fixture（writeback_sample.json）灌一筆 snapshot ＋逐列 placement，讀回驗證；
驗 FK cascade（刪 snapshot → placements 連帶刪）。需 DB。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"
FIXTURE = Path(__file__).resolve().parents[2] / "docs" / "lb-integration" / "fixtures" / "writeback_sample.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


async def test_snapshot_and_placements_roundtrip(client, db_session) -> None:
    if (await client.get(f"/api/v2/worksheets/{WS}")).status_code != 200:
        pytest.skip("demo worksheet 未種")
    from ddm_v2.models.v2.lb_writeback import LbRowPlacement, LbWritebackSnapshot

    new = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    payload = _fixture()

    snap = LbWritebackSnapshot(
        id=uuid.uuid4(), worksheet_id=uuid.UUID(new),
        contract_version=payload["contract_version"],
        lb_project_id=payload["project_id"], lb_version_id=payload["version_id"],
        lb_result_id=payload["result_id"],
        generated_at=datetime.now(timezone.utc),
        unattended_machine_policy=payload["unattended_machine_policy"],
        unattended_machine_policy_source=payload["unattended_machine_policy_source"],
        source_url=None, payload=payload, created_by="IEC141289",
    )
    db_session.add(snap)
    await db_session.flush()

    for r in payload["rows"]:
        db_session.add(LbRowPlacement(
            id=uuid.uuid4(), snapshot_id=snap.id,
            source_wi_row_id=uuid.UUID(r["source_wi_row_id"]),
            task_id=r["task_id"], line_index=r["line_index"], station_index=r["station_index"],
            workers=r["workers"], units=r["units"], offline_flag=r["offline_flag"],
        ))
    await db_session.flush()

    # 讀回：列數 == fixture rows
    n = (await db_session.execute(
        select(func.count()).select_from(LbRowPlacement).where(LbRowPlacement.snapshot_id == snap.id)
    )).scalar_one()
    assert n == len(payload["rows"]) == 33

    # offline 列的 station_index 為 NULL、workers 為 []
    off = (await db_session.execute(
        select(LbRowPlacement).where(LbRowPlacement.snapshot_id == snap.id,
                                     LbRowPlacement.offline_flag.is_(True))
    )).scalars().all()
    assert off and all(p.station_index is None and p.workers == [] for p in off)

    # applied_at 預設 NULL（尚未套用）
    assert snap.applied_at is None and snap.applied_rows is None

    # FK cascade：刪 snapshot → placements 連帶刪
    await db_session.delete(snap)
    await db_session.flush()
    n2 = (await db_session.execute(
        select(func.count()).select_from(LbRowPlacement).where(LbRowPlacement.snapshot_id == snap.id)
    )).scalar_one()
    assert n2 == 0
