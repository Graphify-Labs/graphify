"""#2973 — save_semantic_cache must recover a group whose reported
source_file never resolves to a real file, by an unambiguous basename match
against the already dispatched allowlist, instead of silently dropping it.

A weak or local backend's adaptive-retry split path (llm.py bisecting a
chunk that overflowed context and retrying) sometimes re-prompts with a
reduced file subset and loses track of which of the original chunk's files
a given node came from, so its source_file drifts to something that never
resolves at all. Without recovery this silently discarded the group's nodes
and edges from the cache on every incremental run.
"""
from __future__ import annotations

import pytest

from graphify.cache import load_cached, save_semantic_cache


def test_malformed_but_basename_unique_path_recovers(tmp_path):
    real = tmp_path / "sub" / "weird_named_file.py"
    real.parent.mkdir(parents=True)
    real.write_text("def f(): pass\n")

    nodes = [{"id": "n1", "label": "f", "source_file": "lost_dir/weird_named_file.py"}]
    saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[real])
    assert saved == 1

    cached = load_cached(real, root=tmp_path, kind="semantic")
    assert cached is not None
    assert {n["id"] for n in cached["nodes"]} == {"n1"}


def test_ambiguous_basename_stays_skipped(tmp_path):
    a = tmp_path / "pkg_a" / "shared.py"
    b = tmp_path / "pkg_b" / "shared.py"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text("def f(): pass\n")
    b.write_text("def g(): pass\n")

    nodes = [{"id": "n1", "label": "f", "source_file": "lost_dir/shared.py"}]
    with pytest.warns(RuntimeWarning, match="do not resolve to real files"):
        saved = save_semantic_cache(nodes, [], root=tmp_path, allowed_source_files=[a, b])
    assert saved == 0
    assert load_cached(a, root=tmp_path, kind="semantic") is None
    assert load_cached(b, root=tmp_path, kind="semantic") is None


def test_unscoped_call_with_no_allowlist_is_unaffected(tmp_path):
    # No allowed_source_files at all: recovery must never run, so a
    # genuinely bogus path is skipped exactly as before this fix, and a
    # normal well formed path still resolves and saves.
    real = tmp_path / "sub" / "weird_named_file.py"
    real.parent.mkdir(parents=True)
    real.write_text("def f(): pass\n")

    nodes = [
        {"id": "n1", "label": "f", "source_file": "sub/weird_named_file.py"},
        {"id": "n2", "label": "g", "source_file": "totally/does/not/exist.py"},
    ]
    saved = save_semantic_cache(nodes, [], root=tmp_path)
    assert saved == 1

    cached = load_cached(real, root=tmp_path, kind="semantic")
    assert cached is not None
    assert {n["id"] for n in cached["nodes"]} == {"n1"}
