"""範本關鍵字比對（單一實作）。

`/motion-templates/match` 端點與匯入預覽（ADR-025 D10）共用同一個 `score_keywords`——
比對邏輯只有一份，避免兩條路對同一描述給出不同命中（DISC-03「單一引擎」精神在比對面的延伸）。
"""
from __future__ import annotations

import re


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
