"""A `std::`-qualified type is not a project symbol and must not bind to one (#5219).

`_cpp_collect_type_refs` keeps only the tail of a qualified name, so
`std::chrono::seconds` became the stub `seconds`, and the corpus-wide rewire
mapped that stub onto the only project symbol with that label, here a
`using seconds = ...` alias in the anonymous namespace of another `.cc`.

The reference stays (the graph still says a type uses `seconds`), but a
`std::`-qualified name now gets its own sourceless stub that the rewire skips.
Template arguments inside a std type (`std::vector<HttpClient>`) are the
project's own types and are references as before.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract

_HISTORY = """#include <chrono>
namespace { using seconds = std::chrono::duration<double>; }
double age() { return seconds(1).count(); }
"""


def _run(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    return extract(paths, cache_root=tmp_path / "graphify-out", parallel=False)


def _by_id(result: dict) -> dict[str, dict]:
    return {n["id"]: n for n in result["nodes"]}


def _refs(result: dict) -> set[tuple[str, str]]:
    nodes = _by_id(result)
    return {
        (nodes.get(e["source"], {}).get("label", e["source"]),
         nodes.get(e["target"], {}).get("label", e["target"]))
        for e in result["edges"]
        if e["relation"] == "references"
    }


def _project_symbol(result: dict, label: str) -> str:
    return next(n["id"] for n in result["nodes"] if n["label"] == label and n.get("source_file"))


def _targets(result: dict, source_label: str) -> set[str]:
    source = next(n["id"] for n in result["nodes"] if n["label"] == source_label)
    return {e["target"] for e in result["edges"]
            if e["relation"] == "references" and e["source"] == source}


def test_std_qualified_type_does_not_bind_to_a_project_alias_of_the_same_name(tmp_path):
    r = _run(tmp_path, {
        "libc/src/history.cc": _HISTORY,
        "libb/src/user.cc": "#include <chrono>\nstruct Timer { std::chrono::seconds wait; };\n",
    })
    nodes = _by_id(r)
    alias = _project_symbol(r, "seconds")
    targets = _targets(r, "Timer")
    assert alias not in targets, "Timer's std::chrono::seconds bound to the project alias"
    # the reference itself is kept, on the standard library's own stub
    std_stubs = [nodes[t] for t in targets if nodes[t]["label"] == "seconds"]
    assert len(std_stubs) == 1 and not std_stubs[0].get("source_file")
    assert not any(
        e["target"] == alias and e["relation"] == "references" and e["source"] != alias
        for e in r["edges"]
    ), "the project's own `seconds` alias picked up a phantom reference"


def test_leading_global_scope_and_nested_std_namespaces_are_covered(tmp_path):
    r = _run(tmp_path, {
        "history.cc": _HISTORY,
        "user.cc": ("#include <chrono>\n"
                    "struct A { ::std::chrono::seconds a; std::chrono::seconds b; };\n"),
    })
    assert _project_symbol(r, "seconds") not in _targets(r, "A")


def test_unqualified_name_still_binds_to_the_project_symbol(tmp_path):
    """Only `std::`-qualified names are fenced off: a project type referenced by
    its bare name keeps resolving across files."""
    r = _run(tmp_path, {
        "types.hpp": "struct Ticks {};\n",
        "user.cc": '#include "types.hpp"\nstruct Clock { Ticks t; };\n',
    })
    assert ("Clock", "Ticks") in _refs(r)
    assert _project_symbol(r, "Ticks") in _targets(r, "Clock")


def test_template_arguments_of_a_std_type_are_still_references(tmp_path):
    r = _run(tmp_path, {
        "client.hpp": "struct HttpClient {};\nstruct Auth {};\n",
        "svc.cc": ('#include <vector>\n#include <map>\n#include <string>\n#include "client.hpp"\n'
                   "struct Svc {\n  std::vector<HttpClient> clients;\n"
                   "  std::map<std::string, Auth> auth;\n};\n"),
    })
    refs = _refs(r)
    assert ("Svc", "HttpClient") in refs
    assert ("Svc", "Auth") in refs
    # and the std containers themselves are still referenced, as before
    assert ("Svc", "vector") in refs and ("Svc", "map") in refs


def test_a_project_type_in_a_project_namespace_still_resolves(tmp_path):
    r = _run(tmp_path, {
        "net.hpp": "namespace net { struct Socket {}; }\n",
        "app.cc": '#include "net.hpp"\nstruct App { net::Socket s; };\n',
    })
    assert ("App", "Socket") in _refs(r)


def test_a_local_type_named_like_a_std_one_does_not_capture_the_std_reference(tmp_path):
    """`struct string {}` in the file must not absorb `std::string`."""
    r = _run(tmp_path, {
        "a.cc": "#include <string>\nstruct string {};\nstruct Holder { std::string s; string t; };\n",
    })
    nodes = _by_id(r)
    local = _project_symbol(r, "string")
    targets = _targets(r, "Holder")
    assert local in targets            # the bare `string` is the local type
    assert any(nodes[t]["label"] == "string" and not nodes[t].get("source_file")
               for t in targets), "std::string should keep its own stub"
