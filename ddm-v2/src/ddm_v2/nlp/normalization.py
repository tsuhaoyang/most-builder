"""NLP normalization：NFKC → OpenCC(s2twp) → 空白收斂 → 英文小寫。

純函數；無狀態；thread-safe（OpenCC converter 物件線程安全）。
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

try:
    import opencc as _opencc_mod
    _converter = _opencc_mod.OpenCC("s2twp")
except Exception as exc:
    # opencc-python-reimplemented is a declared runtime dependency; fail loudly
    # rather than silently degrading normalisation output.
    logger.critical("Failed to initialize OpenCC('s2twp'): %s", exc)
    raise RuntimeError(f"opencc initialization failed: {exc}") from exc


def normalize(text: str) -> str:
    """NFKC → OpenCC s2twp（若可用）→ 空白收斂 → 英文小寫。

    規則：
    - NFKC：全形英數/標點 → ASCII、正規化 unicode 組合字元
    - OpenCC s2twp：簡體中文 → 繁體中文（台灣習慣用字），已是繁體者不變
    - 空白收斂：連續空白（不含換行）摺疊為單一空格，首尾去除
    - 英文小寫：ASCII 字母轉小寫（中文不受影響）
    """
    text = unicodedata.normalize("NFKC", text)
    text = _converter.convert(text)
    text = re.sub(r"[^\S\n]+", " ", text).strip().lower()
    return text
