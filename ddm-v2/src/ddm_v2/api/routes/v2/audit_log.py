"""稽核日誌查詢 API（impl-06c/d）。

GET /api/v2/audit-log
  - 需 approver 以上角色（ROLE_ORDER approver=2）
  - 查 workflow_audit_log，依 created_at DESC 固定排序
  - 支援精確比對過濾：entity_type / entity_id / actor / action
  - 支援時間範圍：from_dt / to_dt
  - 支援廠區過濾：site_id（impl-06d）
    - 僅對 entity_type='process_version' 套用；其他 entity_type 不受 site 過濾影響
    - approver 可傳自己廠區的 site_id；admin 可不傳（查全域）
  - 分頁：limit（max 200）/ offset
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, require_role
from ddm_v2.database import get_db_session
from ddm_v2.models.v2.audit import WorkflowAuditLog
from ddm_v2.models.v2.org import Product, Sku
from ddm_v2.models.v2.worksheet import ProcessVersion
from ddm_v2.schemas.v2.audit import AuditLogEntry, AuditLogListOut

router = APIRouter(prefix="/api/v2", tags=["v2-audit"])


@router.get("/audit-log", response_model=AuditLogListOut)
async def list_audit_log(
    entity_type: Optional[str] = Query(None, description="精確比對 entity_type"),
    entity_id: Optional[uuid.UUID] = Query(None, description="精確比對 entity_id"),
    actor: Optional[str] = Query(None, description="精確比對員工編號"),
    action: Optional[str] = Query(None, description="精確比對 action（approve/promote/publish/retire…）"),
    from_dt: Optional[datetime] = Query(None, description="created_at >= from_dt"),
    to_dt: Optional[datetime] = Query(None, description="created_at <= to_dt"),
    site_id: Optional[uuid.UUID] = Query(
        None,
        description=(
            "廠區過濾（impl-06d）：僅對 entity_type='process_version' 套用，"
            "其他 entity_type 不受影響。approver 傳自己廠區；admin 不傳查全域。"
        ),
    ),
    limit: int = Query(50, ge=1, le=200, description="每頁筆數（最大 200）"),
    offset: int = Query(0, ge=0, description="跳過筆數"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_role("approver")),
) -> AuditLogListOut:
    """查詢工作流稽核日誌（approver 以上可查全域）。"""
    # clamp limit 上限至 200
    limit = min(limit, 200)

    # 組合過濾條件
    filters = []
    if entity_type is not None:
        filters.append(WorkflowAuditLog.entity_type == entity_type)
    if entity_id is not None:
        filters.append(WorkflowAuditLog.entity_id == entity_id)
    if actor is not None:
        filters.append(WorkflowAuditLog.actor == actor)
    if action is not None:
        filters.append(WorkflowAuditLog.action == action)
    if from_dt is not None:
        filters.append(WorkflowAuditLog.created_at >= from_dt)
    if to_dt is not None:
        filters.append(WorkflowAuditLog.created_at <= to_dt)
    if site_id is not None:
        # 取出屬於該 site 的所有 process_version.id
        # 路徑：ProcessVersion.sku_id → Sku.product_id → Product.site_id
        pv_subq = (
            select(ProcessVersion.id)
            .join(Sku, Sku.id == ProcessVersion.sku_id)
            .join(Product, Product.id == Sku.product_id)
            .where(Product.site_id == site_id)
            .scalar_subquery()
        )
        # 僅對 entity_type='process_version' 套用；其他 entity_type 原樣保留
        filters.append(
            or_(
                WorkflowAuditLog.entity_type != "process_version",
                WorkflowAuditLog.entity_id.in_(pv_subq),
            )
        )

    # COUNT（先取 total，不拉整表）
    count_q = select(func.count()).select_from(WorkflowAuditLog)
    if filters:
        count_q = count_q.where(*filters)
    total: int = (await session.execute(count_q)).scalar_one()

    # 資料查詢
    items_q = select(WorkflowAuditLog)
    if filters:
        items_q = items_q.where(*filters)
    items_q = (
        items_q
        .order_by(WorkflowAuditLog.created_at.desc(), WorkflowAuditLog.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(items_q)).scalars().all()

    return AuditLogListOut(
        total=total,
        items=[
            AuditLogEntry(
                id=row.id,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                action=row.action,
                from_status=row.from_status,
                to_status=row.to_status,
                actor=row.actor,
                comment=row.comment,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in rows
        ],
    )
