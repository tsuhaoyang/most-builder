"""nl-draft 的 planner 出處與舊 LLM run 重播（integration）。

ADR-037（2026-11-14）：MOST 內的 LLM planner 已移除，nl-draft 一律走 rule_based
（`fallback=True`、`fallback_rule_based`）。但 `ai_parse_runs` 裡已有 planner＝llm 的
舊資料列，快取重播必須照原樣回報它們當初的 planner／model／prompt_version——
本檔把那些舊列的形狀**直接寫進 DB** 來釘住重播（ADR-037 D1：舊列必須仍可讀取與重播）。
"""
from __future__ import annotations

import os
import uuid

import pytest

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration

# ADR-037 前寫入端用的版本字串之一；這裡只當「舊列裡存著的值」，不再有對應的模組常數。
_LEGACY_PROMPT_VERSION = "plan-v2.0"
_LEGACY_MODEL = "fake-model-x"


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def _nl_draft(client, text: str) -> dict:
    code = await _get_rs_code(client)
    r = await client.post("/api/v2/worksheets/nl-draft", json={"text": text, "rule_set_code": code})
    assert r.status_code == 200, r.text
    return r.json()


async def _rewrite_run_as_legacy_llm(db_session, text: str, *, with_prompt_version: bool) -> None:
    """把剛寫下的 rule run 改成 ADR-037 前 LLM run 的形狀（同一筆、同一 input_hash）。"""
    from sqlalchemy import select

    from ddm_v2.models.v2.ai_ops import AiParseRun

    row = (
        await db_session.execute(select(AiParseRun).where(AiParseRun.raw_text == text))
    ).scalar_one()
    raw: dict = {
        "content": "{}",
        "model": _LEGACY_MODEL,
        "usage": {},
        "response_format_mode": "json_object",
    }
    if with_prompt_version:
        raw["prompt_version"] = _LEGACY_PROMPT_VERSION
    row.llm_raw_response = raw  # 指派新 dict 才會被 ORM 視為 dirty（JSONB 非 Mutable）
    row.fallback = False
    await db_session.commit()


async def test_nl_draft_uses_rule_planner(client):
    """ADR-037：planner 一律 rule_based_v1、fallback=true、帶 fallback_rule_based。"""
    data = await _nl_draft(client, f"治具fallback{uuid.uuid4().hex[:6]}")
    ai = data["ai"]
    assert ai["provenance"]["fallback"] is True
    assert ai["provenance"]["planner"] == "rule_based_v1"
    assert ai["provenance"]["model"] is None
    assert ai["provenance"]["prompt_version"] is None
    assert "fallback_rule_based" in ai["routing_reasons"]


async def test_stale_legacy_llm_env_has_no_effect(client, monkeypatch):
    """舊環境殘留 DDM_WI_AI_ENABLED=1 與 DDM_LLM_* 時，不得重新啟用任何 LLM 呼叫。

    ADR-037 D2：新開關另名 DDM_AI_SERVICE_ENABLED，就是為了讓舊值 `true` 不會在新路徑完成前
    意外打開功能。單看 planner＝rule 證明不了「沒有發 HTTP」（失敗時本來也會 fallback），
    所以另外斷言設定物件上已沒有那些欄位。
    """
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    monkeypatch.setenv("DDM_LLM_BASE_URL", "http://127.0.0.1:1")
    get_settings.cache_clear()
    try:
        s = get_settings()
        for gone in ("wi_ai_enabled", "llm_base_url", "llm_api_key", "llm_model", "llm_timeout_s"):
            assert not hasattr(s, gone), f"settings 仍有 {gone}——舊 LLM 設定沒有移乾淨"
        data = await _nl_draft(client, f"治具舊設定{uuid.uuid4().hex[:6]}")
        assert data["ai"]["provenance"]["planner"] == "rule_based_v1"
    finally:
        get_settings.cache_clear()


async def test_legacy_provenance_reports_rule_parser(client):
    """頂層 legacy `provenance.parser` 也必須是 rule_based_v1（不得謊報）。"""
    prov = (await _nl_draft(client, f"治具legacyprov{uuid.uuid4().hex[:6]}"))["provenance"]
    assert prov["parser"] == "rule_based_v1"
    assert prov["model"] is None
    assert prov["prompt_version"] is None
    assert prov["fallback"] is True
    # fresh 路徑：這批 slots 直接來自 RuleBasedParser，與 planner 無關。
    assert prov["slots_parser"] == "rule_based_v1"


async def test_cached_replay_of_a_legacy_llm_run_reports_its_own_provenance(client, db_session):
    """舊 LLM run 重播：planner／model／prompt_version 照**當初那一趟**回報。

    `slots_parser` 是分路徑的事實：重播走 `legacy_from_run_snapshot`，legacy slots 是從 run
    存下來的 `slot_candidates` 還原的，對 planner＝llm 的舊列必須說 `slot_linker:llm`，
    不得照抄 `rule_based_v1`。版本讀的是 run 自己存的值，不是任何模組常數。
    """
    text = f"拿起治具{uuid.uuid4().hex[:6]}"
    await _nl_draft(client, text)
    await _rewrite_run_as_legacy_llm(db_session, text, with_prompt_version=True)

    data2 = await _nl_draft(client, text)
    assert data2["ai"]["provenance"]["cached"] is True, "沒命中快取，這條測不到重播路徑"
    assert data2["ai"]["provenance"]["planner"] == "llm"
    assert data2["ai"]["provenance"]["fallback"] is False
    assert data2["ai"]["provenance"]["model"] == _LEGACY_MODEL
    assert data2["ai"]["provenance"]["prompt_version"] == _LEGACY_PROMPT_VERSION
    prov2 = data2["provenance"]
    assert prov2["from_cached_run"] is True
    assert prov2["parser"] == "llm", "快取重播把舊 LLM run 說成 rule_based_v1"
    assert prov2["model"] == _LEGACY_MODEL
    assert prov2["prompt_version"] == _LEGACY_PROMPT_VERSION
    assert prov2["slots_parser"] == "slot_linker:llm", (
        "重播的 slots 是 LLM plan 經 SlotLinker 得到的，說 rule_based_v1 即謊報來源"
    )


async def test_cached_replay_of_a_legacy_row_without_prompt_version_reports_none(
    client, db_session
):
    """更早的舊 LLM run（`llm_raw_response` 沒有 `prompt_version` 鍵）重播時回 `None`。

    誠實的「不知道」勝過自信的錯答：不得回退成任何常數。
    """
    text = f"拿起舊資料治具{uuid.uuid4().hex[:6]}"
    await _nl_draft(client, text)
    await _rewrite_run_as_legacy_llm(db_session, text, with_prompt_version=False)

    data2 = await _nl_draft(client, text)
    assert data2["ai"]["provenance"]["cached"] is True, "沒命中快取，這條測不到重播路徑"
    assert data2["ai"]["provenance"]["prompt_version"] is None
    assert data2["provenance"]["prompt_version"] is None
    # 其餘 provenance 不受影響（只有版本是未知的）
    assert data2["provenance"]["parser"] == "llm"
    assert data2["provenance"]["model"] == _LEGACY_MODEL


async def test_settings_cache_not_leaked_by_preceding_tests():
    """跑完上面 monkeypatch env 的測試後，`get_settings()` 不得留下過期物件。

    `get_settings` 是 `lru_cache(maxsize=1)`：monkeypatch 還原 env 不會作廢已建好的
    `Settings`。比對「現在快取住的」與「用當下 env 重建的」：不相等就代表有測試漏了
    cache_clear。本測試放在檔尾，覆蓋範圍是同檔在它之前執行的測試。
    """
    from ddm_v2.settings import get_settings

    inherited = get_settings()
    get_settings.cache_clear()
    from_env = get_settings()
    assert inherited == from_env, (
        f"get_settings 快取洩漏：cached={inherited} != env={from_env}"
    )
