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
    # Legal C#, and one id after normalization. Each property gets its own node
    # (#4415) and one edge, rather than a second edge hung on the first
    # property's node.
    defines, r = _extract(tmp_path, {"S.cs": (
        "public class Odd {\n"
        "    public int Count { get; set; }\n"
        "    public int count { get; set; }\n"
        "}\n"
    )})
    odd = _find(r, "Odd")
    assert defines == {(odd, _find(r, "Count")), (odd, _find(r, "count"))}
    assert _find(r, "Count") != _find(r, "count")


# The calls a property, indexer or operator makes belong to that member: its
# accessor and operator bodies run code just like a method's.

def _calls(r):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}


def _kind(r, kind):
    return [n for n in r["nodes"] if (n.get("metadata") or {}).get("kind") == kind]


def test_property_accessor_bodies_call_from_the_property(tmp_path):
    _, r = _extract(tmp_path, {"S.cs": (
        "public class Svc {\n"
        "    int _v;\n"
        "    public int Block { get { return Load(); } set { Save(value); } }\n"
        "    public int Arrow { get => Load(); }\n"
        "    public int Body => Compute();\n"
        "    public int Auto { get; set; } = Seed();\n"
        "    int Load() { return _v; }\n"
        "    void Save(int v) { _v = v; }\n"
        "    int Compute() { return 1; }\n"
        "    static int Seed() { return 0; }\n"
        "}\n"
    )})
    calls = _calls(r)
    load, save = _find(r, ".Load()"), _find(r, ".Save()")
    assert {(_find(r, "Block"), load), (_find(r, "Block"), save)} <= calls
    assert (_find(r, "Arrow"), load) in calls
    assert (_find(r, "Body"), _find(r, ".Compute()")) in calls
    # An initializer runs in the constructor, not in the property.
    assert (_find(r, "Auto"), _find(r, ".Seed()")) not in calls


def test_accessor_call_prefers_its_own_type_like_a_method(tmp_path):
    # Other comes last, so a file-wide name lookup would pick its Load().
    _, r = _extract(tmp_path, {"S.cs": (
        "public class Svc {\n"
        "    public int Value => Load();\n"
        "    int Load() { return 1; }\n"
        "}\n"
        "public class Other { public int Load() { return 2; } }\n"
    )})
    own = next(n["id"] for n in r["nodes"] if n["label"] == ".Load()" and "svc" in n["id"])
    other = next(n["id"] for n in r["nodes"] if n["label"] == ".Load()" and "other" in n["id"])
    assert (_find(r, "Value"), own) in _calls(r)
    assert (_find(r, "Value"), other) not in _calls(r)


def test_accessor_call_through_a_typed_receiver_resolves_cross_file(tmp_path):
    _, r = _extract(tmp_path, {
        "Repo.cs": "namespace Demo { public class Repo { public int Count() { return 0; } } }\n",
        "Svc.cs": (
            "namespace Demo { public class Svc {\n"
            "    private Repo _repo;\n"
            "    public int Total => _repo.Count();\n"
            "} }\n"
        ),
    })
    assert (_find(r, "Total"), _find(r, ".Count()")) in _calls(r)


def test_indexer_is_a_node_and_owns_its_accessor_calls(tmp_path):
    _, r = _extract(tmp_path, {"S.cs": (
        "public class Bag {\n"
        "    public int This { get; set; }\n"
        "    public int this[int i] { get { return Get(i); } }\n"
        "    public int this[string k] => Find(k);\n"
        "    int Get(int i) { return i; }\n"
        "    int Find(string k) { return 0; }\n"
        "}\n"
    )})
    indexers = {n["metadata"]["signature"]: n["id"] for n in _kind(r, "indexer")}
    assert set(indexers) == {"int", "string"}
    assert indexers["int"] != indexers["string"]
    # The `This` property keeps the id it had before indexers were nodes.
    assert _find(r, "This") == _find(r, "Bag") + "_this"
    assert _find(r, "This") not in indexers.values()
    calls = _calls(r)
    assert (indexers["int"], _find(r, ".Get()")) in calls
    assert (indexers["string"], _find(r, ".Find()")) in calls


def test_operators_and_conversions_are_nodes_that_own_their_calls(tmp_path):
    _, r = _extract(tmp_path, {"S.cs": (
        "public class Money {\n"
        "    public static Money operator +(Money a, Money b) => Add(a, b);\n"
        "    public static explicit operator int(Money m) { return ToInt(m); }\n"
        "    public static explicit operator long(Money m) { return ToLong(m); }\n"
        "    static Money Add(Money a, Money b) { return a; }\n"
        "    static int ToInt(Money m) { return 0; }\n"
        "    static long ToLong(Money m) { return 0; }\n"
        "}\n"
    )})
    ops = {n["label"]: n["id"] for n in _kind(r, "operator")}
    assert set(ops) == {".operator +()", ".operator int()", ".operator long()"}
    calls = _calls(r)
    assert (ops[".operator +()"], _find(r, ".Add()")) in calls
    assert (ops[".operator int()"], _find(r, ".ToInt()")) in calls
    assert (ops[".operator long()"], _find(r, ".ToLong()")) in calls
    assert (ops[".operator int()"], _find(r, ".ToLong()")) not in calls


def test_accessor_base_call_resolves_to_the_base_in_another_file(tmp_path):
    _, r = _extract(tmp_path, {
        "Base.cs": "namespace Demo { public class Base { public int Compute() { return 0; } } }\n",
        "Svc.cs": (
            "namespace Demo { public class Svc : Base {\n"
            "    public int Total => base.Compute();\n"
            "} }\n"
        ),
    })
    assert (_find(r, "Total"), _find(r, ".Compute()")) in _calls(r)


def test_accessor_call_binds_the_other_partial_half_over_a_same_named_method(tmp_path):
    _, r = _extract(tmp_path, {
        "SvcA.cs": "namespace Demo { public partial class Svc { public int Value => Load(); } }\n",
        "SvcB.cs": "namespace Demo { public partial class Svc { int Load() { return 1; } } }\n",
        "Other.cs": "namespace Demo { public class Other { public int Load() { return 2; } } }\n",
    })
    own = next(n["id"] for n in r["nodes"] if n["label"] == ".Load()" and "svc" in n["id"])
    other = next(n["id"] for n in r["nodes"] if n["label"] == ".Load()" and "other" in n["id"])
    assert (_find(r, "Value"), own) in _calls(r)
    assert (_find(r, "Value"), other) not in _calls(r)


def test_explicit_interface_indexers_keep_their_own_calls(tmp_path):
    _, r = _extract(tmp_path, {"S.cs": (
        "public interface IA { int this[int i] { get; } }\n"
        "public interface IB { int this[int i] { get; } }\n"
        "public class C : IA, IB {\n"
        "    int IA.this[int i] => A();\n"
        "    int IB.this[int i] => B();\n"
        "    int A() { return 1; }\n"
        "    int B() { return 2; }\n"
        "}\n"
    )})
    by_line = {n["source_location"]: n["id"] for n in _kind(r, "indexer")
               if "_c_" in n["id"]}
    assert len(by_line) == 2
    calls = _calls(r)
    assert (by_line["L4"], _find(r, ".A()")) in calls
    assert (by_line["L5"], _find(r, ".B()")) in calls
    assert (by_line["L4"], _find(r, ".B()")) not in calls


def test_property_sharing_a_methods_id_does_not_lend_it_its_calls(tmp_path):
    # `IRun.Next` and `Next()` normalize to one id, which the method owns; the
    # property's call must not be credited to the method (a self-loop here).
    _, r = _extract(tmp_path, {"S.cs": (
        "public interface IRun { int Next { get; } }\n"
        "public class Run : IRun {\n"
        "    int Next() { return Other(); }\n"
        "    int IRun.Next => Next();\n"
        "    int Other() { return 0; }\n"
        "}\n"
    )})
    method = _find(r, ".Next()")
    assert (method, method) not in _calls(r)
    assert (method, _find(r, ".Other()")) in _calls(r)
