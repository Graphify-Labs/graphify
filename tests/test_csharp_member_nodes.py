"""C# fields and properties get a node, like C++ data members (#3006).

`_CSHARP_CONFIG` emitted a `references` edge to a member's *type* and no node for
the member, so C# was the only language with a class-shaped type layer whose
state was absent from the graph. C++ has emitted a node per data member with a
`defines` edge for a while, #2971 is adding the same for C structs, and Swift
computed properties became nodes in #2220. This brings C# to that line.

The node is the class's state, so it does not depend on what that state is typed
as: a primitive and a generic parameter both leave a member behind, even though
neither produces a type reference.
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
    defines = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "defines"}
    return defines, r


def _find(r, label):
    return next(n["id"] for n in r["nodes"] if n["label"] == label)


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def test_auto_property_becomes_a_member_node(tmp_path):
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Variant {\n"
        "    public bool IsShowCategory { get; set; }\n"
        "}\n"
    )})
    assert (_find(r, "Variant"), _find(r, "IsShowCategory")) in defines


def test_field_becomes_a_member_node(tmp_path):
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Variant {\n"
        "    private Widget _widget;\n"
        "}\n"
        "public class Widget { }\n"
    )})
    assert (_find(r, "Variant"), _find(r, "_widget")) in defines


def test_one_declaration_with_several_names_leaves_one_node_each(tmp_path):
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Point {\n"
        "    private int x, y;\n"
        "}\n"
    )})
    point = _find(r, "Point")
    assert (point, _find(r, "x")) in defines
    assert (point, _find(r, "y")) in defines


def test_a_primitive_member_still_gets_a_node(tmp_path):
    # `int` produces no member-worthy type reference, and the member is still
    # part of the class's state.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Counter {\n"
        "    private int _count;\n"
        "    public string Name { get; set; }\n"
        "}\n"
    )})
    counter = _find(r, "Counter")
    assert (counter, _find(r, "_count")) in defines
    assert (counter, _find(r, "Name")) in defines


def test_a_generic_parameter_typed_member_still_gets_a_node(tmp_path):
    # The type-reference path returns early for a type parameter, which is right
    # for a reference and wrong for the member itself.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Box<T> {\n"
        "    private T _value;\n"
        "}\n"
    )})
    assert (_find(r, "Box"), _find(r, "_value")) in defines


def test_a_const_member_gets_a_node(tmp_path):
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Limits {\n"
        "    public const int Max = 100;\n"
        "}\n"
    )})
    assert (_find(r, "Limits"), _find(r, "Max")) in defines


def test_member_type_references_are_kept(tmp_path):
    # Regression guard for #1591: the member node is additive, the reference to
    # the member's type stays.
    _, r = _extract(tmp_path, {"S.cs": (
        "public class Holder {\n"
        "    public Widget Main { get; set; }\n"
        "}\n"
        "public class Widget { }\n"
    )})
    references = {(e["source"], e["target"], e.get("context")) for e in r["edges"]
                  if e["relation"] == "references"}
    assert (_find(r, "Holder"), _find(r, "Widget"), "field") in references
    assert "Main" in _labels(r)


def test_methods_are_still_methods(tmp_path):
    # A property is not a method: it lands on `defines`, the method on `method`.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Variant {\n"
        "    public bool Flag { get; set; }\n"
        "    public void Touch() { }\n"
        "}\n"
    )})
    variant = _find(r, "Variant")
    methods = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "method"}
    assert (variant, _find(r, "Flag")) in defines
    assert (variant, _find(r, ".Touch()")) in methods
    assert (variant, _find(r, ".Touch()")) not in defines
