"""`merge-graphs` finishes a member call whose receiver type is in another repo (#3152).

A single-repo build binds `obj.method()` only when the receiver's type is declared
in the same build, so a call into another repository was dropped with the receiver
type already in hand and nothing about it reached `graph.json` — the only artifact
`merge-graphs` and `global add` read. The two-repo graph was missing precisely the
edges that make it a call graph.

The Java, C++, C# and Swift resolvers now park those calls on the caller node and
this pass finishes them after the merge. The cases below pin what it must NOT do
as much as what it must: the single-definition guard, the cross-repo-only scope,
and the language guard are what keep it from fabricating an edge from a name
collision.
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.cross_repo_calls import (
    CROSS_REPO_CALL_MARKER,
    link_cross_repo_member_calls,
)

PYTHON = sys.executable


def _needs(module: str):
    """Skip a real-extraction case when its tree-sitter grammar is absent."""
    try:
        importlib.import_module(module)
        missing = False
    except ImportError:
        missing = True
    return pytest.mark.skipif(missing, reason=f"{module} not installed")


needs_java = _needs("tree_sitter_java")
needs_cpp = _needs("tree_sitter_cpp")
needs_csharp = _needs("tree_sitter_c_sharp")
needs_swift = _needs("tree_sitter_swift")


def _caller(repo: str, parked: list[dict], node_id: str = "app_run",
            source_file: str = "src/App.java") -> tuple[str, dict]:
    return f"{repo}::{node_id}", {
        "label": ".run()", "source_file": source_file, "repo": repo,
        "metadata": {"unresolved_calls": parked},
    }


def _declaration(repo: str, label: str, source_file: str = "src/Greeter.java",
                 node_id: str = "greeter", sourced: bool = True) -> tuple[str, dict]:
    data: dict = {"label": label, "repo": repo, "_callable_class": True, "_callable": True}
    if sourced:
        data["source_file"] = source_file
    return f"{repo}::{node_id}", data


def _method(repo: str, label: str = ".greet()", node_id: str = "greeter_greet",
            source_file: str = "src/Greeter.java") -> tuple[str, dict]:
    return f"{repo}::{node_id}", {"label": label, "repo": repo,
                                  "source_file": source_file, "_callable": True}


def _graph(*, caller, declarations, relation: str = "method") -> nx.Graph:
    """Build a merged-graph shape: one caller plus (declaration, member) pairs."""
    G = nx.Graph()
    G.add_node(caller[0], **caller[1])
    for decl, method in declarations:
        G.add_node(decl[0], **decl[1])
        G.add_node(method[0], **method[1])
        G.add_edge(decl[0], method[0], relation=relation)
    return G


def _added_calls(G: nx.Graph) -> set[tuple[str, str]]:
    return {(data.get("_src"), data.get("_tgt"))
            for _, _, data in G.edges(data=True) if data.get(CROSS_REPO_CALL_MARKER)}


PARKED_GREET = [{"callee": "greet", "receiver_type": "Greeter", "lang": "java", "line": "L10"}]


def test_a_parked_call_binds_to_the_one_declaration_in_another_repo():
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter"), _method("b"))],
    )
    assert link_cross_repo_member_calls(G) == 1
    assert _added_calls(G) == {("a::app_run", "b::greeter_greet")}
    data = G.edges["a::app_run", "b::greeter_greet"]
    assert data["relation"] == "calls"
    assert data["confidence"] == "INFERRED"
    assert data["context"] == "cross_repo"
    assert data["source_location"] == "L10"


def test_two_repos_declaring_the_same_name_bind_nothing():
    # The single-definition guard the single-repo resolvers apply. Two `Greeter`
    # declarations mean the call is ambiguous, and guessing one is worse than
    # leaving the edge out.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[
            (_declaration("b", "Greeter"), _method("b")),
            (_declaration("c", "Greeter"), _method("c")),
        ],
    )
    assert link_cross_repo_member_calls(G) == 0
    assert _added_calls(G) == set()


def test_a_declaration_in_the_callers_own_repo_binds_nothing():
    # A call parked from repo `a` was parked because `a` has no such type. If one
    # shows up under `a` anyway the single-repo resolver already had its chance
    # and refused; this pass only ever crosses a repo boundary.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("a", "Greeter"), _method("a"))],
    )
    assert link_cross_repo_member_calls(G) == 0


def test_a_declaration_in_another_language_binds_nothing():
    # Without the language guard a Java `Greeter` binds just as happily to a
    # Python class of the same name in another repo.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter", "greeter.py"),
                       _method("b", source_file="greeter.py"))],
    )
    assert link_cross_repo_member_calls(G) == 0


PARKED_CPP = [{"callee": "greet", "receiver_type": "Greeter", "lang": "cpp", "line": "L1"}]


def test_a_cpp_call_does_not_bind_to_a_csharp_declaration():
    # Every parking language now has its own suffix set, so the guard has to keep
    # them apart from each other and not just from the languages that never park.
    G = _graph(
        caller=_caller("a", PARKED_CPP, source_file="src/app.cpp"),
        declarations=[(_declaration("b", "Greeter", "Greeter.cs"),
                       _method("b", ".greet()", source_file="Greeter.cs"))],
    )
    assert link_cross_repo_member_calls(G) == 0


def test_a_cpp_header_declaration_answers_through_defines():
    # A C++ class that only declares `void greet();` owns it through `defines`,
    # the relation the extractor also uses for fields, so a header-only library
    # would otherwise answer nothing.
    G = _graph(
        caller=_caller("a", PARKED_CPP, source_file="src/app.cpp"),
        declarations=[(_declaration("b", "Greeter", "greeter.h"),
                       _method("b", "greet", source_file="greeter.h"))],
        relation="defines",
    )
    assert link_cross_repo_member_calls(G) == 1
    assert _added_calls(G) == {("a::app_run", "b::greeter_greet")}


def test_a_defines_member_does_not_answer_a_java_call():
    # Outside C++ a `defines` target is a field, and a field cannot be called.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter"), _method("b"))],
        relation="defines",
    )
    assert link_cross_repo_member_calls(G) == 0


def test_the_definition_answers_before_a_same_named_declaration():
    # A C++ class declares `void greet();` in its header (`defines`) and defines
    # it out of line in the `.cpp` (`method`). Both hang off the one folded class
    # node, and the definition is the better target.
    decl = _declaration("b", "Greeter", "greeter.h")
    G = _graph(
        caller=_caller("a", PARKED_CPP, source_file="src/app.cpp"),
        declarations=[(decl, _method("b", "greet", "greeter_decl", "greeter.h"))],
        relation="defines",
    )
    definition = _method("b", ".greet()", "greeter_def", "greeter.cpp")
    G.add_node(definition[0], **definition[1])
    G.add_edge(decl[0], definition[0], relation="method")

    assert link_cross_repo_member_calls(G) == 1
    assert _added_calls(G) == {("a::app_run", "b::greeter_def")}


def test_a_sourceless_stub_does_not_answer_a_parked_call():
    # A stub minted for a dangling reference has no declaration behind it, so it
    # cannot own the method the call is looking for.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter", sourced=False), _method("b"))],
    )
    assert link_cross_repo_member_calls(G) == 0


def test_a_declaration_without_that_method_binds_nothing():
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter"), _method("b", ".farewell()"))],
    )
    assert link_cross_repo_member_calls(G) == 0


def test_an_unknown_language_binds_nothing():
    # Only languages listed in _LANG_SUFFIXES park calls; an entry from anywhere
    # else cannot be language-checked, so it is not acted on.
    parked = [{"callee": "greet", "receiver_type": "Greeter", "lang": "cobol"}]
    G = _graph(
        caller=_caller("a", parked),
        declarations=[(_declaration("b", "Greeter"), _method("b"))],
    )
    assert link_cross_repo_member_calls(G) == 0


def test_running_twice_does_not_duplicate_the_edge():
    # `global add` composes one repo at a time and revisits the same pairs on
    # every add, so the pass must be safe to re-run over its own output.
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter"), _method("b"))],
    )
    assert link_cross_repo_member_calls(G) == 1
    edges_after_first = G.number_of_edges()
    assert link_cross_repo_member_calls(G) == 1
    assert G.number_of_edges() == edges_after_first


def test_a_repo_that_stops_declaring_the_type_loses_the_edge():
    """Recompute-from-scratch is what keeps a stale answer from surviving."""
    G = _graph(
        caller=_caller("a", PARKED_GREET),
        declarations=[(_declaration("b", "Greeter"), _method("b"))],
    )
    assert link_cross_repo_member_calls(G) == 1
    G.remove_node("b::greeter_greet")
    assert link_cross_repo_member_calls(G) == 0
    assert _added_calls(G) == set()


def _write_graph(path: Path, nodes: list[dict], links: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"directed": False, "multigraph": False, "graph": {},
                                "nodes": nodes, "links": links}), encoding="utf-8")


def _merge(tmp_path: Path, a: Path, b: Path) -> dict:
    out = tmp_path / "merged.json"
    result = subprocess.run([PYTHON, "-m", "graphify", "merge-graphs", str(a), str(b),
                             "--out", str(out)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, f"merge failed: {result.stderr}"
    return {"data": json.loads(out.read_text(encoding="utf-8")), "stdout": result.stdout}


def _build(tmp_path: Path, repo: str, name: str, body: str) -> Path:
    """Extract one repo the way a real build does and write its `graph.json`."""
    from graphify.extract import extract

    path = tmp_path / repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    result = extract([path], cache_root=tmp_path / repo / "graphify-out")
    graph = tmp_path / repo / "graphify-out" / "graph.json"
    _write_graph(graph, result["nodes"], result["edges"])
    return graph


def _parked(graph: Path) -> list[dict]:
    """Every parked entry in a written `graph.json`, flattened across nodes."""
    return [entry
            for node in json.loads(graph.read_text(encoding="utf-8"))["nodes"]
            if isinstance(node.get("metadata"), dict)
            for entry in node["metadata"].get("unresolved_calls", [])]


def _cross_repo_calls(merged: dict) -> list[dict]:
    return [e for e in merged["data"]["links"]
            if e.get("relation") == "calls" and e.get("context") == "cross_repo"]


def test_merge_graphs_cli_finishes_the_parked_call(tmp_path: Path):
    # The pass has to be reached through the real command, not just called
    # directly, and it has to survive the repo prefixing the merge applies.
    a = tmp_path / "app" / "graphify-out" / "graph.json"
    b = tmp_path / "lib" / "graphify-out" / "graph.json"
    _write_graph(a, [{"id": "app_run", "label": ".run()", "source_file": "src/App.java",
                      "metadata": {"unresolved_calls": PARKED_GREET}}], [])
    _write_graph(
        b,
        [{"id": "greeter", "label": "Greeter", "source_file": "src/Greeter.java",
          "_callable_class": True, "_callable": True},
         {"id": "greeter_greet", "label": ".greet()", "source_file": "src/Greeter.java",
          "_callable": True}],
        [{"source": "greeter", "target": "greeter_greet", "relation": "method"}],
    )

    merged = _merge(tmp_path, a, b)
    calls = _cross_repo_calls(merged)
    assert len(calls) == 1, merged["stdout"]
    assert {calls[0]["source"], calls[0]["target"]} == {"app::app_run", "lib::greeter_greet"}
    assert calls[0]["confidence"] == "INFERRED"


@needs_java
def test_a_java_build_parks_the_call_and_the_merge_finishes_it(tmp_path: Path):
    """The two halves together: a real Java extraction of each repo, then the
    merge. `App` calls a method on a `Greeter` that only the other repo declares,
    which is the case a single build resolves for one corpus and drops for two."""
    app = _build(tmp_path, "app", "src/App.java",
                 "class App {\n"
                 "    Greeter greeter;\n"
                 "    void run() { this.greeter.greet(); }\n"
                 "}\n")
    lib = _build(tmp_path, "lib", "src/Greeter.java",
                 "class Greeter { void greet() {} }\n")

    parked = _parked(app)
    assert len(parked) == 1, parked
    entry = parked[0]
    assert (entry["callee"], entry["receiver_type"], entry["lang"]) == ("greet", "Greeter", "java")
    assert entry["line"], "the call site travels with the entry so the merged edge can carry it"

    merged = _merge(tmp_path, app, lib)
    calls = _cross_repo_calls(merged)
    assert len(calls) == 1, merged["stdout"]
    endpoints = {calls[0]["source"], calls[0]["target"]}
    assert any(e.startswith("app::") and "run" in e for e in endpoints), endpoints
    assert any(e.startswith("lib::") and "greet" in e for e in endpoints), endpoints


@pytest.mark.parametrize("lang,callee,app_file,lib_file", [
    pytest.param(
        "cpp", "greet",
        ("src/app.cpp", "void run() { Greeter g; g.greet(); }\n"),
        ("src/greeter.cpp", "class Greeter {\n public:\n  void greet() {}\n};\n"),
        marks=needs_cpp, id="cpp-typed-local",
    ),
    pytest.param(
        # `Greeter::greet()` is also the shape of a namespace-qualified free
        # function, so this is the arm that leans hardest on the merge's guards.
        "cpp", "greet",
        ("src/app.cpp", "void run() { Greeter::greet(); }\n"),
        ("src/greeter.cpp", "class Greeter {\n public:\n  static void greet() {}\n};\n"),
        marks=needs_cpp, id="cpp-qualified-receiver",
    ),
    pytest.param(
        "csharp", "Greet",
        ("src/App.cs", "class App {\n"
                       "    Greeter greeter;\n"
                       "    void Run() { greeter.Greet(); }\n"
                       "}\n"),
        ("src/Greeter.cs", "class Greeter { public void Greet() {} }\n"),
        marks=needs_csharp, id="csharp-field-receiver",
    ),
    pytest.param(
        "swift", "greet",
        ("src/App.swift", "class App {\n"
                          "    var greeter: Greeter\n"
                          "    func run() { greeter.greet() }\n"
                          "}\n"),
        ("src/Greeter.swift", "class Greeter { func greet() {} }\n"),
        marks=needs_swift, id="swift-property-receiver",
    ),
])
def test_each_language_parks_the_call_and_the_merge_finishes_it(
    tmp_path: Path, lang: str, callee: str, app_file: tuple[str, str],
    lib_file: tuple[str, str],
):
    """The Java case above, once per language that parks: the receiver's type is
    declared only in the other repo, so the build parks the call by name and the
    merge finishes it. The parked `lang` is asserted because it is what the merge
    matches the declaring file's suffix against."""
    app = _build(tmp_path, "app", *app_file)
    lib = _build(tmp_path, "lib", *lib_file)

    parked = _parked(app)
    assert len(parked) == 1, parked
    assert (parked[0]["callee"], parked[0]["receiver_type"], parked[0]["lang"]) == (
        callee, "Greeter", lang)
    assert parked[0]["line"], "the call site travels with the entry"

    merged = _merge(tmp_path, app, lib)
    calls = _cross_repo_calls(merged)
    assert len(calls) == 1, merged["stdout"]
    endpoints = {calls[0]["source"], calls[0]["target"]}
    assert any(e.startswith("app::") and "run" in e.lower() for e in endpoints), endpoints
    assert any(e.startswith("lib::") and callee.lower() in e.lower()
               for e in endpoints), endpoints

