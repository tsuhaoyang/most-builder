"""距離建議與距離設定 API（ADR-038 D5.6 修訂，W7b）。

GET  /api/v2/worksheets/{worksheet_id}/distance-suggestions          存著的建議（viewer）
POST /api/v2/worksheets/{worksheet_id}/distance-suggestions/compute  依區域座標重新算（analyst；草稿版本）
POST /api/v2/worksheets/{worksheet_id}/distance-suggestions/apply    確認並套用到工時表（analyst；草稿版本）
GET  /api/v2/modeling-policy/distance-settings                       新建工時表會用的距離設定（viewer）
POST /api/v2/modeling-policy/distance-settings                       發布新的距離設定（admin）

套用：每一列的每一格都要是 `suggested`，否則 409 `DISTANCE_NOT_APPLICABLE`（列出列與原因）；重算結果和存著的
不同 → 409 `DISTANCE_SUGGESTION_CHANGED`（要重新算再確認）；revision 不符 → 409 `WORKSHEET_REVISION_CONFLICT`。
成功時走整份存檔，那些列的距離狀態設為 confirmed，TMU 由引擎重算。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ServiceUnavailableError, ValidationError
from ddm_v2.models.v2.distance import WiRowDistanceSuggestion
from ddm_v2.most_engine import SequenceError
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.distance import (
    DistanceApplyIn,
    DistanceSettingsIn,
    DistanceSettingsOut,
    DistanceSuggestionListOut,
    DistanceSuggestionOut,
)
from ddm_v2.schemas.v2.worksheet import WorksheetReadOut
from ddm_v2.services.v2 import distance_service as svc
from ddm_v2.services.v2 import policy_service

router = APIRouter(prefix="/api/v2", tags=["v2-distance"])

MAX_REPORTED = 200


def _not_found(worksheet_id: uuid.UUID) -> NotFoundError:
    return NotFoundError(
        f"worksheet 不存在：{worksheet_id}",
        detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id)},
    )


def _out(worksheet_id: uuid.UUID, items: list[WiRowDistanceSuggestion]) -> DistanceSuggestionListOut:
    return DistanceSuggestionListOut(worksheet_id=worksheet_id, items=[
        DistanceSuggestionOut(
            wi_row_id=s.wi_row_id, slot=s.slot, status=s.status, field=s.field,  # type: ignore[arg-type]
            distance_cm=float(s.distance_cm) if s.distance_cm is not None else None, reason=s.reason,
            endpoints=s.endpoints, snapshot_id=s.snapshot_id, threshold_cm=float(s.threshold_cm),
            person_offset_cm=list(s.person_offset_cm), modeling_policy_version_id=s.modeling_policy_version_id,
            computed_by=s.computed_by, computed_at=s.computed_at, applied_by=s.applied_by, applied_at=s.applied_at,
        )
        for s in items
    ])


@router.get("/worksheets/{worksheet_id}/distance-suggestions", response_model=DistanceSuggestionListOut)
async def list_suggestions(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> DistanceSuggestionListOut:
    try:
        items = await svc.list_suggestions(session, worksheet_id)
    except svc.WorksheetNotFound:
        raise _not_found(worksheet_id) from None
    return _out(worksheet_id, items)


@router.post("/worksheets/{worksheet_id}/distance-suggestions/compute", response_model=DistanceSuggestionListOut)
async def compute(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> DistanceSuggestionListOut:
    try:
        items = await svc.compute_and_store(session, worksheet_id, actor=user.employee_no)
    except svc.WorksheetNotFound:
        raise _not_found(worksheet_id) from None
    except svc.NotEditable as exc:
        raise ConflictError(str(exc), detail={"code": ErrorCode.CONFLICT}) from None
    return _out(worksheet_id, items)


@router.post("/worksheets/{worksheet_id}/distance-suggestions/apply", response_model=WorksheetReadOut)
async def apply(
    worksheet_id: uuid.UUID,
    payload: DistanceApplyIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await svc.apply_suggestions(
            session, worksheet_id, payload.wi_row_ids, base_revision=payload.base_revision,
            computed_at=payload.computed_at, actor=user.employee_no,
        )
    except svc.WorksheetNotFound:
        raise _not_found(worksheet_id) from None
    except svc.NotEditable as exc:
        raise ConflictError(str(exc), detail={"code": ErrorCode.CONFLICT}) from None
    except svc.NotApplicable as exc:
        items = sorted(exc.rows.items(), key=lambda kv: str(kv[0]))
        raise ConflictError(str(exc), detail={
            "code": ErrorCode.DISTANCE_NOT_APPLICABLE, "row_count": len(items),
            "rows": [{"wi_row_id": str(k), "reason": v} for k, v in items[:MAX_REPORTED]],
        }) from None
    except svc.MixedRuleSets as exc:
        raise ConflictError(
            "工時表各列的規則版本不一致，無法自動套用距離（請先統一規則版本）",
            detail={"code": ErrorCode.CONFLICT, "field": "rule_set_code", "rule_set_codes": list(exc.args[0])[:20]},
        ) from None
    except svc.SuggestionChanged as exc:
        raise ConflictError(str(exc), detail={
            "code": ErrorCode.DISTANCE_SUGGESTION_CHANGED, "row_count": len(exc.rows),
            "wi_row_ids": [str(r) for r in exc.rows[:MAX_REPORTED]],
        }) from None
    except SequenceError as e:
        # 套用後引擎算不過（例：foot 超出值表）：同整份存檔的回應形狀（code＝引擎錯誤碼，帶 seq_no／row_id）
        compat: dict = {"code": e.code, "message": str(e)}
        row_id = getattr(e, "row_id", None)
        if row_id is not None:
            compat["seq_no"] = getattr(e, "seq_no", None)
            compat["row_id"] = str(row_id)
        raise ValidationError(str(e), detail={**compat}) from None
    except RuleSetIncomplete as e:
        raise ConflictError(str(e), detail={"code": ErrorCode.RULE_SET_INCOMPLETE}) from None
    # WORKSHEET_REVISION_CONFLICT 是 ConflictError，由全域 handler 回 409


async def _current_settings(session: AsyncSession) -> DistanceSettingsOut:
    try:
        policy = await policy_service.get_default_modeling_policy(session)
    except policy_service.NoDefaultPolicy as exc:
        raise ServiceUnavailableError(str(exc), detail={"code": ErrorCode.NO_DEFAULT_POLICY}) from None
    settings, source = policy_service.distance_settings(policy)
    return DistanceSettingsOut(
        modeling_policy_version_id=policy.id, version_no=policy.version_no, source=source,  # type: ignore[arg-type]
        reach_foot_threshold_cm=settings["reach_foot_threshold_cm"], person_offset_cm=settings["person_offset_cm"],
    )


@router.get("/modeling-policy/distance-settings", response_model=DistanceSettingsOut)
async def get_settings(
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> DistanceSettingsOut:
    return await _current_settings(session)


@router.post("/modeling-policy/distance-settings", response_model=DistanceSettingsOut, status_code=201)
async def publish_settings(
    payload: DistanceSettingsIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("admin")),
) -> DistanceSettingsOut:
    try:
        await policy_service.publish_distance_settings(
            session, reach_foot_threshold_cm=payload.reach_foot_threshold_cm,
            person_offset_cm=payload.person_offset_cm, actor=user.employee_no,
        )
    except policy_service.NoDefaultPolicy as exc:
        raise ServiceUnavailableError(str(exc), detail={"code": ErrorCode.NO_DEFAULT_POLICY}) from None
    return await _current_settings(session)
