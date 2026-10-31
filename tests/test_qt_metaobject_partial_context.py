"""REQ-QML-022-AC06: unknown borrowed edge context differs from corrupt complete proof."""
from __future__ import annotations

import copy

import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_metaobject import QtMetaobjectIndex
from graphify.qt_project_index import QtProjectIndex
from graphify.qt_qml_bridge import build_qt_qml_bridge
from graphify.qt_qml_pipeline import resolve_qt_qml
from tests.qt_metaobject_helpers import analyzed, facts, member_edges, member_sites, sources
from tests.qt_analysis_helpers import analysis
from graphify.extractors.qml_facts import qml_metadata


@pytest.mark.parametrize("complete", [False, True])
def test_node_only_borrowed_alias_keeps_source_without_own_meta_authority(tmp_path, complete):
    """Omitted ownership remains unknown; explicitly complete-empty ownership must reject."""
    accepted = analyzed(tmp_path)
    context = copy.deepcopy([n for n in accepted["nodes"] if n["source_file"] == "backend.hpp"])
    before = copy.deepcopy(context)
    alias = tmp_path / "alias.hpp"
    alias.write_text("using PublicAlias = Backend;\n", encoding="utf-8")
    # Keep explicit complete-empty ownership distinct from the omitted unknown
    # edge context, using the public list input rather than a generic expander.
    if complete:
        result = extract([alias], root=tmp_path, cache_root=tmp_path, parallel=False,
            resolution_context_nodes=context, resolution_context_edges=[])
    else:
        result = extract([alias], root=tmp_path, cache_root=tmp_path, parallel=False,
            resolution_context_nodes=context)
    if complete:
        assert {item["code"] for item in result["qml_failures"]} == {"QML_RESOLUTION_FAILED"}
    else:
        assert not result.get("qml_failures") and len(facts(result, "type_alias")) == 1
    assert not [e for e in result["edges"] if e.get("context") in {"qml_js_call", "qt_signal_emit"}]
    assert context == before


def test_direct_node_only_bridge_retains_type_but_cannot_resolve_own_member(tmp_path):
    """Existing optional node-only APIs remain callable with explicit unavailable ownership."""
    accepted = analyzed(tmp_path)
    project = QtProjectIndex(accepted["nodes"], accepted["edges"], root=tmp_path)
    index = build_qt_qml_bridge(accepted["nodes"], root=tmp_path, project_index=project)
    provider = index.module_type("Public.Probe", 1, 0, "Service")
    assert provider.status == "resolved"
    member = index.member(provider.target_id, "ownMethod")
    assert member.status == "unavailable" and member.reason == "native_metaobject_ownership_unavailable"


def test_real_node_only_qml_refresh_keeps_provider_but_no_own_meta_member_binding(tmp_path):
    """A real borrowed procedural provider preserves type use without borrowing absent moc ownership."""
    files = sources()
    header = files["backend.hpp"] + '\nvoid install(){qmlRegisterType<Backend>("Public.Probe",1,0,"Service");}\n'
    accepted = analysis(tmp_path, {"backend.hpp": header})
    path = tmp_path / "Main.qml"
    path.write_text(files["Main.qml"], encoding="utf-8")
    before = copy.deepcopy(accepted)
    refreshed = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False,
        resolution_context_nodes=accepted["nodes"])
    assert not refreshed.get("qml_failures")
    assert len(member_sites(refreshed)) == 3 and not member_edges(refreshed)
    assert {qml_metadata(n)["status"] for n in member_sites(refreshed)} == {"unavailable"}
    types = [qml_metadata(n) for n in refreshed["nodes"] if qml_metadata(n).get("kind") == "type_use"]
    assert len(types) == 1 and types[0]["status"] == "resolved"
    assert accepted == before


@pytest.mark.parametrize("corruption", ["foreign_flag", "wrong_owner", "missing_marker", "canonical"])
def test_unknown_borrowed_marker_cannot_override_source_or_provided_edge_corruption(tmp_path, corruption):
    """Selective unknown edge state does not pardon contradictory source/count/actual owner evidence."""
    accepted = analyzed(tmp_path)
    marker, = facts(accepted, "metaobject")
    unknown = frozenset({marker["id"]})
    owned = next(e for e in accepted["edges"] if e["target"] == marker["id"])
    if corruption == "foreign_flag":
        unknown = frozenset({"foreign-marker"})
    elif corruption == "wrong_owner":
        owned["source"] = owned["_src"] = "foreign-class"
    elif corruption == "missing_marker":
        accepted["nodes"].remove(marker)
    else:
        owner, = facts(accepted, "class")
        identity = qt_metadata(owner)["class_id"]
        next(n for n in accepted["nodes"] if n["id"] == identity)["_callable_class"] = False
    with pytest.raises(ValueError, match="QT_METADATA"):
        QtMetaobjectIndex(accepted["nodes"], accepted["edges"], unknown_metaobject_ownership=unknown)


def test_fresh_graph_missing_owned_edge_stays_integrity_failure_even_with_partial_caller_context(tmp_path):
    """Fresh marker promises cannot borrow the node-only exception intended for actual context facts."""
    accepted = analyzed(tmp_path)
    marker, = facts(accepted, "metaobject")
    accepted["edges"] = [e for e in accepted["edges"] if e["target"] != marker["id"]]
    alias = tmp_path / "alias.hpp"
    alias.write_text("using PublicAlias = Backend;\n", encoding="utf-8")
    fresh = {"nodes": [], "edges": []}
    failures = resolve_qt_qml([alias], [fresh], accepted["nodes"], accepted["edges"], root=tmp_path,
        context_nodes=None, context_edges=None)
    assert failures and {item["code"] for item in fresh["qml_failures"]} == {"QML_RESOLUTION_FAILED"}
    with pytest.raises(ValueError, match="QT_METADATA"):
        build_from_json(accepted, root=tmp_path)


def test_typed_base_context_preserves_base_marker_without_authorizing_derived_own_member(tmp_path):
    """The existing declared Base* path owns Base's metaobject; it makes no Derived lookup claim."""
    files = {
        "backend.hpp": "class Base : public QObject { Q_OBJECT public: Q_INVOKABLE int baseMethod(); }; "
                       "class Derived : public Base { public: Q_INVOKABLE int ownMethod(); };",
        "CMakeLists.txt": "qt_add_qml_module(app URI Public.Probe VERSION 1.0 "
                            "QML_FILES Main.qml SOURCES backend.hpp register.cpp)",
        "Main.qml": "import QtQml\nQtObject { property int inheritedResult: backend.baseMethod(); "
                    "property int ownResult: backend.ownMethod() }",
        "register.cpp": "void boot(Derived *derived) { Base *backend = derived; QQmlApplicationEngine engine; "
                        'engine.rootContext()->setContextProperty("backend", backend); '
                        f'engine.load(QUrl("{(tmp_path / "Main.qml").as_uri()}")); }}',
    }
    result = analysis(tmp_path, files)
    access, = facts(result, "context_access")
    edge, = [e for e in result["edges"] if e.get("context") == "qt_context_member"]
    proof = qt_metadata(edge)["endpoint_proof"]
    member = next(n for n in result["nodes"] if n["id"] == proof["member_fact_id"])
    assert qt_metadata(member)["raw_name"] == "baseMethod"
    assert edge["target"] == qt_metadata(access)["target_id"]
    owner = next(n for n in facts(result, "class") if qt_metadata(n)["class_name"] == "Base")
    marker, = facts(result, "metaobject")
    assert proof["class_id"] == qt_metadata(owner)["class_id"]
    assert proof["metaobject_fact_id"] == marker["id"]
    assert {owner["id"], marker["id"]} <= set(proof["evidence"])
    graph = build_from_json(result, root=tmp_path)
    assert any(data.get("context") == "qt_context_member" for _, _, data in graph.edges(data=True))
