"""R2a policy manifest：hash 穩定 + factory constants。"""
from __future__ import annotations

from ddm_v2.services.v2.policy_service import (
    FACTORY_DEFAULT_VERSION_NO,
    LEVEL_FACTORY_CODE,
    LEVEL_FACTORY_V1_ID,
    MODELING_FACTORY_CODE,
    MODELING_FACTORY_V1_ID,
    level_v1_content_hash,
    modeling_v1_content_hash,
)


def test_factory_identity_constants():
    assert MODELING_FACTORY_CODE == "MODELING_FACTORY"
    assert LEVEL_FACTORY_CODE == "LEVEL_FACTORY"
    assert FACTORY_DEFAULT_VERSION_NO == 1
    assert str(MODELING_FACTORY_V1_ID) == "a1000000-0000-4000-8000-000000000001"
    assert str(LEVEL_FACTORY_V1_ID) == "a2000000-0000-4000-8000-000000000001"


def test_v1_content_hashes_stable():
    """與 migration v2_0030 硬編碼 hash 鎖定；改 V1 payload 必須同步改 migration。"""
    assert modeling_v1_content_hash() == (
        "a76b79a92cf0b2072c6cb91918d8b1b3736522b383f60d7929f1bf2b0f4132a5"
    )
    assert level_v1_content_hash() == (
        "6e214aee3cfc02bbb83732f235588b4ad474b17064b9809fd9fbd9a0662c39aa"
    )
