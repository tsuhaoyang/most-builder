"""同義詞 retired gate（ADR-024 §5 / D11-BE）。

ADR-014 明定同義詞是 published 版本唯一可後補的資料——**不受 clone-on-write 限制**。
ADR-024 §5 收斂：draft/published 可增刪同義詞，唯 retired（終態）不可。

⚠️ 本檔的核心是**互為對照的兩條**：
  - published 增刪同義詞 → 成功（證明沒把 ADR-014 特例擋掉）
  - retired 增刪同義詞 → 409 RULE_SET_RETIRED
只測 retired 失敗無法證明沒有連 published 一起擋。

所有版本皆由 V2 clone 出的拋棄式版本，never touch V1/V2（回放基準）。
"""
from __future__ import annotations

import uuid

import pytest

from ddm_v2.services.v2 import rule_set_service as rss
from ddm_v2.services.v2 import synonym_service as syn_svc

pytestmark = pytest.mark.integration

SOURCE = "MINIMOST_FACTORY_V2"  # active published；唯讀來源，不得改動


async def _throwaway(db_session, status: str) -> str:
    """clone 出拋棄式版本並帶到指定 status（draft / published / retired）。"""
    code = f"UT_SYN_{uuid.uuid4().hex[:8]}"
    await rss.clone_draft(db_session, SOURCE, code, "syn gate test")
    if status in ("published", "retired"):
        await rss.publish(db_session, code, actor="UT")
    if status == "retired":
        # retire 前置 is_active=false；cloned 版本本就非 active
        await rss.retire(db_session, code, actor="UT")
    await db_session.commit()
    return code


def _payload() -> dict:
    # parameter='A' → band-based，create_synonym 的 option_code FK 驗證依設計跳過，
    # 不必查 rule_b_options 等子表即可測 gate。synonym_raw 隨機避免 UNIQUE 撞。
    return {"parameter": "A", "option_code": "A6", "synonym_raw": f"別名{uuid.uuid4().hex[:6]}"}


def _url(code: str) -> str:
    return f"/api/v2/rule-sets/{code}/synonyms"


# ── create ──────────────────────────────────────────────────────────

async def test_create_synonym_on_draft_succeeds(client, db_session):
    code = await _throwaway(db_session, "draft")
    r = await client.post(_url(code), json=_payload())
    assert r.status_code == 201, r.text
    assert r.json()["parameter"] == "A"


async def test_create_synonym_on_published_succeeds(client, db_session):
    """ADR-014 特例：published 可後補同義詞。這條證明 gate 沒擋錯（對照組）。"""
    code = await _throwaway(db_session, "published")
    r = await client.post(_url(code), json=_payload())
    assert r.status_code == 201, r.text
    # 確認真的落庫（非空洞性）
    listed = (await client.get(_url(code))).json()
    assert any(s["id"] == r.json()["id"] for s in listed)


async def test_create_synonym_on_retired_returns_409(client, db_session):
    code = await _throwaway(db_session, "retired")
    r = await client.post(_url(code), json=_payload())
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict) and detail["code"] == "RULE_SET_RETIRED", detail
    # 被拒不得有副作用：清單仍為空
    assert (await client.get(_url(code))).json() == []


# ── delete ──────────────────────────────────────────────────────────

async def test_delete_synonym_on_retired_returns_409(client, db_session):
    """先在 published 建同義詞（成功），retire 後刪 → 409；且該同義詞未被刪除。"""
    code = await _throwaway(db_session, "published")
    created = await syn_svc.create_synonym(
        db_session, code, data=_payload(), created_by="UT"
    )
    syn_id = created["id"]
    await rss.retire(db_session, code, actor="UT")
    await db_session.commit()

    r = await client.delete(f"{_url(code)}/{syn_id}")
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert isinstance(detail, dict) and detail["code"] == "RULE_SET_RETIRED", detail
    # 被拒的刪除不得有副作用：同義詞仍在
    listed = (await client.get(_url(code))).json()
    assert any(s["id"] == syn_id for s in listed), "retired 刪除被拒後同義詞不得消失"
