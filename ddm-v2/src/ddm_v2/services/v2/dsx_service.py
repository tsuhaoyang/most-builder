"""DSX a3 距離查詢的協調層（DSX 整合 API 契約 v2 §3.1／§6；ADR-031 D4／I1／I4／I5）。

流程：feature flag → （wi_row_id 有值時）確認該列存在且版本仍為 draft →
解析 `vocab_id`→`external_code`（即 DSX 物件 id，§2.3/§2.4，剝除 §2.3a 的合成
`to` 後綴）→ 呼叫 DSX client → 成功則 upsert `wi_row_dsx_suggestions` 快照（唯一出處記錄）。

`wi_row_id` 是 optional（2026-08-24 User 裁決，契約 §6）：`workbench-v3/` 組新列時
（尚未存檔，`id` 只存在瀏覽器端）沒有真實 `WiRow` 可指。缺席時**不驗、不查、不寫
快照**——距離查詢照樣成功回傳，只是少了「這筆建議當初從哪查來的」這筆稽核紀錄，
僅限「組新列、還沒存檔」這個情境。D4／I1／I5 不變式沒有放寬：沒有任何東西自動寫進
`slot_inputs`，使用者仍要手動選填、走既有存檔流程。

§2.3a 合成 `to` 後綴：`scripts/dev_seed_dsx_vocab.py` 對 DSX `vocab_kinds=[from, to]`
的物件（工作站/輸送帶/料車/料盒等，可雙向）額外多種一列 `kind='to'`，`external_code`
加 `SYNTHETIC_TO_SUFFIX` 後綴以繞過 `external_code` unique 限制。這個後綴只存在於
MOST 這一側，DSX 不認得——送給 `dsx_client.query_distance` 前必須先剝除。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.exceptions import ConflictError, NotFoundError
from ddm_v2.models.v2.dsx_suggestion import WiRowDsxSuggestion
from ddm_v2.models.v2.vocab import WorkVocabItem
from ddm_v2.models.v2.worksheet import MostWorksheet, ProcessVersion, WiRow
from ddm_v2.services.v2 import dsx_client
from ddm_v2.settings import get_settings

A_SLOT_KEY = "a3"

# scripts/dev_seed_dsx_vocab.py 用同一個常數種合成的 to 列，見本模組 docstring §2.3a。
SYNTHETIC_TO_SUFFIX = "__to"


def _strip_synthetic_suffix(external_code: str) -> str:
    if external_code.endswith(SYNTHETIC_TO_SUFFIX):
        return external_code[: -len(SYNTHETIC_TO_SUFFIX)]
    return external_code


async def _require_row_writable(session: AsyncSession, wi_row_id: UUID) -> None:
    """wi_row_id 有值＝這次查詢要寫入 wi_row_dsx_suggestions。

    比照 `wi_context_service._require_editable_row`：列不存在 → 404；所屬版本
    已凍結（非 draft）→ 409（拒絕寫入，但查詢本身仍可能是想看建議值——MVP 選擇
    整體拒絕，理由與 wi_context 一致：已凍結版本本來就不該再產生任何新的編輯痕跡）。
    """
    wr = await session.get(WiRow, wi_row_id)
    if wr is None:
        raise NotFoundError(f"wi_row 不存在：{wi_row_id}")
    ws = await session.get(MostWorksheet, wr.worksheet_id)
    if ws is None:
        raise NotFoundError(f"worksheet 不存在：{wr.worksheet_id}")
    pv = await session.get(ProcessVersion, ws.process_version_id)
    if pv is not None and pv.status != "draft":
        raise ConflictError(
            f"版本狀態為 {pv.status}，已凍結不可寫入 DSX 建議快照（請另存新檔）",
            detail={"code": "VERSION_PUBLISHED"},
        )


async def get_a3_distance(
    session: AsyncSession,
    *,
    wi_row_id: UUID | None,
    from_vocab_id: UUID,
    to_vocab_id: UUID,
    actor: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.dsx_integration_enabled:
        return {"available": False, "reason": "integration_disabled"}

    if wi_row_id is not None:
        await _require_row_writable(session, wi_row_id)

    from_item = await session.get(WorkVocabItem, from_vocab_id)
    to_item = await session.get(WorkVocabItem, to_vocab_id)
    if from_item is None or not from_item.external_code:
        return {"available": False, "reason": "vocab_not_mapped"}
    if to_item is None or not to_item.external_code:
        return {"available": False, "reason": "vocab_not_mapped"}

    if not settings.dsx_api_base_url:
        raise RuntimeError(
            "DDM_DSX_INTEGRATION_ENABLED=1 但 DDM_DSX_API_BASE_URL 未設定"
        )

    try:
        result = await dsx_client.query_distance(
            base_url=settings.dsx_api_base_url,
            from_id=from_item.external_code,
            to_id=_strip_synthetic_suffix(to_item.external_code),
            timeout_s=settings.dsx_timeout_s,
        )
    except dsx_client.DsxObjectNotFound:
        return {"available": False, "reason": "dsx_object_not_found"}
    except dsx_client.DsxUnreachable:
        return {"available": False, "reason": "dsx_unreachable"}
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        # DSX 回了看不懂的東西（缺欄位／非數字／非 JSON）——對 IE 而言效果跟連不上
        # 一樣：這個組合現在算不出建議值，不需要開第二個 reason（沿用 dsx_unreachable）。
        return {"available": False, "reason": "dsx_unreachable"}

    queried_at = datetime.now(timezone.utc)
    # wi_row_id 缺席（組新列、還沒存檔）→ 沒有真實 WiRow 可指，不寫快照（契約 §6）。
    if wi_row_id is not None:
        await _upsert_suggestion(
            session,
            wi_row_id=wi_row_id,
            from_vocab_id=from_vocab_id,
            to_vocab_id=to_vocab_id,
            result=result,
            queried_at=queried_at,
            actor=actor,
        )

    return {
        "available": True,
        "distance_cm": result.distance_cm,
        "horizontal_cm": result.horizontal_cm,
        "vertical_cm": result.vertical_cm,
        "provisional": result.provisional,
        "measure_from_mode": result.measure_from_mode,
        "warnings": result.warnings,
        "queried_at": queried_at.isoformat(),
    }


async def _upsert_suggestion(
    session: AsyncSession,
    *,
    wi_row_id: UUID,
    from_vocab_id: UUID,
    to_vocab_id: UUID,
    result: dsx_client.DsxDistanceResult,
    queried_at: datetime,
    actor: str | None,
) -> WiRowDsxSuggestion:
    existing = (
        await session.execute(
            select(WiRowDsxSuggestion).where(
                WiRowDsxSuggestion.wi_row_id == wi_row_id,
                WiRowDsxSuggestion.a_slot_key == A_SLOT_KEY,
            )
        )
    ).scalar_one_or_none()
    distance_dec = Decimal(str(result.distance_cm))
    if existing is None:
        row = WiRowDsxSuggestion(
            id=uuid.uuid4(),
            wi_row_id=wi_row_id,
            a_slot_key=A_SLOT_KEY,
            from_vocab_id=from_vocab_id,
            to_vocab_id=to_vocab_id,
            raw_distance_cm=distance_dec,
            dsx_response=result.raw,
            queried_at=queried_at,
            created_by=actor,
            updated_by=actor,
        )
        session.add(row)
    else:
        existing.from_vocab_id = from_vocab_id
        existing.to_vocab_id = to_vocab_id
        existing.raw_distance_cm = distance_dec
        existing.dsx_response = result.raw
        existing.queried_at = queried_at
        existing.updated_by = actor
        existing.updated_at = datetime.now(timezone.utc)
        row = existing
    await session.flush()
    return row
