"""WI Set Project API 路由。

路由清單：
  GET    /api/v2/wi-set-projects                               列所有專案（viewer+）
  POST   /api/v2/wi-set-projects                               建立專案（analyst+）
  GET    /api/v2/wi-set-projects/{project_id}                  取單一專案含條目（viewer+）
  PUT    /api/v2/wi-set-projects/{project_id}                  更新 metadata（analyst+）
  DELETE /api/v2/wi-set-projects/{project_id}                  刪除（analyst+，限 draft）
  POST   /api/v2/wi-set-projects/{project_id}/items            新增條目（analyst+）
  DELETE /api/v2/wi-set-projects/{project_id}/items/{item_id}  移除條目（analyst+）
  PUT    /api/v2/wi-set-projects/{project_id}/items/reorder    重排序（analyst+）
  POST   /api/v2/wi-set-projects/{project_id}/duplicate        複製專案（analyst+）
    POST   /api/v2/wi-set-projects/{project_id}/instantiate      建立分析案件並實體化 WI（analyst+）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.models.v2.motion_module import MotionModule, MotionModuleVersion
from ddm_v2.models.v2.wi_set import WiSetItem, WiSetProject
from ddm_v2.schemas.v2.wi_set import (
    ReorderRequest,
    WiSetInstantiateIn,
    WiSetInstantiateOut,
    WiSetItemCreate,
    WiSetItemOut,
    WiSetProjectCreate,
    WiSetProjectOut,
    WiSetProjectUpdate,
)
from ddm_v2.services.v2 import wi_set_service

router = APIRouter(prefix="/api/v2", tags=["v2-wi-set"])

# ── 內部工具 ──────────────────────────────────────────────────────────


async def _resolve_template_snapshots(
    session: AsyncSession, wi_template_id: uuid.UUID
) -> dict:
    """由 motion module（＋current version）解析快照欄（F-02a 伺服器端快照）。

    module 不存在 → 404。尚無發布版本（current_version=0）→ 計數/TMU 皆 0。
    """
    module = await session.get(MotionModule, wi_template_id)
    if module is None:
        msg = f"組件模組不存在：{wi_template_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    version: MotionModuleVersion | None = None
    if module.current_version > 0:
        version = (
            await session.execute(
                select(MotionModuleVersion).where(
                    MotionModuleVersion.module_id == module.id,
                    MotionModuleVersion.version_no == module.current_version,
                )
            )
        ).scalar_one_or_none()
    # 值權威：total_seconds 直接讀引擎 publish 時算好的 version.total_seconds
    # （Numeric(12,4)），不在 route 內重算 TMU→秒。
    return {
        "wi_name_snapshot": module.name_zh,
        "wi_code_snapshot": None,  # motion_modules 尚無 code 欄
        "action_count_snapshot": len(version.rows) if version is not None else 0,
        "total_tmu_snapshot": float(version.total_tmu) if version is not None else 0.0,
        "total_seconds_snapshot": (
            float(version.total_seconds) if version is not None else 0.0
        ),
    }


async def _get_project_or_404(
    session: AsyncSession, project_id: uuid.UUID
) -> WiSetProject:
    result = await session.execute(
        select(WiSetProject)
        .where(WiSetProject.id == project_id)
        .options(selectinload(WiSetProject.items))
    )
    project = result.scalar_one_or_none()
    if project is None:
        msg = f"專案不存在：{project_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    return project


# ── 列表 ─────────────────────────────────────────────────────────────


@router.get("/wi-set-projects", response_model=list[WiSetProjectOut])
async def list_projects(
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[WiSetProjectOut]:
    stmt = select(WiSetProject).options(selectinload(WiSetProject.items))
    if status is not None:
        stmt = stmt.where(WiSetProject.status == status)
    stmt = stmt.order_by(WiSetProject.created_at.desc())
    rows = (await session.execute(stmt)).scalars().all()
    return [WiSetProjectOut.model_validate(r) for r in rows]


# ── 建立 ─────────────────────────────────────────────────────────────


@router.post("/wi-set-projects", response_model=WiSetProjectOut, status_code=201)
async def create_project(
    payload: WiSetProjectCreate,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiSetProjectOut:
    # 衝碼檢查
    existing = (
        await session.execute(
            select(WiSetProject).where(
                WiSetProject.project_code == payload.project_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        msg = f"project_code 已存在：{payload.project_code}"
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})
    project = WiSetProject(
        project_code=payload.project_code,
        name=payload.name,
        site=payload.site,
        bu=payload.bu,
        process=payload.process,
        family=payload.family,
        model=payload.model,
        description=payload.description,
        status="draft",
        created_by=user.employee_no,
    )
    session.add(project)
    await session.flush()
    await session.refresh(project, ["items"])
    return WiSetProjectOut.model_validate(project)


# ── 取單一 ───────────────────────────────────────────────────────────


@router.get("/wi-set-projects/{project_id}", response_model=WiSetProjectOut)
async def get_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> WiSetProjectOut:
    project = await _get_project_or_404(session, project_id)
    return WiSetProjectOut.model_validate(project)


# ── 更新 metadata ─────────────────────────────────────────────────────


@router.put("/wi-set-projects/{project_id}", response_model=WiSetProjectOut)
async def update_project(
    project_id: uuid.UUID,
    payload: WiSetProjectUpdate,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> WiSetProjectOut:
    project = await _get_project_or_404(session, project_id)

    # 若要換 project_code，先做唯一性檢查
    if payload.project_code is not None and payload.project_code != project.project_code:
        clash = (
            await session.execute(
                select(WiSetProject).where(
                    WiSetProject.project_code == payload.project_code
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            msg = f"project_code 已存在：{payload.project_code}"
            raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    await session.flush()
    await session.refresh(project, ["items"])
    return WiSetProjectOut.model_validate(project)


# ── 刪除（限 draft）─────────────────────────────────────────────────


@router.delete("/wi-set-projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> None:
    project = await _get_project_or_404(session, project_id)
    if project.status != "draft":
        msg = f"只有 draft 狀態的專案可以刪除（目前：{project.status}）"
        raise ConflictError(msg, detail={"code": ErrorCode.CONFLICT, "_compat_detail": msg})
    await session.delete(project)
    await session.flush()


# ── 新增條目 ─────────────────────────────────────────────────────────


@router.post(
    "/wi-set-projects/{project_id}/items",
    response_model=WiSetItemOut,
    status_code=201,
)
async def add_item(
    project_id: uuid.UUID,
    payload: WiSetItemCreate,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> WiSetItemOut:
    """新增條目。

    快照規則（F-02a，值權威原則）：
    - wi_template_id 有值 → 快照一律由伺服器從 motion module 解析回填，
      忽略 client 送來的快照值（避免 client 端算值繞過 most_engine 權威）。
    - wi_template_id 無值（手動條目）→ 使用 client 快照值（未給的數值欄預設 0）。
    """
    # 確認專案存在
    result = await session.execute(
        select(WiSetProject).where(WiSetProject.id == project_id)
    )
    if result.scalar_one_or_none() is None:
        msg = f"專案不存在：{project_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})

    # 快照解析
    if payload.wi_template_id is not None:
        snaps = await _resolve_template_snapshots(session, payload.wi_template_id)
    else:
        snaps = {
            "wi_name_snapshot": payload.wi_name_snapshot,  # schema 已驗證必填
            "wi_code_snapshot": payload.wi_code_snapshot,
            "action_count_snapshot": payload.action_count_snapshot or 0,
            "total_tmu_snapshot": payload.total_tmu_snapshot or 0.0,
            "total_seconds_snapshot": payload.total_seconds_snapshot or 0.0,
        }

    # max(seq_no) + 1
    max_seq = (
        await session.execute(
            select(func.max(WiSetItem.seq_no)).where(
                WiSetItem.project_id == project_id
            )
        )
    ).scalar()
    next_seq = (max_seq or 0) + 1

    item = WiSetItem(
        project_id=project_id,
        seq_no=next_seq,
        wi_template_id=payload.wi_template_id,
        notes=payload.notes,
        **snaps,
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return WiSetItemOut.model_validate(item)


# ── 移除條目 ─────────────────────────────────────────────────────────


@router.delete(
    "/wi-set-projects/{project_id}/items/{item_id}", status_code=204
)
async def remove_item(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> None:
    result = await session.execute(
        select(WiSetItem).where(
            WiSetItem.id == item_id, WiSetItem.project_id == project_id
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        msg = f"條目不存在：{item_id}（專案 {project_id}）"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})
    await session.delete(item)
    await session.flush()


# ── 重排序（PUT 在 /{item_id} 之前，避免路徑衝突）────────────────────
# 注意：此路由必須在 /{item_id} 具體路由之前定義。


@router.put(
    "/wi-set-projects/{project_id}/items/reorder", status_code=200
)
async def reorder_items(
    project_id: uuid.UUID,
    payload: ReorderRequest,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    # 確認專案存在
    result = await session.execute(
        select(WiSetProject).where(WiSetProject.id == project_id)
    )
    if result.scalar_one_or_none() is None:
        msg = f"專案不存在：{project_id}"
        raise NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "_compat_detail": msg})

    # 取出屬於此專案的全部條目
    existing = (
        await session.execute(
            select(WiSetItem).where(WiSetItem.project_id == project_id)
        )
    ).scalars().all()
    existing_ids = {item.id for item in existing}

    # 驗證 ordered_ids 完整性
    requested_ids = set(payload.ordered_ids)
    if requested_ids != existing_ids:
        msg = "ordered_ids 必須包含且僅包含此專案的所有條目 ID"
        raise ValidationError(msg, detail={"code": ErrorCode.VALIDATION_ERROR, "_compat_detail": msg})

    id_to_item = {item.id: item for item in existing}
    for new_seq, item_id in enumerate(payload.ordered_ids, start=1):
        id_to_item[item_id].seq_no = new_seq

    await session.flush()
    return {"ok": True}


# ── 複製專案 ─────────────────────────────────────────────────────────


@router.post(
    "/wi-set-projects/{project_id}/duplicate",
    response_model=WiSetProjectOut,
    status_code=201,
)
async def duplicate_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiSetProjectOut:
    original = await _get_project_or_404(session, project_id)

    new_code = original.project_code + "_copy"
    # 若 _copy 已存在，附上 suffix 避免衝突
    suffix = 1
    candidate = new_code
    while True:
        clash = (
            await session.execute(
                select(WiSetProject).where(WiSetProject.project_code == candidate)
            )
        ).scalar_one_or_none()
        if clash is None:
            break
        suffix += 1
        candidate = f"{new_code}_{suffix}"
    new_code = candidate

    new_project = WiSetProject(
        project_code=new_code,
        name=original.name,
        site=original.site,
        bu=original.bu,
        process=original.process,
        family=original.family,
        model=original.model,
        description=original.description,
        status="draft",
        created_by=user.employee_no,
    )
    session.add(new_project)
    await session.flush()

    for src_item in original.items:
        new_item = WiSetItem(
            project_id=new_project.id,
            seq_no=src_item.seq_no,
            wi_template_id=src_item.wi_template_id,
            wi_code_snapshot=src_item.wi_code_snapshot,
            wi_name_snapshot=src_item.wi_name_snapshot,
            action_count_snapshot=src_item.action_count_snapshot,
            total_tmu_snapshot=src_item.total_tmu_snapshot,
            total_seconds_snapshot=src_item.total_seconds_snapshot,
            notes=src_item.notes,
        )
        session.add(new_item)

    await session.flush()
    await session.refresh(new_project, ["items"])
    return WiSetProjectOut.model_validate(new_project)


@router.post(
    "/wi-set-projects/{project_id}/instantiate",
    response_model=WiSetInstantiateOut,
    status_code=201,
)
async def instantiate_project(
    project_id: uuid.UUID,
    payload: WiSetInstantiateIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiSetInstantiateOut:
    try:
        result = await wi_set_service.instantiate_project(
            session, project_id, payload, user.employee_no
        )
    except wi_set_service.WiSetInstantiationError as error:
        # service 顯式 code 動態攜帶（PROJECT_NOT_FOUND→404，其餘→422）；
        # _compat_detail 保留原 {code,message} dict（維持既有契約，I3 不更名）。
        compat = {"code": error.code, "message": error.message}
        detail = {"code": error.code, "_compat_detail": compat}
        if error.code == "PROJECT_NOT_FOUND":
            raise NotFoundError(error.message, detail=detail) from error
        raise ValidationError(error.message, detail=detail) from error
    return WiSetInstantiateOut.model_validate(result)
