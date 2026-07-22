"""Object-literal repository-pattern methods get their own graph nodes.

`const repo = { findX(...) {...}, y: async () => {...} }` at module scope
previously produced exactly ONE node — for `repo` itself — and nothing for
its methods. The module-level-const branch that handles object/array/factory
values created that single node and then unconditionally returned True,
which short-circuits the caller's default recursive descent into `repo`'s
children, so `findX`/`y` were never visited by any code path and never
became nodes. Every call into or out of such a method was therefore
invisible to the graph — `affected findX`, `explain findX`, and the call
graph itself all silently dropped this whole pattern.

This is distinct from #2023/#1985 (edge resolution to nodes that already
exist) — here, the target node never existed to resolve to in the first
place. Reproduced against a real 28-method repository object in the wild
(`paymentsRepo` in a production TypeScript codebase) before this fix.
"""
from __future__ import annotations

from graphify.extract import extract


def _graph(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    r = extract([tmp_path / n for n in files], cache_root=tmp_path / "graphify-out")
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    ids = {n["id"] for n in r["nodes"]}
    calls = {(lbl.get(e["source"]), lbl.get(e["target"])) for e in r["edges"]
              if e["relation"] == "calls"}
    methods = {(e["source"], e["target"]) for e in r["edges"]
               if e["relation"] == "method"}
    return r, ids, calls, methods


_REPO_TS = (
    "function doStuff(a: string) { return a; }\n\n"
    "export const repo = {\n"
    "  findX(a: string) {\n"
    "    return doStuff(a);\n"
    "  },\n"
    "  async listY(a: string) {\n"
    "    return doStuff(a);\n"
    "  },\n"
    "  arrowZ: async (a: string) => {\n"
    "    return doStuff(a);\n"
    "  },\n"
    "};\n"
)


def test_shorthand_method_gets_its_own_node(tmp_path):
    r, ids, _calls, _methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    assert any(i.endswith("_repo_findx") for i in ids), ids


def test_async_shorthand_method_gets_its_own_node(tmp_path):
    r, ids, _calls, _methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    assert any(i.endswith("_repo_listy") for i in ids), ids


def test_arrow_valued_property_gets_its_own_node(tmp_path):
    r, ids, _calls, _methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    assert any(i.endswith("_repo_arrowz") for i in ids), ids


def test_object_still_gets_its_own_container_node(tmp_path):
    r, ids, _calls, _methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    assert any(i.endswith("_repo") and not i.endswith("_findx")
               and not i.endswith("_listy") and not i.endswith("_arrowz")
               for i in ids), ids


def test_method_edge_from_container_to_each_member(tmp_path):
    r, ids, _calls, methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    container = next(i for i in ids if i.endswith("_repo"))
    targets = {t for s, t in methods if s == container}
    assert len(targets) == 3, methods


def test_call_inside_method_body_resolves(tmp_path):
    r, _ids, calls, _methods = _graph(tmp_path, {"repo.ts": _REPO_TS})
    assert any(s == ".findX()" and t == "doStuff()" for s, t in calls), calls


def test_same_file_call_to_member_expression_method_resolves(tmp_path):
    # Cross-file member-call resolution through an imported plain-object binding
    # (as opposed to a `new Class()` instance, which test_ts_receiver_member_calls.py
    # covers) is a separate, broader resolution concern — out of scope here, matching
    # this module's docstring on #2023/#1985. This asserts what the fix actually
    # guarantees: once the node exists, a same-file caller resolves to it.
    same_file = _REPO_TS + (
        "export function caller() {\n"
        "  return repo.findX(\"a\");\n"
        "}\n"
    )
    r, _ids, calls, _methods = _graph(tmp_path, {"repo.ts": same_file})
    assert any(s == "caller()" and t == ".findX()" for s, t in calls), calls
