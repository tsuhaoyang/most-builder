"""i18n 覆核狀態 API（ADR-032 D6）：待審清單摘要 ＋ 清單。

GET /api/v2/i18n/review/summary ：`{total, reviewed, pending}`（analyst+）
GET /api/v2/i18n/review/pending ：待審列表，可篩 entity_type/status（analyst+）

角色＝analyst 以上（D6：取字典 admin 入口與主數據 analyst 入口的**下界**——
清單同時涵蓋兩類物件，不落在任何單一既有入口之下；沿用既有 `require_role`，
不另造權限模型）。本輪只有讀端點；覆核（標記完成）留給下一輪前端 + 對應的
mutation 端點。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, require_role
from ddm_v2.database import get_db_session
from ddm_v2.schemas.v2.i18n import I18nPendingItemOut, I18nReviewSummaryOut
from ddm_v2.services.v2 import i18n_service as svc

router = APIRouter(prefix="/api/v2/i18n", tags=["v2-i18n"])

_ENTITY_TYPE_PATTERN = r"^(rule_option|vocab_item|motion_template)$"
_STATUS_PATTERN = r"^(never_translated|unreviewed|stale)$"


@router.get("/review/summary", response_model=I18nReviewSummaryOut)
async def get_review_summary(
    entity_type: str | None = Query(default=None, pattern=_ENTITY_TYPE_PATTERN),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> I18nReviewSummaryOut:
    data = await svc.summary(session, entity_type=entity_type)
    return I18nReviewSummaryOut(**data)


@router.get("/review/pending", response_model=list[I18nPendingItemOut])
async def list_review_pending(
    entity_type: str | None = Query(default=None, pattern=_ENTITY_TYPE_PATTERN),
    status: str | None = Query(default=None, pattern=_STATUS_PATTERN),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> list[I18nPendingItemOut]:
    rows = await svc.pending_rows(session, entity_type=entity_type, status=status)
    return [
        I18nPendingItemOut(
            entity_type=r.entity_type,  # type: ignore[arg-type]
            scope_key=r.scope_key,
            field=r.field,
            status=r.status,  # type: ignore[arg-type]
            rule_set_code=r.rule_set_code,
            source_zh=r.source_zh,
            target_en=r.target_en,
            source_changed=r.source_changed,
            review_source=r.review_source,  # type: ignore[arg-type]
            translated_by=r.translated_by,
            translated_at=r.translated_at,
            reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at,
        )
        for r in rows
    ]
