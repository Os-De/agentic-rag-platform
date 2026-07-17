"""RBAC matrix — mirrors architecture doc §6. If this table changes, change both."""

import pytest

from app.auth.deps import ROLE_RANK, has_permission


def test_hierarchy_order():
    assert ROLE_RANK["viewer"] < ROLE_RANK["engineer"] < ROLE_RANK["admin"]


@pytest.mark.parametrize(
    ("user_role", "min_role", "allowed"),
    [
        ("viewer", "viewer", True),
        ("viewer", "engineer", False),   # viewers cannot ingest
        ("viewer", "admin", False),
        ("engineer", "viewer", True),
        ("engineer", "engineer", True),
        ("engineer", "admin", False),    # engineers cannot manage users
        ("admin", "viewer", True),
        ("admin", "engineer", True),
        ("admin", "admin", True),
        ("unknown-role", "viewer", False),
    ],
)
def test_permission_matrix(user_role, min_role, allowed):
    assert has_permission(user_role, min_role) is allowed
