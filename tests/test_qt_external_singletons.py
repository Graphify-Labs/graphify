"""INC-QML-68: external singleton setup is one engine's source relationship."""
from __future__ import annotations

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_access import collect_qt_cpp_access
from graphify.extractors.qt_cpp_exposure import enrich_qt_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.paths import load_node_link_graph
from graphify.qt_qml_access_index import QtQmlAccessIndex
from graphify.qt_external_singletons import resolve_external_singletons
from tests.qt_analysis_helpers import sites
from tests.qt_external_singleton_helpers import (HEADER, LOAD, SETUP, analyzed, binding_edges,
                                                  setup_metadata, setup_sites)


def test_req_qml022_ac05_external_singleton_setup_has_exact_source_binding_and_json(tmp_path):
    """Registered type, actual instance and same engine/load retain separate identities."""
    result = analyzed(tmp_path)
    setup = setup_sites(result)[0]
    md = qt_metadata(setup)
    assert md["status"] == "resolved" and md["runtime_success"] == "unverified"
    assert md["lifetime_status"] == "unverified" and md["ownership_transfer"] is False
    assert len(md["receiver_declaration_id"]) == len(md["provider_declaration_id"]) == 64
    assert md["provider_at_load_declaration_id"] == md["provider_declaration_id"]
    registration = [node for node in sites(result, "registration") if qt_metadata(node).get("singleton")][0]
    assert md["registration_id"] == registration["id"]
    assert md["provider_class_id"] == qt_metadata(registration)["class_id"]
    assert {edge["target"] for edge in binding_edges(result)} == {
        registration["id"], md["provider_class_id"], md["component_target_id"]}
    graph = build_from_json(result, root=tmp_path, directed=True)
    destination = tmp_path / "proof.json"
    to_json(graph, {}, str(destination))
    loaded = load_node_link_graph(json.loads(destination.read_text()))
    assert qt_metadata(loaded.nodes[setup["id"]]) == md
    assert all(loaded.has_edge(edge["source"], edge["target"]) for edge in binding_edges(result))
    assert not sites(result, "context_binding")


@pytest.mark.parametrize("prefix,expression,signature", [
    ("Service singleton; QQmlApplicationEngine engine;", "&singleton", "void boot()"),
    ("using Engine = QQmlApplicationEngine; Engine engine;", "singleton", "void boot(Service *singleton)"),
    ("", "singleton", "void boot(Service *singleton, QQmlApplicationEngine &engine)"),
])
def test_req_qml022_ac05_external_singleton_keeps_sdk_alias_and_parameter_identity(tmp_path, prefix, expression, signature):
    """Original SDK type/instance declarations govern aliases and direct parameters."""
    statement = SETUP.replace("&singleton", expression)
    result = analyzed(tmp_path, f"{signature} {{ {prefix} {statement} {LOAD} }}")
    assert setup_metadata(result)["status"] == "resolved"
    assert len(binding_edges(result)) == 3


@pytest.mark.parametrize("body", [
    f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} }}",
    f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {LOAD} {SETUP} }}",
    f"void boot(bool ready) {{ Service singleton; QQmlApplicationEngine engine; if(ready) {{ {SETUP} }} {LOAD} }}",
    f"void boot() {{ Service singleton; QQmlApplicationEngine engine; QQmlApplicationEngine other; {SETUP} {LOAD.replace('engine.', 'other.')} }}",
    f"void boot() {{ QQmlApplicationEngine engine; {{ Service singleton; {SETUP} }} {LOAD} }}",
    f"void boot(Service *singleton, Service *other) {{ QQmlApplicationEngine engine; {SETUP.replace('&singleton', 'singleton')} singleton = other; {LOAD} }}",
    f"void boot(Service *singleton, QQmlApplicationEngine *engine, QQmlApplicationEngine *other) {{ {SETUP.replace('engine.', 'engine->').replace('&singleton', 'singleton')} engine = other; {LOAD.replace('engine.', 'engine->')} }}",
    f"void boot() {{ Other singleton; QQmlApplicationEngine engine; {SETUP} {LOAD} }}",
    f"void boot() {{ Service singleton; QQmlApplicationEngine engine; engine.singletonInstance<Service*>(\"Public.Tools\", \"State\"); {SETUP} {LOAD} }}",
    f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} engine.clearSingletons(); {LOAD} }}",
])
def test_req_qml022_ac05_unproven_external_singleton_state_never_gets_binding(tmp_path, body):
    """No load, late/conditional/mismatched use, lifetime or assignment uncertainty stays explicit."""
    result = analyzed(tmp_path, body)
    md = setup_metadata(result)
    assert md["status"] != "resolved" and md["reason"]
    assert not binding_edges(result)


@pytest.mark.parametrize("second", [SETUP, SETUP.replace('"State"', "typeName")])
def test_req_qml022_ac05_duplicate_or_unknown_same_engine_setup_never_guesses(tmp_path, second):
    """A possibly repeated type/engine setup cannot establish the once-only precondition."""
    result = analyzed(tmp_path, f"void boot(const char *typeName) {{ Service singleton; QQmlApplicationEngine engine; {SETUP} {second} {LOAD} }}")
    assert len(setup_sites(result)) == 2
    assert all(qt_metadata(site)["status"] != "resolved" for site in setup_sites(result))
    assert not binding_edges(result)


@pytest.mark.parametrize("replace", ["unregistered", "not_singleton", "callback"])
def test_req_qml022_ac05_external_singleton_needs_accepted_singleton_registration(tmp_path, replace):
    """Unknown type and opaque callback/global registrations grant no new source binding."""
    header = HEADER.replace("QML_NAMED_ELEMENT(State)", "") if replace == "unregistered" else HEADER.replace("QML_SINGLETON", "")
    body = None
    if replace == "callback":
        header = HEADER.replace("QML_NAMED_ELEMENT(State) QML_SINGLETON", "")
        body = f'void boot() {{ qmlRegisterSingletonType<Service>("Public.Tools",1,0,"State",unknownFactory); Service singleton; QQmlApplicationEngine engine; {SETUP} {LOAD} }}'
    result = analyzed(tmp_path, body, header)
    assert setup_metadata(result)["status"] != "resolved"
    assert not binding_edges(result)


def test_req_qml022_ac05_same_spelled_source_engine_is_not_sdk_api(tmp_path):
    """An ordinary source method cannot acquire SDK engine/provider authority by spelling."""
    source = f"class QQmlApplicationEngine {{ public: void setExternalSingletonInstance(const char*,const char*,QObject*); }}; void boot() {{ Service singleton; QQmlApplicationEngine engine; {SETUP} }}"
    result = analyzed(tmp_path, source)
    assert not setup_sites(result) and not binding_edges(result)


def test_req_qml022_ac05_direct_source_collector_preserves_instance_and_load_checkpoint(tmp_path):
    """The direct producer borrows canonical generic proof, then owns identity/ranges."""
    result = analyzed(tmp_path)
    paths = [tmp_path / "backend.hpp", tmp_path / "main.cpp"]
    per_file = [{"nodes": [], "edges": []} for _ in paths]
    accepted = [node for node in result["nodes"] if not qt_metadata(node)]
    ids = {node["id"] for node in accepted}
    edges = [edge for edge in result["edges"] if edge["source"] in ids and edge["target"] in ids]
    enrich_qt_cpp(paths, per_file, root=tmp_path, accepted_nodes=accepted, accepted_edges=edges)
    collect_qt_cpp_access(paths, per_file, root=tmp_path,
                         accepted_nodes=accepted + [node for item in per_file for node in item["nodes"]],
                         accepted_edges=edges + [edge for item in per_file for edge in item["edges"]])
    direct = setup_metadata({"nodes": [node for item in per_file for node in item["nodes"]]})
    facade = setup_metadata(result)
    for key in ["span", "receiver_declaration_id", "provider_declaration_id", "provider_root_type_id",
                "provider_at_load_declaration_id", "provider_at_load_status", "checkpoint_load_id"]:
        assert direct[key] == facade[key]
    span = direct["span"]
    assert (tmp_path / "main.cpp").read_bytes()[span["start_byte"]:span["end_byte"]] == SETUP[:-1].encode()


def test_req_qml022_ac05_external_singleton_accepts_actual_qqmlengine_component_load(tmp_path):
    """A QQmlComponent must retain its explicit source-engine association."""
    url = (tmp_path / "Main.qml").as_uri()
    body = f'void boot() {{ Service singleton; QQmlEngine engine; {SETUP} QQmlComponent component(&engine); component.loadUrl(QUrl("{url}")); }}'
    result = analyzed(tmp_path, body)
    assert setup_metadata(result)["status"] == "resolved"
    assert len(binding_edges(result)) == 3


@pytest.mark.parametrize("change", ["spacing", "duplicate_loads", "dynamic_provider", "unevaluated",
                                    "qualified_receiver", "template_api", "wrong_operator"])
def test_req_qml022_ac05_external_singleton_source_context_boundaries(tmp_path, change):
    """Whitespace is syntax; extra loads, computed instances and fake chains are uncertainty."""
    statement = SETUP
    loads = LOAD
    if change == "spacing":
        statement = statement.replace("engine.", "engine /* keep */ . ")
    elif change == "duplicate_loads":
        loads += LOAD
    elif change == "dynamic_provider":
        statement = statement.replace("&singleton", "getSingleton()")
    elif change == "unevaluated":
        statement = "sizeof(" + statement[:-1] + ");"
    elif change == "template_api":
        statement = statement.replace("setExternalSingletonInstance(", "setExternalSingletonInstance<int>(")
    elif change == "wrong_operator":
        statement = statement.replace("engine.", "engine->")
    else:
        statement = statement.replace("engine.", "holder.engine.")
    result = analyzed(tmp_path, f"void boot() {{ Service singleton; QQmlApplicationEngine engine; {statement} {loads} }}")
    if change == "qualified_receiver":
        assert not setup_sites(result)
    else:
        assert (setup_metadata(result)["status"] == "resolved") == (change == "spacing")
    assert bool(binding_edges(result)) == (change == "spacing")


@pytest.mark.parametrize("field,value", [("span", None), ("api_supported", "true"),
                                         ("runtime_success", True), ("ownership_transfer", 0),
                                         ("module_uri", []), ("prior_singleton_use", []),
                                         ("singleton_state_reset", "false")])
def test_req_qml022_ac06_corrupt_external_setup_transport_rejects_before_lookup(tmp_path, field, value):
    """Malformed source evidence is a controlled integrity failure, never a binding."""
    result = copy.deepcopy(analyzed(tmp_path))
    setup = setup_sites(result)[0]
    update_qt(setup, **{field: value})
    index = QtQmlAccessIndex(result["nodes"], result["edges"], root=tmp_path)
    with pytest.raises(ValueError, match="QT_METADATA"):
        resolve_external_singletons([result], index, result["nodes"], result["edges"])
