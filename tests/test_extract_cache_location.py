"""AST extraction caches live in Helix state, never beside source files."""

from graphify.cache import file_hash
from graphify.extract import extract


def _corpus(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.py").write_text("def a():\n    return 1\n")
    (root / "b.py").write_text("def b():\n    return a()\n")
    return root


def test_extract_populates_caller_owned_cache_without_filesystem_sidecar(tmp_path):
    corpus = _corpus(tmp_path)
    cache = {}
    result = extract([corpus / "a.py", corpus / "b.py"], root=corpus, cache=cache, parallel=False)
    assert result["nodes"]
    assert len(cache) == 2
    assert not (corpus / "graphify-out").exists()
    assert not (tmp_path / "graphify-out").exists()


def test_second_extract_reuses_same_state_cache(tmp_path, monkeypatch):
    corpus = _corpus(tmp_path)
    cache = {}
    first = extract([corpus / "a.py"], root=corpus, cache=cache, parallel=False)

    def should_not_run(*args, **kwargs):
        raise AssertionError("cached source was re-extracted")

    monkeypatch.setattr("graphify.extract._safe_extract_with_xaml_root", should_not_run)
    second = extract([corpus / "a.py"], root=corpus, cache=cache, parallel=False)
    assert second == first


def test_deprecated_cache_root_does_not_create_sidecars(tmp_path):
    corpus = _corpus(tmp_path)
    legacy_location = tmp_path / "legacy-cache-location"
    extract([corpus / "a.py"], root=corpus, cache_root=legacy_location, parallel=False)
    assert not legacy_location.exists()


def test_file_hash_is_content_based_and_root_independent(tmp_path):
    corpus = _corpus(tmp_path)
    assert file_hash(corpus / "a.py", corpus) == file_hash(corpus / "a.py", tmp_path)
