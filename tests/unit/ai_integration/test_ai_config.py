"""ai_integration.config：設定讀取、金鑰遮蔽、base URL 安全檢查（ADR-037 D7）。"""
from __future__ import annotations

import pytest

from ddm_v2.ai_integration.config import (
    MIN_KEY_LENGTH,
    SecretValue,
    is_allowed_address,
    load_config,
    validate_config,
    validate_target,
)
from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind

pytestmark = pytest.mark.unit

KEY = "k" * MIN_KEY_LENGTH
HOST = "ai-service.internal"


def _env(**over: str) -> dict[str, str]:
    env = {
        "DDM_AI_SERVICE_ENABLED": "1",
        "DDM_AI_SERVICE_BASE_URL": f"https://{HOST}:8443",
        "DDM_AI_SERVICE_ALLOWED_HOSTS": HOST,
        "DDM_AI_SERVICE_KEY": KEY,
    }
    env.update(over)
    return env


def _private(host: str, port: int) -> list[str]:  # noqa: ARG001
    return ["10.1.2.3"]


def _kind(fn) -> AiServiceErrorKind:  # type: ignore[no-untyped-def]
    with pytest.raises(AiServiceError) as exc:
        fn()
    return exc.value.kind


def test_defaults_are_off_and_never_read_legacy_names():
    cfg = load_config({"DDM_WI_AI_ENABLED": "1", "DDM_LLM_BASE_URL": "https://api.openai.com/v1"})
    assert cfg.enabled is False, "舊開關名不得啟用新整合（ADR-037 D2）"
    assert cfg.base_url is None and cfg.key is None
    assert _kind(lambda: validate_config(cfg, resolver=_private)) is AiServiceErrorKind.DISABLED


def test_key_never_appears_in_repr_or_str():
    cfg = load_config(_env())
    for text in (repr(cfg), str(cfg), repr(cfg.key), str(cfg.key)):
        assert KEY not in text
    assert cfg.key is not None and cfg.key.reveal() == KEY


def test_key_file_is_supported(tmp_path):
    f = tmp_path / "key"
    f.write_text(KEY + "\n", encoding="utf-8")
    cfg = load_config(_env(DDM_AI_SERVICE_KEY="", DDM_AI_SERVICE_KEY_FILE=str(f)))
    assert cfg.key == SecretValue(KEY)


def test_identity_headers_are_the_fixed_service_identity():
    """ADR-037 D7：不送員工編號；四個 header 都是部署設定的服務身分。"""
    cfg = load_config(_env(DDM_AI_SERVICE_SERVICE_USER="svc-most", DDM_AI_SERVICE_PLANT_CODE="P01"))
    assert cfg.identity_headers() == {
        "X-User-Id": "svc-most",
        "X-User-Role": "service",
        "X-Plant-Code": "P01",
        "X-Username": "svc-most",
    }


def test_valid_config_passes():
    validate_config(load_config(_env()), resolver=_private)


@pytest.mark.parametrize(
    "over,code",
    [
        ({"DDM_AI_SERVICE_KEY": "short"}, "key_too_short"),
        ({"DDM_AI_SERVICE_BASE_URL": f"http://{HOST}"}, "plaintext_not_allowed"),
        ({"DDM_AI_SERVICE_BASE_URL": "https://evil.example"}, "host_not_allowed"),
        ({"DDM_AI_SERVICE_BASE_URL": f"https://u:p@{HOST}"}, "userinfo_in_url"),
        ({"DDM_AI_SERVICE_BASE_URL": f"ftp://{HOST}"}, "bad_scheme_or_host"),
        ({"DDM_AI_SERVICE_TIMEOUT_S": "0"}, "bad_limits"),
    ],
)
def test_misconfiguration_is_rejected(over: dict[str, str], code: str):
    with pytest.raises(AiServiceError) as exc:
        validate_config(load_config(_env(**over)), resolver=_private)
    assert exc.value.kind is AiServiceErrorKind.MISCONFIGURED
    assert exc.value.upstream_code == code


def test_incomplete_config_is_disabled_not_misconfigured():
    cfg = load_config(_env(DDM_AI_SERVICE_KEY=""))
    assert _kind(lambda: validate_config(cfg, resolver=_private)) is AiServiceErrorKind.DISABLED


@pytest.mark.parametrize(
    "ip,ok",
    [
        ("10.0.0.5", True),
        ("172.16.1.1", True),
        ("192.168.1.10", True),
        ("127.0.0.1", True),
        ("fd00::1", True),
        ("169.254.169.254", False),  # 雲端 metadata
        ("fe80::1", False),
        ("8.8.8.8", False),
        ("172.32.3.60", False),  # 非 RFC1918（CI_GATES 的 DSX 主機先例）
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("::ffff:169.254.169.254", False),  # IPv4-mapped 繞道
        ("::1", True),  # IPv6 loopback
        ("fd00:ec2::254", False),  # AWS IPv6 metadata（ULA 範圍內）
        ("2002:a9fe:a9fe::1", False),  # 6to4 內嵌 169.254.169.254
        ("64:ff9b::a9fe:a9fe", False),  # NAT64 內嵌
        ("100.64.0.1", False),  # CGNAT
        ("not-an-ip", False),
        ("fe80::1%eth0", False),
        ("2001::1", False),  # IETF protocol assignments
        ("2001:0:4136:e378::1", False),  # Teredo
        ("2001:db8::1", False),  # 文件用
        ("192.0.2.1", False),  # TEST-NET-1
        ("198.18.0.1", False),  # benchmarking
    ],
)
def test_address_policy(ip: str, ok: bool):
    assert is_allowed_address(ip) is ok


def test_host_resolving_to_public_address_is_rejected():
    with pytest.raises(AiServiceError) as exc:
        validate_target(f"https://{HOST}", frozenset({HOST}), allow_plaintext=False, resolver=lambda h, p: ["8.8.8.8"])
    assert exc.value.upstream_code == "address_not_private"


def test_any_bad_address_among_several_is_rejected():
    """DNS 回多筆時只要有一筆不合格就拒絕（不挑好的那筆用）。"""
    with pytest.raises(AiServiceError):
        validate_target(
            f"https://{HOST}", frozenset({HOST}), allow_plaintext=False, resolver=lambda h, p: ["10.0.0.1", "169.254.169.254"]
        )


@pytest.mark.parametrize(
    "env_over",
    [{"DDM_AI_SERVICE_TIMEOUT_S": "abc"}, {"DDM_AI_SERVICE_MAX_RETRIES": "x"}, {"DDM_AI_SERVICE_KEY_FILE": "/nonexistent/key"}],
)
def test_unreadable_config_is_misconfigured_not_a_crash(env_over: dict[str, str]):
    with pytest.raises(AiServiceError) as exc:
        load_config(_env(**env_over))
    assert exc.value.kind is AiServiceErrorKind.MISCONFIGURED


@pytest.mark.parametrize(
    "over,code",
    [
        ({"DDM_AI_SERVICE_TIMEOUT_S": "nan"}, "bad_limits"),
        ({"DDM_AI_SERVICE_TIMEOUT_S": "inf"}, "bad_limits"),
        ({"DDM_AI_SERVICE_TIMEOUT_S": "9999"}, "bad_limits"),
        ({"DDM_AI_SERVICE_MAX_RETRIES": "99"}, "bad_limits"),
        ({"DDM_AI_SERVICE_BASE_URL": f"https://{HOST}:99999"}, "unparsable_url"),
        ({"DDM_AI_SERVICE_BASE_URL": f"https://{HOST}:abc"}, "unparsable_url"),
        ({"DDM_AI_SERVICE_BASE_URL": "https://[::1"}, "unparsable_url"),
        ({"DDM_AI_SERVICE_BASE_URL": f"https://{HOST}/\x01x"}, "unparsable_url"),
        ({"DDM_AI_SERVICE_BASE_URL": f"https://{HOST}/a b"}, "unparsable_url"),
        ({"DDM_AI_SERVICE_KEY": "金鑰" * MIN_KEY_LENGTH}, "key_not_printable_ascii"),
        ({"DDM_AI_SERVICE_SERVICE_USER": "svc\nX-Injected: 1"}, "identity_or_bundle_invalid"),
    ],
)
def test_edge_values_are_misconfigured_not_crashes(over: dict[str, str], code: str):
    with pytest.raises(AiServiceError) as exc:
        validate_config(load_config(_env(**over)), resolver=_private)
    assert exc.value.kind is AiServiceErrorKind.MISCONFIGURED
    assert exc.value.upstream_code == code


def test_resolver_value_error_is_unreachable_not_a_crash():
    def bad(h: str, p: int) -> list[str]:
        raise ValueError("bad idna")

    with pytest.raises(AiServiceError) as exc:
        validate_target(f"https://{HOST}", frozenset({HOST}), allow_plaintext=False, resolver=bad)
    assert exc.value.kind is AiServiceErrorKind.UNREACHABLE


def test_dns_failure_is_unreachable():
    def boom(h: str, p: int) -> list[str]:
        raise OSError("no such host")

    with pytest.raises(AiServiceError) as exc:
        validate_target(f"https://{HOST}", frozenset({HOST}), allow_plaintext=False, resolver=boom)
    assert exc.value.kind is AiServiceErrorKind.UNREACHABLE
