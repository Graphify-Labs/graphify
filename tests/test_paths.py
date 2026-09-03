"""Tests for graphify.paths — the shared test-path classifier (#1553)."""

from __future__ import annotations

import pytest

from graphify.paths import (
    _is_test_path,
    disambiguate_ambiguous_candidates,
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


# --- cross-platform absoluteness for STORED paths ---------------------------
# Path.is_absolute()/os.path.isabs() answer for the host OS, which is the wrong
# question for a path read out of graph.json: graphs are built in Docker/CI and
# updated on Windows (and vice versa), so the string in hand may follow the
# other platform's rules. Getting this wrong bakes an on-disk path into node IDs
# (#2197, #1789) or joins an absolute path under the scan root.

@pytest.mark.parametrize("path", [
    "/home/ci/build/repo/docs/api/README.md",   # POSIX absolute
    "/",                                        # POSIX root
    "C:/Users/u/repo/docs/a.md",                # Windows drive, forward slashes
    r"C:\Users\u\repo\docs\a.md",               # Windows drive, backslashes
    r"\\server\share\docs\a.md",                # UNC
    "//server/share/docs/a.md",                 # UNC, forward slashes
])
def test_is_absolute_any_platform_accepts_both_conventions(path):
    from graphify.paths import is_absolute_any_platform
    assert is_absolute_any_platform(path) is True, (
        f"{path!r} is absolute on some platform and must be treated as such"
    )


@pytest.mark.parametrize("path", [
    "docs/api/README.md",
    r"docs\api\README.md",
    "README.md",
    ".",
    "",
    None,
    r"\foo",         # Windows root-relative (no drive) — not absolute anywhere
])
def test_is_absolute_any_platform_rejects_relative(path):
    from graphify.paths import is_absolute_any_platform
    assert is_absolute_any_platform(path) is False


def test_is_absolute_any_platform_is_host_independent():
    """The whole point: the answer must not depend on which OS is running.

    Both spellings are absolute somewhere, so both must return True on every
    host — that is exactly what Path.is_absolute() fails to do.
    """
    from graphify.paths import is_absolute_any_platform
    assert is_absolute_any_platform("/home/ci/x.md")
    assert is_absolute_any_platform("C:/Users/u/x.md")
