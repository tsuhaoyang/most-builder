"""案件清單服務：JOIN ProcessVersion → MostWorksheet → SKU → Product → Site。

total_tmu 由 SUM(MostCycle.total_tmu * WiRow.frequency) 批次聚合（MostWorksheet 無存儲欄）。
SIMO 群組以頻率加權總和估算；精確值見案件詳情（read_worksheet）。
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.org import Product, Site, Sku
from ddm_v2.models.v2.worksheet import MostCycle, MostWorksheet, ProcessVersion, WiRow


async def list_cases(
    session: AsyncSession,
    status: str | None = None,
    site_id: uuid.UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """案件清單（含分頁）。"""
    # 批次聚合 total_tmu：SUM(mc.total_tmu * wr.frequency) per worksheet（單一 JOIN，非 N+1）。
    # SIMO 群組應取群內 max，SQL 層過複雜；以頻率加權總和估算。精確值見案件詳情。
    tmu_sub = (
        select(
            WiRow.worksheet_id.label("ws_id"),
            func.sum(MostCycle.total_tmu * WiRow.frequency).label("total_tmu"),
        )
        .join(MostCycle, MostCycle.wi_row_id == WiRow.id)
        .group_by(WiRow.worksheet_id)
        .subquery("tmu_agg")
    )

    # 基底 JOIN：ProcessVersion → MostWorksheet → tmu_agg → Sku → Product → Site
    base_q = (
        select(
            ProcessVersion,
            MostWorksheet.id.label("worksheet_id"),
            Sku.id.label("sku_id"),
            Sku.name_zh.label("sku_name_zh"),
            Sku.sku_code.label("sku_code"),
            Product.id.label("product_id"),
            Product.name_zh.label("product_name"),
            Site.id.label("site_id"),
            Site.name_zh.label("site_name"),
            tmu_sub.c.total_tmu.label("ws_total_tmu"),
        )
        .join(MostWorksheet, MostWorksheet.process_version_id == ProcessVersion.id)
        .outerjoin(tmu_sub, tmu_sub.c.ws_id == MostWorksheet.id)
        .join(Sku, Sku.id == ProcessVersion.sku_id)
        .join(Product, Product.id == Sku.product_id)
        .join(Site, Site.id == Product.site_id)
    )

    if status:
        base_q = base_q.where(ProcessVersion.status == status)
    if site_id:
        base_q = base_q.where(Site.id == site_id)

    # total count
    count_q = select(func.count()).select_from(base_q.subquery())
    total: int = (await session.execute(count_q)).scalar_one()

    # 分頁
    rows_q = base_q.order_by(ProcessVersion.created_at.desc()).offset(offset).limit(limit)
    rows = (await session.execute(rows_q)).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        pv: ProcessVersion = row[0]
        ws_id: uuid.UUID = row.worksheet_id
        sku_id: uuid.UUID = row.sku_id
        sku_name_zh: str | None = row.sku_name_zh
        sku_code: str = row.sku_code
        product_id: uuid.UUID = row.product_id
        product_name: str = row.product_name
        site_id_val: uuid.UUID = row.site_id
        site_name: str = row.site_name
        total_tmu_val = row.ws_total_tmu  # 已由 tmu_agg 批次算好

        items.append({
            "process_version_id": pv.id,
            "worksheet_id": ws_id,
            "version_no": pv.version_no,
            "status": pv.status,
            "site_id": site_id_val,
            "site_name": site_name,
            "product_id": product_id,
            "product_name": product_name,
            "sku_id": sku_id,
            "sku_name": sku_name_zh or sku_code,
            "process_name": sku_name_zh or sku_code,
            "approved_at": pv.published_at,
            "created_at": pv.created_at,
            "total_tmu": float(total_tmu_val) if total_tmu_val is not None else None,
        })

    return {"total": total, "items": items}
