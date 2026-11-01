"""INC-QML-110: source-owned class case survives direct and canonical consumers."""
from __future__ import annotations

import json
import hashlib

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_member_identity import member_fact
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.extractors.qt_cpp_type_scope import NativeTypeScope
from graphify.paths import load_node_link_graph
from tests.cpp_class_case_helpers import classes, member_calls, produced, source
from tests.cpp_same_unit_helpers import validate_span


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("out_of_line,forwards", [(False, False), (True, False), (True, True)])
@pytest.mark.parametrize("profile", ["lf", "bom_crlf"])
def test_req_qml022_ac02_distinct_global_class_case_keeps_actual_members(tmp_path, mode, out_of_line, forwards, profile):
    """The normalization domain must not merge two distinct literal class owners."""
    raw = source(out_of_line=out_of_line, forwards=forwards)
    if profile == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80 original\r\n" + raw.replace(b"\n", b"\r\n")
    result = produced(tmp_path, raw, mode=mode)
    owners = classes(result)
    assert set(owners) == {"Box", "box"} and len({node["id"] for node in owners.values()}) == 2
    fields = [node for node in result["nodes"] if node.get("label") == "field"]
    assert len(fields) == 2 and len({node["id"] for node in fields}) == 2
    for owner in owners.values():
        assert validate_span(raw, class_fact(owner)).startswith(b"struct ")
        actual = [edge["target"] for edge in result["edges"] if edge["source"] == owner["id"] and edge.get("relation") == "method"]
        assert len(actual) == 1
        assert member_fact(next(node for node in result["nodes"] if node["id"] == actual[0]))
    assert len(member_calls(result)) == 2
    graph = build_from_json(result, root=tmp_path)
    output = tmp_path / "saved.json"
    assert to_json(graph, {}, str(output), force=True)
    restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
    assert {name: restored.nodes[node["id"]]["metadata"]["cpp_class"] for name, node in owners.items()} == {
        name: node["metadata"]["cpp_class"] for name, node in owners.items()}


def test_req_qml008_ac02_class_case_ids_are_order_line_and_root_independent(tmp_path):
    """Only an actual collision changes legacy spelling; source order/line never selects a winner."""
    identities = []
    for index, (reverse, prefix) in enumerate([(False, b""), (True, b"// shifted source\n")]):
        root = tmp_path / str(index)
        root.mkdir()
        result = produced(root, prefix + source(reverse=reverse), mode="facade")
        assert set(classes(result)) == {"Box", "box"}
        identities.append({name: node["id"] for name, node in classes(result).items()})
    assert identities[0] == identities[1]


def test_req_qml008_ac02_unambiguous_global_and_namespace_ids_preserve_legacy_contract(tmp_path):
    """The repair does not rename every global class or the existing qualified recipe."""
    path = tmp_path / "unit.cpp"
    result = produced(tmp_path, b"struct Box{}; namespace Public {struct Box{};}")
    owners = classes(result)
    assert owners["Box"]["id"] == _make_id(_file_stem(path), "Box")
    from graphify.extractors.cpp_identity import qualified_class_id
    assert owners["Public::Box"]["id"] == qualified_class_id(_file_stem(path), "Public::Box")


@pytest.mark.parametrize("names", [("Cpp",), ("Cpp", "CPP")])
def test_req_qml008_ac02_file_class_collision_keeps_actual_file_and_literal_owners(tmp_path, names):
    """The existing #4854 file reservation stays independent of the class-only census."""
    raw = ("void helper(){}\n" + "\n".join(f"struct {name}{{void run(){{helper();}}}};" for name in names)).encode()
    result = produced(tmp_path, raw)
    file, = [node for node in result["nodes"] if node["id"] == _make_id(str(tmp_path / "unit.cpp"))]
    assert file["label"] == "unit.cpp" and not file.get("_callable_class")
    owners = classes(result)
    assert set(owners) == set(names) and len({node["id"] for node in owners.values()}) == len(names)
    assert file["id"] not in {node["id"] for node in owners.values()}
    assert len(member_calls(result)) == len(names)


def test_req_qml022_ac02_class_case_type_and_unambiguous_alias_targets_remain_distinct(tmp_path):
    """Existing type/alias references use exact class names and actual allocated IDs."""
    raw = (b"struct Box{};struct box{};using UpperAlias=Box;using LowerAlias=box;"
           b"struct Holder{Box *upper;box *lower;UpperAlias *namedUpper;LowerAlias *namedLower;};")
    result = produced(tmp_path, raw)
    owners = classes(result)
    assert set(owners) == {"Box", "box", "Holder"}
    aliases = {node["label"]: node for node in result["nodes"] if node["label"] in {"UpperAlias", "LowerAlias"}}
    unit = read_cpp(tmp_path / "unit.cpp", tmp_path)
    types = NativeTypeScope(unit, map_cpp(unit, result["nodes"], result["edges"], root=tmp_path))
    for alias, target in [("UpperAlias", "Box"), ("LowerAlias", "box")]:
        assert types.resolve_class(alias, raw.index((alias + " *named").encode())) == ([owners[target]["id"]], "")
        assert any(edge["source"] == owners["Holder"]["id"] and edge["target"] == aliases[alias]["id"]
                   and edge.get("relation") == "references" for edge in result["edges"])


@pytest.mark.parametrize("kind", ["forward", "conditional", "duplicate"])
def test_req_qml022_ac06_case_census_cannot_choose_an_unproved_complete_class(tmp_path, kind):
    """A collision domain preserves source declarations while independent body proof stays strict."""
    upper = (b"struct Box;" if kind == "forward" else b"struct Box{void run(){helper();}};")
    if kind == "conditional":
        upper = b"#if FEATURE\n" + upper + b"\n#endif\n"
    elif kind == "duplicate":
        upper += upper
    raw = b"void helper(){}\n" + upper + b"\nstruct box{void run(){helper();}};\n"
    result = produced(tmp_path, raw)
    owners = classes(result)
    assert set(owners) == {"Box", "box"} and owners["Box"]["id"] != owners["box"]["id"]
    assert class_fact(owners["box"])["is_definition"] and not class_fact(owners["box"])["ambiguous"]
    assert len(member_calls(result)) == 1


@pytest.mark.parametrize("mode", ["direct", "facade"])
@pytest.mark.parametrize("constructors", [False, True])
def test_req_qml008_ac02_literal_class_domain_lookalike_keeps_legacy_identity(tmp_path, mode, constructors):
    """An actual literal name reserves its ID before collision domains are allocated."""
    lookalike = "cppq_" + hashlib.sha256(b"Box").hexdigest() + "_Box"
    legacy = produced(tmp_path, f"struct {lookalike}{{}};".encode(), mode=mode)
    legacy_id = classes(legacy)[lookalike]["id"]
    expected = None
    for reverse in (False, True):
        names = ["Box", "box", lookalike]
        if reverse:
            names.reverse()
        forward = "".join(f"struct {name};\n" for name in names)
        bodies = "".join(f"struct {name}{{int field;" + (name if constructors else "void run")
                         + "(){helper();}};\n" for name in names)
        raw = ("void helper(){}\n" + forward + bodies).encode()
        result = produced(tmp_path, raw, mode=mode)
        owners = classes(result)
        assert set(owners) == set(names) and len({node["id"] for node in owners.values()}) == 3
        assert owners[lookalike]["id"] == legacy_id
        actual = {name: node["id"] for name, node in owners.items()}
        if expected is None:
            expected = actual
        assert actual == expected
        assert len([edge for edge in result["edges"] if edge.get("relation") == "calls"]) == 3
        for owner in owners.values():
            assert validate_span(raw, class_fact(owner)).startswith(b"struct ")
        graph = build_from_json(result, root=tmp_path)
        output = tmp_path / "lookalike.json"
        assert to_json(graph, {}, str(output), force=True)
        restored = load_node_link_graph(json.loads(output.read_text(encoding="utf-8")))
        assert all(restored.nodes[node["id"]]["metadata"]["cpp_class"] == node["metadata"]["cpp_class"]
                   for node in owners.values())
