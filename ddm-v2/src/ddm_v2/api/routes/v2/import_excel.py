"""v2 Excel 匯入 API（Phase 2a，ADR-013）：upload → map(preview) → staging；profiles 可重用。

讀＝viewer+；上傳/對應/存 profile＝analyst+。2a 只到 staging，不進 worksheet（提交政策＝2b）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationError,
)
from ddm_v2.models.v2.import_staging import ExcelImport, ImportProfile
from ddm_v2.schemas.v2.import_excel import (
    MapIn,
    PreviewOut,
    ProfileIn,
    ProfileOut,
    SheetPreview,
    UploadOut,
)
from ddm_v2.services.v2 import import_service

router = APIRouter(prefix="/api/v2/imports", tags=["v2-imports"])

_PREVIEW_ROWS = 30  # 回應只帶前 N 列供選表頭/欄位（staging 存完整）

# 上傳位元組上限（security F2）：`file.read()` 整份進記憶體，無上限＝任何 analyst
# 一支請求就能打爆 RAM。10 MiB 的依據：真實 WI 工時表實測 <1 MiB（純儲存格資料，
# _MAX_ROWS=1000×_MAX_COLS=60 也只會取用到前面一小段），10 MiB 已是 10 倍餘裕；
# 再大的檔幾乎必然是貼了圖片/嵌入物件的工作簿，本功能只讀 cell 值，收下也沒意義。
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _profile_out(p: ImportProfile) -> ProfileOut:
    return ProfileOut(id=p.id, name=p.name, sheet_hint=p.sheet_hint, header_row=p.header_row,
                      column_map=dict(p.column_map or {}), time_unit=p.time_unit, owner=p.owner)


@router.post("/upload", response_model=UploadOut)
async def upload(file: UploadFile = File(...), worksheet_id: uuid.UUID | None = None,
                 session: AsyncSession = Depends(get_db_session, scope="function"),
                 actor: CurrentUser = Depends(require_role("analyst"))) -> UploadOut:
    # 讀上限+1 位元組即可判斷超限，不把整份超大檔吸進記憶體才檢查。
    content = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        msg = (
            f"檔案超過上限 {_MAX_UPLOAD_BYTES // (1024 * 1024)} MiB，"
            "請移除圖片/嵌入物件或拆分工作簿後重試"
        )
        raise PayloadTooLargeError(
            msg,
            detail={
                "code": ErrorCode.PAYLOAD_TOO_LARGE,
                "max_bytes": _MAX_UPLOAD_BYTES,
                "_compat_detail": msg,
            },
        )
    try:
        raw = import_service.parse_workbook(content)
    except Exception as e:  # noqa: BLE001
        msg = f"無法解析 Excel：{e}"
        raise ValidationError(
            msg,
            detail={"code": ErrorCode.VALIDATION_ERROR, "_compat_detail": msg},
        ) from e
    if not raw["sheets"]:
        raise ValidationError(
            "檔案沒有可讀的分頁",
            detail={"code": ErrorCode.VALIDATION_ERROR, "_compat_detail": "檔案沒有可讀的分頁"},
        )

    rec = ExcelImport(id=uuid.uuid4(), worksheet_id=worksheet_id, source_name=file.filename,
                      status="uploaded", raw_payload=raw, imported_by=actor.employee_no)
    session.add(rec)
    await session.flush()

    first = raw["sheets"][0]
    suggested_hr = import_service.suggest_header_row(first["grid"])
    profiles = (await session.execute(select(ImportProfile).order_by(ImportProfile.name))).scalars().all()
    sheets = [SheetPreview(name=s["name"], grid=[r for r in s["grid"][:_PREVIEW_ROWS]],
                           n_rows=s["n_rows"], n_cols=s["n_cols"]) for s in raw["sheets"]]
    return UploadOut(import_id=rec.id, source_name=file.filename, sheets=sheets,
                     suggested_sheet=first["name"], suggested_header_row=suggested_hr,
                     profiles=[_profile_out(p) for p in profiles])


@router.post("/{import_id}/map", response_model=PreviewOut)
async def map_columns(import_id: uuid.UUID, payload: MapIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                      _: CurrentUser = Depends(require_role("analyst"))) -> PreviewOut:
    rec = await session.get(ExcelImport, import_id)
    if rec is None:
        raise NotFoundError(
            "匯入批次不存在",
            detail={"code": ErrorCode.NOT_FOUND, "resource": "import", "_compat_detail": "匯入批次不存在"},
        )
    rows, warnings = import_service.apply_mapping(rec.raw_payload, payload.sheet, payload.header_row,
                                                  payload.column_map, payload.time_unit)
    rec.sheet, rec.header_row = payload.sheet, payload.header_row
    rec.column_map, rec.time_unit = payload.column_map, payload.time_unit
    rec.staged_rows, rec.status = rows, "mapped"   # 存乾淨列（match 不落 schema，回應時才附）
    await session.flush()
    fields = [f for f in payload.column_map]
    # ADR-025 D10：逐行併入範本建議（match + 以 active 重算 TMU）；不改動已存的 staged_rows。
    enriched = await import_service.build_row_matches(session, rows)
    return PreviewOut(import_id=import_id, fields=fields, rows=enriched, n=len(enriched), warnings=warnings)


@router.get("/{import_id}", response_model=PreviewOut)
async def get_import(import_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                     _: CurrentUser = Depends(current_user)) -> PreviewOut:
    rec = await session.get(ExcelImport, import_id)
    if rec is None:
        raise NotFoundError(
            "匯入批次不存在",
            detail={"code": ErrorCode.NOT_FOUND, "resource": "import", "_compat_detail": "匯入批次不存在"},
        )
    rows = rec.staged_rows or []
    # ADR-025 D10：match 以「現在」的 active 重算，不持久化 → GET 每次重新計算（避免 stale TMU）。
    enriched = await import_service.build_row_matches(session, rows)
    return PreviewOut(import_id=import_id, fields=list((rec.column_map or {}).keys()),
                      rows=enriched, n=len(enriched), warnings=[])


@router.get("/profiles/list", response_model=list[ProfileOut])
async def list_profiles(session: AsyncSession = Depends(get_db_session, scope="function"), _: CurrentUser = Depends(current_user)) -> list[ProfileOut]:
    rows = (await session.execute(select(ImportProfile).order_by(ImportProfile.name))).scalars().all()
    return [_profile_out(p) for p in rows]


@router.post("/profiles", response_model=ProfileOut, status_code=201)
async def create_profile(payload: ProfileIn, session: AsyncSession = Depends(get_db_session, scope="function"),
                         actor: CurrentUser = Depends(require_role("analyst"))) -> ProfileOut:
    p = ImportProfile(id=uuid.uuid4(), name=payload.name, sheet_hint=payload.sheet_hint,
                      header_row=payload.header_row, column_map=payload.column_map,
                      time_unit=payload.time_unit, owner=actor.employee_no)
    session.add(p)
    await session.flush()
    return _profile_out(p)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: uuid.UUID, session: AsyncSession = Depends(get_db_session, scope="function"),
                         _: CurrentUser = Depends(require_role("analyst"))) -> None:
    p = await session.get(ImportProfile, profile_id)
    if p is not None:
        await session.delete(p)
        await session.flush()


# ── Phase 2b：提交 staged rows → worksheet ──────────────────────────────────────

class RowAdoption(BaseModel):
    """ADR-025 D10：採用某暫存列的範本建議。**只收 template_id**，TMU 一律後端以 active 重算。"""
    row_index: int
    template_id: uuid.UUID


class SubmitIn(BaseModel):
    worksheet_id: uuid.UUID
    rule_set_code: str | None = None
    row_adoptions: list[RowAdoption] = Field(default_factory=list)
    # R1：樂觀鎖（過渡期可省略）
    base_revision: int | None = Field(default=None, ge=1)


class SubmitOut(BaseModel):
    worksheet_id: str
    n_rows: int
    n_with_analysis: int
    n_need_review: int
    warnings: list[str]
    revision_no: int | None = None
    content_hash: str | None = None


@router.post("/{import_id}/submit", response_model=SubmitOut)
async def submit_import(
    import_id: uuid.UUID,
    payload: SubmitIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    actor: CurrentUser = Depends(require_role("analyst")),
) -> SubmitOut:
    """Phase 2b：staged rows → worksheet WiRow（stub MOST cycle，analyst 後補分析）。"""
    try:
        result = await import_service.submit_to_worksheet(
            session, import_id, payload.worksheet_id, payload.rule_set_code, actor.employee_no,
            row_adoptions=payload.row_adoptions,
            base_revision=payload.base_revision,
        )
    except ValueError as e:
        code = str(e)
        if code == "import_not_found":
            raise NotFoundError(
                "匯入批次不存在",
                detail={"code": ErrorCode.NOT_FOUND, "resource": "import", "_compat_detail": "匯入批次不存在"},
            ) from None
        if code == "already_submitted":
            # Fix-H2：已提交批次不得重複提交
            raise ConflictError(
                "此匯入批次已完成提交，如需再次匯入請重新上傳",
                detail={"code": ErrorCode.CONFLICT, "_compat_detail": "此匯入批次已完成提交，如需再次匯入請重新上傳"},
            ) from None
        if code == "import_not_mapped":
            raise ConflictError(
                "匯入批次尚未完成欄位對應（status 須為 mapped）",
                detail={"code": ErrorCode.CONFLICT, "_compat_detail": "匯入批次尚未完成欄位對應（status 須為 mapped）"},
            ) from None
        if code == "worksheet_not_found":
            raise NotFoundError(
                "工序表不存在",
                detail={"code": ErrorCode.NOT_FOUND, "resource": "worksheet", "_compat_detail": "工序表不存在"},
            ) from None
        if code == "worksheet_not_draft":
            # Fix-H3：只允許提交到 draft 工序表
            raise ConflictError(
                "工序表已發布或退役，無法新增列（須為 draft 狀態）",
                detail={"code": ErrorCode.CONFLICT, "_compat_detail": "工序表已發布或退役，無法新增列（須為 draft 狀態）"},
            ) from None
        if code == "no_staged_rows":
            raise ValidationError(
                "無暫存列可提交",
                detail={"code": ErrorCode.VALIDATION_ERROR, "_compat_detail": "無暫存列可提交"},
            ) from None
        raise ValidationError(
            str(e),
            detail={"code": ErrorCode.VALIDATION_ERROR, "_compat_detail": str(e)},
        ) from None
    return SubmitOut(**result)
