"""v2 Excel 匯入 API（Phase 2a，ADR-013）：upload → map(preview) → staging；profiles 可重用。

讀＝viewer+；上傳/對應/存 profile＝analyst+。2a 只到 staging，不進 worksheet（提交政策＝2b）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
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


def _profile_out(p: ImportProfile) -> ProfileOut:
    return ProfileOut(id=p.id, name=p.name, sheet_hint=p.sheet_hint, header_row=p.header_row,
                      column_map=dict(p.column_map or {}), time_unit=p.time_unit, owner=p.owner)


@router.post("/upload", response_model=UploadOut)
async def upload(file: UploadFile = File(...), worksheet_id: uuid.UUID | None = None,
                 session: AsyncSession = Depends(get_db_session, scope="function"),
                 actor: CurrentUser = Depends(require_role("analyst"))) -> UploadOut:
    content = await file.read()
    try:
        raw = import_service.parse_workbook(content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"無法解析 Excel：{e}") from e
    if not raw["sheets"]:
        raise HTTPException(status_code=422, detail="檔案沒有可讀的分頁")

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
        raise HTTPException(status_code=404, detail="匯入批次不存在")
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
        raise HTTPException(status_code=404, detail="匯入批次不存在")
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
            raise HTTPException(status_code=404, detail="匯入批次不存在")
        if code == "already_submitted":
            # Fix-H2：已提交批次不得重複提交
            raise HTTPException(status_code=409, detail="此匯入批次已完成提交，如需再次匯入請重新上傳")
        if code == "import_not_mapped":
            raise HTTPException(status_code=409, detail="匯入批次尚未完成欄位對應（status 須為 mapped）")
        if code == "worksheet_not_found":
            raise HTTPException(status_code=404, detail="工序表不存在")
        if code == "worksheet_not_draft":
            # Fix-H3：只允許提交到 draft 工序表
            raise HTTPException(status_code=409, detail="工序表已發布或退役，無法新增列（須為 draft 狀態）")
        if code == "no_staged_rows":
            raise HTTPException(status_code=422, detail="無暫存列可提交")
        raise HTTPException(status_code=422, detail=str(e))
    return SubmitOut(**result)
