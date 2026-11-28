"""Inherited receiver members resolve only through unambiguous static base paths."""
import importlib.util
import json

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_cpp") is None,
    reason="tree_sitter_cpp not installed",
)


def _extract(tmp_path, source, header="", extra=None):
    files = {"use.cpp": source}
    if header:
        files["types.hpp"] = header
        files["use.cpp"] = '#include "types.hpp"\n' + source
    files.update(extra or {})
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths, extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)


def _calls(result, caller="Run()"):
    nodes = {n["id"]: n for n in result["nodes"]}
    owners = {e["target"]: nodes[e["source"]].get("_cpp_qualified")
              for e in result["edges"] if e["relation"] in {"method", "defines"}}
    return {(owners.get(e["target"]), nodes[e["target"]]["label"], e["confidence"])
            for e in result["edges"] if e["relation"] == "calls"
            and nodes[e["source"]]["label"] == caller}


@pytest.mark.parametrize("expression", ["x.Work()", "x.actions.Work()"])
def test_inherited_methods_and_fields(tmp_path, expression):
    _, result = _extract(tmp_path, f"void Run(app::Derived& x) {{ {expression}; }}", """
namespace app {
struct Actions { void Work(); };
struct Base { Actions actions; void Work(); };
struct Mid : Base {};
struct Derived : Mid {};
}
""")
    owner = "app::Actions" if "actions" in expression else "app::Base"
    assert _calls(result) == {(owner, ".Work()", "INFERRED")}


@pytest.mark.parametrize("expression", ["this->actions.Work()", "actions.Work()", "this->Work()"])
def test_inherited_this_and_implicit_fields(tmp_path, expression):
    _, result = _extract(tmp_path, f"""
struct Actions {{ void Work(); }};
struct Base {{ Actions actions; void Work(); }};
struct Derived : Base {{ void Run() {{ {expression}; }} }};
""")
    owner = "Actions" if "actions" in expression else "Base"
    confidence = "INFERRED" if "actions" in expression else "EXTRACTED"
    assert _calls(result, ".Run()") == {(owner, ".Work()", confidence)}


def test_nearest_member_hides_a_base_member(tmp_path):
    _, result = _extract(tmp_path, """
struct First { void Work(); }; struct Second { void Work(); };
struct Base { First actions; void Work(); };
struct Derived : Base { Second actions; void Work(); };
void Run(Derived& x) { x.actions.Work(); x.Work(); }
""")
    assert _calls(result) == {("Second", ".Work()", "INFERRED"),
                              ("Derived", ".Work()", "INFERRED")}


@pytest.mark.parametrize("hidden", ["int Work;", "using Work = int;", "struct Work {};",
                                     "enum { Work };", "union Work { int x; };", "union { int Work; };",
                                     "void Work(int); void Work(double);"])
def test_a_derived_declaration_blocks_a_base_method(tmp_path, hidden):
    _, result = _extract(tmp_path, f"""
struct Base {{ void Work(); }};
struct Derived : Base {{ {hidden} }};
void Run(Derived& x) {{ x.Work(); }}
""")
    assert not any(owner == "Base" for owner, _, _ in _calls(result))


def test_a_hidden_this_member_is_not_rebound_to_a_base_method(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { void Work(); };
struct Derived : Base { using Work = int; void Run() { this->Work(); } };
""")
    assert _calls(result, ".Run()") == set()


def test_unknown_derived_field_hides_the_base_field(tmp_path):
    _, result = _extract(tmp_path, """
struct Actions { void Work(); }; struct Base { Actions actions; };
struct Derived : Base { Missing actions; };
void Run(Derived& x) { x.actions.Work(); }
""")
    assert _calls(result) == set()


@pytest.mark.parametrize("bases", ["Left, Right", "Left, Missing", "Missing, Left"])
def test_multiple_or_unknown_base_candidates_are_not_guessed(tmp_path, bases):
    _, result = _extract(tmp_path, f"""
struct Left {{ void Work(); }}; struct Right {{ void Work(); }};
struct Derived : {bases} {{}};
void Run(Derived& x) {{ x.Work(); }}
""")
    assert _calls(result) == set()


def test_multiple_inheritance_with_one_member_candidate_is_supported(tmp_path):
    _, result = _extract(tmp_path, """
struct Left { void Work(); }; struct Right { void Other(); };
struct Derived : Left, Right {};
void Run(Derived& x) { x.Work(); }
""")
    assert _calls(result) == {("Left", ".Work()", "INFERRED")}


def test_nonvirtual_diamond_is_ambiguous_even_with_one_method_node(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { void Work(); }; struct Left : Base {}; struct Right : Base {};
struct Derived : Left, Right {};
void Run(Derived& x) { x.Work(); }
""")
    assert _calls(result) == set()


@pytest.mark.parametrize("base", ["Missing", "Unknown<Actions>", "virtual Actions"])
def test_unsupported_bases_are_not_guessed(tmp_path, base):
    _, result = _extract(tmp_path, f"""
struct Actions {{ void Work(); }}; struct Derived : {base} {{}};
void Run(Derived& x) {{ x.Work(); }}
""")
    assert _calls(result) == set()


def test_inheritance_cycle_stops(tmp_path):
    _, result = _extract(tmp_path, """
struct First; struct Second : First {}; struct First : Second {};
void Run(First& x) { x.Work(); }
""")
    assert _calls(result) == set()


def test_inherited_overload_family_is_not_a_unique_target(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { void Work(int); void Work(double); }; struct Derived : Base {};
void Run(Derived& x) { x.Work(1); }
""")
    assert _calls(result) == set()


def test_virtual_call_stays_on_its_declared_static_base(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { virtual void Work(); }; struct Derived : Base { void Work() override; };
void Run(Base& x) { x.Work(); }
""")
    assert _calls(result) == {("Base", ".Work()", "INFERRED")}


def test_aliased_base_preserves_namespace_and_case(tmp_path):
    _, result = _extract(tmp_path, "void Run(app::Derived& x) { x.Work(); x.work(); }",
                         "namespace app { struct Base { void Work(); }; using Parent = Base; struct Derived : Parent {}; }",
                         {"other.hpp": "namespace other { struct Base { void Work(); }; }"})
    assert _calls(result) == {("app::Base", ".Work()", "INFERRED")}


def test_a_scope_qualified_inherited_static_call(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { static void Work(); }; struct Derived : Base {};
void Run() { Derived::Work(); }
""")
    assert _calls(result) == {("Base", ".Work()", "EXTRACTED")}


def test_a_scope_qualified_call_preserves_receiver_case(tmp_path):
    _, result = _extract(tmp_path, """
struct Base { static void Work(); }; struct Derived : Base {};
void Run() { DERIVED::Work(); }
""")
    assert _calls(result) == set()


def test_an_inherited_field_uses_its_declaring_class_alias(tmp_path):
    _, result = _extract(tmp_path, """
struct Actions { void Work(); };
struct Base { using Alias = Actions; Alias actions; }; struct Derived : Base {};
void Run(Derived& x) { x.actions.Work(); }
""")
    assert _calls(result) == {("Actions", ".Work()", "INFERRED")}


def test_unincluded_base_is_not_supplied_by_the_corpus(tmp_path):
    _, result = _extract(tmp_path, "struct Derived : Base {}; void Run(Derived& x) { x.Work(); }",
                         extra={"other.hpp": "struct Base { void Work(); };"})
    assert _calls(result) == set()


def test_deep_inheritance_stops_without_recursion_failure(tmp_path):
    types = "struct Base0 { void Work(); };\n" + "\n".join(
        f"struct Base{i} : Base{i - 1} {{}};" for i in range(1, 128))
    _, result = _extract(tmp_path, types + "\nvoid Run(Base127& x) { x.Work(); }")
    assert _calls(result) == set()


def test_incremental_caller_reuses_persisted_base_and_field_facts(tmp_path):
    paths, original = _extract(tmp_path, "void Run(Derived& x) { x.actions.Work(); }", """
struct Actions { void Work(); }; struct Base { Actions actions; }; struct Derived : Base {};
""")
    original = json.loads(json.dumps(original))
    fresh = extract([paths[0]], root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
                    resolution_context_nodes=[n for n in original["nodes"] if n.get("source_file") != "use.cpp"],
                    resolution_context_edges=[e for e in original["edges"] if e.get("source_file") != "use.cpp"])
    assert _calls({"nodes": original["nodes"] + fresh["nodes"],
                   "edges": [e for e in original["edges"] if e["relation"] in {"method", "defines"}]
                   + fresh["edges"]}) == {("Actions", ".Work()", "INFERRED")}


def test_old_ast_cache_does_not_hide_inherited_alias_fields(tmp_path, monkeypatch):
    import graphify.cache as cache

    assert cache._AST_CACHE_SCHEMA >= 43
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 42)
        paths, _ = _extract(tmp_path, "void Run(Derived& x) { x.actions.Work(); }", """
struct Actions { void Work(); };
struct Base { using Alias = Actions; Alias actions; }; struct Derived : Base {};
""")
    for path in (tmp_path / "cache").rglob("*.json"):
        value = path.read_text(encoding="utf-8")
        path.write_text(value.replace('"_cpp_type_bindings"', '"old_bindings"')
                        .replace('"_cpp_lookup"', '"old_lookup"'), encoding="utf-8")
    fresh = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert _calls(fresh) == {("Actions", ".Work()", "INFERRED")}


def test_new_member_edges_preserve_raw_call_metadata(tmp_path):
    from graphify.extract import _resolve_cpp_member_calls, extract_cpp

    path = tmp_path / "use.cpp"
    path.write_text("struct Base { void Work(); }; struct Derived : Base {}; "
                    "void Run(Derived& x) { x.Work(); }", encoding="utf-8")
    result = extract_cpp(path)
    raw = next(rc for rc in result["raw_calls"] if rc.get("callee") == "Work")
    raw["metadata"] = {"recovered_by": "cpp_conditional_initializers", "branch": "unknown"}
    _resolve_cpp_member_calls([result], result["nodes"], result["edges"])
    edge = next(e for e in result["edges"] if e["relation"] == "calls")
    assert edge["metadata"] == raw["metadata"]


def test_include_traversal_is_cached_between_include_directives(tmp_path):
    from graphify.cpp_resolution import CppTypeLookup

    _, result = _extract(tmp_path, "void Run(Derived& x) { x.Work(); }", '#include "base.hpp"\nstruct Derived : Base {};',
                         {"base.hpp": "struct Base { void Work(); };"})
    lookup = CppTypeLookup(result["nodes"], result["edges"])
    visits = []

    class CountedImports(list):
        def __iter__(self):
            visits.append(1)
            return super().__iter__()

    lookup.imports = {source: CountedImports(imports) for source, imports in lookup.imports.items()}
    assert lookup.reachable("use.cpp", 100) == {"use.cpp", "types.hpp", "base.hpp"}
    traversals = len(visits)
    assert lookup.reachable("use.cpp", 200) == {"use.cpp", "types.hpp", "base.hpp"}
    assert len(visits) == traversals
    assert lookup.reachable("use.cpp", 0) == {"use.cpp"}


def test_absent_members_do_not_rewalk_shared_inheritance_subtrees(tmp_path, monkeypatch):
    from graphify.cpp_resolution import CppTypeLookup

    source = "struct A0 {}; struct B0 {};\n" + "\n".join(
        f"struct A{i} : A{i - 1}, B{i - 1} {{}}; struct B{i} : A{i - 1}, B{i - 1} {{}};"
        for i in range(1, 13))
    _, result = _extract(tmp_path, source)
    lookup = CppTypeLookup(result["nodes"], result["edges"])
    original = lookup.resolve
    visits = []

    def counted(*args):
        visits.append(1)
        return original(*args)

    monkeypatch.setattr(lookup, "resolve", counted)
    [owner] = lookup.types["A12"]
    assert lookup.member_owner(owner, "Missing", "method") is None
    assert len(visits) <= 50
