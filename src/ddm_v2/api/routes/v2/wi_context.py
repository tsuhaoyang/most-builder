"""正式工序 context API（R3a）。

GET/PUT/DELETE /api/v2/wi-rows/{wi_row_id}/context
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.schemas.v2.wi_context import WiContextOut, WiContextUpsertIn
from ddm_v2.services.v2 import wi_context_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-wi-context"])


@router.get("/wi-rows/{wi_row_id}/context", response_model=WiContextOut)
async def get_wi_row_context(
    wi_row_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> WiContextOut:
    return WiContextOut(**await svc.get_context(session, wi_row_id))


@router.put("/wi-rows/{wi_row_id}/context", response_model=WiContextOut)
async def put_wi_row_context(
    wi_row_id: uuid.UUID,
    payload: WiContextUpsertIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiContextOut:
    return WiContextOut(
        **await svc.upsert_context(
            session,
            wi_row_id,
            schema_version=payload.schema_version,
            context_data=payload.context_data,
            source=payload.source,
            actor=user.employee_no,
        )
    )


@router.delete("/wi-rows/{wi_row_id}/context", status_code=204)
async def delete_wi_row_context(
    wi_row_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> None:
    await svc.delete_context(session, wi_row_id)
