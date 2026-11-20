"""MOST 端的外送守門：並行上限、每人每分鐘、每日預算、相同請求合併（ADR-037 D8）。

`GuardedWiParser` 包住任何 `WiParserPort`（通常是 `AiServiceWiParser`），本身也實作同一個 port。
所有限制都**只在 MOST 程序內**計數（單程序前提；ADR-037 D8、實作計畫 S5 另議多 worker）。

逐筆處理順序：

0. **不外送的請求不佔配額**：超長語句由守門直接回 `failed`＋`text_too_long_not_sent`（D6），不取並行許可、不扣預算。
   `context` 有白名單外的鍵是呼叫端 bug，在任何計數之前就 `ValueError`。
1. **相同請求合併（single-flight）**：key＝(bundle、scope、語言、lane、sha256(allow-list、context、語句))。
   同 key 已有請求在途 → 等它的結果，不再外送、也不計配額。只合併「在途」的請求；完成後不快取
   （持久快取由 `ai_parse_runs.input_hash` 負責，S3）。
   **只共用真的外送後的結果**（含上游失敗）。領頭者自己的處境——並行等不到許可、配額被拒、被取消、
   內層拋例外——不傳給等待者；等待者重來（可能成為新的領頭者）。等待者的 provenance 不帶
   `run_id`／`request_id`（那是領頭者那次外送的對帳 id），改記 `shared_run_id`。
2. **並行上限**（依 lane 各一個 semaphore，批量不會卡住互動）：等待時間在 client 的總時限之外，
   所以另設取得上限（`acquire_timeout_s`），等不到 → `QUOTA_EXCEEDED`，不讓請求無限排隊。
   這個期限從請求進來就起算（等待者重來時用剩餘時間），同一個 key 的重試鏈不會把等待時間疊加。
3. 拿到許可後才扣 **每日預算**（UTC 日）與 **每人每分鐘**（滑動 60 秒，單調時鐘）：超過 → 該筆
   `failed`＋`QUOTA_EXCEEDED`，不外送。預算只計**真的外送**的請求。

不拋例外：所有拒絕都轉成該筆 `failed`（ADR-037 D2），呼叫端走 rule_based。
`actor`／`scope` 缺漏、`context` 含白名單外的鍵是呼叫端 bug → `ValueError`
（不能讓「沒有身分」變成「不受配額限制」）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import deque
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Literal

from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.ports import (
    CONTEXT_WHITELIST,
    AllowLists,
    WiParseRequest,
    WiParseResult,
    WiParserPort,
)
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS

Lane = Literal["interactive", "batch"]

_WINDOW_S = 60.0
# 記錄的觸發者超過這個數就掃掉已過期的，避免 `_per_user` 隨時間只增不減
_SWEEP_ABOVE = 1024


def _utc_day(now: float) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%d")


def _norm_actor(actor: str) -> str:
    """配額以正規化後的觸發者計：大小寫或前後空白不同不能各拿一份額度。"""
    return actor.strip().casefold()


class GuardedWiParser:
    def __init__(
        self,
        inner: WiParserPort,
        *,
        bundle_code: str,
        concurrency: dict[Lane, int],
        per_user_per_minute: int,
        daily_budget: int,
        acquire_timeout_s: float = 10.0,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if set(concurrency) != {"interactive", "batch"} or any(n < 1 for n in concurrency.values()):
            raise ValueError("concurrency must define interactive and batch lanes, each >= 1")
        if per_user_per_minute < 1 or daily_budget < 1:
            raise ValueError("per_user_per_minute and daily_budget must be >= 1")
        if acquire_timeout_s < 0:
            raise ValueError("acquire_timeout_s must be >= 0")
        self._inner = inner
        self._bundle_code = bundle_code
        self._semaphores = {lane: asyncio.Semaphore(n) for lane, n in concurrency.items()}
        self._per_user_per_minute = per_user_per_minute
        self._daily_budget = daily_budget
        self._acquire_timeout_s = acquire_timeout_s
        self._clock = clock  # 牆上時鐘：只用來決定 UTC 日
        self._monotonic = monotonic  # 單調時鐘：每人視窗，不受校時往回跳影響
        self._per_user: dict[str, deque[float]] = {}
        self._day: str | None = None
        self._day_count = 0
        # 在途結果：None＝領頭者的結果不可共用（本地拒絕、取消、例外），等待者要自己重來
        self._in_flight: dict[tuple[str, str, str, str, str], asyncio.Future[WiParseResult | None]] = {}

    # ── 配額 ────────────────────────────────────────────────────────────

    def _take_quota(self, actor: str) -> str | None:
        """成功回 None 並記一筆；超過回拒絕原因。`actor` 須已正規化。"""
        day = _utc_day(self._clock())
        # 只在日期「往後」時歸零；校時把牆上時鐘往回撥不能重置當日預算（YYYY-MM-DD 可直接比大小）
        if self._day is None or day > self._day:
            self._day, self._day_count = day, 0
        if self._day_count >= self._daily_budget:
            return "DAILY_BUDGET_EXHAUSTED"
        now = self._monotonic()
        if len(self._per_user) > _SWEEP_ABOVE:
            self._sweep(now)
        window = self._per_user.get(actor)
        if window is None:
            window = deque()
        while window and now - window[0] >= _WINDOW_S:
            window.popleft()
        if len(window) >= self._per_user_per_minute:
            self._per_user[actor] = window
            return "PER_USER_RATE_LIMITED"
        window.append(now)
        self._per_user[actor] = window
        self._day_count += 1
        return None

    def _sweep(self, now: float) -> None:
        for actor in [a for a, w in self._per_user.items() if not w or now - w[-1] >= _WINDOW_S]:
            del self._per_user[actor]

    @property
    def daily_count(self) -> int:
        return self._day_count

    # ── port ────────────────────────────────────────────────────────────

    async def parse(
        self,
        requests: Sequence[WiParseRequest],
        *,
        allow_lists: AllowLists,
        lane: Lane,
    ) -> list[WiParseResult]:
        for req in requests:
            if not _norm_actor(req.actor):
                raise ValueError("WiParseRequest.actor is required for MOST-side quotas (ADR-037 D8)")
            if not req.scope:
                raise ValueError("WiParseRequest.scope is required for single-flight isolation (ADR-037 D8)")
            extra = set(req.context) - CONTEXT_WHITELIST
            if extra:
                raise ValueError(f"context keys not in ADR-037 D7 whitelist: {sorted(extra)}")
        return [await self._parse_one(req, allow_lists, lane) for req in requests]

    def _key(self, req: WiParseRequest, allow_lists: AllowLists, lane: Lane) -> tuple[str, str, str, str, str]:
        # allow-list 與 context 也要進 key：結果是用領頭者的 allow-list 篩出來的，
        # 不能給 allow-list／context 不同的請求用
        allow = json.dumps({k: sorted(v) for k, v in allow_lists.items()}, sort_keys=True, ensure_ascii=False)
        ctx = json.dumps(sorted(req.context.items()), ensure_ascii=False)
        digest = hashlib.sha256(f"{allow}\x00{ctx}\x00{req.wi_statement}".encode("utf-8")).hexdigest()
        return (self._bundle_code, req.scope, req.source_lang, lane, digest)

    @staticmethod
    def _as_follower(shared: WiParseResult, item_id: str) -> WiParseResult:
        """共用結果給等待者：換成自己的 item_id；run_id／request_id 屬於領頭者那一次外送，不能掛在別人名下。"""
        prov = dict(shared.provenance) if shared.provenance is not None else None
        if prov is not None:
            leader_run = prov.pop("run_id", None)
            prov.pop("request_id", None)
            if leader_run is not None:
                prov["shared_run_id"] = leader_run
        return shared.model_copy(update={"item_id": item_id, "provenance": prov})

    async def _parse_one(self, req: WiParseRequest, allow_lists: AllowLists, lane: Lane) -> WiParseResult:
        if len(req.wi_statement) > MAX_PARSE_TEXT_CHARS:
            # 不外送（D6）：守門自己回 failed，不依賴內層是誰；不佔並行許可、不扣配額，也不對整段超長字串做 hash
            return WiParseResult(item_id=req.item_id, status="failed", issues=("text_too_long_not_sent",))

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._acquire_timeout_s
        key = self._key(req, allow_lists, lane)
        while True:
            existing = self._in_flight.get(key)
            if existing is None:
                break
            shared = await asyncio.shield(existing)
            if shared is not None:
                return self._as_follower(shared, req.item_id)
            # 領頭者被拒絕、取消或出錯：那是領頭者自己的處境，換我重來（可能成為新的領頭者）

        future: asyncio.Future[WiParseResult | None] = loop.create_future()
        self._in_flight[key] = future
        shareable: WiParseResult | None = None
        try:
            result, is_sendable = await self._send(req, allow_lists, lane, deadline)
            if is_sendable:
                shareable = result
            return result
        finally:
            # 取消或例外時 shareable 仍是 None：等待者不繼承，也不會永遠等下去
            if not future.done():
                future.set_result(shareable)
            self._in_flight.pop(key, None)

    async def _send(
        self, req: WiParseRequest, allow_lists: AllowLists, lane: Lane, deadline: float
    ) -> tuple[WiParseResult, bool]:
        """回傳 (結果, 是否為真的外送結果)。本地拒絕（並行、配額）不外送，也不可共用給別人。"""
        semaphore = self._semaphores[lane]
        remaining = max(0.0, deadline - asyncio.get_running_loop().time())
        try:
            async with asyncio.timeout(remaining):
                await semaphore.acquire()
        except TimeoutError:
            return self._refused(req, "LOCAL_CONCURRENCY_LIMIT"), False
        try:
            # 拿到並行許可之後才扣配額：等不到許可的請求不消耗預算
            refusal = self._take_quota(_norm_actor(req.actor))
            if refusal is not None:
                return self._refused(req, refusal), False
            (result,) = await self._inner.parse([req], allow_lists=allow_lists, lane=lane)
        finally:
            semaphore.release()
        return result, True

    @staticmethod
    def _refused(req: WiParseRequest, code: str) -> WiParseResult:
        return WiParseResult(
            item_id=req.item_id,
            status="failed",
            error_kind=AiServiceErrorKind.QUOTA_EXCEEDED,
            provenance={"upstream_code": code},
        )
