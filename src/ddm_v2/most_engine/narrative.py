"""後端敘事產生：cycle + vocab 名 + rule-set 標籤/句字 → 可朗讀 METHOD 句（單一權威）。

**改這裡通常必須也改 `narrative_en.py`**（ADR-032 R3）：英文是平行的獨立組句系統，
不是本檔的分支。新增敘事規則（例如再加一個 `display_rule` 值）只改單邊，英文會靜默落後。

存檔時由此產生並存 most_cycles.narrative_zh，供匯出/讀回使用（不靠前端拼）。
依據 minimost-sequence-model-core-logic-spec §5 ＋ ADR-014 E6（v3 認證顯示規則）：
- P 附加 display_rule 三態：show_self（插入/卡合取代 base 動詞）、prefix_visible_term（對準前綴）、hidden（只計 TMU 不入句）。
- GM 移動格（slot3）含手度（twist）→ 句中插入「翻轉『object』」（v3 dependency 規則）。
- slot repeat > 1 → 動詞後綴「×N」。
- M 格的手度／腳步（`pricing_kind` ∈ `M_COMPANION_KINDS`）**不入句**：它們是字典裡與 verb
  平行的伴隨維度（`hand_degree`／`foot_step`），字典中全部沒有句面，只是 v2 把三個控制群
  壓扁成同一張 `rule_m_verbs` 才長得像替代動詞。

labels 形狀（由 providers.load_options_from_db 提供）：
  {"g": {code: {"label", "sentence"}}, "p_base": {...}, "p_addon": {code: {"label", "sentence", "display_rule"}},
   "m_verb": {...}, "x": {...}, "i": {...}}
sentence 為 NULL 時回退 label（V1 資料相容）。**這個回退是「缺句面」的補救，不是「不入句」
的表達**——真正要排除的選項各有顯式機制（P 附加＝`display_rule='hidden'`、X/I＝`x_none`／
`i_none` 哨兵、M 伴隨維度＝本檔的 `pricing_kind` 判斷），不靠句面留空來達成。
"""
from __future__ import annotations

from typing import Any

from ddm_v2.most_engine.rule_set_data import M_COMPANION_KINDS

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


def _m_verb_entry(m3: dict[str, Any], labels: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """M 段的敘事動詞＝第一顆**非伴隨維度**的分量；整格沒有動詞 → None（M 子句整段不出現）。

    與 `narrative_en._m_verb_entry` 是刻意的平行實作（ADR-032 R3／D8），共用的只有
    `M_COMPANION_KINDS` 這個定義。未知碼（不在 labels 裡）視為動詞，維持既有的「回退成
    泛稱動詞」行為——那是素材缺漏，不是語意上不該入句。
    """
    for comp in m3.get("m_components") or []:
        entry = labels.get("m_verb", {}).get(comp.get("verb_code"))
        if (entry or {}).get("pricing_kind") in M_COMPANION_KINDS:
            continue
        return entry or {}
    return None


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
    # 空白防呆與 `narrative_en._noun()` 對齊（ADR-032 R3）：純空白詞彙名若原樣入句，
    # 中文會產出「抓握「   」」這種空白受詞並落盤、跟著匯出。`obj` 必須**先 strip 再回退**
    # ——`"   "` 是 truthy，順序反了會繞過「目標物」而讓受詞整個消失。
    # 此 strip 只影響入口驗證已擋掉、DB 零存量的空白輸入；對任何實際資料位元級不變（ADR-032 I2）。
    hand = (vocab.get("hand") or "").strip()
    frm = (vocab.get("from") or "").strip()
    to = (vocab.get("to") or "").strip()
    obj = (vocab.get("object") or "").strip() or "目標物"
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
        # 子句先收進 list 再以「，」串接（與 `narrative_en` 的 `parts` 同構，ADR-032 R3）。
        # 逐句 `s += "，" + ...` 的寫法會在**第一個出現的子句前面**留一個多餘的逗號：
        # 沒有 `to`、M 又沒有動詞時就是「…伸手約30公分。，刷條形碼，並檢查。」。
        # 這是既有缺陷（與英文化無關），但 M 伴隨維度不入句之後這條路更常被走到。
        parts: list[str] = []
        if to:
            parts.append("在" + to + "一側")
        mv_entry = _m_verb_entry(m3, labels)
        if mv_entry is not None:
            mv = _sent(mv_entry) or "控制"
            parts.append("以" + mv + _rep_suffix(m3) + "實施移動")
        x_sent = _sent(labels.get("x", {}).get(x4.get("x_code"))) if x4.get("x_code") not in (None, "x_none") else ""
        if x_sent:
            parts.append(x_sent + _rep_suffix(x4))
        i_sent = _sent(labels.get("i", {}).get(i5.get("i_code"))) if i5.get("i_code") not in (None, "i_none") else ""
        if i_sent:
            parts.append(i_sent + _rep_suffix(i5))
        if parts:                      # 一個子句都沒有就不要多吐一個句號（原本會收成「。。」）
            s += "，".join(parts) + "。"

    s += "最後收束返回。"
    return s
