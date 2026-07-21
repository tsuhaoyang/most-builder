"""Rule-set 反向治理操作（ADR-023 D3b）：DELETE draft ／ unretire。

背景（D4 前端審查發現的兩個「有去無回」狀態）：
- clone-on-write 是 draft 產生器但沒有刪除端點 → draft 只會累積
  （本 repo 已清過一次 268 筆測試殘留版本）。
- `retired` 原本是終態（只有 publish/activate/retire），誤按封存後無 UI 可救。

⚠️ 所有會改狀態的操作一律走 `throwaway_rule_set` 建的拋棄式版本，**不得**對
V1/V2 動手（它們是回放基準版本，見 test_rule_set_replay_isolation.py）。
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.services.v2 import rule_set_service as svc

pytestmark = pytest.mark.integration

CODE = "MINIMOST_FACTORY_V2"  # active 版本（唯讀來源，不得被本檔改動）


@pytest_asyncio.fixture
async def draft(db_session) -> str:
    """clone 出一個拋棄式 draft（provenance='cloned'，非 active）。"""
    code = f"UT_DEL_{uuid.uuid4().hex[:8]}"
    await svc.clone_draft(db_session, CODE, code, "D3b 拋棄式草稿")
    await db_session.commit()
    return code


async def _row(db_session, code: str) -> RuleSet:
    rs = (await db_session.execute(select(RuleSet).where(RuleSet.code == code))).scalar_one()
    await db_session.refresh(rs)
    return rs


async def _detail(resp) -> dict:
    body = resp.json()["detail"]
    assert isinstance(body, dict), f"錯誤形狀應為 {{code, message}}，收到 {body!r}"
    return body


# ══════════════════════════════════════════════════════════════════
# DELETE /rule-sets/{code}
# ══════════════════════════════════════════════════════════════════


async def test_delete_draft_happy_path_cascades_children(client, db_session, draft):
    """draft 刪除成功，且 13 張級聯子表的列數歸零。

    只查 `rule_sets` 不夠：CASCADE 若沒生效（或未來有人把 FK 改成 SET NULL），
    表頭會消失但子表留下孤兒列，而那正是「殘留」的樣子。
    """
    rs_id = (await _row(db_session, draft)).id
    before = await svc.count_children(db_session, rs_id)
    assert before["rule_a_bands"] > 0, "拋棄式草稿應已 clone 出子表，否則本測試驗不到 CASCADE"

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    assert r.json()["children_deleted"]["rule_a_bands"] == before["rule_a_bands"]

    assert (await db_session.execute(
        select(RuleSet).where(RuleSet.code == draft))).scalar_one_or_none() is None

    after = await svc.count_children(db_session, rs_id)
    for table, n in after.items():
        assert n == 0, f"子表 {table} 仍有 {n} 列孤兒（CASCADE 未生效）"


async def test_delete_writes_audit_log_that_survives_the_entity(client, db_session, draft):
    """稽核先寫、實體後刪；`workflow_audit_log` 無 FK 且 append-only，log 必須留存。

    （v2_0017 建表時明文「無 FK 強制，允許實體刪除後 log 留存」；v2_0018 加了
    禁 UPDATE/DELETE 的 trigger。所以不需要、也不允許用刪 audit 來繞開 FK。）
    """
    rs_id = (await _row(db_session, draft)).id
    assert (await client.delete(f"/api/v2/rule-sets/{draft}")).status_code == 200

    rows = (await db_session.execute(text(
        "SELECT action, from_status, to_status, payload FROM workflow_audit_log "
        "WHERE entity_type='rule_set' AND entity_id=:i AND action='delete'"
    ), {"i": rs_id})).all()
    assert len(rows) == 1, "刪除必須留下恰好一筆 action='delete' 稽核"
    action, from_status, to_status, payload = rows[0]
    assert (from_status, to_status) == ("draft", None)
    assert payload["code"] == draft
    assert payload["children_deleted"]["rule_a_bands"] > 0, "實體沒了之後，log 要說得清刪掉的是什麼"


async def test_delete_published_returns_409_not_draft(client, db_session, draft):
    await svc.publish(db_session, draft, actor="UT_D3B")
    await db_session.commit()

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 409, r.text
    # 只斷言 409 會空洞通過：本端點有五種 409，狀態碼分不出是哪一種守門擋下的。
    assert (await _detail(r))["code"] == "RULE_SET_NOT_DRAFT"
    assert (await _row(db_session, draft)).status == "published", "被拒的刪除不得有副作用"


async def test_delete_retired_returns_409_not_draft(client, db_session, draft):
    await svc.publish(db_session, draft, actor="UT_D3B")
    await svc.retire(db_session, draft, actor="UT_D3B")
    await db_session.commit()

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 409, r.text
    assert (await _detail(r))["code"] == "RULE_SET_NOT_DRAFT"
    assert (await _row(db_session, draft)).status == "retired"


async def test_delete_certified_import_returns_409_even_when_draft(client, db_session, draft):
    """認證匯入版本即使 status='draft' 也不可刪（ADR-014 / §3.3 規則 3）。

    理論上認證版不會是 draft——所以這個 gate 必須**顯式**擋，不能靠「反正它是 published」
    的推論；本測試就是把那個推論拿掉之後的情況。
    """
    rs = await _row(db_session, draft)
    rs.provenance = "certified_import"
    await db_session.commit()

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 409, r.text
    assert (await _detail(r))["code"] == "CERTIFIED_IMMUTABLE"
    assert (await _row(db_session, draft)).code == draft, "被拒的刪除不得有副作用"


async def test_delete_active_returns_409(client, db_session, draft):
    """is_active=true 不可刪（防呆；draft 理論上不會 active，同樣顯式擋）。

    partial unique index 只允許一個 active，故先把現行 active 降下來再抬這個 draft。
    """
    await db_session.execute(text("UPDATE rule_sets SET is_active=false WHERE is_active"))
    rs = await _row(db_session, draft)
    rs.is_active = True
    await db_session.commit()

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 409, r.text
    assert (await _detail(r))["code"] == "RULE_SET_ACTIVE"
    assert (await _row(db_session, draft)).is_active is True


async def test_delete_referenced_draft_returns_409_with_reference_count(client, db_session, draft):
    """★ 回放鐵則（ADR-023 §3.4）：被 cycle 引用的 draft 不可刪。

    `load_rule_set_from_db` 依鐵則不做治理狀態過濾——它不會「跳過」被刪的版本，
    只會找不到列。所以刪掉一個被引用的版本＝那些歷史 cycle 永久失去規則版本。
    DB 的 RESTRICT FK 是最後防線，但那會變成 IntegrityError 500；服務層必須先擋，
    回 409＋引用數，讓使用者知道「有幾筆擋著」。
    """
    rs_id = (await _row(db_session, draft)).id
    cycle_id = (await db_session.execute(text("SELECT id FROM most_cycles LIMIT 1"))).scalar_one()
    await db_session.execute(
        text("UPDATE most_cycles SET rule_set_id=:rs WHERE id=:i"), {"rs": rs_id, "i": cycle_id})
    await db_session.commit()

    r = await client.delete(f"/api/v2/rule-sets/{draft}")
    assert r.status_code == 409, r.text
    detail = await _detail(r)
    assert detail["code"] == "RULE_SET_IN_USE"
    assert detail["references"]["most_cycles"] == 1, "409 必須指出引用數，否則使用者不知道卡在哪"

    assert (await db_session.execute(
        select(RuleSet).where(RuleSet.code == draft))).scalar_one_or_none() is not None
    assert (await svc.count_children(db_session, rs_id))["rule_a_bands"] > 0, \
        "被拒的刪除不得留下半套（子表被清、表頭還在）"


async def test_count_references_covers_every_restrict_referrer(db_session, draft):
    """三條 RESTRICT FK 都要被數到——漏一條就是一條 500 的路。

    以 DB 的 pg_catalog 為準對照模組常數（model 與 migration 兩邊之外的第三方見證），
    這樣未來新增第四張引用表時，這個測試會先變紅。
    """
    rs_id = (await _row(db_session, draft)).id
    actual = set((await svc.count_references(db_session, rs_id)).keys())
    expected = {row[0] for row in (await db_session.execute(text("""
        SELECT c.conrelid::regclass::text FROM pg_constraint c
        JOIN pg_class p ON p.oid = c.confrelid
        WHERE p.relname = 'rule_sets' AND c.contype = 'f' AND c.confdeltype = 'r'
    """))).all()}
    assert actual == expected, f"引用方清單與 DB 的 RESTRICT FK 不一致：{actual} vs {expected}"


async def test_delete_missing_rule_set_returns_404(client):
    r = await client.delete("/api/v2/rule-sets/UT_NO_SUCH_RULE_SET")
    assert r.status_code == 404, r.text


async def test_delete_analyst_returns_403(client, db_session, draft):
    """RBAC：delete 與 retire/publish 同級（approver）；analyst → 403 且無副作用。"""
    analyst = "GAPTEST_ANALYST_RS_DEL"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst, "display_name": "D3b Analyst Delete",
        "roles": ["analyst"], "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    r = await client.delete(f"/api/v2/rule-sets/{draft}", headers={"X-Username": analyst})
    assert r.status_code == 403, r.text
    assert (await db_session.execute(
        select(RuleSet).where(RuleSet.code == draft))).scalar_one_or_none() is not None


# ══════════════════════════════════════════════════════════════════
# POST /rule-sets/{code}/unretire
# ══════════════════════════════════════════════════════════════════


async def test_unretire_returns_to_published_without_activating(client, db_session, draft):
    """retired → published，且 `is_active` **仍為 False**。

    解除封存不等於啟用：要啟用得另外走 `/activate`（那條才有 validate_complete
    ＋單一 active 的把關）。若這裡順手啟用，等於繞過發布把關直接換掉全系統的計算依據。
    """
    await svc.publish(db_session, draft, actor="UT_D3B")
    await svc.retire(db_session, draft, actor="UT_D3B")
    await db_session.commit()
    active_before = (await db_session.execute(
        select(RuleSet.code).where(RuleSet.is_active.is_(True)))).scalars().all()

    r = await client.post(f"/api/v2/rule-sets/{draft}/unretire")
    assert r.status_code == 200, r.text
    assert r.json() == {"code": draft, "status": "published", "is_active": False}

    rs = await _row(db_session, draft)
    assert rs.status == "published"
    assert rs.is_active is False, "解除封存不得順便啟用"
    active_after = (await db_session.execute(
        select(RuleSet.code).where(RuleSet.is_active.is_(True)))).scalars().all()
    assert active_after == active_before, "解除封存不得改動全系統的 active 版本"


async def test_unretire_writes_audit(client, db_session, draft):
    await svc.publish(db_session, draft, actor="UT_D3B")
    await svc.retire(db_session, draft, actor="UT_D3B")
    await db_session.commit()
    rs_id = (await _row(db_session, draft)).id

    assert (await client.post(f"/api/v2/rule-sets/{draft}/unretire")).status_code == 200
    rows = (await db_session.execute(text(
        "SELECT from_status, to_status FROM workflow_audit_log "
        "WHERE entity_type='rule_set' AND entity_id=:i AND action='unretire'"
    ), {"i": rs_id})).all()
    assert rows == [("retired", "published")]


async def test_unretire_draft_returns_409(client, db_session, draft):
    r = await client.post(f"/api/v2/rule-sets/{draft}/unretire")
    assert r.status_code == 409, r.text
    assert (await _detail(r))["code"] == "RULE_SET_NOT_RETIRED"
    assert (await _row(db_session, draft)).status == "draft", "被拒的解除封存不得有副作用"


async def test_unretire_published_returns_409(client, db_session, draft):
    await svc.publish(db_session, draft, actor="UT_D3B")
    await db_session.commit()

    r = await client.post(f"/api/v2/rule-sets/{draft}/unretire")
    assert r.status_code == 409, r.text
    assert (await _detail(r))["code"] == "RULE_SET_NOT_RETIRED"


async def test_unretire_missing_rule_set_returns_404(client):
    r = await client.post("/api/v2/rule-sets/UT_NO_SUCH_RULE_SET/unretire")
    assert r.status_code == 404, r.text


async def test_unretire_analyst_returns_403(client, db_session, draft):
    """RBAC：unretire 與 retire 同級（approver）；analyst → 403 且狀態不變。"""
    await svc.publish(db_session, draft, actor="UT_D3B")
    await svc.retire(db_session, draft, actor="UT_D3B")
    await db_session.commit()

    analyst = "GAPTEST_ANALYST_RS_UNRET"
    ur = await client.post("/api/v2/admin/users", json={
        "employee_no": analyst, "display_name": "D3b Analyst Unretire",
        "roles": ["analyst"], "site_ids": [],
    })
    assert ur.status_code == 200, ur.text

    r = await client.post(f"/api/v2/rule-sets/{draft}/unretire", headers={"X-Username": analyst})
    assert r.status_code == 403, r.text
    assert (await _row(db_session, draft)).status == "retired", "403 後不得留下任何解除封存副作用"


async def test_retired_rule_set_still_loadable_after_unretire_cycle(db_session, draft):
    """回放鐵則：retire → unretire 全程 `load_rule_set_from_db` 都載得到。

    治理狀態只在「選擇」時生效；載入路徑永不過濾（§3.4）。
    """
    from ddm_v2.most_engine.providers import load_rule_set_from_db

    await svc.publish(db_session, draft, actor="UT_D3B")
    await db_session.commit()
    assert (await load_rule_set_from_db(db_session, draft)) is not None

    await svc.retire(db_session, draft, actor="UT_D3B")
    await db_session.commit()
    assert (await load_rule_set_from_db(db_session, draft)) is not None, "retired 版本仍須可回放"

    await svc.unretire(db_session, draft, actor="UT_D3B")
    await db_session.commit()
    assert (await load_rule_set_from_db(db_session, draft)) is not None
