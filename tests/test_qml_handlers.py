"""QML-007-AC01/03 handler subscriptions, emits and lexical JS visibility."""

from graphify.extractors.qml_facts import qml_metadata
from tests.qml_expression_helpers import extraction, nodes, single, target_edges


def test_declared_and_property_change_handlers_are_subscriptions(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 id: root
 property int value: 1
 signal ping(int value)
 function work(n) { return n; }
 onPing: { work(value); }
 onValueChanged: { work(value); }
 function publish() { ping(value); }
}"""})
    signal = single(result, "signal", "ping")
    handler = single(result, "handler", "onPing")
    edge = target_edges(result, handler, "qml_signal_subscription")[0]
    assert edge["relation"] == "references" and edge["target"] == signal["id"]
    notify = single(result, "property_change_signal")
    assert target_edges(result, single(result, "handler", "onValueChanged"))[0]["target"] == notify["id"]
    emission = single(result, "call", "ping")
    assert target_edges(result, emission, "qml_signal_emit")[0]["relation"] == "uses"
    parameter_reads = [site for site in nodes(result, "read", "value")
                       if "value" in qml_metadata(site)["lexical_names"]]
    assert len(parameter_reads) == 1
    assert qml_metadata(parameter_reads[0])["reason"] == "javascript_lexical_binding"


def test_connections_target_and_dynamic_target_stay_distinct(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 id: root
 signal ping(int n)
 function work(n) { return n; }
 property QtObject connection: Connections {
  target: root
  function onPing(n) { work(n); }
 }
 property QtObject dynamicConnection: Connections {
  target: chooseTarget()
  onPing: { work(1); }
 }
}"""})
    handlers = nodes(result, "handler", "onPing")
    assert len(handlers) == 2
    fixed = [site for site in handlers if qml_metadata(site)["connection_target"] == "root"][0]
    assert target_edges(result, fixed)[0]["target"] == single(result, "signal", "ping")["id"]
    dynamic = [site for site in handlers if not qml_metadata(site)["connection_target"]][0]
    assert qml_metadata(dynamic)["status"] == "dynamic"
    assert not target_edges(result, dynamic)


def test_parameters_block_bindings_nested_functions_and_computed_calls(tmp_path):
    result = extraction(tmp_path, {"Main.qml": """QtObject {
 function work() { return 1; }
 function run(work) { work(); }
 function outer() {
  { let work = 3; work(); }
  work();
  function local() { work(); }
  local();
  object[name]();
 }
}"""})
    calls = nodes(result, "call", "work")
    assert len(calls) == 4
    assert sorted(qml_metadata(site)["status"] for site in calls) == ["dynamic", "dynamic", "resolved", "resolved"]
    local = single(result, "call", "local")
    assert target_edges(result, local, "qml_js_call")[0]["target"] == single(result, "js_function", "local")["id"]
    computed = single(result, "call", "dynamic")
    assert qml_metadata(computed)["reason"] == "computed_or_runtime_target"
    assert not target_edges(result, computed)


def test_inherited_and_alias_target_signal_parameters_shadow_properties(tmp_path):
    result = extraction(tmp_path, {"Base.qml": "QtObject { signal ping(int value) }",
        "Main.qml": """Base {
 id: root
 property int value: 1
 property alias chosen: child
 property Base childObject: Base { id: child }
 function helper(n) { return n; }
 onPing: { helper(value); }
 property QtObject subscription: Connections {
  target: root.chosen
  onPing: { helper(value); }
 }
}"""})
    signal = single(result, "signal", "ping", "Base.qml")
    assert qml_metadata(signal)["parameter_names"] == ["value"]
    for handler in nodes(result, "handler", "onPing"):
        assert target_edges(result, handler)[0]["target"] == signal["id"]
    reads = nodes(result, "read", "value", "Main.qml")
    assert len(reads) == 2
    assert all(qml_metadata(site)["reason"] == "javascript_lexical_binding" for site in reads)
    assert all(not target_edges(result, site) for site in reads)


def test_signal_parameter_transport_limit_is_explicit_failure(tmp_path):
    from graphify.extractors.qml import extract_qml
    path = tmp_path / "Main.qml"
    parameters = ", ".join(f"int n{i}" for i in range(51))
    path.write_text("QtObject { signal ping(" + parameters + ") }", encoding="utf-8")
    result = extract_qml(path, root=tmp_path)
    assert result["qml_failures"] == [{"code": "QML_LIMIT", "source_file": "Main.qml"}]
    assert not result["nodes"]
