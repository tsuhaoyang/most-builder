"""AI review events → feedback candidates（§11.2 / §12.3）。

任何 candidate 都不自動生效（I7）；僅落庫供後續人工 promotion。
"""
from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.ai_ops import AiFeedbackCandidate, AiParseRun, AiReviewEvent

EVENT_TYPES = frozenset(
    {
        "accept_plan",
        "split_action",
        "merge_actions",
        "reorder_action",
        "add_action",
        "delete_action",
        "replace_role",
        "replace_candidate",
        "change_sequence_model",
        "change_quantity_policy",
        "mark_missing",
        "accept_all",
    }
)


class RunNotFound(Exception):
    pass


class ValidationError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _is_low_or_missing_before(before: dict | None) -> bool:
    if before is None:
        return True
    if before.get("option_code") in (None, ""):
        return True
    if before.get("no_candidate") is True:
        return True
    score = before.get("score")
    if score is not None:
        try:
            return float(score) < 0.7
        except (TypeError, ValueError):
            return False
    reason = before.get("review_reason") or before.get("reason")
    return reason in {"no_candidate", "low_score"}


def _surface_text(after: dict | None, target: dict | None) -> str | None:
    if after:
        for key in ("surface_text", "text", "synonym_raw", "label"):
            val = after.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    if target:
        for key in ("surface_text", "text"):
            val = target.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _text_in_source(surface: str, raw_text: str, normalized_text: str) -> bool:
    s = surface.strip()
    if not s:
        return False
    return s in raw_text or s in normalized_text or s.lower() in normalized_text.lower()


def derive_candidates(
    *,
    event_type: str,
    target: dict | None,
    before: dict | None,
    after: dict | None,
    run: AiParseRun,
) -> list[dict[str, Any]]:
    """回傳待寫入的 feedback candidate dicts（尚無 id / review_event_id）。"""
    out: list[dict[str, Any]] = []
    if event_type == "replace_candidate" and _is_low_or_missing_before(before):
        surface = _surface_text(after, target)
        if surface and _text_in_source(surface, run.raw_text, run.normalized_text):
            param = None
            option_code = None
            if target:
                param = target.get("parameter")
            if after:
                option_code = after.get("option_code")
            if param and option_code:
                out.append(
                    {
                        "kind": "synonym",
                        "payload": {
                            "parameter": param,
                            "option_code": option_code,
                            "surface_text": surface,
                            "normalized": run.normalized_text,
                        },
                        "status": "candidate",
                    }
                )
    elif event_type in {"split_action", "merge_actions", "replace_role"}:
        out.append(
            {
                "kind": "few_shot",
                "payload": {
                    "event_type": event_type,
                    "normalized_text": run.normalized_text,
                    "target": target,
                    "before": before,
                    "after": after,
                },
                "status": "candidate",
            }
        )
    elif event_type == "accept_all":
        out.append(
            {
                "kind": "gold",
                "payload": {
                    "run_id": str(run.id),
                    "normalized_text": run.normalized_text,
                    "plan": run.plan,
                },
                "status": "candidate",
            }
        )
    return out


async def record_reviews(
    session: AsyncSession,
    *,
    run_id: UUID,
    events: list[dict[str, Any]],
    reviewer: str,
    ui_version: str | None,
) -> dict[str, Any]:
    if not events:
        raise ValidationError("events 不可為空")

    run = await session.get(AiParseRun, run_id)
    if run is None:
        raise RunNotFound(str(run_id))

    event_ids: list[str] = []
    candidate_ids: list[str] = []

    for raw in events:
        event_type = raw.get("event_type")
        if event_type not in EVENT_TYPES:
            raise ValidationError(f"unknown event_type: {event_type}")
        ev_id = uuid.uuid4()
        ev = AiReviewEvent(
            id=ev_id,
            run_id=run_id,
            event_type=event_type,
            target=raw.get("target"),
            before=raw.get("before"),
            after=raw.get("after"),
            reason=raw.get("reason"),
            reviewer=reviewer,
            ui_version=ui_version,
        )
        session.add(ev)
        await session.flush()
        event_ids.append(str(ev_id))

        for cand in derive_candidates(
            event_type=event_type,
            target=raw.get("target"),
            before=raw.get("before"),
            after=raw.get("after"),
            run=run,
        ):
            cid = uuid.uuid4()
            session.add(
                AiFeedbackCandidate(
                    id=cid,
                    review_event_id=ev_id,
                    kind=cand["kind"],
                    payload=cand["payload"],
                    status=cand["status"],
                )
            )
            candidate_ids.append(str(cid))

    await session.flush()
    from ddm_v2.services.v2.outbox_service import enqueue_review_recorded

    await enqueue_review_recorded(
        session,
        run_id=run_id,
        review_event_ids=event_ids,
        review_event_types=[e.get("event_type") for e in events if e.get("event_type")],
        worksheet_id=run.worksheet_id,
        worksheet_revision=int(run.source_revision) if run.source_revision is not None else None,
    )
    return {
        "run_id": str(run_id),
        "event_ids": event_ids,
        "candidate_ids": candidate_ids,
    }


async def list_events_for_run(session: AsyncSession, run_id: UUID) -> list[dict]:
    q = await session.execute(
        select(AiReviewEvent)
        .where(AiReviewEvent.run_id == run_id)
        .order_by(AiReviewEvent.created_at.asc())
    )
    rows = q.scalars().all()
    return [
        {
            "id": str(r.id),
            "run_id": str(r.run_id),
            "event_type": r.event_type,
            "target": r.target,
            "before": r.before,
            "after": r.after,
            "reason": r.reason,
            "reviewer": r.reviewer,
            "ui_version": r.ui_version,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
