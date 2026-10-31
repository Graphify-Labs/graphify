"""REQ-QML-018-AC03/AC04/AC06: original C++ declarator shape bounds API authority."""
from __future__ import annotations

import copy

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.qt_qml_projection import allows_qt_qml_edge
from tests.qt_adoption_fixture import NATIVE, sources
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("declaration", [
    "Backend **makeBackend()", "Backend *&makeBackend()", "Backend &&makeBackend()",
    "Backend makeBackend()", "Backend (*makeBackend())[2]", "Backend (*makeBackend())()",
])
def test_req_qml018_ac03_factory_unsupported_shape_cannot_lend_api(tmp_path, declaration):
    """Valid syntax with multiple indirections, values or compound returns stays opaque."""
    native = NATIVE.replace("Backend *makeBackend()", declaration)
    result = analysis(tmp_path, sources(tmp_path, native=native))
    assert not sites(result, "context_binding")


@pytest.mark.parametrize("declaration", [
    "Backend **backend", "Backend *&backend", "Backend backend[2]",
    "Backend (*backend)()", "Backend backend",
])
def test_req_qml018_ac03_field_unsupported_shape_cannot_lend_api(tmp_path, declaration):
    """A field's named base class alone does not establish one object endpoint."""
    native = NATIVE.replace("Backend *backend", declaration)
    result = analysis(tmp_path, sources(tmp_path, "factory->backend", native=native))
    assert not sites(result, "context_binding")


@pytest.mark.parametrize("raw,getter", [
    ("Service**", "Service **"), ("Service*&", "Service *&"),
    ("Service&&", "Service &&"), ("Service", "Service "),
])
def test_req_qml018_ac04_child_unsupported_shape_cannot_lend_signal(tmp_path, raw, getter):
    """Matching property/getter base classes cannot erase unsupported pointer depth."""
    native = NATIVE.replace("Q_PROPERTY(Service* service", "Q_PROPERTY(" + raw + " service")
    native = native.replace("Service *service()", getter + "service()")
    result = analysis(tmp_path, sources(tmp_path, native=native))
    assert len(sites(result, "context_binding")) == 1
    by_id = {node["id"]: node for node in result["nodes"]}
    assert not any(qt_metadata(by_id[qt_metadata(node)["endpoint_proof"]["class_id"]]).get("class_name") == "Service"
                   for node in sites(result, "context_access"))
    assert not sites(result, "context_subscription")


@pytest.mark.parametrize("declaration,expression", [
    ("Factory **factory", "factory->makeBackend()"),
    ("Factory *&factory", "factory->makeBackend()"),
    ("Factory *factory[2]", "factory->makeBackend()"),
    ("Factory (*factory)()", "factory->makeBackend()"),
    ("Factory factory", "factory->makeBackend()"),
    ("Factory *factory", "factory.makeBackend()"),
])
def test_req_qml018_ac03_root_shape_must_match_literal_member_operator(tmp_path, declaration, expression):
    """The selected lexical declaration retains its shape before member traversal."""
    inputs = sources(tmp_path, expression)
    inputs["access.cpp"] = inputs["access.cpp"].replace("Factory *factory", declaration)
    assert not sites(analysis(tmp_path, inputs), "context_binding")


@pytest.mark.parametrize("root,expression,returned", [
    ("Factory *const factory", "factory->makeBackend()", "Backend * const"),
    ("const Factory *factory", "factory->makeBackend()", "const Backend *"),
    ("Factory &factory", "factory.makeBackend()", "Backend *"),
    ("Factory factory", "factory.makeBackend()", "Backend *"),
])
def test_req_qml018_ac03_single_pointer_reference_and_cv_shapes_remain_inspectable(tmp_path, root, expression, returned):
    """Supported root/value and API forms retain lexical CV rather than stripping it."""
    native = NATIVE.replace("Backend *makeBackend()", returned + " makeBackend()")
    inputs = sources(tmp_path, expression, native=native)
    inputs["access.cpp"] = inputs["access.cpp"].replace("Factory *factory", root)
    result = analysis(tmp_path, inputs)
    assert len(sites(result, "context_binding")) == 1
    member = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    assert qt_metadata(member)["api_type_spelling"].strip() == returned.strip()
    exposure = sites(result, "context_exposure")[0]
    assert qt_metadata(exposure)["provider_root_type_spelling"].strip() == root.replace("factory", "").strip()


@pytest.mark.parametrize("corruption", ["factory", "property", "getter", "root", "operator"])
def test_req_qml018_ac06_consumer_rejects_corrupt_declarator_shape(tmp_path, corruption):
    """Persisted canonical targets cannot lend API authority after shape corruption."""
    result = analysis(tmp_path, sources(tmp_path))
    nodes, edges = copy.deepcopy((result["nodes"], result["edges"]))
    by_id = {node["id"]: node for node in nodes}
    edge = next(edge for edge in edges if edge.get("context") == "qt_context_subscription")
    source, target = by_id[edge["source"]], by_id[edge["target"]]
    if corruption in {"root", "operator"}:
        chosen = next(node for node in nodes if qt_metadata(node).get("kind") == "context_exposure")
        if corruption == "root":
            update_qt(chosen, provider_root_type_spelling="Factory **")
        else:
            steps = qt_metadata(chosen)["provider_expression_steps"]
            steps[0]["operator"] = "."
            update_qt(chosen, provider_expression_steps=steps)
    else:
        kind, name = {"factory": ("member", "makeBackend"), "property": ("property", "service"),
                      "getter": ("member", "service")}[corruption]
        chosen = next(node for node in nodes if qt_metadata(node).get("kind") == kind
                      and qt_metadata(node).get("raw_name") == name)
        update_qt(chosen, api_type_spelling="Backend **" if corruption == "factory" else "Service *&")
    assert not allows_qt_qml_edge(source, target, edge, source_id=source["id"], target_id=target["id"], nodes=by_id)


@pytest.mark.parametrize("mode", ["address", "local", "this", "reference_field"])
def test_req_qml018_ac03_source_owned_object_root_forms_retain_api(tmp_path, mode):
    """Address-of, initialized locals, this and reference fields retain bounded lexical authority."""
    inputs = sources(tmp_path, "&backend" if mode == "address" else "local->makeBackend()" if mode == "local"
                     else "factory->backend" if mode == "reference_field" else "factory->makeBackend()")
    if mode == "address":
        inputs["access.cpp"] = inputs["access.cpp"].replace("Backend *backend", "Backend backend")
    elif mode == "local":
        inputs["access.cpp"] = inputs["access.cpp"].replace(" QQmlApplicationEngine", " Factory *local = factory; QQmlApplicationEngine")
    elif mode == "reference_field":
        inputs["native.h"] = inputs["native.h"].replace("Backend *backend", "Backend &backend")
    else:
        body = 'void expose() { QQmlApplicationEngine engine; engine.rootContext()->setContextProperty("backend", this);'
        body += 'engine.load(QUrl("' + (tmp_path / "Main.qml").as_uri() + '")); }'
        inputs["native.h"] = inputs["native.h"].replace("public: Service *service()", "public: " + body + " Service *service()")
        inputs["access.cpp"] = '#include "native.h"\n'
    result = analysis(tmp_path, inputs)
    assert len(sites(result, "context_binding")) == 1
    assert len(sites(result, "context_subscription")) == 2


def test_req_qml018_ac03_opaque_root_alias_retains_shape_uncertainty(tmp_path):
    """A pointer typedef is not normalized into a convenient one-object root."""
    inputs = sources(tmp_path)
    inputs["access.cpp"] = inputs["access.cpp"].replace("void use(Factory *factory", "using Handle = Factory**;\nvoid use(Handle factory")
    result = analysis(tmp_path, inputs)
    assert not sites(result, "context_binding")
    md = qt_metadata(sites(result, "context_exposure")[0])
    assert md["provider_root_type_spelling"] == "Handle"
    assert md["provider_type_reason"] == "native_type_alias_unsupported"


def test_req_qml018_ac03_reference_return_uses_canonical_generic_admission(tmp_path):
    """An admitted reference factory supplies its exact generic callable and declared API."""
    inputs = sources(tmp_path, native=NATIVE.replace("Backend *makeBackend()", "Backend &makeBackend()"))
    result = analysis(tmp_path, inputs)
    member = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    md = qt_metadata(member)
    assert md["api_type_spelling"] == "Backend &" and md["api_type_status"] == "resolved"
    assert md["generic_target_id"] in {node["id"] for node in result["nodes"]}
    assert len(sites(result, "context_binding")) == 1


@pytest.mark.parametrize("returned,status", [("const Backend *", "resolved"), ("Backend **", "unsupported")])
def test_req_qml018_ac03_direct_producer_keeps_original_cv_shape_and_byte_position(tmp_path, returned, status):
    """Direct declaration facts match the facade over BOM, CRLF and a Unicode prefix."""
    from graphify.extractors.qt_cpp_exposure import _class_facts
    from graphify.extractors.qt_cpp_facts import QtFacts
    from graphify.extractors.qt_cpp_mapping import map_cpp
    from graphify.extractors.qt_cpp_syntax import read_cpp
    native = "\ufeff// café\r\n" + NATIVE.replace("Backend *makeBackend()", returned + "makeBackend()").replace("\n", "\r\n")
    result = analysis(tmp_path, sources(tmp_path, native=native))
    unit = read_cpp(tmp_path / "native.h", tmp_path)
    mapping = map_cpp(unit, result["nodes"], result["edges"], root=tmp_path)
    facts = QtFacts(unit)
    _class_facts(mapping, facts, classes=mapping.classes)
    direct = next(node for node in facts.nodes if qt_metadata(node).get("kind") == "member"
                  and qt_metadata(node).get("raw_name") == "makeBackend")
    facade = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "makeBackend")
    fields = ("api_type_spelling", "api_type_target_id", "api_type_status", "api_type_reason", "api_type_position")
    direct_md = qt_metadata(direct)
    assert {key: direct_md[key] for key in fields} == {key: qt_metadata(facade)[key] for key in fields}
    assert direct_md["api_type_spelling"] == returned and direct_md["api_type_status"] == status
    assert unit.source[direct_md["api_type_position"]:].startswith(returned.encode())
