"""目錄/結構 API：Site / Product / Sku / 在 SKU 下建立工序表。

歸屬鏈：Site → Product → Sku → ProcessVersion(版本) → MostWorksheet(工序表)。
讀＝任何登入者；建立/修改＝IE+；停用＝PATCH is_active=false（軟，FK 為 RESTRICT）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.schemas.v2.catalog import (
    ProductIn,
    ProductOut,
    ProductPatch,
    SiteOut,
    SkuIn,
    SkuOut,
    SkuPatch,
    WorksheetCreateIn,
    WorksheetCreateOut,
    WorksheetSummaryOut,
)
from ddm_v2.services.v2 import catalog_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-catalog"])


@router.get("/sites", response_model=list[SiteOut])
async def list_sites(session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)):
    return await svc.list_sites(session)


@router.get("/products", response_model=list[ProductOut])
async def list_products(site_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session),
                        _: CurrentUser = Depends(current_user)):
    return await svc.list_products(session, site_id)


@router.post("/products", response_model=ProductOut, status_code=201)
async def create_product(payload: ProductIn, session: AsyncSession = Depends(get_db_session),
                         _: CurrentUser = Depends(require_role("IE"))):
    return await svc.create_product(session, payload)


@router.patch("/products/{product_id}", response_model=ProductOut)
async def update_product(product_id: uuid.UUID, patch: ProductPatch, session: AsyncSession = Depends(get_db_session),
                         _: CurrentUser = Depends(require_role("IE"))):
    return await svc.update_product(session, product_id, patch)


@router.get("/skus", response_model=list[SkuOut])
async def list_skus(product_id: uuid.UUID | None = None, session: AsyncSession = Depends(get_db_session),
                    _: CurrentUser = Depends(current_user)):
    return await svc.list_skus(session, product_id)


@router.post("/skus", response_model=SkuOut, status_code=201)
async def create_sku(payload: SkuIn, session: AsyncSession = Depends(get_db_session),
                     _: CurrentUser = Depends(require_role("IE"))):
    return await svc.create_sku(session, payload)


@router.patch("/skus/{sku_id}", response_model=SkuOut)
async def update_sku(sku_id: uuid.UUID, patch: SkuPatch, session: AsyncSession = Depends(get_db_session),
                     _: CurrentUser = Depends(require_role("IE"))):
    return await svc.update_sku(session, sku_id, patch)


# ADR-019 Option A: listing=viewer+ intentional; UUID enumerable by design — see ADR-019
@router.get("/skus/{sku_id}/worksheets", response_model=list[WorksheetSummaryOut])
async def list_worksheets(sku_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                          _: CurrentUser = Depends(current_user)):
    return await svc.list_worksheets_by_sku(session, sku_id)


@router.post("/skus/{sku_id}/worksheets", response_model=WorksheetCreateOut, status_code=201)
async def create_worksheet(sku_id: uuid.UUID, payload: WorksheetCreateIn, session: AsyncSession = Depends(get_db_session),
                           user: CurrentUser = Depends(require_role("IE"))):
    return await svc.create_worksheet(session, sku_id, payload, actor=user.employee_no)
