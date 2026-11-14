"""rule_plan_adapter 的語言判定（英文輸入經 rule planner 的路徑）。

由 `test_english_parsing.py` 的 `TestEnglishParsingIntegration` 搬來：原檔其餘部分測的是
已移除的 LLM prompt（ADR-037），本測試測的是保留的確定性元件 `rule_plan_adapter`，
不需要 DB（原 `integration` marker 是誤標）。
"""
from __future__ import annotations

import pytest

from ddm_v2.nlp.ports import NLDraftResult
from ddm_v2.nlp.rule_plan_adapter import _detect_language, plan_from_rule_result

pytestmark = pytest.mark.unit


def test_english_text_processing_flow():
    english_text = "Pick up the electric screwdriver"

    assert _detect_language(english_text) == "en"

    mock_result = NLDraftResult(
        raw_text=english_text,
        normalized_text=english_text,
        suggested_seq="GM",
        context={},
        slots=[],
        overall_confidence=0.8,
        provenance={"parser": "rule_based"},
    )
    plan, _candidates = plan_from_rule_result(mock_result)
    assert plan.language == "en"
    assert plan.normalized_text == english_text
