"""v2 動作範本庫 API：list / create / patch / delete / match。

讀＝viewer+；建立/修改/刪除＝analyst+。
match：以描述關鍵字比對範本（P2 匯入自動建 MOST 用），讀權限即可。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ForbiddenError, NotFoundError
from ddm_v2.models.v2.motion_template import MotionTemplate
from ddm_v2.schemas.v2.most import CycleIn
from ddm_v2.schemas.v2.motion_template import (
    MatchHit,
    MatchIn,
    MotionTemplateIn,
    MotionTemplateOut,
    MotionTemplatePatchIn,
)
from ddm_v2.services.v2.audit_service import log_audit
from ddm_v2.services.v2.template_matching import score_template as _score

router = APIRouter(prefix="/api/v2", tags=["v2-motion-templates"])


def _dump_cycle(cycle: CycleIn) -> dict:
    """範本的 cycle 快照一律不含 rule_set_code（ADR-024 §3-2）。

    範本是「怎麼填七格」的樣板，不是回放快照——它沒有「當初用哪一版算的」這回事。
    套用時必須解析 active rule-set（ADR-023 §3.5），所以存一個版本代碼進去只會誤導：
    既有 16 筆存的是 legacy 的 MINIMOST_FACTORY_V1，P2 接上匯入後會靜默算錯 TMU。
    （對比：motion_module_versions.rows[].cycle 是回放權威，那裡必須留 rule_set_code。）
    """
    return cycle.model_dump(mode="json", exclude={"rule_set_code"})


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
        cycle_template=_dump_cycle(payload.cycle_template),
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
        raise NotFoundError("範本不存在", detail={"code": ErrorCode.NOT_FOUND, "resource": "motion_template", "id": str(template_id), "_compat_detail": "範本不存在"})
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
        raise NotFoundError("範本不存在", detail={"code": ErrorCode.NOT_FOUND, "resource": "motion_template", "id": str(template_id), "_compat_detail": "範本不存在"})
    if not _can_modify(t, user):
        raise ForbiddenError("標準範本需 approver+；草稿僅擁有者可改", detail={"code": ErrorCode.FORBIDDEN, "resource": "motion_template", "action": "modify", "_compat_detail": "標準範本需 approver+；草稿僅擁有者可改"})
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
        t.cycle_template = _dump_cycle(payload.cycle_template)
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
        raise ForbiddenError("標準範本需 approver+；草稿僅擁有者可刪", detail={"code": ErrorCode.FORBIDDEN, "resource": "motion_template", "action": "delete", "_compat_detail": "標準範本需 approver+；草稿僅擁有者可刪"})
    await session.delete(t)
    await session.flush()


@router.post("/motion-templates/match", response_model=list[MatchHit])
async def match_templates(payload: MatchIn, session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> list[MatchHit]:
    rows = (await session.execute(select(MotionTemplate).where(
        MotionTemplate.is_active.is_(True), MotionTemplate.status == "standard"))).scalars().all()  # 匯入只比對標準庫
    scored = []
    for t in rows:
        s, hits = _score(payload.description, t)   # 只傳範本物件；關鍵字由 template_matching 取（ADR-032 I3）
        if s > 0:
            scored.append((s, hits, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [MatchHit(template=_out(t), score=s, matched_keywords=hits) for s, hits, t in scored[: payload.limit]]
