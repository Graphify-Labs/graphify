"""Partial semantic extraction remains a native-cache miss until healed."""

from graphify import llm
from graphify.cache import _group_has_partial_marker, load_cached, save_semantic_cache


def _doc(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Heading\nBody\n")
    return path


def test_intrinsic_and_explicit_partial_entries_are_misses(tmp_path):
    doc = _doc(tmp_path)
    cache = {}
    save_semantic_cache(
        [{"id": "n", "source_file": "doc.md", "_partial": True}], [],
        root=tmp_path, prompt="P", cache=cache,
    )
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache) is None
    save_semantic_cache(
        [{"id": "n", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", partial_source_files=["doc.md"], cache=cache,
    )
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache) is None


def test_complete_reextraction_promotes_partial_entry(tmp_path):
    doc = _doc(tmp_path)
    cache = {}
    save_semantic_cache(
        [], [], root=tmp_path, prompt="P", partial_source_files=["doc.md"], cache=cache,
    )
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache) is None
    complete = [{"id": "n1", "source_file": "doc.md"}, {"id": "n2", "source_file": "doc.md"}]
    save_semantic_cache(complete, [], root=tmp_path, prompt="P", cache=cache)
    loaded = load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache)
    assert loaded is not None and len(loaded["nodes"]) == 2


def test_merge_existing_keeps_prior_partial_and_all_slices(tmp_path):
    doc = _doc(tmp_path)
    cache = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md", "_partial": True}], [],
        root=tmp_path, prompt="P", cache=cache,
    )
    save_semantic_cache(
        [{"id": "n2", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", merge_existing=True, cache=cache,
    )
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache) is None
    peek = load_cached(
        doc, root=tmp_path, kind="semantic", prompt="P", allow_partial=True, cache=cache,
    )
    assert peek is not None and {node["id"] for node in peek["nodes"]} == {"n1", "n2"}


def test_empty_parse_partial_overrides_prior_clean_slice(tmp_path):
    doc = _doc(tmp_path)
    cache = {}
    save_semantic_cache(
        [{"id": "n1", "source_file": "doc.md"}], [], root=tmp_path,
        prompt="P", cache=cache,
    )
    save_semantic_cache(
        [], [], root=tmp_path, prompt="P", merge_existing=True,
        partial_source_files=["doc.md"], cache=cache,
    )
    assert load_cached(doc, root=tmp_path, kind="semantic", prompt="P", cache=cache) is None


def test_partial_helpers_cover_items_and_empty_parse_metadata():
    result = {"nodes": [], "edges": [], "hyperedges": [], "_partial_files": ["big.md"]}
    assert llm._partial_source_files(result) == ["big.md"]
    marked = {
        "nodes": [{"id": "a", "source_file": "x.md"}],
        "edges": [{"source": "a", "target": "b", "source_file": "x.md"}],
        "hyperedges": [{"id": "h", "source_file": "y.md"}],
    }
    llm._mark_partial(marked)
    assert llm._partial_source_files(marked) == ["x.md", "y.md"]
    assert _group_has_partial_marker(marked)
    llm._strip_partial_markers(marked)
    assert not _group_has_partial_marker(marked)
