"""Restored #1990/#1991 cache-root regressions for Helix generation state."""

from __future__ import annotations

import inspect
import warnings

from graphify.cache import check_semantic_cache, save_semantic_cache


def _roots(tmp_path):
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()
    return corpus, out


def test_save_semantic_cache_writes_to_cache_root_not_corpus(tmp_path):
    corpus, out = _roots(tmp_path)
    doc = corpus / "report.md"
    doc.write_text("# Report\nSome content here.")
    state = {}

    saved = save_semantic_cache(
        [{"id": "n1", "source_file": str(doc)}], [],
        root=corpus, cache_root=out, cache=state,
    )

    assert saved == 1 and state
    assert not (corpus / "graphify-out").exists()
    assert not (out / "graphify-out").exists()


def test_save_semantic_cache_no_corpus_graphify_out_created(tmp_path):
    corpus, out = _roots(tmp_path)
    doc = corpus / "notes.md"
    doc.write_text("Notes content.")
    save_semantic_cache(
        [{"id": "x", "source_file": str(doc)}], [],
        root=corpus, cache_root=out, cache={},
    )
    assert not (corpus / "graphify-out").exists()
    assert not (out / "graphify-out").exists()


def test_checkpoint_with_cache_root_is_found_by_check_semantic_cache(tmp_path):
    corpus, out = _roots(tmp_path)
    doc = corpus / "paper.md"
    doc.write_text("Some academic content.")
    state = {}
    save_semantic_cache(
        [{"id": "p1", "source_file": str(doc)}], [], root=corpus,
        cache_root=out, merge_existing=True, allowed_source_files=[doc],
        cache=state,
    )

    nodes, edges, hyperedges, uncached = check_semantic_cache(
        [str(doc)], state, root=corpus
    )
    assert not uncached and not edges and not hyperedges
    assert {node["id"] for node in nodes} == {"p1"}


def test_final_save_with_out_root_populates_cache(tmp_path):
    corpus, out = _roots(tmp_path)
    doc = corpus / "report.md"
    doc.write_text("# Annual Report\nKey findings.")
    state = {}

    saved = save_semantic_cache(
        [{"id": "r1", "source_file": "report.md"}], [], root=corpus,
        cache_root=out, allowed_source_files=[doc], cache=state,
    )

    assert saved == 1
    assert len(state) == 1
    assert next(iter(state)).endswith(":report.md")


def test_final_save_with_wrong_root_emits_warning(tmp_path):
    corpus, out = _roots(tmp_path)
    (corpus / "report.md").write_text("# Report")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        saved = save_semantic_cache(
            [{"id": "r1", "source_file": "report.md"}], [],
            root=out, cache={},
        )

    assert saved == 0
    assert any("corpus root" in str(item.message) for item in caught)


def test_save_semantic_cache_backward_compat_no_cache_root(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    doc = root / "main.md"
    doc.write_text("Main content.")

    saved = save_semantic_cache(
        [{"id": "m1", "source_file": str(doc)}], [], root=root
    )

    assert saved == 0
    assert not (root / "graphify-out").exists()


def test_extract_corpus_parallel_accepts_cache_root_kwarg():
    from graphify.llm import extract_corpus_parallel

    signature = inspect.signature(extract_corpus_parallel)
    assert "cache_root" in signature.parameters
    assert "cache" in signature.parameters
