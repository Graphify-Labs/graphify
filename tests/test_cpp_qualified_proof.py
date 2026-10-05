"""REQ-QML-008: qualified joins reject corrupt or competing source authority."""
import copy

import pytest

from graphify.extract import extract_cpp
from graphify.extractors.cpp_class_proof import class_merge_allowed
from graphify.extractors.cpp_member_identity import canonicalize_cpp_members, member_merge_allowed


def accepted(root):
    header = root / "backend.h"
    implementation = root / "backend.cpp"
    header.write_text("namespace Public { class Base { public: void run(int value); }; }", encoding="utf-8")
    implementation.write_text('#include "backend.h"\nusing namespace Public;\nvoid Base::run(int value) {}', encoding="utf-8")
    results = [extract_cpp(path) for path in (header, implementation)]
    nodes = copy.deepcopy([node for result in results for node in result["nodes"]])
    edges = copy.deepcopy([edge for result in results for edge in result["edges"]])
    declaration = next(node for node in nodes if node.get("metadata", {}).get("cpp_member", {}).get("role") == "declaration")
    definition = next(node for node in nodes if node.get("metadata", {}).get("cpp_member", {}).get("role") == "definition")
    owner = next(node for node in nodes if node.get("metadata", {}).get("cpp_class"))
    return nodes, edges, declaration, definition, owner


def test_req_qml008_ac02_literal_using_namespace_binds_exact_prototype_and_raw_call_owner(tmp_path):
    nodes, edges, declaration, definition, _ = accepted(tmp_path)
    original = definition["id"]
    raw_calls = [{"source": original, "target": "observed", "line": 3}]
    canonicalize_cpp_members(nodes, edges, raw_calls)
    assert definition["id"] == declaration["id"] != original
    assert raw_calls == [{"source": declaration["id"], "target": "observed", "line": 3}]
    assert member_merge_allowed([declaration, definition])
    assert not any(edge.get("target") == original for edge in edges)


@pytest.mark.parametrize("corruption", [
    "missing_definition_parent", "foreign_definition_parent", "inferred_definition_parent",
    "wrong_definition_line", "reversed_columns", "noncallable", "corrupt_transport",
    "missing_class", "incomplete_class", "ambiguous_class", "corrupt_class",
    "missing_prototype_parent", "foreign_prototype_parent", "inferred_prototype_parent",
    "wrong_prototype_line", "ambiguous_prototype", "wrong_signature", "wrong_using",
])
def test_req_qml008_ac02_member_join_rejects_missing_corrupt_and_ambiguous_authority(tmp_path, corruption):
    nodes, edges, declaration, definition, owner = accepted(tmp_path)
    original = definition["id"]
    member = definition["metadata"]["cpp_member"]
    if corruption.endswith("definition_parent"):
        links = [edge for edge in edges if edge["target"] == original and edge["relation"] == "contains"]
        assert links
        if corruption.startswith("missing"):
            edges[:] = [edge for edge in edges if edge not in links]
        else:
            for edge in links:
                edge["source_file" if corruption.startswith("foreign") else "confidence"] = (
                    "foreign.cpp" if corruption.startswith("foreign") else "INFERRED")
    elif corruption.endswith("prototype_parent"):
        links = [edge for edge in edges if edge["target"] == declaration["id"] and edge["relation"] == "method"]
        assert links
        if corruption.startswith("missing"):
            edges[:] = [edge for edge in edges if edge not in links]
        else:
            for edge in links:
                edge["source_file" if corruption.startswith("foreign") else "confidence"] = (
                    "foreign.h" if corruption.startswith("foreign") else "INFERRED")
    elif corruption in {"wrong_definition_line", "wrong_prototype_line"}:
        (definition if corruption == "wrong_definition_line" else declaration)["source_location"] = "L99"
    elif corruption == "reversed_columns":
        member["span"].update(start_column=100, end_column=0)
    elif corruption == "noncallable":
        definition["_callable"] = False
    elif corruption == "corrupt_transport":
        member["owner_b64"] = "invalid!"
    elif corruption == "wrong_signature":
        member["signature"] = "0" * 64
    elif corruption == "wrong_using":
        member["using_b64"] = []
    elif corruption == "ambiguous_prototype":
        declaration["metadata"]["cpp_member"]["ambiguous"] = True
    elif corruption == "missing_class":
        owner["metadata"].pop("cpp_class")
    elif corruption == "corrupt_class":
        owner["metadata"]["cpp_class"]["qualified_name_b64"] = "invalid!"
    else:
        owner["metadata"]["cpp_class"]["is_definition" if corruption == "incomplete_class" else "ambiguous"] = (
            False if corruption == "incomplete_class" else True)
    before_calls = [{"source": original}]
    canonicalize_cpp_members(nodes, edges, before_calls)
    assert definition["id"] == original
    assert before_calls == [{"source": original}]
    assert not member.get("bound_owner_b64")


@pytest.mark.parametrize("corruption", ["qualified", "scope", "span", "missing", "ambiguous"])
def test_req_qml008_ac02_class_merge_never_repairs_invalid_qualified_proof_by_label(tmp_path, corruption):
    _, _, _, _, owner = accepted(tmp_path)
    forward = copy.deepcopy(owner)
    forward["source_file"] = "backend.cpp"
    forward["metadata"]["cpp_class"]["is_definition"] = False
    fact = forward["metadata"]["cpp_class"]
    if corruption == "qualified":
        fact["qualified_name_b64"] = "QmFzZQ=="  # Base, not Public::Base.
    elif corruption == "scope":
        fact["scope_b64"] = ""
    elif corruption == "span":
        fact["span"]["start_row"] = True
    elif corruption == "missing":
        forward["metadata"].pop("cpp_class")
    else:
        fact["ambiguous"] = True
    assert not class_merge_allowed([owner, forward])


@pytest.mark.parametrize("declaration,definition,joins", [
    ("const &", "const &", True), ("const", "", False),
    ("volatile", "const", False), ("&", "&&", False),
])
def test_req_qml008_ac02_qualified_member_signature_preserves_cv_and_reference_overloads(tmp_path, declaration, definition, joins):
    header = tmp_path / "backend.h"
    implementation = tmp_path / "backend.cpp"
    header.write_text(f"namespace Public {{class Base {{public: void run() {declaration};}};}}", encoding="utf-8")
    implementation.write_text(f"void Public::Base::run() {definition} {{}}", encoding="utf-8")
    results = [extract_cpp(path) for path in (header, implementation)]
    nodes = [node for result in results for node in result["nodes"]]
    edges = [edge for result in results for edge in result["edges"]]
    prototype = next(node for node in nodes if node.get("metadata", {}).get("cpp_member", {}).get("role") == "declaration")
    method = next(node for node in nodes if node.get("metadata", {}).get("cpp_member", {}).get("role") == "definition")
    canonicalize_cpp_members(nodes, edges)
    assert bool(method["metadata"]["cpp_member"].get("bound_owner_b64")) is joins
    assert member_merge_allowed([prototype, method]) is joins


@pytest.mark.parametrize("extra", [0, 49])
def test_req_qml008_ac02_using_namespace_bound_cannot_discard_competing_owner(tmp_path, extra):
    from tests.qt_analysis_helpers import analysis

    header = "namespace N00 {class Base {public: void run();};} namespace ZZ {class Base {public: void run();};}"
    filler = "".join(f"namespace N{index:02} {{}}" for index in range(1, extra + 1))
    usings = "\n".join(f"using namespace N{index:02};" for index in range(extra + 1))
    implementation = '#include "backend.h"\n' + usings + "\nusing namespace ZZ;\nvoid Base::run() {}"
    result = analysis(tmp_path, {"backend.h": header + filler, "backend.cpp": implementation})
    definitions = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_member", {}).get("role") == "definition"]
    assert len(definitions) == 1 and definitions[0]["source_file"] == "backend.cpp"
    assert not definitions[0]["metadata"]["cpp_member"].get("bound_owner_b64")
    assert not any(edge["target"] == definitions[0]["id"] and edge["relation"] == "method" for edge in result["edges"])
