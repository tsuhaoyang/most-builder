"""v2 計算 API：把 most_engine 包成端點，產 OpenAPI 供前端型別。

- POST /api/v2/minimost/calculate ：cycle DTO → 權威 TMU + per-slot breakdown
- POST /api/v2/level/validate      ：level rows → R1–R9 issues
- POST /api/v2/level/build-output  ：→ Line Balance 輸出合約（先驗證再產）

rule-set：calculate 依 session 從 **DB** 載入（統一資料源，含完整性 gating）。
options 下拉清單暫讀 seed labels（FE-1 正式版改讀 DB labels）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.most_engine import RuleSetData, SequenceError, compute_cycle, load_rule_set_from_db
from ddm_v2.most_engine import level as level_engine
from ddm_v2.most_engine.providers import load_options_from_db
from ddm_v2.most_engine.rule_set_data import RuleSetIncomplete
from ddm_v2.schemas.v2.most import (
    CalculateResponse,
    CycleIn,
    LevelOutputResponse,
    LevelRowIn,
    LevelValidateResponse,
    SlotBreakdown,
    cycle_in_to_engine,
)

router = APIRouter(prefix="/api/v2", tags=["v2-most"])

@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)) -> dict:
    """目前登入者（前端 role-gating 用）。"""
    return {"employee_no": user.employee_no, "roles": user.roles, "plant_code": user.plant_code, "level": user.level}


async def _load_rule_set(session: AsyncSession, code: str) -> RuleSetData:
    """依 code 從 DB 載入 rule-set；缺 → 404，缺表 → 409（完整性 gating）。"""
    try:
        rs = await load_rule_set_from_db(session, code)
    except NoResultFound as e:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}") from e
    rs.validate_complete()
    return rs


@router.get("/rule-sets/{code}/options")
async def rule_set_options(code: str, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> dict:
    """下拉用：含 label（中/英）的選項清單，從 DB 載（FE-1 正式版，與 calculate 同源）。"""
    opts = await load_options_from_db(session, code)
    if opts is None:
        raise HTTPException(status_code=404, detail=f"rule-set 不存在：{code}")
    return opts


@router.post("/minimost/calculate", response_model=CalculateResponse)
async def calculate(cycle: CycleIn, session: AsyncSession = Depends(get_db_session), _: CurrentUser = Depends(current_user)) -> CalculateResponse:
    try:
        rs = await _load_rule_set(session, cycle.rule_set_code)
    except RuleSetIncomplete as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    try:
        result = compute_cycle(cycle_in_to_engine(cycle), rs)
    except SequenceError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": str(e)}) from e
    return CalculateResponse(
        seq=result.seq,
        rule_set_code=rs.code,
        total_tmu=result.total_tmu,
        total_seconds=result.total_seconds,
        tech_line=result.tech_line,
        breakdown=[SlotBreakdown(letter=L, tmu=t) for L, t in zip(result.letters, result.slot_tmus)],
    )


def _to_level_rows(rows: list[LevelRowIn]) -> list[level_engine.LevelRow]:
    return [level_engine.LevelRow(**r.model_dump()) for r in rows]


@router.post("/level/validate", response_model=LevelValidateResponse)
def validate_level(rows: list[LevelRowIn], _: CurrentUser = Depends(current_user)) -> LevelValidateResponse:
    issues = level_engine.validate(_to_level_rows(rows))
    return LevelValidateResponse(
        valid=not issues,
        issues=[{"code": i.code, "row_index": i.row_index, "message": i.message} for i in issues],
    )


@router.post("/level/build-output", response_model=LevelOutputResponse)
def build_level_output(rows: list[LevelRowIn], _: CurrentUser = Depends(current_user)) -> LevelOutputResponse:
    level_rows = _to_level_rows(rows)
    issues = level_engine.validate(level_rows)
    if issues:
        raise HTTPException(
            status_code=422,
            detail={"message": "Level 驗證未通過，無法輸出", "issues": [{"code": i.code, "row_index": i.row_index, "message": i.message} for i in issues]},
        )
    return LevelOutputResponse(**level_engine.build_output(level_rows))
