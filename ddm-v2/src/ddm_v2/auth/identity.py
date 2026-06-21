"""身分解析（rbac-spec §6）：認證委派 Traefik ForwardAuth，這裡只「讀」gateway 注入的身分。

prod：讀 X-Username(員工編號)/X-User-Id/X-Plant-Code。
dev：`AUTH_DEV_USER=員工編號`（僅非 production），讓本地無 gateway 也能測。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Request


@dataclass(frozen=True)
class Identity:
    employee_no: str
    external_user_id: str | None = None
    plant_code: str | None = None


def _is_production() -> bool:
    return os.getenv("ENV", "development").lower() in {"production", "prod"}


def resolve_identity(request: Request) -> Identity | None:
    """gateway header 優先；本地 dev override 次之；都無 → None（未認證）。"""
    emp = request.headers.get("X-Username")
    if emp:
        return Identity(
            employee_no=emp.strip(),
            external_user_id=request.headers.get("X-User-Id"),
            plant_code=request.headers.get("X-Plant-Code"),
        )
    dev = os.getenv("AUTH_DEV_USER")
    if dev and not _is_production():
        return Identity(employee_no=dev.strip())
    return None
