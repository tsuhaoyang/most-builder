"""R3b outbox：event_no 遞增與 payload constants。"""
from __future__ import annotations

from ddm_v2.services.v2.outbox_service import (
    EVENT_REVIEW_RECORDED,
    EVENT_WORKSHEET_SAVED,
    SCHEMA_REVIEW_V1,
    SCHEMA_WORKSHEET_SAVED_V1,
)


def test_outbox_event_type_constants():
    assert EVENT_REVIEW_RECORDED == "wi_ai.review_recorded"
    assert EVENT_WORKSHEET_SAVED == "worksheet.content_saved"
    assert SCHEMA_REVIEW_V1.endswith(".v1")
    assert SCHEMA_WORKSHEET_SAVED_V1.endswith(".v1")
