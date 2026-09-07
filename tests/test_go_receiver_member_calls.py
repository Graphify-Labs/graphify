"""Go member calls resolve through the receiver's declared type.

The shared cross-file pass skips member calls and the Go extractor read the receiver's
name only to throw it away, so `g.Greet()` on a receiver whose type lives in another
file produced no edge — the Go twin of the Swift gap in #1356. Each case below pins one
source of the receiver's type, and the negative cases pin what must stay unresolved: a
constructor return, a chain that does not start at the method's own receiver, a
package-qualified type, and an ambiguous type name.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)

GREETER = "package svc\n\ntype Greeter struct{}\n\nfunc (g *Greeter) Greet() {}\n"


def _calls(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(label.get(e["source"]), label.get(e["target"])): e
             for e in result["edges"] if e["relation"] == "calls"}
    return calls, result


def _greet_edge(calls: dict) -> dict | None:
    return next((e for (src, tgt), e in calls.items()
                 if src and "un()" in src and tgt == ".Greet()"), None)


def test_a_typed_parameter_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\nfunc Run(g *Greeter) { g.Greet() }\n",
    })
    edge = _greet_edge(calls)
    assert edge is not None, calls
    # The type came from the table, never from the call site: `g` names a variable, so
    # there is no spelling of this call that would be exact.
    assert edge["confidence"] == "INFERRED"


def test_a_struct_field_types_the_receiver_through_the_methods_own_receiver(tmp_path):
    # The dominant Go shape: the dependency is held as a field and used from a method.
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\ntype App struct {\n\tgreeter *Greeter\n}\n\n"
                      "func (a *App) Run() { a.greeter.Greet() }\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_var_declaration_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\nfunc Run() {\n\tvar g Greeter\n\tg.Greet()\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_composite_literal_binding_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\nfunc Run() {\n\tg := Greeter{}\n\tg.Greet()\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_an_address_of_composite_literal_types_the_receiver(tmp_path):
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\nfunc Run() {\n\tg := &Greeter{}\n\tg.Greet()\n}\n",
    })
    assert _greet_edge(calls) is not None, calls


def test_a_constructor_return_resolves_to_nothing(tmp_path):
    # `g := NewGreeter()` types `g` only by reading the constructor's return type, which
    # this pass does not do; nothing in the file writes `Greeter` next to `g`.
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER + "\nfunc NewGreeter() *Greeter { return &Greeter{} }\n",
        "svc/app.go": "package svc\n\nfunc Run() {\n\tg := NewGreeter()\n\tg.Greet()\n}\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_chain_not_rooted_at_the_methods_receiver_resolves_to_nothing(tmp_path):
    # `p.greeter.Greet()` on a parameter: the flat table cannot say that `greeter` is a
    # field of `p`'s type rather than of some other type declared in the file.
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\ntype App struct {\n\tgreeter *Greeter\n}\n\n"
                      "func Run(p *App) { p.greeter.Greet() }\n",
    })
    assert _greet_edge(calls) is None, calls


def test_a_package_qualified_type_resolves_to_nothing(tmp_path):
    # `other.Greeter` names a type in another package; binding it to the local `Greeter`
    # by bare name would ignore the qualifier.
    calls, _ = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/app.go": "package svc\n\nimport \"example.com/other\"\n\n"
                      "func Run(g *other.Greeter) { g.Greet() }\n",
    })
    assert _greet_edge(calls) is None, calls


def test_two_packages_declaring_the_same_type_resolve_to_neither(tmp_path):
    # The single-definition guard: without import evidence, guessing one of two
    # `Greeter`s is worse than leaving the call unresolved.
    calls, _ = _calls(tmp_path, {
        "a/greeter.go": GREETER.replace("package svc", "package a"),
        "b/greeter.go": GREETER.replace("package svc", "package b"),
        "svc/app.go": "package svc\n\nfunc Run(g *Greeter) { g.Greet() }\n",
    })
    assert _greet_edge(calls) is None, calls


def test_the_first_binding_of_a_name_wins(tmp_path):
    # The table is flat per file, so a parameter named like an earlier one has to lose:
    # otherwise `other`'s signature would redirect the first function's calls.
    calls, result = _calls(tmp_path, {
        "svc/greeter.go": GREETER,
        "svc/other.go": "package svc\n\ntype Other struct{}\n\nfunc (o *Other) Greet() {}\n",
        "svc/app.go": "package svc\n\nfunc Run(g *Greeter) { g.Greet() }\n\n"
                      "func Also(g *Other) { g.Greet() }\n",
    })
    source_of = {n["id"]: str(n.get("source_file") or "") for n in result["nodes"]}
    label_of = {n["id"]: n["label"] for n in result["nodes"]}
    run_targets = {source_of[e["target"]] for e in result["edges"]
                   if e["relation"] == "calls"
                   and label_of.get(e["source"]) == "Run()"
                   and label_of.get(e["target"]) == ".Greet()"}
    assert len(run_targets) == 1, run_targets
    assert run_targets.pop().endswith("greeter.go")


def test_a_same_file_method_call_keeps_its_extracted_edge(tmp_path):
    # In-file resolution still happens by bare label before this pass, so the edge must
    # stay EXTRACTED and must not be doubled.
    calls, _ = _calls(tmp_path, {
        "svc/app.go": "package svc\n\ntype App struct{}\n\nfunc (a *App) Greet() {}\n\n"
                      "func Run(a *App) { a.Greet() }\n",
    })
    edges = [e for (src, tgt), e in calls.items() if src == "Run()" and tgt == ".Greet()"]
    assert len(edges) == 1, calls
    assert edges[0]["confidence"] == "EXTRACTED"


def test_a_type_from_another_language_never_answers_a_go_receiver(tmp_path):
    # The declaration index is corpus-wide, so a same-named Java class would both answer
    # the receiver and hide that no Go file declares it — the call belongs to the merge.
    calls, result = _calls(tmp_path, {
        "svc/app.go": "package svc\n\nfunc Run(g *Greeter) { g.Greet() }\n",
        "java/Greeter.java": "public class Greeter { public void Greet() {} }\n",
    })
    assert _greet_edge(calls) is None, calls
    parked = [(n.get("metadata") or {}).get("unresolved_calls")
              for n in result["nodes"] if n["label"] == "Run()"]
    assert parked == [[{"callee": "Greet", "receiver_type": "Greeter",
                        "lang": "go", "line": "L3"}]], parked


def test_the_methods_own_receiver_outranks_an_earlier_binding_of_the_name(tmp_path):
    # `s` is bound to `Server` earlier in the file, but inside `Get` it is the method's own
    # receiver: a `Store` with no `Save` must stay unresolved rather than reach Server's.
    calls, _ = _calls(tmp_path, {
        "svc/a.go": "package svc\n\nfunc Run(s *Server) {}\n\n"
                    "type Store struct{}\n\nfunc (s *Store) Get() { s.Save() }\n",
        "svc/b.go": "package svc\n\ntype Server struct{}\n\nfunc (s *Server) Save() {}\n",
    })
    assert (".Get()", ".Save()") not in calls, calls
