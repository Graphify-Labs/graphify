"""INC-QML-60: new generic identities retain Qt ownership and cache rejection."""
from __future__ import annotations

import json
import hashlib
import copy

import pytest

import graphify.cache as cache
import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.base import _make_id
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.test_qt_final_incremental_parity import normalized
from tests.test_upstream_qt_cache_integration import (
    assert_semantic_preserved,
    python_source,
    semantic_entry,
)


@pytest.fixture
def current_cache(monkeypatch):
    """Simulate the accepted release while preserving independent semantic state."""
    monkeypatch.setattr(cache, "_EXTRACTOR_VERSION", "0.9.99")
    monkeypatch.setattr(cache, "_cleaned_ast_dirs", set())
    for name, value in (("_stat_index", {}), ("_stat_index_root", None),
                        ("_stat_index_anchor", None), ("_stat_index_path", None),
                        ("_stat_index_dirty", False)):
        monkeypatch.setattr(cache, name, value, raising=False)
    yield
    cache._flush_stat_index()


@pytest.mark.parametrize("old_schema", [23, 31, 32, 33, 34, 35, 36, 37, 38])
def test_req_qml011_ac01_ac03_ac04_upstream099_retires_both_predecessors(
        tmp_path, monkeypatch, current_cache, old_schema):
    """Actual predecessor writes miss; a fresh/warm producer keeps semantic bytes."""
    source = python_source(tmp_path)
    semantic = semantic_entry(tmp_path)
    with monkeypatch.context() as predecessor:
        predecessor.setattr(cache, "_AST_CACHE_SCHEMA", old_schema)
        cache.save_cached(source, {"nodes": [{"id": "stale", "label": "stale"}],
                                   "edges": []}, root=tmp_path)
        old_directory = cache.cache_dir(tmp_path)
        assert list(old_directory.glob("*.json"))
    assert cache._AST_CACHE_SCHEMA == 40
    assert cache.load_cached(source, root=tmp_path) is None
    assert not old_directory.exists()
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cache.load_cached(source, root=tmp_path) is not None
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not cold["failed_sources"] and not warm["failed_sources"]
    assert normalized(build_from_json(cold, directed=True, root=tmp_path)) == normalized(
        build_from_json(warm, directed=True, root=tmp_path))
    assert_semantic_preserved(tmp_path, semantic)


def test_req_qml003_ac04_qml014_ac03_colliding_cpp_file_preserves_native_owners(
        tmp_path, current_cache):
    """A file/declaration collision cannot collapse typed constructors or Qt sites."""
    source = tmp_path / "native.hpp"
    source.write_text("""

class Hpp : public QObject {
 Q_OBJECT
public:
 Hpp(int value) { emit changed(); }
 Hpp(double value) { emit changed(); }
signals:
 void changed();
};
class Holder { Hpp *value; };
""", encoding="utf-8")
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    classes = [node for node in cold["nodes"] if node.get("label") == "Hpp"]
    assert len(classes) == 1 and classes[0].get("_callable_class")
    files = [node for node in cold["nodes"] if node.get("label") == source.name]
    assert len(files) == 1 and files[0]["id"] != classes[0]["id"]
    assert files[0]["source_location"] == "L1" and classes[0]["source_location"] == "L3"
    constructors = [node for node in cold["nodes"]
                    if node.get("metadata", {}).get("cpp_constructor")]
    assert len(constructors) == 2 and len({node["id"] for node in constructors}) == 2
    sites = [node for node in cold["nodes"] if qt_metadata(node).get("kind") == "emission"]
    assert len(sites) == 2
    assert {qt_metadata(node).get("owner_id") for node in sites} == {
        node["id"] for node in constructors}
    assert all(qt_metadata(node).get("status") == "resolved" for node in sites)
    holder = next(node for node in cold["nodes"] if node.get("label") == "Holder")
    assert any(edge["source"] == holder["id"] and edge["target"] == classes[0]["id"]
               and edge["relation"] == "references" for edge in cold["edges"])
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not cold["failed_sources"] and not warm["failed_sources"]
    graphs = []
    for name, result in (("cold", cold), ("warm", warm)):
        graph = build_from_json(result, directed=True, root=tmp_path)
        path = tmp_path / (name + ".json")
        assert to_json(graph, {}, str(path), force=True)
        graphs.append(load_node_link_graph(json.loads(path.read_text(encoding="utf-8"))))
    assert normalized(graphs[0]) == normalized(graphs[1])


def test_req_qml014_ac03_cpp_reference_does_not_borrow_an_unrelated_namespace(tmp_path):
    """A declaration registry must not override exact native lexical rejection."""
    source = tmp_path / "scope.hpp"
    source.write_text("namespace Left { class Thing {}; }\n"
                      "namespace Right { class Holder { Thing *value; }; }\n", encoding="utf-8")
    result = extraction.extract_cpp(source)
    thing = next(node for node in result["nodes"]
                 if node.get("label") == "Thing" and node.get("source_file"))
    holder = next(node for node in result["nodes"] if node.get("label") == "Holder")
    assert not any(edge["source"] == holder["id"] and edge["target"] == thing["id"]
                   and edge["relation"] == "references" for edge in result["edges"])


@pytest.mark.parametrize("qualified", [False, True])
@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml014_ac03_cpp_alias_reference_needs_lexical_authority(tmp_path, qualified, mode):
    """A written qualified alias resolves; a sibling namespace cannot borrow it."""
    source = tmp_path / "scope.hpp"
    spelling = "::Left::Count" if qualified else "Count"
    source.write_text("namespace Left { using Count = int; }\n"
                      f"namespace Right {{ class Holder {{ {spelling} *value; }}; }}\n",
                      encoding="utf-8")
    result = (extraction.extract_cpp(source) if mode == "direct" else
              extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False))
    alias = next(node for node in result["nodes"]
                 if node.get("label") == "Count" and node.get("source_file"))
    holder = next(node for node in result["nodes"] if node.get("label") == "Holder")
    resolved = any(edge["source"] == holder["id"] and edge["target"] == alias["id"]
                   and edge["relation"] == "references" for edge in result["edges"])
    assert resolved is qualified


def test_req_qml003_ac04_qml014_ac03_alias_file_collision_keeps_containment(tmp_path):
    """A newly salted alias still belongs to its file and owns real type uses."""
    source = tmp_path / "native.hpp"
    source.write_text("using Hpp = int;\nclass Holder { Hpp value; };\n", encoding="utf-8")
    result = extraction.extract_cpp(source)
    file = next(node for node in result["nodes"] if node.get("label") == source.name)
    alias = next(node for node in result["nodes"] if node.get("label") == "Hpp")
    holder = next(node for node in result["nodes"] if node.get("label") == "Holder")
    assert file["id"] != alias["id"] and alias.get("source_file")
    assert any(edge["source"] == file["id"] and edge["target"] == alias["id"]
               and edge["relation"] == "contains" for edge in result["edges"])
    assert any(edge["source"] == holder["id"] and edge["target"] == alias["id"]
               and edge["relation"] == "references" for edge in result["edges"])


@pytest.mark.parametrize("same_line", [False, True])
@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml014_ac03_reused_alias_node_cannot_supply_another_scope(tmp_path, same_line, mode):
    """Both real aliases survive; even same-line references select only the actual local one.

    The former sourceless assertion guarded a missing second declaration. Once
    both literal identities exist, require the stronger source-owned local
    endpoint while retaining the original prohibition on borrowing Left's node.
    """
    source = tmp_path / "scope.hpp"
    separator = " " if same_line else "\n"
    source.write_text("namespace Left { using Count = int; }" + separator
                      + "namespace Right { using Count = double; class Holder { Count value; }; }\n",
                      encoding="utf-8")
    result = (extraction.extract_cpp(source) if mode == "direct" else
              extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False))
    by_id = {node["id"]: node for node in result["nodes"]}
    holder = next(node for node in result["nodes"] if node.get("label") == "Holder")
    references = [edge for edge in result["edges"]
                  if edge["source"] == holder["id"] and edge["relation"] == "references"]
    aliases = [node for node in result["nodes"] if node.get("label") == "Count" and node.get("source_file")]
    assert len(aliases) == 2 and len({node["id"] for node in aliases}) == 2
    expected = {}
    for namespace in ("Left", "Right"):
        suffix = _make_id("cppalias", hashlib.sha256(f"{namespace}::Count".encode()).hexdigest(), "Count")
        node, = [node for node in aliases if node["id"].endswith("_" + suffix)]
        expected[namespace] = node["id"]
    assert references and {edge["target"] for edge in references} == {expected["Right"]}
    assert all(edge["target"] != expected["Left"] and by_id[edge["target"]].get("source_file") for edge in references)


def test_req_qml022_ac06_schema37_missing_anonymous_call_regenerates_without_source_change(
        tmp_path, monkeypatch, current_cache):
    """A successful actual37 fragment cannot retain the omitted helper after the epoch change."""
    source = tmp_path / "panel.cpp"
    raw = b"namespace {void helper(){}}\nstruct Panel{void run();};\nvoid Panel::run(){helper();}\n"
    source.write_bytes(raw)
    semantic = semantic_entry(tmp_path)
    direct = extraction.extract_cpp(source)
    target = next(node["id"] for node in direct["nodes"] if node.get("label") == "helper()")
    assert any(edge.get("relation") == "calls" and edge.get("target") == target for edge in direct["edges"])
    stale = copy.deepcopy(direct)
    for node in stale["nodes"]:
        node.get("metadata", {}).get("cpp_function", {}).pop("anonymous_scope_proof", None)
    stale["edges"] = [edge for edge in stale["edges"]
                      if not (edge.get("relation") == "calls" and edge.get("target") == target)]
    with monkeypatch.context() as predecessor:
        predecessor.setattr(cache, "_AST_CACHE_SCHEMA", 37)
        cache.save_cached(source, stale, root=tmp_path)
        prior = cache.cache_dir(tmp_path)
        accepted = cache.load_cached(source, root=tmp_path)
        assert accepted is not None and list(prior.glob("*.json"))
        assert not any(edge.get("relation") == "calls" and edge.get("target") == target
                       for edge in accepted["edges"])
        assert not any(node.get("metadata", {}).get("cpp_function", {}).get("anonymous_scope_proof")
                       for node in accepted["nodes"])
    assert cache.load_cached(source, root=tmp_path) is None
    assert cache._AST_CACHE_SCHEMA == 40
    assert not prior.exists() and source.read_bytes() == raw
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not cold["failed_sources"] and not warm["failed_sources"]
    for result in (cold, warm):
        helper = next(node["id"] for node in result["nodes"] if node.get("label") == "helper()")
        assert any(edge.get("relation") == "calls" and edge.get("target") == helper for edge in result["edges"])
    assert normalized(build_from_json(cold, directed=True, root=tmp_path)) == normalized(
        build_from_json(warm, directed=True, root=tmp_path))
    assert source.read_bytes() == raw
    assert_semantic_preserved(tmp_path, semantic)


def test_req_qml022_ac06_schema38_missing_direct_origin_reparses_source_roles(
        tmp_path, monkeypatch, current_cache):
    """A successful unmarked38 fragment cannot replay the direct definition/prototype collapse."""
    source = tmp_path / "panel.cpp"
    raw = (b"void helper(){}\nstruct Panel{void run();};\n"
           b"void Panel::run(){helper();}\nnamespace{void helper();}\n")
    source.write_bytes(raw)
    semantic = semantic_entry(tmp_path)
    direct = extraction.extract_cpp(source)
    stale = copy.deepcopy(direct)
    facts = [node for node in stale["nodes"]
             if any(key in node.get("metadata", {}) for key in ("cpp_function", "cpp_prototype"))]
    assert facts and all(node.get("_origin") == "ast" for node in facts)
    for node in facts:
        node.pop("_origin")
    with monkeypatch.context() as predecessor:
        predecessor.setattr(cache, "_AST_CACHE_SCHEMA", 38)
        cache.save_cached(source, stale, root=tmp_path)
        directory = cache.cache_dir(tmp_path)
        accepted = cache.load_cached(source, root=tmp_path)
        assert accepted is not None and list(directory.glob("*.json"))
        assert all(node.get("_origin") is None for node in accepted["nodes"]
                   if any(key in node.get("metadata", {}) for key in ("cpp_function", "cpp_prototype")))
    assert cache.load_cached(source, root=tmp_path) is None and cache._AST_CACHE_SCHEMA == 40
    assert not directory.exists() and source.read_bytes() == raw
    cold = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    warm = extraction.extract([source], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert cold == warm and not cold["failed_sources"]
    for result in (direct, cold, warm):
        graph = build_from_json(copy.deepcopy(result), directed=True, root=tmp_path)
        calls = [(target, data) for _, target, data in graph.edges(data=True)
                 if data.get("relation") == "calls" and graph.nodes[target].get("label") == "helper()"]
        (target, edge), = calls
        assert edge["confidence"] == "EXTRACTED"
        assert graph.nodes[target]["metadata"]["cpp_function"]["role"] == "definition"
        assert graph.nodes[target]["metadata"]["cpp_function"]["namespace_status"] == "available"
        assert any(node.get("metadata", {}).get("cpp_prototype", {}).get("scope_status") == "anonymous"
                   for _, node in graph.nodes(data=True))
    assert source.read_bytes() == raw
    assert_semantic_preserved(tmp_path, semantic)
