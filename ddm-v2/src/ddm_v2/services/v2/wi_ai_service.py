"""WI AI Parser orchestrator（L0–L2：plan → link → compile → engine gate）。

Spec §10；drafts 由 most_compiler + engine 產生，禁止在本層算 TMU。
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
import uuid
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.ai_ops import AiDeploymentBundle, AiParseRun
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.models.v2.worksheet import MostWorksheet
from ddm_v2.most_compiler.compile import allow_lists_from_rule_set, compile_plan
from ddm_v2.most_compiler.engine_gate import apply_engine_gate
from ddm_v2.most_engine import load_rule_set_from_db
from ddm_v2.most_engine.providers import load_options_from_db
from ddm_v2.nlp.contracts import (
    CycleDraft,
    ParseContext,
    ParseRunResult,
    PlannerOutput,
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.linking import SlotLinker
from ddm_v2.nlp.llm_client import OpenAICompatClient
from ddm_v2.nlp.llm_planner import LLMPlannerAdapter
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS, normalize_with_map
from ddm_v2.nlp.planner_ports import LLMRawResponse, PlannerError
from ddm_v2.nlp.prompts import plan_v1
from ddm_v2.nlp.routing import compute_routing
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import (
    legacy_from_parse_run,
    legacy_from_run_snapshot,
    plan_from_rule_result,
)
from ddm_v2.services.v2 import synonym_service as syn_svc
from ddm_v2.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_BUNDLE_CODE = "wi-ai-dev-000"

# 同步 CPU 段（normalize_with_map／RuleBasedParser.parse）的逾時上限。
# 為什麼是 10s：長度上限（MAX_PARSE_TEXT_CHARS=2000）已把病理最壞情況鎖在
# 本機實測 ≈2–3s；10s ≈ 3 倍餘裕（涵蓋較慢的部署 CPU），同時把「守衛被繞過」
# 的殘餘風險從分鐘級壓到秒級。逾時丟 TimeoutError → tick_job 的 item 級
# retry/failed 路徑接手。注意：wait_for 只中斷 await 端，executor 執行緒會跑完
# 才回收——這是刻意取捨：loop 保持回應優先，殘餘執行緒有 attempt 上限封頂。
PARSE_CPU_TIMEOUT_S = 10.0


class TextTooLong(ValueError):
    """解析輸入超過 MAX_PARSE_TEXT_CHARS（呼叫端應標 review，不應重試）。"""

    def __init__(self, length: int) -> None:
        self.length = length
        super().__init__(
            f"parse text too long: {length} chars > {MAX_PARSE_TEXT_CHARS} limit"
        )


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
    llm = run.llm_raw_response if isinstance(run.llm_raw_response, dict) else {}
    planner = "rule_based_v1" if run.fallback or not llm else "llm"
    provenance = {
        "deployment_bundle_code": bundle_code,
        "planner": planner,
        "model": llm.get("model"),
        "prompt_version": None if run.fallback else plan_v1.PROMPT_VERSION,
        "fallback": bool(run.fallback),
        "cached": cached,
        "latency_ms": run.latency or {},
        "response_format_mode": llm.get("response_format_mode"),
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
        source_revision=int(run.source_revision) if run.source_revision is not None else None,
    )


def _plan_from_planner_output(
    *,
    raw_text: str,
    normalized_text: str,
    source_ref: SourceRef,
    output: PlannerOutput,
) -> WorkInstructionPlan:
    return WorkInstructionPlan(
        source_text=raw_text,
        normalized_text=normalized_text,
        language=output.language,
        source_ref=source_ref,
        actions=output.actions,
        dependencies=output.dependencies,
        unresolved=list(output.unresolved),
    )


def _build_llm_client() -> OpenAICompatClient:
    s = get_settings()
    return OpenAICompatClient(
        base_url=s.llm_base_url,
        model=s.llm_model,
        api_key=s.llm_api_key,
        response_format_mode="json_object",
    )


async def _try_llm_plan(
    *,
    normalized_text: str,
    context: ParseContext,
    timeout_s: float,
) -> tuple[PlannerOutput, LLMRawResponse]:
    planner = LLMPlannerAdapter(_build_llm_client(), timeout_s=timeout_s)
    return await planner.plan(normalized_text, context)


def _option_labels(opts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    def _lmap(rows_: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            o["code"]: {
                "label": o.get("label"),
                "sentence": o.get("sentence"),
                "display_rule": o.get("display_rule"),
            }
            for o in rows_
        }

    return {
        "g": _lmap(opts.get("g") or []),
        "p_base": _lmap(opts.get("p_bases") or []),
        "p_addon": _lmap(opts.get("p_addons") or []),
        "m_verb": _lmap(opts.get("m_verbs") or []),
        "x": _lmap(opts.get("x") or []),
        "i": _lmap(opts.get("i") or []),
    }


async def parse_interactive(
    session: AsyncSession,
    *,
    text: str,
    rule_set_code: str,
    created_by: str,
    context: ParseContext | None = None,
    worksheet_id: UUID | None = None,
    bundle_code: str | None = None,
    source_kind: str = "interactive",
    import_id: UUID | None = None,
    import_row_index: int | None = None,
) -> tuple[ParseRunResult, dict]:
    """回傳 (ParseRunResult, legacy_nl_draft_dict)。

    ``source_kind='import_row'`` 時寫入 import_id／import_row_index（L4）。
    """
    if source_kind not in {"interactive", "import_row"}:
        raise ValueError(f"invalid source_kind: {source_kind}")
    # 長度守衛（防毒 job 卡死 event loop 的第一層）：normalize_with_map 的
    # SequenceMatcher 最壞 O(n·m)，超長輸入不進 parser。批次路徑（tick_job）
    # 在呼叫前就標 review，不會走到這裡；此處是所有呼叫端的最後防線。
    if len(text) > MAX_PARSE_TEXT_CHARS:
        raise TextTooLong(len(text))
    t0 = time.perf_counter()
    resolved_bundle = _resolve_bundle_code(bundle_code)
    ctx = context or ParseContext(rule_set_code=rule_set_code)
    if ctx.rule_set_code != rule_set_code:
        ctx = ctx.model_copy(update={"rule_set_code": rule_set_code})

    # CPU 段移出 event loop（第二層）：SequenceMatcher 是純 Python 同步碼，直接
    # 呼叫會卡住 loop，asyncio.wait_for 對「同步阻塞」根本沒有中斷點——必須先丟
    # executor 讓 loop 保持回應，timeout 才有作用點。executor 內是純函數，不碰
    # AsyncSession。
    loop = asyncio.get_running_loop()
    norm, _offset_map = await asyncio.wait_for(
        loop.run_in_executor(None, normalize_with_map, text),
        timeout=PARSE_CPU_TIMEOUT_S,
    )
    t_norm = time.perf_counter()

    rs = await _get_rule_set(session, rule_set_code)
    bundle = await _get_active_bundle(session, code=resolved_bundle)

    source_revision: int | None = None
    worksheet_key = ""
    if worksheet_id is not None:
        ws_for_rev = await session.get(MostWorksheet, worksheet_id)
        if ws_for_rev is not None:
            source_revision = int(ws_for_rev.revision_no)
            # 納入 hash：revision 變了必須重新 parse（否則「重新解析」仍命中舊 source_revision）
            worksheet_key = f"{worksheet_id}:{source_revision}"
        else:
            worksheet_key = str(worksheet_id)

    context_snapshot = ctx.model_dump()
    context_hash = _sha256(_canonical_json(context_snapshot))
    # D3：hash 使用 bundle.code（穩定字串）而非 UUID；與 settings/bundle seed 對齊。
    input_hash = _sha256(
        "|".join([norm, context_hash, bundle.code, rule_set_code, source_kind, worksheet_key])
    )

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
    # rule parser 同樣是同步 CPU 段（normalize + lexicon 全文最長匹配）→ executor。
    rule_result = await asyncio.wait_for(
        loop.run_in_executor(
            None, functools.partial(parser.parse, text, rule_set_code=rule_set_code)
        ),
        timeout=PARSE_CPU_TIMEOUT_S,
    )

    source_ref = SourceRef(
        kind="import_row" if source_kind == "import_row" else "interactive",
        worksheet_id=str(worksheet_id) if worksheet_id else None,
        import_id=str(import_id) if import_id else None,
        import_row_index=import_row_index,
    )
    rule_plan, rule_candidates = plan_from_rule_result(rule_result, source_ref=source_ref)

    settings = get_settings()
    llm_raw: LLMRawResponse | None = None
    used_fallback = True
    planner_name = "rule_based_v1"
    prompt_version: str | None = None
    model_name: str | None = None
    plan = rule_plan
    routing_extra: list[str] = []

    if settings.wi_ai_enabled:
        try:
            planner_out, llm_raw = await _try_llm_plan(
                normalized_text=norm,
                context=ctx,
                timeout_s=settings.llm_timeout_s,
            )
            plan = _plan_from_planner_output(
                raw_text=text,
                normalized_text=norm,
                source_ref=source_ref,
                output=planner_out,
            )
            used_fallback = False
            planner_name = "llm"
            prompt_version = plan_v1.PROMPT_VERSION
            model_name = llm_raw.model
            if len(plan.actions) != len(rule_plan.actions) or (
                plan.actions
                and rule_plan.actions
                and plan.actions[0].action_type != rule_plan.actions[0].action_type
            ):
                routing_extra.append("baseline_disagreement")
        except (
            PlannerError,
            httpx.HTTPError,
            httpx.TimeoutException,
            OSError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            logger.warning("LLM planner failed; falling back to rule_based: %s", exc)
            used_fallback = True
            routing_extra.append("fallback_rule_based")
            plan = rule_plan
            if isinstance(exc, PlannerError) and exc.raw is not None:
                llm_raw = exc.raw
    else:
        routing_extra.append("fallback_rule_based")

    t_plan = time.perf_counter()

    # L2：linking（rule fallback 可沿用 rule_candidates；LLM plan 一律重 link）
    linker = SlotLinker(synonyms)
    if used_fallback and rule_candidates:
        # rule plan 無 roles：仍跑 linker 補齊；與 rule slots merge（linker 優先）
        linked = await linker.link(plan, session=session, rule_set_id=rs.id)
        if linked:
            candidates = linked
        else:
            candidates = rule_candidates
    else:
        candidates = await linker.link(plan, session=session, rule_set_id=rs.id)

    t_link = time.perf_counter()

    rsdata = await load_rule_set_from_db(session, rule_set_code)
    rsdata.validate_complete()
    allow = allow_lists_from_rule_set(rsdata)
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code=rule_set_code,
        allow_lists=allow,
    )
    t_compile = time.perf_counter()

    opts = await load_options_from_db(session, rule_set_code)
    drafts = apply_engine_gate(drafts, rsdata, labels=_option_labels(opts))
    t_engine = time.perf_counter()

    routing_status, routing_reasons = compute_routing(
        plan,
        candidates,
        drafts,
        extra_reasons=routing_extra,
        auto_enabled=settings.wi_ai_auto_enabled,
    )

    latency = {
        "normalize": round((t_norm - t0) * 1000, 2),
        "plan": round((t_plan - t_norm) * 1000, 2),
        "link": round((t_link - t_plan) * 1000, 2),
        "compile": round((t_compile - t_link) * 1000, 2),
        "engine": round((t_engine - t_compile) * 1000, 2),
    }
    if llm_raw is not None:
        latency["llm"] = llm_raw.latency_ms

    run_id = uuid.uuid4()
    run = AiParseRun(
        id=run_id,
        source_kind=source_kind,
        worksheet_id=worksheet_id,
        import_id=import_id,
        import_row_index=import_row_index,
        raw_text=text,
        normalized_text=norm,
        input_hash=input_hash,
        context_snapshot=context_snapshot,
        context_hash=context_hash,
        rule_set_id=rs.id,
        bundle_id=bundle.id,
        plan=plan.model_dump(),
        slot_candidates=[c.model_dump() for c in candidates],
        drafts=[d.model_dump() for d in drafts],
        llm_raw_response=(
            {
                "content": llm_raw.content,
                "model": llm_raw.model,
                "usage": llm_raw.usage,
                "response_format_mode": llm_raw.response_format_mode,
            }
            if llm_raw is not None
            else None
        ),
        routing_status=routing_status,
        routing_reasons=routing_reasons,
        fallback=used_fallback,
        cached=False,
        latency=latency,
        error=None,
        created_by=created_by,
        source_revision=source_revision,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
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
        drafts=drafts,
        routing_status=routing_status,  # type: ignore[arg-type]
        routing_reasons=routing_reasons,
        provenance={
            "deployment_bundle_code": bundle.code,
            "planner": planner_name,
            "model": model_name,
            "prompt_version": prompt_version,
            "fallback": used_fallback,
            "cached": False,
            "latency_ms": latency,
            "response_format_mode": (
                llm_raw.response_format_mode if llm_raw is not None else None
            ),
        },
    )
    # 相容：仍回 rule_based 的 GM-shaped slots（舊前端）；ai.drafts 是權威草稿
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
