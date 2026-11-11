"""NLP draft parser port 合約與輸出 dataclasses。

DraftParserPort 是 Protocol；RuleBasedParser 是第一個 adapter。
future adapter（retrieval.py）只需實作同一 Protocol，無需改此合約。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SlotCandidate:
    """單一 slot 的候選選項。"""

    option_code: str
    score: float  # 0..1 校準信心：exact=0.95 / longest_match=0.8 / default=0.3
    source: str   # "exact" | "longest_match" | "retrieval" | "default"


@dataclass(frozen=True)
class SlotSuggestion:
    """GM/CM 序列中一個 slot 的建議結果。"""

    slot_index: int          # 0..6
    field: str               # 例 "g_code" / "p_base_code" / "a_code"
    chosen: SlotCandidate | None
    top_k: list[SlotCandidate]  # 含 chosen；跨參數歧義時 ≥2
    needs_review: bool


@dataclass(frozen=True)
class NLDraftResult:
    """NL 解析完整結果。"""

    raw_text: str
    normalized_text: str
    suggested_seq: str | None   # "GM" | "CM" | None
    context: dict               # hand / object / from / to / reach_cm（vocab 候選）
    slots: list[SlotSuggestion]
    overall_confidence: float
    provenance: dict            # parser 版本、rule_set_code、耗時(ms)


class DraftParserPort(Protocol):
    """NL draft parser adapter 介面。"""

    def parse(self, text: str, rule_set_code: str) -> NLDraftResult:
        ...
