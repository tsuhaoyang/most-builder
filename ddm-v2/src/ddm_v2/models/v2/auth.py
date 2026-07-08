"""RBAC 本地授權（rbac-spec §5）：app_users 把員工編號對應到 MOST 角色。

認證委派 Traefik ForwardAuth（LB auth_service）；此表只管「授權」。
穩定鍵＝employee_no（X-Username）；external_user_id（X-User-Id）為輔助。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from ddm_v2.models.v2.base import Base, TimestampMixin, uuid_pk


class AppUser(Base, TimestampMixin):
    __tablename__ = "app_users"

    id: Mapped[UUID] = uuid_pk()
    employee_no: Mapped[str] = mapped_column(Text, nullable=False, unique=True)  # 穩定鍵（X-Username）
    external_user_id: Mapped[str | None] = mapped_column(Text)                   # 輔助（X-User-Id）
    display_name: Mapped[str | None] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))  # 空＝viewer
    site_ids: Mapped[list[UUID]] = mapped_column(ARRAY(PG_UUID(as_uuid=True)), nullable=False, server_default=text("'{}'::uuid[]"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
