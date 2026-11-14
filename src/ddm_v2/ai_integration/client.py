"""ai_service HTTP client：`POST /v1/llm/structured-completion`（ADR-037 D2／D7／D8）。

契約權威是 ai_service 的 `docs/api/openapi.json`（`StructuredCompletionRequest`／`Response`）與
api spec §2.2（錯誤信封）、§4.1（錯誤碼表）。本模組只依賴 ai_service main 上已實作的端點。

安全與資源上限：

- `trust_env=False`：不吃環境的 proxy／`.netrc`，請求只會去 base URL。
- `follow_redirects=False`：redirect 一律視為錯誤，不跟隨（否則金鑰會被帶到別的 host）。
- 每次請求前用同一個 resolver 重新檢查 host 解析出的位址（防 DNS 重新綁定）。這仍有 TOCTOU
  空窗（檢查與 httpx 實際連線之間），完整解法是把連線釘在檢查過的 IP，留待部署確定 TLS 方案時做。
- 單次請求總時限用 `asyncio.timeout` 包住（httpx 的 timeout 是逐段計時，不是總時限；同 `dsx_client`）。
- 回應本文以串流讀取，超過 `MAX_RESPONSE_BYTES` 即中止。
- 金鑰只出現在送出的 header；例外訊息不含金鑰、URL、upstream message。

時限：`timeout_s` 是**整次呼叫（含重試與退避）的總預算**；每次嘗試只拿剩餘時間，送給
ai_service 的 `deadline_ms` 也隨之遞減。

熔斷：程序內計數。以**請求**為單位計失敗（一次請求重試三次只算一次）；連續 N 個請求失敗就
開路一段時間，冷卻後只放**一個**試探請求（half-open），其餘照樣快速失敗，直到試探有結果。
多 worker 部署時每個程序各自計數——ADR-037 D8 已註明單程序前提，S5 批量階段另議。

外部字串：upstream 的 `error.code` 與 provenance 欄位都是外部可控字串，進 log／provenance 前一律
驗格式與長度（不合格記 `UNKNOWN`／判契約不符），避免 log injection 與外部字串入庫。
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import re
import time
from dataclasses import dataclass
from typing import Any

import httpx

from ddm_v2.ai_integration.config import (
    MAX_RESPONSE_BYTES,
    AiServiceConfig,
    Resolver,
    default_resolver,
    validate_target,
)
from ddm_v2.ai_integration.errors import (
    CIRCUIT_COUNTED_KINDS,
    RETRYABLE_KINDS,
    AiServiceError,
    AiServiceErrorKind,
)

logger = logging.getLogger(__name__)

CONTRACT_VERSION = "ai-structured-completion-v1"
ENDPOINT_PATH = "/v1/llm/structured-completion"
LANES = frozenset({"interactive", "batch"})

_STATUS_TO_KIND: dict[int, AiServiceErrorKind] = {
    401: AiServiceErrorKind.AUTH,
    403: AiServiceErrorKind.AUTH,
    429: AiServiceErrorKind.RATE_LIMITED,
    504: AiServiceErrorKind.TIMEOUT,
}
# 依 ai_service error.code 細分（api spec §4.1）；沒列到的回落到 HTTP 狀態分類
_CODE_TO_KIND: dict[str, AiServiceErrorKind] = {
    "AUTH_REQUIRED": AiServiceErrorKind.AUTH,
    "FORBIDDEN": AiServiceErrorKind.AUTH,
    "ADMISSION_REJECTED": AiServiceErrorKind.RATE_LIMITED,
    "BUNDLE_NOT_RUNNABLE": AiServiceErrorKind.BUNDLE_NOT_RUNNABLE,
    "SCHEMA_VALIDATION_FAILED": AiServiceErrorKind.MODEL_OUTPUT_INVALID,
    "PROVIDER_TIMEOUT": AiServiceErrorKind.TIMEOUT,
    "PROVIDER_UNREACHABLE": AiServiceErrorKind.UPSTREAM,
    "PROVIDER_AUTH_REQUIRED": AiServiceErrorKind.UPSTREAM,
    "PROVIDER_NOT_CONFIGURED": AiServiceErrorKind.DEPLOYMENT,
    "TOOL_SCHEMA_MISMATCH": AiServiceErrorKind.DEPLOYMENT,
    "PROMPT_ASSET_MISMATCH": AiServiceErrorKind.DEPLOYMENT,
    "PROMPT_RENDERER_MISSING": AiServiceErrorKind.DEPLOYMENT,
    "PROMPT_VALIDATOR_MISSING": AiServiceErrorKind.DEPLOYMENT,
    "BUNDLE_DECLARATION_CONFLICT": AiServiceErrorKind.DEPLOYMENT,
    "EMBEDDING_DIM_MISMATCH": AiServiceErrorKind.DEPLOYMENT,
    "TOOL_OUTPUT_SCHEMA_MISMATCH": AiServiceErrorKind.DEPLOYMENT,
    "FLOW_RUNTIME_ERROR": AiServiceErrorKind.DEPLOYMENT,
}

# ai_service 錯誤碼的格式（api spec §4.1：大寫 snake case）。不合格式的值不進 log／provenance。
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
UNKNOWN_UPSTREAM_CODE = "UNKNOWN"
RUNNABLE_BUNDLE_STATUSES = frozenset({"shadow", "active"})
MAX_PROVENANCE_FIELD_LEN = 128
_SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9._:/@+\-]{1,128}$")
MAX_RETRY_AFTER_S = 30.0


@dataclass(frozen=True)
class CompletionProvenance:
    """ai_service 回應的 `provenance`（`ProvenanceSummary`；去敏版本）。"""

    run_id: str
    bundle_code: str
    bundle_status: str
    model_requested: str
    model_served: str
    prompt_variant: str | None
    prompt_version: str | None
    retry_count: int


@dataclass(frozen=True)
class CompletionResult:
    content: dict[str, Any]
    provenance: CompletionProvenance
    request_id: str
    latency_ms: float
    attempts: int


class CircuitBreaker:
    def __init__(self, *, threshold: int = 5, cooldown_s: float = 30.0, clock=time.monotonic) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    def allow(self) -> bool:
        """關閉時放行；開路時冷卻期內拒絕；冷卻期過後只放一個試探請求（half-open）。"""
        if self._opened_at is None:
            return True
        if self._probe_in_flight or self._clock() - self._opened_at < self._cooldown_s:
            return False
        self._probe_in_flight = True
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._probe_in_flight = False

    def record_failure(self) -> None:
        self._failures += 1
        if self._probe_in_flight or self._failures >= self._threshold:
            self._opened_at = self._clock()  # 試探失敗＝重新開路，冷卻期重算
        self._probe_in_flight = False

    def record_neutral(self) -> None:
        """不代表服務健康與否的結果（呼叫端錯、模型輸出錯）：試探結束但不改變開路狀態。"""
        if self._probe_in_flight:
            self._probe_in_flight = False
            self._opened_at = self._clock()

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


def _parse_retry_after(raw: str | None) -> float | None:
    try:
        value = float(raw) if raw is not None else None
    except ValueError:
        return None
    if value is None or not math.isfinite(value):
        return None
    return min(max(0.0, value), MAX_RETRY_AFTER_S)


def _safe_code(raw: object) -> str | None:
    if raw is None:
        return None
    return raw if isinstance(raw, str) and _CODE_RE.fullmatch(raw) else UNKNOWN_UPSTREAM_CODE


def _safe_text(raw: object, *, required: bool) -> str | None:
    """provenance 欄位：只接受短的識別字元；不合格 → 必填者判契約不符，選填者記 None。"""
    if raw is None and not required:
        return None
    if isinstance(raw, str) and _SAFE_TEXT_RE.fullmatch(raw):
        return raw
    if required:
        raise ValueError("provenance field")
    return None


def _error_from_response(status: int, body: bytes, headers: httpx.Headers) -> AiServiceError:
    code: object = None
    try:
        parsed = json.loads(body)
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict) and "code" in err:
            code = err["code"]  # 型別與格式由下面的 _safe_code 驗
    except (ValueError, UnicodeDecodeError, RecursionError):
        code = None  # 純文字 500、深層巢狀等：只靠 HTTP 狀態分類
    safe = _safe_code(code)
    kind = _CODE_TO_KIND.get(safe or "") or _STATUS_TO_KIND.get(status)
    if kind is None:
        kind = AiServiceErrorKind.UPSTREAM if status >= 500 else AiServiceErrorKind.REQUEST_REJECTED
    return AiServiceError(
        kind,
        upstream_code=safe,
        http_status=status,
        retry_after_s=_parse_retry_after(headers.get("retry-after")),
    )


def _parse_success(body: bytes, *, expected_bundle: str) -> tuple[dict[str, Any], CompletionProvenance]:
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or data.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("contract_version")
        content = data["content"]
        p = data["provenance"]
        if not isinstance(content, dict) or not isinstance(p, dict):
            raise ValueError("shape")
        retry_count = p.get("retry_count", 0)
        if isinstance(retry_count, bool) or not isinstance(retry_count, int) or not 0 <= retry_count <= 100:
            raise ValueError("retry_count")
        prov = CompletionProvenance(
            run_id=str(_safe_text(p.get("run_id"), required=True)),
            bundle_code=str(_safe_text(p.get("bundle_code"), required=True)),
            bundle_status=str(_safe_text(p.get("bundle_status"), required=True)),
            model_requested=str(_safe_text(p.get("model_requested"), required=True)),
            model_served=str(_safe_text(p.get("model_served"), required=True)),
            prompt_variant=_safe_text(p.get("prompt_variant"), required=False),
            prompt_version=_safe_text(p.get("prompt_version"), required=False),
            retry_count=retry_count,
        )
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, RecursionError) as exc:
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH) from exc
    # 跑的必須是我們要的 bundle，且是可執行狀態——否則就是上游路由或狀態出錯
    if prov.bundle_code != expected_bundle:
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="BUNDLE_MISMATCH")
    if prov.bundle_status not in RUNNABLE_BUNDLE_STATUSES:
        raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="BUNDLE_STATUS_UNEXPECTED")
    return content, prov


class AiServiceClient:
    def __init__(
        self,
        config: AiServiceConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Resolver = default_resolver,
        breaker: CircuitBreaker | None = None,
        sleep=asyncio.sleep,
        jitter=random.random,
    ) -> None:
        self._config = config
        self._transport = transport
        self._resolver = resolver
        self._breaker = breaker or CircuitBreaker()
        self._sleep = sleep
        self._jitter = jitter

    @property
    def breaker(self) -> CircuitBreaker:
        return self._breaker

    def _headers(self, request_id: str) -> dict[str, str]:
        key = self._config.key
        if key is None:
            raise AiServiceError(AiServiceErrorKind.DISABLED, upstream_code="incomplete_config")
        return {
            **self._config.identity_headers(),
            "X-AI-Service-Key": key.reveal(),
            "X-Request-Id": request_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _post_once(
        self, body: dict[str, Any], request_id: str, budget_s: float
    ) -> tuple[dict[str, Any], CompletionProvenance]:
        cfg = self._config
        assert cfg.base_url is not None
        url = cfg.base_url.rstrip("/") + ENDPOINT_PATH
        body = {**body, "deadline_ms": max(0, int(budget_s * 1000))}
        try:
            # 單一總時限涵蓋 DNS 檢查與 HTTP（避免兩段各拿一整份預算）
            async with asyncio.timeout(budget_s):
                # DNS 解析是同步呼叫：丟到 thread，避免慢 DNS 卡住 event loop
                await asyncio.to_thread(
                    validate_target,
                    cfg.base_url,
                    cfg.allowed_hosts,
                    allow_plaintext=cfg.allow_plaintext,
                    resolver=self._resolver,
                )
                async with httpx.AsyncClient(
                    timeout=budget_s,
                    transport=self._transport,
                    trust_env=False,
                    follow_redirects=False,
                ) as client:
                    async with client.stream("POST", url, json=body, headers=self._headers(request_id)) as resp:
                        chunks: list[bytes] = []
                        size = 0
                        async for chunk in resp.aiter_bytes():
                            size += len(chunk)
                            if size > MAX_RESPONSE_BYTES:
                                raise AiServiceError(AiServiceErrorKind.RESPONSE_TOO_LARGE, http_status=resp.status_code)
                            chunks.append(chunk)
                        raw = b"".join(chunks)
                        status, headers = resp.status_code, resp.headers
        except AiServiceError:
            raise
        except TimeoutError as exc:
            raise AiServiceError(AiServiceErrorKind.TIMEOUT) from exc
        except httpx.TimeoutException as exc:
            raise AiServiceError(AiServiceErrorKind.TIMEOUT) from exc
        except httpx.TransportError as exc:
            raise AiServiceError(AiServiceErrorKind.UNREACHABLE) from exc
        except httpx.InvalidURL as exc:
            raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="unparsable_url") from exc
        except httpx.HTTPError as exc:
            # 例如 DecodingError（宣稱 gzip 但本文不是）：回應本身壞了
            raise AiServiceError(AiServiceErrorKind.CONTRACT_MISMATCH, upstream_code="UNDECODABLE_RESPONSE") from exc
        if 300 <= status < 400:
            raise AiServiceError(AiServiceErrorKind.UNREACHABLE, upstream_code="redirect_refused", http_status=status)
        if status != 200:
            raise _error_from_response(status, raw, headers)
        return _parse_success(raw, expected_bundle=cfg.bundle_code)

    async def structured_completion(
        self,
        *,
        variables: dict[str, Any],
        json_schema: dict[str, Any],
        prompt_variant: str | None,
        lane: str,
        request_id: str,
    ) -> CompletionResult:
        if lane not in LANES:
            raise ValueError(f"unknown lane: {lane}")
        cfg = self._config
        if not (math.isfinite(cfg.timeout_s) and cfg.timeout_s > 0):
            # 正式路徑由 validate_config 擋；直接建 client 時也不得在取得熔斷許可後才失敗
            raise AiServiceError(AiServiceErrorKind.MISCONFIGURED, upstream_code="bad_limits")
        body = {
            "contract_version": CONTRACT_VERSION,
            "bundle_code": cfg.bundle_code,
            "variables": variables,
            "prompt_variant": prompt_variant,
            "json_schema": json_schema,
            "lane": lane,
            "deadline_ms": int(cfg.timeout_s * 1000),  # 每次嘗試前改成剩餘預算
        }
        if not self._breaker.allow():
            raise AiServiceError(AiServiceErrorKind.CIRCUIT_OPEN)
        try:
            return await self._call_with_retries(body, request_id)
        except AiServiceError:
            raise  # 已在 _call_with_retries 記錄熔斷結果
        except BaseException:
            # 取消（使用者斷線、外層 timeout）或非預期例外：熔斷器沒有得到結論。不處理的話
            # half-open 試探旗標會永遠卡住，整合停擺到重啟為止。
            self._breaker.record_neutral()
            raise

    async def _call_with_retries(self, body: dict[str, Any], request_id: str) -> CompletionResult:
        cfg = self._config
        t0 = time.perf_counter()
        deadline = t0 + cfg.timeout_s
        attempt = 0
        while True:
            attempt += 1
            remaining = deadline - time.perf_counter()
            try:
                if remaining <= 0:
                    raise AiServiceError(AiServiceErrorKind.TIMEOUT, upstream_code="BUDGET_EXHAUSTED")
                content, prov = await self._post_once(body, request_id, remaining)
            except AiServiceError as err:
                retry = err.kind in RETRYABLE_KINDS and attempt <= cfg.max_retries
                delay = 0.0
                if retry:
                    base = err.retry_after_s if err.retry_after_s is not None else 0.5 * (2 ** (attempt - 1))
                    delay = base + self._jitter() * 0.25
                    retry = time.perf_counter() + delay < deadline
                if not retry:
                    if err.kind in CIRCUIT_COUNTED_KINDS:
                        self._breaker.record_failure()
                    else:
                        self._breaker.record_neutral()
                    logger.warning("ai_service call failed: %s (request_id=%s, attempts=%d)", err, request_id, attempt)
                    raise
                await self._sleep(delay)
                continue
            self._breaker.record_success()
            return CompletionResult(
                content=content,
                provenance=prov,
                request_id=request_id,
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                attempts=attempt,
            )
