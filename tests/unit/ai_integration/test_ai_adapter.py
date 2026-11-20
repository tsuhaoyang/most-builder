"""ai_integration.adapter／fake：`WiParserPort` 的降級語意與外送範圍（ADR-037 D2／D6／D7）。"""
from __future__ import annotations

import httpx
import pytest
from fakes.ai_service_app import FakeAiService, Reply, error_body

from ddm_v2.ai_integration.adapter import AiServiceWiParser, DisabledWiParser, build_wi_parser
from ddm_v2.ai_integration.client import AiServiceClient
from ddm_v2.ai_integration.config import MIN_KEY_LENGTH, load_config
from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.fake import FakeWiParser
from ddm_v2.ai_integration.ports import WiParseRequest
from ddm_v2.ai_integration.schema import wi_motion_parse_schema
from ddm_v2.most_compiler.compile import allow_lists_from_rule_set
from ddm_v2.most_engine.providers import build_from_seed_v2
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS

pytestmark = pytest.mark.unit

ALLOW = allow_lists_from_rule_set(build_from_seed_v2())
HOST = "ai-service.internal"
ENV = {
    "DDM_AI_SERVICE_ENABLED": "1",
    "DDM_AI_SERVICE_BASE_URL": f"https://{HOST}",
    "DDM_AI_SERVICE_ALLOWED_HOSTS": HOST,
    "DDM_AI_SERVICE_KEY": "k" * MIN_KEY_LENGTH,
    "DDM_AI_SERVICE_MAX_RETRIES": "0",
}


def _private(h: str, p: int) -> list[str]:  # noqa: ARG001
    return ["10.0.0.9"]


def _parser(fake: FakeAiService) -> AiServiceWiParser:
    async def no_sleep(_s: float) -> None:
        return None

    client = AiServiceClient(
        load_config(ENV), transport=httpx.ASGITransport(app=fake.app()), resolver=_private, sleep=no_sleep
    )
    return AiServiceWiParser(client)


def _req(item_id: str = "r1", text: str = "從料架上拿取假DIMM，去除其包裝袋", lang: str = "zh") -> WiParseRequest:
    return WiParseRequest(item_id=item_id, wi_statement=text, source_lang=lang)


async def test_ok_result_carries_motions_and_redacted_provenance():
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    (res,) = await _parser(fake).parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.status == "ok" and len(res.motions) == 2
    assert res.provenance is not None
    assert res.provenance["run_id"] == "run-golden-0"
    assert res.provenance["request_id"]
    body = fake.received[0]["body"]
    assert body["prompt_variant"] == "zh"
    assert body["json_schema"] == wi_motion_parse_schema(), "送出的必須是 MOST 端的 schema 複本"


async def test_only_the_statement_language_and_empty_context_are_sent():
    """ADR-037 D7：外送只含 WI 語句；首輪 context 白名單為空。"""
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    await _parser(fake).parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert fake.received[0]["body"]["variables"] == {
        "wi_statement": "從料架上拿取假DIMM，去除其包裝袋",
        "source_lang": "zh",
        "context": {},
    }


async def test_context_outside_the_whitelist_is_a_programming_error():
    req = WiParseRequest(item_id="r1", wi_statement="x", source_lang="zh", context={"available_tools": "起子"})
    with pytest.raises(ValueError):
        await _parser(FakeAiService()).parse([req], allow_lists=ALLOW, lane="interactive")


async def test_failures_degrade_per_item_and_never_raise():
    fake = FakeAiService(script=["ok:fewshot-zh-0", Reply(422, error_body("SCHEMA_VALIDATION_FAILED")), "ok:fewshot-en-3"])
    results = await _parser(fake).parse(
        [_req("a"), _req("b"), _req("c", "Pick up the screwdriver", "en")], allow_lists=ALLOW, lane="batch"
    )
    assert [r.item_id for r in results] == ["a", "b", "c"]
    assert [r.status for r in results] == ["ok", "failed", "ok"]
    assert results[1].error_kind is AiServiceErrorKind.MODEL_OUTPUT_INVALID
    assert results[1].provenance is not None and results[1].provenance["upstream_code"] == "SCHEMA_VALIDATION_FAILED"


async def test_contract_mismatch_in_content_degrades():
    fake = FakeAiService(script=[Reply(200, {"contract_version": "ai-structured-completion-v1",
                                             "content": {"output": {"motions": []}},
                                             "provenance": {"run_id": "r", "bundle_code": "b", "bundle_status": "shadow",
                                                            "model_requested": "m", "model_served": "m", "retry_count": 0}})])
    (res,) = await _parser(fake).parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.status == "failed" and res.error_kind is AiServiceErrorKind.CONTRACT_MISMATCH


async def test_over_long_statement_is_not_sent():
    fake = FakeAiService()
    (res,) = await _parser(fake).parse([_req(text="字" * (MAX_PARSE_TEXT_CHARS + 1))], allow_lists=ALLOW, lane="batch")
    assert res.status == "failed" and "text_too_long_not_sent" in res.issues
    assert fake.received == []


async def test_disabled_config_builds_a_parser_that_never_calls_out():
    parser = build_wi_parser(load_config({}), resolver=_private)
    assert isinstance(parser, DisabledWiParser)
    (res,) = await parser.parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.status == "failed" and res.error_kind is AiServiceErrorKind.DISABLED


async def test_misconfigured_config_is_disabled_with_reason():
    parser = build_wi_parser(load_config({**ENV, "DDM_AI_SERVICE_BASE_URL": "https://evil.example"}), resolver=_private)
    (res,) = await parser.parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.error_kind is AiServiceErrorKind.MISCONFIGURED


async def test_unreadable_env_builds_a_disabled_parser(monkeypatch):
    monkeypatch.setenv("DDM_AI_SERVICE_ENABLED", "1")
    monkeypatch.setenv("DDM_AI_SERVICE_TIMEOUT_S", "not-a-number")
    parser = build_wi_parser(resolver=_private)
    assert isinstance(parser, DisabledWiParser)
    (res,) = await parser.parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.error_kind is AiServiceErrorKind.MISCONFIGURED


async def test_malformed_motion_values_degrade_the_item_not_the_batch():
    resp = __import__("copy").deepcopy(__import__("fakes.ai_service_app", fromlist=["golden_cases"]).golden_cases()["fewshot-zh-0"]["response"])
    resp["content"]["motions"][0]["hand"] = ["LH"]
    fake = FakeAiService(script=[Reply(200, resp), "ok:fewshot-zh-0"])
    a, b = await _parser(fake).parse([_req("a"), _req("b")], allow_lists=ALLOW, lane="batch")
    assert a.status == "ok" and "hand_invalid" in a.motions[0].issues
    assert b.status == "ok"


async def test_valid_config_builds_the_guarded_http_parser():
    from ddm_v2.ai_integration.guard import GuardedWiParser

    parser = build_wi_parser(load_config(ENV), resolver=_private)
    assert isinstance(parser, GuardedWiParser), "外送一律經 MOST 端配額與並行守門（ADR-037 D8）"
    assert isinstance(parser._inner, AiServiceWiParser)


async def test_actor_and_scope_are_never_sent():
    """ADR-037 D7：員工編號只給 MOST 端配額用，不得出現在送出的 body 或 header。"""
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    req = WiParseRequest(item_id="r1", wi_statement="拿起DIMM", source_lang="zh", actor="IEC141289", scope="site-7")
    await _parser(fake).parse([req], allow_lists=ALLOW, lane="interactive")
    sent = fake.received[0]
    assert "IEC141289" not in str(sent["body"]) and "IEC141289" not in str(sent["headers"])
    assert "site-7" not in str(sent["body"]) and "site-7" not in str(sent["headers"])


async def test_fake_parser_runs_the_real_mapper():
    def content_for(req: WiParseRequest):
        if req.item_id == "down":
            return AiServiceErrorKind.UNREACHABLE
        return {"motions": [{"hand": "RH", "seq_kind": "GM", "sub_activity": "x", "object": "y",
                             "slots": {"s0_A": {"kind": "reach"}, "s1_B": None, "s2_G": "g_fake",
                                       "s3": {"kind": "reach"}, "s4": None,
                                       "s5": {"base": "p_hold", "addon": []}, "s6_A": {"kind": "reach"}}}]}

    fake = FakeWiParser(content_for)
    ok, down = await fake.parse([_req("ok"), _req("down")], allow_lists=ALLOW, lane="interactive")
    assert ok.status == "ok" and ok.motions[0].g2 is None and "unknown_code:s2_G" in ok.motions[0].issues
    assert down.status == "failed" and down.error_kind is AiServiceErrorKind.UNREACHABLE
    assert fake.calls == [("ok", "interactive"), ("down", "interactive")]


async def test_unexpected_mapper_exception_degrades_to_contract_mismatch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """mapper 對不預期的形狀拋任何例外，都要變成該筆 failed，不能穿出 port（ADR-037 D2）。"""
    import ddm_v2.ai_integration.adapter as adapter_mod

    def boom(_content, _allow):
        raise KeyError("SECRET-RESPONSE-VALUE")

    monkeypatch.setattr(adapter_mod, "map_content", boom)
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    (res,) = await _parser(fake).parse([_req()], allow_lists=ALLOW, lane="interactive")
    assert res.status == "failed" and res.error_kind is AiServiceErrorKind.CONTRACT_MISMATCH
    assert res.provenance is not None and res.provenance["upstream_code"] == "MAPPER_REJECTED"
    warned = [r for r in caplog.records if "mapper rejected" in r.getMessage()]
    assert warned, "降級要留 WARNING，讓維運看得到 mapper bug"
    assert warned[0].exc_info is None and "SECRET-RESPONSE-VALUE" not in caplog.text, "log 只記例外類別，不含例外訊息、語句或回應內容"
    assert "KeyError" in warned[0].getMessage()
