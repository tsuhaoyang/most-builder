"""Seed MODELING_FACTORY / LEVEL_FACTORY v1（R2a）。idempotent by (code, version_no)。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ddm_v2.models.v2.policy import LevelPolicyVersion, ModelingPolicyVersion
from ddm_v2.services.v2.policy_service import (
    COMPILER_CONTRACT_VERSION,
    FACTORY_DEFAULT_VERSION_NO,
    LEVEL_CONFIG_JSON_V1,
    LEVEL_FACTORY_CODE,
    LEVEL_FACTORY_V1_ID,
    LEVEL_SCHEMA_VERSION,
    MODELING_FACTORY_CODE,
    MODELING_FACTORY_V1_ID,
    MODELING_POLICY_JSON_V1,
    MODELING_SCHEMA_VERSION,
    OUTPUT_CONTRACT_VERSION,
    VALIDATOR_REVISION,
    level_v1_content_hash,
    modeling_v1_content_hash,
)


def seed_modeling_policy_factory_v1(session: Any) -> ModelingPolicyVersion:
    existing = session.get(ModelingPolicyVersion, MODELING_FACTORY_V1_ID)
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    row = ModelingPolicyVersion(
        id=MODELING_FACTORY_V1_ID,
        code=MODELING_FACTORY_CODE,
        version_no=FACTORY_DEFAULT_VERSION_NO,
        name="MODELING_FACTORY_V1",
        status="published",
        site_id=None,
        process_type=None,
        schema_version=MODELING_SCHEMA_VERSION,
        compiler_contract_version=COMPILER_CONTRACT_VERSION,
        policy_json=dict(MODELING_POLICY_JSON_V1),
        content_hash=modeling_v1_content_hash(),
        created_by="system",
        published_by="system",
        published_at=now,
    )
    session.add(row)
    return row


def seed_level_policy_factory_v1(session: Any) -> LevelPolicyVersion:
    existing = session.get(LevelPolicyVersion, LEVEL_FACTORY_V1_ID)
    if existing is not None:
        return existing
    now = datetime.now(timezone.utc)
    row = LevelPolicyVersion(
        id=LEVEL_FACTORY_V1_ID,
        code=LEVEL_FACTORY_CODE,
        version_no=FACTORY_DEFAULT_VERSION_NO,
        name="LEVEL_FACTORY_V1",
        status="published",
        schema_version=LEVEL_SCHEMA_VERSION,
        validator_revision=VALIDATOR_REVISION,
        output_contract_version=OUTPUT_CONTRACT_VERSION,
        config_json=dict(LEVEL_CONFIG_JSON_V1),
        content_hash=level_v1_content_hash(),
        created_by="system",
        published_by="system",
        published_at=now,
    )
    session.add(row)
    return row


def seed_policy_factory_v1(session: Any) -> tuple[ModelingPolicyVersion, LevelPolicyVersion]:
    return seed_modeling_policy_factory_v1(session), seed_level_policy_factory_v1(session)


# 供測試／診斷：固定 id
FACTORY_V1_IDS: dict[str, UUID] = {
    "modeling": MODELING_FACTORY_V1_ID,
    "level": LEVEL_FACTORY_V1_ID,
}
