"""Real CLI/watch lifecycle for receiver, engine, alias and loader corrections."""
from __future__ import annotations

import pytest

import graphify.extract as extraction
import graphify.qt_incremental as policy
from graphify.affected import affected_nodes, load_graph, resolve_seed
from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


def fixture(root):
    """A public resource fixture keeps native handles fixed while parenting changes."""
    sources = {
        "Main.qml": 'import QtQuick\nItem { property int value: 9; '
                    'Item { objectName: "left"; property int value: 1; '
                    'Item { objectName: "deep"; property int value: 2 } } }',
        "access.cpp": 'void use() { QQuickView view; view.setSource(QUrl("qrc:/ui/Main.qml")); '
                      'auto root = view.rootObject(); auto left = root->findChild<QObject*>("left"); '
                      'left->property("value"); auto deep = left->findChild<QObject*>("deep"); }',
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
        "keep.py": 'def helper(): return 7\n\ndef retained(): return helper()\n',
    }
    for name, content in sources.items():
        (root / name).write_text(content, encoding="utf-8", newline="")
    return root / "Main.qml"


def access(graph):
    return {identity: qt_metadata(node) for identity, node in graph.nodes(data=True)
            if qt_metadata(node).get("kind") == "qml_access"}


def products(root):
    output = root / "graphify-out"
    return {name: (output / name).read_bytes() for name in
            ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")}


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_receiver_tree_and_member_updates_remove_stale_edges(tmp_path, monkeypatch, operation):
    """Lost child members cannot borrow the root; moved children cannot stay descendants."""
    source = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    original_cpp = (tmp_path / "access.cpp").read_bytes()
    initial = run(tmp_path, monkeypatch, operation)
    before = access(initial)
    assert len(before) == 3 and all(md["status"] == "resolved" for md in before.values())
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / ".cold"))
    consumer = load_graph(tmp_path / "graphify-out/graph.json")
    for identity, md in before.items():
        assert resolve_seed(initial, identity, tmp_path) == identity
        assert identity in {hit.node_id for hit in affected_nodes(consumer, md["target_id"], relations=["uses"], depth=1)}
    source.write_text('import QtQuick\nItem { property int value: 9; '
                      'Item { objectName: "left" } '
                      'Item { objectName: "deep"; property int value: 2 } }', encoding="utf-8")
    edited = run(tmp_path, monkeypatch, operation, [source])
    after = access(edited)
    assert set(after) == set(before)
    lost = [identity for identity, md in after.items() if md["status"] != "resolved"]
    assert len(lost) == 2
    for identity in lost:
        assert not after[identity].get("target_id")
        assert after[identity]["span"] == before[identity]["span"]
        assert not any(data.get("_src", start) == identity and data.get("relation") == "uses"
                       for start, _, data in edited.edges(data=True))
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited"))
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edited"))
    assert unrelated(initial) == unrelated(edited)
    assert (tmp_path / "access.cpp").read_bytes() == original_cpp
    assert normalized(run(tmp_path, monkeypatch, operation, [source])) == normalized(edited)
    unchanged = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(edited)
    assert products(tmp_path) == unchanged


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_policy_refresh_failure_retains_products_and_retry(tmp_path, monkeypatch, operation):
    """A same-package policy upgrade and real parse failure retain every accepted product."""
    source = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    with monkeypatch.context() as previous:
        previous.setattr(policy, "QT_POLICY_VERSION", 6)
        initial = run(tmp_path, previous, operation)
    before, observed, real = products(tmp_path), [], extraction.extract

    def observe(paths, **kwargs):
        observed.extend(paths)
        return real(paths, **kwargs)

    monkeypatch.setattr(extraction, "extract", observe)
    refreshed = run(tmp_path, monkeypatch, operation, [])
    assert tmp_path / "access.cpp" in observed and source in observed
    assert normalized(refreshed) == normalized(initial)
    assert products(tmp_path)[".qt_analysis.json"] != before[".qt_analysis.json"]
    valid, accepted = source.read_bytes(), products(tmp_path)
    source.write_text("Item { property int value: }", encoding="utf-8")
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            run(tmp_path, monkeypatch, operation, [source])
        assert rejected.value.code == 1
    else:
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert products(tmp_path) == accepted
    source.write_bytes(valid)
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(recovered) == normalized(refreshed)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)


@pytest.mark.parametrize("failure_stage", ["join", "replacement"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_failed_completion_keeps_prior_graph_and_retries(tmp_path, monkeypatch, operation, failure_stage):
    """Real resolution/write work must complete before accepted graph/state replacement."""
    import graphify.watch as watch
    from graphify.qt_qml_access_index import QtQmlAccessIndex
    from graphify.watch import _rebuild_code

    source = fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    # The declared type is observable in source facts; numeric initializer
    # evaluation is outside this analyzer and would not force a graph write.
    source.write_bytes(source.read_bytes().replace(b"property int value: 1", b"property real value: 1"))
    real_member, real_replace = QtQmlAccessIndex.member, watch.os_replace_with_fallback

    def failed_member(*args, **kwargs):
        assert real_member(*args, **kwargs).target_id
        raise RuntimeError("injected resolution completion failure")

    def failed_replace(start, destination):
        if str(destination).endswith("graph.json"):
            raise PermissionError("injected graph replacement failure")
        return real_replace(start, destination)

    with monkeypatch.context() as failed:
        if failure_stage == "join":
            failed.setattr(QtQmlAccessIndex, "member", failed_member)
        else:
            failed.setattr(watch, "os_replace_with_fallback", failed_replace)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failed, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert products(tmp_path) == accepted
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(recovered) != normalized(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".repaired"))
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
