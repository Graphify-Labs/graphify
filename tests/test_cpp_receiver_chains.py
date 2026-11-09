"""Declared C++ receiver chains resolve without guessing by method name."""
import json

import pytest

from graphify.extract import extract


HEADER = """
#include <memory>
namespace app {
struct Direct { void Execute() {} };
struct Smart { void Execute() {} };
struct ValueClient { Direct actions; };
struct SmartClient { std::unique_ptr<Smart> actions; };
struct SharedClient { std::shared_ptr<Smart> actions; };
struct RawClient { Smart* actions; };
struct Outer { SmartClient client; };
}
"""


def _extract(tmp_path, source, header=HEADER, reverse=False):
    paths = [tmp_path / "types.hpp", tmp_path / "use.cpp"]
    paths[0].write_text(header, encoding="utf-8")
    paths[1].write_text('#include "types.hpp"\n' + source, encoding="utf-8")
    result = extract(paths[::-1] if reverse else paths, root=tmp_path,
                     cache_root=tmp_path / "cache", parallel=False)
    return paths, result


def _calls(result, caller="Run()"):
    nodes = {n["id"]: n for n in result["nodes"]}
    owners = {e["target"]: nodes[e["source"]].get("_cpp_qualified")
              for e in result["edges"] if e["relation"] in {"method", "defines"}}
    return [(owners.get(e["target"]), nodes[e["target"]]["label"], e["confidence"])
            for e in result["edges"] if e["relation"] == "calls"
            and nodes[e["source"]]["label"] == caller]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("parameter,expression,owner", [
    ("app::Direct& x", "x.Execute()", "app::Direct"),
    ("std::unique_ptr<app::Smart>& x", "x->Execute()", "app::Smart"),
    ("app::ValueClient& x", "x.actions.Execute()", "app::Direct"),
    ("app::SmartClient& x", "x.actions->Execute()", "app::Smart"),
    ("app::SharedClient* x", "x->actions->Execute()", "app::Smart"),
    ("app::RawClient& x", "(x).actions->Execute()", "app::Smart"),
    ("app::Outer& x", "x.client.actions->Execute()", "app::Smart"),
    ("app::SmartClient& x", "([&] { x.actions->Execute(); })()", "app::Smart"),
])
def test_split_header_chains(tmp_path, parameter, expression, owner, reverse):
    paths, result = _extract(tmp_path, f"void Run({parameter}) {{ {expression}; }}", reverse=reverse)
    assert _calls(result) == [(owner, ".Execute()", "INFERRED")]
    cached = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert _calls(cached) == _calls(result)


def test_scope_and_same_named_fields(tmp_path):
    _, result = _extract(tmp_path, """
void Run(app::SmartClient& x) {
    { app::ValueClient x; x.actions.Execute(); }
    ([&](app::ValueClient& x) { x.actions.Execute(); })(*(app::ValueClient*)nullptr);
    x.actions->Execute();
}
void Other(app::ValueClient& x) { x.actions.Execute(); }
""")
    assert set(_calls(result)) == {("app::Direct", ".Execute()", "INFERRED"),
                                   ("app::Smart", ".Execute()", "INFERRED")}
    assert _calls(result, "Other()") == [("app::Direct", ".Execute()", "INFERRED")]


@pytest.mark.parametrize("body", [
    "{ auto x = unknown(); x.actions->Execute(); }",
    "([&](auto& x) { x.actions->Execute(); })(unknown());",
    "([x = unknown()] { x.actions->Execute(); })();",
    "{ std::vector<app::SmartClient> x; x.actions->Execute(); }",
    "{ UnresolvedAlias x; x.actions->Execute(); }",
    "x.missing->Execute();",
    "x.actions.Execute();",  # dot accesses the wrapper, not its pointee
])
def test_unsupported_or_shadowed_receivers_do_not_guess(tmp_path, body):
    _, result = _extract(tmp_path, f"void Run(app::SmartClient& x) {{ {body} }}")
    assert _calls(result) == []


def test_namespace_ambiguity_does_not_pick_a_same_named_class(tmp_path):
    header = HEADER + "\nnamespace other { struct SmartClient { app::Direct actions; }; }"
    _, result = _extract(tmp_path, "void Run(SmartClient& x) { x.actions->Execute(); }", header)
    assert _calls(result) == []


@pytest.mark.parametrize("body", [
    "([&](app::ValueClient& x) { x.actions.Execute(); })(*(app::ValueClient*)nullptr);",
    "{ app::ValueClient x; x.actions.Execute(); }",
])
def test_inner_binding_is_the_only_target(tmp_path, body):
    _, result = _extract(tmp_path, f"void Run(app::SmartClient& x) {{ {body} }}")
    assert _calls(result) == [("app::Direct", ".Execute()", "INFERRED")]


@pytest.mark.parametrize("expression", ["unknown().actions->Execute()", "x.missing->Execute()",
                                       "x.actions->execute()", "x.actions.Execute()"])
def test_same_file_and_case_collisions_do_not_guess(tmp_path, expression):
    _, result = _extract(tmp_path, HEADER + f"\nvoid Run(app::SmartClient& x) {{ {expression}; }}", "")
    assert _calls(result) == []


def test_lowercase_smart_pointer_type_uses_the_declared_receiver(tmp_path):
    _, result = _extract(tmp_path, """
struct action { void Execute() {} };
void Run(std::unique_ptr<action>& x) { x->Execute(); }
""", "")
    assert _calls(result) == [("action", ".Execute()", "INFERRED")]


@pytest.mark.parametrize("expression", ["this->client.actions->Execute()", "client.actions->Execute()"])
def test_explicit_this_chain_and_implicit_field(tmp_path, expression):
    header = HEADER + "\nstruct Holder { app::SmartClient client; void Run(); };"
    _, result = _extract(tmp_path, f"void Holder::Run() {{ {expression}; }}", header)
    assert _calls(result, "Holder::Run()") == [("app::Smart", ".Execute()", "INFERRED")]


def test_forward_declaration_is_not_a_competing_definition(tmp_path):
    paths, _ = _extract(tmp_path, "void Run(app::SmartClient& x) { x.actions->Execute(); }")
    forward = tmp_path / "forward.hpp"
    forward.write_text("namespace app { struct Smart; }", encoding="utf-8")
    result = extract([forward, *paths], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert _calls(result) == [("app::Smart", ".Execute()", "INFERRED")]


@pytest.mark.parametrize("wrapper", ["std::weak_ptr<app::Smart>", "CustomPtr<app::Smart>",
                                    "std::unique_ptr<app::Smart[]>",
                                    "std::unique_ptr<app::Smart, CustomDeleter>"])
def test_unsupported_pointer_wrappers_do_not_unwrap(tmp_path, wrapper):
    _, result = _extract(tmp_path, f"void Run({wrapper}& x) {{ x->Execute(); }}")
    assert _calls(result) == []


def test_prior_ast_cache_is_not_reused(tmp_path, monkeypatch):
    import graphify.cache as cache
    current = cache._AST_CACHE_SCHEMA
    assert current > 40
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 40)
        paths, _ = _extract(tmp_path, "void Run(app::SmartClient& x) { x.actions->Execute(); }")
        # Strip the new metadata as if these entries predated chain support.
        for path in (tmp_path / "cache").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace('"_cpp_fields"', '"old_fields"')
                           .replace('"cpp_receiver_chain"', '"old_chain"'), encoding="utf-8")
    fresh = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert _calls(fresh) == [("app::Smart", ".Execute()", "INFERRED")]


def test_incremental_caller_uses_persisted_header_fields(tmp_path):
    paths, result = _extract(tmp_path, "void Run(app::SmartClient& x) { x.actions->Execute(); }")
    result = json.loads(json.dumps(result))
    paths[1].write_text(paths[1].read_text(encoding="utf-8") + "\n// caller edit\n", encoding="utf-8")
    fresh = extract([paths[1]], root=tmp_path, cache_root=tmp_path / "cache", parallel=False,
                    resolution_context_nodes=[n for n in result["nodes"] if n.get("source_file") != "use.cpp"],
                    resolution_context_edges=[e for e in result["edges"] if e.get("source_file") != "use.cpp"])
    combined = {"nodes": result["nodes"] + fresh["nodes"], "edges": [
        e for e in result["edges"] if e.get("relation") in {"method", "defines"}
    ] + fresh["edges"]}
    assert _calls(combined) == [("app::Smart", ".Execute()", "INFERRED")]
    assert not any(n.get("source_file") == "types.hpp" for n in fresh["nodes"])
