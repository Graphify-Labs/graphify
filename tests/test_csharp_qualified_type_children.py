"""INC-QML-94: actual qualified-type AST children own nested reference facts."""
from __future__ import annotations

import html

import pytest

from graphify.extract import extract, extract_csharp


def references(result):
    nodes = {node["id"]: node for node in result["nodes"]}
    return [(nodes[edge["target"]], edge) for edge in result["edges"] if edge["relation"] == "references"]


@pytest.mark.parametrize("declaration", [
    "public System.Collections.Generic.Dictionary<string, Domain.Widget> Value;",
    "public System.Collections.Generic.Dictionary<string, Domain.Widget> Value{get;set;}",
    "public System.Collections.Generic.Dictionary<string, Domain.Widget> Value(){return null;}",
    "public void Value(System.Collections.Generic.Dictionary<string, Domain.Widget> value){}",
    "public System.Collections.Generic.Dictionary<string, Domain.Widget> this[int key]=>null;",
])
def test_req_qml022_ac02_dotted_argument_cannot_replace_qualified_container(tmp_path, declaration):
    """The actual name field owns Dictionary; Domain.Widget remains its generic argument in every member role."""
    path = tmp_path / "Members.cs"
    path.write_text("namespace Domain{class Widget{}}class Holder{" + declaration + "}")
    for result in (extract_csharp(path), extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)):
        facts = references(result)
        assert any(node["label"] == "Dictionary" and edge.get("metadata", {}).get("ref_qualifier") == "System.Collections.Generic"
                   for node, edge in facts)
        assert any(node["label"] == "Widget" and edge.get("context") == "generic_arg"
                   and edge.get("metadata", {}).get("ref_qualifier") == "Domain" for node, edge in facts)
        assert not any(node["label"] in {"Widget>", "Domain", "string"} for node, _ in facts)


def test_req_qml022_ac02_generic_qualifier_arguments_are_collected_without_namespace_placeholders(tmp_path):
    """Generic arguments on both nested segments are source type uses; namespace tokens are not."""
    path = tmp_path / "Members.cs"
    path.write_text("class Widget{}class Key{}class Holder{N.Outer<Widget>.Inner<Key> value;}")
    result = extract_csharp(path)
    facts = references(result)
    assert {node["label"] for node, edge in facts if edge.get("context") == "generic_arg"} == {"Widget", "Key"}
    assert any(node["label"] == "Inner" and html.unescape(edge.get("metadata", {}).get("ref_qualifier", "")) == "N.Outer<Widget>" for node, edge in facts)
    assert not any(node["label"] == "N" for node, _ in facts)


def test_req_qml022_ac06_qualified_argument_bypasses_only_its_actual_type_parameter_shadow(tmp_path):
    """A source-qualified Domain.T is distinct from lexical T; the bare generic argument stays unbound."""
    path = tmp_path / "Members.cs"
    path.write_text("namespace Domain{class T{}}class Holder<T>{N.Pair<T,Domain.T> value;}")
    result = extract_csharp(path)
    typed = [(node, edge) for node, edge in references(result) if node["label"] == "T"]
    assert len(typed) == 1 and typed[0][1]["metadata"]["ref_qualifier"] == "Domain"


def test_req_qml022_ac06_global_type_reference_selects_exact_root_without_alias_borrowing(tmp_path):
    """The built-in root qualifier cannot be redirected by a same-named using alias or namespace class."""
    path = tmp_path / "Members.cs"
    path.write_text("using Widget=Other.Widget;class Widget{}namespace Other{class Widget{}}"
                    "class Holder<Widget>{public global::Widget Item{get;set;}}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    root = next(node for node in result["nodes"] if node["label"] == "Widget" and node.get("_callable_class")
                and not node.get("metadata", {}).get("namespace"))
    targets = [(node, edge) for node, edge in references(result) if edge.get("metadata", {}).get("ref_token") == "Widget"]
    assert len(targets) == 1 and targets[0][0]["id"] == root["id"]
    assert targets[0][1]["metadata"]["ref_qualifier"] == "global::"
    assert not any(node["label"] == "global" for node, _ in references(result))


def test_req_qml022_ac06_unknown_alias_qualifier_cannot_lend_a_global_type(tmp_path):
    """An unsupported alias-qualified spelling is no authority for an unrelated global T."""
    path = tmp_path / "Members.cs"
    path.write_text("class T{}class Alias{}class Holder{Alias::T value;}")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert not any(node.get("source_file") and node["label"] in {"T", "Alias"} for node, _ in references(result))
