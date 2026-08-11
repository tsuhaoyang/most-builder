"""AI review events API（L3）。

POST /api/v2/nl-drafts/{run_id}/reviews → 201（analyst+）
GET  /api/v2/nl-drafts/{run_id}/reviews → 200 list（viewer+，便於驗收查詢）
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.services.v2 import ai_review_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-ai-review"])

EVENT_TYPE_PATTERN = (
    "^(accept_plan|split_action|merge_actions|reorder_action|add_action|"
    "delete_action|replace_role|replace_candidate|change_sequence_model|"
    "change_quantity_policy|mark_missing|accept_all)$"
)


class ReviewEventIn(BaseModel):
    event_type: str = Field(..., pattern=EVENT_TYPE_PATTERN)
    target: dict | None = None
    before: dict | None = None
    after: dict | None = None
    reason: str | None = None


class ReviewBatchIn(BaseModel):
    events: list[ReviewEventIn] = Field(..., min_length=1)
    ui_version: str | None = None


@router.post("/nl-drafts/{run_id}/reviews", status_code=201)
async def post_reviews(
    run_id: UUID,
    payload: ReviewBatchIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await svc.record_reviews(
            session,
            run_id=run_id,
            events=[e.model_dump() for e in payload.events],
            reviewer=user.employee_no,
            ui_version=payload.ui_version,
        )
    except svc.RunNotFound:
        raise HTTPException(status_code=404, detail=f"parse run 不存在：{run_id}") from None
    except svc.ValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "VALIDATION_ERROR", "message": exc.message}
        ) from None


@router.get("/nl-drafts/{run_id}/reviews")
async def get_reviews(
    run_id: UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[dict]:
    # 確認 run 存在
    from ddm_v2.models.v2.ai_ops import AiParseRun

    run = await session.get(AiParseRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"parse run 不存在：{run_id}")
    return await svc.list_events_for_run(session, run_id)
