"""REQ-QML-022-AC02/AC06: source-backed member declarators keep their roles."""
from __future__ import annotations

import pytest

from graphify.extract import extract_cpp


def source(tmp_path, body):
    """Byte-authored fixtures expose offset shifts as well as missing nodes."""
    path = tmp_path / "members.hpp"
    raw = ("\ufeff// café 雪\r\nstruct Value {}; struct Base { virtual ~Base() = default; };\r\nusing Callback = void(int);\r\n"
           "class Owner : public Base { public:\r\n" + body + "\r\n};\r\n").encode("utf-8")
    path.write_bytes(raw)
    return raw, extract_cpp(path)


def member(result, label, owner="Owner", relation="defines"):
    """The declared owner edge, rather than a matching label, locates a member."""
    owners = {node["id"] for node in result["nodes"] if node["label"] == owner}
    identities = {edge["target"] for edge in result["edges"]
                  if edge["source"] in owners and edge["relation"] == relation
                  and edge["confidence"] == "EXTRACTED"}
    matches = [node for node in result["nodes"] if node["id"] in identities and node["label"] == label]
    assert len(matches) == 1, (label, matches)
    return matches[0]


@pytest.mark.parametrize("declaration,name", [
    ("Value &borrowed;", "borrowed"),
    ("Value &&moving;", "moving"),
    ("Value *&pointerReference;", "pointerReference"),
    ("Value *const &qualifiedReference;", "qualifiedReference"),
    ("Value *pointer;", "pointer"),
    ("Value plain;", "plain"),
    ("Value array[2];", "array"),
    ("Callback &aliasCallback;", "aliasCallback"),
    ("void (&functionReference)(int);", "functionReference"),
    ("void (*functionPointer)(int);", "functionPointer"),
    ("void (*const constantPointer)(int);", "constantPointer"),
    ("int (*callbacks[2])(int);", "callbacks"),
    ("Value (&arrayReference)[2];", "arrayReference"),
    ("Value (&&rvalueArray)[2];", "rvalueArray"),
    ("Callback *aliases[2];", "aliases"),
    ("int " + "(" * 70 + "nested" + ")" * 70 + ";", "nested"),
])
def test_req_qml022_ac02_member_fields_are_owned_noncallable_declarations(tmp_path, declaration, name):
    """A reference or callback is a data member even when its AST contains a function."""
    raw, result = source(tmp_path, declaration)
    assert not result.get("parse_errors")
    node = member(result, name)
    assert not node.get("_callable") and not node.get("_callable_class")
    assert not any(edge["target"] == node["id"] and edge["relation"] == "method" for edge in result["edges"])
    fact = node.get("metadata", {}).get("cpp_declarator", {})
    assert fact["contract_version"] == 1 and fact["kind"] == "field"
    span = fact["span"]
    fragment = raw[span["start_byte"]:span["end_byte"]]
    assert name.encode() in fragment and fragment in declaration.encode()
    assert node["source_location"] == f"L{span['start_row'] + 1}"
    assert span["start_row"] == 4 and span["end_row"] == 4


@pytest.mark.parametrize("declaration,name", [
    ("Value &borrow();", "borrow"),
    ("Value &&move();", "move"),
    ("Value *pointer();", "pointer"),
    ("void (*factory())(int);", "factory"),
    ("void run() const;", "run"),
])
def test_req_qml022_ac02_function_binding_stays_callable_through_return_wrappers(tmp_path, declaration, name):
    """The binding nearest the name distinguishes a method returning a callback from a callback field."""
    _, result = source(tmp_path, declaration)
    assert not result.get("parse_errors")
    node = member(result, f".{name}()", relation="method")
    assert node.get("_callable") is True
    assert not any(edge["target"] == node["id"] and edge["relation"] == "defines" for edge in result["edges"])


@pytest.mark.parametrize("prototype", [
    "~Owner();", "virtual ~Owner();", "~Owner() noexcept;", "~Owner() override;",
])
def test_req_qml022_ac02_destructor_prototypes_have_distinct_callable_identity(tmp_path, prototype):
    """Typed-less destructor declarations cannot disappear or collapse into their constructor."""
    raw, result = source(tmp_path, "Owner(); " + prototype)
    destructor = member(result, ".~Owner()", relation="method")
    constructor = member(result, ".Owner()", relation="method")
    assert destructor["id"] != constructor["id"]
    assert destructor.get("_callable") is True
    fact = destructor["metadata"]["cpp_declarator"]
    assert fact["kind"] == "destructor"
    span = fact["span"]
    assert raw[span["start_byte"]:span["end_byte"]].startswith(b"~Owner()")


def test_req_qml022_ac02_nested_same_named_members_keep_exact_class_owner(tmp_path):
    """Identical spelling in distinct namespace/nested owners remains separate source facts."""
    path = tmp_path / "members.hpp"
    path.write_text("""struct Value {};
namespace First { struct Owner { Value &field; ~Owner(); }; }
namespace Second { struct Owner { Value &field; ~Owner(); struct Inner { Value &field; ~Inner(); }; }; }
""", encoding="utf-8")
    result = extract_cpp(path)
    fields = [node for node in result["nodes"] if node["label"] == "field"]
    destructors = [node for node in result["nodes"] if node["label"] in {".~Owner()", ".~Inner()"}]
    assert len(fields) == len({node["id"] for node in fields}) == 3
    assert len(destructors) == len({node["id"] for node in destructors}) == 3
    for node in fields + destructors:
        relation = "defines" if node in fields else "method"
        assert len([edge for edge in result["edges"] if edge["target"] == node["id"] and edge["relation"] == relation]) == 1


def test_req_qml022_ac06_inert_or_partial_declarators_do_not_invent_members(tmp_path):
    """Only actual named declarators authorize facts; comments/strings/errors are not names."""
    _, result = source(tmp_path, '''
// Value &ghost; ~Owner(); void (*ghostCallback)(int);
const char *text = "Value &ghost; ~Owner();";
Value &;
void (*)(int);
''')
    labels = {node["label"] for node in result["nodes"]}
    assert not {"ghost", "ghostCallback", ".~Owner()"} & labels
    assert not any(node.get("_callable") for node in result["nodes"] if node["label"] == "text")


@pytest.mark.parametrize("declaration,name,kind", [
    ("Value Owner::*memberPointer;", "memberPointer", "data"),
    ("void (Owner::*memberFunction)(int) const;", "memberFunction", "function"),
])
def test_req_qml022_ac02_member_pointer_compatibility_keeps_original_field_proof(tmp_path, declaration, name, kind):
    """INC72 promotes the original parser-gap controls into exact source-backed field regressions."""
    raw, result = source(tmp_path, declaration)
    assert not result.get("parse_errors")
    owner = next(node for node in result["nodes"] if node["label"] == "Owner")
    node = member(result, name)
    assert not node.get("_callable")
    assert not [edge for edge in result["edges"] if edge["source"] == owner["id"] and edge["relation"] == "method"]
    proof = node["metadata"]["cpp_declarator"]
    pointer = proof["member_pointer"]
    assert pointer["kind"] == kind and pointer["owner_spelling"] == "Owner"
    assert pointer["owner_status"] == "source_only"
    span = proof["span"]
    assert b"Owner::" in raw[span["start_byte"]:span["end_byte"]]


def test_req_qml022_ac02_mixed_declarators_and_existing_destructor_definitions(tmp_path):
    """Each declarator owns its role, while inline/defaulted/deleted definitions retain existing IDs."""
    _, result = source(tmp_path, "Value &first, *second; ~Owner() = default; void run();")
    member(result, "first")
    member(result, "second")
    member(result, ".~Owner()", relation="method")
    member(result, ".run()", relation="method")
