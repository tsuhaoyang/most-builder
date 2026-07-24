"""工序表回應帶 default_rule_set 現況狀態（ADR-023 §3.4-4 警示徽章 / D11-BE）。

default_rule_set_id 是建立時凍結的快照；retire 不回溯改寫，但工作台須顯示徽章
「本工序表使用已下架規則版本」。本檔驗證回應帶足夠資料供徽章判斷，且**回放鐵則**
不受影響——把 default_rule_set retire 掉，工序表的 cycle 重算 TMU 仍不變。

⚠️ 徽章資料是**額外查詢**、純顯示；不進計算路徑。所有會改狀態的操作只動拋棄式版本，
never touch V1/V2。
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.worksheet import MostWorksheet
from ddm_v2.services.v2 import rule_set_service as rss

pytestmark = pytest.mark.integration

WS = "55555555-5555-5555-5555-555555555555"      # demo 工序表（default_rule_set = V2）
OBJ = "66666666-6666-6666-6666-666666666666"


def _gm_row():
    # cycle 綁 V1 快照（TMU=28）；與 default_rule_set 無關——正是要證明的分離。
    return {"id": str(uuid.uuid4()), "seq_no": 1, "hand": "RH", "object_vocab_id": OBJ,
            "frequency": 1, "narrative": "badge ut",
            "cycle": {"seq": "GM", "rule_set_code": "MINIMOST_FACTORY_V1",
                      "a0": {"reach_cm": 20}, "g2": {"g_code": "g_grasp"},
                      "a3": {"reach_cm": 25}, "p5": {"p_base_code": "p_place_none"}},
            "level": {"ascription": "main", "level": "1"}}


async def _seeded(client) -> bool:
    return (await client.get(f"/api/v2/worksheets/{WS}")).status_code == 200


async def _throwaway_published(db_session) -> tuple[str, uuid.UUID]:
    code = f"UT_BADGE_{uuid.uuid4().hex[:8]}"
    await rss.clone_draft(db_session, "MINIMOST_FACTORY_V2", code, "badge ut")
    await rss.publish(db_session, code, actor="UT")
    await db_session.commit()
    rs = (await db_session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one()
    return code, rs.id


async def test_badge_published_active_version(client, db_session):
    """工序表用 active published 版本（V2）→ 回應帶 status=='published'、is_active==true。

    明確把工序表指向 active 版本（不依賴 demo seed 當初挑了哪版），只讀 V2 不改它。
    """
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    active = (await db_session.execute(select(RuleSet).where(RuleSet.is_active.is_(True)))).scalar_one()
    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    ws_row = await db_session.get(MostWorksheet, uuid.UUID(new_ws))
    ws_row.default_rule_set_id = active.id
    await db_session.commit()

    body = (await client.get(f"/api/v2/worksheets/{new_ws}")).json()
    drs = body["default_rule_set"]
    assert drs is not None
    assert drs["code"] == active.code
    assert drs["status"] == "published"
    assert drs["is_active"] is True


async def test_badge_reflects_retire_without_changing_replay(client, db_session):
    """把工序表的 default_rule_set retire → 徽章狀態轉 retired，但 cycle TMU 不變（回放鐵則）。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    tw_code, tw_id = await _throwaway_published(db_session)

    # 拿一張隔離工序表（clone demo）並把其 default_rule_set 指向拋棄式版本
    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    ws_row = await db_session.get(MostWorksheet, uuid.UUID(new_ws))
    ws_row.default_rule_set_id = tw_id
    await db_session.commit()

    # 存一列 GM（cycle 綁 V1 → TMU=28）
    saved = await client.put(f"/api/v2/worksheets/{new_ws}", json={"rows": [_gm_row()]})
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["total_tmu"] == 28
    assert body["default_rule_set"]["code"] == tw_code
    assert body["default_rule_set"]["status"] == "published"
    assert body["default_rule_set"]["is_active"] is False

    # retire 該 default_rule_set
    await rss.retire(db_session, tw_code, actor="UT")
    await db_session.commit()

    # 重讀同一工序表：徽章轉 retired，但 TMU 回放不受影響
    rd = (await client.get(f"/api/v2/worksheets/{new_ws}")).json()
    assert rd["default_rule_set"]["status"] == "retired"
    assert rd["default_rule_set"]["code"] == tw_code
    assert rd["total_tmu"] == 28, "回放鐵則：default_rule_set retire 不得改寫 cycle TMU"
    assert rd["rows"][0]["cycle"]["total_tmu"] == 28


async def test_badge_null_default_rule_set_is_none_not_error(client, db_session):
    """default_rule_set_id 為 NULL → 該欄回 null，不報錯。"""
    if not await _seeded(client):
        pytest.skip("demo worksheet 未種（先跑 dev_seed_v2.py）")
    new_ws = (await client.post(f"/api/v2/worksheets/{WS}/clone")).json()["new_worksheet_id"]
    ws_row = await db_session.get(MostWorksheet, uuid.UUID(new_ws))
    ws_row.default_rule_set_id = None
    await db_session.commit()

    rd = await client.get(f"/api/v2/worksheets/{new_ws}")
    assert rd.status_code == 200, rd.text
    assert rd.json()["default_rule_set"] is None
