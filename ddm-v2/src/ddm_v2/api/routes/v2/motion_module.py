"""motion_modules API 路由（impl-04）。

路由清單：
  GET    /api/v2/motion-modules                          列表+關鍵字搜尋
  POST   /api/v2/motion-modules                          建立模組（draft）
  GET    /api/v2/motion-modules/{id}                     取模組詳情（含 current version）
  PUT    /api/v2/motion-modules/{id}                     改 metadata（限 draft）
  DELETE /api/v2/motion-modules/{id}                     刪除模組
  POST   /api/v2/motion-modules/{id}/clone               複製模組
  POST   /api/v2/motion-modules/{id}/publish             發布新版本
  POST   /api/v2/motion-modules/{id}/versions/from-rows  apply-back（工序表同步回模組庫）
  PUT    /api/v2/motion-modules/{id}/rows/{row_index}    row 級編輯 → 重算 → 發新版本（ADR-022 A-2）
  POST   /api/v2/motion-modules/{id}/rows/reorder        row 重排 → 發新版本（ADR-022 A-2）
  DELETE /api/v2/motion-modules/{id}/rows/{row_index}    row 刪除 → 重算 → 發新版本（ADR-022 A-2）
  POST   /api/v2/motion-modules/{id}/promote             升格（personal→site/global）[501 placeholder]
  GET    /api/v2/motion-modules/{id}/versions            版本歷史
  PUT    /api/v2/motion-modules/reorder                  排序（analyst 以上）
  POST   /api/v2/worksheets/{wid}/rows/from-module       實體化至工序表
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from ddm_v2.most_engine import SequenceError
from ddm_v2.schemas.v2.motion_module import (
    FromModuleRequest,
    InstantiateResponse,
    ModuleRowIn,
    MotionModuleCreate,
    MotionModuleResponse,
    MotionModuleUpdate,
    MotionModuleVersionResponse,
    PublishRequest,
    ReorderRequest,
    RowsReorderRequest,
    VersionFromRowsRequest,
)
from ddm_v2.services.v2 import motion_module_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-motion-modules"])


# ── 列表 ─────────────────────────────────────────────────────────────

@router.get("/motion-modules", response_model=list[MotionModuleResponse])
async def list_modules(
    q: str | None = None,
    scope: str | None = None,
    category: str | None = None,
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(current_user),
) -> list[MotionModuleResponse]:
    return await svc.list_modules(
        session, user.employee_no, q=q, scope=scope, category=category, status=status
    )


# ── 建立 ─────────────────────────────────────────────────────────────

@router.post("/motion-modules", response_model=MotionModuleResponse, status_code=201)
async def create_module(
    payload: MotionModuleCreate,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleResponse:
    try:
        return await svc.create_module(session, payload, user.employee_no, user.level)
    except svc.ScopePermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "create", "_compat_detail": msg}) from None


# ── 取詳情 ───────────────────────────────────────────────────────────

@router.get("/motion-modules/{module_id}", response_model=MotionModuleResponse)
async def get_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(current_user),
) -> MotionModuleResponse:
    try:
        # SM-1：傳入 user.employee_no 供 service 進行 personal scope 能見度檢查
        return await svc.get_module(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None


# ── 排序（stub）─────────────────────────────────────────────────────
# 注意：此路由必須在 /{module_id} 路由之前定義，避免路徑衝突。

@router.put("/motion-modules/reorder", status_code=200)
async def reorder_modules(
    payload: ReorderRequest,
    # SM-6：reorder 需要 analyst 以上角色（修改 module 顯示順序屬 analyst 工作域）。
    _: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    # TODO: motion_modules 尚無 seq_no 欄位；前端在 local state 管理顯示順序。
    # 待 seq_no 欄位加入後，在此持久化 ordered_ids 對應的新順序。
    return {"ok": True}


# ── 改 metadata ──────────────────────────────────────────────────────

@router.put("/motion-modules/{module_id}", response_model=MotionModuleResponse)
async def update_module(
    module_id: uuid.UUID,
    payload: MotionModuleUpdate,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleResponse:
    try:
        # SM-3：傳入 user.level 供 service 進行 scope escalation 檢查
        return await svc.update_module(session, module_id, payload, user.employee_no, user.level)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None
    except svc.ModuleNotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.ScopePermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "modify", "_compat_detail": msg}) from None


# ── 刪除 ─────────────────────────────────────────────────────────────

@router.delete("/motion-modules/{module_id}", status_code=204)
async def delete_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> None:
    try:
        await svc.delete_module(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None
    except svc.ScopePermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "delete", "_compat_detail": msg}) from None
    except svc.ModuleIsStandard as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None


# ── 複製 ─────────────────────────────────────────────────────────────

@router.post(
    "/motion-modules/{module_id}/clone",
    response_model=MotionModuleResponse,
    status_code=201,
)
async def clone_module(
    module_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleResponse:
    try:
        return await svc.clone_module(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None


# ── 發布新版本 ───────────────────────────────────────────────────────

@router.post(
    "/motion-modules/{module_id}/publish",
    response_model=MotionModuleVersionResponse,
    status_code=201,
)
async def publish_version(
    module_id: uuid.UUID,
    payload: PublishRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleVersionResponse:
    try:
        return await svc.publish_version(session, module_id, payload, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None
    except svc.ModuleNotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.ScopePermissionError as e:
        # SM-5：publish 時的 ownership guard → 403
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "publish", "_compat_detail": msg}) from None
    except svc.RuleSetNotFound as e:
        msg = f"rule-set 不存在：{e}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": str(e), "_compat_detail": msg}) from None
    except svc.PublishValidationError as e:
        compat = {"code": e.code, "row_index": e.row_index, "message": e.message}
        raise ValidationError(e.message, detail={**compat, "_compat_detail": compat}) from e
    except SequenceError as e:
        # I1：engine SequenceError 的 code 維持動態讀取（不常數化、不碰 engine）。
        compat = {"code": e.code, "message": str(e)}
        raise ValidationError(compat["message"], detail={**compat, "_compat_detail": compat}) from e


# ── apply-back：從工序表列同步回模組庫（SM-7）────────────────────────

@router.post(
    "/motion-modules/{module_id}/versions/from-rows",
    response_model=MotionModuleVersionResponse,
    status_code=201,
)
async def create_version_from_rows(
    module_id: uuid.UUID,
    payload: VersionFromRowsRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleVersionResponse:
    """apply-back：把已修改的 rows 同步回模組，建立新版本（F-03b §3）。"""
    try:
        return await svc.create_version_from_rows(session, module_id, payload, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None
    except svc.ModuleNotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.ScopePermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "publish", "_compat_detail": msg}) from None
    except svc.RuleSetNotFound as e:
        msg = f"rule-set 不存在：{e}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": str(e), "_compat_detail": msg}) from None
    except svc.PublishValidationError as e:
        compat = {"code": e.code, "row_index": e.row_index, "message": e.message}
        raise ValidationError(e.message, detail={**compat, "_compat_detail": compat}) from e
    except SequenceError as e:
        # I1：engine SequenceError 的 code 維持動態讀取（不常數化、不碰 engine）。
        compat = {"code": e.code, "message": str(e)}
        raise ValidationError(compat["message"], detail={**compat, "_compat_detail": compat}) from e


# ── row 級操作（ADR-022 A-2：WI 微調 = Inspector 後端）───────────────

async def _run_row_op(coro) -> MotionModuleVersionResponse:
    """row 級操作共用錯誤對映（404/409/403/422）。"""
    try:
        return await coro
    except svc.ModuleNotFound as e:
        msg = f"模組不存在：{e}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(e), "_compat_detail": msg}) from None
    except svc.ModuleVersionNotFound as e:
        msg = str(e)
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module_version", "id": str(e), "_compat_detail": msg}) from None
    except svc.ModuleRowNotFound as e:
        msg = str(e)
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module_row", "id": str(e), "_compat_detail": msg}) from None
    except svc.ModuleNotEditable as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.ScopePermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "module", "action": "publish", "_compat_detail": msg}) from None
    except svc.RuleSetNotFound as e:
        msg = f"rule-set 不存在：{e}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": str(e), "_compat_detail": msg}) from None
    except svc.PublishValidationError as e:
        compat = {"code": e.code, "row_index": e.row_index, "message": e.message}
        raise ValidationError(e.message, detail={**compat, "_compat_detail": compat}) from e
    except SequenceError as e:
        # I1：engine SequenceError 的 code 維持動態讀取（不常數化、不碰 engine）。
        compat = {"code": e.code, "message": str(e)}
        raise ValidationError(compat["message"], detail={**compat, "_compat_detail": compat}) from e


@router.put(
    "/motion-modules/{module_id}/rows/{row_index}",
    response_model=MotionModuleVersionResponse,
)
async def update_module_row(
    module_id: uuid.UUID,
    row_index: int,
    payload: ModuleRowIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleVersionResponse:
    """替換單列 → 引擎重算全表 → 發新版本（回新版本 detail）。"""
    return await _run_row_op(
        svc.update_row(session, module_id, row_index, payload, user.employee_no)
    )


@router.post(
    "/motion-modules/{module_id}/rows/reorder",
    response_model=MotionModuleVersionResponse,
)
async def reorder_module_rows(
    module_id: uuid.UUID,
    payload: RowsReorderRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleVersionResponse:
    """重排 rows → 發新版本。ordered_indexes 須為 0..n-1 完整排列（否則 422）。"""
    return await _run_row_op(
        svc.reorder_rows(session, module_id, payload.ordered_indexes, user.employee_no)
    )


@router.delete(
    "/motion-modules/{module_id}/rows/{row_index}",
    response_model=MotionModuleVersionResponse,
)
async def delete_module_row(
    module_id: uuid.UUID,
    row_index: int,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> MotionModuleVersionResponse:
    """刪除單列 → 重算 → 發新版本；刪到 0 列 → 422（WI 至少 1 動作）。"""
    return await _run_row_op(
        svc.delete_row(session, module_id, row_index, user.employee_no)
    )


# ── 升格（promote）——501 placeholder，P5 後接 ADR-018 審核流 ─────────

@router.post("/motion-modules/{module_id}/promote", status_code=501)
async def promote_module(
    module_id: uuid.UUID,
    _: CurrentUser = Depends(require_role("approver")),
) -> dict:
    # ADR-034 §A4 batch 5：501（Not Implemented）是「端點尚未存在」的路由級佔位，
    # 不是 domain 錯誤契約的一環（無對應 DomainError 家族），故維持裸 HTTPException。
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
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(current_user),
) -> list[MotionModuleVersionResponse]:
    try:
        # SM-1 gap fix：傳入 user.employee_no 供 service 進行 personal scope 能見度檢查
        return await svc.get_versions(session, module_id, user.employee_no)
    except svc.ModuleNotFound:
        msg = f"模組不存在：{module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(module_id), "_compat_detail": msg}) from None


# ── 實體化至工序表 ───────────────────────────────────────────────────

@router.post(
    "/worksheets/{worksheet_id}/rows/from-module",
    response_model=InstantiateResponse,
    status_code=201,
)
async def instantiate_to_worksheet(
    worksheet_id: uuid.UUID,
    payload: FromModuleRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> InstantiateResponse:
    try:
        result = await svc.instantiate_to_worksheet(
            session, worksheet_id, payload, user.employee_no
        )
    except svc.WorksheetNotFound:
        msg = f"工序表不存在：{worksheet_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id), "_compat_detail": msg}) from None
    except svc.WorksheetPermissionError as e:
        msg = str(e)
        raise ForbiddenError(msg, detail={"code": ErrorCode.FORBIDDEN, "resource": "worksheet", "action": "instantiate", "_compat_detail": msg}) from None
    except svc.ModuleNotFound:
        msg = f"模組不存在：{payload.module_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module", "module_id": str(payload.module_id), "_compat_detail": msg}) from None
    except svc.ModuleRetired as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.ModuleVersionNotFound as e:
        msg = str(e)
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "module_version", "id": str(e), "_compat_detail": msg}) from None
    except svc.RuleSetNotFound as e:
        msg = str(e)
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg}) from None
    except svc.PublishValidationError as e:
        # 版本快照內 simo_pair_index 非法（舊資料/手改 DB）→ 明確報錯，不靜默當主列
        compat = {"code": e.code, "row_index": e.row_index, "message": e.message}
        raise ValidationError(e.message, detail={**compat, "_compat_detail": compat}) from e

    return InstantiateResponse(
        new_rows=result["new_rows"],
        tmu_drift=result["tmu_drift"],
        skipped_vocab_missing=result.get("skipped_vocab_missing", 0),
        revision_no=result.get("revision_no"),
        content_hash=result.get("content_hash"),
    )
