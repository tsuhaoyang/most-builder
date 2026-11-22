"""WI AI Parser orchestrator（L0–L2：plan → link → compile → engine gate）。

Spec §10；drafts 由 most_compiler + engine 產生，禁止在本層算 TMU。

ADR-037（2026-11-14）：MOST 內的 LLM planner 已移除，plan 預設來自 rule_based。
外部 ai_service 經 `WiParserPort` 接入（實作計畫 S3）：呼叫端傳 `external=ExternalAi(...)` 才走外部路徑，
沒傳就與先前完全相同；外部失敗一律降級回 rule_based。既有 `ai_parse_runs` 中 planner＝llm 的舊列
仍由 `_result_from_run` 照原樣讀取與重播。

⚠️ 本檔不得訂閱入站防腐層的 sanitize observer（`nlp/inbound_guard` 的 Sanitize ＋ Observer 型別）：
它帶的是被剝除的外部原文值，只給評測腳本。守衛：
`tests/unit/test_production_no_sanitize_observer.py`（零容忍字面掃描，註解也算命中，
所以本檔不寫出那個參數名）。
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.ai_integration.plan_adapter import build_plan_from_motions, preview_drafts
from ddm_v2.ai_integration.ports import Hand, WiParseRequest, WiParserPort
from ddm_v2.ai_integration.provenance import sanitize_ai_service_provenance, validate_provenance
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
    SlotCandidateSet,
    SourceRef,
    WorkInstructionPlan,
)
from ddm_v2.nlp.linking import SlotLinker
from ddm_v2.nlp.normalization import MAX_PARSE_TEXT_CHARS, normalize_with_map
from ddm_v2.nlp.routing import compute_routing
from ddm_v2.nlp.rule_based import RuleBasedParser
from ddm_v2.nlp.rule_plan_adapter import (
    LEGACY_SLOTS_PARSER,
    detect_language,
    legacy_from_parse_run,
    legacy_from_run_snapshot,
    legacy_provenance,
    plan_from_rule_result,
)
from ddm_v2.services.v2 import synonym_service as syn_svc
from ddm_v2.settings import get_settings

logger = logging.getLogger(__name__)

DEFAULT_BUNDLE_CODE = "wi-ai-dev-000"
# v2_0050 的佔位 bundle：所有外部 ai_service 的 run 都指向它；實際的 ai_service bundle 代碼記在 provenance
EXTERNAL_BUNDLE_CODE = "external-ai-service"


@dataclass(frozen=True)
class ExternalAi:
    """單句外部 AI 路徑的呼叫參數（ADR-037 D2／D8）。呼叫端（路由）依開關與角色決定要不要傳。

    `service_bundle_code` 是**部署設定**的 ai_service bundle（`DDM_AI_SERVICE_BUNDLE_CODE`；不是 MOST 的佔位
    bundle）：呼叫前就已知，所以能納入 `input_hash`——快取命中時不呼叫 ai_service、不扣額度；換 bundle
    （換 prompt）自然 miss。呼叫後會比對回應的 `bundle_code` 與它是否一致，不一致就降級。
    `known_hand` 也納入 `input_hash`：它決定 `ai_hand_hint_mismatch`，不同手別的請求不該共用同一份旗標。
    `actor`／`scope` 只給 MOST 端的配額與合併用，絕不外送。`known_hand` 是 MOST 已知的手別
    （Excel 欄或使用者輸入），給了才比對 ai_service 的手別提示。
    """

    port: WiParserPort
    service_bundle_code: str
    actor: str
    scope: str
    known_hand: Hand | None = None

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
            # v2_0050 的佔位 bundle（kind=external）只給外部 ai_service 的落盤用，
            # 不是 rule_based／llm 路徑可選的 bundle（否則 analyst 傳 bundle_code 就能選到）
            AiDeploymentBundle.kind != "external",
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


def _external_response_provenance(prov: dict[str, Any], *, cached: bool, latency: dict[str, Any]) -> dict[str, Any]:
    """外部 run 的回應 provenance。新寫入與重播共用這一支，兩邊不會漂移。"""
    return {
        "deployment_bundle_code": prov.get("bundle_code"),
        "planner": "ai_service",
        "model": prov.get("model_served"),
        "prompt_version": prov.get("prompt_version"),
        "fallback": False,
        "cached": cached,
        "latency_ms": latency,
        "response_format_mode": None,
        "ai_run_id": prov.get("run_id"),
        "motion_labels": list(prov.get("motion_labels") or []),
        "dropped": list(prov.get("dropped") or []),
    }


def _result_from_run(run: AiParseRun, *, cached: bool, bundle_code: str) -> ParseRunResult:
    if bundle_code == EXTERNAL_BUNDLE_CODE:
        # 外部 ai_service 的 run：出處讀 `run.provenance`（寫入時已過 allow-list），不看 `llm_raw_response`
        provenance = _external_response_provenance(
            run.provenance if isinstance(run.provenance, dict) else {},
            cached=cached,
            latency=run.latency or {},
        )
        return ParseRunResult(
            run_id=str(run.id),
            plan=WorkInstructionPlan.model_validate(run.plan),
            slot_candidates=[SlotCandidateSet.model_validate(c) for c in (run.slot_candidates or [])],
            drafts=[CycleDraft.model_validate(d) for d in (run.drafts or [])],
            routing_status=run.routing_status,  # type: ignore[arg-type]
            routing_reasons=list(run.routing_reasons or []),
            provenance=provenance,
            source_revision=int(run.source_revision) if run.source_revision is not None else None,
        )
    llm = run.llm_raw_response if isinstance(run.llm_raw_response, dict) else {}
    planner = "rule_based_v1" if run.fallback or not llm else "llm"
    provenance = {
        "deployment_bundle_code": bundle_code,
        "planner": planner,
        "model": llm.get("model"),
        # 讀當初那一趟寫下的版本，**不是**當下的模組常數：`ai_parse_runs` 沒有
        # prompt_version 欄（有那欄的是 `ai_deployment_bundles`），所以它跟 model／
        # usage 一樣存在 `llm_raw_response` 裡。常數升版（如 plan-v1 → plan-v1.3）時，
        # 讀常數會讓 DB 裡每一筆既有 run 都謊報成新版本。
        # 舊資料列沒有這個鍵 → None。誠實的「不知道」勝過自信的錯答，不得回退成常數。
        "prompt_version": llm.get("prompt_version"),
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


def _option_labels(opts: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """AI 落地路徑專用的**純中文** label map。

    ⚠️ **不得改用 `most_engine/providers.py` 裡那支共用的 label-map builder**
    （確切名稱見 `tests/unit/test_i18n_en_field_isolation.py` 的 `FORBIDDEN_EN_CARRIERS`；
    本檔刻意不寫出那些字面，因為該守衛是零容忍的字面 grep，連註解也算命中）。
    ADR-032 I3「違反即否決」。看起來這是可以 DRY 掉的重複，但這份重複是**刻意的**：

        wi_ai_service（本函式） → most_compiler/engine_gate.py → compute_cycle
                                                                 ↑ 決定 TMU 的路徑

    那支共用 builder 會把英文欄（`*_en` 系列）帶進 labels dict，等於讓未經覆核的機器翻譯
    進入決定 TMU 的路徑——正是 I3 禁止的事。今天 `engine_gate` 只拿 labels 餵中文
    `build_narrative()`（`compute_cycle` 吃的是 `RuleSetData`），實際風險為零；但
    「現在沒被消費」離「被消費」只有一個提交，I3 守的就是這段距離。

    2026-08-19 已有人（做 DRY 清理時）真的這樣改過一次，**全測試綠**才被人工複審抓到——
    因此上述守衛已擴大到掃本檔與 `most_compiler/`，並新增「載體符號」維度
    （純欄位名 grep 看不穿函式邊界）。要改這裡之前，先讀那支測試的檔頭。

    `pricing_kind` 是 rule-set 的結構欄（不是英文欄、不參與 TMU）：敘事層靠它認出
    M 的手度／腳步是伴隨維度而不入句（ADR-032 D7.6），中英兩套樣板同一個判準。

    **本函式的職責就是「投影掉英文欄」**：傳進來的 `opts`（選項載入器的回傳值）本來就
    含英文欄，那是給前端下拉用的，正常且必要。安全的理由不在來源乾淨，而在下面 `_lmap()`
    是**逐鍵白名單**——只挑 `label`／`sentence`／`display_rule`／`pricing_kind` 四個鍵，
    新增欄位預設不會被帶下去。改成 `**o` 或任何「除了某某以外全帶」的寫法即違反 I3。
    （下游 `apply_engine_gate` 另有執行期不變式會擋，但那是安全網，不是本函式免責的理由。）
    """
    def _lmap(rows_: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            o["code"]: {
                "label": o.get("label"),
                "sentence": o.get("sentence"),
                "display_rule": o.get("display_rule"),
                "pricing_kind": o.get("pricing_kind"),
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


async def _parse_rule_based(
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
    degraded: dict[str, Any] | None = None,
    _norm: str | None = None,
) -> tuple[ParseRunResult, dict]:
    """rule_based 路徑（ADR-037 前就有的行為，未改）。

    ``source_kind='import_row'`` 時寫入 import_id／import_row_index（L4）。
    `degraded`：外部 ai_service 失敗而降級到這裡時的原因（只有 MOST 自己的分類與代碼）；
    寫進該 run 的 `error` 欄位，回應的標註由呼叫端加（快取命中的 run 不重寫）。
    `_norm`：外部路徑降級時把已算好的 normalize 結果帶進來，不重算（那是 O(n·m) 的 CPU）。
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
    if _norm is not None:
        norm = _norm
    else:
        norm, _offset_map = await asyncio.wait_for(
            loop.run_in_executor(None, normalize_with_map, text),
            timeout=PARSE_CPU_TIMEOUT_S,
        )
    t_norm = time.perf_counter()

    rs = await _get_rule_set(session, rule_set_code)
    bundle = await _get_active_bundle(session, code=resolved_bundle)

    # 納入 hash：revision 變了必須重新 parse（否則「重新解析」仍命中舊 source_revision）
    worksheet_key, source_revision = await _worksheet_key(session, worksheet_id)

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
    # ADR-037：MOST 內不再呼叫 LLM。plan 一律是 rule plan；`fallback=True` 與
    # `fallback_rule_based` 維持既有語意（＝沒有 AI planner 參與），前端與 routing 不變。
    used_fallback = True
    planner_name = "rule_based_v1"
    prompt_version: str | None = None
    model_name: str | None = None
    plan = rule_plan
    routing_extra: list[str] = ["fallback_rule_based"]

    t_plan = time.perf_counter()

    # L2：linking（rule plan 無 roles：仍跑 linker 補齊；linker 無結果時沿用 rule_candidates）
    linker = SlotLinker(synonyms)
    linked = await linker.link(plan, session=session, rule_set_id=rs.id)
    candidates = linked if linked else rule_candidates

    t_link = time.perf_counter()

    rsdata = await load_rule_set_from_db(session, rule_set_code)
    rsdata.validate_complete()
    allow = allow_lists_from_rule_set(rsdata)
    drafts = compile_plan(
        plan,
        candidates,
        rule_set_code=rule_set_code,
        allow_lists=allow,
        face_hit_params=linker.face_hit_params(plan),
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
        # 欄位保留給既有資料列（舊 LLM run 的 content／model／usage／prompt_version）；
        # 新寫入一律為 None。外部 ai_service 的回應落點在實作計畫 S3 定案。
        llm_raw_response=None,
        routing_status=routing_status,
        routing_reasons=routing_reasons,
        fallback=used_fallback,
        cached=False,
        latency=latency,
        error={"ai_service": degraded} if degraded else None,
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
            "response_format_mode": None,
        },
    )
    # 相容：仍回 rule_based 的 GM-shaped slots（舊前端）；ai.drafts 是權威草稿。
    # provenance 走 legacy_provenance()：slots 出處記在 slots_parser，parser 說的是
    # 這一趟實際跑的 planner（直接傳 rule_result.provenance 會讓 parser 永遠是
    # rule_based_v1——那個欄位曾兩度誤導實機驗證）。
    legacy = legacy_from_parse_run(
        raw_text=rule_result.raw_text,
        normalized_text=rule_result.normalized_text,
        slots=rule_result.slots,
        suggested_seq=rule_result.suggested_seq,
        overall_confidence=rule_result.overall_confidence,
        provenance=legacy_provenance(
            rule_provenance=rule_result.provenance,
            planner=planner_name,
            model=model_name,
            prompt_version=prompt_version,
            fallback=used_fallback,
            # 這條路徑的 legacy slots 就是上面 `slots=rule_result.slots` 那批，
            # 出自 RuleBasedParser，與 planner 無關（重播路徑不同，見 legacy_provenance）。
            slots_parser=LEGACY_SLOTS_PARSER,
        ),
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


# ═════════════════════════════════════════════════════════════════════
# 外部 ai_service 路徑（ADR-037；實作計畫 S3）
# ═════════════════════════════════════════════════════════════════════

_UPSTREAM_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# 這些分類是維運資訊（設定、金鑰、部署、MOST 自己的 bug）：完整代碼只留在 `run.error` 與 log，
# 回給前端的 `ai_error` 不帶 `upstream_code`（例：`host_not_allowed`、`key_too_short` 會洩漏內部設定規則）
_INTERNAL_KINDS = frozenset(
    {"misconfigured", "auth", "deployment", "request_rejected", "contract_mismatch", "internal_error", "bundle_not_runnable"}
)


@dataclass(frozen=True)
class _Degraded:
    """外部路徑降級的原因：只含 MOST 自己的分類與代碼，不含 ai_service 的文字或錯誤訊息。"""

    error_kind: str
    upstream_code: str | None = None
    norm: str | None = None  # 已算好的 normalize 結果，降級走 rule 路徑時沿用

    def __post_init__(self) -> None:
        code = self.upstream_code
        if code is not None and not _UPSTREAM_CODE_RE.fullmatch(code):
            object.__setattr__(self, "upstream_code", None)  # 不是 MOST／client 的代碼形狀：不收

    def record(self) -> dict[str, Any]:
        """寫進 `ai_parse_runs.error` 的完整版（維運用）。"""
        return {"error_kind": self.error_kind, "upstream_code": self.upstream_code}

    def public(self) -> dict[str, Any]:
        """回給前端的版本：維運類分類不帶 `upstream_code`。"""
        code = None if self.error_kind in _INTERNAL_KINDS else self.upstream_code
        return {"error_kind": self.error_kind, "upstream_code": code}


def _exc_summary(exc: BaseException) -> str:
    """log 用的例外摘要。pydantic 的 `ValidationError` 訊息會帶 input_value（可能是使用者語句），一律只記類別；
    其他例外記類別與前 200 字（guard 的 ValueError／client 的 RuntimeError 是 MOST 固定字串）。"""
    if isinstance(exc, ValidationError) or not isinstance(exc, (ValueError, RuntimeError)):
        return type(exc).__name__
    return f"{type(exc).__name__}: {str(exc)[:200]}"


async def _worksheet_key(session: AsyncSession, worksheet_id: UUID | None) -> tuple[str, int | None]:
    if worksheet_id is None:
        return "", None
    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        return str(worksheet_id), None
    revision = int(ws.revision_no)
    # 納入 hash：revision 變了必須重新 parse
    return f"{worksheet_id}:{revision}", revision


async def _get_external_bundle(session: AsyncSession) -> AiDeploymentBundle | None:
    q = await session.execute(
        select(AiDeploymentBundle).where(
            AiDeploymentBundle.code == EXTERNAL_BUNDLE_CODE,
            AiDeploymentBundle.kind == "external",
            AiDeploymentBundle.status == "active",
        )
    )
    return q.scalar_one_or_none()


def _annotate_degraded(
    result: ParseRunResult, legacy: dict, degraded: _Degraded
) -> tuple[ParseRunResult, dict]:
    """降級後的回應標註：讓前端看得到「為什麼這次沒有 AI 草稿」（維運細節只在 `run.error` 與 log）。"""
    public = degraded.public()
    result = result.model_copy(update={"provenance": {**result.provenance, "ai_error": public}})
    legacy = {**legacy, "provenance": {**(legacy.get("provenance") or {}), "ai_error": public}}
    return result, legacy


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
    external: ExternalAi | None = None,
) -> tuple[ParseRunResult, dict]:
    """回傳 (ParseRunResult, legacy_nl_draft_dict)。

    `external=None`：與先前完全相同（rule_based）。
    `external` 有值：先試外部 ai_service；任何失敗（port 回 failed、guard 的 `ValueError`／`RuntimeError`、
    結果空、plan 建不起來）都**降級**成 rule_based，回應與該 run 的 `error` 帶原因（`ai_error`），不拋給呼叫端。
    只支援單句（`source_kind='interactive'`）；批量（S5）維持 rule_based。

    ⚠️ 外部路徑會在呼叫 ai_service **之前** `session.commit()`（ADR-037 D8：呼叫期間不占用 DB 連線）。
    呼叫端在這之前不得有「失敗時需要回滾」的未提交寫入。
    """
    if external is None:
        return await _parse_rule_based(
            session,
            text=text,
            rule_set_code=rule_set_code,
            created_by=created_by,
            context=context,
            worksheet_id=worksheet_id,
            bundle_code=bundle_code,
            source_kind=source_kind,
            import_id=import_id,
            import_row_index=import_row_index,
        )
    if source_kind != "interactive":
        raise ValueError("external ai_service path supports source_kind='interactive' only")
    if len(text) > MAX_PARSE_TEXT_CHARS:
        raise TextTooLong(len(text))
    ctx = context or ParseContext(rule_set_code=rule_set_code)
    if ctx.rule_set_code != rule_set_code:
        ctx = ctx.model_copy(update={"rule_set_code": rule_set_code})

    outcome = await _parse_external(
        session,
        text=text,
        rule_set_code=rule_set_code,
        created_by=created_by,
        ctx=ctx,
        worksheet_id=worksheet_id,
        external=external,
    )
    if not isinstance(outcome, _Degraded):
        return outcome
    result, legacy = await _parse_rule_based(
        session,
        text=text,
        rule_set_code=rule_set_code,
        created_by=created_by,
        context=ctx,
        worksheet_id=worksheet_id,
        bundle_code=bundle_code,
        source_kind=source_kind,
        degraded=outcome.record(),
        _norm=outcome.norm,
    )
    return _annotate_degraded(result, legacy, outcome)


async def _parse_external(
    session: AsyncSession,
    *,
    text: str,
    rule_set_code: str,
    created_by: str,
    ctx: ParseContext,
    worksheet_id: UUID | None,
    external: ExternalAi,
) -> tuple[ParseRunResult, dict] | _Degraded:
    """成功回 (result, legacy)；降級回 `_Degraded`。`RuleSetNotFound` 等呼叫端錯誤照常往上拋。

    順序刻意如此：**讀完所有要讀的 → 結束交易 → 呼叫 ai_service → 算完所有東西 → 最後才寫 run**。
    run 的寫入是最後一個副作用，所以呼叫之後的任何失敗都不會留下「已扣額度卻半寫的 run」。
    """
    # 下面會 `session.commit()` 以釋放連線，commit 會連帶提交呼叫端未提交的寫入；呼叫端不得有「失敗時需要回滾」
    # 的東西——有就是呼叫端的 bug，在這裡擋下。必須在任何查詢**之前**檢查：SQLAlchemy 的 autoflush 會在第一個查詢時
    # 把待寫入的物件 flush 出去，之後 `session.new` 就看不到它們了。已 flush 但未提交的寫入無法偵測，靠呼叫端遵守。
    if session.new or session.dirty or session.deleted:
        raise RuntimeError("external ai path requires a session without pending writes (it commits before the call)")
    t0 = time.perf_counter()
    loop = asyncio.get_running_loop()
    norm, _offset_map = await asyncio.wait_for(
        loop.run_in_executor(None, normalize_with_map, text), timeout=PARSE_CPU_TIMEOUT_S
    )
    t_norm = time.perf_counter()

    rs = await _get_rule_set(session, rule_set_code)
    bundle = await _get_external_bundle(session)
    if bundle is None:
        logger.error("external ai bundle %r is missing or inactive; degrading to rule_based", EXTERNAL_BUNDLE_CODE)
        return _Degraded("misconfigured", "EXTERNAL_BUNDLE_MISSING", norm=norm)

    worksheet_key, source_revision = await _worksheet_key(session, worksheet_id)
    context_snapshot = ctx.model_dump()
    context_hash = _sha256(_canonical_json(context_snapshot))
    # 快取鍵含**設定的** ai_service bundle code（呼叫前就已知）與 known_hand：
    # - 換 bundle／prompt 自然 miss；命中時不呼叫 ai_service、不扣額度。所有外部 run 共用同一個佔位
    #   bundle，所以這是唯一的區分。
    # - known_hand 決定 `ai_hand_hint_mismatch`，不同手別的請求不該共用同一份旗標。
    input_hash = _sha256(
        "|".join(
            [
                "external", norm, context_hash, bundle.code, external.service_bundle_code,
                external.known_hand or "", rule_set_code, "interactive", worksheet_key,
            ]
        )
    )
    existing = await _find_cached_run(session, input_hash=input_hash, bundle_id=bundle.id)
    if existing is not None:
        return _replay_external(existing, bundle_code=bundle.code, text=text)

    rsdata = await load_rule_set_from_db(session, rule_set_code)
    rsdata.validate_complete()
    allow = allow_lists_from_rule_set(rsdata)
    opts = await load_options_from_db(session, rule_set_code)
    rs_id, bundle_id = rs.id, bundle.id
    language = detect_language(norm)

    # ADR-037 D8：呼叫 ai_service 期間不占用 DB 連線。上面該讀的都讀完了；commit 結束這個交易、歸還連線
    # （session 是 expire_on_commit=False，上面的物件仍可讀）。
    await session.commit()

    try:
        (res,) = await external.port.parse(
            [
                WiParseRequest(
                    item_id="r1",
                    wi_statement=text,
                    source_lang="en" if language == "en" else "zh",
                    context={},
                    actor=external.actor,
                    scope=external.scope,
                )
            ],
            allow_lists=allow,
            lane="interactive",
        )
    except (ValueError, RuntimeError) as exc:
        # guard 的 ValueError（actor／scope 缺漏、context 越界）是呼叫端 bug；RuntimeError 是 schema hash 不符。
        # 對使用者降級，對維運大聲：記 ERROR，不記語句（pydantic 的訊息會帶輸入值，見 `_exc_summary`）。
        logger.error("external ai_service call refused (%s)", _exc_summary(exc))
        return _Degraded("misconfigured", type(exc).__name__.upper(), norm=norm)
    except Exception as exc:  # noqa: BLE001  port 契約是不拋；萬一拋了也不能讓 nl-draft 失敗
        logger.error("external ai_service port raised unexpectedly (%s)", _exc_summary(exc))
        return _Degraded("internal_error", type(exc).__name__.upper(), norm=norm)
    t_ai = time.perf_counter()

    if res.status != "ok":
        kind = res.error_kind.value if res.error_kind is not None else "unknown"
        if kind != "disabled":
            logger.warning("external ai_service returned failed (%s); degrading to rule_based", kind)
        code = (res.provenance or {}).get("upstream_code")
        return _Degraded(kind, code if isinstance(code, str) else None, norm=norm)
    if not res.motions:
        return _Degraded("empty_result", None, norm=norm)
    served_bundle = (res.provenance or {}).get("bundle_code")
    if served_bundle is not None and served_bundle != external.service_bundle_code:
        # client 本來就驗過 BUNDLE_MISMATCH；這裡是縱深防禦：run 若用設定的 bundle 當鍵、卻存了別的 bundle 的結果，
        # 之後換 bundle 仍會命中這份舊結果
        logger.error("external ai_service served an unexpected bundle; degrading to rule_based")
        return _Degraded("contract_mismatch", "BUNDLE_MISMATCH", norm=norm)

    source_ref = SourceRef(
        kind="interactive",
        worksheet_id=str(worksheet_id) if worksheet_id else None,
        import_id=None,
        import_row_index=None,
    )
    try:
        build = build_plan_from_motions(
            res.motions,
            source_text=text,
            normalized_text=norm,
            language=language,  # type: ignore[arg-type]
            source_ref=source_ref,
            result_issues=res.issues,
            known_hand=external.known_hand,
            allow_lists=allow,
        )
        drafts = preview_drafts(
            build.plan, build.candidates, rule_set_code=rule_set_code, allow_lists=allow, face_hit_params=None
        )
        t_compile = time.perf_counter()
        drafts = apply_engine_gate(drafts, rsdata, labels=_option_labels(opts))
        t_engine = time.perf_counter()
        # 一律不 auto（ADR-037 D4：AI 路徑逐項人工採用），不論 `wi_ai_auto_enabled`
        routing_status, routing_reasons = compute_routing(
            build.plan, build.candidates, drafts, extra_reasons=build.reasons, auto_enabled=False
        )
        prov, dropped_keys = sanitize_ai_service_provenance(res.provenance)
        prov["motion_labels"] = [
            {"action_id": aid, "sub_activity": lb.sub_activity, "object_text": lb.object_text, "hand_hint": lb.hand_hint}
            for aid, lb in build.labels.items()
        ]
        prov["dropped"] = list(build.dropped)
        validate_provenance(prov)
    except Exception as exc:  # noqa: BLE001
        logger.error("external ai_service result could not be turned into a plan (%s)", _exc_summary(exc))
        return _Degraded("contract_mismatch", "PLAN_BUILD_FAILED", norm=norm)
    if dropped_keys:
        # 鍵名是 adapter／guard 固定的，不是外部字串；ai_service 新增欄位時維運才看得到
        logger.warning("external ai_service provenance keys dropped by the allow-list: %s", sorted(dropped_keys))
    upstream = prov.get("run_id")
    latency = {
        "normalize": round((t_norm - t0) * 1000, 2),
        "ai_call": round((t_ai - t_norm) * 1000, 2),
        "compile": round((t_compile - t_ai) * 1000, 2),
        "engine": round((t_engine - t_compile) * 1000, 2),
    }
    result = ParseRunResult(
        run_id="",  # 下面寫入 run 後才有 id
        plan=build.plan,
        slot_candidates=build.candidates,
        drafts=drafts,
        routing_status=routing_status,  # type: ignore[arg-type]
        routing_reasons=routing_reasons,
        provenance=_external_response_provenance(prov, cached=False, latency=latency),
        source_revision=source_revision,
    )

    # legacy 的 GM 形狀 slots（舊前端）：仍由 MOST 自己的 rule parser 產生，出處標 rule_based——
    # 不是 AI 產生的。同時是 S4 與 AI 結果比對時的 MOST 基準。這段是同步 CPU（可能逾時），
    # 失敗不能讓整個請求失敗（ai_service 已經回了、額度已扣）：改用存檔候選還原的 legacy。
    legacy: dict | None = None
    try:
        synonyms = await syn_svc.list_synonyms(session, rule_set_code)
        rule_result = await asyncio.wait_for(
            loop.run_in_executor(
                None, functools.partial(RuleBasedParser(synonyms).parse, text, rule_set_code=rule_set_code)
            ),
            timeout=PARSE_CPU_TIMEOUT_S,
        )
        legacy = legacy_from_parse_run(
            raw_text=rule_result.raw_text,
            normalized_text=rule_result.normalized_text,
            slots=rule_result.slots,
            suggested_seq=rule_result.suggested_seq,
            overall_confidence=rule_result.overall_confidence,
            provenance=legacy_provenance(
                rule_provenance=rule_result.provenance,
                planner="ai_service",
                model=prov.get("model_served"),
                prompt_version=prov.get("prompt_version"),
                fallback=False,
                slots_parser=LEGACY_SLOTS_PARSER,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("legacy rule slots unavailable for an external result (%s)", _exc_summary(exc))

    run_id = uuid.uuid4()
    run = AiParseRun(
        id=run_id,
        source_kind="interactive",
        worksheet_id=worksheet_id,
        raw_text=text,
        normalized_text=norm,
        input_hash=input_hash,
        context_snapshot=context_snapshot,
        context_hash=context_hash,
        rule_set_id=rs_id,
        bundle_id=bundle_id,
        plan=build.plan.model_dump(),
        slot_candidates=[c.model_dump() for c in build.candidates],
        drafts=[d.model_dump() for d in drafts],
        llm_raw_response=None,
        routing_status=routing_status,
        routing_reasons=routing_reasons,
        fallback=False,
        cached=False,
        latency=latency,
        error=None,
        created_by=created_by,
        source_revision=source_revision,
        provenance=prov,
        upstream_run_id=upstream if isinstance(upstream, str) else None,
    )
    try:
        async with session.begin_nested():
            session.add(run)
            await session.flush()
    except IntegrityError:
        raced = await _find_cached_run(session, input_hash=input_hash, bundle_id=bundle_id)
        if raced is None:
            raise
        return _replay_external(raced, bundle_code=EXTERNAL_BUNDLE_CODE, text=text, raced=True)

    result = result.model_copy(update={"run_id": str(run_id)})
    if legacy is None:
        legacy = legacy_from_run_snapshot(raw_text=text, result=result, provenance_extra={"cached_run_id": result.run_id})
        legacy["provenance"]["slots_parser"] = "ai_candidates"
    return result, legacy


def _replay_external(
    run: AiParseRun, *, bundle_code: str, text: str, raced: bool = False
) -> tuple[ParseRunResult, dict]:
    result = _result_from_run(run, cached=True, bundle_code=bundle_code)
    extra: dict[str, Any] = {"cached_run_id": result.run_id}
    if raced:
        extra["raced"] = True
    legacy = legacy_from_run_snapshot(raw_text=text, result=result, provenance_extra=extra)
    # 重播的 legacy slots 是從存檔的候選還原的（AI 的候選，chosen 為空），不是 slot linker 的產物
    legacy["provenance"]["slots_parser"] = "ai_candidates"
    return result, legacy
