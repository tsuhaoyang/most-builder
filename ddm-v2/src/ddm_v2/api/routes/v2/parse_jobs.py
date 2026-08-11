"""L4：批次 parse-jobs API（附掛 imports；不改 map/submit）。

POST   /api/v2/imports/{import_id}/parse-jobs
GET    /api/v2/imports/{import_id}/parse-jobs/{job_id}
POST   /api/v2/imports/{import_id}/parse-jobs/{job_id}/tick
POST   /api/v2/imports/{import_id}/parse-jobs/{job_id}/cancel
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.services.v2 import parse_job_service as svc
from ddm_v2.services.v2 import synonym_service as syn_svc

router = APIRouter(prefix="/api/v2/imports", tags=["v2-parse-jobs"])


class ParseJobCreateIn(BaseModel):
    rule_set_code: str = Field(..., min_length=1)
    idempotency_key: str | None = None
    bundle_code: str | None = None


class TickIn(BaseModel):
    limit: int = Field(default=1, ge=1, le=4)
    worker_id: str | None = None


@router.post("/{import_id}/parse-jobs", status_code=201)
async def create_parse_job(
    import_id: UUID,
    payload: ParseJobCreateIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await svc.create_parse_job(
            session,
            import_id=import_id,
            rule_set_code=payload.rule_set_code,
            requested_by=actor.employee_no,
            idempotency_key=payload.idempotency_key,
            bundle_code=payload.bundle_code,
        )
    except svc.ImportNotFound:
        raise HTTPException(status_code=404, detail="匯入批次不存在") from None
    except svc.NoStagedRows:
        raise HTTPException(status_code=422, detail="無可用暫存列（需先 map 且含 description）") from None
    except syn_svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule set 不存在：{payload.rule_set_code}") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.get("/{import_id}/parse-jobs/{job_id}")
async def get_parse_job(
    import_id: UUID,
    job_id: UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    try:
        return await svc.get_job(session, import_id=import_id, job_id=job_id)
    except svc.JobNotFound:
        raise HTTPException(status_code=404, detail="parse job 不存在") from None


@router.post("/{import_id}/parse-jobs/{job_id}/tick")
async def tick_parse_job(
    import_id: UUID,
    job_id: UUID,
    payload: TickIn | None = None,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """處理最多 limit 筆（≤4）。rule_set／bundle 一律用 job 建立時 pin 的值。"""
    body = payload or TickIn()
    try:
        return await svc.tick_job(
            session,
            import_id=import_id,
            job_id=job_id,
            limit=body.limit,
            worker_id=body.worker_id or f"api:{actor.employee_no}",
        )
    except svc.JobNotFound:
        raise HTTPException(status_code=404, detail="parse job 不存在") from None
    except syn_svc.RuleSetNotFound as exc:
        raise HTTPException(status_code=404, detail=f"pinned rule set 不存在：{exc}") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@router.post("/{import_id}/parse-jobs/{job_id}/cancel")
async def cancel_parse_job(
    import_id: UUID,
    job_id: UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await svc.request_cancel(session, import_id=import_id, job_id=job_id)
    except svc.JobNotFound:
        raise HTTPException(status_code=404, detail="parse job 不存在") from None
