"""Tests for graphify.paths — the shared test-path classifier (#1553)."""

from __future__ import annotations

import json

import pytest

from graphify.paths import (
    _is_test_path,
    disambiguate_ambiguous_candidates,
    query_config_defaults,
)


@pytest.mark.parametrize(
    "path",
    [
        # test dir segments
        "tests/foo.py",
        "src/tests/foo.py",
        "test/foo.go",
        "spec/foo.rb",
        "specs/foo.rb",
        "app/__tests__/foo.js",
        "a/b/TESTS/foo.py",  # case-insensitive segment
        # test filename conventions
        "src/test_service.py",
        "pkg/service_test.go",
        "src/service.test.ts",
        "src/service.spec.ts",
        "src/service_spec.rb",
        "ps/Module.Tests.ps1",
        "java/FooTest.java",
        "java/FooTests.java",
        "cs/FooTests.cs",
        # windows separators
        "src\\tests\\foo.py",
        "src\\service_test.py",
    ],
)
def test_is_test_path_positive(path: str) -> None:
    assert _is_test_path(path) is True, path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "latest.py",
        "contest.py",
        "src/contest.py",
        "src/greatest/x.py",
        "src/service.py",
        "lib/helper.go",
        "src/attestation.py",  # "test" only as substring, not a segment
        "src/testimony.py",  # filename starts with "test" but no underscore
        "src/contest/x.py",  # "contest" is not "test"
        "src/greatest.cs",  # ends with "test" but not "Tests.cs"
        "src/protest.java",  # not "*Test.java"
        "config/manifest.json",
    ],
)
def test_is_test_path_negative(path: str) -> None:
    assert _is_test_path(path) is False, path


def test_disambiguate_drops_test_candidate_for_nontest_call_site() -> None:
    winner = disambiguate_ambiguous_candidates(
        ["src", "mock"],
        {"src": "src/service.py", "mock": "tests/test_service.py"},
        "src/caller.py",
    )
    assert winner == "src"


def test_disambiguate_bails_on_two_nontest_candidates() -> None:
    winner = disambiguate_ambiguous_candidates(
        ["a", "b"],
        {"a": "alpha/a.py", "b": "beta/b.py"},
        "pkg/caller.py",
    )
    assert winner is None


def test_disambiguate_test_call_site_prefers_test_local() -> None:
    winner = disambiguate_ambiguous_candidates(
        ["src", "local"],
        {"src": "src/service.py", "local": "tests/test_service.py"},
        "tests/test_service.py",
    )
    assert winner == "local"


def test_disambiguate_path_proximity_same_dir() -> None:
    # Two non-test candidates; the one in the call site's directory wins.
    winner = disambiguate_ambiguous_candidates(
        ["near", "far"],
        {"near": "pkg/a/service.py", "far": "pkg/b/service.py"},
        "pkg/a/caller.py",
    )
    assert winner == "near"


# --- query_config_defaults (per-project config.json, #1654) -----------------


def _write_config(tmp_path, data) -> None:
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")


def test_query_config_defaults_nested_query_object(tmp_path) -> None:
    _write_config(tmp_path, {"query": {"default_budget": 4000, "default_depth": 3}})
    assert query_config_defaults(tmp_path / "config.json") == {"budget": 4000, "depth": 3}


def test_query_config_defaults_flat_keys(tmp_path) -> None:
    _write_config(tmp_path, {"budget": 1234, "depth": 5})
    assert query_config_defaults(tmp_path / "config.json") == {"budget": 1234, "depth": 5}


def test_query_config_defaults_partial(tmp_path) -> None:
    _write_config(tmp_path, {"query": {"default_depth": 4}})
    assert query_config_defaults(tmp_path / "config.json") == {"depth": 4}


def test_query_config_defaults_nested_wins_over_flat(tmp_path) -> None:
    _write_config(tmp_path, {"query": {"default_budget": 4000}, "budget": 9999})
    assert query_config_defaults(tmp_path / "config.json") == {"budget": 4000}


def test_query_config_defaults_missing_file(tmp_path) -> None:
    assert query_config_defaults(tmp_path / "does-not-exist.json") == {}


def test_query_config_defaults_malformed_json(tmp_path) -> None:
    (tmp_path / "config.json").write_text("{not valid json", encoding="utf-8")
    assert query_config_defaults(tmp_path / "config.json") == {}


def test_query_config_defaults_rejects_bad_values(tmp_path) -> None:
    # non-int, bool, zero, and negative values are all ignored.
    _write_config(
        tmp_path,
        {"query": {"default_budget": "lots", "default_depth": -1}, "budget": True, "depth": 0},
    )
    assert query_config_defaults(tmp_path / "config.json") == {}


def test_query_config_defaults_non_dict_top_level(tmp_path) -> None:
    (tmp_path / "config.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert query_config_defaults(tmp_path / "config.json") == {}
