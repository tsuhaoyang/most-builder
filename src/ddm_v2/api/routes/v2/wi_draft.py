"""工作區編輯區 API（ADR-038 D2／D3，W1）。全部需要 analyst 以上（寫入工時表的同一門檻）。

GET    /api/v2/worksheets/{worksheet_id}/drafts          列出編輯區
POST   /api/v2/worksheets/{worksheet_id}/drafts          新增手動草稿列
PATCH  /api/v2/worksheet-drafts/{draft_id}               修改一列（回到 pending）
DELETE /api/v2/worksheet-drafts/{draft_id}               刪除一列（已寫入的不能刪）
POST   /api/v2/worksheets/{worksheet_id}/drafts/confirm  確認一些列或一整組
POST   /api/v2/worksheets/{worksheet_id}/drafts/commit   寫入工時表（已確認的列追加到表尾）
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.most_engine import SequenceError
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.wi_draft import (
    WiDraftCommitIn,
    WiDraftCommitOut,
    WiDraftConfirmIn,
    WiDraftCreateIn,
    WiDraftListOut,
    WiDraftOut,
    WiDraftPatchIn,
)
from ddm_v2.services.v2 import wi_draft_service as svc
from ddm_v2.services.v2.worksheet_service import NotEditable, RuleSetNotFound, WorksheetNotFound

router = APIRouter(prefix="/api/v2", tags=["v2-worksheet-drafts"])


def _not_found_ws(worksheet_id: uuid.UUID | str) -> NotFoundError:
    return NotFoundError(
        f"worksheet 不存在：{worksheet_id}",
        detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id)},
    )


def _not_found_draft(ids: str) -> NotFoundError:
    return NotFoundError(
        f"草稿列不存在：{ids}", detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet_draft"}
    )


def _map_common(exc: Exception, worksheet_id: uuid.UUID | str | None = None) -> Exception:
    if isinstance(exc, WorksheetNotFound):
        return _not_found_ws(worksheet_id or str(exc))
    if isinstance(exc, svc.DraftNotFound):
        return _not_found_draft(str(exc))
    if isinstance(exc, (NotEditable, svc.DraftStateConflict)):
        return ConflictError(str(exc), detail={"code": ErrorCode.CONFLICT})
    return exc


@router.get("/worksheets/{worksheet_id}/drafts", response_model=WiDraftListOut)
async def list_drafts(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> WiDraftListOut:
    try:
        drafts = await svc.list_drafts(session, worksheet_id)
    except WorksheetNotFound:
        raise _not_found_ws(worksheet_id) from None
    return WiDraftListOut(worksheet_id=worksheet_id, items=[WiDraftOut.model_validate(d, from_attributes=True) for d in drafts])


@router.post("/worksheets/{worksheet_id}/drafts", response_model=WiDraftListOut, status_code=201)
async def create_drafts(
    worksheet_id: uuid.UUID,
    payload: WiDraftCreateIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiDraftListOut:
    try:
        drafts = await svc.add_drafts(session, worksheet_id, payload.items, source="manual", actor=user.employee_no)
    except (WorksheetNotFound, NotEditable) as exc:
        raise _map_common(exc, worksheet_id) from None
    except svc.TooManyDrafts as exc:
        raise ValidationError(
            str(exc), detail={"code": ErrorCode.VALIDATION_ERROR, "field": "items",
                              "max": svc.MAX_DRAFTS_PER_WORKSHEET}
        ) from None
    return WiDraftListOut(worksheet_id=worksheet_id, items=[WiDraftOut.model_validate(d, from_attributes=True) for d in drafts])


@router.patch("/worksheet-drafts/{draft_id}", response_model=WiDraftOut)
async def patch_draft(
    draft_id: uuid.UUID,
    payload: WiDraftPatchIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiDraftOut:
    try:
        draft = await svc.patch_draft(session, draft_id, payload.content, actor=user.employee_no)
    except (WorksheetNotFound, svc.DraftNotFound, NotEditable, svc.DraftStateConflict) as exc:
        raise _map_common(exc) from None
    return WiDraftOut.model_validate(draft, from_attributes=True)


@router.delete("/worksheet-drafts/{draft_id}", status_code=204)
async def delete_draft(
    draft_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> Response:
    try:
        await svc.delete_draft(session, draft_id, actor=user.employee_no)
    except (WorksheetNotFound, svc.DraftNotFound, NotEditable, svc.DraftStateConflict) as exc:
        raise _map_common(exc) from None
    return Response(status_code=204)


@router.post("/worksheets/{worksheet_id}/drafts/confirm", response_model=WiDraftListOut)
async def confirm_drafts(
    worksheet_id: uuid.UUID,
    payload: WiDraftConfirmIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiDraftListOut:
    try:
        drafts = await svc.confirm_drafts(
            session, worksheet_id, draft_ids=payload.draft_ids, group_key=payload.group_key, actor=user.employee_no
        )
    except (WorksheetNotFound, svc.DraftNotFound, NotEditable, svc.DraftStateConflict) as exc:
        raise _map_common(exc, worksheet_id) from None
    return WiDraftListOut(worksheet_id=worksheet_id, items=[WiDraftOut.model_validate(d, from_attributes=True) for d in drafts])


@router.post("/worksheets/{worksheet_id}/drafts/commit", response_model=WiDraftCommitOut)
async def commit_drafts(
    worksheet_id: uuid.UUID,
    payload: WiDraftCommitIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> WiDraftCommitOut:
    """版本衝突走 `WorksheetRevisionConflict`（ConflictError，REVISION_CONFLICT），草稿維持已確認、整筆回滾。"""
    try:
        out, drafts = await svc.commit_drafts(
            session, worksheet_id, base_revision=payload.base_revision, actor=user.employee_no
        )
    except (WorksheetNotFound, NotEditable) as exc:
        raise _map_common(exc, worksheet_id) from None
    except svc.NothingToCommit:
        raise ValidationError(
            "編輯區沒有已確認的列可寫入", detail={"code": ErrorCode.VALIDATION_ERROR, "field": "status"}
        ) from None
    except svc.SourceNotCommittable as exc:
        raise ConflictError(str(exc), detail={"code": ErrorCode.CONFLICT, "field": "source"}) from None
    except svc.DraftContentInvalid as exc:
        raise ValidationError(
            str(exc), detail={"code": ErrorCode.VALIDATION_ERROR, "draft_id": str(exc.draft_id)}
        ) from None
    except svc.DraftComputeError as exc:
        # 引擎的 code 原樣帶出（ADR-034 §3：engine code 動態讀取）；row 定位改用草稿 id
        cause = exc.cause
        raise ValidationError(
            str(cause),
            detail={"code": getattr(cause, "code", ErrorCode.VALIDATION_ERROR), "message": str(cause),
                    "draft_id": str(exc.draft_id)},
        ) from None
    except RuleSetNotFound as exc:
        raise NotFoundError(
            f"rule-set 不存在：{exc}",
            detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": str(exc)},
        ) from None
    except RuleSetIncomplete as exc:
        raise ConflictError(str(exc), detail={"code": ErrorCode.RULE_SET_INCOMPLETE}) from None
    except SequenceError as exc:
        compat: dict = {"code": exc.code, "message": str(exc)}
        row_id = getattr(exc, "row_id", None)
        if row_id is not None:
            compat["seq_no"] = getattr(exc, "seq_no", None)
            compat["row_id"] = str(row_id)
        raise ValidationError(str(exc), detail={**compat}) from None
    return WiDraftCommitOut(
        worksheet_id=worksheet_id,
        revision_no=int(out["revision_no"]),
        committed=[WiDraftOut.model_validate(d, from_attributes=True) for d in drafts],
    )
