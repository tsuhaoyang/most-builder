"""`FakeWiParser`：給下游（S3 的 wi_ai_service、S4 審核）單元測試用的 in-process 假 parser。

不走 HTTP、不經 client；回應仍走真的 `map_content`，所以 allow-list 與上限檢查照樣生效。
要測 HTTP 層（錯誤信封、逾時、redirect、回應大小）請用 `tests/fakes/ai_service_app.py`
（真的 ASGI app，經 httpx transport 呼叫）。
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

from ddm_v2.ai_integration.errors import AiServiceError, AiServiceErrorKind
from ddm_v2.ai_integration.mapper import map_content
from ddm_v2.ai_integration.ports import AllowLists, WiParseRequest, WiParseResult

ContentFn = Callable[[WiParseRequest], dict[str, Any] | AiServiceErrorKind]


class FakeWiParser:
    def __init__(self, content_for: ContentFn) -> None:
        self._content_for = content_for
        self.calls: list[tuple[str, str]] = []

    async def parse(
        self,
        requests: Sequence[WiParseRequest],
        *,
        allow_lists: AllowLists,
        lane: Literal["interactive", "batch"],
    ) -> list[WiParseResult]:
        out: list[WiParseResult] = []
        for req in requests:
            self.calls.append((req.item_id, lane))
            produced = self._content_for(req)
            if isinstance(produced, AiServiceErrorKind):
                out.append(WiParseResult(item_id=req.item_id, status="failed", error_kind=produced))
                continue
            try:
                motions, issues = map_content(produced, allow_lists)
            except AiServiceError as err:
                out.append(WiParseResult(item_id=req.item_id, status="failed", error_kind=err.kind))
                continue
            out.append(
                WiParseResult(
                    item_id=req.item_id,
                    status="ok",
                    motions=tuple(motions),
                    issues=tuple(issues),
                    provenance={"run_id": f"fake-{req.item_id}", "bundle_code": "fake"},
                )
            )
        return out
