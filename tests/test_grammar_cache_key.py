"""#4236 - the AST cache namespace must include the tree-sitter grammar set:
upgrading a grammar package must invalidate cached extractions produced by
the old grammar, even when the graphify version and source files are
unchanged."""
from __future__ import annotations

import pytest

import graphify.cache as cache_mod


@pytest.fixture(autouse=True)
def _reset_grammar_fp_cache(monkeypatch):
    monkeypatch.setattr(cache_mod, "_GRAMMAR_FINGERPRINT_CACHE", None)


def test_ast_cache_dir_is_grammar_namespaced(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_GRAPHIFY_OUT", str(tmp_path / "out"))
    d = cache_mod.cache_dir(tmp_path, kind="ast")
    name = d.name
    assert name.startswith(f"v{cache_mod._EXTRACTOR_VERSION}-s{cache_mod._AST_CACHE_SCHEMA}-g"), name
    assert name.endswith(cache_mod._grammar_fingerprint()), name


def test_ast_cache_dir_changes_when_grammar_set_changes(tmp_path, monkeypatch):
    """End-to-end of the fix: a grammar upgrade moves the AST cache to a new
    directory, so stale pre-upgrade entries are never served."""
    import importlib.metadata as md

    import graphify.cache as c

    class _D:
        def __init__(self, name, version):
            self.version = version
            self.metadata = {"Name": name}

    monkeypatch.setattr(c, "_GRAPHIFY_OUT", str(tmp_path / "out"))
    monkeypatch.setattr(md, "distributions", lambda: [_D("tree-sitter-swift", "0.7.2")])
    monkeypatch.setattr(c, "_GRAMMAR_FINGERPRINT_CACHE", None)
    d1 = c.cache_dir(tmp_path, kind="ast")
    monkeypatch.setattr(md, "distributions", lambda: [_D("tree-sitter-swift", "0.7.4")])
    monkeypatch.setattr(c, "_GRAMMAR_FINGERPRINT_CACHE", None)
    monkeypatch.setattr(c, "_cleaned_ast_dirs", set())
    d2 = c.cache_dir(tmp_path, kind="ast")
    assert d1 != d2


def test_grammar_fingerprint_changes_with_grammar_versions(monkeypatch):
    import graphify.cache as c

    class _D:
        def __init__(self, name, version):
            self.version = version
            self.metadata = {"Name": name}

    import importlib.metadata as md

    monkeypatch.setattr(md, "distributions", lambda: [_D("tree-sitter", "0.25.2"), _D("tree-sitter-swift", "0.7.2")])
    monkeypatch.setattr(c, "_GRAMMAR_FINGERPRINT_CACHE", None)
    fp1 = c._grammar_fingerprint()
    monkeypatch.setattr(md, "distributions", lambda: [_D("tree-sitter", "0.25.2"), _D("tree-sitter-swift", "0.7.4")])
    monkeypatch.setattr(c, "_GRAMMAR_FINGERPRINT_CACHE", None)
    fp2 = c._grammar_fingerprint()
    assert fp1 != fp2


def test_grammar_fingerprint_stable_for_same_set(monkeypatch):
    import graphify.cache as c

    class _D:
        def __init__(self, name, version):
            self.version = version
            self.metadata = {"Name": name}

    import importlib.metadata as md

    monkeypatch.setattr(md, "distributions", lambda: [_D("tree-sitter", "0.25.2"), _D("tree-sitter-swift", "0.7.4")])
    fp1 = c._grammar_fingerprint()
    monkeypatch.setattr(c, "_GRAMMAR_FINGERPRINT_CACHE", None)  # force recompute
    assert c._grammar_fingerprint() == fp1
