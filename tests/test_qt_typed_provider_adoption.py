"""REQ-QML-018-AC03/AC04: declared factories and typed service paths."""
from __future__ import annotations

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_analysis_helpers import analysis, sites
from tests.qt_adoption_fixture import NATIVE, sources
from tests.qt_adoption_fixture import QML


@pytest.mark.parametrize("expression", ["factory->makeBackend()", "factory->backend"])
def test_req_qml018_ac03_declared_expression_selects_backend_api(tmp_path, expression):
    """A typed return/field lends its declared API, never runtime allocation evidence."""
    result = analysis(tmp_path, sources(tmp_path, expression))
    bindings = sites(result, "context_binding")
    assert len(bindings) == 1
    metadata = qt_metadata(bindings[0])
    assert metadata["provider_class_name"] == "Backend"
    assert metadata["provider_declaration_id"]
    assert metadata.get("provider_type_evidence")


@pytest.mark.parametrize("expression", ["backend", "factory->makeBackend()"])
def test_req_qml018_ac04_typed_service_call_and_property_are_source_owned(tmp_path, expression):
    """The child property's declared Service API owns refresh/count endpoints."""
    result = analysis(tmp_path, sources(tmp_path, expression))
    accesses = sites(result, "context_access")
    by_id = {node["id"]: node for node in result["nodes"]}
    targets = [by_id[qt_metadata(node)["target_id"]] for node in accesses]
    proofs = [qt_metadata(node)["endpoint_proof"] for node in accesses]
    assert any(qt_metadata(by_id[proof["member_fact_id"]]).get("raw_name") == "refresh"
               and proof["canonical_target_id"] == qt_metadata(by_id[proof["member_fact_id"]])["generic_target_id"]
               and by_id[proof["canonical_target_id"]].get("label") == ".refresh()" for proof in proofs)
    assert any(qt_metadata(node).get("raw_name") == "count" for node in targets)
    for access in accesses:
        proof = qt_metadata(access).get("endpoint_proof", {})
        assert proof.get("evidence") and proof.get("canonical_target_id")


@pytest.mark.parametrize("expression", ["backend", "factory->makeBackend()"])
def test_req_qml018_ac04_context_service_subscriptions_have_distinct_sites(tmp_path, expression):
    """Connections and signal.connect preserve direction without delivery calls."""
    result = analysis(tmp_path, sources(tmp_path, expression))
    subscriptions = sites(result, "context_subscription")
    assert len(subscriptions) == 2
    assert {qt_metadata(node).get("subscription_form") for node in subscriptions} == {"Connections", "signal.connect"}
    assert all(qt_metadata(node)["status"] == "resolved" for node in subscriptions)
    assert not [edge for edge in result["edges"] if edge.get("context") == "qt_context_subscription" and edge.get("relation") == "calls"]


@pytest.mark.parametrize("change", [
    lambda native: native.replace("Backend *makeBackend()", "Unknown *makeBackend()"),
    lambda native: native.replace("Backend *makeBackend()", "Backend *makeBackend(int value)"),
    lambda native: native.replace("public: Backend *makeBackend()", "private: Backend *makeBackend()"),
    lambda native: native.replace("Backend *makeBackend() { throw 7; }", "Backend *makeBackend(); Service *makeBackend();"),
])
def test_req_qml018_ac03_unknown_or_conflicting_factory_never_supplies_provider(tmp_path, change):
    """Incomplete, overload, access and conflicting return evidence cannot guess a type."""
    result = analysis(tmp_path, sources(tmp_path, native=change(NATIVE)))
    assert not sites(result, "context_binding") and not sites(result, "context_access")


@pytest.mark.parametrize("expression", ["factory->makeBackend(1)", "factory->missing", "factory->backend->missing()"])
def test_req_qml018_ac03_unsupported_provider_expression_never_executes_or_guesses(tmp_path, expression):
    """Unknown fields, arguments and undeclared intermediate methods remain opaque."""
    result = analysis(tmp_path, sources(tmp_path, expression))
    assert not sites(result, "context_binding")


def test_req_qml018_ac03_multiple_declared_expression_hops_lend_service_api(tmp_path):
    """A public field followed by its public getter lends the final declared API."""
    result = analysis(tmp_path, sources(tmp_path, "factory->backend->service()"))
    binding = sites(result, "context_binding")[0]
    assert qt_metadata(binding)["provider_class_name"] == "Service"


def test_req_qml018_ac03_conditional_provider_declaration_is_not_api_authority(tmp_path):
    """Accepted syntax in an unevaluated preprocessor branch cannot expose a provider."""
    native = "#if FEATURE\n" + NATIVE + "\n#endif\n"
    assert not sites(analysis(tmp_path, sources(tmp_path, "backend", native=native)), "context_binding")


@pytest.mark.parametrize("mutation", ["reassign", "conditional", "private_field"])
def test_req_qml018_ac03_root_identity_and_member_access_are_required(tmp_path, mutation):
    """Declared return type cannot repair a changed lifetime, condition or private field."""
    inputs = sources(tmp_path, "factory->backend" if mutation == "private_field" else "factory->makeBackend()")
    if mutation == "reassign":
        inputs["access.cpp"] = inputs["access.cpp"].replace(" QQmlApplicationEngine", " factory = nullptr; QQmlApplicationEngine")
    elif mutation == "conditional":
        inputs["access.cpp"] = inputs["access.cpp"].replace("engine.rootContext()", "if (factory) engine.rootContext()")
    else:
        inputs["native.h"] = inputs["native.h"].replace(" Backend *backend;", "private: Backend *backend;")
    assert not sites(analysis(tmp_path, inputs), "context_binding")


@pytest.mark.parametrize("change", [
    lambda text: text.replace("Q_PROPERTY(Service* service", "Q_PROPERTY(Unknown* service"),
    lambda text: text.replace("Service *service()", "Unknown *service()"),
    lambda text: text.replace("Q_PROPERTY(Service* service READ service)",
                              "#if FEATURE\n Q_PROPERTY(Service* service READ service)\n#endif"),
    lambda text: text.replace("Q_INVOKABLE void refresh() {}", "Q_INVOKABLE void refresh() {} Q_INVOKABLE void refresh(int count) {}"),
])
def test_req_qml018_ac04_unproven_child_types_or_overloads_do_not_select_terminal_api(tmp_path, change):
    """Property and getter agree on one type; terminal overloads remain unresolved."""
    result = analysis(tmp_path, sources(tmp_path, native=change(NATIVE)))
    assert sites(result, "context_binding")
    assert not any(qt_metadata(node).get("endpoint_proof", {}).get("kind") == "function"
                   for node in sites(result, "context_access"))


def test_req_qml018_ac04_ordinary_method_is_not_a_signal_subscription(tmp_path):
    """A same-name invokable does not lend Qt signal semantics to connect syntax."""
    result = analysis(tmp_path, sources(tmp_path, native=NATIVE.replace("signals: void ready();", "public: Q_INVOKABLE void ready();")))
    assert not sites(result, "context_subscription")


@pytest.mark.parametrize("mutation,expected", [("root", 1), ("callback", 1), ("own_property", 0)])
def test_req_qml018_ac04_qml_lexical_and_property_shadows_precede_context_provider(tmp_path, mutation, expected):
    """Parameter/callback scopes and own properties prevent provider fallback."""
    qml = QML.replace("function run()", "function run(backend)" if mutation == "root" else
                      "function run(handleReady)" if mutation == "callback" else "function run()")
    if mutation == "own_property":
        qml = qml.replace("QtObject {", "QtObject { property QtObject backend: QtObject {}", 1)
    result = analysis(tmp_path, sources(tmp_path, qml=qml))
    assert len(sites(result, "context_subscription")) == expected


@pytest.mark.parametrize("style,expected", [("legacy", False), ("function", True), ("arrow", True)])
def test_req_qml018_ac04_native_implicit_parameters_do_not_bind_explicit_handlers(tmp_path, style, expected):
    """Only legacy blocks inherit native signal names; explicit formals stay local."""
    handler = {"legacy": "onReady: { count }", "function": "function onReady(value) { count }",
               "arrow": "onReady: (value) => { count }"}[style]
    qml = 'import QtQml\nQtObject { property int count: 2; property Connections sub: Connections {'
    qml += 'target: backend.service; ' + handler + ' } }'
    native = NATIVE.replace("void ready();", "void ready(int count);")
    result = analysis(tmp_path, sources(tmp_path, qml=qml, native=native))
    assert len(sites(result, "context_subscription")) == 1
    reads = [node for node in result["nodes"] if node.get("metadata", {}).get("qml", {}).get("kind") == "read"]
    from graphify.extractors.qml_facts import qml_metadata
    count = next(node for node in reads if qml_metadata(node).get("reference") == "count")
    actual = any(edge["source"] == count["id"] and edge.get("context") == "qml_binding_read"
                 for edge in result["edges"])
    assert actual is expected


@pytest.mark.parametrize("path", ["backend.service.parent.service.count", "backend." + "service." * 9 + "count"])
def test_req_qml018_ac04_cyclic_and_oversized_child_paths_stay_unresolved(tmp_path, path):
    """Cycle and chain limits cannot resolve by choosing an earlier convenient type."""
    native = "class Backend;\n" + NATIVE.replace(" Q_PROPERTY(int count READ count)",
        " Q_PROPERTY(int count READ count) Q_PROPERTY(Backend* parent READ parent)")
    native = native.replace("public: int count()", "public: Backend* parent() { throw 7; } int count()")
    qml = "import QtQml\nQtObject { property int count: " + path + " }"
    result = analysis(tmp_path, sources(tmp_path, qml=qml, native=native))
    assert not sites(result, "context_access")


@pytest.mark.parametrize("callback,expected", [("/* callback */ handleReady", 2), ("() => {}", 1), ("handleReady, 7", 1)])
def test_req_qml018_ac04_callback_ast_comment_and_unsupported_forms_are_distinct(tmp_path, callback, expected):
    """Comments preserve a literal callback; arbitrary expressions do not establish it."""
    qml = QML.replace("ready.connect(handleReady)", "ready.connect(" + callback + ")")
    result = analysis(tmp_path, sources(tmp_path, qml=qml))
    assert len(sites(result, "context_subscription")) == expected


def test_req_qml018_ac04_child_property_changed_handler_uses_real_notify_signal(tmp_path):
    """A context child property's change handler retains its differently named NOTIFY."""
    native = NATIVE.replace("Q_PROPERTY(int count READ count)", "Q_PROPERTY(int count READ count NOTIFY actualCount)")
    native = native.replace("signals: void ready();", "signals: void ready(); void actualCount();")
    qml = QML.replace("function onReady()", "function onCountChanged()")
    result = analysis(tmp_path, sources(tmp_path, native=native, qml=qml))
    subscriptions = sites(result, "context_subscription")
    assert len(subscriptions) == 2
    nodes = {node["id"]: node for node in result["nodes"]}
    handler = next(node for node in subscriptions if qt_metadata(node)["subscription_form"] == "Connections")
    proof = qt_metadata(handler)["endpoint_proof"]
    assert qt_metadata(nodes[proof["member_fact_id"]])["raw_name"] == "actualCount"


def test_req_qml018_ac03_duplicate_typed_context_exposures_remain_ambiguous(tmp_path):
    """Two independent exposures cannot choose a convenient provider occurrence."""
    inputs = sources(tmp_path)
    fragment = 'engine.rootContext()->setContextProperty("backend", factory->makeBackend());'
    inputs["access.cpp"] = inputs["access.cpp"].replace(fragment, fragment + fragment)
    result = analysis(tmp_path, inputs)
    bindings = sites(result, "context_binding")
    assert len(bindings) == 2 and all(qt_metadata(node)["status"] == "ambiguous" for node in bindings)
    assert not sites(result, "context_access") and not sites(result, "context_subscription")
