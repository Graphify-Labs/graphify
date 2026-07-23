"""Semantic extraction cache lives in Helix generation state, never sidecars."""

from pathlib import Path

from graphify.cache import check_semantic_cache, save_semantic_cache


def test_semantic_cache_round_trips_through_generation_mapping(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    doc = corpus / "paper.md"
    doc.write_text("Some academic content.")
    cache: dict = {}

    saved = save_semantic_cache(
        [{"id": "p1", "label": "Paper", "source_file": str(doc)}],
        [],
        root=corpus,
        merge_existing=True,
        allowed_source_files=[doc],
        cache=cache,
    )
    nodes, edges, hyperedges, uncached = check_semantic_cache(
        [str(doc)], cache, root=corpus
    )

    assert saved == 1
    assert not uncached and not edges and not hyperedges
    assert nodes[0]["id"] == "p1"
    assert Path(nodes[0]["source_file"]) == doc


def test_semantic_cache_uses_corpus_root_for_relative_sources(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    doc = corpus / "report.md"
    doc.write_text("# Annual Report\nKey findings.")
    cache: dict = {}

    saved = save_semantic_cache(
        [{"id": "r1", "source_file": "report.md"}],
        [],
        root=corpus,
        allowed_source_files=[doc],
        cache=cache,
    )

    assert saved == 1
    assert len(cache) == 1
    assert not (corpus / "graphify-out").exists()


def test_semantic_cache_is_inert_without_generation_mapping(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    doc = root / "main.md"
    doc.write_text("Main content.")

    saved = save_semantic_cache(
        [{"id": "m1", "source_file": str(doc)}], [], root=root
    )

    assert saved == 0
    assert list(root.iterdir()) == [doc]


def test_semantic_cache_invalidates_content_changes(tmp_path: Path):
    root = tmp_path / "project"
    root.mkdir()
    doc = root / "main.md"
    doc.write_text("Original body.")
    cache: dict = {}
    save_semantic_cache(
        [{"id": "m1", "source_file": str(doc)}], [], root=root, cache=cache
    )
    doc.write_text("Changed body.")

    nodes, _edges, _hyperedges, uncached = check_semantic_cache(
        [str(doc)], cache, root=root
    )

    assert not nodes
    assert uncached == [str(doc)]
