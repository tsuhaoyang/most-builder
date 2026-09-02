"""Language-aware prompt builder for WI AI parser.

This module extends the existing prompt system to support both Chinese and English
language processing, detecting the language and selecting appropriate prompts.
"""
from __future__ import annotations

from ddm_v2.nlp.prompts.plan_v1 import SYSTEM_PROMPT, build_user_message, FEW_SHOTS
from ddm_v2.nlp.prompts.plan_v1_en import SYSTEM_PROMPT_EN, build_user_message_en, ENGLISH_FEW_SHOTS


def detect_language(text: str) -> str:
    """Detect language of input text.
    
    Returns 'zh' for Chinese, 'en' for English, 'mixed' for mixed content.
    This is more sophisticated than the simple version in rule_plan_adapter.py
    """
    if not text:
        return "zh"  # Default to Chinese for empty text
    
    # Count CJK characters (Chinese, Japanese, Korean)
    cjk_count = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    
    # Count ASCII letters 
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    
    # Count total non-whitespace characters
    total_chars = len([ch for ch in text if not ch.isspace()])
    
    if total_chars == 0:
        return "zh"
    
    cjk_ratio = cjk_count / total_chars
    ascii_ratio = ascii_letters / total_chars
    
    # If majority CJK characters, it's Chinese
    if cjk_ratio >= 0.3:
        return "zh"
    
    # If majority ASCII letters and very few CJK, it's English  
    if ascii_ratio >= 0.5 and cjk_ratio < 0.1:
        return "en"
    
    # Mixed content
    return "mixed"


def build_language_aware_prompt(normalized_text: str, context_snapshot: dict) -> tuple[str, list[tuple[str, str]], str]:
    """Build prompt components based on detected language.
    
    Returns:
        (system_prompt, few_shots, user_message)
    """
    language = detect_language(normalized_text)
    
    if language == "en":
        # Pure English: use English prompts
        system_prompt = SYSTEM_PROMPT_EN
        few_shots = ENGLISH_FEW_SHOTS
        user_message = build_user_message_en(normalized_text, context_snapshot)
    elif language == "mixed":
        # Mixed content: use Chinese system prompt but include English examples
        system_prompt = SYSTEM_PROMPT
        # Combine Chinese and English few-shots for mixed content
        few_shots = FEW_SHOTS + ENGLISH_FEW_SHOTS
        user_message = build_user_message(normalized_text, context_snapshot)
    else:
        # Chinese or default: use original Chinese prompts
        system_prompt = SYSTEM_PROMPT
        few_shots = FEW_SHOTS
        user_message = build_user_message(normalized_text, context_snapshot)
    
    return system_prompt, few_shots, user_message


def get_prompt_components_for_language(language: str) -> tuple[str, list[tuple[str, str]]]:
    """Get system prompt and few-shots for a specific language.
    
    Args:
        language: 'zh', 'en', or 'mixed'
    
    Returns:
        (system_prompt, few_shots)
    """
    if language == "en":
        return SYSTEM_PROMPT_EN, ENGLISH_FEW_SHOTS
    elif language == "mixed":
        return SYSTEM_PROMPT, FEW_SHOTS + ENGLISH_FEW_SHOTS
    else:  # 'zh' or default
        return SYSTEM_PROMPT, FEW_SHOTS