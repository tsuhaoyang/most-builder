"""同義詞維護 API（impl-05）。

GET    /api/v2/rule-sets/{code}/synonyms          → list（viewer+）
POST   /api/v2/rule-sets/{code}/synonyms          → 201 created（analyst+）
DELETE /api/v2/rule-sets/{code}/synonyms/{syn_id} → 204（analyst+）

409 衝突回應：
- 同 (parameter, synonym_norm, option_code) 重複（v2_0038 UNIQUE）：
  {"detail": {"code": "SYNONYM_CONFLICT", "existing": {...}}}
- 同面其他 code 撞同一 priority（D3-018 H1）：
  {"detail": {"code": "SYNONYM_PRIORITY_COLLISION", "message": ..., "existing": {...}}}
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.auth.deps import CurrentUser, current_user, require_role
from ddm_v2.database import get_db_session
from ddm_v2.errors.registry import ErrorCode
from ddm_v2.exceptions import ConflictError, NotFoundError, ValidationError
from ddm_v2.services.v2 import synonym_service as svc

router = APIRouter(prefix="/api/v2", tags=["v2-synonyms"])


class SynonymIn(BaseModel):
    parameter: str = Field(..., pattern=r"^(A|B|G|P|M|X|I|vocab)$")
    option_code: str
    synonym_raw: str = Field(..., min_length=1, max_length=200)
    priority: int = 0


@router.get("/rule-sets/{code}/synonyms")
async def list_synonyms(
    code: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(current_user),
) -> list[dict]:
    try:
        return await svc.list_synonyms(session, code)
    except svc.RuleSetNotFound:
        msg = f"rule-set 不存在：{code}"
        raise NotFoundError(
            msg,
            detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": code},
        ) from None


@router.post("/rule-sets/{code}/synonyms", status_code=201)
async def create_synonym(
    code: str,
    payload: SynonymIn,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    user: CurrentUser = Depends(require_role("analyst")),
) -> dict:
    try:
        return await svc.create_synonym(
            session,
            code,
            data=payload.model_dump(),
            created_by=user.employee_no,
        )
    except svc.RuleSetNotFound:
        msg = f"rule-set 不存在：{code}"
        raise NotFoundError(
            msg,
            detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": code},
        ) from None
    except svc.RuleSetRetired:
        compat = {"code": "RULE_SET_RETIRED", "message": f"rule-set {code} 已下架（終態），不可增刪同義詞"}
        raise ConflictError(
            compat["message"],
            detail={**compat},
        ) from None
    except svc.OptionCodeNotFound as e:
        compat = {"code": "OPTION_CODE_NOT_FOUND", "parameter": e.parameter, "option_code": e.option_code}
        raise ValidationError(
            f"option_code 不存在：{e.option_code}",
            detail={**compat},
        ) from None
    except ValueError as e:
        compat = {"code": "VALIDATION_ERROR", "message": str(e)}
        raise ValidationError(
            str(e),
            detail={**compat},
        ) from e
    except svc.SynonymConflict as e:
        compat = {"code": "SYNONYM_CONFLICT", "existing": e.existing}
        raise ConflictError(
            "同義詞已存在",
            detail={**compat},
        ) from None
    except svc.SynonymPriorityCollision as e:
        compat = {
            "code": "SYNONYM_PRIORITY_COLLISION",
            "message": (
                f"「{payload.synonym_raw}」在參數 {payload.parameter} 已映射到 "
                f"{e.existing.get('option_code')}（priority {e.priority}）——"
                "一面多 code 需以不同 priority 顯式宣告偏好序"
                "（數字小者優先，0＝預設）"
            ),
            "existing": e.existing,
        }
        raise ConflictError(
            compat["message"],
            detail={**compat},
        ) from None


@router.delete("/rule-sets/{code}/synonyms/{syn_id}", status_code=204)
async def delete_synonym(
    code: str,
    syn_id: str,
    session: AsyncSession = Depends(get_db_session, scope="function"),
    _: CurrentUser = Depends(require_role("analyst")),
) -> Response:
    try:
        await svc.delete_synonym(session, syn_id, code)
    except svc.RuleSetNotFound:
        msg = f"rule-set 不存在：{code}"
        raise NotFoundError(
            msg,
            detail={"code": ErrorCode.NOT_FOUND, "resource": "rule_set", "rule_set_code": code},
        ) from None
    except svc.RuleSetRetired:
        compat = {"code": "RULE_SET_RETIRED", "message": f"rule-set {code} 已下架（終態），不可增刪同義詞"}
        raise ConflictError(
            compat["message"],
            detail={**compat},
        ) from None
    except svc.SynonymNotFound:
        msg = f"同義詞不存在：{syn_id}"
        raise NotFoundError(
            msg,
            detail={"code": ErrorCode.NOT_FOUND, "resource": "synonym", "synonym_id": syn_id},
        ) from None
    return Response(status_code=204)
