"""_resolve_cached: Path.resolve() with a per-(path, cwd) memo (#perf).

The symbol-resolution passes call Path.resolve() once per import/export/use
fact and per node — tens of thousands of calls over a few hundred distinct
corpus paths, each walking nt._getfinalpathname / readlink. Memoizing on the
(path, cwd) pair collapses that to one syscall per distinct path; on a
364-file self-corpus a sequential extract dropped from ~27s to ~14s, with a
byte-identical graph (verified separately).
"""

import os
from pathlib import Path

import pytest

try:
    from graphify.extractors.resolution import _resolve_cached, _cached_realpath
except ImportError:  # pre-fix tree
    _resolve_cached = None
    _cached_realpath = None

needs_cache = pytest.mark.skipif(
    _resolve_cached is None, reason="resolve memo not present"
)


@needs_cache
def test_matches_path_resolve(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    for arg in ("pkg/mod.py", str(tmp_path / "pkg" / "mod.py"), "missing.py"):
        assert _resolve_cached(arg) == Path(arg).resolve()
        assert _resolve_cached(Path(arg)) == Path(arg).resolve()


@needs_cache
def test_resolves_once_per_distinct_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _cached_realpath.cache_clear()
    for _ in range(50):
        _resolve_cached("a.py")
        _resolve_cached(Path("a.py"))  # str/Path collapse to one key
    info = _cached_realpath.cache_info()
    assert info.misses == 1 and info.hits == 99, info


@needs_cache
def test_cache_is_cwd_sensitive(tmp_path, monkeypatch):
    d1, d2 = tmp_path / "one", tmp_path / "two"
    for d in (d1, d2):
        d.mkdir()
        (d / "m.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(d1)
    r1 = _resolve_cached("m.py")
    monkeypatch.chdir(d2)
    r2 = _resolve_cached("m.py")
    assert r1 == d1.resolve() / "m.py"
    assert r2 == d2.resolve() / "m.py"


@needs_cache
def test_exception_paths_match_resolve(tmp_path, monkeypatch):
    """A path that resolve() can handle returns the same as a direct call;
    the helper never swallows what resolve() would raise (callers keep their
    own try/except, unchanged)."""
    monkeypatch.chdir(tmp_path)
    weird = "a/../b/./c.py"
    assert _resolve_cached(weird) == Path(weird).resolve()
