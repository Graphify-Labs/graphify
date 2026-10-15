"""`merge-graphs` finishes a Python `from module import symbol` call across repos (#3744).

A single-repo build binds `from config_validator import validator_from_json` plus a
plain `validator_from_json(...)` call only when `config_validator.py` is in the same
build. When it lives in another repository the import resolves to nothing on disk,
the facts pass skipped it, and nothing reached `graph.json`: the merged graph had an
`imports_from` edge to a sourceless placeholder and no `calls` edge at all.

The Python resolver now parks those names on the caller (and the import itself on
the importing file node) and the #3152 merge pass finishes them by module stem. As
with the member-call series, the cases below pin the guards as much as the edges:
exactly one other-repo module, exactly one top-level definition, Python only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import networkx as nx

from graphify.cross_repo_calls import CROSS_REPO_CALL_MARKER, link_cross_repo_member_calls

PYTHON = sys.executable

LIB = (
    "def validator_from_json(data):\n"
    "    return ConfDict(data)\n"
    "\n"
    "\n"
    "class ConfDict:\n"
    "    def __init__(self, data):\n"
    "        self.data = data\n"
)
APP = (
    "from config_validator import validator_from_json\n"
    "\n"
    "\n"
    "def load(payload):\n"
    "    return validator_from_json(payload)\n"
)


def _write_graph(path: Path, nodes: list[dict], links: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"directed": False, "multigraph": False, "graph": {},
                                "nodes": nodes, "links": links}), encoding="utf-8")


def _build(tmp_path: Path, repo: str, files: dict[str, str]) -> Path:
    """Extract one repo the way a real build does and write its `graph.json`."""
    from graphify.extract import extract

    paths = []
    for name, body in files.items():
        path = tmp_path / repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=tmp_path / repo, cache_root=tmp_path / repo / "graphify-out")
    graph = tmp_path / repo / "graphify-out" / "graph.json"
    _write_graph(graph, result["nodes"], result["edges"])
    return graph


def _merge(tmp_path: Path, *graphs: Path) -> dict:
    out = tmp_path / "merged.json"
    result = subprocess.run([PYTHON, "-m", "graphify", "merge-graphs", *map(str, graphs),
                             "--out", str(out)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, f"merge failed: {result.stderr}"
    return json.loads(out.read_text(encoding="utf-8"))


def _parked(graph: Path) -> list[tuple[str, dict]]:
    return [(node["label"], entry)
            for node in json.loads(graph.read_text(encoding="utf-8"))["nodes"]
            if isinstance(node.get("metadata"), dict)
            for entry in node["metadata"].get("unresolved_calls", [])]


def _cross_repo_edges(merged: dict) -> set[tuple]:
    label = {n["id"]: n.get("label") for n in merged["nodes"]}
    return {
        (label.get(e.get("_src", e["source"])), e["relation"], label.get(e.get("_tgt", e["target"])))
        for e in merged["links"]
        if e.get(CROSS_REPO_CALL_MARKER)
    }


# --- the build parks ---------------------------------------------------------


def test_an_unresolved_from_import_call_is_parked_on_its_caller(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    parked = _parked(app)
    calls = [(label, e) for label, e in parked if e.get("relation") != "imports"]
    assert len(calls) == 1, parked
    label, entry = calls[0]
    assert label == "load()"
    assert (entry["module"], entry["callee"], entry["lang"]) == (
        "config_validator", "validator_from_json", "python")
    assert entry["line"], "the call site travels with the entry"


def test_the_import_itself_is_parked_on_the_importing_file(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    imports = [(label, e) for label, e in _parked(app) if e.get("relation") == "imports"]
    assert imports == [("app.py", {
        "callee": "validator_from_json", "module": "config_validator",
        "lang": "python", "relation": "imports", "line": "L1",
    })], imports


def test_an_aliased_import_parks_the_imported_name_not_the_alias(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": (
        "from config_validator import validator_from_json as vfj\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    return vfj(payload)\n"
    )})
    calls = [e for _, e in _parked(app) if e.get("relation") != "imports"]
    assert [e["callee"] for e in calls] == ["validator_from_json"], calls


def test_an_import_resolved_in_the_same_build_parks_nothing(tmp_path: Path):
    """The joint scan already binds it; parking it too would be a second edge."""
    joint = _build(tmp_path, "joint", {"app.py": APP, "config_validator.py": LIB})
    assert _parked(joint) == []


def test_a_dotted_or_relative_import_parks_nothing(tmp_path: Path):
    """Single-module stems only: `pkg.sub` and `.sibling` are out of scope."""
    app = _build(tmp_path, "app", {"app.py": (
        "from pkg.config_validator import validator_from_json\n"
        "from .sibling import helper\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    helper()\n"
        "    return validator_from_json(payload)\n"
    )})
    assert _parked(app) == []


def test_an_imported_name_that_is_never_called_parks_only_the_import(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": (
        "from config_validator import validator_from_json\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    return payload\n"
    )})
    assert [e.get("relation") for _, e in _parked(app)] == ["imports"]


# --- the merge finishes ------------------------------------------------------


def test_the_merge_finishes_the_call_and_the_import(tmp_path: Path):
    """#3744's exact repro, end to end through the real command."""
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    edges = _cross_repo_edges(_merge(tmp_path, app, lib))
    assert ("load()", "calls", "validator_from_json()") in edges, edges
    assert ("app.py", "imports", "validator_from_json()") in edges, edges
    assert ("app.py", "imports_from", "config_validator.py") in edges, edges


def test_the_merged_call_is_inferred_and_tagged(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    merged = _merge(tmp_path, app, lib)
    calls = [e for e in merged["links"]
             if e.get(CROSS_REPO_CALL_MARKER) and e["relation"] == "calls"]
    assert len(calls) == 1
    assert calls[0]["confidence"] == "INFERRED"
    assert calls[0]["context"] == "cross_repo"


def test_two_repos_providing_the_module_bind_nothing(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    lib2 = _build(tmp_path, "lib2", {"config_validator.py": LIB})
    assert _cross_repo_edges(_merge(tmp_path, app, lib, lib2)) == set()


def test_a_module_without_that_name_binds_nothing(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": "def other():\n    return 1\n"})
    edges = _cross_repo_edges(_merge(tmp_path, app, lib))
    assert not any(rel in ("calls", "imports") for _, rel, _ in edges), edges


def test_a_method_of_the_same_name_does_not_answer(tmp_path: Path):
    """`from m import f` names a top-level binding; `C.f` in m is not it."""
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": (
        "class Holder:\n"
        "    def validator_from_json(self, data):\n"
        "        return data\n"
    )})
    edges = _cross_repo_edges(_merge(tmp_path, app, lib))
    assert not any(rel == "calls" for _, rel, _ in edges), edges


def test_an_imported_class_call_binds_to_the_class(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": (
        "from config_validator import ConfDict\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    return ConfDict(payload)\n"
    )})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    edges = _cross_repo_edges(_merge(tmp_path, app, lib))
    assert ("load()", "calls", "ConfDict") in edges, edges


def test_a_same_named_module_in_another_language_binds_nothing():
    G = nx.Graph()
    G.add_node("app::app", label="app.py", source_file="app.py", repo="app",
               metadata={"unresolved_calls": [
                   {"callee": "f", "module": "util", "lang": "python", "relation": "imports"}]})
    G.add_node("lib::util", label="util.js", source_file="util.js", repo="lib")
    G.add_node("lib::util_f", label="f()", source_file="util.js", repo="lib")
    G.add_edge("lib::util", "lib::util_f", relation="contains")
    assert link_cross_repo_member_calls(G) == 0


def test_running_twice_does_not_duplicate_the_edges():
    G = nx.Graph()
    G.add_node("app::app", label="app.py", source_file="app.py", repo="app")
    G.add_node("app::app_load", label="load()", source_file="app.py", repo="app",
               metadata={"unresolved_calls": [
                   {"callee": "f", "module": "util", "lang": "python", "line": "L5"}]})
    G.add_node("lib::util", label="util.py", source_file="util.py", repo="lib")
    G.add_node("lib::util_f", label="f()", source_file="util.py", repo="lib")
    G.add_edge("lib::util", "lib::util_f", relation="contains")
    assert link_cross_repo_member_calls(G) == 1
    assert link_cross_repo_member_calls(G) == 1
    assert G.number_of_edges() == 2


def test_the_callers_own_repo_never_answers():
    """This pass never re-decides a call inside one repo."""
    G = nx.Graph()
    G.add_node("app::app_load", label="load()", source_file="app.py", repo="app",
               metadata={"unresolved_calls": [
                   {"callee": "f", "module": "util", "lang": "python", "line": "L5"}]})
    G.add_node("app::util", label="util.py", source_file="util.py", repo="app")
    G.add_node("app::util_f", label="f()", source_file="util.py", repo="app")
    G.add_edge("app::util", "app::util_f", relation="contains")
    assert link_cross_repo_member_calls(G) == 0


def test_a_stdlib_import_parks_nothing(tmp_path: Path):
    """`from collections import deque` is the stdlib, never another repo's loose
    `collections.py`, so it must not be offered to the merge at all."""
    app = _build(tmp_path, "app", {"app.py": (
        "from collections import deque\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    return deque(payload)\n"
    )})
    assert _parked(app) == []


def test_a_stdlib_named_module_in_another_repo_is_never_bound(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": (
        "from collections import deque\n"
        "\n"
        "\n"
        "def load(payload):\n"
        "    return deque(payload)\n"
    )})
    lib = _build(tmp_path, "lib", {"collections.py": "def deque(x):\n    return x\n"})
    assert _cross_repo_edges(_merge(tmp_path, app, lib)) == set()


# --- review follow-ups on #4474 ---------------------------------------------

CALLERS = (
    "import functools\n"
    "from config_validator import validator_from_json\n"
    "\n"
    "\n"
    "def load(payload):\n"
    "    return validator_from_json(payload)\n"
    "\n"
    "\n"
    "@functools.lru_cache\n"
    "def load_cached(payload):\n"
    "    return validator_from_json(payload)\n"
    "\n"
    "\n"
    "class Service:\n"
    "    def run(self, payload):\n"
    "        return validator_from_json(payload)\n"
)


def test_decorated_functions_and_methods_park_their_calls(tmp_path: Path):
    """Flask/FastAPI/Click code is mostly decorated functions; the facts pass's
    own call walk skipped them and every method. Parking reads the per-file raw
    calls, the same facts the joint scan binds these calls from."""
    app = _build(tmp_path, "app", {"app.py": CALLERS})
    callers = sorted(label for label, e in _parked(app) if e.get("relation") != "imports")
    assert callers == [".run()", "load()", "load_cached()"], callers


def test_decorated_functions_and_methods_link_like_the_joint_scan(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": CALLERS})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    calls = {src for src, rel, _ in _cross_repo_edges(_merge(tmp_path, app, lib))
             if rel == "calls"}
    assert calls == {"load()", "load_cached()", ".run()"}, calls


def test_a_module_inside_a_package_does_not_answer_a_bare_import(tmp_path: Path):
    """`mylib/utils.py` is importable only as `mylib.utils`, so it must not answer
    `from utils import retry` — the in-repo resolver refuses it too (#2072)."""
    app = _build(tmp_path, "app", {"app.py": (
        "from utils import retry\n"
        "\n"
        "\n"
        "def load():\n"
        "    return retry()\n"
    )})
    lib = _build(tmp_path, "lib", {
        "mylib/__init__.py": "",
        "mylib/utils.py": "def retry():\n    return 1\n",
    })
    assert _cross_repo_edges(_merge(tmp_path, app, lib)) == set()


def test_a_loose_module_in_a_non_package_directory_still_answers(tmp_path: Path):
    """The package guard keys on `__init__.py`, not on nesting: a module in a
    plain directory (scripts on the path, src layouts without a package) binds."""
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"src/config_validator.py": LIB})
    edges = _cross_repo_edges(_merge(tmp_path, app, lib))
    assert ("load()", "calls", "validator_from_json()") in edges, edges


def test_the_merge_summary_does_not_call_import_edges_member_calls(tmp_path: Path):
    app = _build(tmp_path, "app", {"app.py": APP})
    lib = _build(tmp_path, "lib", {"config_validator.py": LIB})
    out = tmp_path / "merged.json"
    result = subprocess.run([PYTHON, "-m", "graphify", "merge-graphs", str(app), str(lib),
                             "--out", str(out)], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "linked 3 edge(s) across repos (calls and imports)" in result.stdout, result.stdout
    assert "member call(s)" not in result.stdout
