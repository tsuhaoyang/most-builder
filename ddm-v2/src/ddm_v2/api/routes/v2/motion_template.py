"""v2 動作範本庫 API：list / create / patch / delete / match。

讀＝viewer+；建立/修改/刪除＝analyst+。
match：以描述關鍵字比對範本（P2 匯入自動建 MOST 用），讀權限即可。
"""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.schemas.v2.motion_template import (
    MatchHit,
    MatchIn,
    MotionTemplateIn,
    MotionTemplateOut,
    MotionTemplatePatchIn,
)
from ddm_v2.services.v2.audit_service import log_audit

router = APIRouter(prefix="/api/v2", tags=["v2-motion-templates"])


def _out(t: MotionTemplate) -> MotionTemplateOut:
    return MotionTemplateOut(
        id=t.id, name_zh=t.name_zh, name_en=t.name_en, category=t.category,
        keywords=list(t.keywords or []), seq_kind=t.seq_kind,
        cycle_template=t.cycle_template, status=t.status, owner=t.owner, is_active=t.is_active,
    )


def _can_modify(t: MotionTemplate, user: CurrentUser) -> bool:
    """標準＝approver+ 才可改/刪；草稿＝擁有者本人或 approver+。"""
    if t.status == "standard":
        return user.level >= 2
    return user.level >= 2 or (t.owner == user.employee_no)


def _score(description: str, keywords: list[str]) -> tuple[float, list[str]]:
    """關鍵字比對：命中以關鍵字長度加權（越具體越高）。中文 substring、英文 word/substring 皆可。"""
    text = (description or "").lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    hits: list[str] = []
    score = 0.0
    for kw in keywords or []:
        k = str(kw).strip().lower()
        if not k:
            continue
        matched = (k in text) or (k in tokens)
        if matched:
            hits.append(kw)
            score += len(k)
    return score, hits


@router.get("/motion-templates", response_model=list[MotionTemplateOut])
async def list_templates(session: AsyncSession = Depends(get_db_session, scope="function"), user: CurrentUser = Depends(current_user)) -> list[MotionTemplateOut]:
    """標準範本（所有人）＋ 自己的草稿（僅擁有者）。"""
    rows = (await session.execute(
        select(MotionTemplate).where(MotionTemplate.is_active.is_(True)).order_by(MotionTemplate.status.desc(), MotionTemplate.category, MotionTemplate.name_zh)
    )).scalars().all()
    visible = [t for t in rows if t.status == "standard" or t.owner == user.employee_no]
    return [_out(t) for t in visible]


@router.post("/motion-templates", response_model=MotionTemplateOut, status_code=201)
async def create_template(payload: MotionTemplateIn, session: AsyncSession = Depends(get_db_session, scope="function"), actor: CurrentUser = Depends(require_role("analyst"))) -> MotionTemplateOut:
    """一律建為個人草稿（owner=建立者）；要成標準走 /promote。"""
    t = MotionTemplate(
        id=uuid.uuid4(), name_zh=payload.name_zh, name_en=payload.name_en, category=payload.category,
        keywords=payload.keywords, seq_kind=payload.seq_kind,
        cycle_template=payload.cycle_template.model_dump(mode="json"),
        status="draft", owner=actor.employee_no, created_by=actor.employee_no,
    )
    session.add(t)
    await session.flush()
    return _out(t)


@router.post("/motion-templates/{template_id}/promote", response_model=MotionTemplateOut)
async def promote_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), approver: CurrentUser = Depends(require_role("approver"))) -> MotionTemplateOut:
    """草稿 → 廠標準（approver+）。"""
    t = await session.get(MotionTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="範本不存在")
    prev_status = t.status
    t.status = "standard"
    t.owner = None
    await log_audit(
        session,
        entity_type="motion_template",
        entity_id=template_id,
        action="promote",
        from_status=prev_status,
        to_status="standard",
        actor=approver.employee_no,
    )
    await session.flush()
    return _out(t)


@router.patch("/motion-templates/{template_id}", response_model=MotionTemplateOut)
async def patch_template(template_id: uuid.UUID, payload: MotionTemplatePatchIn, session: AsyncSession = Depends(get_db_session, scope="function"), user: CurrentUser = Depends(require_role("analyst"))) -> MotionTemplateOut:
    t = await session.get(MotionTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="範本不存在")
    if not _can_modify(t, user):
        raise HTTPException(status_code=403, detail="標準範本需 approver+；草稿僅擁有者可改")
    if payload.name_zh is not None:
        t.name_zh = payload.name_zh
    if payload.name_en is not None:
        t.name_en = payload.name_en
    if payload.category is not None:
        t.category = payload.category
    if payload.keywords is not None:
        t.keywords = payload.keywords
    if payload.seq_kind is not None:
        t.seq_kind = payload.seq_kind
    if payload.cycle_template is not None:
        t.cycle_template = payload.cycle_template.model_dump(mode="json")
    if payload.is_active is not None:
        t.is_active = payload.is_active
    await session.flush()
    return _out(t)


@router.delete("/motion-templates/{template_id}", status_code=204)
async def delete_template(template_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"), user: CurrentUser = Depends(require_role("analyst"))) -> None:
    t = await session.get(MotionTemplate, template_id)
    if t is None:
        return
    if not _can_modify(t, user):
        raise HTTPException(status_code=403, detail="標準範本需 approver+；草稿僅擁有者可刪")
    await session.delete(t)
    await session.flush()


@router.post("/motion-templates/match", response_model=list[MatchHit])
async def match_templates(payload: MatchIn, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> list[MatchHit]:
    rows = (await session.execute(select(MotionTemplate).where(
        MotionTemplate.is_active.is_(True), MotionTemplate.status == "standard"))).scalars().all()  # 匯入只比對標準庫
    scored = []
    for t in rows:
        s, hits = _score(payload.description, list(t.keywords or []))
        if s > 0:
            scored.append((s, hits, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [MatchHit(template=_out(t), score=s, matched_keywords=hits) for s, hits, t in scored[: payload.limit]]
