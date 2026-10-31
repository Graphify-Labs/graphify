"""INC-QML-71: the mixed-language member audit retains actual C# fields."""
from __future__ import annotations

import base64
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_csharp
from graphify.paths import load_node_link_graph


def fields(result):
    return [node for node in result["nodes"] if node.get("metadata", {}).get("csharp_member", {}).get("kind") == "field"]


@pytest.mark.parametrize("type_name", ["int", "T", "System.Collections.Generic.List<string>",
                                      "System.Action", "int[]", "string?"])
def test_class_fields_keep_actual_names_and_owner(tmp_path, type_name):
    """Primitive/generic/delegate/array fields are declarations, never methods."""
    path = tmp_path / "Member.cs"
    path.write_text(f"class Holder<T> {{ public {type_name} first, second; void Run(){{int local=0;}} }}", encoding="utf-8")
    result = extract_csharp(path)
    values = fields(result)
    assert {n["label"] for n in values} == {"first", "second"}
    owner = next(n for n in result["nodes"] if n["label"] == "Holder")
    for node in values:
        md = node["metadata"]["csharp_member"]
        assert base64.b64decode(md["declared_type_b64"], validate=True).decode() == type_name
        assert md["type_status"] == "source_only"
        assert node.get("_callable") is not True
        assert any(e["source"] == owner["id"] and e["target"] == node["id"] and e["relation"] == "defines" for e in result["edges"])
    assert not any(n["label"] == "local" for n in result["nodes"])


def test_field_method_and_property_name_collisions_preserve_each_symbol(tmp_path):
    """Case/underscore collisions cannot steal callable or property identities."""
    path = tmp_path / "Holder.cs"
    path.write_text("class Holder { int _Value; public int Value {get;set;} int value; "
                    "System.Action _Run; void Run(){} void Use(){Run();} }", encoding="utf-8")
    result = extract_csharp(path)
    nodes = [n for n in result["nodes"] if n["label"].removeprefix(".").removesuffix("()") in {"_Value", "Value", "value", "_Run", "Run", "Use"}]
    assert len(nodes) == len({n["id"] for n in nodes}) == 6
    by_name = {n["label"].removeprefix(".").removesuffix("()"): n["id"] for n in nodes}
    assert any(e["source"] == by_name["Use"] and e["target"] == by_name["Run"] and e["relation"] == "calls" for e in result["edges"])
    assert not any(e["target"] == by_name["_Run"] and e["relation"] == "calls" for e in result["edges"])


def test_fields_have_original_declarator_bytes_and_modifiers(tmp_path):
    """BOM/CRLF/Unicode and initializer commas do not shift the named field span."""
    raw = "\ufeff// café\r\nclass Holder { private static readonly string 名 = Make(1,2), other = \"x\"; }\r\n".encode()
    path = tmp_path / "Holder.cs"
    path.write_bytes(raw)
    result = extract_csharp(path)
    values = fields(result)
    assert {n["label"] for n in values} == {"名", "other"}
    for node in values:
        md = node["metadata"]["csharp_member"]
        span = md["span"]
        assert raw[span["start_byte"]:span["end_byte"]].decode().startswith(node["label"])
        assert md["modifiers"] == ["private", "static", "readonly"]
        assert span["start_row"] == 1


def test_nested_types_namespaces_and_partial_declarations_keep_ownership(tmp_path):
    """Each source-owned field remains with its actual accepted containing type."""
    path = tmp_path / "Members.cs"
    path.write_text("namespace Left { partial class Holder { int first; class Inner { int nested; } } "
                    "partial class Holder { int second; } } namespace Right { class Holder { int first; } }", encoding="utf-8")
    result = extract_csharp(path)
    values = fields(result)
    assert len(values) == 4
    owners = {n["id"]: n for n in result["nodes"] if n.get("_callable_class")}
    for node in values:
        md = node["metadata"]["csharp_member"]
        parents = {e["source"] for e in result["edges"] if e["target"] == node["id"] and e["relation"] == "defines"}
        assert len(parents) == 1 and parents <= owners.keys()
        assert owners[next(iter(parents))]["label"] == ("Inner" if node["label"] == "nested" else "Holder")
    first = [n for n in values if n["label"] == "first"]
    assert len({n["id"] for n in first}) == 2
    assert len({e["source"] for e in result["edges"] if e["target"] in {n["id"] for n in first} and e["relation"] == "defines"}) == 2


def test_partial_syntax_does_not_invent_missing_field_names(tmp_path):
    """A malformed sibling cannot create a field from a type token or initializer."""
    path = tmp_path / "Bad.cs"
    path.write_text("class Bad { int good; int ; string broken = ; }", encoding="utf-8")
    result = extract_csharp(path)
    assert {n["label"] for n in fields(result)} <= {"good", "broken"}
    assert any(n["label"] == "good" for n in fields(result))


def test_facade_cold_warm_and_export_reload_preserve_fields(tmp_path):
    """Actual extraction/cache/export retain fields without a second C# runtime."""
    path = tmp_path / "Holder.cs"
    path.write_text("class Holder { public int count; private string _label; }", encoding="utf-8")
    seen = []
    for phase in ("cold", "warm"):
        result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
        assert not result["failed_sources"] and {n["label"] for n in fields(result)} == {"count", "_label"}
        graph = build_from_json(result, root=tmp_path, directed=True)
        output = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(output), force=True)
        loaded = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        durable = fields({"nodes": [{**n, "id": identity} for identity, n in loaded.nodes(data=True)]})
        assert {n["label"] for n in durable} == {"count", "_label"}
        seen.append({(n["id"], n["label"]) for n in durable})
    assert seen[0] == seen[1]


def test_large_field_type_is_explicitly_unsupported_without_losing_the_field(tmp_path):
    """Lossless metadata bounds cannot silently turn a truncated type into authority."""
    path = tmp_path / "Bound.cs"
    path.write_text("class Holder { public Container<" + "A" * 390 + "> value; }", encoding="utf-8")
    result = extract_csharp(path)
    member = fields(result)[0]["metadata"]["csharp_member"]
    assert member["type_status"] == "unsupported" and member["type_reason"] == "field_type_literal_limit"
    assert member["declared_type_b64"] == ""


def test_partial_fields_in_subdirectories_follow_actual_remapped_edges(tmp_path):
    """Prefix and partial-class remaps preserve one edge-owned containing type."""
    paths = []
    for name, field in (("Parts/One.cs", "first"), ("Generated/Two.cs", "second")):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"namespace App {{ partial class Holder {{ int {field}; }} }}", encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    owner = [n for n in result["nodes"] if n["label"] == "Holder"]
    assert len(owner) == 1
    values = fields(result)
    assert {n["label"] for n in values} == {"first", "second"}
    for node in values:
        assert "owner_id" not in node["metadata"]["csharp_member"]
        assert {e["source"] for e in result["edges"] if e["target"] == node["id"] and e["relation"] == "defines"} == {owner[0]["id"]}


@pytest.mark.parametrize("other", ["", "class Other { public void callback(){} }"])
def test_delegate_field_storage_never_becomes_a_concrete_callable_target(tmp_path, other):
    """A field invocation cannot call its storage node or a convenient global method."""
    path = tmp_path / "Delegate.cs"
    path.write_text("class C { public System.Action callback; void Use(){ callback(); } } " + other, encoding="utf-8")
    result = extract_csharp(path)
    caller = next(n["id"] for n in result["nodes"] if n["label"] == ".Use()")
    assert len(fields(result)) == 1
    assert not any(e["source"] == caller and e["relation"] == "calls" for e in result["edges"])


def test_conditional_same_named_fields_retain_each_declaration_and_uncertainty(tmp_path):
    """Unknown preprocessing cannot collapse two alternatives into the first type/span."""
    raw = b"class C {\n#if FLAG\n public int value;\n#else\n public string value;\n#endif\n}\n"
    path = tmp_path / "Conditional.cs"
    path.write_bytes(raw)
    result = extract_csharp(path)
    values = fields(result)
    assert len(values) == len({n["id"] for n in values}) == 2
    assert {base64.b64decode(n["metadata"]["csharp_member"]["declared_type_b64"], validate=True).decode() for n in values} == {"int", "string"}
    for node in values:
        md = node["metadata"]["csharp_member"]
        assert md["conditional"] is True
        assert raw[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"value"


@pytest.mark.parametrize("alternative,label", [("public void value(){}", ".value()"),
                                                ("public int value {get;set;}", "value")])
def test_conditional_field_cannot_hide_a_same_named_method_or_property(tmp_path, alternative, label):
    """Conditional role alternatives keep separate declarations and the callable's ID."""
    path = tmp_path / "Roles.cs"
    path.write_text("class C {\n#if FLAG\n public int value;\n#else\n" + alternative + "\n#endif\n}", encoding="utf-8")
    result = extract_csharp(path)
    values = fields(result)
    assert len(values) == 1
    alternatives = [n for n in result["nodes"] if n["label"] == label and n not in values]
    assert len(alternatives) == 1 and alternatives[0]["id"] != values[0]["id"]


def test_escaped_delegate_field_name_blocks_unescaped_bare_call_fallback(tmp_path):
    """C# identifier escapes cannot bypass lexical field-storage shadowing."""
    path = tmp_path / "Escaped.cs"
    path.write_text("class C { public System.Action @callback; void Use(){ callback(); } } "
                    "class Other { public void callback(){} }", encoding="utf-8")
    result = extract_csharp(path)
    caller = next(n["id"] for n in result["nodes"] if n["label"] == ".Use()")
    assert len(fields(result)) == 1
    assert not any(e["source"] == caller and e["relation"] == "calls" for e in result["edges"])


def test_conditional_field_type_cannot_select_the_last_branchs_receiver(tmp_path):
    """Unknown preprocessing retains both declarations and neither concrete receiver target."""
    path = tmp_path / "Receivers.cs"
    path.write_text("class First { public void Run(){} } class Second { public void Run(){} }\n"
                    "class Holder {\n#if FLAG\nFirst worker;\n#else\nSecond worker;\n#endif\n"
                    "void Use(){worker.Run();} }", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    caller = next(n["id"] for n in result["nodes"] if n["label"] == ".Use()")
    assert len(fields(result)) == 2
    assert not any(e["source"] == caller and e["relation"] == "calls" for e in result["edges"])
