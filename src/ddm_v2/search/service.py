"""搜尋服務：L1（精確）+ L2（trgm）+ L3（semantic，可選）"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .adapters.null_provider import NullProvider
from .normalization import normalize
from .ports import EmbeddingProvider


@dataclass
class SearchHit:
    doc_type: str
    ref_id: str
    score: float
    match_type: Literal["text", "semantic", "fused"]
    snippet: str = field(default="")


class SearchService:
    def __init__(self, provider: EmbeddingProvider | None = None):
        self._provider = provider or NullProvider()

    async def search(
        self,
        db: AsyncSession,
        q: str,
        doc_types: list[str] | None = None,
        rule_set_id: str | None = None,
        limit: int = 10,
        caller: str | None = None,
    ) -> dict:
        """回傳 {hits: list[SearchHit], semantic: bool}"""
        q_norm = normalize(q)
        if not q_norm:
            return {"hits": [], "semantic": False}

        types_filter = ""
        params: dict = {"q": q_norm, "limit": limit}
        if doc_types:
            types_filter += " AND doc_type = ANY(:types)"
            params["types"] = doc_types
        if rule_set_id:
            types_filter += " AND (rule_set_id = :rule_set_id OR rule_set_id IS NULL)"
            params["rule_set_id"] = rule_set_id

        # personal scope 過濾：personal 模組只對 owner 可見
        if "motion_module" in (doc_types or []) or doc_types is None:
            types_filter += " AND (doc_type != 'motion_module' OR scope != 'personal' OR owner = :caller)"
            params["caller"] = caller or ""

        # L2: trgm similarity
        l2_sql = text(f"""
            SELECT doc_type, ref_id::text,
                   similarity(content_norm, :q) AS score,
                   LEFT(content_norm, 120) AS snippet
            FROM search_documents
            WHERE content_norm % :q {types_filter}
            ORDER BY score DESC
            LIMIT 20
        """)
        l2_rows = (await db.execute(l2_sql, params)).fetchall()
        hits = [
            SearchHit(r.doc_type, r.ref_id, float(r.score), "text", r.snippet)
            for r in l2_rows
        ]
        semantic = False

        # L3: embedding（若可用）
        vecs = await self._provider.embed([q_norm])
        if vecs:
            try:
                vec_str = "[" + ",".join(str(v) for v in vecs[0]) + "]"
                l3_sql = text(f"""
                    SELECT doc_type, ref_id::text,
                           1 - (embedding <=> :vec::vector) AS score,
                           LEFT(content_norm, 120) AS snippet
                    FROM search_documents
                    WHERE embedding IS NOT NULL {types_filter}
                    ORDER BY embedding <=> :vec::vector
                    LIMIT 20
                """)
                p3 = {**params, "vec": vec_str}
                l3_rows = (await db.execute(l3_sql, p3)).fetchall()
                # RRF 融合（k=60）
                l2_rank = {(r.doc_type, r.ref_id): i + 1 for i, r in enumerate(l2_rows)}
                l3_rank = {(r.doc_type, r.ref_id): i + 1 for i, r in enumerate(l3_rows)}
                all_keys = set(l2_rank) | set(l3_rank)
                rrf_scores = {
                    k: 1 / (60 + l2_rank.get(k, 1000)) + 1 / (60 + l3_rank.get(k, 1000))
                    for k in all_keys
                }
                snippets = {(r.doc_type, r.ref_id): r.snippet for r in list(l2_rows) + list(l3_rows)}
                hits = [
                    SearchHit(k[0], k[1], rrf_scores[k], "fused", snippets.get(k, ""))
                    for k in sorted(rrf_scores, key=rrf_scores.__getitem__, reverse=True)
                ]
                semantic = True
            except Exception as exc:
                import logging as _logging
                _logging.getLogger(__name__).warning("L3 語意查詢失敗，降級 L2: %s", exc)
                # hits 維持 L2 結果，semantic=False

        return {"hits": hits[:limit], "semantic": semantic}


def get_search_service() -> SearchService:
    """FastAPI Depends 用。根據 EMBEDDING_PROVIDER 環境變數選 provider。"""
    prov = os.getenv("EMBEDDING_PROVIDER", "null")
    if prov == "bge_m3_http":
        from .adapters.bge_m3_http import BgeM3HttpProvider
        return SearchService(BgeM3HttpProvider())
    return SearchService(NullProvider())
