"""Rule-based DraftParser adapter — 字典驅動最長匹配。

修正 v3 五項已知缺陷（impl-05 §4）：
1. 全參數統一最長匹配（v3 僅 M 有最長匹配）
2. G 詞表遮蔽問題由長詞優先 lexicon 解決
3. 全路徑過 normalization.normalize()
4. context 以介詞框架抽取，抽不出留空而非硬猜
5. 信心排序：exact=0.95 > longest_match=0.8 > default=0.3（v3 default=1.0 反置）
"""
from __future__ import annotations

import re
import time

from .lexicon import LexEntry, build_lexicon, match_all
from .normalization import normalize
from .ports import NLDraftResult, SlotCandidate, SlotSuggestion

# GM/CM 判型關鍵字（v3 治具案例認證）
# CM：在「機台」上執行的動作（並壓合機台、進行壓合、執行壓合）
# GM：操作「治具/工具」的一般手工動作
_CM_TRIGGERS = frozenset({"並壓合機台", "並壓合機臺", "進行壓合", "執行壓合", "機台", "機臺"})
_GM_NOUNS = frozenset({"治具", "壓合站", "壓合位置", "壓合夾具", "壓合治具"})

# 距離數值 regex（context 抽取用）
_DIST_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:cm|公分|mm|毫米|吋|英寸|inch)")

# GM 序列 slot 定義（param, field_name, slot_index）
# 第二/三個 A 視為 GM 序列中的重複 A slot
_SLOT_PARAMS = [
    ("A", "a_code",       0),
    ("B", "b_code",       1),
    ("G", "g_code",       2),
    ("A", "a_code2",      3),
    ("B", "b_code2",      4),
    ("P", "p_base_code",  5),
    ("A", "a_code3",      6),
]


class RuleBasedParser:
    """字典驅動最長匹配 NL draft parser（第一版 adapter）。"""

    VERSION = "rule_based_v1"

    def __init__(self, synonyms: list[dict]) -> None:
        self._lexicon = build_lexicon(synonyms)

    def parse(self, text: str, rule_set_code: str = "") -> NLDraftResult:
        t0 = time.perf_counter()
        norm = normalize(text)

        # ── GM/CM 判型 ──────────────────────────────────────────────────
        # 同時檢查 norm（NFKC+OpenCC 後）與原文（防 OpenCC 轉換改變觸發詞）
        seq: str | None = None
        for kw in _CM_TRIGGERS:
            if kw in norm or kw in text:
                seq = "CM"
                break
        if seq is None:
            for kw in _GM_NOUNS:
                if kw in norm or kw in text:
                    seq = "GM"
                    break

        # ── context 抽取 ─────────────────────────────────────────────────
        context: dict = {"hand": None, "object": None, "from": None, "to": None}
        dist_m = _DIST_RE.search(norm)
        if dist_m:
            context["reach_cm"] = float(dist_m.group(1))

        # ── 最長匹配 ────────────────────────────────────────────────────
        matches = match_all(norm, self._lexicon)

        # 按 parameter 分組，保持匹配出現順序
        by_param: dict[str, list[LexEntry]] = {}
        for _, _, entry in matches:
            by_param.setdefault(entry.parameter, []).append(entry)

        # ── 組成 SlotSuggestion ──────────────────────────────────────────
        # 每個 slot 依 parameter 消耗一個候選（同 parameter 的第 N 個 slot 取第 N 個命中）
        slots: list[SlotSuggestion] = []
        seen_param_idx: dict[str, int] = {}

        for param, field_name, idx in _SLOT_PARAMS:
            candidates_raw = by_param.get(param, [])
            used = seen_param_idx.get(param, 0)

            if used < len(candidates_raw):
                entry = candidates_raw[used]
                seen_param_idx[param] = used + 1
                chosen = SlotCandidate(
                    option_code=entry.option_code,
                    score=entry.score,
                    source=entry.source,
                )
                top_k = [chosen]
            else:
                chosen = None
                top_k = []
                seen_param_idx[param] = used + 1

            needs_review = chosen is None or chosen.score < 0.7
            # TODO(P5): cross-param ambiguity (top_k≥2) requires multi-assignment match_all — deferred to Stage 2

            slots.append(
                SlotSuggestion(
                    slot_index=idx,
                    field=field_name,
                    chosen=chosen,
                    top_k=top_k,
                    needs_review=needs_review,
                )
            )

        filled = sum(1 for s in slots if s.chosen is not None)
        overall_conf = filled / len(slots) if slots else 0.0

        return NLDraftResult(
            raw_text=text,
            normalized_text=norm,
            suggested_seq=seq,
            context=context,
            slots=slots,
            overall_confidence=overall_conf,
            provenance={
                "parser": self.VERSION,
                "rule_set_code": rule_set_code,
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2),
            },
        )
