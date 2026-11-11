"""案件清單 API：GET /api/v2/cases。

viewer+ 可讀；支援 status / site_id 篩選 + 分頁。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.schemas.v2.cases import CaseListOut
from ddm_v2.services.v2 import cases_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-cases"])


@router.get("/cases", response_model=CaseListOut)
async def list_cases(
    status: str | None = None,
    site_id: uuid.UUID | None = None,
    limit: int = Query(default=100, le=200),
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> CaseListOut:
    result = await svc.list_cases(session, status=status, site_id=site_id, limit=limit, offset=offset)
    return CaseListOut(**result)
