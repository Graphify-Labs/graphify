"""REQ-QML-007/008/017: native notification refresh and durable recovery."""
from __future__ import annotations

import json

import pytest

from graphify.affected import affected_nodes, load_graph
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import collect_files, extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from graphify.qml_resolution_types import qml_metadata
from tests.qt_consumer_helpers import cli as consumer_cli
from tests.test_qt_final_incremental_parity import normalized, run, unrelated
from tests.test_qt_loader_updates import products
from tests.test_qt_native_property_notify import sources


def fixture(root, *, directed=False):
    """Only literal declarations/providers participate; unrelated Python stays fixed."""
    files = sources(parameters="int count")
    files["Main.qml"] = ('import QtQml\nimport Public.Tools 1.0\n'
                         'Backend { onCountChanged: (renamed) => { count; renamed; } }\n')
    files["keep.py"] = 'def helper(): return 7\n\ndef retained(): return helper()\n'
    for name, source in files.items():
        (root / name).write_bytes(source.encode())
    if directed:
        output = root / "graphify-out"
        output.mkdir()
        # Seed through real analysis/export; update inherits this accepted direction.
        assert to_json(cold(root, root / ".seed", directed=True), {}, str(output / "graph.json"), force=True)
    return root / "backend.h"


def cold(root, cache, *, directed=False):
    """A separate real facade/build/export baseline checks every public fact."""
    result = extract(collect_files(root, root=root), root=root, cache_root=cache, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=root, directed=directed)
    output = root / "graphify-out"
    output.mkdir(exist_ok=True)
    path = output / "notify-comparison.json"
    assert to_json(graph, {}, str(path), force=True)
    return load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))


def subscription(graph, *, expected: str | None = "updated"):
    """A handler owns a reference to the actual signal, never delivery/call inference."""
    handlers = {identity: qml_metadata(data) for identity, data in graph.nodes(data=True)
                if qml_metadata(data).get("kind") == "handler"}
    edges = [(data.get("_src", a), data.get("_tgt", b), data) for a, b, data in graph.edges(data=True)
             if data.get("context") == "qml_signal_subscription"]
    assert len(handlers) == 1
    if expected is None:
        assert not edges and all(md["status"] != "resolved" and not md["resolved_target_id"] for md in handlers.values())
        return handlers, edges
    assert len(edges) == 1
    source, target, edge = edges[0]
    assert source in handlers and handlers[source]["resolved_target_id"] == target
    assert handlers[source]["status"] == "resolved" and edge["relation"] == "references"
    assert graph.nodes[target]["label"].lstrip(".") == expected + "()"
    proof = qt_metadata(edge)["native_endpoint"]
    assert proof["kind"] == "signal" and proof["canonical_target_id"] == target
    assert graph.nodes[target]["source_file"] == "backend.h"
    assert graph.has_edge(source, target)
    if graph.is_directed():
        assert not graph.has_edge(target, source)
    assert not any(data.get("relation") == "calls" for a, b, data in graph.edges(data=True)
                   if data.get("_src", a) == source)
    return handlers, edges


@pytest.mark.parametrize("mode", ["manual", "watch"])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml017_ac04_notify_edits_remove_stale_edges_with_full_parity(tmp_path, monkeypatch, capsys, mode, directed):
    """C++/QML/provider-only edits, removal and repeated refresh preserve source facts."""
    header = fixture(tmp_path, directed=directed)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, mode)
    assert initial.is_directed() is directed
    assert normalized(initial) == normalized(cold(tmp_path, tmp_path / ".cold", directed=directed))
    assert normalized(initial) == normalized(cold(tmp_path, tmp_path / ".cold", directed=directed))
    original_handlers, old_links = subscription(initial)
    old_target, untouched = old_links[0][1], unrelated(initial)
    valid = header.read_bytes()
    header.write_bytes(valid.replace(b"updated", b"revised"))
    renamed = run(tmp_path, monkeypatch, mode, [header])
    handlers, edges = subscription(renamed, expected="revised")
    assert set(handlers) == set(original_handlers) and old_target not in renamed
    assert normalized(renamed) == normalized(cold(tmp_path, tmp_path / ".renamed", directed=directed))
    output = tmp_path / "graphify-out/graph.json"
    source, target, _ = edges[0]
    assert "Main.qml" in consumer_cli(monkeypatch, capsys, output, "explain", source)
    assert "revised" in consumer_cli(monkeypatch, capsys, output, "query", source)
    assert source in {hit.node_id for hit in affected_nodes(load_graph(output), target, relations=["references"], depth=1)}
    header.write_bytes(valid)
    assert normalized(run(tmp_path, monkeypatch, mode, [header])) == normalized(initial)

    qml = tmp_path / "Main.qml"
    original_qml = qml.read_bytes()
    qml.write_bytes(original_qml.replace(b"onCountChanged", b"onUnknownChanged"))
    changed = run(tmp_path, monkeypatch, mode, [qml])
    subscription(changed, expected=None)
    assert normalized(changed) == normalized(cold(tmp_path, tmp_path / ".qml", directed=directed))
    qml.write_bytes(original_qml.replace(b"(renamed) => { count; renamed; }", b"{ count; }"))
    injected = run(tmp_path, monkeypatch, mode, [qml])
    subscription(injected)
    reads = [qml_metadata(data) for _, data in injected.nodes(data=True)
             if qml_metadata(data).get("kind") == "read" and qml_metadata(data).get("reference") == "count"]
    assert len(reads) == 1 and reads[0]["status"] == "dynamic" and reads[0]["reason"] == "javascript_lexical_binding"
    assert normalized(injected) == normalized(cold(tmp_path, tmp_path / ".legacy", directed=directed))
    qml.write_bytes(original_qml)
    subscription(run(tmp_path, monkeypatch, mode, [qml]))

    provider = tmp_path / "tools.pro"
    original_provider = provider.read_bytes()
    provider.write_bytes(original_provider.replace(b"Public.Tools", b"Public.Other"))
    missing = run(tmp_path, monkeypatch, mode, [provider])
    subscription(missing, expected=None)
    assert normalized(missing) == normalized(cold(tmp_path, tmp_path / ".provider", directed=directed))
    assert header.read_bytes() == valid
    provider.write_bytes(original_provider)
    subscription(run(tmp_path, monkeypatch, mode, [provider]))

    header.write_bytes(valid.replace(b"NOTIFY updated", b""))
    removed = run(tmp_path, monkeypatch, mode, [header])
    subscription(removed, expected=None)
    assert normalized(removed) == normalized(cold(tmp_path, tmp_path / ".removed", directed=directed))
    assert unrelated(removed) == untouched
    durable = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(removed)
    assert products(tmp_path) == durable


@pytest.mark.parametrize("mode", ["manual", "force", "watch"])
@pytest.mark.parametrize("input_file", ["backend.h", "Main.qml"])
def test_req_qml017_ac04_notify_parse_failure_retains_products_and_recovers(tmp_path, monkeypatch, mode, input_file):
    """Actual malformed native/QML input preserves all four accepted durable products."""
    fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    normal = "manual" if mode == "force" else mode
    initial = run(tmp_path, monkeypatch, normal)
    subscription(initial)
    path = tmp_path / input_file
    original, durable = path.read_bytes(), products(tmp_path)
    path.write_bytes(original + (b"\r\nvoid broken({" if input_file.endswith(".h") else b"\r\nQtObject {"))
    if mode == "watch":
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[path], no_cluster=True)
    else:
        with pytest.raises(SystemExit) as failure:
            if mode == "force":
                from tests.test_qt_cpp_upgrade_invalidation import cli
                cli(tmp_path, monkeypatch, "update", force=True)
            else:
                run(tmp_path, monkeypatch, normal, [path])
        assert failure.value.code == 1
    assert products(tmp_path) == durable
    path.write_bytes(original)
    assert normalized(run(tmp_path, monkeypatch, normal, [path])) == normalized(initial)
    repaired = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, normal, [])) == normalized(initial)
    assert products(tmp_path) == repaired


@pytest.mark.parametrize("mode", ["manual", "watch"])
def test_req_qml017_ac04_notify_manifest_failure_rolls_back_and_retries(tmp_path, monkeypatch, mode):
    """A real post-graph manifest replacement failure rolls the entire cohort back."""
    import graphify.watch as watch
    header = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, mode)
    subscription(initial)
    durable = products(tmp_path)
    header.write_bytes(header.read_bytes().replace(b"updated", b"revised"))
    replace, attempts = watch.os_replace_with_fallback, []

    def fail_once(start, destination):
        if str(destination).endswith("manifest.json") and not attempts:
            attempts.append(str(destination))
            raise PermissionError("injected native-notify manifest replacement failure")
        return replace(start, destination)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", fail_once)
        if mode == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failure, mode, [header])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[header], no_cluster=True)
    assert attempts and products(tmp_path) == durable
    recovered = run(tmp_path, monkeypatch, mode, [header])
    subscription(recovered, expected="revised")
    assert normalized(recovered) != normalized(initial)
    assert normalized(recovered) == normalized(cold(tmp_path, tmp_path / ".retry"))
    repaired = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(recovered)
    assert products(tmp_path) == repaired
