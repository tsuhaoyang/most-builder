"""英文 METHOD 敘事產生：與 `narrative.py` **平行**的獨立組句系統（ADR-032 D7）。

**改這裡通常必須也改 `narrative.py`，反之亦然**（ADR-032 R3）：兩檔共用同一份輸入
（cycle ＋ labels ＋ vocab），但組句規則各自獨立。`tests/unit/test_narrative.py` 以
雙語參數化的語意不變式守著兩邊不漂移（D8）——只改一邊會缺一項不變式而紅。

**為什麼不是把中文句子翻譯、也不是在 `narrative.py` 加 `if locale ==` 分支**（D7.3）：
1. 連接詞歸屬不同——中文把「並」寫進資料（X 7/11、I 8/9 條的 `label_zh` 以「並」開頭），
   英文的連接詞必須由**樣板**生成，資料只給乾淨片語。
2. `display_rule='prefix_visible_term'` 的「前綴」是中文語序假設；英文的對應可見詞落在
   **動詞之後**（「以『對準組』放置」→ "assemble it, aligned to within 4 mm"），
   同一個欄位值在兩套樣板要被解讀成不同位置。
3. 句型骨架不同——英文工業 METHOD 慣例是**祈使句**加手別前綴（"RH: grasp…"），
   沿用中文主謂會得到 "The right hand grasps…" 這種沒有工廠會用的句子。

`sentence_text_en` 的資料契約（與 `sentence_text_zh` **不同**，見 D7.3.1）：
- **不含連接詞**（不要寫 "and …"／"while …"）——連接詞由本模組生成。
- G：**及物動詞本身**，受詞由樣板自 vocab 填入真實名詞（"grasp" → "grasp the rack"）。
- P／M：**自足的動詞片語，含代名詞受詞**（"hold it in place"、"press the button"）——
  受詞在第一句已經以真實名詞introduce過，之後改用代名詞才自然，且 `m_btn`／`m_screw`
  這類選項本來就自帶受詞，樣板無法一律補 "it"。
- X：**動名詞**片語（"dispensing glue"），樣板補 "while"。
- I：**過去分詞**片語（"aligned to the point"），樣板不補連接詞（D7.4 案例 3：
  X 的同時性與 I 的視覺對準在英文取不同連接方式，中文則一律「並」）。

`labels` 形狀同 `narrative.py`，另需 `label_en`／`sentence_en` 兩鍵（由
`providers.load_options_from_db` 提供）。英文素材缺漏時回退中文（ADR-032 D10：
沒有 `sentence_text_en` 的素材，英文敘事只能回退中文），不留空動詞。
"""
from __future__ import annotations

from typing import Any


def _fmt(n: float | None) -> str:
    if not n:
        return ""
    return f"{n:g}"


def _sent(entry: dict[str, Any] | None) -> str:
    """英文句面的回退鏈：句面 → 標籤 → 中文句面 → 中文標籤。"""
    if not entry:
        return ""
    return (
        entry.get("sentence_en")
        or entry.get("label_en")
        or entry.get("sentence")
        or entry.get("label")
        or ""
    )


def _rep_suffix(slot: dict[str, Any] | None) -> str:
    rc = (slot or {}).get("repeat_count")
    return f" (×{int(rc)})" if rc and int(rc) > 1 else ""


def _noun(name: str) -> str:
    """句中的受詞名詞組：加定冠詞，並在安全時把首字母降為小寫。

    只有「首字除第一個字母外全小寫」才降格（Dummy DIMM → the dummy DIMM）。
    工廠詞彙充斥縮寫（DIMM／PSU／I/O 擋板／CPU 拉桿），無條件降格會產出 "dIMM"。

    先 strip 再判空：`"   ".split(maxsplit=1)` 是空 list，`if not name` 只擋得掉 ""，
    純空白會在 `[0]` 炸 IndexError。Phase C 之後敘事是**讀取時**產生的，一筆空白詞彙名
    會讓任何人讀模組/版本/工作表都 500，毒源在 `work_vocab_items` 而不在被讀的那筆資料
    （根因側的輸入驗證見 `schemas/v2/vocab.py`）。
    """
    name = (name or "").strip()
    if not name:
        return ""
    first = name.split(maxsplit=1)[0]
    if first[1:].islower():
        name = name[0].lower() + name[1:]
    return "the " + name


def _p_visible(p5: dict[str, Any], labels: dict[str, dict[str, Any]]) -> str:
    """E6 的英文解讀：`prefix_visible_term` 在英文是**後綴**，不是前綴（D7.3.2）。"""
    visible = _sent(labels.get("p_base", {}).get(p5.get("p_base_code")))
    postfix = ""
    for code in p5.get("p_addon_codes") or []:
        addon = labels.get("p_addon", {}).get(code) or {}
        rule = addon.get("display_rule") or "show_self"
        if rule == "hidden":
            continue
        if rule == "prefix_visible_term":
            postfix = _sent(addon)
        else:  # show_self：取代 base 動詞（插入/卡合）
            visible = _sent(addon) or visible
    if postfix and visible:
        return f"{visible}, {postfix}"
    return visible or postfix


def build_narrative_en(cycle: dict[str, Any], labels: dict[str, dict[str, Any]], vocab: dict[str, str]) -> str:
    """cycle＝CycleIn dict；labels 見模組 docstring；vocab＝{object/from/to/hand}。

    `vocab["hand"]` 收的是**原始手別代碼**（RH/LH/BH），不是像中文那樣預先轉好的顯示字串
    ——英文以代碼本身當祈使句前綴（D7.4 案例 4）。
    """
    seq = cycle.get("seq")
    hand = (vocab.get("hand") or "").strip()
    frm = _noun(vocab.get("from") or "")
    to = _noun(vocab.get("to") or "")
    obj = _noun(vocab.get("object") or "part")
    g2 = cycle.get("g2") or {}
    g = _sent(labels.get("g", {}).get(g2.get("g_code"))) or "get"

    reach0 = (cycle.get("a0") or {}).get("reach_cm") or 0
    first = g + (f" {obj}" if obj else "") + _rep_suffix(g2)
    if frm:
        first += f" from {frm}"          # 中文的來源片語前置於動詞，英文後置於受詞（D7.4 案例 1）
    if reach0:
        first += f", reaching ~{_fmt(reach0)} cm"
    sentences = [f"{hand}: {first}." if hand else f"{first[0].upper()}{first[1:]}."]

    parts: list[str] = []
    if seq == "GM":
        a3 = cycle.get("a3") or {}
        p5 = cycle.get("p5") or {}
        reach3 = a3.get("reach_cm") or 0
        twist = a3.get("twist_deg")
        move = f"move ~{_fmt(reach3)} cm" if reach3 else ("move" if (to or twist) else "")
        if move:
            # 中文修飾語序＝距離→手度→目的地；英文＝距離→目的地→分詞片語（D7.4 案例 2）
            if to:
                move += f" to {to}"
            if twist:
                move += f", turning {obj or 'the part'} over"
            parts.append(move)
        p_vis = _p_visible(p5, labels)
        if p_vis:
            parts.append(p_vis + _rep_suffix(p5))
        if parts:
            sentences.append("Then " + ", and ".join(parts) + ".")
    else:
        m3 = cycle.get("m3") or {}
        x4 = cycle.get("x4") or {}
        i5 = cycle.get("i5") or {}
        mcs = m3.get("m_components") or []
        if mcs:
            mv = _sent(labels.get("m_verb", {}).get(mcs[0].get("verb_code"))) or "control it"
            head = mv + _rep_suffix(m3)
            if to:
                head += f" at {to}"
            parts.append(head)
        elif to:
            parts.append(f"work at {to}")
        x_sent = _sent(labels.get("x", {}).get(x4.get("x_code"))) if x4.get("x_code") not in (None, "x_none") else ""
        if x_sent:
            parts.append("while " + x_sent + _rep_suffix(x4))
        i_sent = _sent(labels.get("i", {}).get(i5.get("i_code"))) if i5.get("i_code") not in (None, "i_none") else ""
        if i_sent:
            parts.append(i_sent + _rep_suffix(i5))
        if parts:
            sentences.append("Then " + ", ".join(parts) + ".")

    sentences.append("Finally, return to the start position.")
    return " ".join(sentences)
