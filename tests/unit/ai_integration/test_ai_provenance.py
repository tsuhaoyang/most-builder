"""ai_integration.provenance：落 DB／回 API 前的鍵 allow-list（ADR-037 D7）。"""
from __future__ import annotations

import ast
import pathlib

import pytest

from ddm_v2.ai_integration.provenance import (
    AI_SERVICE_KEYS,
    ALLOWED_KEYS,
    MAX_DROPPED,
    MAX_IDENT_LEN,
    MAX_MOTION_LABELS,
    MAX_TEXT_LEN,
    MOST_OWNED_KEYS,
    sanitize_ai_service_provenance,
    validate_provenance,
)

pytestmark = pytest.mark.unit

SECRETS = ["api_key", "X-AI-Service-Key", "employee_no", "user_id", "wi_statement", "raw_text", "error_message", "authorization"]


def test_only_allow_listed_scalar_keys_survive():
    raw = {"run_id": "r1", "model_served": "m", "attempts": 2, "latency_ms": 12.5, "prompt_version": None,
           **{k: "x" for k in SECRETS}}
    clean, dropped = sanitize_ai_service_provenance(raw)
    assert clean == {"run_id": "r1", "model_served": "m", "attempts": 2, "latency_ms": 12.5, "prompt_version": None}
    assert sorted(dropped) == sorted(SECRETS)


def test_oversized_strings_and_booleans_are_dropped():
    clean, dropped = sanitize_ai_service_provenance(
        {"run_id": "x" * (MAX_IDENT_LEN + 1), "model_served": "y" * MAX_IDENT_LEN, "attempts": True}
    )
    assert clean == {"model_served": "y" * MAX_IDENT_LEN} and sorted(dropped) == ["attempts", "run_id"]


@pytest.mark.parametrize("bad", ["<script>alert(1)</script>", "a b", "line\nbreak", "ctl\x07", "中文", "a;b", ""])
def test_strings_that_are_not_identifier_characters_are_dropped(bad):
    clean, dropped = sanitize_ai_service_provenance({"model_served": bad, "run_id": "ok-1"})
    assert clean == {"run_id": "ok-1"} and dropped == ["model_served"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_dropped_because_jsonb_cannot_hold_them(bad):
    clean, dropped = sanitize_ai_service_provenance({"latency_ms": bad, "attempts": 1})
    assert clean == {"attempts": 1} and dropped == ["latency_ms"]


def test_most_owned_keys_cannot_be_smuggled_in_from_the_external_side():
    clean, dropped = sanitize_ai_service_provenance({"motion_labels": [{"sub_activity": "x"}], "dropped": ["a1:b4"]})
    assert clean == {} and sorted(dropped) == ["dropped", "motion_labels"]


def test_none_and_empty_inputs_are_fine():
    assert sanitize_ai_service_provenance(None) == ({}, [])
    assert sanitize_ai_service_provenance({}) == ({}, [])


def test_dropped_key_names_are_length_capped():
    _, dropped = sanitize_ai_service_provenance({"k" * 500: "v"})
    assert len(dropped[0]) == 64


def test_validate_accepts_a_well_formed_provenance():
    validate_provenance({"run_id": "r", "motion_labels": [{"action_id": "a1", "sub_activity": "s", "object_text": "o",
                                                           "hand_hint": None}], "dropped": ["a1:b4"]})
    validate_provenance({})


@pytest.mark.parametrize("key", SECRETS)
def test_validate_rejects_any_key_outside_the_allow_list(key):
    with pytest.raises(ValueError, match="allow-list"):
        validate_provenance({"run_id": "r", key: "x"})


@pytest.mark.parametrize(
    "bad",
    [
        {"motion_labels": "not a list"},
        {"motion_labels": [{"action_id": "a1", "secret": "x"}]},
        {"motion_labels": [{"action_id": "a1", "sub_activity": 5}]},
        {"motion_labels": ["str"]},
        {"dropped": "a1:b4"},
        {"dropped": [1]},
    ],
)
def test_validate_rejects_malformed_most_owned_fields(bad):
    with pytest.raises(ValueError):
        validate_provenance(bad)


def test_the_allow_list_has_no_secret_looking_keys_and_matches_what_the_adapter_and_guard_emit():
    assert ALLOWED_KEYS == AI_SERVICE_KEYS | MOST_OWNED_KEYS
    assert not {k for k in ALLOWED_KEYS if any(w in k for w in ("key", "secret", "token", "password", "employee", "user", "text", "message"))} - {"object_text"}
    root = pathlib.Path(__file__).resolve().parents[3] / "src" / "ddm_v2" / "ai_integration"
    emitted: set[str] = set()
    for name in ("adapter.py", "guard.py"):
        for node in ast.walk(ast.parse((root / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "provenance" and isinstance(node.value, ast.Dict):
                emitted |= {k.value for k in node.value.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    assert emitted, "掃不到 adapter／guard 的 provenance 字面量：掃描器壞了"
    assert emitted <= AI_SERVICE_KEYS, f"adapter／guard 輸出了不在 allow-list 的鍵：{sorted(emitted - AI_SERVICE_KEYS)}"


LABEL = {"action_id": "a1", "sub_activity": "s", "object_text": "o", "hand_hint": "LH"}


@pytest.mark.parametrize(
    "bad",
    [
        {"motion_labels": [{**LABEL, "hand_hint": "XX"}]},
        {"motion_labels": [{**LABEL, "action_id": "b1"}]},
        {"motion_labels": [{**LABEL, "action_id": "a1; DROP"}]},
        {"motion_labels": [{**LABEL, "sub_activity": "x" * (MAX_TEXT_LEN + 1)}]},
        {"motion_labels": [LABEL] * (MAX_MOTION_LABELS + 1)},
        {"dropped": ["a1:b4"] * (MAX_DROPPED + 1)},
        {"dropped": ["not-a-slot"]},
        {"dropped": ["a1:<b>"]},
        {"run_id": "has space"},
        {"latency_ms": float("nan")},
    ],
)
def test_validate_rejects_dirty_values_even_when_the_keys_are_allowed(bad):
    with pytest.raises(ValueError):
        validate_provenance(bad)


def test_validate_accepts_the_largest_legitimate_shape():
    validate_provenance({
        "motion_labels": [{**LABEL, "action_id": f"a{i}"} for i in range(1, MAX_MOTION_LABELS + 1)],
        "dropped": [f"a{i}:a0.magnitude_hint" for i in range(1, 11)],
        "run_id": "run-1", "attempts": 3, "latency_ms": 12.5,
    })
