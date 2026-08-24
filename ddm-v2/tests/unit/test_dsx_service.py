"""dsx_service.get_a3_distance——四種 available=false 分支、external_code 解析、
feature flag off 的行為、`wi_row_id` optional 時的快照寫入分歧
（免 DB：用 fake session 替身，DSX client 用 monkeypatch 替換）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from ddm_v2.exceptions import ConflictError, NotFoundError
from ddm_v2.models.v2.dsx_suggestion import WiRowDsxSuggestion
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.services.v2 import dsx_client, dsx_service
from ddm_v2.settings import get_settings

WI_ROW_ID = uuid.uuid4()
FROM_VOCAB_ID = uuid.uuid4()
TO_VOCAB_ID = uuid.uuid4()
_WORKSHEET_ID = uuid.uuid4()
_PROCESS_VERSION_ID = uuid.uuid4()


def _writable_row_gets(
    wi_row_id: uuid.UUID = WI_ROW_ID, *, status: str = "draft"
) -> dict[tuple[type, object], object]:
    """`_require_row_writable` 的 `.get()` 三連查——draft 版本，本函式回傳可寫入的組合。"""
    return {
        (WiRow, wi_row_id): WiRow(worksheet_id=_WORKSHEET_ID),
        (MostWorksheet, _WORKSHEET_ID): MostWorksheet(process_version_id=_PROCESS_VERSION_ID),
        (ProcessVersion, _PROCESS_VERSION_ID): ProcessVersion(status=status),
    }


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    """`.get()` 從固定字典回值；`.execute()` 回一個固定 scalar_one_or_none 結果。

    不解析真的 SQL——足以測 dsx_service 的分支邏輯，DB 層的 upsert 語意另有整合測試
    （真的跑過 migration）。
    """

    def __init__(self, gets: dict[tuple[type, object], object], execute_value=None):
        self._gets = gets
        self._execute_value = execute_value
        self.added: list[object] = []
        self.flushed = False

    async def get(self, model, pk):
        if (model, pk) not in self._gets:
            raise AssertionError(f"unexpected session.get({model.__name__}, {pk})")
        return self._gets[(model, pk)]

    async def execute(self, _stmt):
        return _FakeResult(self._execute_value)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True


def _vocab(external_code: str | None) -> WorkVocabItem:
    return WorkVocabItem(external_code=external_code)


@pytest.fixture(autouse=True)
def _clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
    """比照 test_wi_ai_fallback.py 的慣例：monkeypatch env 後必須 clear lru_cache，
    否則跨測試殘留過期 Settings（見該檔 test_settings_cache_not_leaked_by_preceding_tests）。
    """
    yield
    get_settings.cache_clear()


async def test_integration_disabled_short_circuits_without_touching_session_or_client(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "0")
    get_settings.cache_clear()

    session = _FakeSession(gets={})  # 任何 .get() 呼叫都會讓測試失敗（見 _FakeSession）
    result = await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result == {"available": False, "reason": "integration_disabled"}


@pytest.mark.parametrize(
    "from_item,to_item",
    [
        (None, _vocab("tool_01")),
        (_vocab("tool_01"), None),
        (_vocab(None), _vocab("tool_01")),
        (_vocab("tool_01"), _vocab(None)),
    ],
)
async def test_vocab_not_mapped_when_either_side_lacks_external_code(
    monkeypatch: pytest.MonkeyPatch, from_item, to_item
):
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    get_settings.cache_clear()

    session = _FakeSession(
        gets={
            **_writable_row_gets(),
            (WorkVocabItem, FROM_VOCAB_ID): from_item,
            (WorkVocabItem, TO_VOCAB_ID): to_item,
        }
    )
    result = await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result == {"available": False, "reason": "vocab_not_mapped"}


async def test_missing_base_url_while_enabled_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
):
    """DDM_DSX_INTEGRATION_ENABLED=1 但沒設 base_url——設定錯誤，route 層轉 503（No error bypass）。"""
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.delenv("DDM_DSX_API_BASE_URL", raising=False)
    get_settings.cache_clear()

    session = _FakeSession(
        gets={
            **_writable_row_gets(),
            (WorkVocabItem, FROM_VOCAB_ID): _vocab("tool_01"),
            (WorkVocabItem, TO_VOCAB_ID): _vocab("bin_white"),
        }
    )
    with pytest.raises(RuntimeError):
        await dsx_service.get_a3_distance(
            session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
        )


async def _enabled_session(monkeypatch: pytest.MonkeyPatch, execute_value=None) -> _FakeSession:
    monkeypatch.setenv("DDM_DSX_INTEGRATION_ENABLED", "1")
    monkeypatch.setenv("DDM_DSX_API_BASE_URL", "http://127.0.0.1:1")
    get_settings.cache_clear()
    return _FakeSession(
        gets={
            **_writable_row_gets(),
            (WorkVocabItem, FROM_VOCAB_ID): _vocab("tool_01"),
            (WorkVocabItem, TO_VOCAB_ID): _vocab("bin_white"),
        },
        execute_value=execute_value,
    )


async def test_dsx_object_not_found_maps_to_reason(monkeypatch: pytest.MonkeyPatch):
    session = await _enabled_session(monkeypatch)

    async def _raise_not_found(**_kw):
        raise dsx_client.DsxObjectNotFound("boom")

    monkeypatch.setattr(dsx_client, "query_distance", _raise_not_found)

    result = await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result == {"available": False, "reason": "dsx_object_not_found"}
    assert session.added == [], "查無此物件不該寫入 suggestion 快照"


async def test_dsx_unreachable_maps_to_reason_distinct_from_object_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    session = await _enabled_session(monkeypatch)

    async def _raise_unreachable(**_kw):
        raise dsx_client.DsxUnreachable("boom")

    monkeypatch.setattr(dsx_client, "query_distance", _raise_unreachable)

    result = await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result == {"available": False, "reason": "dsx_unreachable"}
    assert session.added == []


async def test_success_writes_suggestion_snapshot_and_returns_distance(
    monkeypatch: pytest.MonkeyPatch,
):
    session = await _enabled_session(monkeypatch, execute_value=None)  # 沒有既有快照 → insert

    async def _fake_query(**_kw):
        return dsx_client.DsxDistanceResult(
            distance_cm=42.5,
            provisional=True,
            measure_from_mode="shoulder",
            warnings=["P4 未定"],
            raw={"distance_cm": 42.5, "station_id": "most-single-station"},
            horizontal_cm=40.0,
            vertical_cm=12.0,
        )

    monkeypatch.setattr(dsx_client, "query_distance", _fake_query)

    result = await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result["available"] is True
    assert result["distance_cm"] == 42.5
    assert result["horizontal_cm"] == 40.0
    assert result["vertical_cm"] == 12.0
    assert result["provisional"] is True
    assert result["measure_from_mode"] == "shoulder"
    assert result["warnings"] == ["P4 未定"]
    assert result["queried_at"]

    assert session.flushed is True
    assert len(session.added) == 1
    row = session.added[0]
    assert isinstance(row, WiRowDsxSuggestion)
    assert row.wi_row_id == WI_ROW_ID
    assert row.a_slot_key == "a3"
    assert float(row.raw_distance_cm) == 42.5
    assert row.dsx_response == {"distance_cm": 42.5, "station_id": "most-single-station"}


async def test_success_upserts_existing_suggestion_in_place(monkeypatch: pytest.MonkeyPatch):
    existing = WiRowDsxSuggestion(
        id=uuid.uuid4(),
        wi_row_id=WI_ROW_ID,
        a_slot_key="a3",
        from_vocab_id=FROM_VOCAB_ID,
        to_vocab_id=TO_VOCAB_ID,
        raw_distance_cm=10,
        dsx_response={"distance_cm": 10},
        queried_at=datetime.now(timezone.utc),
    )
    session = await _enabled_session(monkeypatch, execute_value=existing)

    async def _fake_query(**_kw):
        return dsx_client.DsxDistanceResult(
            distance_cm=42.5, provisional=True, measure_from_mode="shoulder", warnings=[], raw={}
        )

    monkeypatch.setattr(dsx_client, "query_distance", _fake_query)

    await dsx_service.get_a3_distance(
        session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert session.added == [], "既有快照走 UPDATE，不新增一列"
    assert float(existing.raw_distance_cm) == 42.5


async def test_wi_row_id_missing_row_raises_not_found_before_touching_dsx(
    monkeypatch: pytest.MonkeyPatch,
):
    """wi_row_id 有值但指向不存在的列——不得等 flush() 才炸 IntegrityError，query_distance 不該被叫到。"""
    session = await _enabled_session(monkeypatch)
    session._gets[(WiRow, WI_ROW_ID)] = None

    async def _fail_if_called(**_kw):
        raise AssertionError("wi_row 不存在時不該呼叫 DSX client")

    monkeypatch.setattr(dsx_client, "query_distance", _fail_if_called)

    with pytest.raises(NotFoundError):
        await dsx_service.get_a3_distance(
            session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
        )


async def test_wi_row_id_on_non_draft_version_raises_conflict(monkeypatch: pytest.MonkeyPatch):
    """所屬版本已凍結（非 draft）——拒絕寫入，比照 wi_context_service._require_editable_row。"""
    session = await _enabled_session(monkeypatch)
    session._gets.update(_writable_row_gets(status="approved"))

    with pytest.raises(ConflictError):
        await dsx_service.get_a3_distance(
            session, wi_row_id=WI_ROW_ID, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
        )


async def test_wi_row_id_none_succeeds_without_writing_snapshot(monkeypatch: pytest.MonkeyPatch):
    """組新列、尚未存檔（契約 §6）：`wi_row_id=None` 時不查、不驗、不寫快照，
    但距離查詢本身照樣成功——D4／I1／I5 不變式不受影響，只是少一筆出處紀錄。
    """
    session = await _enabled_session(monkeypatch, execute_value=None)

    async def _fake_query(**_kw):
        return dsx_client.DsxDistanceResult(
            distance_cm=17.0, provisional=True, measure_from_mode="shoulder", warnings=[], raw={}
        )

    monkeypatch.setattr(dsx_client, "query_distance", _fake_query)

    result = await dsx_service.get_a3_distance(
        session, wi_row_id=None, from_vocab_id=FROM_VOCAB_ID, to_vocab_id=TO_VOCAB_ID
    )
    assert result["available"] is True
    assert result["distance_cm"] == 17.0
    # DSX 沒給水平/垂直分量（本測試的 DsxDistanceResult 沒帶這兩個欄位，用預設值 None）
    # ——不得炸掉，也不能被靜默塞 0。
    assert result["horizontal_cm"] is None
    assert result["vertical_cm"] is None
    assert session.added == [], "wi_row_id 缺席時不得寫入 suggestion 快照"
    assert session.flushed is False
