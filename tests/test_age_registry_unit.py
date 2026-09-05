"""Tier-1 (pure, DB-free) unit tests for graphify.age_registry.

See docs/AGE_PLAN.md "Testing strategy": identity/ownership resolution is
pure and DB-free by design, so it is pinned here in default CI. Schema
creation and registration (tier 2, live Postgres) are in
tests/test_age_registry_integration.py.
"""
from __future__ import annotations

import uuid

import pytest

from graphify import age_registry as reg


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("git@github.com:owner/repo.git", "github.com/owner/repo"),
        ("https://github.com/owner/repo.git", "github.com/owner/repo"),
        ("https://github.com/owner/repo", "github.com/owner/repo"),
        ("https://user:token@github.com/owner/repo.git", "github.com/owner/repo"),
        ("git@github.com:owner/repo", "github.com/owner/repo"),
        ("https://gitlab.example.com/group/sub/repo.git", "gitlab.example.com/group/sub/repo"),
        ("HTTPS://GitHub.com/Owner/Repo.git", "github.com/owner/repo"),
    ],
)
def test_normalize_remote_url_ssh_and_https_agree(raw, expected):
    assert reg.normalize_remote_url(raw) == expected


def test_normalize_remote_url_ssh_and_https_of_same_repo_match():
    ssh = reg.normalize_remote_url("git@github.com:owner/repo.git")
    https = reg.normalize_remote_url("https://github.com/owner/repo.git")
    assert ssh == https


def test_repository_id_for_is_deterministic():
    a = reg.repository_id_for("git@github.com:owner/repo.git")
    b = reg.repository_id_for("https://github.com/owner/repo.git")
    assert a == b
    # A valid UUID string.
    assert uuid.UUID(a)


def test_repository_id_for_differs_across_repos():
    a = reg.repository_id_for("https://github.com/owner/repo-a.git")
    b = reg.repository_id_for("https://github.com/owner/repo-b.git")
    assert a != b


def test_resolve_owner_prefers_explicit():
    assert reg.resolve_owner(
        explicit="alice", remote_url="https://github.com/bob/repo.git", git_email="carol@x.com"
    ) == "alice"


def test_resolve_owner_falls_back_to_remote_url_owner_segment():
    assert reg.resolve_owner(
        remote_url="https://github.com/bob/repo.git", git_email="carol@x.com"
    ) == "bob"


def test_resolve_owner_falls_back_to_git_email():
    assert reg.resolve_owner(git_email="carol@x.com") == "carol@x.com"


def test_resolve_owner_none_when_nothing_available():
    assert reg.resolve_owner() is None


def test_graphify_package_version_returns_a_string():
    assert isinstance(reg.graphify_package_version(), str)
    assert reg.graphify_package_version() != ""


def test_schema_version_is_pinned_string():
    assert isinstance(reg.SCHEMA_VERSION, str)
