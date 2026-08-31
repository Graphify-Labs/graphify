"""Regression tests for #1990 and #1991.

#1990 — `graphify extract --out` saves recovery checkpoints in the wrong directory.
         save_semantic_cache must write to cache_root (the --out dir), not root
         (the corpus dir), when they differ.

#1991 — Final semantic-cache save resolves source_file paths against out_root
         and silently writes 0 entries when corpus files do not exist there.
         Fixed by passing root=target (corpus), cache_root=out_root to
         save_semantic_cache so source_file resolution and cache placement are
         independently anchored.
"""
import warnings
from pathlib import Path

import pytest

from graphify.cache import (
    check_semantic_cache,
    file_hash,
    load_cached,
    save_semantic_cache,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _semantic_dir(root: Path, mode: str | None = None) -> Path:
    kind = "semantic" if mode is None else f"semantic-{mode}"
    return root / "graphify-out" / "cache" / kind


def _count_cache_files(base: Path) -> int:
    """Count .json files under a cache dir (recursively, excluding .tmp)."""
    if not base.is_dir():
        return 0
    return sum(1 for _ in base.rglob("*.json"))


# ---------------------------------------------------------------------------
# #1990 — checkpoint writes to cache_root, not corpus root
# ---------------------------------------------------------------------------


def test_save_semantic_cache_writes_to_cache_root_not_corpus(tmp_path):
    """When cache_root differs from root, cache files must land under cache_root."""
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()

    doc = corpus / "report.md"
    doc.write_text("# Report\nSome content here.")

    nodes = [{"id": "n1", "label": "Report", "source_file": str(doc)}]
    edges: list = []

    saved = save_semantic_cache(
        nodes, edges, root=corpus, cache_root=out
    )

    assert saved == 1, "expected 1 entry written"
    # Cache file must be under the out dir, not the corpus dir
    assert _count_cache_files(_semantic_dir(out)) == 1
    assert _count_cache_files(_semantic_dir(corpus)) == 0


def test_save_semantic_cache_no_corpus_graphify_out_created(tmp_path):
    """With cache_root set, no graphify-out/ dir should be created inside corpus."""
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()

    doc = corpus / "notes.md"
    doc.write_text("Notes content.")

    save_semantic_cache(
        [{"id": "x", "label": "X", "source_file": str(doc)}],
        [],
        root=corpus,
        cache_root=out,
    )

    assert not (corpus / "graphify-out").exists(), (
        "graphify-out/ must not be created inside the corpus when cache_root is set"
    )


# ---------------------------------------------------------------------------
# #1990 — checkpoint written with cache_root is found on recovery read
# ---------------------------------------------------------------------------


def test_checkpoint_with_cache_root_is_found_by_check_semantic_cache(tmp_path):
    """A checkpoint saved with cache_root can be retrieved by check_semantic_cache
    using the same root/cache_root split — simulating recovery after interruption."""
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()

    doc = corpus / "paper.md"
    doc.write_text("Some academic content.")

    nodes = [{"id": "p1", "label": "Paper", "source_file": str(doc)}]

    # Simulate a checkpoint written mid-run (merge_existing path)
    save_semantic_cache(
        nodes, [],
        root=corpus,
        cache_root=out,
        merge_existing=True,
        allowed_source_files=[doc],
    )

    # Recovery read: check_semantic_cache with the same root/cache_root split
    # cli.py now uses (root=target, cache_root=out_root).
    cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(
        [str(doc)], root=corpus, cache_root=out
    )

    assert len(uncached) == 0, f"expected cache hit, got miss for: {uncached}"
    assert any(n.get("id") == "p1" for n in cached_nodes)


# ---------------------------------------------------------------------------
# #1991 — final save resolves source_file against corpus root, not out_root
# ---------------------------------------------------------------------------


def test_final_save_with_out_root_populates_cache(tmp_path):
    """When root=corpus and cache_root=out, source_file resolution must use
    corpus as anchor so p.is_file() succeeds and the entry is written."""
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()

    doc = corpus / "report.md"
    doc.write_text("# Annual Report\nKey findings.")

    # This is the pattern that was broken: source_file is relative to corpus,
    # but was previously resolved against out_root, making p.is_file() → False.
    nodes = [{"id": "r1", "label": "AnnualReport", "source_file": "report.md"}]

    saved = save_semantic_cache(
        nodes, [],
        root=corpus,
        cache_root=out,
        allowed_source_files=[doc],
    )

    assert saved == 1, (
        "final save must write 1 entry when root=corpus and source_file is "
        "relative to corpus — resolving against out_root caused 0 writes (#1991)"
    )
    assert _count_cache_files(_semantic_dir(out)) == 1


def test_final_save_with_wrong_root_emits_warning(tmp_path):
    """Passing root=out_root (the old broken behaviour) silently writes 0 entries;
    the fix adds a RuntimeWarning when ALL groups are dropped."""
    corpus = tmp_path / "corpus"
    out = tmp_path / "out"
    corpus.mkdir()
    out.mkdir()

    doc = corpus / "report.md"
    doc.write_text("# Report")

    # Old (broken) call: root=out, no cache_root — the corpus-relative
    # source_file is resolved against out where the file doesn't exist
    # → 0 entries written.
    nodes = [{"id": "r1", "label": "R", "source_file": "report.md"}]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        saved = save_semantic_cache(nodes, [], root=out)

    assert saved == 0
    # The new warning must fire when every group is dropped
    assert any(
        "#1991" in str(warning.message) for warning in w
    ), "expected RuntimeWarning mentioning #1991 when all groups are silently skipped"


# ---------------------------------------------------------------------------
# Backward compat — omitting cache_root keeps legacy behaviour
# ---------------------------------------------------------------------------


def test_save_semantic_cache_backward_compat_no_cache_root(tmp_path):
    """When cache_root is omitted, cache files still land under root (unchanged)."""
    root = tmp_path / "project"
    root.mkdir()

    doc = root / "main.md"
    doc.write_text("Main content.")

    nodes = [{"id": "m1", "label": "Main", "source_file": str(doc)}]

    saved = save_semantic_cache(nodes, [], root=root)

    assert saved == 1
    assert _count_cache_files(_semantic_dir(root)) == 1


def test_extract_corpus_parallel_accepts_cache_root_kwarg():
    """extract_corpus_parallel must accept a cache_root kwarg without raising
    (import + signature check — no actual LLM call)."""
    import inspect
    from graphify.llm import extract_corpus_parallel

    sig = inspect.signature(extract_corpus_parallel)
    assert "cache_root" in sig.parameters, (
        "extract_corpus_parallel must expose cache_root so cli.py can plumb "
        "out_root through to _checkpoint_chunk (#1990)"
    )
