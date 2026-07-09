from __future__ import annotations

import re


def normalize(text: str) -> str:
    """P0 版本：去除標點、摺疊空白。impl-05 實作後替換。"""
    text = re.sub(r"[，。、：；「」【】()（）\-_]", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def build_content_norm(
    name: str,
    description: str = "",
    keywords: list[str] | None = None,
) -> str:
    parts = [name, description] + (keywords or [])
    return normalize(" ".join(p for p in parts if p))
