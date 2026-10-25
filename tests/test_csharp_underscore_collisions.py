"""C# names that differ only by `_` or case keep their own nodes (#4415).

``ids.py:make_id`` strips leading/trailing underscores and casefolds, so in C#
`Action()` / `_Action()`, `Size` / `_Size`, `Load()` / `load()` and the types
`Pair` / `_Pair` each minted ONE id. ``add_node`` kept the first declaration
and dropped the second: the dropped method's calls were credited to the
survivor, and a dropped type's members hung off the other type. This is the
Python collision of #3302; C# gets the same rule: a group with exactly one
name without a leading underscore keeps the plain id on it, every other name
is salted.

Separately, the C# member-call resolver keyed methods by a lowercased
alphanumeric form of the name, so `this.Put()` bound to `_Put()` on a nearer
base class instead of `Put()` further up.
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
        return extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def _ids(r, label):
    return [n["id"] for n in r["nodes"] if n["label"] == label and n.get("source_file")]


def _one(r, label):
    ids = _ids(r, label)
    assert len(ids) == 1, (label, ids)
    return ids[0]


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_underscore_method_pair_keeps_both_methods(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Widget {\n"
        "    public bool Action() { return true; }\n"
        "    protected bool _Action() { return Action(); }\n"
        "}\n"
    )})
    widget, action, private = _one(r, "Widget"), _one(r, ".Action()"), _one(r, "._Action()")
    assert action != private
    assert {(widget, action), (widget, private)} <= _edges(r, "method")
    # The private method's call is its own, not a self-loop on the public one.
    assert (private, action) in _edges(r, "calls")
    assert (action, action) not in _edges(r, "calls")


def test_public_name_keeps_the_id_it_has_without_the_sibling(tmp_path):
    solo = _extract(tmp_path / "a", {"S.cs": (
        "public class Widget { public bool Action() { return true; } }\n"
    )})
    pair = _extract(tmp_path / "b", {"S.cs": (
        "public class Widget {\n"
        "    protected bool _Action() { return true; }\n"
        "    public bool Action() { return true; }\n"
        "}\n"
    )})
    # Adding or removing the private sibling re-points nothing.
    assert _one(pair, ".Action()") == _one(solo, ".Action()")


def test_ids_do_not_depend_on_declaration_order(tmp_path):
    first = _extract(tmp_path / "a", {"S.cs": (
        "public class Widget {\n"
        "    public bool Action() { return true; }\n"
        "    protected bool _Action() { return true; }\n"
        "}\n"
    )})
    second = _extract(tmp_path / "b", {"S.cs": (
        "public class Widget {\n"
        "    protected bool _Action() { return true; }\n"
        "    public bool Action() { return true; }\n"
        "}\n"
    )})
    for label in (".Action()", "._Action()"):
        assert _one(first, label) == _one(second, label)


def test_underscore_property_pair_keeps_both_properties(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Host {\n"
        "    public int Size { get; set; }\n"
        "    private int _Size { get; set; }\n"
        "}\n"
    )})
    host = _one(r, "Host")
    assert {(host, _one(r, "Size")), (host, _one(r, "_Size"))} <= _edges(r, "defines")


def test_case_only_method_pair_keeps_both_methods(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Host {\n"
        "    public void Load() { }\n"
        "    public void load() { }\n"
        "}\n"
    )})
    assert _one(r, ".Load()") != _one(r, ".load()")


def test_overloads_are_not_an_underscore_collision(tmp_path):
    # Overloads are one name, so this rule leaves them alone; they get a node
    # each through the overload rule instead (#4584), the first keeping the
    # plain id.
    r = _extract(tmp_path, {"S.cs": (
        "public class Host {\n"
        "    public void Save() { }\n"
        "    public void Save(int x) { }\n"
        "}\n"
    )})
    ids = _ids(r, ".Save()")
    assert len(ids) == 2
    assert "s_host_save" in ids


def test_member_behind_preprocessor_directive_is_counted(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Host {\n"
        "    public void Run() { }\n"
        "#if DEBUG\n"
        "    private void _Run() { }\n"
        "#endif\n"
        "}\n"
    )})
    assert _one(r, ".Run()") != _one(r, "._Run()")


def test_same_file_partial_halves_share_the_group(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public partial class Host { public void Foo() { } }\n"
        "public partial class Host { private void _Foo() { } }\n"
    )})
    assert _one(r, ".Foo()") != _one(r, "._Foo()")


def test_underscore_type_pair_keeps_both_types_and_their_members(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "namespace Demo {\n"
        "    public class Pair { public void Go() { } }\n"
        "    public class _Pair { public void Stop() { } }\n"
        "}\n"
    )})
    pair, private = _one(r, "Pair"), _one(r, "_Pair")
    assert pair != private
    method = _edges(r, "method")
    assert (pair, _one(r, ".Go()")) in method
    assert (private, _one(r, ".Stop()")) in method


def test_type_behind_file_level_preprocessor_directive_is_counted(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "namespace Demo {\n"
        "#if NET8\n"
        "    public class _Pair { public void Stop() { } }\n"
        "#endif\n"
        "    public class Pair { public void Go() { } }\n"
        "}\n"
    )})
    assert _one(r, "Pair") != _one(r, "_Pair")


def test_underscore_generic_type_pair_keeps_both_types(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Effect<T> { public void Fire() { } }\n"
        "public class _Effect<T> { public void Fire() { } }\n"
    )})
    assert _one(r, "Effect") != _one(r, "_Effect")
    assert len(_ids(r, ".Fire()")) == 2


def test_underscore_nested_type_pair_keeps_both_types(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Host {\n"
        "    public class Item { }\n"
        "    private class _Item { }\n"
        "}\n"
    )})
    assert _one(r, "Item") != _one(r, "_Item")


def test_bases_in_another_file_reach_the_right_type(tmp_path):
    r = _extract(tmp_path, {
        "A.cs": (
            "namespace Demo {\n"
            "    public class _Pair { public void Stop() { } }\n"
            "    public class Pair { public void Go() { } }\n"
            "}\n"
        ),
        "B.cs": (
            "namespace Demo {\n"
            "    public class Z : _Pair { public void M() { this.Stop(); } }\n"
            "    public class Y : Pair { public void N() { this.Go(); } }\n"
            "}\n"
        ),
    })
    inherits = _edges(r, "inherits")
    assert (_one(r, "Z"), _one(r, "_Pair")) in inherits
    assert (_one(r, "Y"), _one(r, "Pair")) in inherits
    calls = _edges(r, "calls")
    assert (_one(r, ".M()"), _one(r, ".Stop()")) in calls
    assert (_one(r, ".N()"), _one(r, ".Go()")) in calls


def test_base_in_the_same_file_reaches_the_right_type(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class _Pair { }\n"
        "public class Pair { }\n"
        "public class Z : _Pair { }\n"
        "public class Y : Pair { }\n"
    )})
    inherits = _edges(r, "inherits")
    assert (_one(r, "Z"), _one(r, "_Pair")) in inherits
    assert (_one(r, "Y"), _one(r, "Pair")) in inherits


def test_member_call_does_not_bind_to_an_underscore_sibling_on_a_nearer_base(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class BaseStore {\n"
        "    public virtual object Get(string n) { return null; }\n"
        "    public virtual bool Put(string n, object v) { return true; }\n"
        "}\n"
        "public class CachedStore : BaseStore {\n"
        "    protected object _Get(string n) { return null; }\n"
        "    protected bool _Put(string n, object v) { return true; }\n"
        "}\n"
        "public class Widget : CachedStore {\n"
        "    public void Consume(Widget other) {\n"
        "        this.Put(\"A\", 1);\n"
        "        other.Get(\"B\");\n"
        "    }\n"
        "}\n"
    )})
    calls = _edges(r, "calls")
    consume = _one(r, ".Consume()")
    assert (consume, _one(r, ".Put()")) in calls
    assert (consume, _one(r, ".Get()")) in calls
    assert (consume, _one(r, "._Put()")) not in calls
    assert (consume, _one(r, "._Get()")) not in calls


def test_member_call_across_partial_halves_binds_by_exact_name(tmp_path):
    r = _extract(tmp_path, {
        "H1.cs": "public partial class Host { public void Foo() { } }\n",
        "H2.cs": (
            "public partial class Host {\n"
            "    private void _Foo() { this.Foo(); }\n"
            "    public void Bar() { this._Foo(); }\n"
            "}\n"
        ),
    })
    calls = _edges(r, "calls")
    assert (_one(r, "._Foo()"), _one(r, ".Foo()")) in calls
    assert (_one(r, ".Bar()"), _one(r, "._Foo()")) in calls


def test_base_call_reaches_the_underscore_method(tmp_path):
    r = _extract(tmp_path, {"S.cs": (
        "public class Widget {\n"
        "    public virtual bool Action() { return true; }\n"
        "    protected virtual bool _Action() { return true; }\n"
        "}\n"
        "public class SubWidget : Widget {\n"
        "    protected override bool _Action() { return base._Action(); }\n"
        "}\n"
    )})
    sub, base = sorted(_ids(r, "._Action()"), key=lambda nid: "subwidget" not in nid)
    assert (sub, base) in _edges(r, "calls")
    assert (sub, _one(r, ".Action()")) not in _edges(r, "calls")
