"""ai_service 部署設定與 base URL 安全檢查（ADR-037 D2／D7／D8）。

## 為什麼不放進 `ddm_v2.settings.Settings`

`Settings` 是 frozen dataclass，`repr(settings)` 會印出每一欄。服務金鑰一旦放進去，任何一行
`logger.info(settings)` 或測試失敗訊息就會把它帶出去。本模組的 `AiServiceConfig` 把金鑰包在
`SecretValue`（`repr`／`str` 一律遮蔽），並且只在組 header 的那一刻取出明文。

## 設定（全部來自部署層環境變數；不提供 UI／API 修改，ADR-037 D7）

| 環境變數 | 預設 | 說明 |
|---|---|---|
| `DDM_AI_SERVICE_ENABLED` | false | 總開關。刻意不沿用舊名 `DDM_WI_AI_ENABLED`（ADR-037 D2） |
| `DDM_AI_SERVICE_BASE_URL` | （無） | 例 `https://ai-service.internal:8443` |
| `DDM_AI_SERVICE_ALLOWED_HOSTS` | （無） | 逗號分隔；base URL 的 host 必須在其中 |
| `DDM_AI_SERVICE_ALLOW_PLAINTEXT` | false | 允許 `http://`；即使開啟，也只接受解析到私網位址的 host |
| `DDM_AI_SERVICE_KEY` | （無） | 服務金鑰（`X-AI-Service-Key`）；可用 `DDM_AI_SERVICE_KEY_FILE` 指向檔案 |
| `DDM_AI_SERVICE_BUNDLE_CODE` | `most-wi-motion-parse-poc003` | bundle 不可變，換 prompt＝換 code |
| `DDM_AI_SERVICE_SERVICE_USER` | `most-service` | 服務身分（ADR-037 D7：不送員工編號） |
| `DDM_AI_SERVICE_PLANT_CODE` | `MOST` | 服務身分所屬廠 |
| `DDM_AI_SERVICE_TIMEOUT_S` | 15 | 單次請求總時限（含重試前的單次呼叫） |
| `DDM_AI_SERVICE_MAX_RETRIES` | 2 | 可重試錯誤（429／5xx／逾時）的最多重試次數 |

## 服務身分（ADR-037 D7）

ai_service 的 `structured-completion` 用 `require_acting_user`：除了服務金鑰，還要求
`X-User-Id`、`X-User-Role`、`X-Plant-Code`、`X-Username` 四個 header，缺任一回 401。
ADR-037 裁決不送員工編號，所以這四個 header 一律填**固定的服務身分**（來自部署設定），
**絕不**取自入站請求或 `CurrentUser`。使用者歸屬由 MOST 自己的稽核紀錄以 `run_id` 對帳。
ai_service 端不得依這些 header 授權（ADR-037 D7、計畫 §7 第 8 項）。
"""
from __future__ import annotations

import ipaddress
import math
import os
import re
import socket
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind

DEFAULT_BUNDLE_CODE = "most-wi-motion-parse-poc003"
DEFAULT_SERVICE_USER = "most-service"
DEFAULT_PLANT_CODE = "MOST"
# ai_service 不解讀 role 語意（auth-tenancy §2.1）；送一個說明身分性質的固定字串
SERVICE_ROLE = "service"
MIN_KEY_LENGTH = 24
MAX_TIMEOUT_S = 120.0
MAX_RETRIES_CAP = 5
# header 值：只接受可列印 ASCII（httpx 對非 latin-1 會丟非 AiServiceError 的例外）
_HEADER_SAFE = re.compile(r"^[\x21-\x7e]+$")

# ADR-037 D8 的保守預設（暫定，量測後調整）
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_MAX_RETRIES = 2
MAX_RESPONSE_BYTES = 256 * 1024

Resolver = Callable[[str, int], Iterable[str]]


class SecretValue:
    """只在 `reveal()` 時給出明文；`repr`／`str`／比較都不洩漏。"""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "SecretValue('**********')"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:  # 只供測試比較；不暴露值
        return isinstance(other, SecretValue) and other._value == self._value

    def __hash__(self) -> int:
        return hash(("SecretValue", len(self._value)))


@dataclass(frozen=True)
class AiServiceConfig:
    enabled: bool
    base_url: str | None
    allowed_hosts: frozenset[str]
    allow_plaintext: bool
    key: SecretValue | None = field(repr=False)
    bundle_code: str
    service_user: str
    plant_code: str
    timeout_s: float
    max_retries: int

    def identity_headers(self) -> dict[str, str]:
        """固定的服務身分 header（不含金鑰）。"""
        return {
            "X-User-Id": self.service_user,
            "X-User-Role": SERVICE_ROLE,
            "X-Plant-Code": self.plant_code,
            "X-Username": self.service_user,
        }


def _parse_bool(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_key(env: dict[str, str]) -> SecretValue | None:
    path = (env.get("DDM_AI_SERVICE_KEY_FILE") or "").strip()
    if path:
        value = Path(path).read_text(encoding="utf-8").strip()
    else:
        value = (env.get("DDM_AI_SERVICE_KEY") or "").strip()
    return SecretValue(value) if value else None


def load_config(env: dict[str, str] | None = None) -> AiServiceConfig:
    """從環境變數讀設定。不做網路檢查（那是 `validate_config` 的事）。

    數值格式錯誤或金鑰檔讀不到時丟 `AiServiceError(MISCONFIGURED)`（不讓 ValueError／OSError
    變成啟動失敗；呼叫端據此停用整合）。
    """
    try:
        return _load_config(env)
    except (ValueError, OSError) as exc:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="unreadable_config") from exc


def _load_config(env: dict[str, str] | None) -> AiServiceConfig:
    e = dict(os.environ if env is None else env)
    hosts = frozenset(h.strip().lower() for h in (e.get("DDM_AI_SERVICE_ALLOWED_HOSTS") or "").split(",") if h.strip())
    return AiServiceConfig(
        enabled=_parse_bool(e.get("DDM_AI_SERVICE_ENABLED")),
        base_url=(e.get("DDM_AI_SERVICE_BASE_URL") or "").strip() or None,
        allowed_hosts=hosts,
        allow_plaintext=_parse_bool(e.get("DDM_AI_SERVICE_ALLOW_PLAINTEXT")),
        key=_read_key(e),
        bundle_code=(e.get("DDM_AI_SERVICE_BUNDLE_CODE") or DEFAULT_BUNDLE_CODE).strip(),
        service_user=(e.get("DDM_AI_SERVICE_SERVICE_USER") or DEFAULT_SERVICE_USER).strip(),
        plant_code=(e.get("DDM_AI_SERVICE_PLANT_CODE") or DEFAULT_PLANT_CODE).strip(),
        timeout_s=float(e.get("DDM_AI_SERVICE_TIMEOUT_S") or DEFAULT_TIMEOUT_S),
        max_retries=int(e.get("DDM_AI_SERVICE_MAX_RETRIES") or DEFAULT_MAX_RETRIES),
    )


def default_resolver(host: str, port: int) -> list[str]:
    return sorted({str(info[4][0]) for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


# 雖然落在 is_private 範圍內、但實際上是雲端 metadata 或內嵌其他位址的前綴，一律擋。
_DENIED_NETWORKS = tuple(
    ipaddress.ip_network(n)
    for n in (
        "fd00:ec2::/32",  # AWS IPv6 metadata（ULA 範圍內）
        "2002::/16",  # 6to4（可內嵌 169.254.169.254）
        "64:ff9b::/96",  # NAT64 well-known（內嵌 IPv4）
        "64:ff9b:1::/48",  # NAT64 local-use
        "100.64.0.0/10",  # CGNAT（非 RFC1918）
        # Python 的 is_private 把下列特殊用途段算進來，但它們不是內網位址
        "2001::/23",  # IETF protocol assignments（含 Teredo 2001::/32）
        "2001:db8::/32",  # 文件用
        "3fff::/20",  # 文件用
        "192.0.0.0/24",  # IETF protocol assignments
        "192.0.2.0/24",  # TEST-NET-1
        "198.18.0.0/15",  # benchmarking
    )
)


def is_allowed_address(ip_text: str) -> bool:
    """只接受私網位址（RFC1918、ULA）與 loopback（含 IPv6 `::1`）；擋 link-local（含雲端 metadata
    169.254.169.254）、multicast、未指定、保留位址、`_DENIED_NETWORKS` 與一切公網位址。
    格式不合法的字串回 False（不拋例外）。"""
    try:
        ip = ipaddress.ip_address(ip_text.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    if any(ip in net for net in _DENIED_NETWORKS if net.version == ip.version):
        return False
    if ip.is_loopback:
        return True
    if ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
        return False
    return ip.is_private


def validate_target(
    base_url: str,
    allowed_hosts: frozenset[str],
    *,
    allow_plaintext: bool,
    resolver: Resolver = default_resolver,
) -> list[str]:
    """檢查 base URL 是否可連；回傳解析後的位址清單。不合法就丟 `AiServiceError(MISCONFIGURED)`。

    連線時 client 會再用同一個 resolver 檢查一次（防 DNS 重新綁定，ADR-037 D7）。
    """
    try:
        parts = urlsplit(base_url)
        scheme = (parts.scheme or "").lower()
        host = (parts.hostname or "").lower()
        explicit_port = parts.port
    except ValueError as exc:  # 壞 port、未閉合的 IPv6 字面
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="unparsable_url") from exc
    if not _HEADER_SAFE.fullmatch(base_url):  # 控制字元、空白、非 ASCII（含 path／query）
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="unparsable_url")
    if scheme not in {"https", "http"} or not host:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="bad_scheme_or_host")
    if parts.username or parts.password:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="userinfo_in_url")
    if scheme == "http" and not allow_plaintext:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="plaintext_not_allowed")
    if host not in allowed_hosts:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="host_not_allowed")
    port = explicit_port or (443 if scheme == "https" else 80)
    try:
        addresses = [str(a) for a in resolver(host, port)]
    except (OSError, ValueError) as exc:  # UnicodeError 是 ValueError 的子類
        raise AiServiceError(AiServiceErrorKind.UNREACHABLE, upstream_code="dns_failed") from exc
    if not addresses:
        raise AiServiceError(AiServiceErrorKind.UNREACHABLE, upstream_code="dns_empty")
    bad = [a for a in addresses if not is_allowed_address(a)]
    if bad:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="address_not_private")
    return addresses


def validate_config(config: AiServiceConfig, *, resolver: Resolver = default_resolver) -> None:
    """開關開啟時必須通過的檢查；不通過丟 `AiServiceError`，呼叫端據此停用整合並記錄。"""
    if not config.enabled:
        raise AiServiceError(AiServiceErrorKind.DISABLED)
    if not config.base_url or config.key is None:
        raise AiServiceError(AiServiceErrorKind.DISABLED, upstream_code="incomplete_config")
    if len(config.key.reveal()) < MIN_KEY_LENGTH:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="key_too_short")
    if not _HEADER_SAFE.fullmatch(config.key.reveal()):
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="key_not_printable_ascii")
    for value in (config.bundle_code, config.service_user, config.plant_code):
        if not value or not _HEADER_SAFE.fullmatch(value):
            raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="identity_or_bundle_invalid")
    if not (math.isfinite(config.timeout_s) and 0 < config.timeout_s <= MAX_TIMEOUT_S):
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="bad_limits")
    if not 0 <= config.max_retries <= MAX_RETRIES_CAP:
        raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="bad_limits")
    validate_target(
        config.base_url, config.allowed_hosts, allow_plaintext=config.allow_plaintext, resolver=resolver
    )
