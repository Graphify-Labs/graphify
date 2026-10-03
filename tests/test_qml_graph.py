"""QML-01 mixed-language, graph projection and spawned-worker boundaries."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import multiprocessing

import networkx as nx

from graphify.build import build_from_json
from graphify.extract import _extract_single_file, extract
from graphify.extractors.qml import extract_qml
from graphify.validate import validate_extraction
from tests.qml_test_helpers import by_kind, canonical, qml, write_qml


def test_qml010_ac02_directed_build_and_reload_keep_all_ownership_and_qml_metadata(tmp_path):
    """Existing graph assembly preserves distinct source-backed declarations and edges."""
    extraction = extract_qml(write_qml(tmp_path), root=tmp_path)
    graph = build_from_json(extraction, directed=True, root=tmp_path)
    assert graph.is_directed()
    assert set(graph) == {node["id"] for node in extraction["nodes"]}
    expected = {(edge["source"], edge["target"], edge["relation"]) for edge in extraction["edges"]}
    assert {(source, target, data["relation"]) for source, target, data in graph.edges(data=True)} == expected
    serialized = json.loads(json.dumps(nx.node_link_data(graph, edges="edges"), ensure_ascii=False))
    restored = nx.node_link_graph(serialized, edges="edges")
    assert set(restored) == set(graph)
    assert all(restored.nodes[node["id"]]["metadata"]["qml"] == node["metadata"]["qml"] for node in extraction["nodes"])
    assert all(restored.edges[source, target]["confidence"] == "EXTRACTED" for source, target in restored.edges)


def test_qml003_ac02_same_stem_cpp_js_and_qml_do_not_merge(tmp_path):
    """Generic same-stem producers cannot overwrite hashed QML file/member ownership."""
    qml_path = write_qml(tmp_path, "Panel.qml", "Item { property int value: 1; function run() { return value; } }\n")
    cpp_path, js_path = tmp_path / "Panel.cpp", tmp_path / "Panel.js"
    cpp_path.write_text("int run() { return 1; }\n", encoding="utf-8")
    js_path.write_text("export function run() { return 2; }\n", encoding="utf-8")
    direct = extract_qml(qml_path, root=tmp_path)
    batch = extract([qml_path, cpp_path, js_path], cache_root=tmp_path / "cache", root=tmp_path, parallel=False)
    qml_nodes = [node for node in batch["nodes"] if node.get("metadata", {}).get("qml")]
    assert len(qml_nodes) == len(direct["nodes"])
    assert {node["id"] for node in qml_nodes} == {node["id"] for node in direct["nodes"]}
    assert {node["source_file"] for node in batch["nodes"]} >= {"Panel.qml", "Panel.cpp", "Panel.js"}
    assert validate_extraction(batch) == []


def test_qml003_ac04_batch_filesystem_order_and_warm_cache_do_not_change_facts(tmp_path):
    """Production cache/reordering cannot remove declarations or scope metadata."""
    paths = [write_qml(tmp_path, relative) for relative in ("left/Main.qml", "right/Main.qml")]
    kwargs = {"cache_root": tmp_path / "cache", "root": tmp_path, "parallel": False}
    cold = extract(paths, **kwargs)
    warm = extract(list(reversed(paths)), **kwargs)
    assert canonical(cold) == canonical(warm)
    assert len(by_kind(cold, "component")) == 2
    assert len({node["id"] for node in cold["nodes"]}) == len(cold["nodes"])


def test_qml003_ac04_spawned_worker_retains_explicit_root_and_scope_ids(tmp_path):
    """A real spawn worker runs the registered production path, without fallback fakes."""
    path = write_qml(tmp_path, "ui/Main.qml")
    direct = extract_qml(path, root=tmp_path)
    context = multiprocessing.get_context("spawn")
    work = (0, str(path), str(tmp_path), str(tmp_path / "worker-cache"))
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as pool:
        index, result = pool.submit(_extract_single_file, work).result(timeout=45)
    assert index == 0 and canonical(result) == canonical(direct)
    assert all(node["source_file"] == "ui/Main.qml" for node in result["nodes"])
    assert len({qml(node)["component_key"] for node in by_kind(result, "object")}) == 1
