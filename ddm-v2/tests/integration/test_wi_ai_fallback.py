"""L1 orchestrator fallback：LLM 關／失敗時走 rule（integration）。"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def test_nl_draft_fallback_when_llm_disabled(client, monkeypatch):
    """wi_ai_enabled=false → planner=rule_based_v1、fallback=true。"""
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "0")
    get_settings.cache_clear()

    code = await _get_rs_code(client)
    r = await client.post(
        "/api/v2/worksheets/nl-draft",
        json={"text": f"治具fallback{uuid.uuid4().hex[:6]}", "rule_set_code": code},
    )
    assert r.status_code == 200, r.text
    ai = r.json()["ai"]
    assert ai["provenance"]["fallback"] is True
    assert ai["provenance"]["planner"] == "rule_based_v1"


async def test_nl_draft_fallback_when_llm_unreachable(client, monkeypatch):
    """wi_ai_enabled=1 但 base_url 不可達 → 仍 200 + rule fallback。"""
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    monkeypatch.setenv("DDM_LLM_BASE_URL", "http://127.0.0.1:1")  # 必定拒絕連線
    monkeypatch.setenv("DDM_LLM_TIMEOUT_S", "0.5")
    get_settings.cache_clear()

    code = await _get_rs_code(client)
    r = await client.post(
        "/api/v2/worksheets/nl-draft",
        json={"text": f"治具連線失敗{uuid.uuid4().hex[:6]}", "rule_set_code": code},
    )
    assert r.status_code == 200, r.text
    ai = r.json()["ai"]
    assert ai["provenance"]["fallback"] is True
    assert "fallback_rule_based" in ai["routing_reasons"]
    assert ai["provenance"]["planner"] == "rule_based_v1"
