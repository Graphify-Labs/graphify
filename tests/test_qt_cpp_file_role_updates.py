"""INC-QML-33/35 retain file roles and retire only stale generated import endpoints."""
from __future__ import annotations

import json
import os
import stat

import pytest

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_cpp_file_roles import cpp_fixture
from tests.test_qt_final_incremental_parity import clean, normalized, run


def cpp_membership(graph):
    """The C++ endpoint is its original generic file ID, never a guessed class."""
    return next(qml_metadata(node) for _, node in graph.nodes(data=True)
                if qml_metadata(node).get("kind") == "membership_resolution"
                and qml_metadata(node).get("source_kind") == "cpp")


def assert_file_context(graph):
    target = cpp_membership(graph)["target_id"]
    assert target and graph.nodes[target]["source_file"] == "backend.cpp"
    unknown = [identity for identity, node in graph.nodes(data=True)
               if qt_metadata(node).get("kind") == "emission" and not qt_metadata(node).get("owner_id")]
    assert unknown and all(graph.has_edge(target, identity) for identity in unknown)
    assert all(any(endpoint == identity and data.get("context") == "qt_source_file"
                   and data["relation"] == "contains" and data["confidence"] == "EXTRACTED"
                   for _, endpoint, data in graph.edges(target, data=True)) for identity in unknown)
    return target


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml020_ac03_cpp_transport_edits_and_removal_preserve_exact_membership(tmp_path, monkeypatch, operation):
    """Cold/warm/manual/watch/JSON products retain file roles as native type proof changes."""
    cpp_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold-cache")
    assert normalized(clean(tmp_path, tmp_path / ".cold-cache")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    file_id = assert_file_context(initial)
    path = tmp_path / "backend.cpp"
    original = path.read_bytes()

    # Namespace-import type authority is conservatively incomplete, but the
    # accepted file still owns source context and explicit build membership.
    path.write_bytes(original.replace(b"using QObject = int;", b"using namespace Hidden;"))
    changed = run(tmp_path, monkeypatch, operation, [path])
    assert assert_file_context(changed) == file_id
    assert changed.nodes[file_id]["metadata"]["cpp_constructor_types"]["complete"] is False
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".changed-cache"))
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(changed)

    # An unavailable source cannot keep its unchanged module declaration's
    # previous endpoint; restoration produces the same accepted file identity.
    path.unlink()
    removed = run(tmp_path, monkeypatch, operation, [path])
    assert file_id not in removed
    assert "missing" not in removed, "Deleted C++ source left its generated include endpoint"
    assert cpp_membership(removed)["status"] == "unavailable"
    assert not cpp_membership(removed)["target_id"]
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    path.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [path])
    assert assert_file_context(restored) == file_id
    assert "missing" in restored
    assert normalized(restored) == normalized(initial)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(restored)


def products(root):
    return {name: (root / "graphify-out" / name).read_bytes()
            for name in ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")}


def has_import(graph, source):
    return any(data.get("relation") == "imports" and data.get("source_file") == source
               and data.get("_origin") == "ast"
               for _, _, data in graph.edges("missing", data=True))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_cpp_deleted_import_keeps_still_referenced_external_endpoint(tmp_path, monkeypatch, operation):
    """A second real import protects the shared endpoint until its final source reference disappears."""
    cpp_fixture(tmp_path)
    keeper = tmp_path / "keeper.cpp"
    original = b'#include "missing.hpp"\nint keep() { return 1; }\n'
    keeper.write_bytes(original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert has_import(initial, "backend.cpp") and has_import(initial, "keeper.cpp")
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".initial-cache"))
    source = tmp_path / "backend.cpp"
    backend = source.read_bytes()
    source.unlink()
    removed = run(tmp_path, monkeypatch, operation, [source])
    assert "missing" in removed and has_import(removed, "keeper.cpp")
    assert not has_import(removed, "backend.cpp")
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))

    # Removing the final import is a real C++ edit, independent of metadata
    # membership and the earlier source deletion. Re-addition restores its ID.
    keeper.write_bytes(original.split(b"\n", 1)[1])
    edited = run(tmp_path, monkeypatch, operation, [keeper])
    assert "missing" not in edited
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited-cache"))
    keeper.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [keeper])
    assert "missing" in restored and has_import(restored, "keeper.cpp")
    assert normalized(restored) == normalized(removed)
    source.write_bytes(backend)
    restored = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(restored) == normalized(initial)
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(restored)
    assert products(tmp_path) == before


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_cpp_orphan_cleanup_failed_publication_preserves_products_and_retries(tmp_path, monkeypatch, operation):
    """Real graph-write rejection preserves old products/cache; deletion retry retires the orphan."""
    from graphify.watch import _rebuild_code
    from graphify.cache import cache_dir
    from tests.test_qt_final_incremental_parity import published
    from tests.test_qt_readonly_publication import durable

    cpp_fixture(tmp_path)
    # Qt cohort sources deliberately bypass individual AST reuse. An unrelated
    # real Python source supplies old cache bytes that rejected publication must
    # preserve, rather than fabricating an entry or claiming an empty cache.
    (tmp_path / "keep.py").write_bytes(b"def untouched(): return 7\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert "missing" in initial
    accepted = durable(tmp_path)
    cache = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*.json")}
    assert cache
    source = tmp_path / "backend.cpp"
    original = source.read_bytes()
    source.unlink()
    target = tmp_path / "graphify-out/graph.json"
    target.chmod(stat.S_IREAD)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, monkeypatch, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
        assert durable(tmp_path) == accepted
        assert all(path.exists() and path.read_bytes() == data for path, data in cache.items())
        assert normalized(published(tmp_path)) == normalized(initial)
        assert not target.stat().st_mode & stat.S_IWRITE
        assert not list(target.parent.glob(".gfy-*.tmp"))
    finally:
        target.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert "missing" not in repaired
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".repaired-cache"))
    accepted = durable(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(repaired)
    assert durable(tmp_path) == accepted
    source.write_bytes(original)
    assert normalized(run(tmp_path, monkeypatch, operation, [source])) == normalized(initial)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_cpp_import_cleanup_preserves_same_label_source_and_semantic_roles(tmp_path, monkeypatch, operation):
    """Exact endpoint identity controls cleanup; equal display labels do not erase unrelated facts."""
    cpp_fixture(tmp_path)
    (tmp_path / "keeper.cpp").write_bytes(b"class missing {};\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    source_owned = next(identity for identity, node in initial.nodes(data=True)
                        if node.get("label") == "missing" and node.get("source_file") == "keeper.cpp")
    output = tmp_path / "graphify-out/graph.json"
    raw = json.loads(output.read_text(encoding="utf-8"))
    retained = [{"id": "authored_missing", "label": "missing", "type": "external", "external": True,
                 "file_type": "concept", "source_file": "", "_origin": "semantic"},
                {"id": "manual_missing", "label": "missing", "type": "concept",
                 "file_type": "concept", "source_file": ""}]
    raw["nodes"].extend(retained)
    output.write_text(json.dumps(raw), encoding="utf-8")
    source = tmp_path / "backend.cpp"
    source.unlink()
    removed = run(tmp_path, monkeypatch, operation, [source])
    assert "missing" not in removed
    assert {"authored_missing", "manual_missing", source_owned} <= set(removed)
    assert removed.nodes["authored_missing"]["_origin"] == "semantic"
    expected_nodes, expected_edges = normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    actual_nodes, actual_edges = normalized(removed)
    assert set(actual_nodes) == set(expected_nodes) | {node["id"] for node in retained}
    assert all(actual_nodes[identity] == data for identity, data in expected_nodes.items())
    assert actual_edges == expected_edges
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)
    assert products(tmp_path) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("corruption", ["semantic_origin", "unmarked_origin", "foreign_source",
                                         "conflicting_source", "context", "confidence", "opposite_direction",
                                         "metadata", "metadata_empty", "foreign_origin", "ast_origin",
                                         "callable", "type", "source", "label",
                                         "partial_direction", "foreign_direction"])
def test_req_qml011_ac04_cpp_import_cleanup_requires_exact_prior_source_proof(tmp_path, monkeypatch, operation, corruption):
    """Retired unproved imports cannot authorize cleanup, even when the remaining candidate is valid."""
    cpp_fixture(tmp_path)
    (tmp_path / "keeper.cpp").write_bytes(b"int retained() { return 7; }\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    run(tmp_path, monkeypatch, operation)
    output = tmp_path / "graphify-out/graph.json"
    raw = json.loads(output.read_bytes())
    edge = next(edge for edge in raw["links"] if edge.get("relation") == "imports"
                and edge.get("source_file") == "backend.cpp")
    if corruption == "semantic_origin":
        edge["_origin"] = "semantic"
    elif corruption == "unmarked_origin":
        edge.pop("_origin")
    elif corruption in {"foreign_source", "conflicting_source"}:
        edge["source_file"] = "foreign.cpp" if corruption == "foreign_source" else "keeper.cpp"
    elif corruption in {"context", "confidence"}:
        edge[corruption] = "unproved"
    elif corruption == "opposite_direction":
        edge["_src"], edge["_tgt"] = edge["target"], edge["source"]
    elif corruption in {"metadata", "metadata_empty", "foreign_origin", "ast_origin", "callable", "type", "source", "label"}:
        target = next(node for node in raw["nodes"] if node["id"] == "missing")
        key, value = {"metadata": ("metadata", {"note": "authored context"}),
                      "metadata_empty": ("metadata", {}), "foreign_origin": ("_origin", "foreign"),
                      "ast_origin": ("_origin", "ast"), "callable": ("_callable", True),
                      "type": ("type", "class"), "source": ("source_file", "keeper.cpp"),
                      "label": ("label", "authored display")}[corruption]
        target[key] = value
    else:
        edge["_src"] = edge["source"] if corruption == "partial_direction" else "foreign_endpoint"
        if corruption == "foreign_direction":
            edge["_tgt"] = edge["target"]
    output.write_text(json.dumps(raw), encoding="utf-8")
    source = tmp_path / "backend.cpp"
    source.unlink()
    removed = run(tmp_path, monkeypatch, operation, [source])
    assert "missing" in removed and removed.degree("missing") == 0
    expected_nodes, expected_edges = normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    actual_nodes, actual_edges = normalized(removed)
    assert set(actual_nodes) == set(expected_nodes) | {"missing"}
    assert all(actual_nodes[identity] == data for identity, data in expected_nodes.items())
    assert actual_edges == expected_edges
    if corruption == "metadata":
        assert removed.nodes["missing"]["metadata"] == {"note": "authored context"}
