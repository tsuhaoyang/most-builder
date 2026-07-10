"""v2 詞彙庫主數據 API（FE-5）：list / create / patch / soft-delete。

對外取資料的單一入口；現以本地 DB（LocalDbProvider 精神）為後援，日後可換 MasterDataProvider
從外部系統（PLM/MES/ERP）取得。被已發布 WI 引用者只可軟刪（is_active=false），不可硬刪（E1）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.schemas.v2.vocab import VocabItemIn, VocabItemOut, VocabPatchIn

router = APIRouter(prefix="/api/v2", tags=["v2-vocab"])


def _out(v: WorkVocabItem) -> VocabItemOut:
    return VocabItemOut(id=v.id, kind=v.kind, name_zh=v.name_zh, name_en=v.name_en,
                        external_code=v.external_code, source_system=v.source_system, is_active=v.is_active)


@router.get("/vocab", response_model=list[VocabItemOut])
async def list_vocab(kind: str | None = Query(default=None), session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> list[VocabItemOut]:
    stmt = select(WorkVocabItem).where(WorkVocabItem.is_active.is_(True), WorkVocabItem.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(WorkVocabItem.kind == kind)
    stmt = stmt.order_by(WorkVocabItem.kind, WorkVocabItem.name_zh)
    rows = (await session.execute(stmt)).scalars().all()
    return [_out(v) for v in rows]


@router.post("/vocab", response_model=VocabItemOut, status_code=201)
async def create_vocab(payload: VocabItemIn, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(require_role("analyst"))) -> VocabItemOut:
    v = WorkVocabItem(id=uuid.uuid4(), kind=payload.kind, name_zh=payload.name_zh, name_en=payload.name_en,
                      external_code=payload.external_code or None, source_system=payload.source_system, site_id=payload.site_id)
    session.add(v)
    await session.flush()
    return _out(v)


@router.patch("/vocab/{item_id}", response_model=VocabItemOut)
async def patch_vocab(item_id: uuid.UUID, payload: VocabPatchIn, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(require_role("analyst"))) -> VocabItemOut:
    v = await session.get(WorkVocabItem, item_id)
    if v is None or not v.is_active:
        raise HTTPException(status_code=404, detail=f"詞彙不存在：{item_id}")
    if payload.name_zh is not None:
        v.name_zh = payload.name_zh
    if payload.name_en is not None:
        v.name_en = payload.name_en
    if payload.external_code is not None:
        v.external_code = payload.external_code or None
    await session.flush()
    return _out(v)


@router.delete("/vocab/{item_id}", status_code=204)
async def soft_delete_vocab(item_id: uuid.UUID, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(require_role("analyst"))) -> None:
    v = await session.get(WorkVocabItem, item_id)
    if v is None or not v.is_active:
        raise HTTPException(status_code=404, detail=f"詞彙不存在：{item_id}")
    v.is_active = False
    v.deleted_at = datetime.now(timezone.utc)
    await session.flush()
