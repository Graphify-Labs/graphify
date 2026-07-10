"""Tests for graphify.skill_migrations — version math + migration selection."""
from __future__ import annotations

from graphify.skill_migrations import (
    MIGRATIONS,
    applicable_migrations,
    compare_versions,
    drift_state,
    parse_version,
)


def test_parse_version_basic():
    assert parse_version("0.9.2") == (0, 9, 2)
    assert parse_version("1.2.0") == (1, 2, 0)


def test_parse_version_handles_unknown_and_empty():
    assert parse_version("unknown") == (0,)
    assert parse_version("") == (0,)


def test_parse_version_strips_prerelease_tags():
    assert parse_version("1.2.0rc1") == (1, 2, 0)


def test_compare_versions_numeric_not_lexical():
    # 0.10 > 0.9 numerically (a string compare would get this wrong).
    assert compare_versions("0.10.0", "0.9.9") == 1
    assert compare_versions("0.9.0", "0.9.2") == -1


def test_compare_versions_pads_lengths():
    assert compare_versions("0.9", "0.9.0") == 0


def test_drift_state():
    assert drift_state("0.9.0", "0.9.0") == "current"
    assert drift_state("0.9.0", "0.9.2") == "behind"
    assert drift_state("0.9.2", "0.9.0") == "ahead"


def test_applicable_migrations_current_is_empty():
    # Installed == package: nothing to apply.
    assert applicable_migrations("0.9.0", "0.9.0") == []


def test_applicable_migrations_fresh_install_includes_baseline():
    # unknown -> 0.9.0 should surface the baseline migration.
    got = applicable_migrations("unknown", "0.9.0")
    assert [m.version for m in got] == ["0.9.0"]


def test_applicable_migrations_ahead_is_empty():
    # Installed skill newer than package: nothing to migrate *to*.
    assert applicable_migrations("0.9.2", "0.9.0") == []


def test_migrations_registry_is_sorted():
    versions = [m.version for m in MIGRATIONS]
    ordered = sorted(versions, key=parse_version)
    assert versions == ordered
