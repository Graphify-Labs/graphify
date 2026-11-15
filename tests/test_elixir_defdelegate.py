"""`defdelegate` defines an invocable function in the module (#4132).

`defdelegate greet(name), to: Greeter` declares a callable `greet` whose body is
delegated to another module. It has the same `call` head shape as `def`, but was
missing from the def-family recognizer, so no node was minted and same-module
calls to the delegated name dangled.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _graph(tmp_path: Path):
    src = tmp_path / "facade.ex"
    src.write_text(
        "defmodule Facade do\n"
        "  defdelegate start(x), to: Worker\n"
        "  defdelegate stop(x), to: Worker, as: :halt\n"
        "  def run(x) do\n"
        "    start(x)\n"
        "    stop(x)\n"
        "  end\n"
        "end\n",
        encoding="utf-8",
    )
    result = extract([src], cache_root=tmp_path / "graphify-out")
    label = {n["id"]: n["label"] for n in result["nodes"]}
    return result, label


def _edges(result, label, relation):
    return {
        (label[e["source"]], label[e["target"]])
        for e in result["edges"]
        if e["relation"] == relation and e["source"] in label and e["target"] in label
    }


def test_defdelegate_defines_functions(tmp_path: Path) -> None:
    result, label = _graph(tmp_path)
    labels = set(label.values())
    assert "start()" in labels, "defdelegate function dropped"
    assert "stop()" in labels, "defdelegate-with-as function dropped"
    methods = _edges(result, label, "method")
    assert ("Facade", "start()") in methods
    assert ("Facade", "stop()") in methods


def test_defdelegate_same_module_calls_resolve(tmp_path: Path) -> None:
    result, label = _graph(tmp_path)
    calls = _edges(result, label, "calls")
    assert ("run()", "start()") in calls, "call to a delegated function dangled"
    assert ("run()", "stop()") in calls


def test_defdelegate_leaves_no_dangling_edges(tmp_path: Path) -> None:
    result, _ = _graph(tmp_path)
    node_ids = {n["id"] for n in result["nodes"]}
    dangling = [
        e for e in result["edges"]
        if e["source"] not in node_ids or e["target"] not in node_ids
    ]
    assert not dangling, f"defdelegate produced dangling edges: {dangling}"
