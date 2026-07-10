"""v2 rule-set 編輯/版本化 API（#1）。list / full / clone-draft / put-full / publish。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.services.v2 import rule_set_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-ruleset"])


class CloneDraftIn(BaseModel):
    new_code: str
    name_zh: str | None = None


@router.get("/rule-sets")
async def list_rule_sets(session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> list[dict]:
    return await svc.list_rule_sets(session)


@router.get("/rule-sets/{code}/full")
async def get_full(code: str, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await svc.load_full(session, code)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")


@router.post("/rule-sets/{code}/clone-draft")
async def clone_draft(code: str, payload: CloneDraftIn, session: AsyncSession = Depends(get_db_session),
                      _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.clone_draft(session, code, payload.new_code, payload.name_zh)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.RuleSetExists:
        raise HTTPException(status_code=409, detail=f"code 已存在：{payload.new_code}")


@router.put("/rule-sets/{code}/full")
async def put_full(code: str, full: dict[str, Any] = Body(...), session: AsyncSession = Depends(get_db_session),
                   _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.replace_children(session, code, full)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/rule-sets/{code}/publish")
async def publish(code: str, session: AsyncSession = Depends(get_db_session),
                  user: CurrentUser = Depends(require_role("approver"))) -> dict:
    try:
        return await svc.publish(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
