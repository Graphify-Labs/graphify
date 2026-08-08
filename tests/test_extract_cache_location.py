"""#1774 — extract() must never write its AST cache into the analyzed source tree.

The cache is an output. When no cache_root is given it used to default to the
inferred common parent of the input files — the source tree — so analyzing a
read-only corpus (someone else's repo, a knowledge base) silently created
graphify-out/cache/ inside it. It now defaults to the current working directory;
an explicit cache_root still wins.

Crucially, the cache *location* is decoupled from the key/id *anchor*: the
inferred common parent still anchors the content-hash keys, node ids and the
XAML scan boundary, so keys stay relative and portable even when the corpus
lives outside CWD. (An earlier one-line fix that pointed the anchor itself at
CWD would have made keys absolute and machine-specific for out-of-CWD corpora.)
"""
from __future__ import annotations

from pathlib import Path

import graphify.extract as ex
import graphify.cache as cache
from graphify.cache import load_cached, file_hash


def _reset_stat_index():
    """The stat-index location is chosen once per process via a module global
    (#1747). Reset it so a test sees a fresh-process decision — otherwise an
    earlier test pins the location and masks where THIS extract would write it."""
    cache._stat_index_root = None
    cache._stat_index = {}
    cache._stat_index_dirty = False


def _make_corpus(base: Path) -> Path:
    corpus = base / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("class Base:\n    def hello(self):\n        return 1\n")
    (corpus / "b.py").write_text("from a import Base\n\nclass Sub(Base):\n    pass\n")
    return corpus


def test_default_cache_lands_in_cwd_not_source_tree(tmp_path, monkeypatch):
    _reset_stat_index()
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    result = ex.extract([corpus / "a.py", corpus / "b.py"], parallel=False)

    assert result["nodes"], "extraction should still produce nodes"
    # Nothing at all in the source tree — not the AST cache, and not the
    # stat-index.json the hash fastpath writes (which file_hash used to anchor on
    # the key-root, leaving a stray graphify-out/ in a writable corpus, #1774).
    assert not (corpus / "graphify-out").exists(), (
        "cache/stat-index written into the analyzed source tree (#1774)"
    )
    assert (work / "graphify-out" / "cache").is_dir(), "cache should land under CWD"


def test_default_cache_does_not_leave_stat_index_in_source_tree(tmp_path, monkeypatch):
    """Fresh-process regression for the stat-index leak specifically: even for a
    WRITABLE out-of-CWD corpus (where the write would succeed), file_hash's
    stat-index must follow the cache location, not the key anchor (#1774)."""
    _reset_stat_index()
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "elsewhere"
    work.mkdir()
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py", corpus / "b.py"], parallel=False)
    # The stat index is buffered in memory and flushed at interpreter exit; force
    # the flush now so we can assert WHERE it lands.
    cache._flush_stat_index()

    assert not (corpus / "graphify-out").exists(), "stat-index leaked into the corpus"
    assert (work / "graphify-out" / "cache" / "stat-index.json").exists(), (
        "stat-index should be written under the cache location (CWD)"
    )


def test_explicit_cache_root_still_wins(tmp_path, monkeypatch):
    _reset_stat_index()
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "out"
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py"], cache_root=out, parallel=False)

    assert (out / "graphify-out" / "cache").is_dir()
    assert not (corpus / "graphify-out").exists()
    assert not (work / "graphify-out").exists()


def test_default_cache_round_trips_via_extract(tmp_path, monkeypatch):
    """A second extract() of the same corpus must hit the CWD cache the first
    wrote — the real contract (both runs anchor keys on the inferred corpus root
    and locate the cache at CWD)."""
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py"], parallel=False)
    # Look up with the same anchor extract() uses (the corpus dir) and the CWD
    # cache location — this must hit.
    hit = load_cached(corpus / "a.py", corpus.resolve(), cache_root=Path(".").resolve())
    assert hit is not None, "second run should hit the CWD cache written by the first"


def test_cache_keys_stay_relative_for_out_of_cwd_corpus(tmp_path, monkeypatch):
    """The location/anchor split must keep content-hash keys anchored on the
    corpus (relative, portable) even when the corpus is outside CWD — not
    re-anchored to CWD, which would bake a machine-specific absolute path into
    the key and break shared/CI cache reuse (#1774 regression guard)."""
    import hashlib

    corpus = _make_corpus(tmp_path)
    work = tmp_path / "elsewhere" / "work"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py"], parallel=False)

    root = corpus.resolve()
    key = file_hash(corpus / "a.py", root)
    raw = (corpus / "a.py").read_bytes()

    def _key_with(anchor_rel: str) -> str:
        h = hashlib.sha256()
        h.update(raw)
        h.update(b"\x00")
        h.update(anchor_rel.encode())
        return h.hexdigest()

    # Portable: keyed on the relative path within the corpus...
    assert key == _key_with("a.py")
    # ...not on the absolute path (which the CWD-anchor one-liner would produce).
    abs_rel = str((corpus / "a.py").resolve()).lower()
    assert key != _key_with(abs_rel)
