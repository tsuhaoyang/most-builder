"""NL draft 解析 API（impl-05 → WI AI L0 加法演進）。

POST /api/v2/worksheets/nl-draft
  body: {"text": str, "rule_set_code": str, "context"?, "worksheet_id"?}
  → 舊 NLDraftResult 欄位 + ai（ParseRunResult 形） + multi_action_warning

唯讀於 worksheet；寫入 ai_parse_runs（AI 專用表）。建議結果需 IE 確認才寫入 slot_inputs。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.nlp.contracts import ParseContext
from ddm_v2.services.v2 import synonym_service as syn_svc
from ddm_v2.services.v2 import wi_ai_service

router = APIRouter(prefix="/api/v2", tags=["v2-nl-draft"])


class NLDraftContextIn(BaseModel):
    station_hint: str | None = None
    available_tools: list[str] = Field(default_factory=list)
    available_locations: list[str] = Field(default_factory=list)
    previous_row_summary: str | None = None


class NLDraftIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    rule_set_code: str = Field(..., min_length=1)
    context: NLDraftContextIn | None = None
    worksheet_id: UUID | None = None


@router.post("/worksheets/nl-draft")
async def nl_draft(
    payload: NLDraftIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(current_user),
) -> dict:
    """解析自然語言描述，回傳 MOST slot 建議（唯讀於 worksheet）＋ AI plan run。"""
    ctx = None
    if payload.context is not None:
        ctx = ParseContext(
            rule_set_code=payload.rule_set_code,
            station_hint=payload.context.station_hint,
            available_tools=payload.context.available_tools,
            available_locations=payload.context.available_locations,
            previous_row_summary=payload.context.previous_row_summary,
        )

    try:
        result, legacy = await wi_ai_service.parse_interactive(
            session,
            text=payload.text,
            rule_set_code=payload.rule_set_code,
            created_by=user.employee_no,
            context=ctx,
            worksheet_id=payload.worksheet_id,
        )
    except syn_svc.RuleSetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"rule-set 不存在：{payload.rule_set_code}",
        ) from None
    except RuntimeError as exc:
        # bundle 未 seed 等設定錯誤
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    multi_action = len(result.plan.actions) > 1
    body = {
        **legacy,
        "ai": {
            "run_id": result.run_id,
            "plan": result.plan.model_dump(),
            "slot_candidates": [c.model_dump() for c in result.slot_candidates],
            "drafts": [d.model_dump() for d in result.drafts],
            "routing_status": result.routing_status,
            "routing_reasons": result.routing_reasons,
            "provenance": result.provenance,
        },
        "multi_action_warning": multi_action,
    }
    return body
