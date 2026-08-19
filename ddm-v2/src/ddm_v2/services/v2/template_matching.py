"""範本關鍵字比對（單一實作）。

`/motion-templates/match` 端點與匯入預覽（ADR-025 D10）共用同一個 `score_keywords`——
比對邏輯只有一份，避免兩條路對同一描述給出不同命中（DISC-03「單一引擎」精神在比對面的延伸）。

**呼叫端一律用 `score_template(description, 範本物件)`，不要自己組關鍵字清單。**
比對結果會決定套用哪個範本 → 決定 `computed_tmu`，所以「關鍵字從哪來」與「怎麼比對」
同樣是決定 TMU 的一環（ADR-032 I3）。守衛只守得住這支模組；把關鍵字來源收斂進
`template_keywords()`，呼叫端就沒有插入未經覆核字串（例如機器翻譯的英文名）的縫。
"""
from __future__ import annotations

import re
from typing import Any


def score_keywords(description: str, keywords: list[str]) -> tuple[float, list[str]]:
    """關鍵字比對：命中以關鍵字長度加權（越具體越高）。中文 substring、英文 word/substring 皆可。"""
    text = (description or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    hits: list[str] = []
    score = 0.0
    for kw in keywords or []:
        k = str(kw).strip().lower()
        if not k:
            continue
        if (k in text) or (k in tokens):
            hits.append(kw)
            score += len(k)
    return score, hits


def template_keywords(t: Any) -> list[str]:
    """範本物件（ORM 列或 `nlp/linking` 用的 dict）→ 比對用的關鍵字清單。

    **比對關鍵字的唯一來源。** 只讀 `keywords` 欄；範本的其他欄（尤其是機器翻譯的
    英文名）一律不進比對面（ADR-032 I3）。
    """
    kws = t.get("keywords") if isinstance(t, dict) else getattr(t, "keywords", None)
    return [str(k) for k in (kws or [])]


def score_template(description: str, t: Any) -> tuple[float, list[str]]:
    """比對單一範本：呼叫端只給範本物件，關鍵字由本模組取（見 `template_keywords`）。"""
    return score_keywords(description, template_keywords(t))
