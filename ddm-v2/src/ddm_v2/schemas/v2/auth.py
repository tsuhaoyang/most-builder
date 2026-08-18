"""使用者管理契約（admin）＋ 自助 /me 契約（ADR-032 D3.1）。"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from ddm_v2.locale import Locale


class MeOut(BaseModel):
    """`GET /api/v2/me` ＋ `PATCH /api/v2/me/locale` 共用回應形狀。

    `locale` 是**已解析**值（`app_users.locale IS NULL` → `DEFAULT_LOCALE`），
    不是資料庫原始值——前端不需要自己做 NULL 回退（ADR-032 D3.1／D3.2）。
    """
    employee_no: str
    roles: list[str]
    plant_code: str | None
    level: int
    locale: Locale


class LocalePatchIn(BaseModel):
    """`PATCH /api/v2/me/locale` 請求體：本人自助改語言偏好，無需 admin。"""
    locale: Locale


class AppUserUpsertIn(BaseModel):
    employee_no: str
    display_name: str | None = None
    roles: list[str] = Field(default_factory=list)        # admin/approver/analyst（空=viewer）
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
