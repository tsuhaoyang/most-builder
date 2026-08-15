"""wi_ai_service 毒輸入防線單元測試（Blocker 1a/1b；無 DB）。

三層防禦中此檔測前兩層：
- 長度守衛：超過 MAX_PARSE_TEXT_CHARS 直接 TextTooLong，不進 parser（不碰 session）
- CPU 段隔離：同步 normalize/parse 段在 executor 內、外包 wait_for——
  超時丟 TimeoutError 且 **event loop 全程保持回應**（heartbeat 能跑）

mutation 對應（證據見交付回報）：
- parse_interactive 的長度守衛拿掉 → test_text_too_long_* 紅
- run_in_executor 拿掉（直接同步呼叫）→ test_timeout_fires_and_loop_stays_alive 紅
  （同步阻塞下 heartbeat 餓死、TimeoutError 也不會發生——wait_for 對同步碼無作用點）
- wait_for 拿掉 → 同測試紅（永遠等 executor 跑完，不會有 TimeoutError）
- **parse 段**（RuleBasedParser.parse）的 executor＋wait_for 拿掉 →
  test_parse_stage_timeout_fires_and_loop_stays_alive 紅；normalize 段測試不動
  （兩段各有一組守衛，只釘 normalize 段時拆 parse 段是靜默 wedge：loop 有回應但
  tick 永不返回、task 不死、done callback 不觸發＝不可觀測）
"""
from __future__ import annotations

import asyncio
import time
import uuid

import pytest

from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS
from ddm_v2.services.v2 import wi_ai_service

pytestmark = pytest.mark.unit


async def test_text_too_long_rejected_before_any_io():
    """超長輸入必須在碰 DB 之前被拒（session=None 仍應丟 TextTooLong 而非 AttributeError）。"""
    with pytest.raises(wi_ai_service.TextTooLong) as ei:
        await wi_ai_service.parse_interactive(
            None,  # type: ignore[arg-type]  # 守衛必須在任何 session 操作之前
            text="甲" * (MAX_PARSE_TEXT_CHARS + 1),
            rule_set_code="MINIMOST_FACTORY_V2",
            created_by="UT",
        )
    assert str(MAX_PARSE_TEXT_CHARS) in str(ei.value)


async def test_text_at_limit_passes_guard():
    """恰好等於上限不觸發 TextTooLong（會走到後續流程，於 session 操作處失敗）。"""
    with pytest.raises(Exception) as ei:
        await wi_ai_service.parse_interactive(
            None,  # type: ignore[arg-type]
            text="乙" * MAX_PARSE_TEXT_CHARS,
            rule_set_code="MINIMOST_FACTORY_V2",
            created_by="UT",
        )
    assert not isinstance(ei.value, wi_ai_service.TextTooLong)


async def test_timeout_fires_and_loop_stays_alive(monkeypatch):
    """CPU 段掛住（同步 sleep）→ wait_for 超時，且超時等待期間 loop 仍在轉。

    單加 wait_for 是無效的：它中斷不了同步阻塞。此測試同時驗證兩件事——
    (1) TimeoutError 真的發生（executor 給了 timeout 作用點）；
    (2) 等待期間 heartbeat task 有推進（loop 沒被卡住）。
    """

    def _stuck_normalize(text: str):
        time.sleep(0.6)  # 模擬 SequenceMatcher 病理輸入的同步阻塞
        return "x", [0]

    monkeypatch.setattr(wi_ai_service, "normalize_with_map", _stuck_normalize)
    monkeypatch.setattr(wi_ai_service, "PARSE_CPU_TIMEOUT_S", 0.15)

    beats = 0

    async def _heartbeat():
        nonlocal beats
        while True:
            beats += 1
            await asyncio.sleep(0.01)

    hb = asyncio.create_task(_heartbeat())
    try:
        with pytest.raises(TimeoutError):
            await wi_ai_service.parse_interactive(
                None,  # type: ignore[arg-type]  # 超時在 session 使用前發生
                text="正常長度輸入",
                rule_set_code="MINIMOST_FACTORY_V2",
                created_by="UT",
            )
    finally:
        hb.cancel()
    # 0.15s 的超時窗內 heartbeat 理論可跑 ~15 次；同步阻塞（mutation）時為 0~1 次
    assert beats >= 5


async def test_parse_stage_timeout_fires_and_loop_stays_alive(monkeypatch):
    """RuleBasedParser.parse 掛住 → **parse 段自己的** wait_for 超時、loop 存活。

    normalize 段維持真實碼（短輸入毫秒級通過）——所以 mutation 只拆 parse 段的
    executor＋wait_for 時本測試紅，而既有的 normalize 段測試不受影響；反之亦然。
    session 相依的讀取（rule_set／bundle／cache／synonyms）以 stub 代替：超時
    必須發生在任何 DB 寫入之前，此處只釘 CPU 段的縱深防禦，不測資料流。
    """

    class _FakeRuleSet:
        code = "MINIMOST_FACTORY_V2"
        id = uuid.uuid4()

    class _FakeBundle:
        code = "wi-ai-dev-000"
        id = uuid.uuid4()

    async def _fake_rule_set(session, code):
        return _FakeRuleSet()

    async def _fake_bundle(session, *, code):
        return _FakeBundle()

    async def _no_cached_run(session, *, input_hash, bundle_id):
        return None

    async def _no_synonyms(session, rule_set_code):
        return []

    def _stuck_parse(self, text, rule_set_code=""):
        time.sleep(0.6)  # 同 normalize 段測試的手法：同步阻塞模擬病理輸入
        # 若 wait_for 被拆，這個假結果會讓後續 plan_from_rule_result 炸出
        # 非 TimeoutError → pytest.raises(TimeoutError) 紅
        return object()

    monkeypatch.setattr(wi_ai_service, "_get_rule_set", _fake_rule_set)
    monkeypatch.setattr(wi_ai_service, "_get_active_bundle", _fake_bundle)
    monkeypatch.setattr(wi_ai_service, "_find_cached_run", _no_cached_run)
    monkeypatch.setattr(wi_ai_service.syn_svc, "list_synonyms", _no_synonyms)
    monkeypatch.setattr(wi_ai_service.RuleBasedParser, "parse", _stuck_parse)
    monkeypatch.setattr(wi_ai_service, "PARSE_CPU_TIMEOUT_S", 0.15)

    beats = 0

    async def _heartbeat():
        nonlocal beats
        while True:
            beats += 1
            await asyncio.sleep(0.01)

    hb = asyncio.create_task(_heartbeat())
    try:
        with pytest.raises(TimeoutError):
            await wi_ai_service.parse_interactive(
                None,  # type: ignore[arg-type]  # 超時在任何 session 寫入前發生
                text="正常長度輸入",
                rule_set_code="MINIMOST_FACTORY_V2",
                created_by="UT",
            )
    finally:
        hb.cancel()
    # 0.15s 的超時窗內 heartbeat 理論可跑 ~15 次；同步阻塞（mutation）時為 0~1 次
    assert beats >= 5


def test_interactive_contract_matches_parse_limit():
    """NLDraftIn.text 的 max_length 必須等於 MAX_PARSE_TEXT_CHARS。

    互動路徑靠 Pydantic 在邊界擋（422）；若兩個數字漂移且 schema 放得比引擎寬，
    超長輸入會穿到 service 層變 TextTooLong（500 而非 422）。
    """
    from ddm_v2.api.routes.v2.nl_draft import NLDraftIn

    field = NLDraftIn.model_fields["text"]
    max_len = next(
        (m.max_length for m in field.metadata if getattr(m, "max_length", None)),
        None,
    )
    assert max_len == MAX_PARSE_TEXT_CHARS
