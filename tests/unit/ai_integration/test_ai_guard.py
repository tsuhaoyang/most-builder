"""ai_integration.guard：MOST 端並行上限、每人每分鐘、每日預算、相同請求合併（ADR-037 D8）。"""
from __future__ import annotations

import asyncio
from collections.abc import Sequence

import pytest

from ddm_v2.ai_integration.errors import AiServiceErrorKind
from ddm_v2.ai_integration.guard import GuardedWiParser
from ddm_v2.ai_integration.ports import AllowLists, WiParseRequest, WiParseResult
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS

pytestmark = pytest.mark.unit

ALLOW: AllowLists = {}


class _Inner:
    """可控的內層 parser：記錄外送次數與最大並行數；`gate` 用來讓請求停在途中。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.active = 0
        self.max_active = 0
        self.gate: asyncio.Event | None = None
        self.raise_exc: BaseException | None = None

    async def parse(self, requests: Sequence[WiParseRequest], *, allow_lists: AllowLists, lane: str) -> list[WiParseResult]:
        (req,) = requests
        self.calls.append((req.item_id, lane))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.gate is not None:
                await self.gate.wait()
            if self.raise_exc is not None:
                raise self.raise_exc
            return [WiParseResult(item_id=req.item_id, status="ok", provenance={"run_id": f"run-{req.item_id}"})]
        finally:
            self.active -= 1


def _guard(inner: _Inner, *, now=None, interactive=2, batch=1, per_min=30, daily=2000, acquire=1.0) -> GuardedWiParser:
    clock = now or [1_000_000.0]
    return GuardedWiParser(
        inner,
        bundle_code="b1",
        concurrency={"interactive": interactive, "batch": batch},
        per_user_per_minute=per_min,
        daily_budget=daily,
        acquire_timeout_s=acquire,
        clock=lambda: clock[0],
        monotonic=lambda: clock[0],
    )


def _req(item_id: str, text: str = "拿起DIMM", *, actor: str = "u1", scope: str = "s1", lang: str = "zh") -> WiParseRequest:
    return WiParseRequest(item_id=item_id, wi_statement=text, source_lang=lang, actor=actor, scope=scope)


async def test_missing_actor_is_a_programming_error():
    with pytest.raises(ValueError):
        await _guard(_Inner()).parse([WiParseRequest(item_id="x", wi_statement="t", source_lang="zh")], allow_lists=ALLOW, lane="interactive")


async def test_concurrent_identical_requests_are_sent_once():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    t1 = asyncio.ensure_future(g.parse([_req("a")], allow_lists=ALLOW, lane="interactive"))
    t2 = asyncio.ensure_future(g.parse([_req("b")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    (ra,), (rb,) = await asyncio.gather(t1, t2)
    assert len(inner.calls) == 1, "相同請求在途時只外送一次"
    assert (ra.item_id, rb.item_id) == ("a", "b"), "合併後各自保留自己的 item_id"
    assert ra.provenance == {"run_id": "run-a"}
    assert rb.provenance == {"shared_run_id": "run-a"}, "等待者的稽核紀錄不能掛在領頭者的 run_id 名下"
    assert g.daily_count == 1, "合併的請求不計配額"


@pytest.mark.parametrize(
    "other",
    [
        _req("b", scope="s2"),  # 不同 site 不合併
        _req("b", lang="en"),
        _req("b", text="拿起螺絲"),
    ],
)
async def test_requests_differing_in_scope_language_or_text_are_not_merged(other: WiParseRequest):
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    t1 = asyncio.ensure_future(g.parse([_req("a")], allow_lists=ALLOW, lane="interactive"))
    t2 = asyncio.ensure_future(g.parse([other], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    await asyncio.gather(t1, t2)
    assert len(inner.calls) == 2


async def test_completed_requests_are_not_cached():
    inner = _Inner()
    g = _guard(inner)
    await g.parse([_req("a")], allow_lists=ALLOW, lane="interactive")
    await g.parse([_req("b")], allow_lists=ALLOW, lane="interactive")
    assert len(inner.calls) == 2, "只合併在途；持久快取由 ai_parse_runs 負責"


async def test_per_lane_concurrency_is_bounded_and_batch_does_not_block_interactive():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, interactive=2, batch=1)
    batch = [asyncio.ensure_future(g.parse([_req(f"b{i}", f"批量{i}")], allow_lists=ALLOW, lane="batch")) for i in range(3)]
    inter = [asyncio.ensure_future(g.parse([_req(f"i{i}", f"互動{i}")], allow_lists=ALLOW, lane="interactive")) for i in range(2)]
    await asyncio.sleep(0.02)
    lanes = [lane for _, lane in inner.calls]
    assert lanes.count("batch") == 1, "batch lane 並行上限 1"
    assert lanes.count("interactive") == 2, "批量排隊時互動照樣送出"
    assert inner.max_active == 3
    inner.gate.set()
    await asyncio.gather(*batch, *inter)
    assert len(inner.calls) == 5


async def test_waiting_too_long_for_a_slot_is_refused_and_does_not_consume_budget():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, batch=1, acquire=0.05)
    first = asyncio.ensure_future(g.parse([_req("b0", "一")], allow_lists=ALLOW, lane="batch"))
    await asyncio.sleep(0.01)
    (second,) = await g.parse([_req("b1", "二")], allow_lists=ALLOW, lane="batch")
    assert second.status == "failed" and second.error_kind is AiServiceErrorKind.QUOTA_EXCEEDED
    assert second.provenance == {"upstream_code": "LOCAL_CONCURRENCY_LIMIT"}
    assert g.daily_count == 1, "等不到許可的請求不扣預算"
    inner.gate.set()
    await first


async def test_per_user_rate_limit_slides_over_sixty_seconds():
    now = [1_000_000.0]
    inner = _Inner()
    g = _guard(inner, now=now, per_min=2)
    for i in range(2):
        (r,) = await g.parse([_req(f"a{i}", f"句{i}")], allow_lists=ALLOW, lane="interactive")
        assert r.status == "ok"
    (blocked,) = await g.parse([_req("a2", "句2")], allow_lists=ALLOW, lane="interactive")
    assert blocked.error_kind is AiServiceErrorKind.QUOTA_EXCEEDED
    assert blocked.provenance == {"upstream_code": "PER_USER_RATE_LIMITED"}
    (other_user,) = await g.parse([_req("x", "句3", actor="u2")], allow_lists=ALLOW, lane="interactive")
    assert other_user.status == "ok", "配額以觸發者分開計"
    now[0] += 60.0
    (again,) = await g.parse([_req("a3", "句4")], allow_lists=ALLOW, lane="interactive")
    assert again.status == "ok"
    assert len(inner.calls) == 4


async def test_daily_budget_stops_sending_and_resets_on_the_next_utc_day():
    now = [1_000_000.0]
    inner = _Inner()
    g = _guard(inner, now=now, daily=2, per_min=100)
    for i in range(2):
        await g.parse([_req(f"a{i}", f"句{i}", actor=f"u{i}")], allow_lists=ALLOW, lane="batch")
    (blocked,) = await g.parse([_req("a2", "句2", actor="u9")], allow_lists=ALLOW, lane="batch")
    assert blocked.provenance == {"upstream_code": "DAILY_BUDGET_EXHAUSTED"}
    assert len(inner.calls) == 2
    now[0] += 86_400.0
    (next_day,) = await g.parse([_req("a3", "句3")], allow_lists=ALLOW, lane="batch")
    assert next_day.status == "ok"


async def test_cancelled_leader_does_not_fail_other_users_waiting_on_the_same_key():
    """領頭者被取消只是它自己的事：等同一個 key 的請求要重新外送，不能繼承 CancelledError。"""
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    leader = asyncio.ensure_future(g.parse([_req("a", actor="u1")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    follower = asyncio.ensure_future(g.parse([_req("b", actor="u2")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    leader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await leader
    await asyncio.sleep(0.01)
    inner.gate.set()
    (rb,) = await asyncio.wait_for(follower, timeout=1.0)
    assert rb.status == "ok" and rb.item_id == "b"
    assert len(inner.calls) == 2, "等待者自己重新外送"
    assert g._in_flight == {}


async def test_inner_exception_in_leader_is_not_inherited_by_followers():
    inner = _Inner()
    inner.gate = asyncio.Event()
    inner.raise_exc = RuntimeError("boom")
    g = _guard(inner)
    leader = asyncio.ensure_future(g.parse([_req("a", actor="u1")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    follower = asyncio.ensure_future(g.parse([_req("b", actor="u2")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    with pytest.raises(RuntimeError):
        await leader
    inner.raise_exc = None
    (rb,) = await asyncio.wait_for(follower, timeout=1.0)
    assert rb.status == "ok"


async def test_followers_retry_when_leader_was_refused_locally():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, interactive=1, acquire=0.05)
    blocker = asyncio.ensure_future(g.parse([_req("z", "占位", actor="u9")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    leader = asyncio.ensure_future(g.parse([_req("a", actor="u1")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    follower = asyncio.ensure_future(g.parse([_req("b", actor="u2")], allow_lists=ALLOW, lane="interactive"))
    (ra,) = await leader  # 等不到並行許可 → 本地拒絕
    assert ra.provenance == {"upstream_code": "LOCAL_CONCURRENCY_LIMIT"}
    inner.gate.set()
    await blocker
    (rb,) = await asyncio.wait_for(follower, timeout=1.0)
    assert rb.status == "ok", "領頭者的並行拒絕不可傳給等待者"


async def test_different_allow_lists_are_not_merged():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    t1 = asyncio.ensure_future(g.parse([_req("a")], allow_lists={"slots": {"A1"}}, lane="interactive"))
    t2 = asyncio.ensure_future(g.parse([_req("b")], allow_lists={"slots": {"A3"}}, lane="interactive"))
    t3 = asyncio.ensure_future(g.parse([_req("c")], allow_lists={"slots": frozenset({"A1"})}, lane="interactive"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    await asyncio.gather(t1, t2, t3)
    assert len(inner.calls) == 2, "allow-list 不同不合併；內容相同（set／frozenset）照樣合併"


async def test_missing_scope_is_a_programming_error():
    with pytest.raises(ValueError, match="scope"):
        await _guard(_Inner()).parse(
            [WiParseRequest(item_id="x", wi_statement="t", source_lang="zh", actor="u1")], allow_lists=ALLOW, lane="interactive"
        )


async def test_cancelling_a_task_waiting_for_a_permit_does_not_leak_it():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, batch=1, acquire=5.0)
    holder = asyncio.ensure_future(g.parse([_req("h", "占位")], allow_lists=ALLOW, lane="batch"))
    await asyncio.sleep(0.01)
    waiter = asyncio.ensure_future(g.parse([_req("w", "等待")], allow_lists=ALLOW, lane="batch"))
    await asyncio.sleep(0.01)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    inner.gate.set()
    await holder
    (r,) = await asyncio.wait_for(g.parse([_req("n", "之後")], allow_lists=ALLOW, lane="batch"), timeout=1.0)
    assert r.status == "ok", "被取消的等待者不可吞掉許可"


async def test_semaphore_is_released_when_the_inner_parser_raises():
    inner = _Inner()
    inner.raise_exc = RuntimeError("schema hash mismatch")
    g = _guard(inner, batch=1)
    with pytest.raises(RuntimeError):
        await g.parse([_req("a")], allow_lists=ALLOW, lane="batch")
    inner.raise_exc = None
    (r,) = await g.parse([_req("b", "另一句")], allow_lists=ALLOW, lane="batch")
    assert r.status == "ok", "例外後許可必須歸還，否則 batch lane 永久卡住"


async def test_follower_provenance_drops_leader_request_and_run_ids():
    class _WithRequestId(_Inner):
        async def parse(self, requests, *, allow_lists, lane):  # type: ignore[override]
            (r,) = await super().parse(requests, allow_lists=allow_lists, lane=lane)
            return [r.model_copy(update={"provenance": {"run_id": "R1", "request_id": "Q1", "bundle_code": "b1"}})]

    inner = _WithRequestId()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    t1 = asyncio.ensure_future(g.parse([_req("a", actor="u1")], allow_lists=ALLOW, lane="interactive"))
    t2 = asyncio.ensure_future(g.parse([_req("b", actor="u2")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    (ra,), (rb,) = await asyncio.gather(t1, t2)
    assert ra.provenance == {"run_id": "R1", "request_id": "Q1", "bundle_code": "b1"}
    assert rb.provenance == {"bundle_code": "b1", "shared_run_id": "R1"}
    assert ra.provenance is not rb.provenance


async def test_cancelling_a_follower_does_not_affect_the_leader_or_other_followers():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    leader = asyncio.ensure_future(g.parse([_req("a", actor="u1")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    f1 = asyncio.ensure_future(g.parse([_req("b", actor="u2")], allow_lists=ALLOW, lane="interactive"))
    f2 = asyncio.ensure_future(g.parse([_req("c", actor="u3")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    f1.cancel()
    with pytest.raises(asyncio.CancelledError):
        await f1
    inner.gate.set()
    (ra,), (rc,) = await asyncio.gather(leader, f2)
    assert ra.status == rc.status == "ok"
    assert len(inner.calls) == 1
    assert g._in_flight == {}


async def test_retry_chain_does_not_stack_acquire_waits():
    """領頭者等不到並行許可而被拒時，同 key 的等待者依序重來，總等待仍以同一個期限為界。"""
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, interactive=1, acquire=0.1)
    blocker = asyncio.ensure_future(g.parse([_req("z", "占位", actor="u9")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    started = asyncio.get_running_loop().time()
    waiters = [
        asyncio.ensure_future(g.parse([_req(f"w{i}", actor=f"u{i}")], allow_lists=ALLOW, lane="interactive"))
        for i in range(5)
    ]
    results = [r for (r,) in await asyncio.gather(*waiters)]
    elapsed = asyncio.get_running_loop().time() - started
    assert all(r.provenance == {"upstream_code": "LOCAL_CONCURRENCY_LIMIT"} for r in results)
    assert elapsed < 0.25, f"5 個等待者不該疊加成 5×0.1 秒，實際 {elapsed:.2f}s"
    inner.gate.set()
    await blocker


async def test_too_long_statement_is_refused_by_the_guard_itself_without_quota_or_permits():
    inner = _Inner()
    g = _guard(inner, per_min=1, batch=1)
    long_text = "長" * (MAX_PARSE_TEXT_CHARS + 1)
    for i in range(3):
        (r,) = await g.parse([_req(f"l{i}", long_text)], allow_lists=ALLOW, lane="batch")
        assert r.status == "failed" and r.issues == ("text_too_long_not_sent",)
    assert inner.calls == [], "不依賴內層：守門自己就不外送"
    assert g.daily_count == 0 and g._per_user == {}
    (ok,) = await g.parse([_req("n", "正常")], allow_lists=ALLOW, lane="batch")
    assert ok.status == "ok" and g.daily_count == 1


async def test_statement_of_exactly_the_max_length_is_sent_and_counted():
    inner = _Inner()
    g = _guard(inner)
    (r,) = await g.parse([_req("e", "長" * MAX_PARSE_TEXT_CHARS)], allow_lists=ALLOW, lane="interactive")
    assert r.status == "ok" and len(inner.calls) == 1 and g.daily_count == 1


async def test_zero_acquire_budget_still_sends_when_a_permit_is_free_and_refuses_when_not():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner, interactive=1, acquire=0.0)
    first = asyncio.ensure_future(g.parse([_req("a", "一")], allow_lists=ALLOW, lane="interactive"))
    await asyncio.sleep(0.01)
    assert len(inner.calls) == 1, "許可空閒時 timeout(0) 不可誤判逾時"
    (second,) = await g.parse([_req("b", "二")], allow_lists=ALLOW, lane="interactive")
    assert second.provenance == {"upstream_code": "LOCAL_CONCURRENCY_LIMIT"}
    inner.gate.set()
    (ra,) = await first
    assert ra.status == "ok"


async def test_sweep_keeps_actors_still_inside_their_window():
    now = [1_000_000.0]
    inner = _Inner()
    g = _guard(inner, now=now, per_min=1, daily=10_000)
    await g.parse([_req("keep", "保留", actor="keeper")], allow_lists=ALLOW, lane="interactive")
    for i in range(1100):
        await g.parse([_req(f"a{i}", f"句{i}", actor=f"u{i}")], allow_lists=ALLOW, lane="interactive")
    # 此時已觸發過掃除；keeper 仍在 60 秒視窗內，不可被誤掃而多拿一份額度
    (again,) = await g.parse([_req("again", "再一句", actor="keeper")], allow_lists=ALLOW, lane="interactive")
    assert again.provenance == {"upstream_code": "PER_USER_RATE_LIMITED"}


async def test_daily_budget_is_not_reset_when_the_wall_clock_goes_backwards():
    now = [1_000_000.0]
    inner = _Inner()
    g = _guard(inner, now=now, daily=1, per_min=100)
    await g.parse([_req("a", "句1")], allow_lists=ALLOW, lane="interactive")
    now[0] -= 86_400.0  # 校時把牆上時鐘往回撥一天
    (r,) = await g.parse([_req("b", "句2", actor="u2")], allow_lists=ALLOW, lane="interactive")
    assert r.provenance == {"upstream_code": "DAILY_BUDGET_EXHAUSTED"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"concurrency": {"interactive": 2}},
        {"concurrency": {"interactive": 2, "batch": 0}},
        {"concurrency": {"interactive": 2, "batch": 1, "extra": 1}},
        {"per_user_per_minute": 0},
        {"daily_budget": 0},
        {"acquire_timeout_s": -1.0},
    ],
)
def test_constructor_fails_fast_on_unusable_limits(kwargs):
    base = {
        "bundle_code": "b1",
        "concurrency": {"interactive": 2, "batch": 1},
        "per_user_per_minute": 30,
        "daily_budget": 2000,
    }
    with pytest.raises(ValueError):
        GuardedWiParser(_Inner(), **{**base, **kwargs})


async def test_context_outside_whitelist_is_rejected_before_any_quota_is_taken():
    g = _guard(_Inner())
    bad = WiParseRequest(item_id="x", wi_statement="t", source_lang="zh", actor="u1", scope="s1", context={"employee_no": "E1"})
    with pytest.raises(ValueError, match="whitelist"):
        await g.parse([bad], allow_lists=ALLOW, lane="interactive")
    assert g.daily_count == 0 and g._per_user == {}


async def test_actor_is_normalized_so_case_and_spaces_do_not_buy_extra_quota():
    inner = _Inner()
    g = _guard(inner, per_min=1)
    (a,) = await g.parse([_req("a", "句1", actor="E001")], allow_lists=ALLOW, lane="interactive")
    (b,) = await g.parse([_req("b", "句2", actor="  e001 ")], allow_lists=ALLOW, lane="interactive")
    assert a.status == "ok"
    assert b.provenance == {"upstream_code": "PER_USER_RATE_LIMITED"}
    with pytest.raises(ValueError):
        await g.parse([_req("c", "句3", actor="   ")], allow_lists=ALLOW, lane="interactive")


async def test_rate_limit_window_ignores_wall_clock_going_backwards():
    wall = [1_000_000.0]
    mono = [500.0]
    inner = _Inner()
    g = GuardedWiParser(
        inner,
        bundle_code="b1",
        concurrency={"interactive": 2, "batch": 1},
        per_user_per_minute=1,
        daily_budget=100,
        clock=lambda: wall[0],
        monotonic=lambda: mono[0],
    )
    await g.parse([_req("a", "句1")], allow_lists=ALLOW, lane="interactive")
    wall[0] -= 3600.0  # 校時把牆上時鐘往回撥
    mono[0] += 61.0
    (r,) = await g.parse([_req("b", "句2")], allow_lists=ALLOW, lane="interactive")
    assert r.status == "ok", "視窗看單調時鐘，不被牆上時鐘往回撥鎖住"


async def test_idle_actors_are_swept_so_the_table_does_not_grow_forever():
    now = [1_000_000.0]
    inner = _Inner()
    g = _guard(inner, now=now, per_min=5, daily=10_000)
    for i in range(1100):
        await g.parse([_req(f"a{i}", f"句{i}", actor=f"u{i}")], allow_lists=ALLOW, lane="interactive")
    now[0] += 120.0
    await g.parse([_req("last", "最後一句", actor="late")], allow_lists=ALLOW, lane="interactive")
    assert len(g._per_user) < 10, "過期的觸發者要被掃掉"


async def test_requests_in_different_lanes_are_not_merged():
    inner = _Inner()
    inner.gate = asyncio.Event()
    g = _guard(inner)
    t1 = asyncio.ensure_future(g.parse([_req("a")], allow_lists=ALLOW, lane="interactive"))
    t2 = asyncio.ensure_future(g.parse([_req("b")], allow_lists=ALLOW, lane="batch"))
    await asyncio.sleep(0.01)
    inner.gate.set()
    await asyncio.gather(t1, t2)
    assert sorted(lane for _, lane in inner.calls) == ["batch", "interactive"]
