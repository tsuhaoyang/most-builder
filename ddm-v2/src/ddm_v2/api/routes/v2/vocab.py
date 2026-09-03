"""v2 詞彙庫主數據 API（FE-5）：list / create / patch / soft-delete。

對外取資料的單一入口；現以本地 DB（LocalDbProvider 精神）為後援，日後可換 MasterDataProvider
從外部系統（PLM/MES/ERP）取得。被已發布 WI 引用者只可軟刪（is_active=false），不可硬刪（E1）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import NotFoundError
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.schemas.v2.vocab import VocabItemIn, VocabItemOut, VocabPatchIn

router = APIRouter(prefix="/api/v2", tags=["v2-vocab"])


def _vocab_not_found(item_id: uuid.UUID) -> NotFoundError:
    """ADR-034 §D3/A4：詞彙 404 → NotFoundError 統一信封（結構化 detail + 相容鍵）。"""
    msg = f"詞彙不存在：{item_id}"
    return NotFoundError(msg, detail={"code": ErrorCode.NOT_FOUND, "resource": "vocab", "id": str(item_id), "_compat_detail": msg})


def _out(v: WorkVocabItem) -> VocabItemOut:
    return VocabItemOut(id=v.id, kind=v.kind, name_zh=v.name_zh, name_en=v.name_en,
                        external_code=v.external_code, source_system=v.source_system, is_active=v.is_active)


@router.get("/vocab", response_model=list[VocabItemOut])
async def list_vocab(
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    include_inactive: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[VocabItemOut]:
    stmt = select(WorkVocabItem).where(WorkVocabItem.deleted_at.is_(None))
    if not include_inactive:
        stmt = stmt.where(WorkVocabItem.is_active.is_(True))
    if kind:
        stmt = stmt.where(WorkVocabItem.kind == kind)
    if q:
        stmt = stmt.where(WorkVocabItem.name_zh.ilike(f"%{q}%"))
    stmt = stmt.order_by(WorkVocabItem.kind, WorkVocabItem.name_zh).offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [_out(v) for v in rows]


@router.post("/vocab", response_model=VocabItemOut, status_code=201)
async def create_vocab(payload: VocabItemIn, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(require_role("analyst"))) -> VocabItemOut:
    v = WorkVocabItem(id=uuid.uuid4(), kind=payload.kind, name_zh=payload.name_zh, name_en=payload.name_en,
                      external_code=payload.external_code or None, source_system=payload.source_system, site_id=payload.site_id)
    session.add(v)
    await session.flush()
    return _out(v)


@router.patch("/vocab/{item_id}", response_model=VocabItemOut)
async def patch_vocab(item_id: uuid.UUID, payload: VocabPatchIn, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(require_role("analyst"))) -> VocabItemOut:
    v = await session.get(WorkVocabItem, item_id)
    if v is None or v.deleted_at is not None:
        raise _vocab_not_found(item_id)
    if payload.name_zh is not None:
        v.name_zh = payload.name_zh
    if "name_en" in payload.model_fields_set:
        # 用「有沒有送這個鍵」而不是「值是不是 None」判斷——schema 把空白/空字串的英文名
        # 正規化成 None（清掉英文名是合法操作），若照 `is not None` 判會變成靜默不生效。
        v.name_en = payload.name_en
    if payload.external_code is not None:
        v.external_code = payload.external_code or None
    if payload.is_active is not None:
        v.is_active = payload.is_active
    await session.flush()
    return _out(v)


@router.delete("/vocab/{item_id}", status_code=204)
async def soft_delete_vocab(item_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(require_role("analyst"))) -> None:
    v = await session.get(WorkVocabItem, item_id)
    if v is None or v.deleted_at is not None:
        raise _vocab_not_found(item_id)
    v.is_active = False
    v.deleted_at = datetime.now(timezone.utc)
    await session.flush()
