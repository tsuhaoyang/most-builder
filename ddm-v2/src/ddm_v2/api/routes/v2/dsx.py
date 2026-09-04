"""DSX 整合 API（MVP，只做 a3）：POST /api/v2/dsx/a3-distance。

DSX 整合 API 契約 v2 §3.1／§6。人類使用者觸發（WiWorkbench.tsx 的 a3/from/to
建立器面板選定 from/to 後），MOST 是呼叫方；`wi_row_id` optional——只有帶了才寫
`wi_row_dsx_suggestions`（出處快照），本端點不寫 wi_rows 本身。

`require_role("analyst")`（非只 `current_user`）：`wi_row_id` 有值時本端點會寫入
`wi_row_dsx_suggestions`，比照 `wi_context.py` 既有寫入端點的角色門檻（`current_user`
只保留給純讀取端點）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ServiceUnavailableError
from ddm_v2.schemas.v2.dsx import A3DistanceIn, A3DistanceOut, DsxUiUrlOut
from ddm_v2.services.v2 import dsx_service
from ddm_v2.settings import get_settings

router = APIRouter(prefix="/api/v2/dsx", tags=["v2-dsx"])


@router.get("/ui-url", response_model=DsxUiUrlOut)
async def dsx_ui_url(_: CurrentUser = Depends(current_user)) -> DsxUiUrlOut:
    return DsxUiUrlOut(url=get_settings().dsx_ui_url)


@router.post("/a3-distance", response_model=A3DistanceOut)
async def a3_distance(
    payload: A3DistanceIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> A3DistanceOut:
    try:
        result = await dsx_service.get_a3_distance(
            session,
            wi_row_id=payload.wi_row_id,
            from_vocab_id=payload.from_vocab_id,
            to_vocab_id=payload.to_vocab_id,
            actor=user.employee_no,
        )
    except RuntimeError as exc:
        # 設定錯誤（integration_enabled=1 但未設 base_url），比照 nl_draft 慣例回 503。
        msg = str(exc)
        raise ServiceUnavailableError(
            msg,
            detail={"code": ErrorCode.SERVICE_UNAVAILABLE},
        ) from exc
    return A3DistanceOut(**result)
