"""L4 批次 parse job（ADR-027 §12；不改 ADR-025 submit）。"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.ai_ops import AiDeploymentBundle, AiParseJob, AiParseJobItem
from ddm_v2.models.v2.import_staging import ExcelImport, ImportRow
from ddm_v2.models.v2.rule_set import RuleSet
from ddm_v2.services.v2 import synonym_service as syn_svc
from ddm_v2.services.v2 import wi_ai_service
from ddm_v2.settings import get_settings

logger = logging.getLogger(__name__)

ROW_SCHEMA = "import-row-v1"
LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
WORKER_ID_DEFAULT = "ddm-parse-worker"
ACTIVE_ITEM = ("queued", "leased", "running")

# claim：queued 或 lease 過期的 leased/running（reclaim）
CLAIM_SQL = """
SELECT id FROM ai_parse_job_items
WHERE job_id = :job_id
  AND available_at <= now()
  AND (
    status = 'queued'
    OR (
      status IN ('leased', 'running')
      AND lease_expires_at IS NOT NULL
      AND lease_expires_at < now()
    )
  )
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT :lim
"""


class ImportNotFound(Exception):
    pass


class JobNotFound(Exception):
    pass


class NoStagedRows(Exception):
    pass


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _row_text(normalized: dict) -> str:
    return str(normalized.get("description") or "").strip()


def _source_row_no(row: dict, index: int) -> int:
    raw = row.get("source_row_no") or row.get("row_no") or row.get("_row")
    if raw is not None:
        return int(raw)
    return index + 1


async def materialize_import_rows(session: AsyncSession, rec: ExcelImport) -> list[ImportRow]:
    """從 staged_rows 雙寫／補齊 import_rows（idempotent on import_id+source_row_no）。"""
    staged = rec.staged_rows or []
    if not staged:
        raise NoStagedRows()

    existing_q = await session.execute(
        select(ImportRow).where(ImportRow.import_id == rec.id)
    )
    by_no = {r.source_row_no: r for r in existing_q.scalars().all()}
    out: list[ImportRow] = []
    for i, row in enumerate(staged):
        source_row_no = _source_row_no(row, i)
        norm = dict(row)
        blob = json.dumps(norm, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        h = _sha256(blob)
        cur = by_no.get(source_row_no)
        if cur is None:
            cur = ImportRow(
                id=uuid.uuid4(),
                import_id=rec.id,
                source_row_no=source_row_no,
                raw_data=None,
                normalized_data=norm,
                schema_version=ROW_SCHEMA,
                input_hash=h,
                status="staged",
            )
            session.add(cur)
            by_no[source_row_no] = cur
        else:
            cur.normalized_data = norm
            cur.input_hash = h
            if cur.status in {"staged", "failed", "skipped"}:
                cur.status = "staged"
        out.append(cur)
    await session.flush()
    return sorted(out, key=lambda r: r.source_row_no)


def job_to_dict(job: AiParseJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "import_id": str(job.import_id),
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "total": job.total,
        "processed": job.processed,
        "succeeded": job.succeeded,
        "review": job.review_count,
        "failed": job.failed,
        "deployment_bundle_id": str(job.deployment_bundle_id),
        "rule_set_id": str(job.rule_set_id),
        "requested_by": job.requested_by,
        "cancel_requested_at": (
            job.cancel_requested_at.isoformat() if job.cancel_requested_at else None
        ),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


async def create_parse_job(
    session: AsyncSession,
    *,
    import_id: UUID,
    rule_set_code: str,
    requested_by: str,
    idempotency_key: str | None = None,
    bundle_code: str | None = None,
) -> dict[str, Any]:
    rec = await session.get(ExcelImport, import_id)
    if rec is None:
        raise ImportNotFound(str(import_id))

    key = idempotency_key or f"{import_id}:{rule_set_code}:{_sha256(str(rec.updated_at))[:12]}"
    existing = await session.execute(
        select(AiParseJob).where(AiParseJob.idempotency_key == key)
    )
    hit = existing.scalar_one_or_none()
    if hit is not None:
        return job_to_dict(hit)

    rows = await materialize_import_rows(session, rec)
    parseable = [r for r in rows if _row_text(r.normalized_data)]
    if not parseable:
        raise NoStagedRows()

    rs = (
        await session.execute(select(RuleSet).where(RuleSet.code == rule_set_code))
    ).scalar_one_or_none()
    if rs is None:
        raise syn_svc.RuleSetNotFound(rule_set_code)

    code = bundle_code or get_settings().wi_ai_bundle_code or wi_ai_service.DEFAULT_BUNDLE_CODE
    bundle = (
        await session.execute(
            select(AiDeploymentBundle).where(
                AiDeploymentBundle.code == code,
                AiDeploymentBundle.status == "active",
            )
        )
    ).scalar_one_or_none()
    if bundle is None:
        raise RuntimeError(f"ai deployment bundle missing or inactive: {code}")

    job = AiParseJob(
        id=uuid.uuid4(),
        idempotency_key=key,
        import_id=import_id,
        deployment_bundle_id=bundle.id,
        rule_set_id=rs.id,
        status="queued",
        total=len(parseable),
        requested_by=requested_by,
    )
    session.add(job)
    try:
        await session.flush()
    except IntegrityError:
        raced = (
            await session.execute(select(AiParseJob).where(AiParseJob.idempotency_key == key))
        ).scalar_one_or_none()
        if raced is None:
            raise
        return job_to_dict(raced)

    for row in parseable:
        session.add(
            AiParseJobItem(
                id=uuid.uuid4(),
                job_id=job.id,
                import_row_id=row.id,
                status="queued",
            )
        )
        row.status = "queued"
    await session.flush()
    return job_to_dict(job)


async def get_job(session: AsyncSession, *, import_id: UUID, job_id: UUID) -> dict[str, Any]:
    job = await session.get(AiParseJob, job_id)
    if job is None or job.import_id != import_id:
        raise JobNotFound(str(job_id))
    return job_to_dict(job)


async def request_cancel(session: AsyncSession, *, import_id: UUID, job_id: UUID) -> dict[str, Any]:
    job = await session.get(AiParseJob, job_id)
    if job is None or job.import_id != import_id:
        raise JobNotFound(str(job_id))
    now = datetime.now(timezone.utc)
    job.cancel_requested_at = now
    await session.execute(
        update(AiParseJobItem)
        .where(
            AiParseJobItem.job_id == job.id,
            AiParseJobItem.status == "queued",
        )
        .values(status="cancelled", updated_at=now)
    )
    await session.flush()
    if await _count_active(session, job.id) == 0:
        job.status = "cancelled"
        job.completed_at = now
    await session.flush()
    return job_to_dict(job)


async def _claim_items(
    session: AsyncSession,
    *,
    job_id: UUID,
    limit: int,
    worker_id: str,
) -> list[UUID]:
    now = datetime.now(timezone.utc)
    lease_exp = now + timedelta(seconds=LEASE_SECONDS)
    rows = (await session.execute(text(CLAIM_SQL), {"job_id": job_id, "lim": limit})).all()
    ids = [r[0] for r in rows]
    if not ids:
        return []
    await session.execute(
        update(AiParseJobItem)
        .where(AiParseJobItem.id.in_(ids))
        .values(
            status="leased",
            lease_owner=worker_id,
            lease_expires_at=lease_exp,
            attempt_count=AiParseJobItem.attempt_count + 1,
            updated_at=now,
        )
    )
    await session.flush()
    return ids


async def _count_active(session: AsyncSession, job_id: UUID) -> int:
    q = await session.execute(
        select(func.count())
        .select_from(AiParseJobItem)
        .where(
            AiParseJobItem.job_id == job_id,
            AiParseJobItem.status.in_(ACTIVE_ITEM),
        )
    )
    return int(q.scalar_one())


async def _bump_job_counters(
    session: AsyncSession,
    job_id: UUID,
    *,
    processed: int = 0,
    succeeded: int = 0,
    review: int = 0,
    failed: int = 0,
) -> None:
    """原子遞增，避免並發 tick last-writer-wins。"""
    if not any((processed, succeeded, review, failed)):
        return
    values: dict[str, Any] = {}
    if processed:
        values["processed"] = AiParseJob.processed + processed
    if succeeded:
        values["succeeded"] = AiParseJob.succeeded + succeeded
    if review:
        values["review_count"] = AiParseJob.review_count + review
    if failed:
        values["failed"] = AiParseJob.failed + failed
    await session.execute(update(AiParseJob).where(AiParseJob.id == job_id).values(**values))


OutcomeBucket = Literal["succeeded", "review", "failed"]


def _classify_outcome(
    *,
    routing_status: str,
    routing_reasons: list[str],
    has_complete_draft: bool,
) -> tuple[OutcomeBucket, str, str | None, dict | None]:
    """回 (bucket, item_status, row_status, last_error)。"""
    if routing_status == "review":
        return "review", "review", "review", None
    if routing_status == "auto" and has_complete_draft:
        return "succeeded", "ready", "ready", None
    if routing_status in {"abstain", "invalid"} or not has_complete_draft:
        return "review", "review", "review", None
    return (
        "failed",
        "failed",
        "failed",
        {"routing_status": routing_status, "routing_reasons": routing_reasons},
    )


async def _finalize_job_status(session: AsyncSession, job: AiParseJob) -> None:
    await session.refresh(job)
    now = datetime.now(timezone.utc)
    active = await _count_active(session, job.id)
    if active > 0:
        job.status = "running" if (job.processed > 0 or job.started_at) else "queued"
        return
    if job.cancel_requested_at:
        job.status = "cancelled"
        job.completed_at = now
        return
    if job.failed > 0 and (job.succeeded + job.review_count) > 0:
        job.status = "partial"
    elif job.failed > 0 and (job.succeeded + job.review_count) == 0:
        job.status = "failed"
    else:
        job.status = "completed"
    job.completed_at = now


async def tick_job(
    session: AsyncSession,
    *,
    import_id: UUID,
    job_id: UUID,
    limit: int = 1,
    worker_id: str = WORKER_ID_DEFAULT,
) -> dict[str, Any]:
    """認領並列處理最多 ``limit`` 筆；一律使用 job ピン定的 rule_set／bundle。"""
    job = await session.get(AiParseJob, job_id)
    if job is None or job.import_id != import_id:
        raise JobNotFound(str(job_id))

    rs = await session.get(RuleSet, job.rule_set_id)
    if rs is None:
        raise syn_svc.RuleSetNotFound(str(job.rule_set_id))
    bundle = await session.get(AiDeploymentBundle, job.deployment_bundle_id)
    if bundle is None:
        raise RuntimeError(f"pinned deployment bundle missing: {job.deployment_bundle_id}")

    now = datetime.now(timezone.utc)
    if job.cancel_requested_at:
        await session.execute(
            update(AiParseJobItem)
            .where(AiParseJobItem.job_id == job.id, AiParseJobItem.status == "queued")
            .values(status="cancelled", updated_at=now)
        )
        await session.flush()
        if await _count_active(session, job.id) == 0:
            job.status = "cancelled"
            job.completed_at = now
            await session.flush()
            return {"job": job_to_dict(job), "processed_now": 0, "item_ids": []}

    if job.status in {"completed", "failed", "cancelled", "partial"} and not job.cancel_requested_at:
        return {"job": job_to_dict(job), "processed_now": 0, "item_ids": []}

    if job.status == "queued":
        job.status = "running"
        job.started_at = now

    claimed = await _claim_items(
        session,
        job_id=job.id,
        limit=max(1, min(limit, 4)),
        worker_id=worker_id,
    )
    processed_now = 0
    for item_id in claimed:
        item = await session.get(AiParseJobItem, item_id)
        if item is None:
            continue
        if job.cancel_requested_at:
            item.status = "cancelled"
            item.lease_owner = None
            item.lease_expires_at = None
            item.updated_at = datetime.now(timezone.utc)
            continue

        row = await session.get(ImportRow, item.import_row_id)
        if row is None:
            item.status = "failed"
            item.last_error = {"message": "import_row missing"}
            await _bump_job_counters(session, job.id, processed=1, failed=1)
            processed_now += 1
            continue

        text_in = _row_text(row.normalized_data)
        item.status = "running"
        row.status = "processing"
        await session.flush()
        try:
            result, _legacy = await wi_ai_service.parse_interactive(
                session,
                text=text_in,
                rule_set_code=rs.code,
                created_by=job.requested_by,
                source_kind="import_row",
                import_id=import_id,
                import_row_index=row.source_row_no,
                bundle_code=bundle.code,
            )
            item.ai_parse_run_id = UUID(result.run_id)
            bucket, item_status, row_status, last_error = _classify_outcome(
                routing_status=result.routing_status,
                routing_reasons=list(result.routing_reasons or []),
                has_complete_draft=any(d.complete for d in result.drafts),
            )
            item.lease_owner = None
            item.lease_expires_at = None
            item.status = item_status
            row.status = row_status  # type: ignore[assignment]
            item.last_error = last_error
            await _bump_job_counters(
                session,
                job.id,
                processed=1,
                succeeded=1 if bucket == "succeeded" else 0,
                review=1 if bucket == "review" else 0,
                failed=1 if bucket == "failed" else 0,
            )
            processed_now += 1
        except Exception as exc:  # noqa: BLE001 — row 級隔離
            logger.exception("parse job item failed: %s", item_id)
            attempts = item.attempt_count or 1
            if attempts < MAX_ATTEMPTS:
                item.status = "queued"
                item.available_at = datetime.now(timezone.utc) + timedelta(seconds=2**attempts)
                item.lease_owner = None
                item.lease_expires_at = None
                item.last_error = {"message": str(exc)}
                row.status = "queued"
            else:
                item.status = "failed"
                item.last_error = {"message": str(exc)}
                row.status = "failed"
                await _bump_job_counters(session, job.id, processed=1, failed=1)
                processed_now += 1
        item.updated_at = datetime.now(timezone.utc)
        await session.flush()

    await _finalize_job_status(session, job)
    await session.flush()
    return {
        "job": job_to_dict(job),
        "processed_now": processed_now,
        "item_ids": [str(i) for i in claimed],
    }
