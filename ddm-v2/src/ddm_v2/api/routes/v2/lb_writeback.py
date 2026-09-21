"""v2 LB 回寫消費 API（ADR-036 B5）。

5 端點：fetch（呼叫 LB 存快照）／import（測試離線驗證，走同一解析）／latest／snapshots／apply-offline（B6）。
權限（ADR-019）：讀 viewer+（current_user）、寫 IE+（require_role("analyst")）。
錯誤（ADR-034 單一信封）：contract 不符 → 422（LB_WRITEBACK_CONTRACT_MISMATCH）；座標格式／payload 格式錯、
舊快照讀不回 → 422（VALIDATION_ERROR）；LB 不可達 → 502（LB_UNREACHABLE）；LB 缺身分 header → 502
（LB_AUTH_REQUIRED）；LB 逾時 → 504（LB_TIMEOUT）；未設定 → 503（LB_NOT_CONFIGURED）。

非錯誤但需留意：apply-offline 的投影報告拋例外時**不回 5xx**，而是 200 ＋ `report.status="unavailable"`
（附 E 碼與完整診斷），離線設定照常套用；根因見 BL-ENG-2。

⚠️ v1 直連 LB 無認證，只可內網／本機（ADR-036 §4；掛 gateway 前不得對外開放）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import NotFoundError, ValidationError
from ddm_v2.services.v2 import lb_writeback_service as wb
from ddm_v2.services.v2 import worksheet_service as wsvc
from ddm_v2.services.v2.lb_client import LB_ID_PATTERN

router = APIRouter(prefix="/api/v2", tags=["v2-lb-writeback"])


class FetchIn(BaseModel):
    # 三個座標直接成為 LB URL 的路徑段：格式不合（`/`、`..`、空白、控制字元、超長…）→ 422，不呼叫 LB。
    lb_project_id: str = Field(pattern=LB_ID_PATTERN)
    lb_version_id: str = Field(pattern=LB_ID_PATTERN)
    lb_result_id: str = Field(pattern=LB_ID_PATTERN)


class ApplyOfflineIn(BaseModel):
    # UUID 型別：非 UUID → 422 VALIDATION_ERROR（原本在 route 內 uuid.UUID() 轉換，會落成無信封 500）。
    # 接受 canonical／32 位無連字號／`{…}`／`urn:uuid:`／大小寫不敏感，並正規化。pydantic 的 UUID parser
    # 比 D7 追記第 3 點的 `uuid.UUID()` **略嚴**（怪位置的連字號它不收）——刻意如此，兩者對正常輸入等價。
    # max_length：pydantic 對 list 逐項收集錯誤、每筆都回吐輸入值，無上限時回應會被放大數倍（實測 5000 筆
    # 壞值 → 回應 1.47 MB／約 6.7×）。設上限後只剩一筆 too_long，回應 ≈ 請求大小（1:1）——壓掉的是**放大
    # 倍率**，不是絕對大小（信封原樣回吐 `exc.errors()` 是 ADR-034 §D5 的契約，全域也沒有 body 大小上限）。
    snapshot_id: uuid.UUID
    wi_row_ids: list[uuid.UUID] = Field(min_length=1, max_length=1000)


def _wsnf(worksheet_id: uuid.UUID) -> NotFoundError:
    return NotFoundError(
        f"worksheet 不存在：{worksheet_id}",
        detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "worksheet_id": str(worksheet_id)},
    )


def _contract_mismatch(exc: wb.LbWritebackContractMismatch) -> ValidationError:
    return ValidationError(str(exc), detail={"code": ErrorCode.LB_WRITEBACK_CONTRACT_MISMATCH, "got": exc.got})


def _malformed(exc: wb.LbWritebackMalformed) -> ValidationError:
    return ValidationError(str(exc), detail={"code": ErrorCode.VALIDATION_ERROR})


def _stale_snapshot(exc: Exception) -> ValidationError:
    """已存的快照在現行（較嚴格）驗證下讀不回來（例如早期寬鬆匯入的 payload）：422，請重新取得，不落 500。"""
    return ValidationError(f"已存的回寫快照不符現行驗證，請重新取得：{exc}", detail={"code": ErrorCode.VALIDATION_ERROR})


@router.post("/worksheets/{worksheet_id}/lb-writeback/fetch")
async def fetch(
    worksheet_id: uuid.UUID, body: FetchIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        read = await wsvc.read_worksheet(session, worksheet_id)
    except wsvc.WorksheetNotFound as exc:
        raise _wsnf(worksheet_id) from exc
    try:
        return await wb.fetch_and_store(
            session, worksheet_id=worksheet_id, worksheet_read=read,
            lb_project_id=body.lb_project_id, lb_version_id=body.lb_version_id,
            lb_result_id=body.lb_result_id, actor=user.employee_no,
        )
    except wb.LbWritebackContractMismatch as exc:
        raise _contract_mismatch(exc) from exc
    except wb.LbWritebackMalformed as exc:
        raise _malformed(exc) from exc


@router.post("/worksheets/{worksheet_id}/lb-writeback/import")
async def import_payload(
    worksheet_id: uuid.UUID, payload: dict,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    """測試／離線驗證用：直接吃回寫 payload 原樣，走同一解析／存檔路徑。"""
    try:
        read = await wsvc.read_worksheet(session, worksheet_id)
    except wsvc.WorksheetNotFound as exc:
        raise _wsnf(worksheet_id) from exc
    try:
        return await wb.import_and_store(
            session, worksheet_id=worksheet_id, worksheet_read=read, payload=payload, actor=user.employee_no,
        )
    except wb.LbWritebackContractMismatch as exc:
        raise _contract_mismatch(exc) from exc
    except wb.LbWritebackMalformed as exc:
        raise _malformed(exc) from exc


@router.get("/worksheets/{worksheet_id}/lb-writeback/latest")
async def latest(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    try:
        read = await wsvc.read_worksheet(session, worksheet_id)
    except wsvc.WorksheetNotFound as exc:
        raise _wsnf(worksheet_id) from exc
    try:
        return await wb.latest(session, worksheet_id=worksheet_id, worksheet_read=read)
    except (wb.LbWritebackContractMismatch, wb.LbWritebackMalformed) as exc:
        raise _stale_snapshot(exc) from exc


@router.get("/worksheets/{worksheet_id}/lb-writeback/snapshots")
async def snapshots(
    worksheet_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    return {"snapshots": await wb.list_snapshots(session, worksheet_id=worksheet_id)}


@router.post("/worksheets/{worksheet_id}/lb-writeback/apply-offline")
async def apply_offline(
    worksheet_id: uuid.UUID, body: ApplyOfflineIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await wb.apply_offline(
            session, worksheet_id=worksheet_id, snapshot_id=body.snapshot_id,
            wi_row_ids=body.wi_row_ids, actor=user.employee_no,
        )
    except wsvc.WorksheetNotFound as exc:
        raise _wsnf(worksheet_id) from exc
    except (wb.LbWritebackContractMismatch, wb.LbWritebackMalformed) as exc:
        raise _stale_snapshot(exc) from exc
