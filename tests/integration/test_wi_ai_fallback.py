"""L1 orchestrator fallback：LLM 關／失敗時走 rule（integration）。"""
from __future__ import annotations

import os
import uuid

import pytest

from ddm_v2.nlp.prompts import plan_v1

if not os.getenv("DATABASE_URL"):
    pytest.skip("需要 DATABASE_URL", allow_module_level=True)

pytestmark = pytest.mark.integration


async def _get_rs_code(client) -> str:
    r = await client.get("/api/v2/rule-sets")
    if r.status_code != 200 or not r.json():
        pytest.skip("DB 無 rule_set，略過")
    return r.json()[0]["code"]


async def _fake_llm(*, normalized_text, context, timeout_s):
    """假 planner：固定回單一 acquire action，不打網路。

    本檔所有「LLM 真的跑了」的測試共用這一支——真的連 LLM 會讓斷言變成
    非決定性的（模型輸出隨版本漂移），而這裡要驗的是 provenance 佈線，不是模型品質。
    """
    from ddm_v2.nlp.contracts import PlannedAction, PlannerOutput
    from ddm_v2.nlp.planner_ports import LLMRawResponse

    out = PlannerOutput(
        language="zh",
        actions=[
            PlannedAction(
                action_id="a1",
                action_type="acquire",
                sequence_order=1,
                roles={},
                evidence=[{"start": 0, "end": len(normalized_text), "text": normalized_text}],
            )
        ],
    )
    raw = LLMRawResponse(
        content="{}",
        model="fake-model-x",
        usage={},
        latency_ms=1.0,
        response_format_mode="json_object",
    )
    return out, raw


async def test_nl_draft_fallback_when_llm_disabled(client, monkeypatch):
    """wi_ai_enabled=false → planner=rule_based_v1、fallback=true。"""
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "0")
    get_settings.cache_clear()
    try:
        code = await _get_rs_code(client)
        r = await client.post(
            "/api/v2/worksheets/nl-draft",
            json={"text": f"治具fallback{uuid.uuid4().hex[:6]}", "rule_set_code": code},
        )
        assert r.status_code == 200, r.text
        ai = r.json()["ai"]
        assert ai["provenance"]["fallback"] is True
        assert ai["provenance"]["planner"] == "rule_based_v1"
    finally:
        # monkeypatch 還得了 env，還不了已建好的 Settings 物件（lru_cache(maxsize=1)）。
        get_settings.cache_clear()


async def test_nl_draft_fallback_when_llm_unreachable(client, monkeypatch):
    """wi_ai_enabled=1 但 base_url 不可達 → 仍 200 + rule fallback。"""
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    monkeypatch.setenv("DDM_LLM_BASE_URL", "http://127.0.0.1:1")  # 必定拒絕連線
    monkeypatch.setenv("DDM_LLM_TIMEOUT_S", "0.5")
    get_settings.cache_clear()
    try:
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
    finally:
        # 不清會把 wi_ai_enabled=True 連同「不可達 base_url」一起漏給後續測試——
        # 那個組合看起來無害，直到某支測試改了 base_url 而這裡的 True 還在。
        get_settings.cache_clear()


async def test_legacy_provenance_reports_rule_parser_when_llm_disabled(client, monkeypatch):
    """LLM 關 → 頂層 legacy `provenance.parser` 也必須是 rule_based_v1（邊界對照組）。"""
    from ddm_v2.settings import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "0")
    get_settings.cache_clear()
    try:
        code = await _get_rs_code(client)
        r = await client.post(
            "/api/v2/worksheets/nl-draft",
            json={"text": f"治具legacyprov{uuid.uuid4().hex[:6]}", "rule_set_code": code},
        )
        assert r.status_code == 200, r.text
        prov = r.json()["provenance"]
        assert prov["parser"] == "rule_based_v1"
        assert prov["model"] is None
        assert prov["prompt_version"] is None
        assert prov["fallback"] is True
        # fresh 路徑：這批 slots 直接來自 RuleBasedParser，與 planner 無關。
        assert prov["slots_parser"] == "rule_based_v1"
    finally:
        get_settings.cache_clear()


async def test_legacy_provenance_reports_llm_when_llm_used(client, monkeypatch):
    """LLM 真的跑了 → 頂層 `provenance.parser` 必須是 llm（不得永遠說 rule_based_v1）。

    這個欄位原本寫死，實機驗證時兩度讓人誤判「LLM 沒被呼叫」。

    `slots_parser` 是**分路徑**的事實，不是常數：
    - fresh（本測試第一次呼叫）：legacy slots 取自 `rule_result.slots`
      → `rule_based_v1`。
    - 快取重播（第二次呼叫走 `legacy_from_run_snapshot`）：legacy slots 是從
      run 存下來的 `slot_candidates` 還原的，那批東西出自 `SlotLinker.link(LLM plan)`
      → `slot_linker:llm`。這裡**不能**是 `rule_based_v1`：同一輸入的第二次回應
      若照抄常數，就等於對「LLM plan 衍生的 slots」謊稱是 rule parser 產的。
    """
    from ddm_v2.services.v2 import wi_ai_service
    from ddm_v2.settings import get_settings

    text = f"拿起治具{uuid.uuid4().hex[:6]}"

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(wi_ai_service, "_try_llm_plan", _fake_llm)
    try:
        from ddm_v2.nlp.normalization import normalize

        code = await _get_rs_code(client)
        body = {"text": text, "rule_set_code": code}
        r = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ai"]["provenance"]["planner"] == "llm"
        assert data["ai"]["provenance"]["fallback"] is False

        prov = data["provenance"]
        assert prov["parser"] == "llm", "legacy provenance 仍謊報 planner"
        assert prov["model"] == "fake-model-x"
        assert prov["prompt_version"] == plan_v1.PROMPT_VERSION
        assert prov["fallback"] is False
        assert prov["slots_parser"] == "rule_based_v1"
        # legacy slots 本身仍是 rule parser 的產物（欄位語意沒被偷換）
        assert normalize(text) == data["normalized_text"]

        # 快取重播：第二次同輸入 → legacy_from_run_snapshot 路徑
        r2 = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["ai"]["provenance"]["cached"] is True
        prov2 = data2["provenance"]
        assert prov2["from_cached_run"] is True
        assert prov2["parser"] == "llm", "快取重播把 planner 說回 rule_based_v1"
        assert prov2["model"] == "fake-model-x"
        assert prov2["prompt_version"] == plan_v1.PROMPT_VERSION
        assert prov2["fallback"] is False
        assert prov2["slots_parser"] == "slot_linker:llm", (
            "重播的 slots 是 LLM plan 經 SlotLinker 得到的，說 rule_based_v1 即謊報來源"
        )
    finally:
        get_settings.cache_clear()


async def test_cached_replay_reports_prompt_version_of_the_run_not_current_constant(
    client, monkeypatch
):
    """快取重播的 `prompt_version` 必須是**當初那一趟**的版本，不是當下的模組常數。

    `ai_parse_runs` 沒有 prompt_version 欄（有那欄的是 `ai_deployment_bundles`），
    重播時若讀 `plan_v1.PROMPT_VERSION`，常數一升版（plan-v1 → plan-v1.3）
    DB 裡既有的每一筆 LLM run 都會改口說自己是新版本——一次提交污染全部歷史。
    版本改存進既有的 `llm_raw_response` JSONB（與 model／usage 同一類呼叫中繼資料）。
    """
    from ddm_v2.services.v2 import wi_ai_service
    from ddm_v2.settings import get_settings

    text = f"拿起版本治具{uuid.uuid4().hex[:6]}"
    version_at_write = plan_v1.PROMPT_VERSION

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(wi_ai_service, "_try_llm_plan", _fake_llm)
    try:
        code = await _get_rs_code(client)
        body = {"text": text, "rule_set_code": code}
        r = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["ai"]["provenance"]["prompt_version"] == version_at_write

        # 模擬「之後有人升版 prompt」——輸入沒變，所以 input_hash 不變、仍命中同一筆 run。
        monkeypatch.setattr(plan_v1, "PROMPT_VERSION", "plan-vNEXT-NEVER-RAN")

        r2 = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["ai"]["provenance"]["cached"] is True, "沒命中快取，這條測不到重播路徑"
        assert data2["ai"]["provenance"]["prompt_version"] == version_at_write, (
            "重播報了當下的模組常數，等於讓既有 run 謊報版本"
        )
        assert data2["provenance"]["prompt_version"] == version_at_write
    finally:
        get_settings.cache_clear()


async def test_cached_replay_of_a_legacy_row_without_prompt_version_reports_none(
    client, db_session, monkeypatch
):
    """本次改動**之前**寫下的 run（`llm_raw_response` 沒有 `prompt_version` 鍵）
    重播時必須回 `None`，不得回退成當下的模組常數。

    這是 P1-2 真正的受害者：DB 裡既有的每一筆 LLM run 都長這樣。上一條測的是
    「有存版本的 run 不被新常數蓋掉」，這條測的是「沒存版本的舊 run 不被新常數冒充」。
    誠實的「不知道」勝過自信的錯答——回退成常數就是把 plan-v1.3 的標籤貼到
    從沒跑過 plan-v1.3 的歷史資料上。
    """
    from sqlalchemy import select

    from ddm_v2.models.v2.ai_ops import AiParseRun
    from ddm_v2.services.v2 import wi_ai_service
    from ddm_v2.settings import get_settings

    text = f"拿起舊資料治具{uuid.uuid4().hex[:6]}"

    get_settings.cache_clear()
    monkeypatch.setenv("DDM_WI_AI_ENABLED", "1")
    get_settings.cache_clear()
    monkeypatch.setattr(wi_ai_service, "_try_llm_plan", _fake_llm)
    try:
        code = await _get_rs_code(client)
        body = {"text": text, "rule_set_code": code}
        r = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["ai"]["provenance"]["fallback"] is False

        # 把這筆 run 降級成「改動前的形狀」：抽掉 prompt_version 鍵（其餘照舊）。
        # 直接改 DB 而不是造假 run，才能保證形狀與既有資料列一致。
        row = (
            await db_session.execute(select(AiParseRun).where(AiParseRun.raw_text == text))
        ).scalar_one()
        raw = dict(row.llm_raw_response or {})
        assert raw.pop("prompt_version", None) is not None, "寫入端沒存版本，這條測不到重播"
        row.llm_raw_response = raw  # 指派新 dict 才會被 ORM 視為 dirty（JSONB 非 Mutable）
        await db_session.commit()

        r2 = await client.post("/api/v2/worksheets/nl-draft", json=body)
        assert r2.status_code == 200, r2.text
        data2 = r2.json()
        assert data2["ai"]["provenance"]["cached"] is True, "沒命中快取，這條測不到重播路徑"
        assert data2["ai"]["provenance"]["prompt_version"] is None, (
            "舊資料列被當下的模組常數冒充了版本"
        )
        assert data2["provenance"]["prompt_version"] is None
        # 其餘 provenance 不受影響（只有版本是未知的）
        assert data2["provenance"]["parser"] == "llm"
        assert data2["provenance"]["model"] == "fake-model-x"
    finally:
        get_settings.cache_clear()


async def test_settings_cache_not_leaked_by_preceding_tests():
    """跑完上面那些 monkeypatch env 的測試後，`get_settings()` 不得留下過期物件。

    `get_settings` 是 `lru_cache(maxsize=1)`：monkeypatch 還原 env 不會作廢已建好的
    `Settings`。曾經因此在後續測試裡留下 `wi_ai_enabled=True` ＋預設
    `llm_base_url`（本機 ollama），而 `_try_llm_plan` 已還原成真的那支
    → 後續測試**真的發出 HTTP**，測試結果被外部服務左右。

    比對「現在快取住的」與「用當下 env 重建的」：不相等就代表有測試漏了 cache_clear。
    本測試放在檔尾，覆蓋範圍是同檔在它之前執行的測試。
    """
    from ddm_v2.settings import get_settings

    inherited = get_settings()
    get_settings.cache_clear()
    from_env = get_settings()
    assert inherited == from_env, (
        f"get_settings 快取洩漏：cached={inherited} != env={from_env}"
    )
