from __future__ import annotations

from collections import Counter
from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _parse_csharp_root(source: bytes):
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp

    parser = Parser(Language(tree_sitter_c_sharp.language()))
    return parser.parse(source).root_node


def _walk_tree(node):
    yield node
    for child in node.children:
        yield from _walk_tree(child)


def _calls(result: dict, callee_label: str) -> list[dict]:
    """Every `calls`/`references` edge whose target node has `callee_label`.
    Method targets are labelled `.Name()`."""
    out = []
    for e in result["edges"]:
        if e.get("relation") not in ("calls", "references"):
            continue
        tgt = _node_by_id(result, e.get("target"))
        if tgt is not None and tgt.get("label") == callee_label:
            out.append(e)
    return out


def _method_owner(result: dict, method_nid: str) -> dict | None:
    for e in result["edges"]:
        if e.get("relation") == "method" and e.get("target") == method_nid:
            return _node_by_id(result, e.get("source"))
    return None


def _call_owner_labels(result: dict, callee_label: str) -> list[str | None]:
    return [
        (_method_owner(result, e["target"]) or {}).get("label")
        for e in _calls(result, callee_label)
    ]


def test_same_file_bare_name_no_misbind(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Other { public void Bar() {} }\n"
                 "class C { public void M() { var b = new B(); b.Bar(); } }\n"
                 "class B { public void Run() {} } }\n")
    result = extract([src], cache_root=tmp_path)
    # b.Bar() must not misbind to same-file Other.Bar; b IS a B, so a `references`-to-B
    # (method-not-found on the correct receiver type) is fine — only a `calls` misbind is wrong.
    _assert_no_calls_edge_from(result, "C", ".M()")


def test_local_var_resolves_not_same_named(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N {\n"
                 "class A { public void Run() {} }\n"
                 "class B { public void Run() {} }\n"
                 "class C { public void M() { var a = new A(); a.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    hits = _calls(result, ".Run()")
    assert len(hits) == 1, f"expected exactly one .Run() edge, got {hits}"
    owner = _method_owner(result, hits[0]["target"])
    assert owner is not None and owner.get("label") == "A", owner
    assert hits[0].get("confidence") == "INFERRED"
    assert hits[0].get("confidence_score") == 0.8
    assert "metadata" not in hits[0]


def test_scope_keyed_no_contamination(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class A { public void Run() {} }\n"
                 "class B { public void Run() {} }\n"
                 "class C { void M1(){ var svc = new A(); svc.Run(); }\n"
                 "void M2(){ var svc = new B(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    assert Counter(_call_owner_labels(result, ".Run()")) == Counter({"A": 1, "B": 1})


def test_redeclare_poison_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class A { public void Run() {} }\n"
                 "class B { public void Run() {} }\n"
                 "class C { void M(){ var svc = new A(); var svc = new B(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_block_local_leak_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class A { public void Run(){} } class B { public void Run(){} }\n"
                 "class C { A svc; void M(){ { B svc = new B(); } svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    # The inner block-local `B svc` is out of scope at svc.Run(); svc binds to the field
    # `A svc`, so field-receiver inference resolves A.Run. The block-local must NOT leak to B.Run.
    _edge_from_to_owner(result, "C", ".M()", "A", ".Run()")
    assert "B" not in _call_owner_labels(result, ".Run()")


def test_call_position_ignores_future_decl(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "class C { void M(){ svc.Run(); var svc = new Service(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_this_and_base_resolve(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Base { public virtual void OnInit(){} }\n"
                 "class C : Base { void Helper(){} void M(){ this.Helper(); base.OnInit(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    helper = _calls(result, ".Helper()")
    base = _calls(result, ".OnInit()")
    assert _call_owner_labels(result, ".Helper()") == ["C"]
    assert _call_owner_labels(result, ".OnInit()") == ["Base"]
    assert helper[0].get("confidence") == "EXTRACTED"
    assert base[0].get("confidence") == "EXTRACTED"


def test_unresolved_base_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class C : ExternalBase { void M(){ base.OnInit(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_partial_class_aggregates(tmp_path: Path):
    p1 = _write(tmp_path / "p1.cs", "namespace N { partial class P { public void A(){} } }\n")
    p2 = _write(tmp_path / "p2.cs",
                "namespace N { partial class P { public void B(){} }\n"
                "class C { void M(){ var p = new P(); p.A(); } } }\n")
    result = extract([p1, p2], cache_root=tmp_path)
    assert _call_owner_labels(result, ".A()") == ["P"]


def test_qualified_local_decl_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace A { class Bar { public void Run(){} } }\n"
                 "namespace B { class Bar { public void Run(){} } }\n"
                 "namespace Use { class C { void M(){ A.Bar f = new A.Bar(); f.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_generic_callee_normalizes(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class G { public void Foo<T>(){} public void Fooint(){} }\n"
                 "class C { void M(){ var g = new G(); g.Foo<int>(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    assert _call_owner_labels(result, ".Foo()") == ["G"]
    assert _calls(result, ".Fooint()") == []


def test_underscore_method_names_distinct(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class S { public void Foo_Bar(){} public void FooBar(){} }\n"
                 "class C { void M(){ var s = new S(); s.Foo_Bar(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    assert _call_owner_labels(result, ".Foo_Bar()") == ["S"]
    assert _calls(result, ".FooBar()") == []


def test_method_return_var_implicit_rhs_resolves(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "class C { Service Get(){ return null; } void M(){ var svc = Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner(result, "C", ".M()", "Service", ".Run()")
    assert edge.get("confidence") == "INFERRED"
    assert edge.get("confidence_score") == 0.8
    assert "metadata" not in edge


def _method_id(result: dict, owner_label: str, method_label: str) -> str:
    for e in result["edges"]:
        if e.get("relation") != "method":
            continue
        owner = _node_by_id(result, e.get("source"))
        target = _node_by_id(result, e.get("target"))
        if owner and target and owner.get("label") == owner_label and target.get("label") == method_label:
            return e["target"]
    raise AssertionError(f"missing method {owner_label}.{method_label}")


def _calls_from_method(result: dict, owner_label: str, method_label: str) -> list[dict]:
    caller = _method_id(result, owner_label, method_label)
    return [
        e for e in result["edges"]
        if e.get("source") == caller and e.get("relation") in ("calls", "references")
    ]


def _assert_no_call_from(result: dict, owner_label: str, method_label: str) -> None:
    edges = _calls_from_method(result, owner_label, method_label)
    assert edges == [], f"expected no member-call edge from {owner_label}.{method_label}, got {edges}"


def _assert_no_calls_edge_from(result: dict, owner_label: str, method_label: str) -> None:
    # A member-call MISBIND is a `calls` edge. A `references` edge to the receiver's own
    # type (the method-not-found fallback) or to a parameter type is correct, not a
    # misbind, so this asserts only that no wrong `calls` resolution was emitted.
    caller = _method_id(result, owner_label, method_label)
    calls = [e for e in result["edges"] if e.get("source") == caller and e.get("relation") == "calls"]
    assert calls == [], f"expected no calls edge from {owner_label}.{method_label}, got {calls}"


def _edge_from_to_owner(result: dict, caller_owner: str, caller_method: str, target_owner: str, target_method: str) -> dict:
    target = _method_id(result, target_owner, target_method)
    for e in _calls_from_method(result, caller_owner, caller_method):
        if e.get("target") == target:
            return e
    raise AssertionError(f"missing call from {caller_owner}.{caller_method} to {target_owner}.{target_method}")


def test_static_receiver_resolves_with_metadata(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class C { void M(){ Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner(result, "C", ".M()", "Logger", ".Warn()")
    assert edge.get("confidence") == "EXTRACTED"
    assert edge.get("metadata", {}).get("csharp_static") is True


def test_static_value_shadow_local_param_field_property_event_skip(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class Actual { public void Warn(){} }\n"
                 "class C { object Logger; event System.Action Ev; int Prop { get; }\n"
                 "void Local(){ Actual Logger = new Actual(); Logger.Warn(); }\n"
                 "void Param(Actual Logger){ Logger.Warn(); }\n"
                 "void Field(){ Logger.Warn(); }\n"
                 "void Property(){ Prop.ToString(); }\n"
                 "void Event(){ Ev(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".Field()")
    _assert_no_call_from(result, "C", ".Property()")
    _assert_no_call_from(result, "C", ".Event()")
    # Local() and Param() resolve Logger:Actual -> Actual.Warn. Field() has an
    # object-typed member named Logger, which shadows the static Logger type but
    # has no accepted bare declared receiver type.
    assert _call_owner_labels(result, ".Warn()").count("Actual") == 2
    assert "Logger" not in _call_owner_labels(result, ".Warn()")


def test_static_namespace_method_typeparam_nested_using_static_alias_shadows_skip(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { namespace Logger { class X{} }\n"
                 "class Tools { public static void Logger(){} }\n"
                 "class Target { public static void Warn(){} }\n"
                 "using Logger = Target;\n"
                 "using static Tools;\n"
                 "class C<Logger> { class Logger { public static void Warn(){} }\n"
                 "void M(){ void Logger(){} Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_inherited_member_shadows_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class Base { public int Logger; public void Other(){} public class Nested{} }\n"
                 "class Derived : Base { void M(){ Logger.Warn(); Other.Warn(); Nested.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "Derived", ".M()")


def test_inherited_nested_type_shadow_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class Base { public class Logger { public static void Warn(){} } }\n"
                 "class Derived : Base { void M(){ Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "Derived", ".M()")


def test_dotted_receiver_resolves_namespace_qualified_and_skips_nested_type_qualifier(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace Lib { class Logger { public static void Warn(){} } }\n"
                 "namespace Use { using Lib; class Outer { public class Inner { public static void Warn(){} }\n"
                 "void Good(){ Lib.Logger.Warn(); }\n"
                 "void Bad(){ Outer.Inner.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "Outer", ".Good()", "Logger", ".Warn()")
    _assert_no_call_from(result, "Outer", ".Bad()")


def test_dotted_receiver_resolves_namespace_alias(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace Lib { class Logger { public static void Warn(){} } }\n"
                 "namespace Use { using L = Lib; class C { void M(){ L.Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Logger", ".Warn()")


def test_dotted_receiver_type_alias_takes_precedence_over_namespace_and_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace B { class Logger { public static void Warn(){} } }\n"
                 "namespace Use { using B = X.Target; class C { void M(){ B.Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_query_range_variable_shadows_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class C { object[] xs; void M(){ var q = from Logger in xs select Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_query_let_join_and_into_variables_shadows_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class C { object[] xs; object[] ys;\n"
                 "void M(){ var q = from x in xs let Logger = x select Logger.Warn(); }\n"
                 "void J(){ var q = from x in xs join Logger in ys on x equals Logger into Logger select Logger.Warn(); }\n"
                 "void I(){ var q = from x in xs select x into Logger select Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")
    _assert_no_call_from(result, "C", ".J()")
    _assert_no_call_from(result, "C", ".I()")


def test_nested_type_caller_inherited_member_shadows_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class Base { public int Logger; }\n"
                 "class Outer { class Inner : Base { void M(){ Logger.Warn(); } } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "Inner", ".M()")


def test_nested_type_base_id_collision_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "class Base { }\n"
                 "class Outer { class Base { protected int Logger; }\n"
                 "class Inner : Base { void M(){ Logger.Warn(); } } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "Inner", ".M()")


def test_global_using_static_shadows_across_files(tmp_path: Path):
    g = _write(tmp_path / "global.cs",
               "global using static N.Tools;\n"
               "namespace N { class Tools { public static void Logger(){} } }\n")
    u = _write(tmp_path / "user.cs",
               "namespace N { class Logger { public static void Warn(){} }\n"
               "class C { void M(){ Logger.Warn(); } } }\n")
    result = extract([g, u], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_global_namespace_using_resolves_static_receiver_across_files(tmp_path: Path):
    g = _write(tmp_path / "global.cs",
               "global using Lib;\n"
               "namespace Lib { class Logger { public static void Warn(){} } }\n")
    u = _write(tmp_path / "user.cs",
               "namespace Use { class C { void M(){ Logger.Warn(); } } }\n")
    result = extract([g, u], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Logger", ".Warn()")


def test_conditional_access_invocation_helper_and_resolution(tmp_path: Path):
    from graphify.extractors import csharp_extract

    helper = getattr(csharp_extract, "csharp_invocation_callee", None)
    assert callable(helper), "expected the C# invocation parser to be extracted"

    source = (
        b"namespace N { class Service { public void Run(){} } "
        b"class C { void M(Service svc){ svc?.Run(); } } }"
    )
    invocation = next(node for node in _walk_tree(_parse_csharp_root(source)) if node.type == "invocation_expression")
    assert helper(invocation, source) == ("Run", True, "svc")

    src = _write(tmp_path / "s.cs", source.decode("utf-8"))
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Service", ".Run()")


def test_csharp_type_table_records_only_identifier_bare_types() -> None:
    from graphify.extract import _build_csharp_type_table

    source = b"class Bar{} class C { void M(){ Bar f; A.Bar q; Bar[] arr; } }"
    root = _parse_csharp_root(source)
    table = _build_csharp_type_table(root, source)
    entries = {
        name: type_name
        for scope_entries in table.values()
        for name, type_name, _ in scope_entries
        if name in {"f", "q", "arr"}
    }
    assert entries == {"f": "Bar", "q": None, "arr": None}


def test_csharp_type_table_matches_shadow_value_binders_minus_type_scoped_binders() -> None:
    from graphify.extract import (
        _build_csharp_shadow_names,
        _build_csharp_type_table,
        _csharp_designator_names,
        _csharp_names_from_variable_declaration,
    )

    source = b"""
namespace N {
class Service { public void Run() {} }
record R(Service recordParam);
class Primary(Service classPrimary) {}
struct S(Service structPrimary) {}
class C {
  Service fieldName;
  event System.Action eventFieldName;
  Service PropertyName { get; }
  event System.Action EventName { add { } remove { } }
  enum E { EnumValue }
  Service[] xs;
  object o;
  object pair;
  void M(Service paramName) {
    Service localName = new Service();
    var objectCreated = new Service();
    var untypedLocal = fieldName;
    foreach (Service foreachName in xs) { }
    try { } catch (Service catchName) { }
    if (o is Service patternName) { }
    if (o is var varPatternName) { }
    var (deconA, deconB) = pair;
    Out(out Service outName);
    Out(out var outVarName);
    var q = from queryFrom in xs
            let queryLet = queryFrom
            join queryJoin in xs on queryFrom equals queryJoin into queryInto
            select queryInto into queryContinuation
            select queryContinuation;
    System.Action<Service> anon = delegate(Service anonymousParam) { anonymousParam.ToString(); };
    xs.Select(implicitLambda => implicitLambda.ToString());
    xs.Select((lambdaA, lambdaB) => lambdaA.ToString());
    xs.Select((Service typedLambdaParam) => typedLambdaParam.ToString());
    void LocalFn(Service localFunctionParam) { localFunctionParam.ToString(); }
  }
  void Out(out Service value) { value = null; }
  Service this[int indexerParam] { get { return fieldName; } }
}
}
"""
    root = _parse_csharp_root(source)

    shadow_values = {
        name
        for buckets in _build_csharp_shadow_names(root, source).values()
        for name in buckets.get("values", [])
    }
    type_table_values = {
        name
        for entries in _build_csharp_type_table(root, source).values()
        for name, _type_name, _decl_start in entries
    }

    def text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8")

    def parameter_owner(node):
        cur = node.parent
        while cur is not None and cur.type in {"bracketed_parameter_list", "parameter_list"}:
            cur = cur.parent
        return cur

    type_scoped_values: set[str] = set()

    def walk(node) -> None:
        if node.type == "parameter":
            owner = parameter_owner(node)
            if owner is not None and owner.type in {
                "class_declaration",
                "enum_declaration",
                "interface_declaration",
                "record_declaration",
                "struct_declaration",
            }:
                type_scoped_values.update(_csharp_designator_names(node, source))
        elif node.type == "variable_declaration":
            if node.parent is not None and node.parent.type in {"field_declaration", "event_field_declaration"}:
                type_scoped_values.update(_csharp_names_from_variable_declaration(node, source))
        elif node.type in {"property_declaration", "event_declaration", "enum_member_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                type_scoped_values.add(text(name_node))

        for child in node.children:
            walk(child)

    walk(root)

    assert type_table_values == shadow_values - type_scoped_values


def test_implicit_enclosing_and_base_methods_resolve(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Base { public void BaseRun(){} }\n"
                 "class C : Base { public void Run(){} void M(){ Run(); BaseRun(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "C", ".Run()")
    _edge_from_to_owner(result, "C", ".M()", "Base", ".BaseRun()")


def test_implicit_shadows_skip_delegate_param_local_static_local_using_static_and_field_event(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Tools { public static void FromStatic(){} }\n"
                 "using static Tools;\n"
                 "class C { System.Action Run; event System.Action Ev; public void RunMethod(){} public void FromStatic(){}\n"
                 "void LocalDelegate(){ System.Action RunMethod = null; RunMethod(); }\n"
                 "void ParamDelegate(System.Action RunMethod){ RunMethod(); }\n"
                 "void FieldDelegate(){ Run(); }\n"
                 "void EventDelegate(){ Ev(); }\n"
                 "void StaticLocal(){ static void RunMethod(){} RunMethod(); }\n"
                 "void LocalTypeParam(){ void Local<RunMethod>(){ RunMethod(); } Local<int>(); }\n"
                 "void UsingStatic(){ FromStatic(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    # Each bare call is shadowed and must not resolve to a method (`calls`). ParamDelegate's
    # `System.Action RunMethod` parameter yields a param-TYPE `references` edge (not a member
    # call), so assert no wrong `calls` resolution rather than zero edges.
    for method in (".LocalDelegate()", ".ParamDelegate()", ".FieldDelegate()", ".EventDelegate()", ".StaticLocal()", ".LocalTypeParam()", ".UsingStatic()"):
        _assert_no_calls_edge_from(result, "C", method)


def test_partial_class_base_aggregation_for_implicit_base_method(tmp_path: Path):
    p1 = _write(tmp_path / "p1.cs", "namespace N { class Base { public void BaseRun(){} } partial class P : Base { } }\n")
    p2 = _write(tmp_path / "p2.cs", "namespace N { partial class P { void M(){ BaseRun(); } } }\n")
    result = extract([p1, p2], cache_root=tmp_path)
    _edge_from_to_owner(result, "P", ".M()", "Base", ".BaseRun()")


def test_implicit_wrong_bare_name_regression_skips_unrelated_same_file_method(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class B { public void Run(){} }\n"
                 "class C { void M(){ Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_implicit_generic_wrong_bare_name_regression_skips_unrelated_same_file_method(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class B { public void Run(){} }\n"
                 "class C { void M(){ Run<int>(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_from(result, "C", ".M()")


def test_typed_foreach_catch_pattern_locals_resolve(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Actual { public void Run() {} }\n"
                 "class C { Actual[] xs; object o;\n"
                 "void Foreach(){ foreach (Actual item in xs) { item.Run(); } }\n"
                 "void Catch(){ try { } catch (Actual caught) { caught.Run(); } }\n"
                 "void Pattern(){ if (o is Actual pat) { pat.Run(); } } } }\n")
    result = extract([src], cache_root=tmp_path)
    assert Counter(_call_owner_labels(result, ".Run()")) == Counter({"Actual": 3})


def test_declared_parameter_receiver_resolves(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run() {} }\n"
                 "class C { void M(Service svc){ svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner(result, "C", ".M()", "Service", ".Run()")
    assert edge.get("confidence") == "INFERRED"
    assert edge.get("confidence_score") == 0.8
    assert "metadata" not in edge


def test_field_property_and_this_member_receivers_resolve(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run() {} }\n"
                 "class C { Service field; Service Prop { get; }\n"
                 "void BareField(){ field.Run(); }\n"
                 "void ThisField(){ this.field.Run(); }\n"
                 "void BareProp(){ Prop.Run(); }\n"
                 "void ThisProp(){ this.Prop.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    for method in (".BareField()", ".ThisField()", ".BareProp()", ".ThisProp()"):
        edge = _edge_from_to_owner(result, "C", method, "Service", ".Run()")
        assert edge.get("confidence") == "INFERRED"
        assert edge.get("confidence_score") == 0.8


def test_local_param_shadow_field_and_untyped_local_poisons(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class FieldSvc { public void Run() {} }\n"
                 "class LocalSvc { public void Run() {} }\n"
                 "class ParamSvc { public void Run() {} }\n"
                 "class C { FieldSvc svc; FieldSvc field;\n"
                 "void Local(){ LocalSvc svc = new LocalSvc(); svc.Run(); }\n"
                 "void Param(ParamSvc svc){ svc.Run(); }\n"
                 "void Untyped(){ var svc = field; svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".Local()", "LocalSvc", ".Run()")
    _edge_from_to_owner(result, "C", ".Param()", "ParamSvc", ".Run()")
    _assert_no_calls_edge_from(result, "C", ".Untyped()")


def test_query_lambda_and_anonymous_method_binders_shadow_field(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class FieldSvc { public void Run() {} }\n"
                 "class OtherSvc { public void Run() {} }\n"
                 "class C { FieldSvc svc; object[] xs;\n"
                 "void Query(){ var q = from svc in xs select svc.Run(); }\n"
                 "void Lambda(){ xs.Select(svc => svc.Run()); }\n"
                 "void Anonymous(){ System.Action<OtherSvc> d = delegate(OtherSvc svc){ svc.Run(); }; } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".Query()")
    _assert_no_calls_edge_from(result, "C", ".Lambda()")
    _edge_from_to_owner(result, "C", ".Anonymous()", "OtherSvc", ".Run()")
    assert "FieldSvc" not in _call_owner_labels(result, ".Run()")


def test_type_parameter_declared_receiver_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class T { public void Run() {} }\n"
                 "class C<T> { void Param(T svc){ svc.Run(); }\n"
                 "void Local(){ T svc; svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".Param()")
    _assert_no_calls_edge_from(result, "C", ".Local()")


def test_visible_nested_declared_receiver_skips_top_level_same_name(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public void Run(){} }\n"
                 "class Outer { class Logger { public void Run(){} }\n"
                 "void M(Logger logger){ logger.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "Outer", ".M()")


def test_instance_receiver_walks_base_chain_for_inherited_method(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Base { public void Run(){} }\n"
                 "class Derived : Base { }\n"
                 "class C { void M(Derived d){ d.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Base", ".Run()")


def test_static_and_dotted_type_receivers_do_not_walk_instance_base_chain(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "using Lib;\n"
                 "namespace Lib { class Base { public void Run(){} } class Derived : Base { } }\n"
                 "namespace Use { class C { void Bare(){ Derived.Run(); }\n"
                 "void Dotted(){ Lib.Derived.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".Bare()")
    _assert_no_calls_edge_from(result, "C", ".Dotted()")


def test_direct_first_skips_unknown_base_without_direct_and_keeps_direct_with_external_base(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Mid : ExternalBase { public void Run(){} }\n"
                 "class Derived : Mid { }\n"
                 "class Direct : ExternalBase { public void Run(){} }\n"
                 "class C { void Shadowed(Derived svc){ svc.Run(); }\n"
                 "void DirectHit(Direct svc){ svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".Shadowed()")
    _edge_from_to_owner(result, "C", ".DirectHit()", "Direct", ".Run()")


def test_positional_record_parameter_receiver_resolves_as_member(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "record R(Service svc) { void Bare(){ svc.Run(); }\n"
                 "void This(){ this.svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "R", ".Bare()", "Service", ".Run()")
    _edge_from_to_owner(result, "R", ".This()", "Service", ".Run()")


def test_record_primary_constructor_base_type_emits_inherits_edge(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger {} record Base(Logger Logger);\n"
                 "record Derived(Logger Other) : Base(Other) { } }\n")
    result = extract([src], cache_root=tmp_path)
    inherits = {
        ((_node_by_id(result, edge.get("source")) or {}).get("label"),
         (_node_by_id(result, edge.get("target")) or {}).get("label"))
        for edge in result["edges"]
        if edge.get("relation") == "inherits"
    }
    assert ("Derived", "Base") in inherits


def test_inherited_record_positional_param_shadows_static_receiver(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Logger { public static void Warn(){} }\n"
                 "record Base(Logger Logger);\n"
                 "record Derived(Logger Other) : Base(Other) { void M(){ Logger.Warn(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "Derived", ".M()")


def test_class_and_struct_primary_constructor_params_do_not_resolve_as_members(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "class C(Service svc) { void M(){ svc.Run(); } }\n"
                 "struct S(Service svc) { void M(){ svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".M()")
    _assert_no_calls_edge_from(result, "S", ".M()")


def test_partial_sibling_member_type_alias_does_not_resolve_at_other_part_call_site(tmp_path: Path):
    a = _write(tmp_path / "a.cs",
               "using S = N.Good;\n"
               "namespace N { partial class C { S svc; }\n"
               "class Good { public void Run(){} } }\n")
    b = _write(tmp_path / "b.cs",
               "using S = N.Bad;\n"
               "namespace N { partial class C { void M(){ svc.Run(); } }\n"
               "class Bad { public void Run(){} } }\n")
    result = extract([a, b], cache_root=tmp_path)
    _assert_no_calls_edge_from(result, "C", ".M()")
    assert "Bad" not in _call_owner_labels(result, ".Run()")
    assert "Good" not in _call_owner_labels(result, ".Run()")


def _method_id_with_owner_namespace(result: dict, owner_label: str, owner_namespace: str, method_label: str) -> str:
    for e in result["edges"]:
        if e.get("relation") != "method":
            continue
        owner = _node_by_id(result, e.get("source"))
        target = _node_by_id(result, e.get("target"))
        metadata = (owner or {}).get("metadata") or {}
        if (
            owner
            and target
            and owner.get("label") == owner_label
            and metadata.get("namespace", "") == owner_namespace
            and target.get("label") == method_label
        ):
            return e["target"]
    raise AssertionError(f"missing method {owner_namespace}.{owner_label}.{method_label}")


def _edge_from_to_owner_namespace(
    result: dict,
    caller_owner: str,
    caller_method: str,
    target_owner: str,
    target_namespace: str,
    target_method: str,
) -> dict:
    target = _method_id_with_owner_namespace(result, target_owner, target_namespace, target_method)
    for e in _calls_from_method(result, caller_owner, caller_method):
        if e.get("target") == target:
            return e
    raise AssertionError(
        f"missing call from {caller_owner}.{caller_method} to {target_namespace}.{target_owner}.{target_method}"
    )


def _assert_no_call_label_from(result: dict, owner_label: str, method_label: str, callee_label: str) -> None:
    labels = [
        (_node_by_id(result, edge.get("target")) or {}).get("label")
        for edge in _calls_from_method(result, owner_label, method_label)
        if edge.get("relation") == "calls"
    ]
    assert callee_label not in labels, f"unexpected {callee_label} call from {owner_label}.{method_label}: {labels}"


def _assert_no_call_to_owner(
    result: dict,
    caller_owner: str,
    caller_method: str,
    target_owner: str,
    target_method: str,
) -> None:
    target = _method_id(result, target_owner, target_method)
    unexpected = [
        edge
        for edge in _calls_from_method(result, caller_owner, caller_method)
        if edge.get("relation") == "calls" and edge.get("target") == target
    ]
    assert unexpected == [], (
        f"unexpected call from {caller_owner}.{caller_method} to {target_owner}.{target_method}: {unexpected}"
    )


def test_method_return_var_this_rhs_resolves(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class ThisSvc { public void Run(){} }\n"
                 "class C { ThisSvc Get(){ return null; } void M(){ var svc = this.Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner(result, "C", ".M()", "ThisSvc", ".Run()")
    assert edge.get("confidence") == "INFERRED"
    assert edge.get("confidence_score") == 0.8


def test_method_return_var_static_and_dotted_rhs_resolve(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace StaticNs { class StaticSvc { public void Run(){} }\n"
                 "class Factory { public static StaticSvc Get(){ return null; } } }\n"
                 "namespace DottedNs { class DottedSvc { public void Run(){} }\n"
                 "class Factory { public static DottedSvc Get(){ return null; } } }\n"
                 "namespace Use { using StaticNs; class C { void M(){ var a = Factory.Get(); a.Run();\n"
                 "var b = DottedNs.Factory.Get(); b.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    assert _edge_from_to_owner(result, "C", ".M()", "StaticSvc", ".Run()").get("confidence") == "INFERRED"
    assert _edge_from_to_owner(result, "C", ".M()", "DottedSvc", ".Run()").get("confidence") == "INFERRED"


def test_method_return_var_resolves_return_type_in_callee_context(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace Lib { class Service { public void Run(){} }\n"
                 "class Factory { public static Service Get(){ return null; } } }\n"
                 "namespace App { using Lib; class Service { public void Run(){} }\n"
                 "class C { void M(){ var svc = Lib.Factory.Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner_namespace(result, "C", ".M()", "Service", "Lib", ".Run()")
    assert edge.get("confidence") == "INFERRED"
    assert "App" not in [
        ((_method_owner(result, e["target"]) or {}).get("metadata") or {}).get("namespace")
        for e in _calls_from_method(result, "C", ".M()")
        if (_node_by_id(result, e.get("target")) or {}).get("label") == ".Run()"
    ]


def test_method_return_var_overloaded_method_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} } class Other { public void Run(){} }\n"
                 "class C { Service Get(){ return null; } Other Get(int i){ return null; }\n"
                 "void M(){ var svc = Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_label_from(result, "C", ".M()", ".Run()")


def test_method_return_var_same_file_partial_overload_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} } class Other { public void Run(){} }\n"
                 "partial class C { Service Get(){ return null; } }\n"
                 "partial class C { Other Get(int i){ return null; } }\n"
                 "partial class C { void M(){ var svc = Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_label_from(result, "C", ".M()", ".Run()")


def test_method_return_var_non_bare_returns_skip(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "using System.Collections.Generic;\n"
                 "namespace N { class Service { public void Run(){} } class Box<T> {}\n"
                 "class C<T> {\n"
                 "Service[] ArrayGet(){ return null; } void ArrayCase(){ var svc = ArrayGet(); svc.Run(); }\n"
                 "Service? NullableGet(){ return null; } void NullableCase(){ var svc = NullableGet(); svc.Run(); }\n"
                 "N.Service QualifiedGet(){ return null; } void QualifiedCase(){ var svc = QualifiedGet(); svc.Run(); }\n"
                 "Box<Service> GenericGet(){ return null; } void GenericCase(){ var svc = GenericGet(); svc.Run(); }\n"
                 "void VoidGet(){ } void VoidCase(){ var svc = VoidGet(); svc.Run(); }\n"
                 "T TypeParamGet(){ return default; } void TypeParamCase(){ var svc = TypeParamGet(); svc.Run(); }\n"
                 "ref Service RefGet(){ throw null; } void RefCase(){ var svc = RefGet(); svc.Run(); }\n"
                 "(Service a, Service b) TupleGet(){ throw null; } void TupleCase(){ var svc = TupleGet(); svc.Run(); }\n"
                 "} }\n")
    result = extract([src], cache_root=tmp_path)
    for method in (
        ".ArrayCase()", ".NullableCase()", ".QualifiedCase()", ".GenericCase()",
        ".VoidCase()", ".TypeParamCase()", ".RefCase()", ".TupleCase()",
    ):
        _assert_no_call_label_from(result, "C", method, ".Run()")


def test_method_return_var_reassignment_poison_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} } class Other { public void Run(){} }\n"
                 "class C { Service Get(){ return null; } Other Other(){ return null; }\n"
                 "void M(){ var svc = Get(); svc = Other(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_label_from(result, "C", ".M()", ".Run()")


def test_method_return_var_inner_declared_local_shadows_outer_inferred(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} } class Other { public void Run(){} }\n"
                 "class C { Service Get(){ return null; }\n"
                 "void M(){ var svc = Get(); { Other svc; svc.Run(); } } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Other", ".Run()")
    _assert_no_call_to_owner(result, "C", ".M()", "Service", ".Run()")


def test_method_return_var_transitive_inference_skips_second_var(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class NextSvc { public void Run(){} }\n"
                 "class Service { public NextSvc Next(){ return null; } public void Run(){} }\n"
                 "class C { Service Get(){ return null; }\n"
                 "void M(){ var a = Get(); var b = a.Next(); a.Run(); b.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _edge_from_to_owner(result, "C", ".M()", "Service", ".Run()")
    run_owners = [
        (_method_owner(result, e["target"]) or {}).get("label")
        for e in _calls_from_method(result, "C", ".M()")
        if (_node_by_id(result, e.get("target")) or {}).get("label") == ".Run()"
    ]
    assert Counter(run_owners) == Counter({"Service": 1})


def test_method_return_var_lowercase_instance_rhs_skips(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "class Factory { public Service Get(){ return null; } }\n"
                 "class C { void M(){ var obj = new Factory(); var svc = obj.Get(); svc.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_label_from(result, "C", ".M()", ".Run()")


def test_method_return_var_property_and_field_rhs_skip(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Service { public void Run(){} }\n"
                 "class C { Service field; Service Prop { get; }\n"
                 "void M(){ var a = field; a.Run(); var b = Prop; b.Run(); } } }\n")
    result = extract([src], cache_root=tmp_path)
    _assert_no_call_label_from(result, "C", ".M()", ".Run()")


def test_method_chained_off_new_expression_resolves(tmp_path: Path):
    src = _write(tmp_path / "s.cs",
                 "namespace N { class Merger {\n"
                 "public Merger(int x) {}\n"
                 "public int Combine(int a, bool b) { return a; } }\n"
                 "class Svc { public int Run(int ctx) {\n"
                 "return new Merger(ctx).Combine(ctx, true); } } }\n")
    result = extract([src], cache_root=tmp_path)
    edge = _edge_from_to_owner(result, "Svc", ".Run()", "Merger", ".Combine()")
    assert edge.get("confidence") == "EXTRACTED"
    assert "metadata" not in edge
