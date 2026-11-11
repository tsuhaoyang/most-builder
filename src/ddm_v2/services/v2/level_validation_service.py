"""Level validation run 服務（R2b）：append-only 證據 + publish gate。

不改 most_engine.level 演算法；只包一層 persist／gate。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import ConflictError, ValidationError
from ddm_v2.models.v2.level_validation import LevelValidationRun
from ddm_v2.models.v2.policy import LevelPolicyVersion
from ddm_v2.models.v2.worksheet import LevelEntry, MostCycle, MostWorksheet, WiRow
from ddm_v2.most_engine import level as level_engine

Trigger = Literal["interactive", "save", "publish", "revalidate"]


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def input_hash_for_rows(rows: list[level_engine.LevelRow]) -> str:
    payload = [
        {
            "content": r.content,
            "raw_seconds": r.raw_seconds,
            "coefficient": r.coefficient,
            "number": r.number,
            "number_count": r.number_count,
            "ascription": r.ascription,
            "level": r.level,
            "countersignature": r.countersignature,
            "parent_countersignature": r.parent_countersignature,
            "order": r.order,
        }
        for r in rows
    ]
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


async def load_level_rows_for_worksheet(
    session: AsyncSession, worksheet_id: uuid.UUID
) -> list[level_engine.LevelRow]:
    """自 DB 組 engine LevelRow（權威：LevelEntry.raw_seconds × coefficient）。"""
    wrs = (
        await session.execute(
            select(WiRow).where(WiRow.worksheet_id == worksheet_id).order_by(WiRow.seq_no)
        )
    ).scalars().all()
    out: list[level_engine.LevelRow] = []
    for wr in wrs:
        lv = (
            await session.execute(select(LevelEntry).where(LevelEntry.wi_row_id == wr.id))
        ).scalar_one_or_none()
        if lv is None:
            continue
        cyc = (
            await session.execute(select(MostCycle).where(MostCycle.wi_row_id == wr.id))
        ).scalar_one_or_none()
        content = (
            (cyc.narrative_zh if cyc and cyc.narrative_zh else None)
            or wr.sub_activity
            or f"列{wr.seq_no}"
        )
        out.append(
            level_engine.LevelRow(
                content=content,
                raw_seconds=float(lv.raw_seconds or 0),
                coefficient=float(lv.coefficient or 1),
                number=lv.number,
                number_count=lv.number_count,
                ascription=lv.ascription,
                level=lv.level,
                countersignature=lv.countersignature,
                parent_countersignature=lv.parent_countersignature,
                order=lv.order_in_group,
            )
        )
    return out


def _issues_payload(issues: list[Any]) -> list[dict[str, Any]]:
    return [{"code": i.code, "row_index": i.row_index, "message": i.message} for i in issues]


def _run_out(run: LevelValidationRun, policy: LevelPolicyVersion) -> dict[str, Any]:
    return {
        "run_id": str(run.id),
        "worksheet_id": str(run.worksheet_id),
        "worksheet_revision": int(run.worksheet_revision),
        "level_policy_version_id": str(run.level_policy_version_id),
        "level_policy_code": policy.code,
        "level_policy_version_no": policy.version_no,
        "input_hash": run.input_hash,
        "valid": bool(run.valid),
        "issues": list(run.issues_json or []),
        "output_contract_version": run.output_contract_version,
        "trigger": run.trigger,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


async def validate_and_persist(
    session: AsyncSession,
    worksheet_id: uuid.UUID,
    *,
    trigger: Trigger,
    actor: str,
) -> dict[str, Any]:
    """驗證目前 worksheet Level 並 append run（同 key 不覆寫，回既有列）。"""
    from ddm_v2.services.v2.worksheet_service import WorksheetNotFound

    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))

    if ws.level_policy_version_id is None:
        raise ConflictError(
            "worksheet 未綁定 level_policy_version_id",
            detail={"code": "LEVEL_POLICY_MISMATCH"},
        )
    policy = await session.get(LevelPolicyVersion, ws.level_policy_version_id)
    if policy is None:
        raise ConflictError(
            "level policy 不存在或已失效",
            detail={"code": "LEVEL_POLICY_MISMATCH"},
        )

    rows = await load_level_rows_for_worksheet(session, worksheet_id)
    issues = level_engine.validate(rows)
    valid = not issues
    input_hash = input_hash_for_rows(rows)
    rev = int(ws.revision_no or 1)

    existing = (
        await session.execute(
            select(LevelValidationRun).where(
                LevelValidationRun.worksheet_id == worksheet_id,
                LevelValidationRun.worksheet_revision == rev,
                LevelValidationRun.level_policy_version_id == policy.id,
                LevelValidationRun.input_hash == input_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _run_out(existing, policy)

    output_json: dict[str, Any] | None = None
    if valid:
        output_json = level_engine.build_output(rows)

    run = LevelValidationRun(
        id=uuid.uuid4(),
        worksheet_id=worksheet_id,
        worksheet_revision=rev,
        level_policy_version_id=policy.id,
        input_hash=input_hash,
        valid=valid,
        issues_json=_issues_payload(issues),
        output_json=output_json,
        output_contract_version=policy.output_contract_version,
        trigger=trigger,
        created_by=actor or "unknown",
    )
    session.add(run)
    await session.flush()
    return _run_out(run, policy)


async def assert_publishable(session: AsyncSession, worksheet_id: uuid.UUID) -> LevelValidationRun:
    """Publish gate（§9.5）：必須有目前 revision + policy + input_hash 的 valid run。

    不在 publish transaction 內新建證據。
    """
    from ddm_v2.services.v2.worksheet_service import WorksheetNotFound

    ws = await session.get(MostWorksheet, worksheet_id)
    if ws is None:
        raise WorksheetNotFound(str(worksheet_id))

    if ws.level_policy_version_id is None:
        raise ConflictError(
            "發布前 worksheet 必須綁定 level policy",
            detail={"code": "LEVEL_POLICY_MISMATCH"},
        )

    rows = await load_level_rows_for_worksheet(session, worksheet_id)
    current_hash = input_hash_for_rows(rows)
    rev = int(ws.revision_no or 1)

    run = (
        await session.execute(
            select(LevelValidationRun)
            .where(
                LevelValidationRun.worksheet_id == worksheet_id,
                LevelValidationRun.worksheet_revision == rev,
                LevelValidationRun.level_policy_version_id == ws.level_policy_version_id,
                LevelValidationRun.input_hash == current_hash,
            )
            .order_by(LevelValidationRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if run is None:
        any_rev = (
            await session.execute(
                select(LevelValidationRun)
                .where(
                    LevelValidationRun.worksheet_id == worksheet_id,
                    LevelValidationRun.worksheet_revision == rev,
                    LevelValidationRun.level_policy_version_id == ws.level_policy_version_id,
                )
                .order_by(LevelValidationRun.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if any_rev is not None and not any_rev.valid:
            raise ValidationError(
                "目前 revision 的 Level 驗證未通過",
                detail={
                    "code": "LEVEL_VALIDATION_FAILED",
                    "issues": json.dumps(any_rev.issues_json or [], ensure_ascii=False),
                },
            )
        raise ConflictError(
            "發布前需先通過 Level 驗證（目前 revision 尚無匹配的 validation run）",
            detail={"code": "LEVEL_VALIDATION_REQUIRED"},
        )

    if not run.valid:
        raise ValidationError(
            "目前 revision 的 Level 驗證未通過",
            detail={
                "code": "LEVEL_VALIDATION_FAILED",
                "issues": json.dumps(run.issues_json or [], ensure_ascii=False),
            },
        )

    return run
