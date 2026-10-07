"""_parse_python_tree memoizes across the two Python resolution passes (#perf).

The symbol-resolution facts pass and the cross-file import pass each parse the
whole .py corpus, back to back, in the main process — so every file was read
and tree-sitter-parsed twice. The parse is now memoized on (path, mtime, size):
the second pass reuses the first pass's tree, a changed file still re-parses.
"""

import time

import pytest

pytest.importorskip("tree_sitter_python")

from graphify.extractors.resolution import _parse_python_tree

try:
    from graphify.extractors.resolution import _parse_python_tree_cached
except ImportError:  # pre-fix tree
    _parse_python_tree_cached = None

needs_cache = pytest.mark.skipif(
    _parse_python_tree_cached is None, reason="parse memo not present"
)


def test_parses_and_returns_source_and_root(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def foo():\n    return 1\n", encoding="utf-8")
    parsed = _parse_python_tree(f)
    assert parsed is not None
    source, root = parsed
    assert b"def foo" in source
    assert root.type == "module"


def test_missing_file_returns_none(tmp_path):
    assert _parse_python_tree(tmp_path / "nope.py") is None


@needs_cache
def test_reuses_parse_within_a_run(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    _parse_python_tree_cached.cache_clear()
    r1 = _parse_python_tree(f)
    for _ in range(9):
        _parse_python_tree(f)
    info = _parse_python_tree_cached.cache_info()
    assert info.misses == 1 and info.hits == 9, info
    # Same cached (source, root) object handed back.
    assert _parse_python_tree(f)[1] is r1[1]


@needs_cache
def test_edit_reparses(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    _parse_python_tree_cached.cache_clear()
    src1, _ = _parse_python_tree(f)
    assert b"x = 1" in src1
    # A rewrite that changes size AND mtime must re-parse, not replay.
    time.sleep(0.01)
    f.write_text("x = 22222\ny = 3\n", encoding="utf-8")
    src2, _ = _parse_python_tree(f)
    assert b"y = 3" in src2, "edited file was served from a stale parse"
