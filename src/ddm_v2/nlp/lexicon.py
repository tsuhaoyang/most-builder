"""最長匹配詞典建構與掃描。

詞典由呼叫方傳入 synonyms list（來自 rule_option_synonyms DB 表），
依 norm 長度降冪排序後做貪婪最長匹配，避免短詞遮蔽長詞（v3 G 詞表缺陷修正）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class LexEntry:
    """詞典條目。"""

    norm: str          # 正規化後的詞（匹配鍵）
    parameter: str     # 'A'|'B'|'G'|'P'|'M'|'X'|'I'|'vocab'
    option_code: str   # 對應的選項 code
    score: float       # 信心分：exact=0.95
    source: str        # "exact"
    priority: int = 0  # 偏好位次：數字小者優先，0＝預設（同面多 code 變體用；D3-017）


def build_lexicon(synonyms: list[dict]) -> list[LexEntry]:
    """從 DB 同義詞 list 建立詞典，依 norm 長度降冪排序（長詞先匹配）。

    Args:
        synonyms: [{"parameter": ..., "option_code": ..., "synonym_norm": ..., "priority": ...}]

    Returns:
        依 len(norm) 降冪排序的 LexEntry list。

    排序不變量（決定性，不依賴呼叫方傳入順序）：
    - 主鍵＝(len(norm), norm) 降冪：長詞先匹配（防子字串遮蔽）。
    - **同 norm 的變體以 (priority, option_code) 升冪決勝**：v2_0038 起同一詞面
      可掛多個 code（IE 裁決的方向變體，如「放至」→ p_place_single(0)/
      p_place_none(1)）；match_all 的位置覆蓋讓先到者得，故排前者＝預設。
      priority 數字小者優先（0＝預設，D3-017 定調）；option_code 收尾保證
      同 priority 也決定性。

    NOTE(impl-05 P4): 第一版所有 DB 同義詞均視為 exact(0.95)。
    "longest_match"(0.8) / "default"(0.3) 信心分層在 Stage 2（retrieval.py）實作。
    score<0.7 的 needs_review 分支目前不會觸發（保留判斷式供日後擴充）。
    """
    entries: list[LexEntry] = []
    for s in synonyms:
        entries.append(
            LexEntry(
                norm=s["synonym_norm"],
                parameter=s["parameter"],
                option_code=s["option_code"],
                score=0.95,
                source="exact",
                # priority 缺欄視同 0（與 DB server_default、SynonymIn 預設一致）
                priority=int(s.get("priority") or 0),
            )
        )
    # 兩段 stable sort：先以 (priority, option_code) 升冪定同 norm 內順序，
    # 再以 (len, norm) 降冪定跨 norm 順序——後者 tie 時保留前者結果。
    entries.sort(key=lambda e: (e.priority, e.option_code))
    entries.sort(key=lambda e: (len(e.norm), e.norm), reverse=True)
    return entries


def match_all(
    text_norm: str, lexicon: list[LexEntry]
) -> list[tuple[int, int, LexEntry]]:
    """最長優先全文掃描。

    按 lexicon 順序（長→短）逐一搜尋 text_norm；命中位置若已被覆蓋則跳過，
    確保較短詞不遮蔽已命中的較長詞。

    Returns:
        [(start, end, entry), ...] 依 start 排序。
    """
    matched: list[tuple[int, int, LexEntry]] = []
    covered: set[int] = set()  # 已覆蓋的字元位置

    for entry in lexicon:
        needle = entry.norm
        nlen = len(needle)
        if nlen == 0:
            continue
        pos = 0
        while True:
            idx = text_norm.find(needle, pos)
            if idx == -1:
                break
            span = set(range(idx, idx + nlen))
            if not span & covered:
                matched.append((idx, idx + nlen, entry))
                covered |= span
            pos = idx + 1

    matched.sort(key=lambda x: x[0])
    return matched
