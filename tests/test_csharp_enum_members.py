"""C# enum members get a node and a `case_of` edge, like Java's (#1719).

`enum_declaration` is in `_CSHARP_CONFIG.class_types`, so the enum type was a
node while its members were not — the type sat in the graph as a leaf. Java has
emitted a node per `enum_constant` with a `case_of` edge since #1719 and Kotlin
since #1738 (both from #1700), and Swift does the same for `enum_entry`. The C#
walk already descends into `enum_member_declaration_list` with the enum as
`parent_class_nid`, so this is the Java shape applied where it was missing.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    case_of = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "case_of"}
    return case_of, r


def _find(r, label):
    return next(n["id"] for n in r["nodes"] if n["label"] == label)


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_enum_member_becomes_a_node(tmp_path):
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum ProcessingType {\n"
        "    Process\n"
        "}\n"
    )})
    assert "Process" in _labels(r)
    assert (_find(r, "ProcessingType"), _find(r, "Process")) in case_of


def test_every_member_gets_its_own_node(tmp_path):
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum ProcessingType {\n"
        "    Process,\n"
        "    ProcessAndCompleteIndex\n"
        "}\n"
    )})
    enum_id = _find(r, "ProcessingType")
    assert (enum_id, _find(r, "Process")) in case_of
    assert (enum_id, _find(r, "ProcessAndCompleteIndex")) in case_of


def test_an_explicit_value_does_not_change_the_member(tmp_path):
    # `= 1` parses as a `value` field next to `name`; the member is read off
    # `name`, so an assigned constant is the same shape as a bare one.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum EntityType {\n"
        "    Variant = 1,\n"
        "    Product = 2\n"
        "}\n"
    )})
    enum_id = _find(r, "EntityType")
    assert (enum_id, _find(r, "Variant")) in case_of
    assert (enum_id, _find(r, "Product")) in case_of


def test_case_only_sibling_members_do_not_duplicate_an_edge(tmp_path):
    # Legal C#, and one id after normalization. The first declaration keeps the
    # node rather than a second edge hanging off it.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum Odd {\n"
        "    Value,\n"
        "    value\n"
        "}\n"
    )})
    assert len(case_of) == 1


def test_a_namespaced_enum_still_emits_members(tmp_path):
    # File-scoped namespaces are handled in the same walk; the enum must not
    # lose its members to the namespace hop.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "namespace Catalog.Events;\n"
        "public enum EntityType {\n"
        "    Brand\n"
        "}\n"
    )})
    assert (_find(r, "EntityType"), _find(r, "Brand")) in case_of


def test_an_enum_nested_in_a_class_emits_members(tmp_path):
    # The member's parent is the enum, not the enclosing class.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public class Holder {\n"
        "    public enum Mode {\n"
        "        Fast\n"
        "    }\n"
        "}\n"
    )})
    mode = _find(r, "Mode")
    assert (mode, _find(r, "Fast")) in case_of
    assert (_find(r, "Holder"), _find(r, "Fast")) not in case_of


def test_the_enum_type_node_is_kept(tmp_path):
    # Regression guard: the member nodes are additive. The enum type stays a
    # node and stays contained by its file.
    _, r = _extract(tmp_path, {"S.cs": (
        "public enum ProcessingType {\n"
        "    Process\n"
        "}\n"
    )})
    enum_id = _find(r, "ProcessingType")
    contains = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "contains"}
    assert any(target == enum_id for _, target in contains)


def test_a_member_is_not_a_method(tmp_path):
    # A member lands on `case_of`, never on `method` — nothing should read it
    # as a callable.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum ProcessingType {\n"
        "    Process\n"
        "}\n"
    )})
    member = _find(r, "Process")
    methods = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "method"}
    assert (_find(r, "ProcessingType"), member) in case_of
    assert (_find(r, "ProcessingType"), member) not in methods


def test_an_empty_enum_emits_no_members(tmp_path):
    case_of, r = _extract(tmp_path, {"S.cs": "public enum Empty {\n}\n"})
    assert "Empty" in _labels(r)
    assert case_of == set()


def test_a_property_and_an_enum_member_sharing_a_name_stay_separate(tmp_path):
    # Member ids are scoped to their declaring type, so a class property and an
    # enum member with the same name are two nodes, not one shared node.
    case_of, r = _extract(tmp_path, {"S.cs": (
        "public enum Mode {\n"
        "    Active\n"
        "}\n"
        "public class Widget {\n"
        "    public bool Active { get; set; }\n"
        "}\n"
    )})
    defines = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "defines"}
    enum_member = next(t for s, t in case_of if s == _find(r, "Mode"))
    class_member = next(t for s, t in defines if s == _find(r, "Widget"))
    assert enum_member != class_member
