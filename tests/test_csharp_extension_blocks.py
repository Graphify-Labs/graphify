"""C# 14 `extension(Receiver r) { … }` blocks (#3510).

The bundled tree-sitter-c-sharp 0.23.5 predates the syntax. A block with a
type-parameter list (`extension<T>(IFoo<T> spec)`) lands its header in an ERROR
node and its `{ }` is adopted as the class body, so the members survive as
class methods but the receiver's type is lost: no `references` edge to it and
`spec.Next()` cannot resolve. A block without one (`extension(IFoo spec)`)
parses clean as a constructor named `extension` holding local functions, so
its members vanished outright, with no syntax-error warning. A newer grammar
parses a real `extension_declaration`, which was an unknown wrapper: members
dropped to file level.

In every shape the receiver now binds like a primary-constructor parameter
(a `references` edge from the class, and receiver-typed member calls) and the
members belong to the enclosing static class.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def _refs(r):
    return {(e["source"], e["target"]) for e in r["edges"]
            if e["relation"] == "references"}


def _methods(r):
    return {(e["source"], e["target"]) for e in r["edges"]
            if e["relation"] == "method"}


def _labels(r):
    return {n["label"] for n in r["nodes"]}


# Two receiver candidates with a same-named method: a bare-name match would be a
# WRONG edge, so resolution has to go through the receiver's declared type.
_TYPES = (
    "public interface IFoo { string? Next(); }\n"
    "public class Other { public string? Next() => null; }\n"
)


def _generic_block(members: str = "        public string? Url() => spec.Next();\n") -> str:
    # The reporter's shape: type-parameter list + where clause.
    return (
        _TYPES
        + "public static class E\n"
        "{\n"
        "    extension<T>(IFoo spec) where T : class\n"
        "    {\n" + members + "    }\n"
        "}\n"
    )


def _plain_block(members: str = "        public string? Url() => spec.Next();\n") -> str:
    return (
        _TYPES
        + "public static class E\n"
        "{\n"
        "    extension(IFoo spec)\n"
        "    {\n" + members + "    }\n"
        "}\n"
    )


def _assert_receiver_recovered(calls, r):
    e = _find(r, "E", "_e")
    ifoo = _find(r, "IFoo", "ifoo")
    url = _find(r, ".Url()", "_e_url")
    assert (e, url) in _methods(r), "the member must belong to the static class"
    assert (e, ifoo) in _refs(r), "the receiver type must produce a references edge"
    assert (url, _find(r, ".Next()", "ifoo")) in calls, \
        "spec.Next() must resolve through the receiver's declared type"
    assert (url, _find(r, ".Next()", "other")) not in calls, \
        "must NOT mis-bind to an unrelated same-named method"


def test_generic_receiver_block_binds_the_receiver(tmp_path):
    """The issue's shape: `extension<T>(IFoo<T> spec) where T : class`."""
    calls, r = _calls(tmp_path, {"S.cs": _generic_block()})
    _assert_receiver_recovered(calls, r)


def test_plain_receiver_block_keeps_its_members(tmp_path):
    """`extension(IFoo spec)` parses clean as a constructor named `extension`;
    its members used to vanish without even a partial-parse warning."""
    calls, r = _calls(tmp_path, {"S.cs": _plain_block()})
    _assert_receiver_recovered(calls, r)
    assert "parse_errors" not in r


def test_generic_receiver_type_arguments_are_not_fabricated(tmp_path):
    """`IFoo<T>` under the ERROR shape: the outer name binds, `T` is the block's
    own type parameter and must not become a phantom type node."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "public interface IFoo<T> { string? Next(); }\n"
        "public static class E\n"
        "{\n"
        "    extension<T>(IFoo<T> spec) where T : class\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    assert (e, _find(r, "IFoo", "ifoo")) in _refs(r)
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "ifoo")) in calls
    assert "T" not in _labels(r)


def test_bare_type_parameter_receiver_binds_nothing(tmp_path):
    """`extension<T>(T item)` names no real type."""
    _, r = _calls(tmp_path, {"S.cs": _TYPES + (
        "public static class E\n"
        "{\n"
        "    extension<T>(T item)\n"
        "    {\n"
        "        public string? Url() => item.ToString();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    assert not [t for s, t in _refs(r) if s == e], "no references from a type-parameter receiver"
    assert "T" not in _labels(r)


def test_predefined_receiver_type_is_not_fabricated(tmp_path):
    """`extension(string s)` / `extension<T>(string s)`: a built-in never
    becomes a referenced node (same rule as primary-constructor parameters)."""
    for header in ("extension(string s)", "extension<T>(string s)"):
        _, r = _calls(tmp_path, {"S.cs": (
            "public static class E\n"
            "{\n"
            f"    {header}\n"
            "    {\n"
            "        public int Len() => s.Length;\n"
            "    }\n"
            "}\n"
        )})
        assert "string" not in _labels(r), header
        assert "String" not in _labels(r), header


def test_unnamed_receiver_references_the_type(tmp_path):
    """`extension(IFoo)` declares static extension members: nothing to bind,
    but the type is still a dependency and the members still belong to E."""
    _, r = _calls(tmp_path, {"S.cs": _TYPES + (
        "public static class E\n"
        "{\n"
        "    extension(IFoo)\n"
        "    {\n"
        "        public static IFoo Create() => null!;\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    ifoo = _find(r, "IFoo", "ifoo")
    create = _find(r, ".Create()", "_e_create")
    assert (e, create) in _methods(r)
    assert (e, ifoo) in _refs(r)
    assert (create, ifoo) in _refs(r), "a member's return type is still referenced"


def test_receiver_modifiers_are_not_read_as_the_type(tmp_path):
    for header in ("extension(ref IFoo spec)", "extension<T>(in IFoo spec) where T : class"):
        calls, r = _calls(tmp_path, {"S.cs": _TYPES + (
            "public static class E\n"
            "{\n"
            f"    {header}\n"
            "    {\n"
            "        public string? Url() => spec.Next();\n"
            "    }\n"
            "}\n"
        )})
        _assert_receiver_recovered(calls, r)
        assert not ({"ref", "in"} & _labels(r)), header


def test_qualified_receiver_type_keeps_its_qualifier(tmp_path):
    """Under the ERROR shape `Acme.IFoo<T>` survives only as text; the edge must
    still point at IFoo and carry the qualifier like every other C# type ref."""
    _, r = _calls(tmp_path, {"S.cs": (
        "namespace Acme { public interface IFoo { string? Next(); } }\n"
        "public static class E\n"
        "{\n"
        "    extension<T>(Acme.IFoo<T> spec)\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    edge = next(x for x in r["edges"]
                if x["relation"] == "references" and x["source"] == e)
    assert edge["metadata"]["ref_token"] == "IFoo"
    assert edge["metadata"]["ref_qualifier"] == "Acme"
    assert "Acme" not in {n["label"] for n in r["nodes"] if n.get("type") != "namespace"}


@pytest.mark.parametrize("header", [
    "extension<T>(global::Acme.IFoo<T> spec) where T : class",   # ERROR shape, dotted
    "extension<T>(Alias::IFoo<T> spec) where T : class",         # ERROR shape, using-alias
    "extension(global::Acme.IFoo spec)",                          # constructor shape, dotted
    "extension(Alias::IFoo spec)",                                # constructor shape, using-alias
])
def test_alias_qualified_receiver_resolves_to_the_real_type(tmp_path, header):
    """`global::A.B` is `A.B` at the root and `X::B` is what `X.B` names, so the
    receiver must reach the real definition — not a dangling stub, and never a
    phantom `global` / `Alias` type node."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "using Alias = Acme;\n"
        "namespace Acme { public interface IFoo { string? Next(); } }\n"
        "namespace Acme { public class Other { public string? Next() => null; } }\n"
        "public static class E\n"
        "{\n"
        f"    {header}\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    ifoo = _find(r, "IFoo", "ifoo")
    assert next(n for n in r["nodes"] if n["id"] == ifoo)["source_file"], "must be the real node"
    assert (e, ifoo) in _refs(r)
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "ifoo")) in calls
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "other")) not in calls
    assert not ({"global", "Alias"} & _labels(r))


def test_root_anchored_receiver_is_unqualified(tmp_path):
    """`global::IFoo` on a root-namespace type carries no qualifier at all."""
    calls, r = _calls(tmp_path, {"S.cs": _TYPES + (
        "public static class E\n"
        "{\n"
        "    extension<T>(global::IFoo<T> spec)\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    _assert_receiver_recovered(calls, r)
    e = _find(r, "E", "_e")
    edge = next(x for x in r["edges"] if x["relation"] == "references" and x["source"] == e)
    assert "qualified" not in edge["metadata"] and "ref_qualifier" not in edge["metadata"]
    assert "global" not in _labels(r)


@pytest.mark.parametrize("header", [
    "extension<T>(Acme.IFoo<System.Collections.Generic.List<T>> spec) where T : class",
    "extension(Acme.IFoo<System.String> spec)",
])
def test_dotted_generic_argument_does_not_split_the_receiver_type(tmp_path, header):
    """A qualified name splits on its own dots, never on one inside a type
    argument: `Acme.IFoo<System.String>` is `IFoo` in `Acme`, not `String>`
    in `Acme.IFoo<System`."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "namespace Acme { public interface IFoo<T> { string? Next(); } }\n"
        "public static class E\n"
        "{\n"
        f"    {header}\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    edge = next(x for x in r["edges"] if x["relation"] == "references" and x["source"] == e)
    assert edge["metadata"]["ref_token"] == "IFoo"
    assert edge["metadata"]["ref_qualifier"] == "Acme"
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "ifoo")) in calls
    assert not [lbl for lbl in _labels(r) if "<" in lbl or ">" in lbl or "&" in lbl]


def test_dotted_generic_argument_does_not_split_a_field_or_base_type(tmp_path):
    """The same rule serves every C# type reference through the shared
    helpers — a field type and a base list here."""
    _, r = _calls(tmp_path, {"S.cs": (
        "namespace Acme { public interface IFoo<T> { } }\n"
        "public class Holder { private Acme.IFoo<System.String> f; }\n"
        "public class Impl : Acme.IFoo<System.String> { }\n"
    )})
    ifoo = _find(r, "IFoo", "ifoo")
    assert (_find(r, "Holder", "holder"), ifoo) in _refs(r)
    assert (_find(r, "Impl", "impl"), ifoo) in {
        (e["source"], e["target"]) for e in r["edges"] if e["relation"] == "implements"
    }
    assert not [lbl for lbl in _labels(r) if "<" in lbl or ">" in lbl or "&" in lbl]


def _generic_arg_refs(r, source_id):
    return {e["target"] for e in r["edges"]
            if e["relation"] == "references" and e["source"] == source_id
            and e.get("context") == "generic_arg"}


@pytest.mark.parametrize("type_expr", [
    "Acme.IFoo<Bar>",                                        # qualified
    "global::Acme.IFoo<Bar>",                                # alias-qualified, dotted
    "global::IFoo2<Bar>",                                    # alias-qualified, undotted
    "Acme.IFoo<System.Collections.Generic.List<Bar>>",       # nested, dotted argument
])
def test_qualified_generic_arguments_are_referenced(tmp_path, type_expr):
    """A qualified or alias-qualified generic type references its type
    arguments the way a bare `IFoo<Bar>` always has; `global::IFoo<Bar>` used
    to reach `Bar` only by accident, next to a phantom `global` node."""
    _, r = _calls(tmp_path, {"S.cs": (
        "namespace Acme { public interface IFoo<T> { } }\n"
        "public interface IFoo2<T> { }\n"
        "public class Bar { }\n"
        f"public class Holder {{ private {type_expr} f; }}\n"
    )})
    holder = _find(r, "Holder", "holder")
    assert _find(r, "Bar", "bar") in _generic_arg_refs(r, holder), type_expr
    assert "global" not in _labels(r)


def test_extension_receiver_generic_arguments_are_referenced(tmp_path):
    """The receiver of a constructor-shaped block goes through the same node
    path, so `Acme.IFoo<Bar>` references Bar as well as IFoo."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "namespace Acme { public interface IFoo<T> { string? Next(); } }\n"
        "public class Bar { }\n"
        "public static class E\n"
        "{\n"
        "    extension(Acme.IFoo<Bar> spec)\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    assert (e, _find(r, "IFoo", "ifoo")) in _refs(r)
    assert _find(r, "Bar", "bar") in _generic_arg_refs(r, e)
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "ifoo")) in calls


def test_nested_type_of_a_generic_outer_keeps_its_own_name(tmp_path):
    """`Outer<int>.Inner`: the type-argument list belongs to the qualifier and
    must not eat the split — `Inner`, qualified by `Outer`."""
    _, r = _calls(tmp_path, {"S.cs": (
        "public class Outer<T> { public class Inner { } }\n"
        "public class Holder { private Outer<int>.Inner f; }\n"
    )})
    holder = _find(r, "Holder", "holder")
    edge = next(x for x in r["edges"] if x["relation"] == "references" and x["source"] == holder)
    assert edge["metadata"]["ref_token"] == "Inner"
    assert edge["metadata"]["ref_qualifier"] == "Outer"


def test_alias_qualifier_is_not_a_type_on_the_shared_node_path(tmp_path):
    """The same `::` reading applies to every C# type reference, so the
    primary-constructor precedent stops fabricating a `global` type node."""
    calls, r = _calls(tmp_path, {"S.cs": _TYPES + (
        "public class Holder(global::IFoo dep)\n"
        "{\n"
        "    public string? Run() => dep.Next();\n"
        "}\n"
    )})
    holder = _find(r, "Holder", "holder")
    assert (holder, _find(r, "IFoo", "ifoo")) in _refs(r)
    assert (_find(r, ".Run()", "holder"), _find(r, ".Next()", "ifoo")) in calls
    assert "global" not in _labels(r)


def test_two_blocks_with_distinct_receivers_both_resolve(tmp_path):
    calls, r = _calls(tmp_path, {"S.cs": (
        "public interface IFoo { string? Next(); }\n"
        "public interface IBar { int Size(); }\n"
        "public static class E\n"
        "{\n"
        "    extension(IFoo foo)\n"
        "    {\n"
        "        public string? Url() => foo.Next();\n"
        "    }\n"
        "    extension(IBar bar)\n"
        "    {\n"
        "        public int Count() => bar.Size();\n"
        "    }\n"
        "}\n"
    )})
    assert (_find(r, ".Url()", "_e_url"), _find(r, ".Next()", "ifoo")) in calls
    assert (_find(r, ".Count()", "_e_count"), _find(r, ".Size()", "ibar")) in calls


def test_same_receiver_name_with_different_types_is_never_a_guess(tmp_path):
    """Two blocks binding `x` to different types: a call through `x` could go
    either way, so it goes nowhere — a missing edge, never a wrong one."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "public interface IFoo { string? Next(); }\n"
        "public interface IBar { string? Next(); }\n"
        "public static class E\n"
        "{\n"
        "    extension(IFoo x)\n"
        "    {\n"
        "        public string? A() => x.Next();\n"
        "    }\n"
        "    extension(IBar x)\n"
        "    {\n"
        "        public string? B() => x.Next();\n"
        "    }\n"
        "}\n"
    )})
    e = _find(r, "E", "_e")
    assert {(e, _find(r, "IFoo", "ifoo")), (e, _find(r, "IBar", "ibar"))} <= _refs(r)
    a, b = _find(r, ".A()", "_e_a"), _find(r, ".B()", "_e_b")
    assert not [t for s, t in calls if s in (a, b)]


def test_receiver_shadowed_by_a_field_of_another_type_is_dropped(tmp_path):
    """A static field named like the receiver but typed differently: the
    class-wide table cannot tell a call in the block from one outside it, so
    the name binds to nothing rather than to either type."""
    calls, r = _calls(tmp_path, {"S.cs": (
        "public interface IFoo { string? Next(); }\n"
        "public interface IBar { string? Next(); }\n"
        "public static class E\n"
        "{\n"
        "    private static IBar x = null!;\n"
        "    extension(IFoo x)\n"
        "    {\n"
        "        public string? A() => x.Next();\n"
        "    }\n"
        "    public static string? B() => x.Next();\n"
        "}\n"
    )})
    a, b = _find(r, ".A()", "_e_a"), _find(r, ".B()", "_e_b")
    assert not [t for s, t in calls if s in (a, b)]


def test_receiver_shadowed_by_a_field_of_the_same_type_still_binds(tmp_path):
    calls, r = _calls(tmp_path, {"S.cs": _plain_block().replace(
        "public static class E\n{\n",
        "public static class E\n{\n    private static IFoo spec = null!;\n",
    )})
    _assert_receiver_recovered(calls, r)


def test_member_declared_before_a_generic_block(tmp_path):
    """With a member ahead of it the ERROR lands inside the class body rather
    than beside it; the receiver is found either way and both members stay E's."""
    calls, r = _calls(tmp_path, {"S.cs": _TYPES + (
        "public static class E\n"
        "{\n"
        "    public static int H() => 3;\n"
        "    extension<T>(IFoo spec) where T : class\n"
        "    {\n"
        "        public string? Url() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    _assert_receiver_recovered(calls, r)
    assert (_find(r, "E", "_e"), _find(r, ".H()", "_e_h")) in _methods(r)


def test_namespaced_file_shape_from_the_issue(tmp_path):
    calls, r = _calls(tmp_path, {"S.cs": (
        "using System;\n"
        "namespace Acme.Persistence;\n"
        "public interface ICompositeCursorPagedSpec<T, TKey> { string? Next(); }\n"
        "public static class CompositeCursorPaginatedResponseInfoExtensions\n"
        "{\n"
        "    extension<T, TKey>(ICompositeCursorPagedSpec<T, TKey> spec) where T : class\n"
        "    {\n"
        "        public string? TryGetNextUrl() => spec.Next();\n"
        "    }\n"
        "}\n"
    )})
    cls = _find(r, "CompositeCursorPaginatedResponseInfoExtensions", "extensions")
    spec = _find(r, "ICompositeCursorPagedSpec", "icompositecursorpagedspec")
    helper = _find(r, ".TryGetNextUrl()", "trygetnexturl")
    assert (cls, helper) in _methods(r)
    assert (cls, spec) in _refs(r)
    assert (helper, _find(r, ".Next()", "icompositecursorpagedspec")) in calls
    assert not ({"T", "TKey"} & _labels(r))


def test_plain_block_member_signature_types_are_referenced(tmp_path):
    """A local_function_statement names its return type `type`, not `returns`;
    the parameter list is shared. Both must reach the member's references."""
    _, r = _calls(tmp_path, {"S.cs": (
        "public interface IFoo { }\n"
        "public interface IBar { }\n"
        "public interface IBaz { }\n"
        "public static class E\n"
        "{\n"
        "    extension(IFoo spec)\n"
        "    {\n"
        "        public IBar Make(IBaz baz) => null!;\n"
        "    }\n"
        "}\n"
    )})
    make = _find(r, ".Make()", "_e_make")
    assert {(make, _find(r, "IBar", "ibar")), (make, _find(r, "IBaz", "ibaz"))} <= _refs(r)


def test_property_inside_a_plain_block_does_not_break_the_methods(tmp_path):
    """0.23.5 turns a property in the constructor-shaped block into error soup;
    whatever it becomes, the methods around it are still extracted."""
    calls, r = _calls(tmp_path, {"S.cs": _plain_block(
        "        public int Count => 1;\n"
        "        public string? Url() => spec.Next();\n"
    )})
    _assert_receiver_recovered(calls, r)


def test_ordinary_local_functions_are_not_promoted(tmp_path):
    """Only a block member arrives with a class parent. A local function inside
    a real constructor, or in a non-static class that happens to be named
    `extension`, is reached by the default recurse and stays as it was."""
    _, r = _calls(tmp_path, {"S.cs": (
        "public class Holder\n"
        "{\n"
        "    public Holder() { int Local() => 1; }\n"
        "}\n"
        "public class extension\n"
        "{\n"
        "    public extension(int x) { int Inner() => x; }\n"
        "}\n"
    )})
    assert not ({".Local()", "Local()", ".Inner()", "Inner()"} & _labels(r))


def _grammar_has_extension_declaration() -> bool:
    import tree_sitter_c_sharp
    from tree_sitter import Language
    return bool(Language(tree_sitter_c_sharp.language())
                .id_for_node_kind("extension_declaration", True))


@pytest.mark.skipif(not _grammar_has_extension_declaration(),
                    reason="installed tree-sitter-c-sharp predates C# 14 extension_declaration")
def test_extension_declaration_grammar_shape(tmp_path):
    """tree-sitter-c-sharp > 0.23.5 parses a real `extension_declaration`. It is
    a container, not a scope: members stay E's, the receiver binds, and the
    block's own `<T>` is a type parameter, not a type."""
    for src in (_generic_block(), _plain_block()):
        calls, r = _calls(tmp_path, {"S.cs": src})
        _assert_receiver_recovered(calls, r)
        assert "parse_errors" not in r
        assert "T" not in _labels(r)
