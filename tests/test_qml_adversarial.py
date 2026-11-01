"""Adversarial production-boundary checks for scoped QML/JS relationship facts."""

from __future__ import annotations

import base64
import copy
import json

import pytest

from graphify.extract import extract_js
from graphify.extractors.qml_ast import parse_source
from graphify.extractors.qml_declarations import Declarations
from graphify.extractors.qml_expressions import collect_relationships
from graphify.extractors.qml_facts import FactBuilder, qml_metadata
from graphify.extractors.qml_scripts import collect_qml_scripts
from graphify.qml_relationships import resolve_qml_relationships
from graphify.security import sanitize_metadata


def _facts(root, source, scripts=None):
    """Exercise the real AST collectors before projection, with no fixture evaluator."""
    path = root / "Main.qml"
    path.write_text(source, encoding="utf-8")
    raw, program, _ = parse_source(path)
    facts = FactBuilder(path, root, raw)
    declarations = Declarations(facts)
    declarations.extract(program)
    collect_relationships(declarations)
    per_file = {path: {"nodes": facts.nodes, "edges": facts.edges}}
    for name, text in (scripts or {}).items():
        script = root / name
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(text, encoding="utf-8")
        per_file[script] = extract_js(script)
    collect_qml_scripts(list(per_file), list(per_file.values()), root=root)
    return per_file


def _resolve(root, per_file):
    nodes = [node for result in per_file.values() for node in result["nodes"]]
    edges = [edge for result in per_file.values() for edge in result["edges"]]
    resolve_qml_relationships(per_file, nodes, edges, root=root)
    return nodes, edges


def _sites(nodes, kind, reference):
    return [node for node in nodes if qml_metadata(node).get("kind") == kind and
            qml_metadata(node).get("reference") == reference]


@pytest.mark.parametrize("loop", [
    "for (let target = 0; target < 1; target++) { target(); }",
    "for (const target of [1]) { target(); }",
    "for (let target in {a: 1}) { target(); }",
])
def test_loop_local_bindings_shadow_qml_only_inside_loop(tmp_path, loop):
    """Loop declarations must prevent false same-name QML calls without leaking out."""
    source = "QtObject { function target() {} function run() { " + loop + " target(); } }"
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source))
    sites = sorted(_sites(nodes, "call", "target"), key=lambda node: qml_metadata(node)["span"]["start_byte"])
    assert len(sites) == 2
    assert qml_metadata(sites[0])["status"] == "dynamic"
    assert qml_metadata(sites[0])["reason"] == "javascript_lexical_binding"
    assert not any(edge["source"] == sites[0]["id"] and edge["relation"] == "calls" for edge in edges)
    assert qml_metadata(sites[1])["status"] == "resolved"


def test_catch_binding_and_arrow_parameter_do_not_capture_outer_qml_function(tmp_path):
    """Catch/arrow binders shadow; a sibling call still reaches the QML function."""
    source = """QtObject {
        function target() {}
        function run() {
            try { throw 1; } catch (target) { target(); }
            const closure = (target) => target();
            target();
        }
    }"""
    nodes, _ = _resolve(tmp_path, _facts(tmp_path, source))
    sites = sorted(_sites(nodes, "call", "target"), key=lambda node: qml_metadata(node)["span"]["start_byte"])
    assert [qml_metadata(site)["status"] for site in sites] == ["dynamic", "dynamic", "resolved"]


def test_for_var_binding_is_function_scoped_and_reassigned_callable_is_dynamic(tmp_path):
    """Function-wide var and changed local callable values cannot fall back to QML."""
    source = """QtObject { function target() {} function run() {
        for (var target of [1]) { target(); } target();
        let chosen = () => 1; chosen = () => 2; chosen();
    } }"""
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source))
    sites = _sites(nodes, "call", "target") + _sites(nodes, "call", "chosen")
    assert len(sites) == 3
    assert all(qml_metadata(site)["status"] != "resolved" for site in sites)
    assert not any(edge["source"] in {site["id"] for site in sites} and edge["relation"] == "calls" for edge in edges)


def test_assignment_target_is_not_read_but_computed_address_reads_are_retained(tmp_path):
    """Writes differ from dependency reads, including receiver/index evaluation."""
    source = """QtObject { id: root; property var store: ({}); property int index: 0;
        property int value: 1;
        function run() { value = 2; store[index] = value; value += index; }
    }"""
    per_file = _facts(tmp_path, source)
    nodes, _ = _resolve(tmp_path, per_file)
    reads = [qml_metadata(node)["reference"] for node in nodes if qml_metadata(node).get("kind") == "read"]
    assert reads.count("value") == 2
    assert reads.count("index") == 2
    assert reads.count("store") == 1


def test_many_lexical_bindings_survive_sanitized_json_without_false_resolution(tmp_path):
    """Transport caps must never turn a proven local binding into a QML reference."""
    bindings = ", ".join(f"a{i:02} = 0" for i in range(60)) + ", target = 0"
    per_file = _facts(tmp_path, "QtObject { function target() {} function run() { let " + bindings + "; target(); } }")
    copied = json.loads(json.dumps(per_file[next(iter(per_file))]))
    for node in copied["nodes"]:
        node["metadata"] = sanitize_metadata(node["metadata"])
    nodes, edges = _resolve(tmp_path, {tmp_path / "Main.qml": copied})
    site = _sites(nodes, "call", "target")[0]
    assert qml_metadata(site)["status"] != "resolved"
    assert not any(edge["source"] == site["id"] and edge["relation"] == "calls" for edge in edges)


def test_exported_arrow_helper_and_local_reexport_have_correct_visibility(tmp_path):
    """ESM export arrows are callable, while re-export clauses do not export locals."""
    source = 'import "helpers.mjs" as Helpers\nQtObject { function run() { Helpers.arrow(); Helpers.local(); } }'
    scripts = {"helpers.mjs": "export const arrow = () => 42; function local() { return 1; } export { local } from './other.mjs';",
               "other.mjs": "export function local() { return 2; }"}
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source, scripts))
    arrow = _sites(nodes, "call", "Helpers.arrow")[0]
    assert qml_metadata(arrow)["status"] == "resolved"
    local = _sites(nodes, "call", "Helpers.local")[0]
    assert qml_metadata(local)["status"] != "resolved"
    assert not any(edge["source"] == local["id"] and edge["relation"] == "calls" for edge in edges)


@pytest.mark.parametrize("library", ["", ".pragma library\n"])
def test_shared_script_never_binds_to_qml_importer_context(tmp_path, library):
    """A shared helper has no arbitrary document's ID/function namespace."""
    source = 'import "shared.js" as Shared\nQtObject { function target() {} function run() { Shared.invoke(); } }'
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source, {"shared.js": library + "function invoke() { target(); }"}))
    helper = _sites(nodes, "call", "target")[0]
    assert qml_metadata(helper)["status"] != "resolved"
    assert not any(edge["source"] == helper["id"] and edge["relation"] == "calls" for edge in edges)


def test_alias_cycle_and_dynamic_connections_have_no_guessed_endpoints(tmp_path):
    """Static alias cycles and runtime target selections remain explicit coverage gaps."""
    source = """QtObject { id: root; property alias first: root.second;
        property alias second: root.first; property bool choose: true;
        signal activated(); function run() { first; }
        Connections { target: choose ? root : null; function onActivated() { root.run(); } }
    }"""
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source))
    aliases = [node for node in nodes if qml_metadata(node).get("kind") == "alias"]
    assert aliases and all(qml_metadata(node)["reason"] == "alias_cycle_or_limit" for node in aliases)
    handler = [node for node in nodes if qml_metadata(node).get("kind") == "handler"][0]
    assert qml_metadata(handler)["reason"] == "connections_runtime_target"
    assert not any(edge["source"] == handler["id"] and edge.get("context") == "qml_signal_subscription" for edge in edges)


def test_explicit_component_body_id_cannot_escape_into_enclosing_document(tmp_path):
    """Qt Component's definition body is a separate ID scope from its declaring object."""
    source = """import QtQml as Qml
        import QtQuick as Quick
        Quick.Item { id: root;
            Qml.Component { id: factory; Qml.QtObject { id: hidden; property int value: 1 } }
            function run() { hidden.value; }
        }"""
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source))
    site = _sites(nodes, "read", "hidden.value")[0]
    assert qml_metadata(site)["status"] != "resolved"
    assert not any(edge["source"] == site["id"] and edge.get("context") == "qml_binding_read" for edge in edges)


def test_mixed_legacy_connections_handlers_do_not_activate_ignored_function_handlers(tmp_path):
    """Qt ignores function-style handlers when one legacy handler exists in that object."""
    source = """QtObject { id: root; signal first(); signal second();
        Connections { target: root; onFirst: {}
            function onSecond() {}
        }
    }"""
    nodes, edges = _resolve(tmp_path, _facts(tmp_path, source))
    handlers = [node for node in nodes if qml_metadata(node).get("kind") == "handler"]
    first = next(node for node in handlers if qml_metadata(node)["reference"] == "first")
    second = next(node for node in handlers if qml_metadata(node)["reference"] == "second")
    assert qml_metadata(first)["status"] == "resolved"
    assert qml_metadata(second)["status"] != "resolved"
    assert not any(edge["source"] == second["id"] and edge.get("context") == "qml_signal_subscription" for edge in edges)


@pytest.mark.parametrize("raw", ["not-a-map", {"raw_name": "!not-base64"},
                                  {"raw_name": base64.b64encode(b"x" * 500).decode()}])
def test_corrupt_semantic_transport_is_bounded_rejection(raw):
    """Malformed/bypassed field transport must reject rather than reinterpret a fact."""
    node = {"metadata": {"qml": {"contract_version": 1, "raw_name": "safe", "raw_values": copy.deepcopy(raw)}}}
    with pytest.raises(ValueError):
        qml_metadata(node)
