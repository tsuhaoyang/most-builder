"""v2 rule-set 編輯/版本化 API（#1）。

list / active / full / clone-draft / put-full / publish / activate / retire。
生命週期契約見 ADR-023 §3.2。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.services.v2 import rule_set_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-ruleset"])


class CloneDraftIn(BaseModel):
    # ADR-023 §3.2：選填，缺省由服務層生成 {code}_DRAFT_{YYYYMMDDHHMM}（查重附序號）。
    new_code: str | None = None
    name_zh: str | None = None


@router.get("/rule-sets")
async def list_rule_sets(
    selectable: bool = Query(False, description="只回 published+active（供 UI 下拉；ADR-023 §3.4 規則 2）"),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[dict]:
    return await svc.list_rule_sets(session, selectable=selectable)


@router.get("/rule-sets/active")
async def get_active(session: AsyncSession = Depends(get_db_session, scope="function"),
                     _: CurrentUser = Depends(current_user)) -> dict:
    """目前啟用中的 rule-set（前端取代寫死常數；ADR-023 §3.5）。無 active＝設定錯誤 → 500。"""
    rs = await svc.get_active_rule_set(session)
    return {"id": str(rs.id), "code": rs.code, "name_zh": rs.name_zh}


@router.get("/rule-sets/{code}/full")
async def get_full(code: str, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> dict:
    try:
        return await svc.load_full(session, code)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")


@router.post("/rule-sets/{code}/clone-draft")
async def clone_draft(code: str, payload: CloneDraftIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                      _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.clone_draft(session, code, payload.new_code, payload.name_zh)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.RuleSetExists:
        raise HTTPException(status_code=409, detail=f"code 已存在：{payload.new_code}")


@router.put("/rule-sets/{code}/full")
async def put_full(code: str, full: dict[str, Any] = Body(...), session: AsyncSession = Depends(get_db_session, scope="function"),
                   _: CurrentUser = Depends(require_role("analyst"))) -> dict:
    try:
        return await svc.replace_children(session, code, full)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/rule-sets/{code}/publish")
async def publish(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                  user: CurrentUser = Depends(require_role("approver"))) -> dict:
    try:
        return await svc.publish(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuleSetIncomplete as e:
        # ADR-023 §3.2：發布前完整性驗證未過 → 409（帶缺表詳情）。
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_INCOMPLETE", "message": str(e)})


@router.post("/rule-sets/{code}/activate")
async def activate(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                   user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """啟用為唯一 active 版本（ADR-023 §3.2）。非 published → 400；不完整 → 409。"""
    try:
        return await svc.activate(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuleSetIncomplete as e:
        raise HTTPException(status_code=409, detail={"code": "RULE_SET_INCOMPLETE", "message": str(e)})


@router.post("/rule-sets/{code}/retire")
async def retire(code: str, session: AsyncSession = Depends(get_db_session, scope="function"),
                 user: CurrentUser = Depends(require_role("approver"))) -> dict:
    """下架版本（ADR-023 §3.2）。啟用中版本 → 400（須先啟用其他版本）。

    ⚠️ 下架不影響回放：已引用該版本的 cycle 仍可載入重算（§3.4）。
    """
    try:
        return await svc.retire(session, code, actor=user.employee_no)
    except svc.RuleSetNotFound:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    except svc.NotEditable as e:
        raise HTTPException(status_code=400, detail=str(e))
