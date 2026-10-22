"""REQ-QML-017-AC01/AC04: literal loader provenance and durable refresh."""
from __future__ import annotations

import json

import pytest

from graphify.affected import affected_nodes, load_graph
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_consumer_helpers import cli as consumer_cli
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


def source(form, target="Main.qml", *, removed=False):
    """Only the admitted static loader forms vary; no Qt runtime is invoked."""
    url = f'QUrl("qrc:/ui/{target}")'
    if form == "engine_constructor":
        load = f'QQmlApplicationEngine engine({url})'
        body = 'QQmlApplicationEngine engine' if removed else load
        body += '; auto root = engine.rootObjects().first();'
    else:
        load = f'component.loadUrl({url})'
        body = 'QQmlEngine engine; QQmlComponent component(&engine); '
        body += '' if removed else load + '; '
        body += 'auto root = component.create();'
    return 'void use() { ' + body + ' root->property("value"); }\n', load


def fixture(root, form):
    content, expression = source(form)
    files = {
        "loader.cpp": content,
        "Main.qml": 'import QtQml\nQtObject { property int value: 1 }\n',
        "Alt.qml": 'import QtQml\nQtObject { property int value: 2 }\n',
        "CMakeLists.txt": 'qt_add_qml_module(app URI Public.Tools VERSION 1.0 QML_FILES Main.qml Alt.qml SOURCES loader.cpp)\n',
        "ui.qrc": '<RCC><qresource prefix="/ui"><file alias="Main.qml">Main.qml</file><file alias="Alt.qml">Alt.qml</file></qresource></RCC>',
        "keep.py": 'def helper(): return 7\n\ndef retained(): return helper()\n',
    }
    for name, text in files.items():
        (root / name).write_bytes(text.encode())
    return root / "loader.cpp", expression


def facts(graph, kind):
    return {identity: qt_metadata(data) for identity, data in graph.nodes(data=True)
            if qt_metadata(data).get("kind") == kind}


def assert_context(graph, source, target, context):
    """CLI/watch can retain parallel edges; inspect the exact logical mechanism."""
    data = graph.get_edge_data(source, target)
    assert data is not None
    records = data.values() if graph.is_multigraph() else [data]
    matches = [edge for edge in records if edge.get("context") == context]
    assert len(matches) == 1
    assert (matches[0].get("_src", source), matches[0].get("_tgt", target)) == (source, target)


def assert_load(graph, original, expression, filename="Main.qml"):
    """The URL-owning source occurrence reaches the exact accepted component."""
    matches = [(identity, md) for identity, md in facts(graph, "qml_load").items()
               if original[md["span"]["start_byte"]:md["span"]["end_byte"]] == expression.encode()]
    assert len(matches) == 1, [(md.get("operation"), md.get("status")) for md in facts(graph, "qml_load").values()]
    assert len(facts(graph, "qml_load")) == 1
    identity, metadata = matches[0]
    assert metadata["status"] == "resolved" and len(metadata["receiver_declaration_id"]) == 64
    target = metadata["target_id"]
    assert graph.nodes[target]["source_file"] == filename and graph.has_edge(identity, target)
    assert_context(graph, identity, target, "qt_cpp_qml_load")
    roots = facts(graph, "qml_root")
    assert len(roots) == 1 and all(md["status"] == "resolved" for md in roots.values())
    assert all(graph.has_edge(root, md["target_id"]) for root, md in roots.items())
    access, md = next(iter(facts(graph, "qml_access").items()))
    assert md["status"] == "resolved" and graph.nodes[md["target_id"]]["source_file"] == filename
    assert graph.has_edge(access, md["target_id"])
    assert_context(graph, access, md["target_id"], "qt_cpp_qml_property_read")


def products(root):
    output = root / "graphify-out"
    return {name: (output / name).read_bytes() for name in
            ("graph.json", "manifest.json", ".qt_analysis.json", ".graphify_root")}


@pytest.mark.parametrize("form", ["engine_constructor", "component_load_url"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_loader_edits_match_cold_warm_manual_and_watch(tmp_path, monkeypatch, form, operation):
    """URL/source removal and metadata/QML edits retire stale persisted joins."""
    cpp, expression = fixture(tmp_path, form)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    cold = clean(tmp_path, tmp_path / ".cold")
    assert_load(cold, cpp.read_bytes(), expression)
    assert normalized(clean(tmp_path, tmp_path / ".cold")) == normalized(cold)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    untouched = unrelated(initial)

    content, expression = source(form, "Alt.qml")
    cpp.write_bytes(content.encode())
    moved = run(tmp_path, monkeypatch, operation, [cpp])
    assert_load(moved, cpp.read_bytes(), expression, "Alt.qml")
    assert normalized(moved) == normalized(clean(tmp_path, tmp_path / ".moved"))
    load_ids, access_ids = set(facts(moved, "qml_load")), set(facts(moved, "qml_access"))
    unchanged_cpp = cpp.read_bytes()

    # A metadata-only alias change invalidates the unchanged native loader.
    resource = tmp_path / "ui.qrc"
    valid_resource = resource.read_bytes()
    resource.write_bytes(valid_resource.replace(b'alias="Alt.qml"', b'alias="renamed.qml"'))
    missing = run(tmp_path, monkeypatch, operation, [resource])
    assert set(facts(missing, "qml_load")) == load_ids and set(facts(missing, "qml_access")) == access_ids
    assert cpp.read_bytes() == unchanged_cpp
    assert all(md["status"] != "resolved" and not md.get("target_id") for md in facts(missing, "qml_load").values())
    assert all(md["status"] != "resolved" and not md.get("target_id") for md in facts(missing, "qml_access").values())
    assert normalized(missing) == normalized(clean(tmp_path, tmp_path / ".missing"))
    resource.write_bytes(valid_resource)
    assert normalized(run(tmp_path, monkeypatch, operation, [resource])) == normalized(moved)

    # The source loader/root survive a QML-only member deletion, but its access
    # must lose the previous target and projected relationship.
    qml = tmp_path / "Alt.qml"
    qml.write_bytes(qml.read_bytes().replace(b"int value:", b"int replacement:"))
    changed = run(tmp_path, monkeypatch, operation, [qml])
    assert set(facts(changed, "qml_load")) == load_ids and set(facts(changed, "qml_access")) == access_ids
    assert cpp.read_bytes() == unchanged_cpp
    assert all(md["status"] == "resolved" for md in facts(changed, "qml_load").values())
    for identity, md in facts(changed, "qml_access").items():
        assert md["status"] != "resolved" and not md.get("target_id")
        assert not any(data.get("_src", start) == identity and data.get("relation") == "uses"
                       for start, _, data in changed.edges(data=True))
    assert normalized(changed) == normalized(clean(tmp_path, tmp_path / ".qml-edit"))
    cpp.write_bytes(source(form, removed=True)[0].encode())
    removed = run(tmp_path, monkeypatch, operation, [cpp])
    assert not [md for md in facts(removed, "qml_load").values() if md["status"] == "resolved"]
    assert all(md["status"] != "resolved" for md in facts(removed, "qml_access").values())
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed"))
    assert unrelated(removed) == untouched
    before = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)
    assert products(tmp_path) == before


@pytest.mark.parametrize("form", ["engine_constructor", "component_load_url"])
@pytest.mark.parametrize("operation", ["manual", "force", "watch"])
def test_req_qml017_ac04_loader_parse_failure_preserves_products_and_recovers(tmp_path, monkeypatch, form, operation):
    """Real malformed input is rejected before all four durable products change."""
    cpp, expression = fixture(tmp_path, form)
    monkeypatch.chdir(tmp_path)
    mode = "manual" if operation == "force" else operation
    initial = run(tmp_path, monkeypatch, mode)
    assert_load(initial, cpp.read_bytes(), expression)
    valid, accepted = cpp.read_bytes(), products(tmp_path)
    cpp.write_bytes(valid + b"void broken({")
    if operation == "watch":
        from graphify.watch import _rebuild_code
        assert not _rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    else:
        with pytest.raises(SystemExit) as rejected:
            if operation == "force":
                from tests.test_qt_cpp_upgrade_invalidation import cli
                cli(tmp_path, monkeypatch, "update", force=True)
            else:
                run(tmp_path, monkeypatch, mode, [cpp])
        assert rejected.value.code == 1
    assert products(tmp_path) == accepted
    cpp.write_bytes(valid)
    repaired = run(tmp_path, monkeypatch, mode, [cpp])
    assert normalized(repaired) == normalized(initial)
    # Repair updates source stat/provenance; the subsequent no-change operation
    # must preserve that repaired durable state, not its historical timestamps.
    repaired_products = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, mode, [])) == normalized(initial)
    assert products(tmp_path) == repaired_products


@pytest.mark.parametrize("form", ["engine_constructor", "component_load_url"])
@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_loader_write_failure_preserves_products_and_retries(tmp_path, monkeypatch, form, operation):
    """The real graph replacement can fail after successful parser/resolver work."""
    import graphify.watch as watch
    cpp, expression = fixture(tmp_path, form)
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    assert_load(initial, cpp.read_bytes(), expression)
    accepted = products(tmp_path)
    content, expression = source(form, "Alt.qml")
    cpp.write_bytes(content.encode())
    real_replace = watch.os_replace_with_fallback

    def fail_replace(start, destination):
        if str(destination).endswith("graph.json"):
            raise PermissionError("injected loader graph replacement failure")
        return real_replace(start, destination)

    with monkeypatch.context() as failure:
        failure.setattr(watch, "os_replace_with_fallback", fail_replace)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failure, operation, [cpp])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    assert products(tmp_path) == accepted
    recovered = run(tmp_path, monkeypatch, operation, [cpp])
    assert_load(recovered, cpp.read_bytes(), expression, "Alt.qml")
    assert normalized(recovered) != normalized(initial)
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered"))
    repeated = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == repeated


@pytest.mark.parametrize("form", ["engine_constructor", "component_load_url"])
def test_req_qml017_ac04_loader_directed_reload_query_and_affected_keep_endpoints(tmp_path, monkeypatch, capsys, form):
    """Actual persisted directed consumers retain the precise loader/member path."""
    cpp, expression = fixture(tmp_path, form)
    from graphify.extract import collect_files, extract
    result = extract(collect_files(tmp_path, root=tmp_path), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "directed.json"
    assert to_json(graph, {}, str(output), force=True)
    loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert_load(loaded, cpp.read_bytes(), expression)
    identity, metadata = next(iter(facts(loaded, "qml_access").items()))
    assert not loaded.has_edge(metadata["target_id"], identity)
    assert "Main.qml" in consumer_cli(monkeypatch, capsys, output, "query", identity)
    assert "loader.cpp" in consumer_cli(monkeypatch, capsys, output, "explain", identity)
    hits = {hit.node_id for hit in affected_nodes(load_graph(output), metadata["target_id"], relations=["uses"], depth=1)}
    assert identity in hits
