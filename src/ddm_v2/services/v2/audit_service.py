"""工作流稽核服務：僅追加寫入 workflow_audit_log（ADR-018 裁決 3）。

呼叫方不得單獨對 WorkflowAuditLog 做 delete/update；
commit 由外層 session 統一負責。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.audit import WorkflowAuditLog


async def log_audit(
    session: AsyncSession,
    entity_type: str,      # 'process_version' | 'motion_module' | 'rule_set'
    entity_id: uuid.UUID,
    action: str,           # 'approve' | 'promote' | 'publish' | 'override' | 'retire'
    from_status: str | None,
    to_status: str | None,
    actor: str,
    comment: str | None = None,
    payload: dict[str, Any] | None = None,
) -> WorkflowAuditLog:
    """僅追加寫入；呼叫後由 session commit 統一提交，不得單獨 delete/update。"""
    entry = WorkflowAuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        comment=comment,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )
    session.add(entry)
    return entry
