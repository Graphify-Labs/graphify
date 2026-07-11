"""#1774 — extract() must never write its AST cache into the analyzed source tree.

The cache is an output. When no cache_root is given it used to default to the
inferred common parent of the input files — the source tree — so analyzing a
read-only corpus (someone else's repo, a knowledge base) silently created
graphify-out/cache/ inside it. It now defaults to the current working
directory, matching cache_dir()'s own default; an explicit cache_root still
wins.
"""
from __future__ import annotations

from pathlib import Path

import graphify.extract as ex
from graphify.cache import load_cached


def _make_corpus(base: Path) -> Path:
    corpus = base / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("class Base:\n    def hello(self):\n        return 1\n")
    (corpus / "b.py").write_text("from a import Base\n\nclass Sub(Base):\n    pass\n")
    return corpus


def test_default_cache_lands_in_cwd_not_source_tree(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    result = ex.extract([corpus / "a.py", corpus / "b.py"], parallel=False)

    assert result["nodes"], "extraction should still produce nodes"
    assert not (corpus / "graphify-out").exists(), (
        "cache written into the analyzed source tree (#1774)"
    )
    assert (work / "graphify-out" / "cache").is_dir(), "cache should land under CWD"


def test_default_cache_round_trips(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py"], parallel=False)
    assert load_cached(corpus / "a.py", Path(".")) is not None, (
        "second run should hit the CWD cache written by the first"
    )


def test_explicit_cache_root_still_wins(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    out = tmp_path / "out"
    monkeypatch.chdir(work)

    ex.extract([corpus / "a.py"], cache_root=out, parallel=False)

    assert (out / "graphify-out" / "cache").is_dir()
    assert not (corpus / "graphify-out").exists()
    assert not (work / "graphify-out").exists()
