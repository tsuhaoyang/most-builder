"""Unit tests for v2_0016 role rename migration logic (no DB required).

Tests the CASE transformation that would be performed by the PostgreSQL
ARRAY(SELECT CASE ... FROM unnest(roles) x) expression.
"""


def transform_roles(roles: list[str]) -> list[str]:
    """Mirrors the SQL: CASE WHEN x='IE' THEN 'analyst' WHEN x='manager' THEN 'approver' ELSE x END."""
    mapping = {"IE": "analyst", "manager": "approver"}
    return [mapping.get(r, r) for r in roles]


def downgrade_roles(roles: list[str]) -> list[str]:
    reverse = {"analyst": "IE", "approver": "manager"}
    return [reverse.get(r, r) for r in roles]


def test_ie_becomes_analyst():
    assert transform_roles(["IE"]) == ["analyst"]


def test_manager_becomes_approver():
    assert transform_roles(["manager"]) == ["approver"]


def test_admin_unchanged():
    assert transform_roles(["admin"]) == ["admin"]


def test_viewer_unchanged():
    assert transform_roles(["viewer"]) == ["viewer"]


def test_mixed_roles_ie_admin():
    assert transform_roles(["IE", "admin"]) == ["analyst", "admin"]


def test_mixed_roles_manager_admin():
    assert transform_roles(["manager", "admin"]) == ["approver", "admin"]


def test_all_roles():
    assert transform_roles(["IE", "manager", "admin"]) == ["analyst", "approver", "admin"]


def test_empty_roles():
    assert transform_roles([]) == []


def test_downgrade_analyst_to_ie():
    assert downgrade_roles(["analyst"]) == ["IE"]


def test_downgrade_approver_to_manager():
    assert downgrade_roles(["approver"]) == ["manager"]


def test_downgrade_symmetric():
    original = ["IE", "manager", "admin"]
    upgraded = transform_roles(original)
    assert downgrade_roles(upgraded) == original
