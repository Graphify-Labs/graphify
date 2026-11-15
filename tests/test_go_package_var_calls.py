"""Calls in a Go package-level `var` initialiser are credited to the file.

Only function and method bodies were walked for calls, so a call made while initialising
a package-level `var`, most often inside a `var provider = func(...) {...}` closure kept
there as a swappable hook, produced no edge and its callee lost the caller. The file is
the owner, as for a module-level call in the other extractors: the initialiser has no
enclosing function.
"""
from __future__ import annotations

import importlib

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("tree_sitter_go") is None,
    reason="tree_sitter_go not installed",
)

DBIMPL = "package dbimpl\n\nfunc ProvideResourceDB(name string) string { return name }\n"


def _calls(tmp_path, files: dict[str, str]) -> set[tuple[str, str]]:
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    result = extract([tmp_path / n for n in files],
                     cache_root=tmp_path / "graphify-out", parallel=False)
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return {(label.get(e["source"]), label.get(e["target"]))
            for e in result["edges"] if e["relation"] == "calls"}


def test_a_call_inside_a_package_level_var_closure_is_credited_to_the_file(tmp_path):
    calls = _calls(tmp_path, {
        "go.mod": "module example.com/m\n\ngo 1.22\n",
        "dbimpl/dbimpl.go": DBIMPL,
        "cmd/migrate.go": "package cmd\n\nimport \"example.com/m/dbimpl\"\n\n"
                          "var resourceDBProvider = func(name string) string {\n"
                          "\treturn dbimpl.ProvideResourceDB(name)\n}\n",
    })
    assert ("migrate.go", "ProvideResourceDB()") in calls, calls


def test_a_same_file_call_in_a_package_level_var_initialiser_is_credited_to_the_file(tmp_path):
    calls = _calls(tmp_path, {
        "svc/svc.go": "package svc\n\nfunc newRegistry() int { return 1 }\n\n"
                      "var (\n\tregistry = newRegistry()\n\tother    = 2\n)\n",
    })
    assert ("svc.go", "newRegistry()") in calls, calls


def test_a_var_declared_inside_a_function_stays_with_the_function(tmp_path):
    # Only the package-level initialiser has no owner; a local `var` keeps its function.
    calls = _calls(tmp_path, {
        "svc/svc.go": "package svc\n\nfunc helper() int { return 1 }\n\n"
                      "func Run() int {\n\tvar x = helper()\n\treturn x\n}\n",
    })
    assert ("Run()", "helper()") in calls, calls
    assert ("svc.go", "helper()") not in calls, calls
