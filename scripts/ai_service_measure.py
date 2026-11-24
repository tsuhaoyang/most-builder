"""ai_service 真實呼叫量測（ADR-037 D9 啟用前置：30 句延遲分布；契約 §4、§5 行為驗證）。

**只在本機開發用**。環境變數只在這支程序裡設定，不動任何服務的設定，也不對使用者開放 AI。
走的是正式程式路徑：`wi_ai_service.parse_interactive(external=…)` → guard → adapter → client → mapper
→ plan adapter → compile 預覽 → engine_gate → routing → 寫 `ai_parse_runs`。

安全：
- 金鑰只從 `DDM_AI_SERVICE_KEY_FILE` 讀，本程式不印、不寫進報告。
- `DATABASE_URL` 必須指向拋棄式測試庫（主機埠不得是 5432——那是使用者的開發庫）。
- 報告寫到 `data/ai-service-measure/`（gitignore）；內含語句與模型輸出，不要 commit。

用法（環境變數見 docs/roadmap/ai-service-integration-plan.md「真實量測」）：
    PYTHONPATH=src .venv/bin/python scripts/ai_service_measure.py smoke      # 3–5 句
    PYTHONPATH=src .venv/bin/python scripts/ai_service_measure.py latency    # 30 句依序
    PYTHONPATH=src .venv/bin/python scripts/ai_service_measure.py errors     # 錯誤分類與 429
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "ai-service-measure"
SAMPLE_XLSX = ROOT / "docs" / "sample_excel" / "MiniMOST1128 (1).xlsx"
GOLD_DIR = ROOT / "tests" / "gold" / "wi_plans"


def _guard_env() -> None:
    """只准用本機的拋棄式測試庫：主機是 loopback、埠不是 5432（使用者的開發庫）、庫名看得出是測試庫。"""
    url = os.environ.get("DATABASE_URL", "")
    parts = urlsplit(url.replace("postgresql+asyncpg", "postgresql"))
    db = parts.path.lstrip("/")
    if (
        not url or parts.hostname not in ("127.0.0.1", "localhost") or parts.port in (None, 5432)
        or "?" in url or not any(tag in db for tag in ("test", "mig", "measure"))
    ):
        sys.exit("DATABASE_URL must point at the local disposable test DB (loopback, not port 5432, test db name)")
    if not os.environ.get("DDM_AI_SERVICE_KEY_FILE"):
        sys.exit("DDM_AI_SERVICE_KEY_FILE is required (the key is never read from argv or printed)")


def sentences() -> list[tuple[str, str | None, str]]:
    """(句子, 手別, 出處)。先取 MiniMOST 樣本的 METHOD 欄，再補 gold 的 source_text。不用真實 SKU 資料。"""
    import openpyxl

    out: list[tuple[str, str | None, str]] = []
    ws = openpyxl.load_workbook(SAMPLE_XLSX, read_only=True, data_only=True)["1126"]
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 6 or not row[6] or not str(row[6]).strip():
            continue
        hand = str(row[5]).strip() if row[5] in ("LH", "RH", "BH") else None
        out.append((str(row[6]).strip(), hand, f"MiniMOST1128!G{i + 1}"))
    seen = {s for s, _h, _src in out}
    for f in sorted(GOLD_DIR.glob("*.json")):
        text = (json.loads(f.read_text(encoding="utf-8")).get("source_text") or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append((text, None, f"gold/{f.stem}"))
    return out


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 2)


async def _parse_one(text: str, hand: str | None, nonce: str) -> dict:
    from ddm_v2.ai_integration.runtime import get_runtime_async
    from ddm_v2.database import get_session_maker
    from ddm_v2.services.v2 import wi_ai_service
    from ddm_v2.services.v2.rule_set_service import get_active_rule_set_code
    from ddm_v2.services.v2.wi_draft_service import drafts_from_parse

    rt = await get_runtime_async()
    if not rt.available:
        raise SystemExit("ai_service runtime not available with the current environment (see WARNING log)")
    async with get_session_maker()() as session:
        code = await get_active_rule_set_code(session)
        await session.commit()
        external = wi_ai_service.ExternalAi(
            port=rt.parser, service_bundle_code=rt.service_bundle_code, actor="MEASURE", scope=f"measure-{nonce}",
            known_hand=hand,  # type: ignore[arg-type]
        )
        t0 = time.perf_counter()
        result, legacy = await wi_ai_service.parse_interactive(
            session, text=text, rule_set_code=code, created_by="MEASURE", external=external,
        )
        wall = time.perf_counter() - t0
        await session.commit()
    prov = result.provenance or {}
    status = wi_ai_service.ai_status_of(prov)
    parsed = drafts_from_parse(result, text=text, hand=hand, wi_group=None, ai_status=status)
    return {
        "status": status,
        "wall_s": round(wall, 2),
        "latency_ms": prov.get("latency_ms"),
        "cached": bool(prov.get("cached")),
        "ai_error": prov.get("ai_error"),
        "upstream_run_id": prov.get("ai_run_id"),
        "model_served": prov.get("model"),
        "prompt_version": prov.get("prompt_version"),
        "routing_status": result.routing_status,
        "routing_reasons": result.routing_reasons,
        "n_actions": len(result.plan.actions),
        "n_drafts": len(result.drafts),
        "chosen_set": [c.parameter for c in result.slot_candidates if c.chosen is not None],
        "role_values": [
            {"action": a.action_id, "role": k, "value": getattr(v, "value", None)}
            for a in result.plan.actions for k, v in a.roles.items() if getattr(v, "value", None) is not None
        ],
        "measurements": [a.action_id for a in result.plan.actions if a.measurements],
        "motion_labels": prov.get("motion_labels"),
        "draft_complete": [p.snapshot["complete"] for p in parsed],
        "draft_issues": [p.snapshot["issues"] for p in parsed],
        "legacy_keys": sorted(legacy.keys()),
    }


async def run_parse(mode: str, offset: int = 0, count: int | None = None) -> dict:
    items = sentences()[offset:]
    items = items[: count or (4 if mode == "smoke" else 30)]
    nonce = uuid.uuid4().hex[:8]
    rows = []
    for i, (text, hand, src) in enumerate(items, 1):
        try:
            r = await _parse_one(text, hand, nonce)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001  量測工具：記下就繼續
            r = {"status": "exception", "error": type(exc).__name__}
        r.update({"i": i, "source": src, "text": text, "hand": hand})
        rows.append(r)
        print(f"[{i:02d}/{len(items)}] {r['status']:<10} wall={r.get('wall_s')}s routing={r.get('routing_status')} "
              f"drafts={r.get('n_drafts')} err={r.get('ai_error')}", flush=True)
    ok = [r["wall_s"] for r in rows if r.get("status") == "ai_service" and not r.get("cached")]
    summary = {
        "n": len(rows),
        "ai_service": sum(r.get("status") == "ai_service" for r in rows),
        "degraded": sum(r.get("status") == "degraded" for r in rows),
        "other": sum(r.get("status") not in ("ai_service", "degraded") for r in rows),
        "cached": sum(bool(r.get("cached")) for r in rows),
    }
    if ok:
        summary.update({
            "wall_s_p50": _pct(ok, 0.5), "wall_s_p95": _pct(ok, 0.95), "wall_s_max": max(ok),
            "wall_s_min": min(ok), "wall_s_mean": round(statistics.mean(ok), 2),
            "over_15s": sum(v > 15 for v in ok), "over_30s": sum(v > 30 for v in ok),
            "over_45s": sum(v > 45 for v in ok), "over_60s": sum(v > 60 for v in ok),
        })
    return {"summary": summary, "rows": rows}


async def run_errors() -> dict:
    """錯誤分類（契約 §4.2）與准入（§5.2）。只用一般服務金鑰；不打 transition。"""
    import httpx

    from ddm_v2.ai_integration.client import AiServiceClient
    from ddm_v2.ai_integration.config import default_resolver, load_config
    from ddm_v2.ai_integration.errors import AiServiceError
    from ddm_v2.ai_integration.schema import wi_motion_parse_schema

    base = load_config()
    variables = {"wi_statement": "左手抓握螺絲", "source_lang": "zh", "context": {}}
    out: dict[str, object] = {}

    async def call(cfg, *, prompt_variant: str = "zh", text: str | None = None) -> dict:
        client = AiServiceClient(cfg, resolver=default_resolver)
        v = dict(variables, wi_statement=text or variables["wi_statement"])
        t0 = time.perf_counter()
        try:
            res = await client.structured_completion(
                variables=v, json_schema=wi_motion_parse_schema(), prompt_variant=prompt_variant,
                lane="interactive", request_id=str(uuid.uuid4()),
            )
            return {"ok": True, "s": round(time.perf_counter() - t0, 2), "attempts": res.attempts}
        except AiServiceError as err:
            return {"ok": False, "s": round(time.perf_counter() - t0, 2), "kind": err.kind.value,
                    "upstream_code": err.upstream_code, "http_status": err.http_status,
                    "retry_after_s": err.retry_after_s}

    env = dict(os.environ)
    # 404：不存在的 bundle
    out["unknown_bundle"] = await call(load_config({**env, "DDM_AI_SERVICE_BUNDLE_CODE": "most-does-not-exist-000"}))
    # 422：bundle 沒宣告的 prompt_variant
    out["bad_prompt_variant"] = await call(base, prompt_variant="xx")
    # 401：錯的金鑰（明確是假的）
    with tempfile.NamedTemporaryFile("w", suffix=".key", delete=True, encoding="utf-8") as fake_key:
        fake_key.write("FAKE-key-for-401-check-000000000000")  # 明確是假的
        fake_key.flush()
        out["wrong_key"] = await call(load_config({**env, "DDM_AI_SERVICE_KEY_FILE": fake_key.name}))
    # X-Request-Id 是否回傳（契約 §2.4：不回傳）；直接打一次 401，看回應 header（不需要 LLM）
    async with httpx.AsyncClient(timeout=10) as raw:
        r = await raw.post(base.base_url.rstrip("/") + "/v1/llm/structured-completion",
                           headers={"X-Request-Id": "measure-echo-check"}, json={})
        out["request_id_echoed"] = "x-request-id" in {k.lower() for k in r.headers}
    # 429：同時送 3 個（ai_service 並行 2），不重試，看分類與 Retry-After
    no_retry = load_config({**env, "DDM_AI_SERVICE_MAX_RETRIES": "0"})
    burst = await asyncio.gather(*[
        call(no_retry, text=f"右手拿起螺絲起子{n}") for n in range(3)
    ])
    out["burst_3_no_retry"] = burst
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["smoke", "latency", "errors"])
    ap.add_argument("--offset", type=int, default=0, help="從第幾句開始（跳過已量過、會命中快取的句子）")
    ap.add_argument("--count", type=int, default=None)
    args = ap.parse_args()
    _guard_env()
    report = asyncio.run(
        run_errors() if args.mode == "errors" else run_parse(args.mode, args.offset, args.count)
    )
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = OUT_DIR / f"{args.mode}-{stamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    path.chmod(0o600)  # 含語句與模型輸出
    print(json.dumps(report.get("summary", report), ensure_ascii=False, indent=2, default=str))
    print(f"report: {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
