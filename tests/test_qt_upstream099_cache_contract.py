"""INC-QML-60: new generic identities retain Qt ownership and cache rejection."""
from __future__ import annotations

import json

import pytest

import graphify.cache as cache
import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
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


@pytest.mark.parametrize("old_schema", [23, 31])
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
    assert cache._AST_CACHE_SCHEMA == 32
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
def test_req_qml014_ac03_cpp_alias_reference_needs_lexical_authority(tmp_path, qualified):
    """A written qualified alias resolves; a sibling namespace cannot borrow it."""
    source = tmp_path / "scope.hpp"
    spelling = "::Left::Count" if qualified else "Count"
    source.write_text("namespace Left { using Count = int; }\n"
                      f"namespace Right {{ class Holder {{ {spelling} *value; }}; }}\n",
                      encoding="utf-8")
    result = extraction.extract_cpp(source)
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
def test_req_qml014_ac03_reused_alias_node_cannot_supply_another_scope(tmp_path, same_line):
    """Even same-line aliases cannot borrow a node allocated in another scope."""
    source = tmp_path / "scope.hpp"
    separator = " " if same_line else "\n"
    source.write_text("namespace Left { using Count = int; }" + separator
                      + "namespace Right { using Count = double; class Holder { Count value; }; }\n",
                      encoding="utf-8")
    result = extraction.extract_cpp(source)
    by_id = {node["id"]: node for node in result["nodes"]}
    holder = next(node for node in result["nodes"] if node.get("label") == "Holder")
    references = [edge for edge in result["edges"]
                  if edge["source"] == holder["id"] and edge["relation"] == "references"]
    assert references and all(not by_id[edge["target"]].get("source_file") for edge in references)
