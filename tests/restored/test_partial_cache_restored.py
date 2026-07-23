"""Restored partial-extraction cache promotion tests for Helix-owned state."""

from graphify import llm
from graphify.cache import (
    _group_has_partial_marker,
    check_semantic_cache,
    load_cached,
    save_semantic_cache,
)


def _doc(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("# Heading\nsome prose\n", encoding="utf-8")
    return doc


def test_intrinsic_partial_marker_makes_entry_a_cache_miss(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    saved = save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md", "_partial": True}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    assert saved == 1
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None


def test_partial_source_files_arg_stamps_entry(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", partial_source_files=["doc.md"], cache=state,
    )
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None


def test_non_partial_entry_loads_normally(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md"}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    loaded = load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    )
    assert loaded is not None and len(loaded["nodes"]) == 1


def test_partial_entry_self_heals_on_complete_reextraction(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md", "_partial": True}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None
    save_semantic_cache(
        [
            {"id": "n1", "source_file": "doc.md"},
            {"id": "n2", "source_file": "doc.md"},
        ],
        [], root=tmp_path, prompt="P", cache=state,
    )
    loaded = load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    )
    assert loaded is not None and len(loaded["nodes"]) == 2


def test_merge_existing_accumulates_slices_and_stays_partial(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md", "_partial": True}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    save_semantic_cache(
        [{"id": "n2", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", merge_existing=True, cache=state,
    )
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None
    peek = load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P",
        allow_partial=True, cache=state,
    )
    assert peek is not None
    assert {node["id"] for node in peek["nodes"]} == {"n1", "n2"}


def test_save_stamps_partial_file_with_no_items(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md"}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    save_semantic_cache(
        [], [], root=tmp_path, prompt="P", merge_existing=True,
        partial_source_files=["doc.md"], cache=state,
    )
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None
    peek = load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P",
        allow_partial=True, cache=state,
    )
    assert peek is not None and {node["id"] for node in peek["nodes"]} == {"n1"}


def test_clean_slice_does_not_repromote_empty_parse_partial(tmp_path):
    doc = _doc(tmp_path)
    state = {}
    save_semantic_cache(
        [], [], root=tmp_path, prompt="P",
        partial_source_files=["doc.md"], cache=state,
    )
    save_semantic_cache(
        [{"id": "n2", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", merge_existing=True, cache=state,
    )
    assert load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", cache=state
    ) is None


def test_partial_files_carries_empty_parse_truncation():
    result = {"nodes": [], "edges": [], "hyperedges": [], "_partial_files": ["big.md"]}
    assert llm._partial_source_files(result) == ["big.md"]
    result["nodes"] = [{"id": "a", "source_file": "x.md", "_partial": True}]
    assert llm._partial_source_files(result) == ["big.md", "x.md"]


def test_stamped_manifest_excludes_partial_files(tmp_path):
    """A partial durable entry is a miss, so the file is re-queued."""
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("A")
    b.write_text("B")
    state = {}
    save_semantic_cache(
        [{"id": "a", "source_file": "a.md"}], [],
        root=tmp_path, prompt="P", cache=state,
    )
    save_semantic_cache(
        [{"id": "b", "source_file": "b.md"}], [], root=tmp_path,
        prompt="P", partial_source_files=["b.md"], cache=state,
    )
    nodes, _edges, _hyperedges, uncached = check_semantic_cache(
        [str(a), str(b)], state, root=tmp_path, prompt="P"
    )
    assert {node["id"] for node in nodes} == {"a"}
    assert uncached == [str(b)]


def test_group_has_partial_marker():
    assert _group_has_partial_marker({"nodes": [{"_partial": True}]}) is True
    assert _group_has_partial_marker({"edges": [{"_partial": True}]}) is True
    assert _group_has_partial_marker({"nodes": [{"id": "a"}]}) is False
    assert _group_has_partial_marker({}) is False


def test_mark_partial_and_partial_source_files():
    result = {
        "nodes": [{"id": "a", "source_file": "x.md"}],
        "edges": [{"source": "a", "target": "b", "source_file": "x.md"}],
        "hyperedges": [{"id": "h", "source_file": "y.md"}],
    }
    llm._mark_partial(result)
    assert all(item["_partial"] is True for bucket in result.values() for item in bucket)
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
    assert all("_partial" not in item for bucket in result.values() for item in bucket)
