"""Tests for partial-extraction cache promotion.

A truncated LLM chunk (`finish_reason="length"` that could not be recovered by
splitting, or a max-depth adaptive-retry give-up) yields an incomplete node set.
It is tagged with an internal ``_partial`` marker; ``save_semantic_cache`` stamps
that file's entry ``partial: True``, and ``load_cached`` then treats a partial
entry as a cache MISS so the file is re-dispatched instead of served forever.
"""

from graphify import llm
from graphify.cache import (
    save_semantic_cache,
    load_cached,
    _group_has_partial_marker,
)


def _doc(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# Heading\nsome prose\n", encoding="utf-8")
    return doc


def test_intrinsic_partial_marker_makes_entry_a_cache_miss(tmp_path):
    doc = _doc(tmp_path)
    nodes = [{"id": "n1", "label": "Heading", "source_file": "doc.md", "_partial": True}]
    saved = save_semantic_cache(nodes, [], root=tmp_path, prompt="P")
    assert saved == 1
    # The stamped entry is present on disk, but load_cached rejects it.
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P") is None


def test_partial_source_files_arg_stamps_entry(tmp_path):
    doc = _doc(tmp_path)
    # No intrinsic marker; partial-ness comes only from the explicit arg.
    nodes = [{"id": "n1", "label": "Heading", "source_file": "doc.md"}]
    save_semantic_cache(nodes, [], root=tmp_path, prompt="P", partial_source_files=["doc.md"])
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P") is None


def test_non_partial_entry_loads_normally(tmp_path):
    doc = _doc(tmp_path)
    nodes = [{"id": "n1", "label": "Heading", "source_file": "doc.md"}]
    save_semantic_cache(nodes, [], root=tmp_path, prompt="P")
    loaded = load_cached(doc, root=tmp_path, kind="semantic", prompt="P")
    assert loaded is not None
    assert len(loaded["nodes"]) == 1


def test_partial_entry_self_heals_on_complete_reextraction(tmp_path):
    doc = _doc(tmp_path)
    partial = [{"id": "n1", "source_file": "doc.md", "_partial": True}]
    save_semantic_cache(partial, [], root=tmp_path, prompt="P")
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P") is None
    # A later complete extraction overwrites the same content-hash key with a
    # non-partial entry, which then serves normally.
    complete = [
        {"id": "n1", "source_file": "doc.md"},
        {"id": "n2", "source_file": "doc.md"},
    ]
    save_semantic_cache(complete, [], root=tmp_path, prompt="P")
    loaded = load_cached(doc, root=tmp_path, kind="semantic", prompt="P")
    assert loaded is not None
    assert len(loaded["nodes"]) == 2


def test_merge_existing_accumulates_slices_and_stays_partial(tmp_path):
    """A file sliced across chunks: an earlier truncated slice must not be
    dropped (nor the entry promoted to complete) by a later clean slice's
    merge_existing checkpoint. The union keeps both slices and the entry stays
    partial until a fully-clean re-extraction overwrites it."""
    doc = _doc(tmp_path)
    partial = [{"id": "n1", "source_file": "doc.md", "_partial": True}]
    save_semantic_cache(partial, [], root=tmp_path, prompt="P")
    fresh = [{"id": "n2", "source_file": "doc.md"}]
    save_semantic_cache(fresh, [], root=tmp_path, prompt="P", merge_existing=True)
    # Normal read is still a miss: the file had a truncated slice, so it must be
    # re-dispatched rather than served.
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P") is None
    # But nothing was lost — both slices are present in the accumulated entry.
    peek = load_cached(doc, root=tmp_path, kind="semantic", prompt="P", allow_partial=True)
    assert peek is not None
    assert {n["id"] for n in peek["nodes"]} == {"n1", "n2"}


def test_stamped_manifest_excludes_partial_files():
    """A truncated file produced output this run but is left unstamped in the
    manifest (like a failed chunk) so detect_incremental re-queues it."""
    from pathlib import Path
    from graphify.cli import _stamped_manifest_files

    files_by_type = {"document": ["a.md", "b.md"], "code": ["x.py"]}
    sem_result = {
        "nodes": [
            {"id": "1", "source_file": "a.md"},
            {"id": "2", "source_file": "b.md"},
        ],
        "edges": [], "hyperedges": [],
    }
    out = _stamped_manifest_files(files_by_type, sem_result, Path("."),
                                  partial_source_files={"b.md"})
    # a.md extracted cleanly -> stamped; b.md truncated -> excluded; code kept.
    assert out["document"] == ["a.md"]
    assert out["code"] == ["x.py"]


def test_group_has_partial_marker():
    assert _group_has_partial_marker({"nodes": [{"_partial": True}]}) is True
    assert _group_has_partial_marker({"edges": [{"_partial": True}]}) is True
    assert _group_has_partial_marker({"nodes": [{"id": "a"}], "edges": [], "hyperedges": []}) is False
    assert _group_has_partial_marker({}) is False


def test_mark_partial_and_partial_source_files():
    result = {
        "nodes": [{"id": "a", "source_file": "x.md"}],
        "edges": [{"source": "a", "target": "b", "source_file": "x.md"}],
        "hyperedges": [{"id": "h", "source_file": "y.md"}],
    }
    llm._mark_partial(result)
    assert result["nodes"][0]["_partial"] is True
    assert result["edges"][0]["_partial"] is True
    assert result["hyperedges"][0]["_partial"] is True
    assert llm._partial_source_files(result) == ["x.md", "y.md"]


def test_partial_source_files_empty_when_unmarked():
    result = {"nodes": [{"id": "a", "source_file": "x.md"}], "edges": [], "hyperedges": []}
    assert llm._partial_source_files(result) == []


def test_strip_partial_markers_removes_internal_key():
    result = {
        "nodes": [{"id": "a", "_partial": True}],
        "edges": [{"source": "a", "target": "b", "_partial": True}],
        "hyperedges": [{"id": "h", "_partial": True}],
    }
    llm._strip_partial_markers(result)
    assert "_partial" not in result["nodes"][0]
    assert "_partial" not in result["edges"][0]
    assert "_partial" not in result["hyperedges"][0]
