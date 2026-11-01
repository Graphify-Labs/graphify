"""INC-QML-37: independent cross-language event occurrences keep bounded metadata."""
from __future__ import annotations

import json
import os
import stat

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis
from tests.test_qt_access_providers import BACKEND, QML


def sources(root, count, *, mixed=True):
    """Each actual source call alternates native/QML direction and operation."""
    statements = []
    for index in range(count):
        operation = "disconnect" if mixed and index % 4 >= 2 else "connect"
        parameters = ('root, SIGNAL(closed()), backend, SLOT(close())' if index % 2 == 0
                      else 'backend, SIGNAL(changed()), root, SLOT(refresh())')
        statements.append(f' QObject::{operation}({parameters});\n')
    source = BACKEND + f'''void use(Backend *backend) {{ QQuickView view;
 view.setSource(QUrl("{(root / 'Main.qml').as_uri()}")); auto root = view.rootObject();
''' + ''.join(statements) + '}\n'
    return {"access.cpp": source, "Main.qml": QML,
            "keep.py": "def helper(): return 7\ndef untouched(): return helper()\n"}


def assert_events(graph, count):
    """Site-owned role nodes and edges retain their own operation/direction/span."""
    events = [(identity, node, qt_metadata(node)) for identity, node in graph.nodes(data=True)
              if qt_metadata(node).get("kind") in {"connect", "disconnect"}]
    assert len(events) == count
    for identity, node, md in events:
        assert md["status"] == "resolved", md
        endpoints = [(role_id, role, qt_metadata(role)) for role_id, role in graph.nodes(data=True)
                     if qt_metadata(role).get("kind") == "event_endpoint"
                     and qt_metadata(role).get("owner_id") == identity]
        assert {values["role"] for _, _, values in endpoints} == {"signal", "receiver"}
        for role_id, role, values in endpoints:
            assert values["span"] == md["span"] and role["source_location"] == node["source_location"]
            assert values["bridge_direction"] == md["bridge_direction"]
            assert graph.has_edge(identity, role_id)
            target = values["target_id"]
            assert graph.has_edge(role_id, target)
            available = graph.get_edge_data(role_id, target)
            available = list(available.values()) if graph.is_multigraph() else [available]
            matching = [edge for edge in available
                        if edge.get("context") == f'qt_qml_{md["kind"]}_{values["role"]}']
            assert len(matching) == 1
            edge = matching[0]
            proof = qt_metadata(edge)
            assert edge["relation"] == "references"
            assert edge["context"] == f'qt_qml_{md["kind"]}_{values["role"]}'
            assert proof["bridge_direction"] == md["bridge_direction"] and proof["span"] == md["span"]
            assert not any(key.startswith("raw_values/") for key in edge["metadata"]["qt"]["raw_values"])
    assert any(node.get("source_file") == "keep.py" for _, node in graph.nodes(data=True))


@pytest.mark.parametrize("count", [1, 2, 3, 4, 8, 16])
@pytest.mark.parametrize("mixed", [False, True])
@pytest.mark.parametrize("directed", [False, True])
def test_req_qml016_ac02_ac04_cross_language_occurrences_keep_own_transport(tmp_path, count, mixed, directed):
    """Real facade/build/writer/reload retain every repeated connect/disconnect occurrence."""
    result = analysis(tmp_path, sources(tmp_path, count, mixed=mixed))
    # Decode every producer edge before graph assembly; repeated encoding cannot
    # quietly erase an earlier valid endpoint through the projection guard.
    for edge in result["edges"]:
        qt_metadata(edge)
    graph = build_from_json(result, root=tmp_path, directed=directed)
    assert_events(graph, count)
    output = tmp_path / "accepted.json"
    assert to_json(graph, {}, str(output), force=True)
    assert_events(load_node_link_graph(json.loads(output.read_bytes())), count)


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac04_cross_event_edits_removal_and_repeat_match_clean(tmp_path, monkeypatch, operation):
    """Real C++-only and QML-only edits retire stale endpoints and preserve unrelated code."""
    from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated

    analysis(tmp_path, sources(tmp_path, 8))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    assert_events(initial, 8)
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold-cache"))
    other = unrelated(initial)
    cpp = tmp_path / "access.cpp"
    original = cpp.read_bytes()
    statements = original.splitlines(keepends=True)
    cpp.write_bytes(b''.join(line for line in statements if b'QObject::disconnect' not in line))
    edited = run(tmp_path, monkeypatch, operation, [cpp])
    assert_events(edited, 4)
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited-cache"))
    assert unrelated(edited) == other
    qml = tmp_path / "Main.qml"
    original_qml = qml.read_bytes()
    qml.write_bytes(original_qml.replace(b'signal closed()', b'signal stopped()'))
    changed = run(tmp_path, monkeypatch, operation, [qml])
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".qml-cache"))
    assert unrelated(changed) == other
    qml.write_bytes(original_qml)
    cpp.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [cpp, qml])
    assert_events(restored, 8)
    assert normalized(restored) == normalized(initial)
    output = tmp_path / "graphify-out/graph.json"
    before = output.read_bytes(), output.stat().st_mtime_ns
    assert normalized(run(tmp_path, monkeypatch, operation)) == normalized(restored)
    assert (output.read_bytes(), output.stat().st_mtime_ns) == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml011_ac03_event_policy_refreshes_unchanged_source(tmp_path, monkeypatch, operation):
    """The previous policy checkpoint cannot authorize the new derived event contract."""
    import graphify.qt_incremental as policy
    from tests.test_qt_final_incremental_parity import normalized, run

    analysis(tmp_path, sources(tmp_path, 4))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    with monkeypatch.context() as older:
        older.setattr(policy, "QT_POLICY_VERSION", policy.QT_POLICY_VERSION - 1)
        prior = run(tmp_path, monkeypatch, operation)
    checkpoint = tmp_path / "graphify-out/.qt_analysis.json"
    old_bytes = checkpoint.read_bytes()
    refreshed = run(tmp_path, monkeypatch, operation, [])
    assert checkpoint.read_bytes() != old_bytes
    assert normalized(refreshed) == normalized(prior)
    assert_events(refreshed, 4)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows read-only publication boundary")
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml018_ac06_cross_event_publication_failure_retains_prior_and_retries(tmp_path, monkeypatch, operation):
    """Actual destination failure preserves accepted events/cache before successful repaired retry."""
    from graphify.cache import cache_dir
    from graphify.watch import _rebuild_code
    from tests.test_qt_final_incremental_parity import clean, normalized, run
    from tests.test_qt_readonly_publication import durable

    analysis(tmp_path, sources(tmp_path, 4))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    accepted = durable(tmp_path)
    cached = {path: path.read_bytes() for path in cache_dir(tmp_path).rglob("*.json")}
    assert cached
    analysis(tmp_path, sources(tmp_path, 8))
    cpp = tmp_path / "access.cpp"
    target = tmp_path / "graphify-out/graph.json"
    target.chmod(stat.S_IREAD)
    try:
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, monkeypatch, operation, [cpp])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
        assert durable(tmp_path) == accepted
        assert all(path.read_bytes() == data for path, data in cached.items())
        assert_events(initial, 4)
    finally:
        target.chmod(stat.S_IWRITE)
    repaired = run(tmp_path, monkeypatch, operation, [cpp])
    assert_events(repaired, 8)
    assert normalized(repaired) == normalized(clean(tmp_path, tmp_path / ".repaired-cache"))
    accepted = durable(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation)) == normalized(repaired)
    assert durable(tmp_path) == accepted
