"""使用者管理契約（admin）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class AppUserUpsertIn(BaseModel):
    employee_no: str
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)        # admin/manager/IE（空=viewer）
    site_ids: list[uuid.UUID] = Field(default_factory=list)


class AppUserPatchIn(BaseModel):
    roles: list[str] | None = None
    site_ids: list[uuid.UUID] | None = None
    is_active: bool | None = None
    display_name: str | None = None


class AppUserOut(BaseModel):
    employee_no: str
    external_user_id: str | None
    display_name: str | None
    roles: list[str]
    site_ids: list[uuid.UUID]
    is_active: bool
