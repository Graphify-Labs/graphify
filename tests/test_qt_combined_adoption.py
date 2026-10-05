"""REQ-QML-018-AC05/AC06/AC07: combined profile through actual CLI and durable consumers."""
from __future__ import annotations

import json
import os

import pytest

import graphify.extract as extraction
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph

from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_combined_adoption_fixture import corpus
from tests.test_qt_final_incremental_parity import normalized, run


def accepted(graph):
    """Assert exact source-backed APIs, subscriptions and constructor emission ownership."""
    bindings = [qt_metadata(node) for _, node in graph.nodes(data=True)
                if qt_metadata(node).get("kind") == "context_binding"]
    assert len(bindings) == 1
    accesses = [qt_metadata(node) for _, node in graph.nodes(data=True)
                if qt_metadata(node).get("kind") == "context_access"]
    assert len(accesses) >= 3 and all(md["status"] == "resolved" for md in accesses)
    subscriptions = [(identity, qt_metadata(node)) for identity, node in graph.nodes(data=True)
                     if qt_metadata(node).get("kind") == "context_subscription"]
    assert len(subscriptions) == 2 and all(md["status"] == "resolved" for _, md in subscriptions)
    for identity, _ in subscriptions:
        assert not any(edge.get("relation") == "calls" for _, _, edge in graph.edges(identity, data=True))
    emissions = [qt_metadata(node) for _, node in graph.nodes(data=True)
                 if qt_metadata(node).get("kind") == "emission"]
    assert len(emissions) == 1 and emissions[0]["status"] == "resolved"
    owner = graph.nodes[emissions[0]["owner_id"]]
    assert owner.get("metadata", {}).get("cpp_constructor")
    assert qt_metadata(graph.nodes[emissions[0]["target_id"]])["class_name"] == "Grand"
    imports = [qml_metadata(node) for _, node in graph.nodes(data=True)
               if qml_metadata(node).get("kind") == "import_resolution"
               and node.get("label") == "Public.Extra"]
    assert imports and all(md["status"] == "resolved" for md in imports)


def clean(root, cache):
    """Use the same explicit analysis roots as the CLI; the facade owns no ambient config."""
    paths = extraction.collect_files(root, root=root)
    result = extraction.extract(paths, root=root, cache_root=cache, parallel=False,
                                qml_import_roots=tuple(json.loads(os.environ["GRAPHIFY_QML_IMPORT_ROOTS"])))
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=root)
    path = root / "graphify-out/combined-comparison.json"
    assert to_json(graph, {}, str(path), force=True)
    return load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("build_system", ["cmake", "qmake"])
@pytest.mark.parametrize("scope", ["whole", "subfolder"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates(tmp_path, monkeypatch, build_system, scope, operation):
    """Each explicit root has its own stable IDs; no cross-root rebasing is inferred."""
    app = corpus(tmp_path, build_system)
    root = tmp_path if scope == "whole" else app
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["app/imports"]' if scope == "whole" else '["imports"]')
    baseline = clean(root, root / ".cold-cache")
    accepted(baseline)
    assert normalized(clean(root, root / ".cold-cache")) == normalized(baseline)
    actual = run(root, monkeypatch, operation)
    accepted(actual)
    assert normalized(actual) == normalized(baseline)
    assert normalized(run(root, monkeypatch, operation, [])) == normalized(actual)
    # QML-only edits rejoin provider and callback declarations from unchanged C++.
    path = app / "Main.qml"
    path.write_bytes(path.read_bytes().replace(b"handleReady", b"received"))
    edited = run(root, monkeypatch, operation, [path])
    accepted(edited)
    assert normalized(edited) == normalized(clean(root, root / ".edited-cache"))
