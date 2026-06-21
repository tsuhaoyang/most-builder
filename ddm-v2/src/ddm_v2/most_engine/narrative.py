"""後端敘事產生（FE-2）：cycle + vocab 名 + rule-set 標籤 → 可朗讀 METHOD 句。

單一權威：存檔時由此產生並存 most_cycles.narrative_zh，供匯出/讀回使用（不靠前端拼）。
依據 minimost-sequence-model-core-logic-spec §5 敘事規範。
"""
from __future__ import annotations

from typing import Any

HAND_NAMES = {"RH": "右手", "LH": "左手", "BH": "雙手"}


def _fmt(n: float | None) -> str:
    if not n:
        return ""
    return f"{n:g}"


def build_narrative(cycle: dict[str, Any], labels: dict[str, dict[str, str]], vocab: dict[str, str]) -> str:
    """cycle＝CycleIn dict；labels＝{g/p_base/m_verb: {code:label}}；vocab＝{object/from/to/hand}。"""
    seq = cycle.get("seq")
    hand = vocab.get("hand") or ""
    frm = vocab.get("from") or ""
    to = vocab.get("to") or ""
    obj = vocab.get("object") or "目標物"
    g = labels.get("g", {}).get(((cycle.get("g2") or {}).get("g_code"))) or "取得"

    reach0 = (cycle.get("a0") or {}).get("reach_cm") or 0
    s = hand + (("從" + frm) if frm else "") + g + "「" + obj + "」"
    if reach0:
        s += "，伸手約" + _fmt(reach0) + "公分"
    s += "。"

    if seq == "GM":
        reach3 = (cycle.get("a3") or {}).get("reach_cm") or 0
        p = labels.get("p_base", {}).get(((cycle.get("p5") or {}).get("p_base_code"))) or ""
        s += "隨後"
        if reach3:
            s += "移動約" + _fmt(reach3) + "公分"
        if to:
            s += ("，" if reach3 else "") + "到" + to
        if p:
            s += "，以「" + p + "」放置"
        s += "。"
    else:
        if to:
            s += "在" + to + "一側"
        mcs = (cycle.get("m3") or {}).get("m_components") or []
        if mcs:
            mv = labels.get("m_verb", {}).get(mcs[0].get("verb_code")) or "控制"
            s += "，以" + mv + "實施移動"
        s += "。"

    s += "最後收束返回。"
    return s
