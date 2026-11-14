"""ai_integration.client：經假 ai_service（ASGI）驗證線上行為（ADR-037 D2／D7／D8）。"""
from __future__ import annotations

import httpx
import pytest
from fakes.ai_service_app import FakeAiService, Reply, error_body, golden_cases

from ddm_v2.ai_integration.client import CONTRACT_VERSION, AiServiceClient, CircuitBreaker
from ddm_v2.ai_integration.config import MIN_KEY_LENGTH, load_config
from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind

pytestmark = pytest.mark.unit

KEY = "s3cret-" + "k" * MIN_KEY_LENGTH
HOST = "ai-service.internal"


def _cfg(**over: str):
    env = {
        "DDM_AI_SERVICE_ENABLED": "1",
        "DDM_AI_SERVICE_BASE_URL": f"https://{HOST}",
        "DDM_AI_SERVICE_ALLOWED_HOSTS": HOST,
        "DDM_AI_SERVICE_KEY": KEY,
        "DDM_AI_SERVICE_TIMEOUT_S": "2",
        "DDM_AI_SERVICE_MAX_RETRIES": "2",
    }
    env.update(over)
    return load_config(env)


def _private(h: str, p: int) -> list[str]:  # noqa: ARG001
    return ["10.0.0.9"]


def golden_response() -> dict:
    import copy

    return copy.deepcopy(golden_cases()["fewshot-zh-0"]["response"])


async def _no_sleep(_s: float) -> None:
    return None


def _client(fake: FakeAiService, *, cfg=None, resolver=_private, breaker=None) -> AiServiceClient:
    return AiServiceClient(
        cfg or _cfg(),
        transport=httpx.ASGITransport(app=fake.app()),
        resolver=resolver,
        breaker=breaker,
        sleep=_no_sleep,
        jitter=lambda: 0.0,
    )


async def _call(client: AiServiceClient, *, lane: str = "interactive"):
    return await client.structured_completion(
        variables={"wi_statement": "拿起DIMM", "source_lang": "zh", "context": {}},
        json_schema={"type": "object"},
        prompt_variant="zh",
        lane=lane,
        request_id="req-1",
    )


async def test_success_sends_contract_body_and_service_identity():
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    result = await _call(_client(fake), lane="batch")
    assert result.content["motions"]
    assert result.provenance.run_id == "run-golden-0"
    assert result.attempts == 1

    sent = fake.received[0]
    body = sent["body"]
    assert body["contract_version"] == CONTRACT_VERSION
    assert body["bundle_code"] == "most-wi-motion-parse-poc003"
    assert body["lane"] == "batch"
    assert 1500 <= body["deadline_ms"] <= 2000, "deadline_ms 是剩餘預算，不超過總時限"
    assert set(body["variables"]) == {"wi_statement", "source_lang", "context"}
    h = sent["headers"]
    assert h["x-ai-service-key"] == KEY
    assert h["x-username"] == "most-service" and h["x-user-id"] == "most-service"
    assert h["x-plant-code"] == "MOST" and h["x-user-role"] == "service"
    assert h["x-request-id"] == "req-1"


@pytest.mark.parametrize(
    "reply,kind,code",
    [
        (Reply(401, error_body("AUTH_REQUIRED")), AiServiceErrorKind.AUTH, "AUTH_REQUIRED"),
        (Reply(409, error_body("BUNDLE_NOT_RUNNABLE")), AiServiceErrorKind.BUNDLE_NOT_RUNNABLE, "BUNDLE_NOT_RUNNABLE"),
        (Reply(422, error_body("SCHEMA_VALIDATION_FAILED")), AiServiceErrorKind.MODEL_OUTPUT_INVALID, "SCHEMA_VALIDATION_FAILED"),
        (Reply(422, error_body("CONTRACT_VERSION_MISMATCH")), AiServiceErrorKind.REQUEST_REJECTED, "CONTRACT_VERSION_MISMATCH"),
        (Reply(503, error_body("PROMPT_ASSET_MISMATCH")), AiServiceErrorKind.DEPLOYMENT, "PROMPT_ASSET_MISMATCH"),
        (Reply(503, error_body("PROVIDER_NOT_CONFIGURED")), AiServiceErrorKind.DEPLOYMENT, "PROVIDER_NOT_CONFIGURED"),
        (Reply(502, error_body("PROVIDER_UNREACHABLE")), AiServiceErrorKind.UPSTREAM, "PROVIDER_UNREACHABLE"),
        (Reply(504, error_body("PROVIDER_TIMEOUT")), AiServiceErrorKind.TIMEOUT, "PROVIDER_TIMEOUT"),
    ],
)
async def test_errors_are_classified_by_code(reply: Reply, kind: AiServiceErrorKind, code: str):
    fake = FakeAiService(script=[reply])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake, cfg=_cfg(DDM_AI_SERVICE_MAX_RETRIES="0")))
    assert exc.value.kind is kind
    assert exc.value.upstream_code == code
    assert exc.value.http_status == reply.status


async def test_plain_text_500_is_upstream_and_retried():
    fake = FakeAiService(script=["text500", "text500", "ok:fewshot-zh-0"])
    result = await _call(_client(fake))
    assert result.attempts == 3 and len(fake.received) == 3


async def test_rate_limit_honours_retry_after_then_succeeds():
    slept: list[float] = []

    async def rec(s: float) -> None:
        slept.append(s)

    fake = FakeAiService(script=[Reply(429, error_body("ADMISSION_REJECTED"), {"Retry-After": "1.5"}), "ok:fewshot-zh-0"])
    client = AiServiceClient(
        _cfg(), transport=httpx.ASGITransport(app=fake.app()), resolver=_private, sleep=rec, jitter=lambda: 0.0
    )
    result = await _call(client)
    assert result.attempts == 2
    assert slept == [1.5]


async def test_retries_are_bounded():
    fake = FakeAiService(script=["text500"])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.kind is AiServiceErrorKind.UPSTREAM
    assert len(fake.received) == 3  # 1 + max_retries(2)


async def test_non_retryable_errors_are_not_retried():
    fake = FakeAiService(script=[Reply(422, error_body("SCHEMA_VALIDATION_FAILED"))])
    with pytest.raises(AiServiceError):
        await _call(_client(fake))
    assert len(fake.received) == 1


async def test_redirect_is_refused_and_not_followed():
    fake = FakeAiService(script=["redirect"])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.upstream_code == "redirect_refused"
    assert len(fake.received) == 1


async def test_oversized_response_is_rejected():
    fake = FakeAiService(script=["huge"])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.kind is AiServiceErrorKind.RESPONSE_TOO_LARGE


async def test_total_timeout_is_enforced():
    fake = FakeAiService(script=["slow"], slow_s=5.0)
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake, cfg=_cfg(DDM_AI_SERVICE_TIMEOUT_S="0.2", DDM_AI_SERVICE_MAX_RETRIES="0")))
    assert exc.value.kind is AiServiceErrorKind.TIMEOUT


@pytest.mark.parametrize(
    "body",
    [
        {"contract_version": "ai-structured-completion-v2", "content": {}, "provenance": {}},
        {"contract_version": CONTRACT_VERSION, "content": [], "provenance": {}},
        {"contract_version": CONTRACT_VERSION, "content": {"motions": []}},
    ],
)
async def test_unexpected_success_shape_is_contract_mismatch(body: dict):
    fake = FakeAiService(script=[Reply(200, body)])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.kind is AiServiceErrorKind.CONTRACT_MISMATCH


async def test_dns_rebinding_is_caught_per_request():
    """啟動時解析到私網、請求時改解析到 metadata 位址 → 不送出請求。"""
    answers = iter([["10.0.0.9"], ["169.254.169.254"]])
    fake = FakeAiService(script=["ok:fewshot-zh-0"])
    client = _client(fake, resolver=lambda h, p: next(answers))
    await _call(client)
    with pytest.raises(AiServiceError) as exc:
        await _call(client)
    assert exc.value.kind is AiServiceErrorKind.MISCONFIGURED
    assert len(fake.received) == 1


async def test_error_messages_never_contain_the_key_or_upstream_message():
    fake = FakeAiService(script=[Reply(401, error_body("AUTH_REQUIRED", message=f"bad key {KEY}"))])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert KEY not in str(exc.value) and "bad key" not in str(exc.value)


async def test_deployment_errors_and_timeouts_are_not_retried():
    """重試不會讓部署不一致變好；逾時重送會重複計費（ADR-037 D8）。"""
    for reply in (Reply(503, error_body("PROMPT_ASSET_MISMATCH")), Reply(504, error_body("PROVIDER_TIMEOUT"))):
        fake = FakeAiService(script=[reply])
        with pytest.raises(AiServiceError):
            await _call(_client(fake))
        assert len(fake.received) == 1


@pytest.mark.parametrize(
    "code",
    ["bad\nINJECTED log line", "x" * 500, "lowercase_code", 42],
)
async def test_upstream_code_is_validated_before_it_reaches_logs(code, caplog):
    fake = FakeAiService(script=[Reply(500, {"error": {"code": code, "message": "m", "detail": None}})])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake, cfg=_cfg(DDM_AI_SERVICE_MAX_RETRIES="0")))
    assert exc.value.upstream_code == "UNKNOWN"
    assert "INJECTED" not in caplog.text and "x" * 100 not in caplog.text


async def test_logs_never_contain_the_key(caplog):
    caplog.set_level("DEBUG")
    fake = FakeAiService(script=[Reply(401, error_body("AUTH_REQUIRED", message=f"bad key {KEY}"))])
    with pytest.raises(AiServiceError):
        await _call(_client(fake))
    assert caplog.records, "這條要有 log 可查，否則是空跑"
    assert KEY not in caplog.text


async def test_undecodable_response_degrades_instead_of_escaping():
    """宣稱 gzip 但本文不是 → httpx.DecodingError；必須轉成 AiServiceError。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-encoding": "gzip"}, content=b"not gzip at all")

    client = AiServiceClient(_cfg(), transport=httpx.MockTransport(handler), resolver=_private, sleep=_no_sleep)
    with pytest.raises(AiServiceError) as exc:
        await _call(client)
    assert exc.value.kind is AiServiceErrorKind.CONTRACT_MISMATCH


@pytest.mark.parametrize(
    "prov_over,code",
    [
        ({"bundle_code": "some-other-bundle"}, "BUNDLE_MISMATCH"),
        ({"bundle_status": "draft"}, "BUNDLE_STATUS_UNEXPECTED"),
        ({"model_served": "evil\nmodel"}, None),
        ({"run_id": "x" * 500}, None),
        ({"retry_count": "3"}, None),
        ({"prompt_variant": {"nested": 1}}, "ok"),
    ],
)
async def test_provenance_is_validated(prov_over: dict, code):
    resp = golden_response()
    resp["provenance"].update(prov_over)
    fake = FakeAiService(script=[Reply(200, resp)])
    if code == "ok":
        result = await _call(_client(fake))
        assert result.provenance.prompt_variant is None, "不合格的選填欄位記 None，不透傳"
        return
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.kind is AiServiceErrorKind.CONTRACT_MISMATCH
    if code:
        assert exc.value.upstream_code == code


async def test_total_budget_covers_retries():
    """總時限涵蓋重試與退避：Retry-After 超過剩餘預算就不再重試。"""
    fake = FakeAiService(script=[Reply(429, error_body("ADMISSION_REJECTED"), {"Retry-After": "10"}), "ok:fewshot-zh-0"])
    with pytest.raises(AiServiceError) as exc:
        await _call(_client(fake))
    assert exc.value.kind is AiServiceErrorKind.RATE_LIMITED
    assert len(fake.received) == 1


@pytest.mark.parametrize("raw", ["nan", "inf", "-5", "garbage"])
def test_retry_after_parsing_is_bounded(raw: str):
    from ddm_v2.ai_integration.client import MAX_RETRY_AFTER_S, _parse_retry_after

    value = _parse_retry_after(raw)
    assert value is None or 0.0 <= value <= MAX_RETRY_AFTER_S


def test_half_open_lets_only_one_probe_through():
    now = [0.0]
    b = CircuitBreaker(threshold=1, cooldown_s=10.0, clock=lambda: now[0])
    b.record_failure()
    assert not b.allow()
    now[0] = 11.0
    assert b.allow() is True
    assert b.allow() is False, "試探進行中，其他請求不得放行"
    b.record_failure()  # 試探失敗 → 重新開路
    assert not b.allow()
    now[0] = 22.0
    assert b.allow() is True
    b.record_success()
    assert b.allow() and b.allow()


def test_neutral_result_during_probe_keeps_the_circuit_open():
    now = [0.0]
    b = CircuitBreaker(threshold=1, cooldown_s=10.0, clock=lambda: now[0])
    b.record_failure()
    now[0] = 11.0
    assert b.allow()
    b.record_neutral()  # 例如 AUTH：不代表服務恢復
    assert not b.allow()


async def test_circuit_counts_requests_not_attempts():
    breaker = CircuitBreaker(threshold=2)
    fake = FakeAiService(script=["text500"])
    with pytest.raises(AiServiceError):
        await _call(_client(fake, breaker=breaker))  # 3 次嘗試、1 個請求
    assert len(fake.received) == 3
    assert not breaker.is_open, "一個請求的重試不得各自計入熔斷"


@pytest.mark.parametrize("status", [200, 500])
async def test_deeply_nested_json_degrades_instead_of_escaping(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=b"[" * 100_000)

    client = AiServiceClient(
        _cfg(DDM_AI_SERVICE_MAX_RETRIES="0"), transport=httpx.MockTransport(handler), resolver=_private, sleep=_no_sleep
    )
    with pytest.raises(AiServiceError):
        await _call(client)


async def test_cancelled_probe_does_not_wedge_the_circuit():
    """half-open 試探被取消（使用者斷線、外層 timeout）後，熔斷器必須能再放下一個試探。"""
    import asyncio

    now = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown_s=10.0, clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 11.0
    fake = FakeAiService(script=["slow"], slow_s=5.0)
    client = _client(fake, cfg=_cfg(DDM_AI_SERVICE_TIMEOUT_S="10"), breaker=breaker)
    task = asyncio.ensure_future(_call(client))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    now[0] = 30.0
    assert breaker.allow(), "取消後試探旗標卡住，整合會停擺到重啟"


@pytest.mark.parametrize("timeout", ["nan", "inf"])
async def test_unvalidated_timeout_fails_before_taking_the_probe(timeout: str):
    """直接建 client（繞過 validate_config）時，壞 timeout 不得在拿到 half-open 許可後才失敗。"""
    now = [0.0]
    breaker = CircuitBreaker(threshold=1, cooldown_s=10.0, clock=lambda: now[0])
    breaker.record_failure()
    now[0] = 11.0
    client = _client(FakeAiService(), cfg=_cfg(DDM_AI_SERVICE_TIMEOUT_S=timeout), breaker=breaker)
    with pytest.raises(AiServiceError) as exc:
        await _call(client)
    assert exc.value.kind is AiServiceErrorKind.MISCONFIGURED
    assert breaker.allow(), "試探許可不得被消耗掉"


async def test_circuit_opens_after_repeated_upstream_failures():
    now = [0.0]
    breaker = CircuitBreaker(threshold=2, cooldown_s=30.0, clock=lambda: now[0])
    fake = FakeAiService(script=["text500"])
    client = _client(fake, cfg=_cfg(DDM_AI_SERVICE_MAX_RETRIES="0"), breaker=breaker)
    for _ in range(2):
        with pytest.raises(AiServiceError):
            await _call(client)
    with pytest.raises(AiServiceError) as exc:
        await _call(client)
    assert exc.value.kind is AiServiceErrorKind.CIRCUIT_OPEN
    assert len(fake.received) == 2, "熔斷中不得再送請求"

    now[0] = 31.0
    fake.script = ["ok:fewshot-zh-0"]
    result = await _call(client)
    assert result.attempts == 1 and not breaker.is_open


async def test_caller_errors_do_not_trip_the_circuit():
    breaker = CircuitBreaker(threshold=1)
    fake = FakeAiService(script=[Reply(422, error_body("SCHEMA_VALIDATION_FAILED"))])
    client = _client(fake, breaker=breaker)
    with pytest.raises(AiServiceError):
        await _call(client)
    assert not breaker.is_open


async def test_unknown_lane_is_a_programming_error():
    with pytest.raises(ValueError):
        await _call(_client(FakeAiService()), lane="bulk")
