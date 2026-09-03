"""v2 worksheet 持久化 API：存/讀整份 WI（寫 wi_rows + most_cycles + level_entries 到 PostgreSQL）。"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.most_engine import SequenceError
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.worksheet import WorksheetReadOut, WorksheetSaveIn
from ddm_v2.services.v2 import worksheet_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-worksheet"])


@router.put("/worksheets/{worksheet_id}", response_model=WorksheetReadOut)
async def save_worksheet(worksheet_id: uuid.UUID, payload: WorksheetSaveIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                         user: CurrentUser = Depends(require_role("analyst"))) -> WorksheetReadOut:
    try:
        result = await svc.save_worksheet(
            session, worksheet_id, payload, edited_by=user.employee_no
        )
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    except svc.RuleSetNotFound as e:
        msg = f"rule-set 不存在：{e}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    except svc.NotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})
    except svc.SimoPairInvalid as e:
        compat = {"code": "SIMO_PAIR_INVALID", "message": str(e)}
        raise ValidationError(
            str(e),
            detail={"code": ErrorCode.SIMO_PAIR_INVALID, "_compat_detail": compat},
        )
    except RuleSetIncomplete as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.RULE_SET_INCOMPLETE, "_compat_detail": msg})
    except SequenceError as e:
        # `svc.RowSequenceError` 會多掛 seq_no／row_id（存檔迴圈裡指得出是哪一列）；
        # 其他 SequenceError 沒有這兩個屬性 → 維持原本的兩鍵 detail。
        # I1：engine e.code 動態讀取，不常數化、不碰 engine（ADR-034 §3）。
        compat: dict = {"code": e.code, "message": str(e)}
        row_id = getattr(e, "row_id", None)
        if row_id is not None:
            compat["seq_no"] = getattr(e, "seq_no", None)
            compat["row_id"] = str(row_id)
        raise ValidationError(str(e), detail={"code": e.code, "_compat_detail": compat})
    return WorksheetReadOut(**result)


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}", response_model=WorksheetReadOut)
async def read_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                         _: CurrentUser = Depends(current_user)) -> WorksheetReadOut:
    try:
        result = await svc.read_worksheet(session, worksheet_id)
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    return WorksheetReadOut(**result)


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/versions")
async def worksheet_versions(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                             _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await svc.list_versions(session, worksheet_id)
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})


@router.post("/worksheets/{worksheet_id}/level/validate")
async def validate_worksheet_level(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """R2b：對目前 worksheet revision 做 Level 驗證並 append validation run。"""
    from ddm_v2.services.v2.level_validation_service import validate_and_persist

    try:
        return await validate_and_persist(
            session, worksheet_id, trigger="interactive", actor=user.employee_no
        )
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    # ConflictError → main.py（LEVEL_POLICY_MISMATCH 等）


@router.post("/worksheets/{worksheet_id}/publish")
async def publish_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                            user: CurrentUser = Depends(require_role("approver"))) -> dict:
    try:
        return await svc.publish_worksheet(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    except svc.NotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})
    # ConflictError / ValidationError → main.py（LEVEL_VALIDATION_* / LEVEL_POLICY_MISMATCH）


@router.post("/worksheets/{worksheet_id}/clone")
async def clone_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                          user: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.clone_worksheet(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})


@router.post("/worksheets/{worksheet_id}/retire")
async def retire_worksheet(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                           user: CurrentUser = Depends(require_role("admin"))) -> dict:
    try:
        return await svc.retire_worksheet(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        msg = f"worksheet 不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    except svc.NotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})
