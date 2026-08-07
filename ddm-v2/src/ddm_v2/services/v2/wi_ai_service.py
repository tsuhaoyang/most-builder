"""WI AI Parser orchestrator（L0：rule 路徑 + run 落庫 + 冪等）。

Spec §10；L0 不做 linking/compiler/engine（drafts=[]）。
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.ai_ops import AiDeploymentBundle, AiParseRun
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.nlp.contracts import (
    CycleDraft,
    ParseContext,
    ParseRunResult,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.normalization import normalize_with_map
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import (
    legacy_from_parse_run,
    legacy_from_run_snapshot,
    plan_from_rule_result,
)
from ddm_v2.services.v2 import synonym_service as syn_svc
from ddm_v2.settings import get_settings

DEFAULT_BUNDLE_CODE = "wi-ai-dev-000"


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _resolve_bundle_code(bundle_code: str | None) -> str:
    if bundle_code:
        return bundle_code
    return get_settings().wi_ai_bundle_code or DEFAULT_BUNDLE_CODE


async def _get_active_bundle(
    session: AsyncSession, *, code: str = DEFAULT_BUNDLE_CODE
) -> AiDeploymentBundle:
    q = await session.execute(
        select(AiDeploymentBundle).where(
            AiDeploymentBundle.code == code,
            AiDeploymentBundle.status == "active",
        )
    )
    bundle = q.scalar_one_or_none()
    if bundle is None:
        raise RuntimeError(f"ai deployment bundle missing or inactive: {code}")
    return bundle


async def _get_rule_set(session: AsyncSession, code: str) -> RuleSet:
    q = await session.execute(select(RuleSet).where(RuleSet.code == code))
    rs = q.scalar_one_or_none()
    if rs is None:
        raise syn_svc.RuleSetNotFound(code)
    return rs


def _result_from_run(run: AiParseRun, *, cached: bool, bundle_code: str) -> ParseRunResult:
    provenance = {
        "deployment_bundle_code": bundle_code,
        "planner": "rule_based_v1",
        "model": None,
        "prompt_version": None,
        "fallback": bool(run.fallback),
        "cached": cached,
        "latency_ms": run.latency or {},
    }
    drafts = [CycleDraft.model_validate(d) for d in (run.drafts or [])]
    return ParseRunResult(
        run_id=str(run.id),
        plan=WorkInstructionPlan.model_validate(run.plan),
        slot_candidates=[SlotCandidateSet.model_validate(c) for c in (run.slot_candidates or [])],
        drafts=drafts,
        routing_status=run.routing_status,  # type: ignore[arg-type]
        routing_reasons=list(run.routing_reasons or []),
        provenance=provenance,
    )


def _compute_routing(plan: WorkInstructionPlan) -> tuple[str, list[str]]:
    """§10.3 L0：全 composite_unknown → abstain；其餘 review（auto 硬關閉）。"""
    reasons = ["fallback_rule_based"]
    if plan.unresolved:
        reasons.extend(plan.unresolved)
    if not plan.actions or all(a.action_type == "composite_unknown" for a in plan.actions):
        if "composite_unknown" not in reasons:
            reasons.append("composite_unknown")
        return "abstain", reasons
    return "review", reasons


async def parse_interactive(
    session: AsyncSession,
    *,
    text: str,
    rule_set_code: str,
    created_by: str,
    context: ParseContext | None = None,
    worksheet_id: UUID | None = None,
    bundle_code: str | None = None,
) -> tuple[ParseRunResult, dict]:
    """回傳 (ParseRunResult, legacy_nl_draft_dict)。"""
    t0 = time.perf_counter()
    resolved_bundle = _resolve_bundle_code(bundle_code)
    ctx = context or ParseContext(rule_set_code=rule_set_code)
    if ctx.rule_set_code != rule_set_code:
        ctx = ctx.model_copy(update={"rule_set_code": rule_set_code})

    norm, _offset_map = normalize_with_map(text)
    t_norm = time.perf_counter()

    rs = await _get_rule_set(session, rule_set_code)
    bundle = await _get_active_bundle(session, code=resolved_bundle)

    context_snapshot = ctx.model_dump()
    context_hash = _sha256(_canonical_json(context_snapshot))
    # D3：hash 使用 bundle.code（穩定字串）而非 UUID；與 settings/bundle seed 對齊。
    input_hash = _sha256("|".join([norm, context_hash, bundle.code, rule_set_code]))

    existing = await _find_cached_run(session, input_hash=input_hash, bundle_id=bundle.id)
    if existing is not None:
        result = _result_from_run(existing, cached=True, bundle_code=bundle.code)
        legacy = legacy_from_run_snapshot(
            raw_text=text,
            result=result,
            provenance_extra={"cached_run_id": result.run_id},
        )
        return result, legacy

    synonyms = await syn_svc.list_synonyms(session, rule_set_code)
    parser = RuleBasedParser(synonyms)
    rule_result = parser.parse(text, rule_set_code=rule_set_code)
    t_plan = time.perf_counter()

    source_ref = SourceRef(
        kind="interactive",
        worksheet_id=str(worksheet_id) if worksheet_id else None,
        import_id=None,
        import_row_index=None,
    )
    plan, candidates = plan_from_rule_result(rule_result, source_ref=source_ref)
    routing_status, routing_reasons = _compute_routing(plan)

    latency = {
        "normalize": round((t_norm - t0) * 1000, 2),
        "plan": round((t_plan - t_norm) * 1000, 2),
        "link": 0.0,
        "compile": 0.0,
        "engine": 0.0,
    }

    run_id = uuid.uuid4()
    run = AiParseRun(
        id=run_id,
        source_kind="interactive",
        worksheet_id=worksheet_id,
        import_id=None,
        import_row_index=None,
        raw_text=text,
        normalized_text=norm,
        input_hash=input_hash,
        context_snapshot=context_snapshot,
        context_hash=context_hash,
        rule_set_id=rs.id,
        bundle_id=bundle.id,
        plan=plan.model_dump(),
        slot_candidates=[c.model_dump() for c in candidates],
        drafts=[],
        llm_raw_response=None,
        routing_status=routing_status,
        routing_reasons=routing_reasons,
        fallback=True,  # L0 全程 rule；L1 起僅 LLM 失敗時為 true
        cached=False,
        latency=latency,
        error=None,
        created_by=created_by,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        # 競態：另一請求已插入同一 (input_hash, bundle_id)
        raced = await _find_cached_run(session, input_hash=input_hash, bundle_id=bundle.id)
        if raced is None:
            raise
        result = _result_from_run(raced, cached=True, bundle_code=bundle.code)
        legacy = legacy_from_run_snapshot(
            raw_text=text,
            result=result,
            provenance_extra={"cached_run_id": result.run_id, "raced": True},
        )
        return result, legacy

    result = ParseRunResult(
        run_id=str(run_id),
        plan=plan,
        slot_candidates=candidates,
        drafts=[],
        routing_status=routing_status,  # type: ignore[arg-type]
        routing_reasons=routing_reasons,
        provenance={
            "deployment_bundle_code": bundle.code,
            "planner": "rule_based_v1",
            "model": None,
            "prompt_version": None,
            "fallback": True,
            "cached": False,
            "latency_ms": latency,
        },
    )
    legacy = legacy_from_parse_run(
        raw_text=rule_result.raw_text,
        normalized_text=rule_result.normalized_text,
        slots=rule_result.slots,
        suggested_seq=rule_result.suggested_seq,
        overall_confidence=rule_result.overall_confidence,
        provenance=rule_result.provenance,
    )
    return result, legacy


async def _find_cached_run(
    session: AsyncSession, *, input_hash: str, bundle_id: UUID
) -> AiParseRun | None:
    cached_q = await session.execute(
        select(AiParseRun)
        .where(
            AiParseRun.input_hash == input_hash,
            AiParseRun.bundle_id == bundle_id,
        )
        .order_by(AiParseRun.created_at.desc())
        .limit(1)
    )
    return cached_q.scalar_one_or_none()
