"""Policy manifest resolver（R2a / ADR-027 §3）。

R0 尚無完整 precedence；R2a 對**新建** worksheet 採明確預設：
`(code=MODELING_FACTORY|LEVEL_FACTORY, version_no=1, status=published)`。
禁止 `MAX(version_no)` / `created_at DESC` 隱式選版；缺預設 → fail closed。

ADR-038 W7b：建模政策的預設改由 `modeling_policy_defaults` **明確指定**（admin 發布新的距離設定時指過去）；
沒有指定列時沿用 V1（與原行為相同）。距離設定放在 `policy_json["distance"]`；版本沒有這段時用
`DEFAULT_DISTANCE_SETTINGS`（Howard 2026-11-23：門檻 70 cm、人端偏移肩高 140 cm），出處標 `default`。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ddm_v2.models.v2.policy import LevelPolicyVersion, ModelingPolicyVersion

# Stable family codes（spec §8.2 / §9.2）；顯示名可為 *_V1
MODELING_FACTORY_CODE = "MODELING_FACTORY"
LEVEL_FACTORY_CODE = "LEVEL_FACTORY"
FACTORY_DEFAULT_VERSION_NO = 1

# 固定 UUID（migration seed / 測試對齊）
MODELING_FACTORY_V1_ID = UUID("a1000000-0000-4000-8000-000000000001")
LEVEL_FACTORY_V1_ID = UUID("a2000000-0000-4000-8000-000000000001")

MODELING_SCHEMA_VERSION = "modeling-policy-v1"
COMPILER_CONTRACT_VERSION = "compiler-v1"
LEVEL_SCHEMA_VERSION = "level-input-v1"
VALIDATOR_REVISION = "ddm_v2.most_engine.level@r1-r9-v1"
OUTPUT_CONTRACT_VERSION = "lb-output-v1"

MODELING_POLICY_JSON_V1: dict[str, Any] = {
    "quantity_policy": "conservative",
    "inspect_merge_into_prior_cm": False,
    "auto_generate_release_return": False,
    "simo_auto_assign": False,
}

LEVEL_CONFIG_JSON_V1: dict[str, Any] = {
    "rules": "r1-r9-canonical",
    "notes": "現行 most_engine.level；尚未 DSL 化",
}


class NoDefaultPolicy(Exception):
    """設定錯誤：找不到核可的 published factory default policy。"""


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def content_hash_for(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def modeling_v1_content_hash() -> str:
    return content_hash_for(
        {
            "schema_version": MODELING_SCHEMA_VERSION,
            "compiler_contract_version": COMPILER_CONTRACT_VERSION,
            "policy_json": MODELING_POLICY_JSON_V1,
        }
    )


def level_v1_content_hash() -> str:
    return content_hash_for(
        {
            "schema_version": LEVEL_SCHEMA_VERSION,
            "validator_revision": VALIDATOR_REVISION,
            "output_contract_version": OUTPUT_CONTRACT_VERSION,
            "config_json": LEVEL_CONFIG_JSON_V1,
        }
    )


async def get_default_modeling_policy(session: AsyncSession) -> ModelingPolicyVersion:
    from ddm_v2.models.v2.distance import ModelingPolicyDefault

    pinned = await session.get(ModelingPolicyDefault, MODELING_FACTORY_CODE)
    if pinned is not None:
        row = await session.get(ModelingPolicyVersion, pinned.version_id)
        if row is None or row.status != "published":
            raise NoDefaultPolicy(f"指定的 modeling policy 預設不存在或未發布：{pinned.version_id}")
        return row
    row = (
        await session.execute(
            select(ModelingPolicyVersion).where(
                ModelingPolicyVersion.code == MODELING_FACTORY_CODE,
                ModelingPolicyVersion.version_no == FACTORY_DEFAULT_VERSION_NO,
                ModelingPolicyVersion.status == "published",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NoDefaultPolicy(
            f"缺少 published modeling policy：{MODELING_FACTORY_CODE}@{FACTORY_DEFAULT_VERSION_NO}"
        )
    return row


async def get_default_level_policy(session: AsyncSession) -> LevelPolicyVersion:
    row = (
        await session.execute(
            select(LevelPolicyVersion).where(
                LevelPolicyVersion.code == LEVEL_FACTORY_CODE,
                LevelPolicyVersion.version_no == FACTORY_DEFAULT_VERSION_NO,
                LevelPolicyVersion.status == "published",
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise NoDefaultPolicy(
            f"缺少 published level policy：{LEVEL_FACTORY_CODE}@{FACTORY_DEFAULT_VERSION_NO}"
        )
    return row


def modeling_summary(row: ModelingPolicyVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "code": row.code,
        "version_no": row.version_no,
        "name": row.name,
        "status": row.status,
    }


def level_summary(row: LevelPolicyVersion | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "code": row.code,
        "version_no": row.version_no,
        "name": row.name,
        "status": row.status,
        "validator_revision": row.validator_revision,
        "output_contract_version": row.output_contract_version,
    }


# ════════ 距離設定（ADR-038 D5.6 (b)，W7b）════════

# ⚠️ 沒有 `distance` 段的政策版本（含 V1）靠這組常數；改它等於悄悄改變既有工時表的距離算法。
# 不得修改——要換值請由 admin 發布新的政策版本（publish_distance_settings）。測試鎖住這組值。
DEFAULT_DISTANCE_SETTINGS: dict[str, Any] = {
    "reach_foot_threshold_cm": 70.0,
    "person_offset_cm": [0.0, 0.0, 140.0],
}


def distance_settings(policy: ModelingPolicyVersion | None) -> tuple[dict[str, Any], str]:
    """回傳 (設定, 出處)。出處：`policy`＝該版本有 `distance` 段；`default`＝沒有，用預設值。"""
    raw = ((policy.policy_json or {}).get("distance") if policy is not None else None) or None
    if not raw:
        return dict(DEFAULT_DISTANCE_SETTINGS), "default"
    return {
        "reach_foot_threshold_cm": float(raw["reach_foot_threshold_cm"]),
        "person_offset_cm": [float(v) for v in raw["person_offset_cm"]],
    }, "policy"


async def publish_distance_settings(
    session: AsyncSession, *, reach_foot_threshold_cm: float, person_offset_cm: list[float], actor: str
) -> ModelingPolicyVersion:
    """以目前的預設版本為底，換上新的距離設定，發布成 MODELING_FACTORY 的下一版，並把預設明確指過去。

    既有工時表記住自己的版本，不受影響；之後新建的工時表才用新版本（ADR-038 D5.6 (b)）。
    """
    from datetime import datetime, timezone

    from sqlalchemy import func

    # 交易級 advisory lock：兩個 admin 同時發布（含預設列還不存在時）依序執行，不會拿到同一個版本號
    from sqlalchemy import text as _text

    from ddm_v2.models.v2.distance import ModelingPolicyDefault

    await session.execute(_text("SELECT pg_advisory_xact_lock(hashtext('modeling_policy_defaults'))"))
    pinned = (await session.execute(
        select(ModelingPolicyDefault).where(ModelingPolicyDefault.code == MODELING_FACTORY_CODE).with_for_update()
    )).scalar_one_or_none()
    base = await get_default_modeling_policy(session)
    next_no = (await session.execute(
        select(func.max(ModelingPolicyVersion.version_no)).where(ModelingPolicyVersion.code == MODELING_FACTORY_CODE)
    )).scalar_one() + 1
    policy_json = {
        **(base.policy_json or {}),
        "distance": {
            "reach_foot_threshold_cm": float(reach_foot_threshold_cm),
            "person_offset_cm": [float(v) for v in person_offset_cm],
        },
    }
    now = datetime.now(timezone.utc)
    row = ModelingPolicyVersion(
        code=MODELING_FACTORY_CODE, version_no=next_no, name=f"{MODELING_FACTORY_CODE}_V{next_no}",
        status="published", site_id=base.site_id, process_type=base.process_type,
        schema_version=base.schema_version, compiler_contract_version=base.compiler_contract_version,
        policy_json=policy_json,
        content_hash=content_hash_for({
            "schema_version": base.schema_version,
            "compiler_contract_version": base.compiler_contract_version,
            "policy_json": policy_json,
        }),
        created_by=actor, published_by=actor, published_at=now,
    )
    session.add(row)
    await session.flush()
    if pinned is None:
        session.add(ModelingPolicyDefault(code=MODELING_FACTORY_CODE, version_id=row.id, set_by=actor, set_at=now))
    else:
        pinned.version_id = row.id
        pinned.set_by = actor
        pinned.set_at = now
    await session.flush()
    return row
