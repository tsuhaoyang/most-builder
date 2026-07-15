"""使用者角色管理 API（admin 限定）：list / upsert(授予角色) / patch(停用等)。

rbac-spec §4/§6。穩定鍵＝員工編號。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, require_role
from ddm_v2.database import get_db_session
from ddm_v2.models.v2.auth import AppUser
from ddm_v2.schemas.v2.auth import AppUserOut, AppUserPatchIn, AppUserUpsertIn

router = APIRouter(prefix="/api/v2/admin", tags=["v2-admin"])

_VALID_ROLES = {"admin", "approver", "analyst"}


def _out(u: AppUser) -> AppUserOut:
    return AppUserOut(employee_no=u.employee_no, external_user_id=u.external_user_id, display_name=u.display_name,
                      roles=list(u.roles or []), site_ids=list(u.site_ids or []), is_active=u.is_active)


def _check_roles(roles: list[str]) -> None:
    bad = set(roles) - _VALID_ROLES
    if bad:
        raise HTTPException(status_code=422, detail=f"未知角色：{sorted(bad)}（合法 {sorted(_VALID_ROLES)}）")


@router.get("/users", response_model=list[AppUserOut])
async def list_users(session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(require_role("admin"))) -> list[AppUserOut]:
    rows = (await session.execute(select(AppUser).order_by(AppUser.employee_no))).scalars().all()
    return [_out(u) for u in rows]


@router.post("/users", response_model=AppUserOut)
async def upsert_user(payload: AppUserUpsertIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                      _: CurrentUser = Depends(require_role("admin"))) -> AppUserOut:
    _check_roles(payload.roles)
    u = (await session.execute(select(AppUser).where(AppUser.employee_no == payload.employee_no))).scalar_one_or_none()
    if u is None:
        u = AppUser(id=uuid.uuid4(), employee_no=payload.employee_no)
        session.add(u)
    u.display_name = payload.display_name or payload.employee_no
    u.roles = payload.roles
    u.site_ids = payload.site_ids
    await session.flush()
    return _out(u)


@router.patch("/users/{employee_no}", response_model=AppUserOut)
async def patch_user(employee_no: str, payload: AppUserPatchIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                     actor: CurrentUser = Depends(require_role("admin"))) -> AppUserOut:
    u = (await session.execute(select(AppUser).where(AppUser.employee_no == employee_no))).scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=404, detail=f"使用者不存在：{employee_no}")
    if payload.roles is not None:
        _check_roles(payload.roles)
        # 防呆：不可移除自己的 admin（避免鎖死）
        if u.employee_no == actor.employee_no and "admin" not in payload.roles:
            raise HTTPException(status_code=409, detail="不可移除自己的 admin 角色")
        u.roles = payload.roles
    if payload.site_ids is not None:
        u.site_ids = payload.site_ids
    if payload.display_name is not None:
        u.display_name = payload.display_name
    if payload.is_active is not None:
        if u.employee_no == actor.employee_no and payload.is_active is False:
            raise HTTPException(status_code=409, detail="不可停用自己")
        u.is_active = payload.is_active
    await session.flush()
    return _out(u)
