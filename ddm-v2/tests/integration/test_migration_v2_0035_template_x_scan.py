"""v2_0035 migration 驗證：範本庫的 V1 遺留 X 碼 `x_scan` → `x_scan_bar`。

直接執行 migration 模組匯出的**同一份 SQL 常數**（不是測試裡另抄一份的近似品），
全程在 conftest 的 rollback transaction 內，不落真實 DB。

涵蓋：
1. 有壞列 → 被修好，且 `x_seconds` 一併正規化為 0（fixed 模式秒數由字典提供）；
2. 不誤傷：其他 X 碼、GM 範本（x4 為 null）原封不動；
3. 冪等：再跑一次 no-op；
4. 修完的 payload 真的能被引擎算出來（不是只把字串換掉就算數）；
5. 真實 DB 現況已無 `x_scan`（環境確實跑過 migration／seed 已修）。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import uuid

import pytest
from sqlalchemy import text

from ddm_v2.most_engine import build_from_seed_v2, compute_cycle
from ddm_v2.schemas.v2.most import CycleIn, cycle_in_to_engine

pytestmark = pytest.mark.integration


def _load_migration():
    p = (
        pathlib.Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions_v2"
        / "v2_0035_motion_template_x_scan_code.py"
    )
    spec = importlib.util.spec_from_file_location("_v2_0035", p)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()

_CM_CYCLE = {
    "seq": "CM",
    "a0": {"reach_cm": 25},
    "b1": {},
    "g2": {"g_code": "g_touch"},
    # M 格留空：孤兒 `m_hand`（計價維度單獨成格）已被引擎判為 M_COMPANION_WITHOUT_VERB，
    # 範本庫的既有資料由 migration v2_0042 清掉。這裡的重點是 X 碼，M 用合法的空格即可。
    "m3": {"m_components": []},
    "x4": {"x_code": "x_scan", "x_seconds": 1.5},
    "i5": {"i_code": "i_check"},
    "a6": {},
}
_GM_CYCLE = {
    "seq": "GM",
    "a0": {"reach_cm": 20},
    "b1": {},
    "g2": {"g_code": "g_grasp"},
    "a3": {"reach_cm": 15},
    "b4": {},
    "p5": {"p_base_code": "p_hold"},
    "a6": {},
}


async def _insert_template(session, cycle: dict, *, seq_kind: str) -> uuid.UUID:
    """繞過 ORM 直接 INSERT，確保測到的是 migration 的 SQL 而非應用層行為。"""
    tid = uuid.uuid4()
    await session.execute(
        text(
            """
            INSERT INTO motion_templates
                (id, name_zh, seq_kind, keywords, cycle_template, status,
                 created_at, updated_at)
            VALUES (:id, :name, :seq, '{}'::text[], CAST(:cyc AS jsonb), 'draft', NOW(), NOW())
            """
        ),
        {"id": tid, "name": f"mig35-{tid.hex[:8]}", "seq": seq_kind, "cyc": json.dumps(cycle)},
    )
    return tid


async def _x4(session, tid: uuid.UUID) -> dict | None:
    return (await session.execute(
        text("SELECT cycle_template -> 'x4' FROM motion_templates WHERE id = :i"), {"i": tid},
    )).scalar_one()


async def test_fix_rewrites_x_scan_and_normalizes_seconds(db_session):
    tid = await _insert_template(db_session, _CM_CYCLE, seq_kind="CM")

    await db_session.execute(text(MIG.SQL_FIX_TEMPLATE_X_SCAN))

    x4 = await _x4(db_session, tid)
    assert x4["x_code"] == "x_scan_bar"
    assert float(x4["x_seconds"]) == 0.0, "fixed 模式秒數由字典提供，殘留 1.5 只會誤導"


async def test_fixed_payload_computes_under_v2_dictionary(db_session):
    """修完要真的算得出來——這才是這條 migration 的目的（原本 SequenceError X_UNKNOWN）。"""
    tid = await _insert_template(db_session, _CM_CYCLE, seq_kind="CM")
    await db_session.execute(text(MIG.SQL_FIX_TEMPLATE_X_SCAN))

    payload = (await db_session.execute(
        text("SELECT cycle_template FROM motion_templates WHERE id = :i"), {"i": tid},
    )).scalar_one()
    result = compute_cycle(cycle_in_to_engine(CycleIn.model_validate(payload)), build_from_seed_v2())
    assert result.total_tmu > 0


async def test_fix_does_not_touch_other_templates(db_session):
    """不誤傷：別的 X 碼、以及 x4 為 null 的 GM 範本都原封不動。"""
    other = dict(_CM_CYCLE, x4={"x_code": "x_press", "x_seconds": 2.0})
    other_id = await _insert_template(db_session, other, seq_kind="CM")
    gm_id = await _insert_template(db_session, _GM_CYCLE, seq_kind="GM")

    await db_session.execute(text(MIG.SQL_FIX_TEMPLATE_X_SCAN))

    x4 = await _x4(db_session, other_id)
    assert x4 == {"x_code": "x_press", "x_seconds": 2.0}
    assert await _x4(db_session, gm_id) is None, "GM 範本沒有 x4，不該被 jsonb_set 生出來"


async def test_fix_is_idempotent(db_session):
    tid = await _insert_template(db_session, _CM_CYCLE, seq_kind="CM")

    await db_session.execute(text(MIG.SQL_FIX_TEMPLATE_X_SCAN))
    first = await _x4(db_session, tid)
    second_run = await db_session.execute(text(MIG.SQL_FIX_TEMPLATE_X_SCAN))

    assert second_run.rowcount == 0, "跑過一次後應選不到列"
    assert await _x4(db_session, tid) == first


async def test_no_x_scan_left_in_real_db(db_session):
    """環境見證：真實 DB（migration 已跑 + seed 已修）裡不該再有 `x_scan` 範本。"""
    left = (await db_session.execute(text(
        "SELECT count(*) FROM motion_templates WHERE cycle_template -> 'x4' ->> 'x_code' = 'x_scan'"
    ))).scalar_one()
    assert left == 0, f"仍有 {left} 筆範本帶 V1 的 x_scan——該環境沒跑到 v2_0035"
