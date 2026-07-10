"""v2 worksheet 持久化 API：存/讀整份 WI（寫 wi_rows + most_cycles + level_entries 到 PostgreSQL）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.most_engine import SequenceError
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.worksheet import WorksheetReadOut, WorksheetSaveIn
from ddm_v2.services.v2 import worksheet_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-worksheet"])


@router.put("/worksheets/{worksheet_id}", response_model=WorksheetReadOut)
async def save_worksheet(worksheet_id: uuid.UUID, payload: WorksheetSaveIn, session: AsyncSession = Depends(get_db_session),
                         user: CurrentUser = Depends(require_role("analyst"))) -> WorksheetReadOut:
    try:
        result = await svc.save_worksheet(session, worksheet_id, payload)
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"worksheet 不存在：{worksheet_id}")
    except svc.RuleSetNotFound as e:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{e}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except svc.SimoPairInvalid as e:
        raise HTTPException(status_code=422, detail={"code": "SIMO_PAIR_INVALID", "message": str(e)})
    except RuleSetIncomplete as e:
        raise HTTPException(status_code=409, detail=str(e))
    except SequenceError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": str(e)})
    return WorksheetReadOut(**result)


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}", response_model=WorksheetReadOut)
async def read_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                         _: CurrentUser = Depends(current_user)) -> WorksheetReadOut:
    try:
        result = await svc.read_worksheet(session, worksheet_id)
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"worksheet 不存在：{worksheet_id}")
    return WorksheetReadOut(**result)


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/versions")
async def worksheet_versions(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                             _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await svc.list_versions(session, worksheet_id)
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"worksheet 不存在：{worksheet_id}")


@router.post("/worksheets/{worksheet_id}/publish")
async def publish_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                            user: CurrentUser = Depends(require_role("approver"))) -> dict:
    try:
        return await svc.publish_worksheet(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"worksheet 不存在：{worksheet_id}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/worksheets/{worksheet_id}/clone")
async def clone_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                          user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.clone_worksheet(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"worksheet 不存在：{worksheet_id}")
