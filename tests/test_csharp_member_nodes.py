"""C# properties get a node, like C++ data members (#3006).

`_CSHARP_CONFIG` emitted a `references` edge to a member's *type* and no node for
the member, so C# was the only language with a class-shaped type layer whose
state was absent from the graph. C++ emits a node per data member with `defines`,
#2971 is adding the same for C structs, and #2220 gave Swift computed properties
nodes. This brings C# to that line.

Properties only, not fields. `ids.normalize_id` casefolds and strips leading
underscores, so `_count` and `Count` are the same id: emitting both would hand
the node to whichever the parser reached first, which is the private backing
field, hiding the public member behind it. In C# the property is the state's
public identity, so it is the half worth having first.
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


def test_every_property_on_a_class_gets_its_own_node(tmp_path):
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Variant {\n"
        "    public bool IsShowCategory { get; set; }\n"
        "    public bool ShowOnWeb { get; set; }\n"
        "}\n"
    )})
    variant = _find(r, "Variant")
    assert (variant, _find(r, "IsShowCategory")) in defines
    assert (variant, _find(r, "ShowOnWeb")) in defines


def test_a_primitive_property_still_gets_a_node(tmp_path):
    # `int` produces no member-worthy type reference, and the property is still
    # part of the class's state.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Counter {\n"
        "    public int Count { get; set; }\n"
        "}\n"
    )})
    assert (_find(r, "Counter"), _find(r, "Count")) in defines


def test_a_generic_parameter_typed_property_still_gets_a_node(tmp_path):
    # The type-reference path returns early for a type parameter, which is right
    # for a reference and wrong for the member itself.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Box<T> {\n"
        "    public T Value { get; set; }\n"
        "}\n"
    )})
    assert (_find(r, "Box"), _find(r, "Value")) in defines


def test_a_backing_field_does_not_take_the_property_node(tmp_path):
    # `_count` and `Count` normalize to one id. The public member is the one to
    # keep, and there is exactly one edge rather than two onto a shared node.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Counter {\n"
        "    private int _count;\n"
        "    public int Count { get; set; }\n"
        "}\n"
    )})
    assert (_find(r, "Counter"), _find(r, "Count")) in defines
    assert len(defines) == 1
    assert "_count" not in _labels(r)


def test_a_field_alone_makes_no_member_node_but_keeps_its_type_reference(tmp_path):
    # Fields are out for now, and the reference to a field's type is untouched.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Runner {\n"
        "    private readonly Worker _worker;\n"
        "}\n"
        "public class Worker { }\n"
    )})
    assert defines == set()
    references = {(e["source"], e["target"], e.get("context")) for e in r["edges"]
                  if e["relation"] == "references"}
    assert (_find(r, "Runner"), _find(r, "Worker"), "field") in references


def test_property_type_references_are_kept(tmp_path):
    # Regression guard for #1591: the member node is additive, the reference to
    # the property's type stays.
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


def test_case_only_sibling_properties_do_not_duplicate_an_edge(tmp_path):
    # Legal C#, and one id after normalization. One node, one edge, rather than a
    # second edge hung on the first property's node.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Odd {\n"
        "    public int Count { get; set; }\n"
        "    public int count { get; set; }\n"
        "}\n"
    )})
    assert len(defines) == 1
