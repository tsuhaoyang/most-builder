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
from ddm_v2.exceptions import NotFoundError
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
