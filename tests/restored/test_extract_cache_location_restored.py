"""Restored cache-location regressions, adapted to generation-owned state.

The old tests protected source trees from cache sidecars.  Helix strengthens that
contract: extraction receives a caller-owned mapping which is persisted with the
active generation, and ``cache_root`` must not create anything on disk.
"""

from graphify.cache import file_hash, load_cached
from graphify.extract import extract


def _make_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.py").write_text("def a():\n    return 1\n")
    (corpus / "b.py").write_text("def b():\n    return a()\n")
    return corpus


def test_default_cache_lands_in_cwd_not_source_tree(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    state_cache = {}

    result = extract(
        [corpus / "a.py", corpus / "b.py"], root=corpus,
        cache=state_cache, parallel=False,
    )

    assert result["nodes"]
    assert len(state_cache) == 2
    assert not (corpus / "graphify-out").exists()
    assert not (work / "graphify-out").exists()


def test_default_cache_does_not_leave_stat_index_in_source_tree(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "elsewhere"
    work.mkdir()
    monkeypatch.chdir(work)

    extract([corpus / "a.py"], root=corpus, cache={}, parallel=False)

    assert not list(corpus.rglob("stat-index.json"))
    assert not list(work.rglob("stat-index.json"))


def test_explicit_cache_root_still_wins(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    deprecated_location = tmp_path / "old-sidecar-location"
    monkeypatch.chdir(work)
    state_cache = {}

    extract(
        [corpus / "a.py"], root=corpus, cache_root=deprecated_location,
        cache=state_cache, parallel=False,
    )

    assert state_cache
    assert not deprecated_location.exists()
    assert not (corpus / "graphify-out").exists()


def test_default_cache_round_trips_via_extract(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    state_cache = {}

    first = extract([corpus / "a.py"], root=corpus, cache=state_cache, parallel=False)
    hit = load_cached(corpus / "a.py", corpus, cache=state_cache)
    second = extract([corpus / "a.py"], root=corpus, cache=state_cache, parallel=False)

    assert hit is not None
    assert second == first


def test_cache_keys_stay_relative_for_out_of_cwd_corpus(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path)
    work = tmp_path / "elsewhere" / "work"
    work.mkdir(parents=True)
    monkeypatch.chdir(work)
    state_cache = {}

    extract([corpus / "a.py"], root=corpus, cache=state_cache, parallel=False)

    key = next(iter(state_cache))
    assert key.endswith(":a.py")
    assert str(corpus) not in key
    assert file_hash(corpus / "a.py", corpus) == file_hash(corpus / "a.py", work)
