"""後端敘事產生：cycle + vocab 名 + rule-set 標籤/句字 → 可朗讀 METHOD 句（單一權威）。

存檔時由此產生並存 most_cycles.narrative_zh，供匯出/讀回使用（不靠前端拼）。
依據 minimost-sequence-model-core-logic-spec §5 ＋ ADR-014 E6（v3 認證顯示規則）：
- P 附加 display_rule 三態：show_self（插入/卡合取代 base 動詞）、prefix_visible_term（對準前綴）、hidden（只計 TMU 不入句）。
- GM 移動格（slot3）含手度（twist）→ 句中插入「翻轉『object』」（v3 dependency 規則）。
- slot repeat > 1 → 動詞後綴「×N」。

labels 形狀（由 providers.load_options_from_db 提供）：
  {"g": {code: {"label", "sentence"}}, "p_base": {...}, "p_addon": {code: {"label", "sentence", "display_rule"}},
   "m_verb": {...}, "x": {...}, "i": {...}}
sentence 為 NULL 時回退 label（V1 資料相容）。
"""
from __future__ import annotations

from typing import Any

HAND_NAMES = {"RH": "右手", "LH": "左手", "BH": "雙手"}


def _fmt(n: float | None) -> str:
    if not n:
        return ""
    return f"{n:g}"


def _sent(entry: dict[str, Any] | None) -> str:
    if not entry:
        return ""
    return entry.get("sentence") or entry.get("label") or ""


def _rep_suffix(slot: dict[str, Any] | None) -> str:
    rc = (slot or {}).get("repeat_count")
    return f"×{int(rc)}" if rc and int(rc) > 1 else ""


def _p_visible(p5: dict[str, Any], labels: dict[str, dict[str, Any]]) -> str:
    """E6：P 段可見詞演算法（display_rule 資料驅動）。"""
    base = _sent(labels.get("p_base", {}).get(p5.get("p_base_code")))
    visible = base
    prefix = ""
    for code in p5.get("p_addon_codes") or []:
        addon = labels.get("p_addon", {}).get(code) or {}
        rule = addon.get("display_rule") or "show_self"
        if rule == "hidden":
            continue
        if rule == "prefix_visible_term":
            prefix = _sent(addon) or addon.get("label") or ""
        else:  # show_self：取代 base 動詞（插入/卡合）
            visible = _sent(addon) or visible
    return prefix + visible


def build_narrative(cycle: dict[str, Any], labels: dict[str, dict[str, Any]], vocab: dict[str, str]) -> str:
    """cycle＝CycleIn dict；labels 見模組 docstring；vocab＝{object/from/to/hand}。"""
    seq = cycle.get("seq")
    hand = vocab.get("hand") or ""
    frm = vocab.get("from") or ""
    to = vocab.get("to") or ""
    obj = vocab.get("object") or "目標物"
    g2 = cycle.get("g2") or {}
    g = _sent(labels.get("g", {}).get(g2.get("g_code"))) or "取得"

    reach0 = (cycle.get("a0") or {}).get("reach_cm") or 0
    s = hand + (("從" + frm) if frm else "") + g + _rep_suffix(g2) + "「" + obj + "」"
    if reach0:
        s += "，伸手約" + _fmt(reach0) + "公分"
    s += "。"

    if seq == "GM":
        a3 = cycle.get("a3") or {}
        p5 = cycle.get("p5") or {}
        reach3 = a3.get("reach_cm") or 0
        s += "隨後"
        if reach3:
            s += "移動約" + _fmt(reach3) + "公分"
        if a3.get("twist_deg"):
            s += ("，" if reach3 else "") + "翻轉「" + obj + "」"  # v3 dependency：A_move 含手度
        if to:
            s += ("，" if (reach3 or a3.get("twist_deg")) else "") + "到" + to
        p_vis = _p_visible(p5, labels)
        if p_vis:
            s += "，以「" + p_vis + "」放置" + _rep_suffix(p5)
        s += "。"
    else:
        m3 = cycle.get("m3") or {}
        x4 = cycle.get("x4") or {}
        i5 = cycle.get("i5") or {}
        if to:
            s += "在" + to + "一側"
        mcs = m3.get("m_components") or []
        if mcs:
            mv = _sent(labels.get("m_verb", {}).get(mcs[0].get("verb_code"))) or "控制"
            s += "，以" + mv + _rep_suffix(m3) + "實施移動"
        x_sent = _sent(labels.get("x", {}).get(x4.get("x_code"))) if x4.get("x_code") not in (None, "x_none") else ""
        if x_sent:
            s += "，" + x_sent + _rep_suffix(x4)
        i_sent = _sent(labels.get("i", {}).get(i5.get("i_code"))) if i5.get("i_code") not in (None, "i_none") else ""
        if i_sent:
            s += "，" + i_sent + _rep_suffix(i5)
        s += "。"

    s += "最後收束返回。"
    return s
