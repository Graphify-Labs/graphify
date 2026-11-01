"""REQ-QML-017-AC03/AC04: declaration identity prevents cross-engine injection."""
from __future__ import annotations

import json
import copy

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_identity import CppDeclarationIdentity, source_reference_key
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites

BACKEND = '''class Backend : public QObject {
 Q_OBJECT Q_PROPERTY(int count READ count)
public: int count() { return 1; }
};
'''


def persisted(root, source, qml=None):
    """Analyze synthetic sources and inspect completed production JSON output."""
    result = analysis(root, {"access.cpp": BACKEND + source,
                            "Main.qml": qml or 'import QtQml\nQtObject { property int value: backend.count }'})
    graph = build_from_json(result, root=root)
    output = root / "proof.json"
    assert to_json(graph, {}, str(output), force=True)
    return result, load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))


@pytest.mark.parametrize("exposure,qml", [
    ('engine.rootContext()->setContextProperty("backend", backend);', 'property int value: backend.count'),
    ('engine.rootContext()->setContextObject(backend);', 'property int value: count'),
    ('engine.setInitialProperties({{"backend", backend}});', 'property var backend; property int value: backend.count'),
])
def test_req_qml017_ac03_disjoint_same_named_engines_cannot_share_provider(tmp_path, exposure, qml):
    """An engine destroyed in one block cannot supply a later distinct engine."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(Backend *backend) {{
 {{ QQmlApplicationEngine engine; {exposure} }}
 {{ QQmlApplicationEngine engine; engine.load(QUrl("{url}")); }}
}}'''
    result, graph = persisted(tmp_path, source, 'import QtQml\nQtObject { ' + qml + ' }')
    assert not sites(result, "context_binding")
    assert not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True)
                if edge.get("context") in {"qt_context_member", "qt_context_exposure", "qt_initial_property"}]


def test_req_qml017_ac03_same_engine_positive_retains_persisted_provider(tmp_path):
    """One declaration may expose a provider and later load its own component."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(Backend *backend) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", backend);
 engine.load(QUrl("{url}")); }}'''
    result, graph = persisted(tmp_path, source)
    binding = sites(result, "context_binding")[0]
    access = sites(result, "context_access")[0]
    assert qt_metadata(binding)["status"] == "resolved"
    assert graph.has_edge(binding["id"], qt_metadata(binding)["component_target_id"])
    assert graph.has_edge(access["id"], qt_metadata(access)["target_id"])


def test_req_qml017_ac03_nested_engine_shadow_does_not_receive_outer_provider(tmp_path):
    """A shadow engine loads its document without inheriting an outer exposure."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(Backend *backend) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("backend", backend);
 {{ QQmlApplicationEngine engine; engine.load(QUrl("{url}")); }} }}'''
    result, graph = persisted(tmp_path, source)
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True) if edge.get("context") == "qt_context_member"]


def test_req_qml017_ac03_local_provider_lifetime_cannot_supply_later_load(tmp_path):
    """Even one engine cannot extend a source-local provider beyond its block."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use() {{ QQmlApplicationEngine engine;
 {{ Backend backend; engine.rootContext()->setContextProperty("backend", &backend); }}
 engine.load(QUrl("{url}")); }}'''
    result, graph = persisted(tmp_path, source)
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True) if edge.get("context") == "qt_context_member"]


def test_req_qml017_ac03_engine_and_provider_parameters_have_exact_identity(tmp_path):
    """Direct parameters establish one source relationship without caller guesses."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(QQmlApplicationEngine &engine, Backend *backend) {{
 engine.rootContext()->setContextProperty("backend", backend); engine.load(QUrl("{url}")); }}'''
    result, graph = persisted(tmp_path, source)
    binding = sites(result, "context_binding")[0]
    metadata = qt_metadata(binding)
    assert metadata["status"] == "resolved"
    assert len(metadata["engine_declaration_id"]) == len(metadata["provider_declaration_id"]) == 64
    assert graph.has_edge(binding["id"], metadata["component_target_id"])


@pytest.mark.parametrize("prefix,engine,role,status,reason", [
    ('QQmlApplicationEngine *engine = new QQmlApplicationEngine; engine = replacement;', 'engine->', "engine", "dynamic", "reassigned_declaration"),
    ('QQmlApplicationEngine engine; QQmlApplicationEngine engine;', 'engine.', "engine", "ambiguous", "declaration_ambiguous"),
    ('QQmlApplicationEngine engine; backend = other;', 'engine.', "provider", "dynamic", "reassigned_declaration"),
])
def test_req_qml017_ac03_rejected_identity_preserves_precise_source_diagnostic(tmp_path, prefix, engine, role, status, reason):
    """Production rejections keep lexical reasons and publish no provider edges."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(Backend *backend, Backend *other, QQmlApplicationEngine *replacement) {{
 {prefix} {engine}rootContext()->setContextProperty("backend", backend);
 {engine}load(QUrl("{url}")); }}'''
    result, graph = persisted(tmp_path, source)
    exposure = qt_metadata(sites(result, "context_exposure")[0])
    assert exposure[role + "_identity_status"] == status
    assert exposure[role + "_identity_reason"] == reason
    assert (exposure["status"], exposure["reason"]) == (status, reason)
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True) if edge.get("context") == "qt_context_member"]


@pytest.mark.parametrize("second,expected", [
    ("backend", ("dynamic", "reassigned_declaration")),
    ("missing", ("unavailable", "provider_component_scope_unestablished")),
])
def test_req_qml017_ac03_initial_properties_report_only_shared_identity_failure(tmp_path, second, expected):
    """A mixed provider list cannot misreport one item's reason as the whole list."""
    url = (tmp_path / "Main.qml").as_uri()
    source = f'''void use(Backend *backend, Backend *other) {{ QQmlApplicationEngine engine;
 backend = other; engine.setInitialProperties({{{{"backend", backend}}, {{"extra", {second}}}}});
 engine.load(QUrl("{url}")); }}'''
    result, graph = persisted(tmp_path, source, 'import QtQml\nQtObject { property var backend; property var extra; property int value: backend.count }')
    metadata = qt_metadata(sites(result, "initial_properties")[0])
    assert (metadata["status"], metadata["reason"]) == expected
    assert not sites(result, "context_binding") and not sites(result, "context_access")
    assert not [edge for _, _, edge in graph.edges(data=True) if edge.get("context") == "qt_initial_property"]


def identity_index(root, source):
    """The shared helper consumes real accepted syntax and canonical C++ mapping."""
    result = analysis(root, {"identity.cpp": source})
    unit = read_cpp(root / "identity.cpp", root)
    snapshot = copy.deepcopy((result["nodes"], result["edges"]))
    mapping = map_cpp(unit, result["nodes"], result["edges"], root=root)
    return CppDeclarationIdentity(unit, mapping), unit, result, snapshot


def test_req_qml017_ac03_nested_shadow_and_disjoint_declarations_are_distinct(tmp_path):
    """Nearest declaration wins only within its own source lexical lifetime."""
    source = '''void use(QQmlApplicationEngine &engine) {
 engine.load("outer");
 { QQmlApplicationEngine engine; engine.load("inner"); }
 { QQmlApplicationEngine engine; engine.load("other"); }
 engine.load("again");
}'''
    index, unit, result, before = identity_index(tmp_path, source)
    values = [index.resolve("engine", unit.source.index(('engine.load("' + name).encode()))
              for name in ("outer", "inner", "other", "again")]
    assert all(value["status"] == "resolved" for value in values)
    assert values[0]["declaration_id"] == values[3]["declaration_id"]
    assert len({value["declaration_id"] for value in values}) == 3
    assert (result["nodes"], result["edges"]) == before


def test_req_qml017_ac04_auto_and_explicit_handles_keep_declaration_identity(tmp_path):
    """An initializer call and subsequent handle use share the actual declaration."""
    source = '''void use() { QQmlApplicationEngine engine;
 auto root = engine.rootObjects().first(); root->property("value");
 QObject *other = engine.rootObjects().first(); other->property("value"); }'''
    index, unit, _, _ = identity_index(tmp_path, source)
    for name in ("root", "other"):
        assigned = unit.source.index(b"engine.rootObjects", unit.source.index((name + " =").encode()))
        used = unit.source.index((name + "->property").encode())
        left, right = index.resolve(name, assigned), index.resolve(name, used)
        assert left["status"] == right["status"] == "resolved"
        assert left["declaration_id"] == right["declaration_id"]


@pytest.mark.parametrize("prefix,expected", [
    ('engine = replacement;', "dynamic"),
    ('{ QQmlApplicationEngine *engine = replacement; engine = replacement; }', "resolved"),
    ('QQmlApplicationEngine *engine;', "ambiguous"),
])
def test_req_qml017_ac04_writes_and_duplicate_declarations_fail_closed(tmp_path, prefix, expected):
    """An inner write cannot poison the outer declaration; actual writes reject."""
    source = f'void use(QQmlApplicationEngine *replacement) {{ QQmlApplicationEngine *engine = new QQmlApplicationEngine; {prefix} engine->load("main"); }}'
    index, unit, _, _ = identity_index(tmp_path, source)
    value = index.resolve("engine", unit.source.index(b'engine->load("main")'))
    assert value["status"] == expected
    assert bool(value["declaration_id"]) is (expected == "resolved")


@pytest.mark.parametrize("source", [
    'void use() { QQmlApplicationEngine engine; if (enabled) { engine.load("main"); } }',
    'void use() { for (QQmlApplicationEngine engine; enabled;) { engine.load("main"); } }',
    'void use() { QQmlApplicationEngine engine; auto f = [&engine] { engine.load("main"); }; }',
    'void use() {\n#if ENABLED\n QQmlApplicationEngine engine;\n#endif\n engine.load("main"); }',
])
def test_req_qml017_ac04_conditional_and_deferred_lifetimes_have_no_identity(tmp_path, source):
    """Conditions and deferred captures cannot authorize a definite engine join."""
    index, unit, _, _ = identity_index(tmp_path, source)
    value = index.resolve("engine", unit.source.index(b'engine.load("main")'))
    assert value["status"] == "dynamic" and value["declaration_id"] == ""


def test_req_qml017_ac04_ids_are_portable_with_original_unicode_bom_crlf_spans(tmp_path):
    """IDs contain no checkout root, and span slices retain original byte offsets."""
    source = '\ufeff// café ✓\r\nvoid use(QQmlApplicationEngine &engine) {\r\n engine.load("main"); }'
    ids = []
    for folder in (tmp_path / "one", tmp_path / "two"):
        folder.mkdir()
        index, unit, _, _ = identity_index(folder, source)
        value = index.resolve("engine", unit.source.index(b'engine.load("main")'))
        assert value["status"] == "resolved" and len(value["declaration_id"]) == 64
        span = value["declaration_span"]
        assert unit.source[span["start_byte"]:span["end_byte"]] == b"&engine"
        assert span["start_row"] == 1
        ids.append(value["declaration_id"])
    assert ids[0] == ids[1]


@pytest.mark.parametrize("identity", [None, "", "a" * 63, "A" * 64, ["a" * 64]])
def test_req_qml017_ac04_missing_or_corrupted_transport_cannot_fall_back_to_name(identity):
    """Legacy names and malformed IDs remain unusable even with an owner key."""
    metadata = {"owner_scope_key": "source_owner", "receiver_reference": "engine", "receiver_declaration_id": identity}
    before = copy.deepcopy(metadata)
    assert source_reference_key(metadata) is None
    assert metadata == before
