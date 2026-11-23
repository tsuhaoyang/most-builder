"""ai_integration.runtime：行程級單例與 status（ADR-037 S3 路由接線）。"""
from __future__ import annotations

import pytest

from ddm_v2.ai_integration import runtime as rt
from ddm_v2.ai_integration.adapter import DisabledWiParser
from ddm_v2.ai_integration.config import MIN_KEY_LENGTH
from ddm_v2.ai_integration.guard import GuardedWiParser

pytestmark = pytest.mark.unit

HOST = "ai-service.internal"
GOOD = {
    "DDM_AI_SERVICE_ENABLED": "1",
    "DDM_AI_SERVICE_BASE_URL": f"https://{HOST}",
    "DDM_AI_SERVICE_ALLOWED_HOSTS": HOST,
    "DDM_AI_SERVICE_KEY": "k" * MIN_KEY_LENGTH,
    "DDM_AI_SERVICE_BUNDLE_CODE": "bundle-x",
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("DDM_AI_SERVICE_"):
            monkeypatch.delenv(k, raising=False)
    rt.reset_for_tests()
    yield
    rt.reset_for_tests()


@pytest.fixture
def private_dns(monkeypatch):
    import ddm_v2.ai_integration.config as cfg

    calls = []

    def resolver(host, port):
        calls.append(host)
        return ["10.0.0.9"]

    monkeypatch.setattr(cfg, "default_resolver", resolver)
    return calls


def _env(monkeypatch, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_disabled_by_default():
    r = rt.get_runtime()
    assert (r.enabled, r.available, r.service_bundle_code) == (False, False, None)
    assert isinstance(r.parser, DisabledWiParser)


def test_enabled_and_valid_gives_a_guarded_parser(monkeypatch, private_dns):
    _env(monkeypatch, GOOD)
    r = rt.get_runtime()
    assert (r.enabled, r.available, r.service_bundle_code) == (True, True, "bundle-x")
    assert isinstance(r.parser, GuardedWiParser)


@pytest.mark.parametrize(
    "override",
    [
        {"DDM_AI_SERVICE_KEY": "short"},
        {"DDM_AI_SERVICE_ALLOWED_HOSTS": "other.internal"},
        {"DDM_AI_SERVICE_BASE_URL": ""},
        {"DDM_AI_SERVICE_TIMEOUT_S": "not-a-number"},
    ],
)
def test_enabled_but_misconfigured_is_enabled_and_not_available(monkeypatch, private_dns, override):
    _env(monkeypatch, {**GOOD, **override})
    r = rt.get_runtime()
    assert r.enabled is True, "營運者開了開關：enabled 反映意圖，不論是哪一種設定錯"
    assert r.available is False and isinstance(r.parser, DisabledWiParser)
    assert r.service_bundle_code is None


def test_a_public_address_is_refused(monkeypatch):
    import ddm_v2.ai_integration.config as cfg

    monkeypatch.setattr(cfg, "default_resolver", lambda h, p: ["8.8.8.8"])
    _env(monkeypatch, GOOD)
    assert rt.get_runtime().available is False


def test_the_runtime_is_built_once_and_shared(monkeypatch, private_dns):
    _env(monkeypatch, GOOD)
    a, b = rt.get_runtime(), rt.get_runtime()
    assert a is b and a.parser is b.parser, "guard 的計數在程序記憶體內：每個請求各建一個＝沒有限制"
    assert len(private_dns) == 1, "DNS 檢查只跑一次"


def test_concurrent_first_calls_build_only_once(monkeypatch, private_dns):
    import threading

    _env(monkeypatch, GOOD)
    results, barrier = [], threading.Barrier(8)

    def worker():
        barrier.wait()
        results.append(rt.get_runtime())

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len({id(r) for r in results}) == 1 and len(private_dns) == 1


def test_an_unexpected_error_while_building_is_contained(monkeypatch, private_dns):
    import ddm_v2.ai_integration.runtime as runtime_mod

    _env(monkeypatch, GOOD)

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(runtime_mod, "GuardedWiParser", boom)
    r = rt.get_runtime()
    assert (r.enabled, r.available) == (True, False) and isinstance(r.parser, DisabledWiParser)
    assert r.expires_at is not None, "非預期錯誤也允許之後重試"


def test_a_transient_dns_failure_is_retried_after_a_while(monkeypatch):
    import ddm_v2.ai_integration.config as cfg
    import ddm_v2.ai_integration.runtime as runtime_mod

    calls = []

    def flaky(host, port):
        calls.append(host)
        if len(calls) == 1:
            raise OSError("dns down")
        return ["10.0.0.9"]

    monkeypatch.setattr(cfg, "default_resolver", flaky)
    _env(monkeypatch, GOOD)
    now = [1000.0]
    monkeypatch.setattr(runtime_mod.time, "monotonic", lambda: now[0])
    first = rt.get_runtime()
    assert first.available is False and first.expires_at == 1000.0 + rt.RETRY_AFTER_S
    assert rt.get_runtime() is first, "冷卻期間不重試（不讓每個請求都打 DNS）"
    now[0] += rt.RETRY_AFTER_S
    second = rt.get_runtime()
    assert second.available is True and len(calls) == 2


def test_a_real_misconfiguration_is_not_retried(monkeypatch, private_dns):
    _env(monkeypatch, {**GOOD, "DDM_AI_SERVICE_KEY": "short"})
    r = rt.get_runtime()
    assert r.expires_at is None, "設定錯要改設定並重啟，不讓每個請求重試"


async def test_the_async_getter_builds_off_the_event_loop(monkeypatch, private_dns):
    import threading

    _env(monkeypatch, GOOD)
    loop_thread = threading.get_ident()
    seen = []
    real = rt._build

    def recording():
        seen.append(threading.get_ident())
        return real()

    monkeypatch.setattr(rt, "_build", recording)
    r = await rt.get_runtime_async()
    assert r.available and seen and seen[0] != loop_thread, "DNS 檢查不能在 event loop 上做"
    await rt.get_runtime_async()
    assert len(seen) == 1


def test_reset_for_tests_rereads_the_environment(monkeypatch, private_dns):
    assert rt.get_runtime().enabled is False
    _env(monkeypatch, GOOD)
    assert rt.get_runtime().enabled is False, "單例：環境變數改了也不會自己重讀"
    rt.reset_for_tests()
    assert rt.get_runtime().enabled is True


def test_the_runtime_repr_contains_no_key(monkeypatch, private_dns):
    _env(monkeypatch, GOOD)
    assert "k" * MIN_KEY_LENGTH not in repr(rt.get_runtime())
