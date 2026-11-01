"""INC-QML-72: bounded member-pointer compatibility preserves original roles."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract_cpp
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


@pytest.mark.parametrize("declaration,name,kind,owner", [
    ("Value Owner::*memberPointer;", "memberPointer", "data", "Owner"),
    ("void (Owner::*memberFunction)(int) const;", "memberFunction", "function", "Owner"),
    ("Value N::Owner::*qualified;", "qualified", "data", "N::Owner"),
    ("Value (::N::Owner::*global);", "global", "data", "::N::Owner"),
    ("Value Owner::*const fixed;", "fixed", "data", "Owner"),
    ("Value Owner::*array[2];", "array", "data", "Owner"),
])
def test_req_qml022_ac02_member_pointer_fields_keep_original_qualification(tmp_path, declaration, name, kind, owner):
    """Source qualification describes the member-pointer type, never its field owner."""
    path = tmp_path / "members.hpp"
    raw = ("\ufeff// café 雪\r\nstruct Value {}; struct Owner {}; namespace N { struct Owner {}; }\r\n"
           "struct Holder {\r\n " + declaration + "\r\n};\r\n").encode()
    path.write_bytes(raw)
    result = extract_cpp(path)
    assert not result.get("parse_errors"), result.get("parse_errors")
    field = [node for node in result["nodes"] if node["label"] == name][0]
    assert not field.get("_callable")
    holder = [node for node in result["nodes"] if node["label"] == "Holder"][0]
    assert any(edge["source"] == holder["id"] and edge["target"] == field["id"] and edge["relation"] == "defines" for edge in result["edges"])
    proof = field["metadata"]["cpp_declarator"]
    pointer = proof["member_pointer"]
    assert pointer["kind"] == kind and pointer["owner_spelling"] == owner
    assert pointer["owner_status"] == "source_only"
    span = proof["span"]
    assert owner.encode() in raw[span["start_byte"]:span["end_byte"]]
    assert name.encode() in raw[span["start_byte"]:span["end_byte"]]
    assert field["source_location"] == f"L{span['start_row'] + 1}"
    unit = read_cpp(path, tmp_path)
    assert len(unit.source) == len(unit.parsed_source)
    assert len(unit.member_pointers) == 1
    assert unit.source == raw


@pytest.mark.parametrize("mixed", [False, True])
def test_req_qml022_ac02_member_pointer_field_cannot_become_typed_object_provider(tmp_path, mixed):
    """A genuine object pointer remains accepted beside the incompatible member-pointer type."""
    declaration = "Target Target::*memberPointer, *ordinary;" if mixed else "Target Target::*memberPointer; Target *ordinary;"
    source = '''class Target : public QObject { Q_OBJECT };
class Holder : public QObject { Q_OBJECT public:
 ''' + declaration + '''
 void (Target::*memberFunction)(int) const;
};'''
    result = analysis(tmp_path, {"members.hpp": source})
    fields = {qt_metadata(node)["raw_name"]: qt_metadata(node) for node in sites(result, "api_field")}
    assert fields["memberPointer"]["api_type_status"] == "unsupported"
    assert fields["memberPointer"]["api_type_reason"] == "member_pointer_is_not_object_pointer"
    assert not fields["memberPointer"]["api_type_target_id"]
    assert "Target::*" in fields["memberPointer"]["raw_type"]
    assert fields["ordinary"]["api_type_status"] == "resolved"
    assert "memberFunction" not in fields
    assert not [node for node in sites(result, "member") if qt_metadata(node)["raw_name"] in {"memberPointer", "memberFunction"}]
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "graph.json"
    to_json(graph, {}, str(output))
    loaded = load_node_link_graph(json.loads(output.read_text()))
    field = [node for node in result["nodes"] if node["label"] == "memberPointer"][0]
    assert loaded.nodes[field["id"]]["metadata"]["cpp_declarator"] == field["metadata"]["cpp_declarator"]


@pytest.mark.parametrize("declaration", [
    "Value Owner<int>::*memberPointer;",
    "Value Owner::*;",
    "void (Owner::*memberFunction)(int;",
    "Value Owner::*get();",
    "Value Owner::*Other::*nested;",
    "int int::*invalidOwner;",
    "void (void::*invalidOwner)(int);",
])
def test_req_qml022_ac06_unsupported_member_pointer_forms_do_not_invent_members(tmp_path, declaration):
    """Templates, missing names, malformed signatures and returned member pointers stay unsupported."""
    path = tmp_path / "members.hpp"
    path.write_bytes(("struct Value {}; struct Holder { " + declaration + " }; ").encode())
    result = extract_cpp(path)
    assert result.get("parse_errors")
    assert not [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_declarator", {}).get("member_pointer")]


def test_req_qml022_ac02_callback_fields_have_no_qt_method_role_but_factory_does(tmp_path):
    """Nearest binding governs Qt methods as well as generic field identity."""
    result = analysis(tmp_path, {"members.hpp": '''class Owner : public QObject { Q_OBJECT };
class Holder : public QObject { Q_OBJECT public:
 void (*callback)(int);
 void (Owner::*memberFunction)(int) const;
 Q_INVOKABLE void (*factory())(int);
};'''})
    methods = {qt_metadata(node)["raw_name"]: qt_metadata(node) for node in sites(result, "member")}
    assert not {"callback", "memberFunction"} & methods.keys()
    assert methods["factory"]["roles"] == ["invokable"]
    assert methods["factory"]["status"] == "resolved"
    for name in ["callback", "memberFunction"]:
        field = [node for node in result["nodes"] if node["label"] == name][0]
        assert field["metadata"]["cpp_declarator"]["kind"] == "field"
        assert not field.get("_callable")


def test_req_qml022_ac06_member_pointer_cannot_supply_context_provider(tmp_path):
    """A genuine QObject field supplies its instance; a member-pointer field cannot."""
    url = (tmp_path / "Main.qml").as_uri()
    source = '''class Target : public QObject { Q_OBJECT };
class Holder : public QObject { Q_OBJECT public: Target Target::*memberPointer; Target *ordinary; };
'''+ f'''void boot(Holder *holder) {{ QQmlApplicationEngine engine;
 engine.rootContext()->setContextProperty("bad", holder->memberPointer);
 engine.rootContext()->setContextProperty("good", holder->ordinary);
 engine.load(QUrl("{url}")); }}'''
    result = analysis(tmp_path, {"members.cpp": source, "Main.qml": "QtObject {}"})
    bindings = sites(result, "context_binding")
    assert [qt_metadata(node)["exposed_name"] for node in bindings] == ["good"]


def test_req_qml022_ac06_member_pointer_fields_coexist_with_existing_overload_cast_recovery(tmp_path):
    """An initializer's member-pointer cast is not another field declarator to adapt."""
    path = tmp_path / "members.hpp"
    path.write_bytes(b'''struct Owner { void signal(int); };
struct Holder {
 void (Owner::*callback)(int);
 inline static auto selected = static_cast<void(Owner::*)(int)>(&Owner::signal);
};''')
    result = extract_cpp(path)
    assert not result.get("parse_errors")
    fields = {node["label"]: node for node in result["nodes"] if node.get("metadata", {}).get("cpp_declarator", {}).get("kind") == "field"}
    assert set(fields) == {"callback", "selected"}
    assert fields["callback"]["metadata"]["cpp_declarator"]["member_pointer"]["kind"] == "function"
    assert "member_pointer" not in fields["selected"]["metadata"]["cpp_declarator"]
