"""v2 匯出 API：WI 1128 預覽 / Excel / LB csv / LB API 接口。

依據 system-architecture-v2 §8.1。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.most_engine import SequenceError
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.worksheet import WorksheetSaveIn
from ddm_v2.services.v2 import export_service as exp
from ddm_v2.services.v2 import worksheet_service as wsvc

router = APIRouter(prefix="/api/v2", tags=["v2-export"])


def _worksheet_not_found(worksheet_id: uuid.UUID) -> NotFoundError:
    """ADR-034 §D3/A4：裸 404 → NotFoundError 統一信封。

    detail 帶結構化 resource/id 供前端在地化組句；error.message 保留原中文字串
    （I2 語意位元級等價）。C4 已移除過渡期 ``_compat_detail`` 相容鍵。
    """
    msg = f"worksheet 不存在：{worksheet_id}"
    return NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id)})


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/export/wi-preview")
async def wi_preview(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await exp.wi_preview(session, worksheet_id)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/export/excel")
async def export_excel(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> Response:
    try:
        data = await exp.to_excel_bytes(session, worksheet_id)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="WI_{worksheet_id}.xlsx"'},
    )


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/export/lb-csv")
async def export_lb_csv(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> Response:
    try:
        text = await exp.to_lb_csv(session, worksheet_id)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)
    return Response(
        content="﻿" + text,  # BOM 讓 Excel 開 CSV 不亂碼
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="LB_{worksheet_id}.csv"'},
    )


@router.post("/worksheets/{worksheet_id}/export/lb-api")
async def export_lb_api(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await exp.lb_api_payload(session, worksheet_id)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)


# ADR-019 Option A: read=viewer+ intentional. lb-report 永遠回報告（不擋），含 E/W（Spec §8.2）
@router.get("/worksheets/{worksheet_id}/export/lb-report")
async def export_lb_report(worksheet_id: uuid.UUID, include_tasks: bool = False, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await exp.lb_export_report(session, worksheet_id, include_tasks=include_tasks)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)


# ADR-019 Option A: read=viewer+（同 lb-report）。未存檔 dry-run 預覽（ADR-035 D10 B3）
@router.post("/worksheets/{worksheet_id}/export/lb-report/preview")
async def export_lb_report_preview(
    worksheet_id: uuid.UUID,
    payload: WorksheetSaveIn,
    include_tasks: bool = False,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    try:
        return await exp.lb_preview_report(session, worksheet_id, payload, include_tasks=include_tasks)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)
    except wsvc.RuleSetNotFound as e:
        raise NotFoundError(f"rule-set 不存在：{e}", detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": str(e)})
    except wsvc.SimoPairInvalid as e:
        raise ValidationError(str(e), detail={"code": "SIMO_PAIR_INVALID", "message": str(e)})
    except RuleSetIncomplete as e:
        raise ConflictError(str(e), detail={"code": ErrorCode.RULE_SET_INCOMPLETE})
    except SequenceError as e:
        # 與 PUT /worksheets/{id} 相同映射（ADR-034 §3；I1 engine 動態碼）
        compat: dict = {"code": e.code, "message": str(e)}
        row_id = getattr(e, "row_id", None)
        if row_id is not None:
            compat["seq_no"] = getattr(e, "seq_no", None)
            compat["row_id"] = str(row_id)
        raise ValidationError(str(e), detail={**compat})


# ADR-019 Option A: read=viewer+ intentional; do NOT add ownership/created_by checks — see ADR-019
@router.get("/worksheets/{worksheet_id}/export/report.xlsx")
async def export_report_xlsx(worksheet_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> Response:
    try:
        data = await exp.to_report_xlsx_bytes(session, worksheet_id)
    except wsvc.WorksheetNotFound:
        raise _worksheet_not_found(worksheet_id)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="MOST_Report_{worksheet_id}.xlsx"'},
    )
