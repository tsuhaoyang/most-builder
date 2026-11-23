"""區域、DSX 物件清單與座標同步、物件歸區 API（ADR-038 D5，W7a）。

GET    /api/v2/zone-categories                       區域類別（viewer）
POST   /api/v2/zone-categories                       新增類別（admin）
GET    /api/v2/skus/{sku_id}/zones                   SKU 的區域與最近一次同步（viewer）
POST   /api/v2/skus/{sku_id}/zones                   新增區域（analyst）
PATCH  /api/v2/zones/{zone_id}                       修改區域；換綁 DSX 物件會清掉中心座標（analyst）
DELETE /api/v2/zones/{zone_id}                       刪除區域；還有物件歸在它底下 → 409 ZONE_IN_USE（analyst）
POST   /api/v2/skus/{sku_id}/zones/sync              從 DSX 同步座標、存快照（analyst）
GET    /api/v2/dsx/objects                           代理 DSX 物件清單，給區域綁定的下拉（analyst）
GET    /api/v2/skus/{sku_id}/object-zones            物件歸區（viewer）
PUT    /api/v2/skus/{sku_id}/object-zones            設定物件歸區；zone_id=null 取消（analyst）
GET    /api/v2/worksheets/{worksheet_id}/objects     這份 WI 用到的物件與目前歸區（viewer）

瀏覽器不直連 DSX（DSX 沒有認證）。DSX 的三種失敗分開回報：整合沒開 503 `DSX_DISABLED`、連不到或回應看不懂
502 `DSX_UNREACHABLE`、座標尚未就緒 409 `DSX_NOT_READY`；物件清單連不到時回 `available=false`，不回空清單。
"""
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import (
    BadGatewayError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from ddm_v2.models.v2.zone import SkuObjectZone
from ddm_v2.schemas.v2.zone import (
    MAX_ZONES_PER_SKU,
    DsxObjectListOut,
    ObjectZoneListOut,
    ObjectZonesIn,
    SyncOut,
    WorksheetObjectsOut,
    ZoneCategoryIn,
    ZoneCategoryOut,
    ZoneIn,
    ZoneListOut,
    ZoneOut,
    ZonePatchIn,
)
from ddm_v2.services.v2 import dsx_client
from ddm_v2.services.v2 import zone_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2-zones"])


def _map(exc: Exception) -> Exception:
    if isinstance(exc, svc.SkuNotFound):
        return NotFoundError(f"SKU 不存在：{exc}", detail={"code": ErrorCode.NOT_FOUND, "resource": "sku"})
    if isinstance(exc, svc.ZoneNotFound):
        return NotFoundError(f"區域不存在：{exc}", detail={"code": ErrorCode.NOT_FOUND, "resource": "zone"})
    if isinstance(exc, svc.CategoryNotFound):
        return NotFoundError(f"區域類別不存在：{exc}", detail={"code": ErrorCode.NOT_FOUND, "resource": "zone_category"})
    if isinstance(exc, svc.VocabNotFound):
        return NotFoundError(
            "物件不存在", detail={"code": ErrorCode.NOT_FOUND, "resource": "vocab_item",
                                "vocab_item_ids": [str(i) for i in exc.ids[:200]]},
        )
    if isinstance(exc, svc.ZoneNameTaken):
        return ConflictError("同一個 SKU 已有同名區域", detail={"code": ErrorCode.CONFLICT, "field": "name"})
    if isinstance(exc, svc.CategoryExists):
        return ConflictError("類別代碼已存在", detail={"code": ErrorCode.CONFLICT, "field": "code"})
    if isinstance(exc, svc.ZoneInUse):
        return ConflictError(str(exc), detail={"code": ErrorCode.ZONE_IN_USE, "object_count": exc.count})
    if isinstance(exc, svc.TooManyZones):
        return ValidationError(str(exc), detail={"code": ErrorCode.VALIDATION_ERROR, "max": MAX_ZONES_PER_SKU})
    if isinstance(exc, svc.DsxDisabled):
        return ServiceUnavailableError("DSX 整合未開啟", detail={"code": ErrorCode.DSX_DISABLED})
    if isinstance(exc, dsx_client.DsxNotReady):
        return ConflictError("DSX 座標尚未就緒（請確認 3D 場景已載入）", detail={"code": ErrorCode.DSX_NOT_READY})
    if isinstance(exc, dsx_client.DsxUnreachable):
        logger.warning("DSX unreachable: %s", exc)
        return BadGatewayError("DSX 無法連線", detail={"code": ErrorCode.DSX_UNREACHABLE})
    if isinstance(exc, svc.DsxMisconfigured):
        logger.error("DSX misconfigured: %s", exc)
        return ServiceUnavailableError("DSX 設定不完整", detail={"code": ErrorCode.SERVICE_UNAVAILABLE})
    return exc


_DOMAIN = (
    svc.SkuNotFound, svc.ZoneNotFound, svc.CategoryNotFound, svc.VocabNotFound, svc.ZoneNameTaken,
    svc.CategoryExists, svc.ZoneInUse, svc.TooManyZones, svc.DsxDisabled, svc.DsxMisconfigured,
)


# ── 類別 ────────────────────────────────────────────────────────────────────

@router.get("/zone-categories", response_model=list[ZoneCategoryOut])
async def list_categories(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[ZoneCategoryOut]:
    return [ZoneCategoryOut.model_validate(c, from_attributes=True) for c in await svc.list_categories(session)]


@router.post("/zone-categories", response_model=ZoneCategoryOut, status_code=201)
async def add_category(
    payload: ZoneCategoryIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("admin")),
) -> ZoneCategoryOut:
    try:
        cat = await svc.add_category(session, **payload.model_dump(), actor=user.employee_no)
    except _DOMAIN as exc:
        raise _map(exc) from None
    return ZoneCategoryOut.model_validate(cat, from_attributes=True)


# ── 區域 ────────────────────────────────────────────────────────────────────

@router.get("/skus/{sku_id}/zones", response_model=ZoneListOut)
async def list_zones(
    sku_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> ZoneListOut:
    try:
        zones, snap = await svc.list_zones(session, sku_id)
    except _DOMAIN as exc:
        raise _map(exc) from None
    return ZoneListOut(
        sku_id=sku_id, zones=[ZoneOut(**svc.zone_out(z)) for z in zones],
        last_snapshot=svc.snapshot_out(snap) if snap else None,
    )


@router.post("/skus/{sku_id}/zones", response_model=ZoneOut, status_code=201)
async def create_zone(
    sku_id: uuid.UUID,
    payload: ZoneIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> ZoneOut:
    try:
        z = await svc.create_zone(session, sku_id, **payload.model_dump(), actor=user.employee_no)
    except _DOMAIN as exc:
        raise _map(exc) from None
    return ZoneOut(**svc.zone_out(z))


@router.patch("/zones/{zone_id}", response_model=ZoneOut)
async def patch_zone(
    zone_id: uuid.UUID,
    payload: ZonePatchIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> ZoneOut:
    # 只套用有帶的欄位；dsx_object_id 帶 null＝解除綁定
    fields = {k: getattr(payload, k) for k in payload.model_fields_set}
    if fields.get("category_id", ...) is None or fields.get("name", ...) is None:
        raise ValidationError("類別與名稱不能清空", detail={"code": ErrorCode.VALIDATION_ERROR})
    try:
        z = await svc.patch_zone(session, zone_id, fields, actor=user.employee_no)
    except _DOMAIN as exc:
        raise _map(exc) from None
    return ZoneOut(**svc.zone_out(z))


@router.delete("/zones/{zone_id}", status_code=204)
async def delete_zone(
    zone_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> Response:
    try:
        await svc.delete_zone(session, zone_id)
    except _DOMAIN as exc:
        raise _map(exc) from None
    logger.info("zone deleted: zone=%s by=%s", zone_id, user.employee_no)
    return Response(status_code=204)


@router.post("/skus/{sku_id}/zones/sync", response_model=SyncOut)
async def sync_zones(
    sku_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> SyncOut:
    try:
        snap, previous, zones, missing, unbound = await svc.sync_from_dsx(session, sku_id, actor=user.employee_no)
    except (*_DOMAIN, dsx_client.DsxNotReady, dsx_client.DsxUnreachable) as exc:
        raise _map(exc) from None
    return SyncOut(
        snapshot=svc.snapshot_out(snap), previous_snapshot=svc.snapshot_out(previous) if previous else None,
        zones=[ZoneOut(**svc.zone_out(z)) for z in zones],
        missing_zone_ids=missing, unbound_zone_ids=unbound,
    )


@router.get("/dsx/objects", response_model=DsxObjectListOut)
async def dsx_objects(_: CurrentUser = Depends(require_role("analyst"))) -> DsxObjectListOut:
    try:
        objs = await svc.dsx_objects()
    except svc.DsxDisabled:
        return DsxObjectListOut(available=False, reason="integration_disabled")
    except dsx_client.DsxUnreachable as exc:
        logger.warning("DSX unreachable: %s", exc)
        return DsxObjectListOut(available=False, reason="dsx_unreachable")
    except svc.DsxMisconfigured as exc:
        raise _map(exc) from None
    return DsxObjectListOut(available=True, objects=[o.__dict__ for o in objs])


# ── 物件歸區 ────────────────────────────────────────────────────────────────

def _assignments_out(sku_id: uuid.UUID, rows: Sequence[SkuObjectZone]) -> ObjectZoneListOut:
    return ObjectZoneListOut(sku_id=sku_id, items=[
        {"vocab_item_id": r.vocab_item_id, "zone_id": r.zone_id,
         "object_point": svc.point_of(r.object_x, r.object_y, r.object_z),
         "assigned_by": r.assigned_by, "assigned_at": r.assigned_at}
        for r in rows
    ])


@router.get("/skus/{sku_id}/object-zones", response_model=ObjectZoneListOut)
async def list_object_zones(
    sku_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> ObjectZoneListOut:
    try:
        rows = await svc.list_object_zones(session, sku_id)
    except _DOMAIN as exc:
        raise _map(exc) from None
    return _assignments_out(sku_id, rows)


@router.put("/skus/{sku_id}/object-zones", response_model=ObjectZoneListOut)
async def set_object_zones(
    sku_id: uuid.UUID,
    payload: ObjectZonesIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> ObjectZoneListOut:
    try:
        rows = await svc.set_object_zones(
            session, sku_id, [(i.vocab_item_id, i.zone_id) for i in payload.items], actor=user.employee_no
        )
    except _DOMAIN as exc:
        raise _map(exc) from None
    return _assignments_out(sku_id, rows)


@router.get("/worksheets/{worksheet_id}/objects", response_model=WorksheetObjectsOut)
async def worksheet_objects(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> WorksheetObjectsOut:
    try:
        sku_id, objs = await svc.worksheet_objects(session, worksheet_id)
    except svc.SkuNotFound:
        raise NotFoundError(
            f"worksheet 不存在：{worksheet_id}",
            detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id)},
        ) from None
    return WorksheetObjectsOut(worksheet_id=worksheet_id, sku_id=sku_id, objects=objs)
