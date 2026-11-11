"""搜尋 API（impl-03）：GET /api/v2/search"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.search.service import get_search_service

router = APIRouter(prefix="/api/v2", tags=["search"])

VALID_TYPES = {"motion_module", "wi_row", "vocab", "worksheet"}


@router.get("/search")
async def search_api(
    q: str = Query(..., min_length=1, max_length=200),
    types: list[str] = Query(default=["motion_module"]),
    rule_set_id: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    user: CurrentUser = Depends(current_user),
    db: AsyncSession = Depends(get_db_session, scope="function"),
):
    filtered_types = [t for t in types if t in VALID_TYPES] or ["motion_module"]
    svc = get_search_service()
    result = await svc.search(db, q, filtered_types, rule_set_id, limit, caller=user.employee_no)
    return {
        "hits": [
            {
                "doc_type": h.doc_type,
                "ref_id": h.ref_id,
                "score": h.score,
                "match_type": h.match_type,
                "snippet": h.snippet,
            }
            for h in result["hits"]
        ],
        "semantic": result["semantic"],
    }
