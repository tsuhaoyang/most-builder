"""NL draft 解析 API（impl-05）。

POST /api/v2/worksheets/nl-draft
  body: {"text": str, "rule_set_code": str}
  → NLDraftResult JSON

唯讀；無副作用；建議結果需 IE 在 UI 確認才寫入 slot_inputs（引擎重算）。
"""
from __future__ import annotations

import dataclasses

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user
from ddm_v2.database import get_db_session
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.services.v2 import synonym_service as syn_svc

router = APIRouter(prefix="/api/v2", tags=["v2-nl-draft"])


class NLDraftIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    rule_set_code: str = Field(..., min_length=1)


def _dataclass_to_dict(obj: object) -> object:
    """遞迴將 frozen dataclass 轉換為可 JSON 序列化的 dict。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(i) for i in obj]
    return obj


@router.post("/worksheets/nl-draft")
async def nl_draft(
    payload: NLDraftIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> dict:
    """解析自然語言描述，回傳 MOST slot 建議（唯讀）。"""
    # 1. 驗證 rule_set 存在（404 若不存在）
    try:
        synonyms = await syn_svc.list_synonyms(session, payload.rule_set_code)
    except syn_svc.RuleSetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"rule-set 不存在：{payload.rule_set_code}",
        )

    # 2. 建立 parser 並執行解析
    parser = RuleBasedParser(synonyms)
    result = parser.parse(payload.text, rule_set_code=payload.rule_set_code)

    # 3. 回傳（dataclass → dict）
    return _dataclass_to_dict(result)
