"""R3a wi-context-v1 schema／hash。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from ddm_v2.schemas.v2.wi_context import (
    WI_CONTEXT_V1,
    context_hash_for,
    validate_context_payload,
)


def test_empty_v1_ok():
    data = validate_context_payload(schema_version=WI_CONTEXT_V1, context_data={})
    assert data["quality_checks"] == []
    assert data["business_tags"] == []
    h1 = context_hash_for(data)
    h2 = context_hash_for(data)
    assert h1 == h2 and len(h1) == 64


def test_reject_unknown_schema_version():
    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_context_payload(schema_version="wi-context-v99", context_data={})


def test_reject_extra_keys():
    with pytest.raises(PydanticValidationError):
        validate_context_payload(
            schema_version=WI_CONTEXT_V1,
            context_data={"tmu": 28, "quality_checks": []},
        )


def test_hash_changes_with_content():
    a = validate_context_payload(
        schema_version=WI_CONTEXT_V1,
        context_data={"safety_notes": ["wear gloves"]},
    )
    b = validate_context_payload(
        schema_version=WI_CONTEXT_V1,
        context_data={"safety_notes": ["no gloves"]},
    )
    assert context_hash_for(a) != context_hash_for(b)
