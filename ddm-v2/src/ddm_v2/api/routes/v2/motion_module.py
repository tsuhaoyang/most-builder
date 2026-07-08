"""motion_modules API 路由（impl-04）。

路由清單：
  GET    /api/v2/motion-modules                     列表+關鍵字搜尋
  POST   /api/v2/motion-modules                     建立模組（draft）
  GET    /api/v2/motion-modules/{id}                取模組詳情（含 current version）
  PUT    /api/v2/motion-modules/{id}                改 metadata（限 draft）
  POST   /api/v2/motion-modules/{id}/publish        發布新版本
  POST   /api/v2/motion-modules/{id}/promote        升格（personal→site/global）[501 placeholder]
  GET    /api/v2/motion-modules/{id}/versions       版本歷史
  POST   /api/v2/worksheets/{wid}/rows/from-module  實體化至工序表
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.most_engine import SequenceError
from ddm_v2.schemas.v2.motion_module import (
    FromModuleRequest,
    InstantiateResponse,
    MotionModuleCreate,
    MotionModuleResponse,
    MotionModuleUpdate,
    MotionModuleVersionResponse,
    PublishRequest,
    ReorderRequest,
)
from ddm_v2.services.v2 import motion_module_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-motion-modules"])


# ── 列表 ─────────────────────────────────────────────────────────────

@router.get("/motion-modules", response_model=list[MotionModuleResponse])
async def list_modules(
    q: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(current_user),
) -> list[MotionModuleResponse]:
    return await svc.list_modules(session, user.employee_no, q=q, scope=scope, category=category)


# ── 建立 ─────────────────────────────────────────────────────────────

@router.post("/motion-modules", response_model=MotionModuleResponse, status_code=201)
async def create_module(
    payload: MotionModuleCreate,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> MotionModuleResponse:
    return await svc.create_module(session, payload, user.employee_no)


# ── 取詳情 ───────────────────────────────────────────────────────────

@router.get("/motion-modules/{module_id}", response_model=MotionModuleResponse)
async def get_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(current_user),
) -> MotionModuleResponse:
    try:
        return await svc.get_module(session, module_id)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")


# ── 排序（stub）─────────────────────────────────────────────────────
# 注意：此路由必須在 /{module_id} 路由之前定義，避免路徑衝突。

@router.put("/motion-modules/reorder", status_code=200)
async def reorder_modules(
    payload: ReorderRequest,
    _: CurrentUser = Depends(current_user),
) -> dict:
    # TODO: motion_modules 尚無 seq_no 欄位；前端在 local state 管理顯示順序。
    # 待 seq_no 欄位加入後，在此持久化 ordered_ids 對應的新順序。
    return {"ok": True}


# ── 改 metadata ──────────────────────────────────────────────────────

@router.put("/motion-modules/{module_id}", response_model=MotionModuleResponse)
async def update_module(
    module_id: uuid.UUID,
    payload: MotionModuleUpdate,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> MotionModuleResponse:
    try:
        return await svc.update_module(session, module_id, payload, user.employee_no)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")
    except svc.ModuleNotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except svc.ScopePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ── 刪除 ─────────────────────────────────────────────────────────────

@router.delete("/motion-modules/{module_id}", status_code=204)
async def delete_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> None:
    try:
        await svc.delete_module(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")
    except svc.ScopePermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except svc.ModuleIsStandard as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── 複製 ─────────────────────────────────────────────────────────────

@router.post(
    "/motion-modules/{module_id}/clone",
    response_model=MotionModuleResponse,
    status_code=201,
)
async def clone_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> MotionModuleResponse:
    try:
        return await svc.clone_module(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")


# ── 發布新版本 ───────────────────────────────────────────────────────

@router.post(
    "/motion-modules/{module_id}/publish",
    response_model=MotionModuleVersionResponse,
    status_code=201,
)
async def publish_version(
    module_id: uuid.UUID,
    payload: PublishRequest,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> MotionModuleVersionResponse:
    try:
        return await svc.publish_version(session, module_id, payload, user.employee_no)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")
    except svc.ModuleNotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except svc.RuleSetNotFound as e:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{e}")
    except svc.PublishValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": e.code,
                "row_index": e.row_index,
                "message": e.message,
            },
        )
    except SequenceError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": e.code, "message": str(e)},
        )


# ── 升格（promote）——501 placeholder，P5 後接 ADR-018 審核流 ─────────

@router.post("/motion-modules/{module_id}/promote", status_code=501)
async def promote_module(
    module_id: uuid.UUID,
    _: CurrentUser = Depends(require_role("manager")),
) -> dict:
    raise HTTPException(
        status_code=501,
        detail="promote 端點尚未實作（P5 接 ADR-018 審核流）。",
    )


# ── 版本歷史 ─────────────────────────────────────────────────────────

@router.get(
    "/motion-modules/{module_id}/versions",
    response_model=list[MotionModuleVersionResponse],
)
async def get_versions(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(current_user),
) -> list[MotionModuleVersionResponse]:
    try:
        return await svc.get_versions(session, module_id)
    except svc.ModuleNotFound:
        raise HTTPException(status_code=404, detail=f"模組不存在：{module_id}")


# ── 實體化至工序表 ───────────────────────────────────────────────────

@router.post(
    "/worksheets/{worksheet_id}/rows/from-module",
    response_model=InstantiateResponse,
    status_code=201,
)
async def instantiate_to_worksheet(
    worksheet_id: uuid.UUID,
    payload: FromModuleRequest,
    session: AsyncSession = Depends(get_db_session),
    user: CurrentUser = Depends(require_role("IE")),
) -> InstantiateResponse:
    try:
        result = await svc.instantiate_to_worksheet(
            session, worksheet_id, payload, user.employee_no
        )
    except svc.WorksheetNotFound:
        raise HTTPException(status_code=404, detail=f"工序表不存在：{worksheet_id}")
    except svc.WorksheetPermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except svc.ModuleNotFound:
        raise HTTPException(
            status_code=404, detail=f"模組不存在：{payload.module_id}"
        )
    except svc.ModuleRetired as e:
        raise HTTPException(status_code=409, detail=str(e))
    except svc.ModuleVersionNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except svc.RuleSetNotFound as e:
        raise HTTPException(status_code=409, detail=str(e))

    return InstantiateResponse(
        new_rows=result["new_rows"],
        tmu_drift=result["tmu_drift"],
    )
