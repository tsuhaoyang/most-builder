"""FastAPI 授權依賴（rbac-spec §4/§6）：current_user（JIT viewer）+ require_role 守門。"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.identity import resolve_identity
from ddm_v2.database import get_db_session
from ddm_v2.models.v2.auth import AppUser

ROLE_ORDER = {"viewer": 0, "analyst": 1, "approver": 2, "admin": 3}


@dataclass
class CurrentUser:
    employee_no: str
    roles: list[str]
    site_ids: list
    plant_code: str | None = None

    @property
    def level(self) -> int:
        return max((ROLE_ORDER.get(r, 0) for r in self.roles), default=0)

    def has(self, role: str) -> bool:
        return self.level >= ROLE_ORDER.get(role, 99)


async def current_user(request: Request, session: AsyncSession = Depends(get_db_session, scope="function")) -> CurrentUser:
    ident = await resolve_identity(request)
    if ident is None:
        mode = os.getenv("DDM_AUTH_MODE", "gateway").lower()
        if mode == "verify":
            detail = ("未認證（verify 模式）：拿不到有效身分。可能原因—無 session cookie、"
                      "cookie 名稱與 LB 不符（DDM_SESSION_COOKIE_NAME），或 MOST 連不到 "
                      f"DDM_LB_VERIFY_URL={os.getenv('DDM_LB_VERIFY_URL', '(未設)')}")
        else:
            detail = "未認證（gateway 模式）：缺 gateway 注入的 X-Username；本地請設 AUTH_DEV_USER"
        raise HTTPException(status_code=401, detail=detail)
    u = (await session.execute(select(AppUser).where(AppUser.employee_no == ident.employee_no))).scalar_one_or_none()
    if u is None:  # JIT：第一次出現 → 建 viewer（無角色），待 admin 授予
        u = AppUser(id=uuid.uuid4(), employee_no=ident.employee_no, external_user_id=ident.external_user_id,
                    display_name=ident.employee_no, roles=[])
        session.add(u)
        await session.flush()
    if not u.is_active:
        raise HTTPException(status_code=403, detail="帳號已停用")
    return CurrentUser(employee_no=u.employee_no, roles=list(u.roles or []), site_ids=list(u.site_ids or []), plant_code=ident.plant_code)


def require_role(min_role: str):
    """回傳一個依賴：角色 < min_role → 403。"""
    async def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.level < ROLE_ORDER[min_role]:
            raise HTTPException(status_code=403, detail=f"需要 {min_role} 以上角色（你目前：{user.roles or ['viewer']}）")
        return user
    return dep
