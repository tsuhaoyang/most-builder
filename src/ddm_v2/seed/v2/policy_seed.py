"""Seed MODELING_FACTORY / LEVEL_FACTORY v1（R2a）。idempotent by (code, version_no)。

定位＝**補種**：migration `v2_0030` 在建表時已 INSERT 這兩列（`ON CONFLICT DO NOTHING`），
所以正常環境跑到這裡都是「已存在 → 原樣取回」。真正會走建列分支的是
「表存在但列被清掉」或以 `Base.metadata.create_all` 起的測試庫。

⚠️ 這三個函式**必須是 async**：`session` 是 `AsyncSession`，`AsyncSession.get()` 回 coroutine。
曾經宣告成同步 `def` 而直接用 `session.get(...)` 的結果是——coroutine 恆為真 →
`existing is not None` 永遠成立 → **從不建列、回傳的是 coroutine 而非 ORM 物件**，
呼叫端一取 `.name` 就 `AttributeError`（CI 的「Migrate + seed」步驟因此長期紅燈）。
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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


async def seed_modeling_policy_factory_v1(session: AsyncSession) -> ModelingPolicyVersion:
    existing = await session.get(ModelingPolicyVersion, MODELING_FACTORY_V1_ID)
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


async def seed_level_policy_factory_v1(session: AsyncSession) -> LevelPolicyVersion:
    existing = await session.get(LevelPolicyVersion, LEVEL_FACTORY_V1_ID)
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


async def seed_policy_factory_v1(
    session: AsyncSession,
) -> tuple[ModelingPolicyVersion, LevelPolicyVersion]:
    """兩份 manifest 一起補種。順序執行（同一條連線，不得 gather）。"""
    return (
        await seed_modeling_policy_factory_v1(session),
        await seed_level_policy_factory_v1(session),
    )


# 供測試／診斷：固定 id
FACTORY_V1_IDS: dict[str, UUID] = {
    "modeling": MODELING_FACTORY_V1_ID,
    "level": LEVEL_FACTORY_V1_ID,
}
