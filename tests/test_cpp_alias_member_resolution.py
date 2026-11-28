"""Alias receiver calls use lexical declarations and explicit include reachability."""
import importlib.util
import json

import pytest

from graphify.extract import extract, extract_cpp

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
        path.parent.mkdir(parents=True, exist_ok=True)
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


@pytest.mark.parametrize("declaration,type_name,expression", [
    ("using Alias = Worker;", "Alias&", "x.Work()"),
    ("typedef Worker Alias;", "Alias&", "x.Work()"),
    ("using Alias = Worker*;", "Alias", "x->Work()"),
    ("typedef Worker* Alias;", "Alias", "x->Work()"),
    ("using First = Worker; using Alias = First;", "Alias&", "x.Work()"),
    ("using Alias = std::unique_ptr<Worker>;", "Alias&", "x->Work()"),
])
def test_namespace_alias_receiver(tmp_path, declaration, type_name, expression):
    _, result = _extract(tmp_path, f"void Run(app::{type_name} x) {{ {expression}; }}",
                         f"namespace app {{ struct Worker {{ void Work(); }}; {declaration} }}")
    assert _calls(result) == {("app::Worker", ".Work()", "INFERRED")}


def test_local_aliases_use_the_receiver_declaration_scope(tmp_path):
    _, result = _extract(tmp_path, """
struct First { void Work(); }; struct Second { void Work(); };
using Alias = First;
void Run() {
    Alias outer;
    { using Alias = Second; Alias inner; inner.Work(); }
    { outer.Work(); using Alias = Second; }
}
""")
    assert _calls(result) == {("First", ".Work()", "INFERRED"),
                              ("Second", ".Work()", "INFERRED")}


@pytest.mark.parametrize("mixed", [False, True], ids=["crlf", "mixed"])
@pytest.mark.parametrize("final_newline", [False, True])
def test_line_endings_preserve_lookup_facts_and_resolution(tmp_path, mixed, final_newline):
    files = {
        "types.hpp": """// café: UTF-8 bytes before every stored position
struct Worker { void Work(); };
struct Other { void Work(); };
using Alias = Worker;
struct Base { Alias item; };
struct Derived : Base {};
""",
        "use.cpp": """// café: includes must not become retroactive
void Before(Alias& x) { x.Work(); }
#include "types.hpp"
void Run(Derived& x) { x.item.Work(); }
void Local() {
    Alias outer;
    { using Alias = Other; Alias inner; inner.Work(); }
    outer.Work();
}
void Hidden() { using Alias = Missing; Alias x; x.Work(); }
""",
    }
    if not final_newline:
        files = {name: source.rstrip("\n") for name, source in files.items()}
    paths = [tmp_path / name for name in files]
    for path in paths:
        path.write_bytes(files[path.name].encode("utf-8"))
    raw = [extract_cpp(path) for path in paths]
    cache_root = tmp_path / "cache"
    expected = extract(paths, root=tmp_path, cache_root=cache_root, parallel=False)
    assert _calls(expected) == {("Worker", ".Work()", "INFERRED")}
    assert _calls(expected, "Local()") == {("Worker", ".Work()", "INFERRED"),
                                          ("Other", ".Work()", "INFERRED")}
    assert _calls(expected, "Before()") == _calls(expected, "Hidden()") == set()

    for path in paths:
        source = files[path.name].replace("\n", "\r\n", 2 if mixed else -1).encode("utf-8")
        path.write_bytes(source)
    assert [extract_cpp(path) for path in paths] == raw
    for _ in range(2):  # Re-extraction, then the warm AST-cache path.
        actual = extract(paths, root=tmp_path, cache_root=cache_root, parallel=False)
        for key in ("nodes", "edges"):
            assert sorted(json.dumps(item, sort_keys=True) for item in actual[key]) == sorted(
                json.dumps(item, sort_keys=True) for item in expected[key])
    for path in paths:
        assert path.read_bytes() == files[path.name].replace(
            "\n", "\r\n", 2 if mixed else -1).encode("utf-8")


def test_class_alias_types_a_field(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { void Work(); };
struct Owner { using Alias = Worker; Alias item; void Run() { item.Work(); } };
""")
    assert _calls(result, ".Run()") == {("Worker", ".Work()", "INFERRED")}


def test_scope_qualified_alias_call(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { static void Work(); }; using Alias = Worker;
void Run() { Alias::Work(); }
""")
    assert _calls(result) == {("Worker", ".Work()", "EXTRACTED")}


def test_alias_target_cannot_be_supplied_by_an_unincluded_header(tmp_path):
    _, result = _extract(tmp_path, "using Alias = Worker; void Run(Alias& x) { x.Work(); }",
                         extra={"other.hpp": "struct Worker { void Work(); };"})
    assert _calls(result) == set()


def test_include_after_a_receiver_declaration_is_not_retroactive(tmp_path):
    _, result = _extract(tmp_path, 'void Run(Alias& x) { x.Work(); }\n#include "other.hpp"',
                         extra={"other.hpp": "struct Worker { void Work(); }; using Alias = Worker;"})
    assert _calls(result) == set()


def test_transitive_include_alias(tmp_path):
    _, result = _extract(tmp_path, "void Run(Alias& x) { x.Work(); }", '#include "other.hpp"',
                         {"other.hpp": "struct Worker { void Work(); }; using Alias = Worker;"})
    assert _calls(result) == {("Worker", ".Work()", "INFERRED")}


@pytest.mark.parametrize("declaration", [
    "using Alias = Missing;", "using Alias = Alias;", "using Alias = Other; using Other = Alias;",
    "using Alias = std::vector<Worker>;", "template<class T> using Alias = T;",
])
def test_unknown_or_unsupported_alias_does_not_guess(tmp_path, declaration):
    _, result = _extract(tmp_path, f"""
struct Worker {{ void Work(); }}; {declaration}
void Run(Alias& x) {{ x.Work(); }}
""")
    assert _calls(result) == set()


def test_later_alias_and_wrong_case_are_not_visible(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { void Work(); }; using alias = Worker;
void Run(Alias& x) { x.Work(); }
using Alias = Worker;
""")
    assert _calls(result) == set()


def test_unincluded_alias_and_target_are_not_visible(tmp_path):
    _, result = _extract(tmp_path, "void Run(Alias& x) { x.Work(); }", extra={
        "other.hpp": "struct Worker { void Work(); }; using Alias = Worker;",
    })
    assert _calls(result) == set()


def test_unknown_local_alias_hides_an_outer_alias(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { void Work(); }; using Alias = Worker;
void Run() { using Alias = Missing; Alias x; x.Work(); }
""")
    assert _calls(result) == set()


def test_namespace_directives_do_not_choose_between_ambiguous_aliases(tmp_path):
    _, result = _extract(tmp_path, """
namespace a { struct Worker { void Work(); }; using Alias = Worker; }
namespace b { struct Worker { void Work(); }; using Alias = Worker; }
using namespace a; using namespace b;
void Run(Alias& x) { x.Work(); }
""")
    assert _calls(result) == set()


def test_a_named_struct_typedef_is_still_a_receiver_type(tmp_path):
    _, result = _extract(tmp_path, """
typedef struct Worker { void Work(); } Worker;
void Run(Worker& x) { x.Work(); }
""")
    assert _calls(result) == {("Worker", ".Work()", "INFERRED")}


def test_unimported_namespace_type_is_not_visible_by_simple_name(tmp_path):
    _, result = _extract(tmp_path, """
namespace app { struct Worker { void Work(); }; }
void Run(Worker& x) { x.Work(); }
""")
    assert _calls(result) == set()


def test_deep_alias_chains_stop_without_recursion_failure(tmp_path):
    aliases = "using Alias0 = Worker;\n" + "\n".join(
        f"using Alias{i} = Alias{i - 1};" for i in range(1, 128))
    _, result = _extract(tmp_path, "struct Worker { void Work(); };\n" + aliases
                         + "\nvoid Run(Alias127& x) { x.Work(); }")
    assert _calls(result) == set()


def test_conditional_alias_alternatives_are_not_configured(tmp_path):
    _, result = _extract(tmp_path, """
struct First { void Work(); }; struct Second { void Work(); };
#if PICK_FIRST
using Alias = First;
#else
using Alias = Second;
#endif
void Run(Alias& x) { x.Work(); }
""")
    assert _calls(result) == set()


def test_a_conditional_alias_hides_an_outer_alias_without_becoming_configured(tmp_path):
    _, result = _extract(tmp_path, """
struct First { void Work(); }; struct Second { void Work(); }; using Alias = First;
void Run() {
#ifdef PICK_SECOND
using Alias = Second;
#endif
Alias x; x.Work();
}
""")
    assert _calls(result) == set()


def test_a_conventional_header_guard_allows_an_alias(tmp_path):
    _, result = _extract(tmp_path, "void Run(Alias& x) { x.Work(); }", """
#ifndef TYPES_HPP
#define TYPES_HPP
struct Worker { void Work(); }; using Alias = Worker;
#endif
""")
    assert _calls(result) == {("Worker", ".Work()", "INFERRED")}


def test_a_later_class_alias_blocks_an_outer_alias_in_an_inline_body(tmp_path):
    _, result = _extract(tmp_path, """
struct Good { void Work(); }; struct Bad { void Work(); }; using Alias = Good;
struct Holder { void Run() { Alias x; x.Work(); } using Alias = Bad; };
""")
    assert not any(owner == "Good" for owner, _, _ in _calls(result, ".Run()"))


@pytest.mark.parametrize("shadow", ["namespace Good = Other;", "using Good = Other;",
                                     "namespace Good {}", "struct Good {};", "union Good {};"])
def test_a_qualified_prefix_blocks_fallback_to_an_outer_namespace(tmp_path, shadow):
    other = "namespace Other {}" if shadow.startswith("namespace Good =") else "struct Other {};"
    _, result = _extract(tmp_path, f"""
namespace Good {{ struct Type {{ void Work(); }}; }}
{other}
namespace app {{ {shadow} void Run(Good::Type& x) {{ x.Work(); }} }}
""")
    assert _calls(result) == set()


def test_incremental_alias_receiver_uses_persisted_header_facts(tmp_path):
    paths, original = _extract(tmp_path, "void Run(app::Alias& x) { x.Work(); }",
                              "namespace app { struct Worker { void Work(); }; using Alias = Worker; }")
    original = json.loads(json.dumps(original))
    fresh = extract([paths[0]], root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
                    resolution_context_nodes=[n for n in original["nodes"] if n.get("source_file") != "use.cpp"],
                    resolution_context_edges=[e for e in original["edges"] if e.get("source_file") != "use.cpp"])
    combined = {"nodes": original["nodes"] + fresh["nodes"],
                "edges": [e for e in original["edges"] if e["relation"] in {"method", "defines"}]
                + fresh["edges"]}
    assert _calls(combined) == {("app::Worker", ".Work()", "INFERRED")}


@pytest.mark.parametrize("source", [
    "using Alias = Foreign; void Run(Alias& x) { x.Work(); }",
    "void Run() { using Alias = Foreign; Alias x; x.Work(); }",
    "void Run() { using Alias = Foreign; Alias::Work(); }",
])
def test_an_unknown_alias_does_not_park_an_unrelated_class_name(tmp_path, source):
    _, result = _extract(tmp_path, source)
    assert not any(entry.get("receiver_type") == "Alias"
                   for node in result["nodes"]
                   for entry in node.get("metadata", {}).get("unresolved_calls", []))


def test_root_relative_literal_include_keeps_the_existing_import_proof(tmp_path):
    _, result = _extract(tmp_path, "", extra={
        "Client/Runner.cpp": '#include "Engine/Worker.hpp"\nvoid Run(Alias& x) { x.Work(); }',
        "Engine/Worker.hpp": "struct Worker { void Work(); }; using Alias = Worker;",
    })
    assert _calls(result) == {("Worker", ".Work()", "INFERRED")}


@pytest.mark.parametrize("header", [
    "struct Worker { void Work(); };\n#ifndef FEATURE\n#define FEATURE\nusing Alias = Worker;\n#endif",
    "#ifndef TYPES_HPP\n#define TYPES_HPP\nstruct Worker { void Work(); }; using Alias = Worker;\n#else\nint version;\n#endif",
    "struct Worker { void Work(); };\n#ifdef FEATURE\nusing Alias = Worker;\n#endif",
])
def test_feature_blocks_and_partial_guards_do_not_configure_aliases(tmp_path, header):
    _, result = _extract(tmp_path, "void Run(Alias& x) { x.Work(); }", header)
    assert _calls(result) == set()


def test_anonymous_nested_namespace_alias_does_not_become_a_global_alias(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { void Work(); };
namespace app { namespace { using Alias = Worker; } }
void Run(Alias& x) { x.Work(); }
""")
    assert _calls(result) == set()


@pytest.mark.parametrize("target", ["std::unique_ptr<Worker&>", "std::shared_ptr<Worker&&>",
                                     "std::unique_ptr<Ref>"])
def test_smart_pointer_pointees_do_not_erase_reference_aliases(tmp_path, target):
    _, result = _extract(tmp_path, f"""
struct Worker {{ void Work(); }}; using Ref = Worker&; using Alias = {target};
void Run(Alias& x) {{ x->Work(); }}
""")
    assert _calls(result) == set()


def test_reference_aliases_still_type_an_ordinary_receiver(tmp_path):
    _, result = _extract(tmp_path, """
struct Worker { void Work(); }; using Alias = Worker&;
void Run(Alias x) { x.Work(); }
""")
    assert _calls(result) == {("Worker", ".Work()", "INFERRED")}


@pytest.mark.parametrize("prefix,expected", [("std", set()), ("::std", {("Wrong", ".Work()", "INFERRED")})])
def test_a_shadowed_std_namespace_is_not_a_standard_pointer_wrapper(tmp_path, prefix, expected):
    _, result = _extract(tmp_path, f"""
struct Wrong {{ void Work(); }}; struct Actual {{ void Work(); }};
namespace app {{
namespace std {{ template<class T> struct unique_ptr {{ Actual* operator->(); }}; }}
using Alias = {prefix}::unique_ptr<Wrong>;
void Run(Alias& x) {{ x->Work(); }}
}}
""")
    assert _calls(result) == expected
