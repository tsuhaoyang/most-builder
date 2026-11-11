"""Policy manifest resolver（R2a / ADR-027 §3）。

R0 尚無完整 precedence；R2a 對**新建** worksheet 採明確預設：
`(code=MODELING_FACTORY|LEVEL_FACTORY, version_no=1, status=published)`。
禁止 `MAX(version_no)` / `created_at DESC` 隱式選版；缺預設 → fail closed。
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
