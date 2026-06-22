"""v2 Excel 匯入 API（Phase 2a，ADR-013）：upload → map(preview) → staging；profiles 可重用。

讀＝viewer+；上傳/對應/存 profile＝IE+。2a 只到 staging，不進 worksheet（提交政策＝2b）。
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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
                 session: AsyncSession = Depends(get_db_session),
                 actor: CurrentUser = Depends(require_role("IE"))) -> UploadOut:
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
async def map_columns(import_id: uuid.UUID, payload: MapIn, session: AsyncSession = Depends(get_db_session),
                      _: CurrentUser = Depends(require_role("IE"))) -> PreviewOut:
    rec = await session.get(ExcelImport, import_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="匯入批次不存在")
    rows, warnings = import_service.apply_mapping(rec.raw_payload, payload.sheet, payload.header_row,
                                                  payload.column_map, payload.time_unit)
    rec.sheet, rec.header_row = payload.sheet, payload.header_row
    rec.column_map, rec.time_unit = payload.column_map, payload.time_unit
    rec.staged_rows, rec.status = rows, "mapped"
    await session.flush()
    fields = [f for f in payload.column_map]
    return PreviewOut(import_id=import_id, fields=fields, rows=rows, n=len(rows), warnings=warnings)


@router.get("/{import_id}", response_model=PreviewOut)
async def get_import(import_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                     _: CurrentUser = Depends(current_user)) -> PreviewOut:
    rec = await session.get(ExcelImport, import_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="匯入批次不存在")
    rows = rec.staged_rows or []
    return PreviewOut(import_id=import_id, fields=list((rec.column_map or {}).keys()),
                      rows=rows, n=len(rows), warnings=[])


@router.get("/profiles/list", response_model=list[ProfileOut])
async def list_profiles(session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> list[ProfileOut]:
    rows = (await session.execute(select(ImportProfile).order_by(ImportProfile.name))).scalars().all()
    return [_profile_out(p) for p in rows]


@router.post("/profiles", response_model=ProfileOut, status_code=201)
async def create_profile(payload: ProfileIn, session: AsyncSession = Depends(get_db_session),
                         actor: CurrentUser = Depends(require_role("IE"))) -> ProfileOut:
    p = ImportProfile(id=uuid.uuid4(), name=payload.name, sheet_hint=payload.sheet_hint,
                      header_row=payload.header_row, column_map=payload.column_map,
                      time_unit=payload.time_unit, owner=actor.employee_no)
    session.add(p)
    await session.flush()
    return _profile_out(p)


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_profile(profile_id: uuid.UUID, session: AsyncSession = Depends(get_db_session),
                         _: CurrentUser = Depends(require_role("IE"))) -> None:
    p = await session.get(ImportProfile, profile_id)
    if p is not None:
        await session.delete(p)
        await session.flush()
