"""Qt source declarations, canonical merges and source-only registration guards."""
from __future__ import annotations

from graphify.extractors.qt_cpp_facts import qt_metadata
from tests.qt_cpp_test_helpers import HEADER, collect, facts


def test_members_properties_and_notify_have_exact_original_evidence(tmp_path):
    result = collect(tmp_path, {"backend.hpp": HEADER})
    class_node = facts(result, "class", "Backend")[0]
    class_md = qt_metadata(class_node)
    assert class_md["source_q_object"] and class_md["is_qobject"]
    assert class_md["generic_target_id"] in {node["id"] for node in result["nodes"]}
    members = {qt_metadata(node)["raw_name"]: qt_metadata(node) for node in facts(result, "member")}
    assert {name: md["roles"] for name, md in members.items()} == {
        "value": [], "next": ["invokable"], "ordinary": [], "valueChanged": ["signal"],
        "setValue": ["slot"], "hidden": ["invokable"]}
    assert members["valueChanged"]["signature"] == "valueChanged(int)"
    assert members["valueChanged"]["parameter_names"] == ["value"]
    assert members["hidden"]["access"] == "private"
    prop = qt_metadata(facts(result, "property", "value")[0])
    assert {key: prop[key] for key in ("raw_type", "read", "write", "notify")} == {
        "raw_type": "int", "read": "value", "write": "setValue", "notify": "valueChanged"}
    source = HEADER.encode()
    assert source[prop["span"]["start_byte"]:prop["span"]["end_byte"]] == b"Q_PROPERTY(int value READ value WRITE setValue NOTIFY valueChanged)"
    links = [qt_metadata(node) for node in facts(result, "property_accessor")]
    assert {link["accessor_role"]: link["status"] for link in links} == {"read": "resolved", "write": "resolved", "notify": "resolved"}
    assert all(link["generic_target_id"] in {node["id"] for node in result["nodes"]} for link in links)


def test_header_implementation_members_reuse_accepted_canonical_ids(tmp_path):
    source = '#include "backend.hpp"\nint Backend::value() const { return 1; }\nint Backend::next(int amount) { return amount; }'
    result = collect(tmp_path, {"backend.hpp": HEADER, "backend.cpp": source})
    for name in ("value", "next"):
        declarations = [qt_metadata(node) for node in facts(result, "member", name)]
        assert len(declarations) == 2
        assert len({item["generic_target_id"] for item in declarations}) == 1
        assert all(item["generic_target_id"] and item["class_id"] for item in declarations)
    assert not any(result.get("qml_failures") for result in result["per_file"])


def test_notify_same_name_ordinary_function_is_not_signal(tmp_path):
    source = '''class B: public QObject { Q_OBJECT Q_PROPERTY(int value READ value NOTIFY changed)
public: int value(); void changed(int value); };'''
    result = collect(tmp_path, {"b.hpp": source})
    notify = next(qt_metadata(node) for node in facts(result, "property_accessor") if qt_metadata(node)["accessor_role"] == "notify")
    assert notify["status"] == "unavailable" and notify["generic_target_id"] == ""
    assert not any(edge.get("metadata", {}).get("qt", {}).get("accessor_role") == "notify" for edge in result["edges"])


def test_identifier_named_element_flags_and_quoted_rejection(tmp_path):
    source = '''class State: public QObject { Q_OBJECT QML_NAMED_ELEMENT(State) QML_SINGLETON QML_UNCREATABLE("Use singleton") };
class Bad: public QObject { Q_OBJECT QML_NAMED_ELEMENT("Bad") };
class Hidden: public QObject { Q_OBJECT QML_ANONYMOUS };'''
    result = collect(tmp_path, {"types.hpp": source})
    registrations = [qt_metadata(node) for node in facts(result, "registration")]
    state = next(md for md in registrations if md["class_name"] == "State")
    assert state["raw_name"] == "State" and state["singleton"] and not state["creatable"]
    bad = next(md for md in registrations if md["class_name"] == "Bad")
    assert bad["status"] == "unsupported" and bad["reason"] == "named_element_requires_identifier"
    hidden = next(md for md in registrations if md["class_name"] == "Hidden")
    assert hidden["anonymous"] and not hidden["raw_name"] and not hidden["creatable"]


def test_literal_registration_variants_exact_versions_and_class_mapping(tmp_path):
    calls = '''void install(Backend *instance) {
qmlRegisterType<Backend>("Demo.Types",1,2,"Backend");
qmlRegisterUncreatableType<Backend>("Demo.Types",1,2,"ReadOnly","reason");
qmlRegisterSingletonType<Backend>("Demo.State",2,0,"State",factory);
qmlRegisterSingletonInstance<Backend>("Demo.State",2,0,"Instance",instance);
qmlRegisterAnonymousType<Backend>("Demo.Types",1);
}'''
    result = collect(tmp_path, {"backend.hpp": HEADER, "register.cpp": calls})
    literal = [qt_metadata(node) for node in facts(result, "registration") if not qt_metadata(node)["module_required"]]
    assert len(literal) == 5 and all(md["status"] == "resolved" for md in literal)
    assert len({md["class_id"] for md in literal}) == 1
    assert {(md["uri"], md["major"], md["minor"], md["raw_name"]) for md in literal} == {
        ("Demo.Types", 1, 2, "Backend"), ("Demo.Types", 1, 2, "ReadOnly"),
        ("Demo.State", 2, 0, "State"), ("Demo.State", 2, 0, "Instance"), ("Demo.Types", 1, 0, "")}


def test_dynamic_unsupported_and_missing_arguments_do_not_become_providers(tmp_path):
    calls = '''void install() {
qmlRegisterType<Backend>(uri,1,0,"Dynamic");
if (enabled) { qmlRegisterType<Backend>("Demo",1,0,"Conditional"); }
qmlRegisterSingletonType<Backend>("Demo",1,0,"MissingCallback");
qmlRegisterUnknown<Backend>("Demo",1,0,"Unknown");
qmlRegisterType<Missing>("Demo",1,0,"Missing");
}'''
    result = collect(tmp_path, {"backend.hpp": HEADER, "register.cpp": calls})
    literal = [qt_metadata(node) for node in facts(result, "registration") if not qt_metadata(node)["module_required"]]
    assert len(literal) == 5 and all(md["status"] != "resolved" for md in literal)
    assert any(md["reason"] == "conditional_registration" for md in literal)
    assert any(md["reason"] == "registration_mechanism_unsupported" for md in literal)
    assert any(md["reason"] == "class_not_in_corpus" for md in literal)


def test_foreign_wrapper_is_explicit_and_nested_macros_do_not_expose_outer(tmp_path):
    source = '''class Outer: public QObject { Q_OBJECT public:
class Inner: public QObject { Q_OBJECT QML_ELEMENT }; };
class Wrapper: public QObject { Q_OBJECT QML_NAMED_ELEMENT(Foreign) QML_FOREIGN(Outer) };'''
    result = collect(tmp_path, {"nested.hpp": source})
    declarations = [qt_metadata(node) for node in facts(result, "registration")]
    assert {md["class_name"] for md in declarations} == {"Outer::Inner", "Wrapper"}
    wrapper = next(md for md in declarations if md["class_name"] == "Wrapper")
    assert wrapper["status"] == "unsupported" and wrapper["unsupported_macros"] == ["QML_FOREIGN"]


def test_conditional_macro_and_property_remain_uncertain(tmp_path):
    source = '''class Backend: public QObject {
Q_OBJECT
#if ENABLE_EXPOSURE
QML_ELEMENT
Q_PROPERTY(int value READ value)
#endif
public: int value();
};'''
    result = collect(tmp_path, {"backend.hpp": source})
    registration = qt_metadata(facts(result, "registration")[0])
    assert registration["status"] == "dynamic" and registration["reason"] == "conditional_exposure"
    prop = qt_metadata(facts(result, "property")[0])
    assert prop["status"] == "dynamic" and prop["reason"] == "conditional_property_declaration"


def test_additional_unsupported_macro_has_original_annotation_evidence(tmp_path):
    result = collect(tmp_path, {"backend.hpp": HEADER.replace("QML_NAMED_ELEMENT(Backend)", "QML_NAMED_ELEMENT(Backend) QML_EXTRA_VERSION(2, 0)")})
    md = qt_metadata(facts(result, "registration")[0])
    assert md["status"] == "unsupported" and md["unsupported_macros"] == ["QML_EXTRA_VERSION"]
    macro = next(item for item in md["annotations"] if item["name"] == "QML_EXTRA_VERSION")
    assert macro["args"] == ["2", "0"]
    source = (tmp_path / "backend.hpp").read_bytes()
    assert source[macro["span"]["start_byte"]:macro["span"]["end_byte"]] == b"QML_EXTRA_VERSION(2, 0)"


def test_pointer_property_name_and_type_remain_separate(tmp_path):
    source = 'class B: public QObject { Q_OBJECT Q_PROPERTY(QObject *child READ child) public: QObject *child(); };'
    result = collect(tmp_path, {"b.hpp": source})
    prop = qt_metadata(facts(result, "property", "child")[0])
    assert prop["raw_type"] == "QObject*" and prop["status"] == "resolved" and prop["read"] == "child"
