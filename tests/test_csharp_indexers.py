"""INC-QML-90: explicit C# indexers are actual source data members."""
from __future__ import annotations

import base64
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_csharp
from graphify.paths import load_node_link_graph


def indexers(result):
    return [n for n in result["nodes"] if n.get("metadata", {}).get("csharp_member", {}).get("kind") == "indexer"]


@pytest.mark.parametrize("owner", ["class", "struct", "interface", "record"])
def test_req_qml022_ac02_explicit_indexer_has_its_actual_containing_type(tmp_path, owner):
    """An actual this-parameter declaration has a source-owned member node and one defines edge."""
    body = "{get;set;}" if owner == "interface" else "{get{return 0;}set{}}"
    path = tmp_path / "Members.cs"
    path.write_text(f"{owner} Holder {{ public int this[int key] {body} }}", encoding="utf-8")
    result = extract_csharp(path)
    member, = indexers(result)
    parent = next(n for n in result["nodes"] if n["label"] == "Holder")
    md = member["metadata"]["csharp_member"]
    assert md["status"] == "source_only" and md["parameter_count"] == 1
    assert base64.b64decode(md["declared_type_b64"], validate=True) == b"int"
    assert member.get("_callable") is not True
    assert [(e["source"], e["target"]) for e in result["edges"]
            if e["relation"] == "defines" and e["target"] == member["id"]] == [(parent["id"], member["id"])]


def test_req_qml022_ac02_indexer_overloads_interfaces_and_named_members_keep_distinct_ids(tmp_path):
    """Role/signature identity cannot collide with @this, fields, properties or another overload."""
    path = tmp_path / "Members.cs"
    path.write_text("interface IMap{int this[int key]{get;}} class Holder:IMap {"
                    "public int this[int key]=>0; public int this[string key]=>1; "
                    "int IMap.this[int key]=>2; public int @this{get;set;} public int this_int;}", encoding="utf-8")
    result = extract_csharp(path)
    members = indexers(result)
    assert len(members) == 4 and len({n["id"] for n in members}) == 4
    ordinary = [n for n in result["nodes"] if n["label"] in {"@this", "this_int"}]
    assert len(ordinary) == 2 and not {n["id"] for n in ordinary} & {n["id"] for n in members}
    assert not any(n["label"] in {"get_Item", "set_Item", ".get_Item()", ".set_Item()"} for n in result["nodes"])


def test_req_qml022_ac02_indexer_keeps_original_type_parameter_and_accessor_provenance(tmp_path):
    """BOM/CRLF/Unicode coordinates describe actual tokens, modifiers and bodies without runtime methods."""
    raw = ("\ufeff// café 雪\r\nclass Key{} class Widget{} class Holder{\r\n Widget item;\r\n"
           " public ref readonly Widget this[Key 名] { get { return ref item; } }\r\n"
           " public Widget this[int key, params string[] rest] { get=>item; private set{} }\r\n} ").encode()
    path = tmp_path / "Members.cs"
    path.write_bytes(raw)
    result = extract_csharp(path)
    values = indexers(result)
    assert len(values) == 2
    for member in values:
        md = member["metadata"]["csharp_member"]
        assert raw[md["name_span"]["start_byte"]:md["name_span"]["end_byte"]] == b"this"
        assert raw[md["span"]["start_byte"]:md["span"]["end_byte"]].lstrip().startswith(b"public")
        for parameter in md["parameters"]:
            literal = raw[parameter["type_span"]["start_byte"]:parameter["type_span"]["end_byte"]]
            assert base64.b64decode(parameter["declared_type_b64"], validate=True) == literal
        for accessor in md["accessors"]:
            name = accessor["name_span"]
            assert raw[name["start_byte"]:name["end_byte"]].decode() == accessor["name"]
    assert {p["name"] for n in values for p in n["metadata"]["csharp_member"]["parameters"]} == {"名", "key", "rest"}


def test_req_qml022_ac02_signature_identity_ignores_names_defaults_return_type_and_body(tmp_path):
    """Source signature identity follows parameter types while changed source provenance is refreshed."""
    path = tmp_path / "Members.cs"
    path.write_text("class Holder{public int this[int key=1]=>0;}", encoding="utf-8")
    first, = indexers(extract_csharp(path))
    path.write_text("class Holder{public string this[int other=2]=>null;}", encoding="utf-8")
    second, = indexers(extract_csharp(path))
    assert first["id"] == second["id"]
    assert second["metadata"]["csharp_member"]["parameters"][0]["name"] == "other"
    assert base64.b64decode(second["metadata"]["csharp_member"]["declared_type_b64"]) == b"string"


def test_req_qml022_ac06_facade_cold_warm_export_reload_preserves_indexers(tmp_path):
    """The production cache/graph/export path retains source roles with no element-access call dispatch."""
    path = tmp_path / "Members.cs"
    path.write_text("class Holder{public int this[int key]{get{return 0;}set{}} public int Run(){return this[0];}}", encoding="utf-8")
    direct, = indexers(extract_csharp(path))
    seen = []
    for phase in ("cold", "warm"):
        result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
        member, = indexers(result)
        assert member["metadata"]["csharp_member"] == direct["metadata"]["csharp_member"]
        assert len(member["metadata"]["csharp_member"]["parameters"]) == 1
        assert {a["name"] for a in member["metadata"]["csharp_member"]["accessors"]} == {"get", "set"}
        assert not any(e["relation"] == "calls" and e["target"] == member["id"] for e in result["edges"])
        graph = build_from_json(result, root=tmp_path, directed=True)
        destination = tmp_path / (phase + ".json")
        assert to_json(graph, {}, str(destination), force=True)
        loaded = load_node_link_graph(json.loads(destination.read_text(encoding="utf-8")))
        assert loaded.nodes[member["id"]]["metadata"]["csharp_member"] == member["metadata"]["csharp_member"]
        seen.append(member["id"])
    assert seen[0] == seen[1]


def test_req_qml022_ac02_element_access_arrays_and_positional_records_do_not_invent_indexers(tmp_path):
    """Only explicit indexer declaration syntax can create the new member role."""
    path = tmp_path / "Members.cs"
    path.write_text("record Item(int Value); class Holder{int[] items; int @this; int Read(){return items[0];}}", encoding="utf-8")
    assert not indexers(extract_csharp(path))
