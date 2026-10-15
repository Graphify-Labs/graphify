"""#3989 — a process that touches more than one cache root must not have the
first root's stat-index.json poisoned with entries from every root that
followed it.

``_ensure_stat_index`` used to bind to the FIRST root/cache_root it ever saw
and return immediately for every later call, for the life of the process.
Reads for a later root silently came from the first root's (irrelevant) file,
and at exit the accumulated in-memory index — now holding entries for every
root ever touched — was written back into the FIRST root's file alone.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from graphify import cache


@pytest.fixture(autouse=True)
def _fresh_index():
    def reset():
        cache._stat_index_root = None
        cache._stat_index_anchor = None
        cache._stat_index = {}
        cache._stat_index_dirty = False
        cache._stat_index_path = None
    reset()
    yield
    reset()


def _make_project(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """Return (source root, absolute cache dir) for a fake project ``name`` —
    the exact shape of the issue's own reproduction (an absolute
    ``_GRAPHIFY_OUT`` set fresh before each root's calls)."""
    src = tmp_path / name / "src"
    src.mkdir(parents=True)
    (src / "doc.md").write_text(f"content of {name}", encoding="utf-8")
    out = tmp_path / name / "out"
    out.mkdir(parents=True)
    return src, out


def _stat_index_file(cache_dir: Path) -> Path:
    return cache_dir / "cache" / "stat-index.json"


def test_each_root_gets_its_own_stat_index_file_not_the_first_roots(monkeypatch, tmp_path):
    """Two different projects, each with their own absolute cache dir, must
    each end up with their OWN stat-index.json — not a shared/poisoned one."""
    src_a, out_a = _make_project(tmp_path, "a")
    src_b, out_b = _make_project(tmp_path, "b")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_a))
        cache.file_hash(src_a / "doc.md", root=src_a)
        monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_b))
        cache.file_hash(src_b / "doc.md", root=src_b)
        cache._flush_stat_index()

    assert _stat_index_file(out_a).exists()
    assert _stat_index_file(out_b).exists()
    index_a = json.loads(_stat_index_file(out_a).read_text(encoding="utf-8"))
    index_b = json.loads(_stat_index_file(out_b).read_text(encoding="utf-8"))
    # Project A's file must hold only A's own (relativized) key, never a key
    # belonging to project B, and vice versa.
    assert any("doc.md" in k for k in index_a)
    assert any("doc.md" in k for k in index_b)
    assert not any(str(src_b) in k for k in index_a)
    assert not any(str(src_a) in k for k in index_b)


def test_switching_cache_root_mid_process_warns(monkeypatch, tmp_path):
    """Crossing from one bound root to another in the same process must be
    visible, not silent (#3989 minimum-fix requirement)."""
    src_a, out_a = _make_project(tmp_path, "a")
    src_b, out_b = _make_project(tmp_path, "b")

    monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_a))
    cache.file_hash(src_a / "doc.md", root=src_a)
    monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_b))
    with pytest.warns(RuntimeWarning, match="stat index switched"):
        cache.file_hash(src_b / "doc.md", root=src_b)


def test_revisiting_the_first_root_reloads_its_own_entries(monkeypatch, tmp_path):
    """After switching away and back, the first root's file must still carry
    its own entry — the switch-back must reload it, not keep serving/writing
    whatever root happened to be bound last."""
    src_a, out_a = _make_project(tmp_path, "a")
    src_b, out_b = _make_project(tmp_path, "b")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_a))
        digest_a_first = cache.file_hash(src_a / "doc.md", root=src_a)
        monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_b))
        cache.file_hash(src_b / "doc.md", root=src_b)
        monkeypatch.setattr(cache, "_GRAPHIFY_OUT", str(out_a))
        digest_a_second = cache.file_hash(src_a / "doc.md", root=src_a)
        cache._flush_stat_index()

    assert digest_a_first == digest_a_second
    index_a = json.loads(_stat_index_file(out_a).read_text(encoding="utf-8"))
    assert any("doc.md" in k for k in index_a)
    assert not any(str(src_b) in k for k in index_a)
