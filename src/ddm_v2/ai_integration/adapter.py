"""`AiServiceWiParser`：`WiParserPort` 的第一個實作（逐句呼叫 structured-completion；ADR-037 D2）。

ai_service 的批量 flow（`wi_motion_parse`）落地後，新增一個 flow adapter 實作同一個 port，
本檔不動。

降級語意：任何失敗（設定、連線、逾時、准入、模型輸出、契約不符）都轉成該筆
`status="failed"`＋`error_kind`，**不拋例外**，呼叫端照舊走 rule_based（ADR-037 D2）。
會拋的只有 MOST 自己的錯誤，刻意不吞：

- context 帶了白名單外的鍵（呼叫端 bug）→ `ValueError`；
- schema 複本 hash 不符（部署的檔案被改過）→ `RuntimeError`（fail-fast）。

S3 的呼叫端（`wi_ai_service`）要在外層再包一層，把這兩種也轉成「AI 不可用、走 rule_based」，
同時記 ERROR log——對使用者降級，對維運大聲失敗。
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Literal

from ddm_v2.ai_integration.client import AiServiceClient
from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind
from ddm_v2.ai_integration.mapper import map_content
from ddm_v2.ai_integration.ports import (
    CONTEXT_WHITELIST,
    AllowLists,
    WiParseRequest,
    WiParseResult,
)
from ddm_v2.ai_integration.schema import wi_motion_parse_schema
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS

logger = logging.getLogger(__name__)


class AiServiceWiParser:
    def __init__(self, client: AiServiceClient) -> None:
        self._client = client

    async def parse(
        self,
        requests: Sequence[WiParseRequest],
        *,
        allow_lists: AllowLists,
        lane: Literal["interactive", "batch"],
    ) -> list[WiParseResult]:
        for req in requests:
            extra = set(req.context) - CONTEXT_WHITELIST
            if extra:
                raise ValueError(f"context keys not in ADR-037 D7 whitelist: {sorted(extra)}")
        schema = wi_motion_parse_schema()
        return [await self._parse_one(req, schema, allow_lists, lane) for req in requests]

    async def _parse_one(
        self,
        req: WiParseRequest,
        schema: dict,
        allow_lists: AllowLists,
        lane: Literal["interactive", "batch"],
    ) -> WiParseResult:
        if len(req.wi_statement) > MAX_PARSE_TEXT_CHARS:
            # ADR-037 D6：超長語句不外送（與 import／parse_job 的既有規則同一個常數）
            return WiParseResult(item_id=req.item_id, status="failed", issues=("text_too_long_not_sent",))
        request_id = str(uuid.uuid4())
        try:
            completion = await self._client.structured_completion(
                variables={"wi_statement": req.wi_statement, "source_lang": req.source_lang, "context": dict(req.context)},
                json_schema=schema,
                prompt_variant=req.source_lang,
                lane=lane,
                request_id=request_id,
            )
            motions, issues = map_content(completion.content, allow_lists)
        except AiServiceError as err:
            return WiParseResult(
                item_id=req.item_id,
                status="failed",
                error_kind=err.kind,
                provenance={"request_id": request_id, "upstream_code": err.upstream_code, "http_status": err.http_status},
            )
        p = completion.provenance
        return WiParseResult(
            item_id=req.item_id,
            status="ok",
            motions=tuple(motions),
            issues=tuple(issues),
            provenance={
                "request_id": request_id,
                "run_id": p.run_id,
                "bundle_code": p.bundle_code,
                "bundle_status": p.bundle_status,
                "model_served": p.model_served,
                "prompt_variant": p.prompt_variant,
                "prompt_version": p.prompt_version,
                "retry_count": p.retry_count,
                "attempts": completion.attempts,
                "latency_ms": completion.latency_ms,
            },
        )


class DisabledWiParser:
    """開關關閉或設定不合法時使用：每筆都回 failed，不做任何網路呼叫。"""

    def __init__(self, kind: AiServiceErrorKind = AiServiceErrorKind.DISABLED) -> None:
        self._kind = kind

    async def parse(
        self,
        requests: Sequence[WiParseRequest],
        *,
        allow_lists: AllowLists,  # noqa: ARG002
        lane: Literal["interactive", "batch"],  # noqa: ARG002
    ) -> list[WiParseResult]:
        return [WiParseResult(item_id=r.item_id, status="failed", error_kind=self._kind) for r in requests]


def build_wi_parser(config=None, *, resolver=None, transport=None):
    """依部署設定建 parser。設定不合法或關閉時回 `DisabledWiParser`，並記一次 WARNING（不含金鑰）。

    S3 起由 `wi_ai_service` 在啟動時呼叫一次；S2 尚無呼叫端。
    """
    from ddm_v2.ai_integration.config import default_resolver, load_config, validate_config

    res = resolver or default_resolver
    try:
        cfg = config if config is not None else load_config()
        validate_config(cfg, resolver=res)
    except AiServiceError as err:
        if err.kind is not AiServiceErrorKind.DISABLED:
            logger.warning("ai_service integration disabled: %s", err)
        return DisabledWiParser(err.kind)
    return AiServiceWiParser(AiServiceClient(cfg, resolver=res, transport=transport))
