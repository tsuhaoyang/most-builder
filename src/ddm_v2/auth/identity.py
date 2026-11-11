"""身分解析（rbac-spec §6）。支援兩種正式模式 + 本地 dev override。

- **gateway**（預設）：認證委派 Traefik ForwardAuth，這裡只「讀」gateway 注入的
  `X-Username`(員工編號)/`X-User-Id`/`X-Plant-Code`。前提：MOST 只能經 gateway 進，
  否則 client 可偽造 header。
- **verify**：MOST 自己拿 session cookie 去打 LB 的 `/auth/verify` 驗證，由回應 header
  取身分。**不信任** client 端的 `X-Username`，因此 MOST 可直接開自己的 port 對外（過渡用）。
- dev：`AUTH_DEV_USER=員工編號`（僅非 production），讓本地無 gateway/無 LB 也能測。

模式由 `DDM_AUTH_MODE` 切換（gateway|verify）。verify 需 `DDM_LB_VERIFY_URL`
（例：`http://<lb-host>/auth/verify`）與 `DDM_SESSION_COOKIE_NAME`（預設 session_id）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
from fastapi import Request


@dataclass(frozen=True)
class Identity:
    employee_no: str
    external_user_id: str | None = None
    plant_code: str | None = None


def _is_production() -> bool:
    return os.getenv("ENV", "development").lower() in {"production", "prod"}


def _dev_identity() -> Identity | None:
    dev = os.getenv("AUTH_DEV_USER")
    if dev and not _is_production():
        return Identity(employee_no=dev.strip())
    return None


def _from_headers(request: Request) -> Identity | None:
    emp = request.headers.get("X-Username")
    if not emp:
        return None
    return Identity(
        employee_no=emp.strip(),
        external_user_id=request.headers.get("X-User-Id"),
        plant_code=request.headers.get("X-Plant-Code"),
    )


async def _from_verify(request: Request) -> Identity | None:
    """verify 模式：以 session cookie 打 LB /auth/verify，由回應 header 取身分。

    不讀 client 的 X-Username（可偽造）；身分一律來自 LB 驗證後的回應，故直接對外亦安全。
    """
    cookie_name = os.getenv("DDM_SESSION_COOKIE_NAME", "session_id")
    sid = request.cookies.get(cookie_name)
    if not sid:
        return _dev_identity()  # 無 session：本地 dev override（非 prod）才給身分
    url = os.getenv("DDM_LB_VERIFY_URL")
    if not url:
        return None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Cookie": f"{cookie_name}={sid}"})
    except httpx.HTTPError:
        return None  # LB 不可達 → 視為未認證（fail-closed）
    if resp.status_code != 200:
        return None
    emp = resp.headers.get("X-Username")
    if not emp:
        return None
    return Identity(
        employee_no=emp.strip(),
        external_user_id=resp.headers.get("X-User-Id"),
        plant_code=resp.headers.get("X-Plant-Code"),
    )


async def resolve_identity(request: Request) -> Identity | None:
    """gateway/verify 模式分流；都無身分 → None（未認證）。"""
    mode = os.getenv("DDM_AUTH_MODE", "gateway").lower()
    if mode == "verify":
        return await _from_verify(request)
    # gateway 模式：信任 ForwardAuth 注入的 header；本地則 dev override
    return _from_headers(request) or _dev_identity()
