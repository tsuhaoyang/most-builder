"""Search 正規化工具——委派至 nlp.normalization（impl-05 落地）。

所有正規化路徑（search 投影、parser 入口、同義詞寫入）統一過同一函數，
確保 DB 中的 synonym_norm 與查詢時的 normalize(query) 結果一致。
"""
from __future__ import annotations

from ddm_v2.nlp.normalization import normalize as _nlp_normalize


def normalize(text: str) -> str:
    """NFKC → OpenCC(s2twp) → 空白收斂 → 英文小寫（委派至 nlp.normalization）。"""
    return _nlp_normalize(text)


def build_content_norm(
    name: str,
    description: str = "",
    keywords: list[str] | None = None,
) -> str:
    """多欄位串接後正規化（供 search_documents.content_norm 欄位寫入使用）。"""
    parts = [name, description] + (keywords or [])
    return normalize(" ".join(p for p in parts if p))
