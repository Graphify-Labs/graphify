"""_source_key memoization: same answers, a fraction of the syscalls (#perf).

``_disambiguate_colliding_node_ids`` computes a source key once per node, per
edge endpoint and per raw_call — tens of thousands of calls for a few hundred
distinct ``source_file`` strings — and each uncached call walked the path
through ``Path.resolve()``'s syscall chain. On a 364-file corpus the pass
spent 15s (34% of a sequential extract) re-resolving identical strings.
"""

import os

import pytest

from graphify.extractors.resolution import _source_key

try:
    from graphify.extractors.resolution import _cached_source_key
except ImportError:  # pre-fix tree: the memoized helper does not exist
    _cached_source_key = None

needs_cache = pytest.mark.skipif(
    _cached_source_key is None, reason="memoized helper not present"
)


def _reference_source_key(source_file, root):
    """The pre-memoization implementation, verbatim."""
    from pathlib import Path

    if not source_file:
        return ""
    source_path = Path(source_file)
    try:
        return str(source_path.resolve().relative_to(root))
    except Exception:
        return str(source_path)


def test_matches_unmemoized_semantics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path.parent

    cases = [
        ("pkg/mod.py", tmp_path),                  # relative, in-root
        (str(tmp_path / "pkg" / "mod.py"), tmp_path),  # absolute, in-root
        (str(outside), tmp_path),                  # out-of-root -> fallback
        ("pkg/ghost.py", tmp_path),                # nonexistent
        ("", tmp_path),                            # empty
    ]
    for source_file, root in cases:
        assert _source_key(source_file, root) == _reference_source_key(
            source_file, root
        ), (source_file, root)


@needs_cache
def test_resolution_happens_once_per_distinct_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _cached_source_key.cache_clear()
    for _ in range(100):
        _source_key("a.py", tmp_path)
    info = _cached_source_key.cache_info()
    assert info.misses == 1 and info.hits == 99, info


@needs_cache
def test_cache_is_cwd_sensitive(tmp_path, monkeypatch):
    """A relative source_file resolves against CWD; a chdir must not replay
    the previous directory's resolution."""
    d1 = tmp_path / "checkout1"
    d2 = tmp_path / "checkout2"
    for d in (d1, d2):
        d.mkdir()
        (d / "mod.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.chdir(d1)
    k1 = _source_key("mod.py", d1)
    monkeypatch.chdir(d2)
    k2 = _source_key("mod.py", d2)
    assert k1 == "mod.py" and k2 == "mod.py"
    # And cross-root: from d2, resolving against d1's root must fall back to
    # the raw path (out-of-root), exactly as the unmemoized code did.
    assert _source_key("mod.py", d1) == _reference_source_key("mod.py", d1)
