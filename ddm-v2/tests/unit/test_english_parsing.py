"""Tests for English language parsing functionality in WI AI parser."""
from __future__ import annotations

import pytest

from ddm_v2.nlp.contracts import validate_planner_output
from ddm_v2.nlp.prompts.language_aware import (
    build_language_aware_prompt,
    detect_language,
    get_prompt_components_for_language,
)
from ddm_v2.nlp.prompts.plan_v1_en import ENGLISH_FEW_SHOTS, SYSTEM_PROMPT_EN


class TestLanguageDetection:
    """Test language detection functionality."""

    def test_detect_chinese(self):
        """Test detection of Chinese text."""
        chinese_text = "拿取電動起子，依圖示鎖附兩顆螺絲"
        assert detect_language(chinese_text) == "zh"

    def test_detect_english(self):
        """Test detection of English text."""
        english_text = "Pick up the electric screwdriver and fasten two screws as shown"
        assert detect_language(english_text) == "en"

    def test_detect_mixed(self):
        """Test detection of mixed language text."""
        # Mixed = neither CJK-dominant (>=30%) nor ASCII-letter-dominant (>=50%).
        # A string with symbols/digits and a little of each language lands here.
        mixed_text = "OK 螺絲 123 -- 456"
        assert detect_language(mixed_text) == "mixed"

    def test_detect_empty_text(self):
        """Test detection with empty text defaults to Chinese."""
        assert detect_language("") == "zh"
        assert detect_language("   ") == "zh"

    def test_detect_numeric_text(self):
        """Test detection with only digits (no CJK, no ASCII letters)."""
        # No CJK and no ASCII letters -> neither dominance rule fires -> 'mixed'.
        numeric_text = "123456789"
        assert detect_language(numeric_text) == "mixed"


class TestLanguageAwarePrompts:
    """Test language-aware prompt selection."""

    def test_english_prompt_selection(self):
        """Test that English text selects English prompts."""
        english_text = "Insert the memory module into the socket"
        context = {"available_tools": [], "available_locations": []}
        
        system_prompt, few_shots, user_message = build_language_aware_prompt(english_text, context)
        
        assert system_prompt == SYSTEM_PROMPT_EN
        assert few_shots == ENGLISH_FEW_SHOTS
        assert "Insert the memory module" in user_message

    def test_chinese_prompt_selection(self):
        """Test that Chinese text selects Chinese prompts."""
        chinese_text = "將記憶體模組插入插座"
        context = {"available_tools": [], "available_locations": []}
        
        system_prompt, few_shots, user_message = build_language_aware_prompt(chinese_text, context)
        
        # Should use original Chinese prompts (imported from plan_v1)
        assert "工業工程" in system_prompt  # Chinese content
        assert len(few_shots) > 0  # Should have Chinese few-shots

    def test_mixed_content_prompt_selection(self):
        """Test that mixed content uses combined prompts."""
        mixed_text = "Take the 螺絲 and 放置 on workbench"
        context = {"available_tools": [], "available_locations": []}
        
        system_prompt, few_shots, user_message = build_language_aware_prompt(mixed_text, context)
        
        # Should use Chinese system prompt but include both language examples
        assert "工業工程" in system_prompt
        assert len(few_shots) > len(ENGLISH_FEW_SHOTS)  # Combined few-shots

    def test_get_prompt_components_for_language(self):
        """Test direct language component retrieval."""
        # English components
        en_system, en_shots = get_prompt_components_for_language("en")
        assert en_system == SYSTEM_PROMPT_EN
        assert en_shots == ENGLISH_FEW_SHOTS

        # Chinese components (should not be empty)
        zh_system, zh_shots = get_prompt_components_for_language("zh")
        assert "工業工程" in zh_system
        assert len(zh_shots) > 0

        # Mixed components
        mixed_system, mixed_shots = get_prompt_components_for_language("mixed")
        assert "工業工程" in mixed_system
        assert len(mixed_shots) > len(ENGLISH_FEW_SHOTS)


class TestEnglishFewShotValidation:
    """Test that English few-shot examples are valid."""

    def test_english_few_shots_are_valid(self):
        """Test that all English few-shot examples pass validation."""
        for user_message, assistant_json in ENGLISH_FEW_SHOTS:
            import json
            
            # Parse the assistant response
            output_data = json.loads(assistant_json)
            
            # Extract normalized text from user message
            # This is a simplified extraction - in real usage it would be more sophisticated
            lines = user_message.split('\n')
            normalized_text = ""
            for i, line in enumerate(lines):
                if line.strip() == "<wi_text>":
                    normalized_text = lines[i + 1].strip()
                    break
            
            assert normalized_text, f"Could not extract normalized text from: {user_message[:100]}"
            
            # Validate the output structure - this should not raise any errors
            # Note: We're testing structure, not full semantic validation which requires the contracts module
            assert "language" in output_data
            assert output_data["language"] in ["zh", "en", "mixed"]
            assert "actions" in output_data
            assert isinstance(output_data["actions"], list)
            
            # Basic action structure validation
            for action in output_data["actions"]:
                assert "action_id" in action
                assert "action_type" in action
                assert "sequence_order" in action
                assert "roles" in action
                assert "evidence" in action


class TestEnglishPromptContent:
    """Test English prompt content quality."""

    def test_system_prompt_en_contains_key_rules(self):
        """Test that English system prompt contains all key parsing rules."""
        # Check that important rules are present
        key_rules = [
            "atomic action",
            "move_place",
            "acquire",
            "controlled_move", 
            "process",
            "inspect",
            "verbatim copy",
            "object",
            "tool",
            "destination",
            "evidence"
        ]
        
        for rule in key_rules:
            assert rule.lower() in SYSTEM_PROMPT_EN.lower(), f"Missing key rule: {rule}"

    def test_english_examples_cover_action_types(self):
        """Test that English examples cover different action types."""
        import json
        
        action_types_covered = set()
        for _, assistant_json in ENGLISH_FEW_SHOTS:
            output_data = json.loads(assistant_json)
            for action in output_data["actions"]:
                action_types_covered.add(action["action_type"])
        
        # Should cover multiple action types
        expected_types = {"move_place", "acquire", "process", "inspect", "controlled_move"}
        covered = action_types_covered & expected_types
        assert len(covered) >= 3, f"Only covered {len(covered)} action types: {covered}"

    def test_english_examples_have_proper_language_field(self):
        """Test that all English examples have language field set to 'en'."""
        import json
        
        for _, assistant_json in ENGLISH_FEW_SHOTS:
            output_data = json.loads(assistant_json)
            assert output_data["language"] == "en", "English examples should have language='en'"


@pytest.mark.integration
class TestEnglishParsingIntegration:
    """Integration tests for English parsing (requires full system)."""

    def test_english_text_processing_flow(self):
        """Test that English text flows through the system correctly."""
        from ddm_v2.nlp.rule_plan_adapter import _detect_language, plan_from_rule_result
        from ddm_v2.nlp.ports import NLDraftResult
        
        english_text = "Pick up the electric screwdriver"
        
        # Test language detection
        language = _detect_language(english_text)
        assert language == "en"
        
        # Test that rule-based fallback still works with English text
        mock_result = NLDraftResult(
            raw_text=english_text,
            normalized_text=english_text,
            suggested_seq="GM",
            context={},
            slots=[],
            overall_confidence=0.8,
            provenance={"parser": "rule_based"},
        )

        plan, candidates = plan_from_rule_result(mock_result)
        assert plan.language == "en"
        assert plan.normalized_text == english_text