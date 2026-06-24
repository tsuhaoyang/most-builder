"""目錄/結構服務：Site→Product→Sku→（建立）工序表。停用＝is_active=false（軟）。"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import ConflictError, NotFoundError
from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion


def _site(s: Site) -> dict[str, Any]:
    return {"id": s.id, "external_code": s.external_code, "name_zh": s.name_zh, "name_en": s.name_en, "is_active": s.is_active}


def _product(p: Product) -> dict[str, Any]:
    return {"id": p.id, "site_id": p.site_id, "external_code": p.external_code, "name_zh": p.name_zh,
            "name_en": p.name_en, "description": p.description, "is_active": p.is_active}


def _sku(s: Sku) -> dict[str, Any]:
    return {"id": s.id, "product_id": s.product_id, "sku_code": s.sku_code, "name_zh": s.name_zh,
            "name_en": s.name_en, "is_active": s.is_active}


async def list_sites(session: AsyncSession) -> list[dict]:
    rows = (await session.execute(select(Site).order_by(Site.name_zh))).scalars().all()
    return [_site(s) for s in rows]


async def list_products(session: AsyncSession, site_id: uuid.UUID | None) -> list[dict]:
    q = select(Product).order_by(Product.name_zh)
    if site_id:
        q = q.where(Product.site_id == site_id)
    return [_product(p) for p in (await session.execute(q)).scalars().all()]


async def create_product(session: AsyncSession, payload) -> dict:
    if await session.get(Site, payload.site_id) is None:
        raise NotFoundError(f"site 不存在：{payload.site_id}")
    if payload.external_code:
        dup = (await session.execute(select(Product).where(Product.external_code == payload.external_code))).scalar_one_or_none()
        if dup:
            raise ConflictError(f"external_code 已存在：{payload.external_code}")
    p = Product(id=uuid.uuid4(), site_id=payload.site_id, name_zh=payload.name_zh,
                external_code=payload.external_code, name_en=payload.name_en, description=payload.description)
    session.add(p)
    await session.flush()
    return _product(p)


async def update_product(session: AsyncSession, product_id: uuid.UUID, patch) -> dict:
    p = await session.get(Product, product_id)
    if p is None:
        raise NotFoundError(f"product 不存在：{product_id}")
    if patch.name_zh is not None:
        p.name_zh = patch.name_zh
    if patch.name_en is not None:
        p.name_en = patch.name_en
    if patch.description is not None:
        p.description = patch.description
    if patch.is_active is not None:
        p.is_active = patch.is_active
    await session.flush()
    return _product(p)


async def list_skus(session: AsyncSession, product_id: uuid.UUID | None) -> list[dict]:
    q = select(Sku).order_by(Sku.sku_code)
    if product_id:
        q = q.where(Sku.product_id == product_id)
    return [_sku(s) for s in (await session.execute(q)).scalars().all()]


async def create_sku(session: AsyncSession, payload) -> dict:
    if await session.get(Product, payload.product_id) is None:
        raise NotFoundError(f"product 不存在：{payload.product_id}")
    dup = (await session.execute(select(Sku).where(
        Sku.product_id == payload.product_id, Sku.sku_code == payload.sku_code))).scalar_one_or_none()
    if dup:
        raise ConflictError(f"此產品下 sku_code 已存在：{payload.sku_code}")
    s = Sku(id=uuid.uuid4(), product_id=payload.product_id, sku_code=payload.sku_code,
            name_zh=payload.name_zh, name_en=payload.name_en)
    session.add(s)
    await session.flush()
    return _sku(s)


async def update_sku(session: AsyncSession, sku_id: uuid.UUID, patch) -> dict:
    s = await session.get(Sku, sku_id)
    if s is None:
        raise NotFoundError(f"sku 不存在：{sku_id}")
    if patch.name_zh is not None:
        s.name_zh = patch.name_zh
    if patch.name_en is not None:
        s.name_en = patch.name_en
    if patch.is_active is not None:
        s.is_active = patch.is_active
    await session.flush()
    return _sku(s)


async def list_worksheets_by_sku(session: AsyncSession, sku_id: uuid.UUID) -> list[dict]:
    if await session.get(Sku, sku_id) is None:
        raise NotFoundError(f"sku 不存在：{sku_id}")
    pvs = (await session.execute(select(ProcessVersion).where(
        ProcessVersion.sku_id == sku_id).order_by(ProcessVersion.created_at))).scalars().all()
    out: list[dict] = []
    for pv in pvs:
        ws = (await session.execute(select(MostWorksheet).where(
            MostWorksheet.process_version_id == pv.id))).scalar_one_or_none()
        if ws is None:
            continue
        out.append({"worksheet_id": ws.id, "version_no": pv.version_no, "status": pv.status,
                    "analyst": ws.analyst, "model_label": ws.model_label})
    return out


async def create_worksheet(session: AsyncSession, sku_id: uuid.UUID, payload, actor: str | None) -> dict:
    if await session.get(Sku, sku_id) is None:
        raise NotFoundError(f"sku 不存在：{sku_id}")
    count = len((await session.execute(select(ProcessVersion).where(ProcessVersion.sku_id == sku_id))).scalars().all())
    rs = (await session.execute(select(RuleSet).where(RuleSet.code == "MINIMOST_FACTORY_V1"))).scalar_one_or_none()
    pv = ProcessVersion(id=uuid.uuid4(), sku_id=sku_id, version_no=f"v{count + 1}", status="draft", created_by=actor)
    ws = MostWorksheet(id=uuid.uuid4(), process_version_id=pv.id, model_label=payload.model_label,
                       analyst=payload.analyst, default_rule_set_id=rs.id if rs else None, status="draft")
    session.add(pv)
    session.add(ws)
    await session.flush()
    return {"worksheet_id": ws.id, "version_no": pv.version_no, "status": "draft"}
