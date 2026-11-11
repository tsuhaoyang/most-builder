"""NLP normalization：NFKC → OpenCC(s2twp) → 空白收斂 → 英文小寫。

純函數；無狀態；thread-safe（OpenCC converter 物件線程安全）。
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# 解析輸入長度上限（單一權威；apply_mapping 警告、parse 入口拒收都引用這個值）。
#
# 為什麼是 2000：
# 1. `normalize_with_map` 用 SequenceMatcher(autojunk=False)，高重複輸入是最壞情況
#    ——實測（2026-08-15，本機 3.11）病理輸入 800 字元 ≈ 0.18s、1600 字元 ≈ 1.4s，
#    成長超過平方；Excel 單格上限 32,767 字元會把 event loop 卡住分鐘級。
#    2000 字元把病理最壞情況鎖在 ≈2–3s，落在 PARSE_CPU_TIMEOUT_S 內。
# 2. 與既有對外契約一致：互動端點 NLDraftIn.text 的 max_length 本來就是 2000，
#    批次路徑沿用同一上限，不另立第二個數字。
# 3. 真實 WI 步驟描述遠低於 200 字元；2000 已是 10 倍以上的餘裕，擋下的只有
#    病理輸入與貼錯欄位的整段文章。
MAX_PARSE_TEXT_CHARS = 2000

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


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """回傳 (normalized_text, offset_map)。

    offset_map[i] = normalized 第 i 個字元對應的 raw text index。
    正規化字串與 ``normalize()`` 位元級相等；map 長度等於 normalized 長度且單調非遞減。
    """
    norm = normalize(text)
    if not norm:
        return "", []
    if not text:
        # normalize("") == ""；上面已處理。理論不可達但防守。
        return norm, [0] * len(norm)

    offset_map: list[int] = []
    sm = SequenceMatcher(a=text, b=norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                offset_map.append(i1 + k)
        elif tag == "replace":
            src_span = max(i2 - i1, 1)
            for k in range(j2 - j1):
                offset_map.append(i1 + min(k, src_span - 1))
        elif tag == "insert":
            src = min(i1, len(text) - 1) if text else 0
            for _ in range(j2 - j1):
                offset_map.append(src)
        # delete: raw 字元被丟掉，不產生 map 項目

    if len(offset_map) != len(norm):
        logger.error(
            "normalize_with_map alignment failed: raw_len=%s norm_len=%s map_len=%s",
            len(text),
            len(norm),
            len(offset_map),
        )
        raise RuntimeError("normalize_with_map alignment failed")

    # 強制單調非遞減（UI highlight 安全）
    for i in range(1, len(offset_map)):
        if offset_map[i] < offset_map[i - 1]:
            offset_map[i] = offset_map[i - 1]

    return norm, offset_map
