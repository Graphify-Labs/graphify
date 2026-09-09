"""Regression tests for direct recursion producing a `calls` self-edge (#3350).

The direct-call path in the tree-sitter engine emitted an edge only when
`tgt_nid != caller_nid`, so a call whose callee resolved to the caller itself —
i.e. direct recursion — was dropped. `factorial` calling `factorial` produced
nothing while `entry` calling `factorial` produced an edge, so the extracted
call structure did not match the source. `build_from_json` has kept a supplied
recursive `calls` self-edge since #2038; only extraction was withholding it.

The one case where a name resolving to the caller is *not* recursion is a local
binding or parameter that shadows the definition, and that stays edge-free.
"""
from __future__ import annotations

from pathlib import Path

import pytest


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _calls(result: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge.get("relation") == "calls"
    }


def test_python_direct_recursion_emits_a_self_edge(tmp_path: Path):
    from graphify.extract import extract

    source = _write(
        tmp_path / "repro.py",
        "def factorial(n):\n"
        "    return 1 if n < 2 else n * factorial(n - 1)\n"
        "\n"
        "def entry(n):\n"
        "    return factorial(n)\n",
    )

    result = extract([source], root=tmp_path, cache_root=tmp_path)

    calls = _calls(result)
    assert ("repro_factorial", "repro_factorial") in calls
    # The ordinary call must be unaffected.
    assert ("repro_entry", "repro_factorial") in calls


def test_recursive_self_edge_carries_extracted_confidence_and_a_location(tmp_path: Path):
    from graphify.extract import extract

    source = _write(
        tmp_path / "walk.py",
        "def walk(node):\n"
        "    for child in node:\n"
        "        walk(child)\n",
    )

    result = extract([source], root=tmp_path, cache_root=tmp_path)

    self_edges = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls" and edge["source"] == edge["target"]
    ]
    assert len(self_edges) == 1
    assert self_edges[0]["confidence"] == "EXTRACTED"
    assert self_edges[0]["source_location"] == "L3"


def test_repeated_recursive_calls_produce_one_edge(tmp_path: Path):
    """The pair-dedup guard still applies: two call sites, one edge."""
    from graphify.extract import extract

    source = _write(
        tmp_path / "fib.py",
        "def fib(n):\n"
        "    if n < 2:\n"
        "        return n\n"
        "    return fib(n - 1) + fib(n - 2)\n",
    )

    result = extract([source], root=tmp_path, cache_root=tmp_path)

    self_edges = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls" and edge["source"] == edge["target"]
    ]
    assert len(self_edges) == 1


def test_javascript_direct_recursion_emits_a_self_edge(tmp_path: Path):
    from graphify.extract import extract

    source = _write(
        tmp_path / "rec.js",
        "function fact(n) { return n < 2 ? 1 : n * fact(n - 1); }\n"
        "function main() { return fact(5); }\n",
    )

    result = extract([source], root=tmp_path, cache_root=tmp_path)

    calls = _calls(result)
    assert ("rec_fact", "rec_fact") in calls
    assert ("rec_main", "rec_fact") in calls


@pytest.mark.parametrize(
    "filename,text",
    [
        (
            "shadow.js",
            "function run() {\n"
            "  const run = () => 1;\n"
            "  return run();\n"
            "}\n",
        ),
        (
            "shadow.py",
            "def run(run):\n"
            "    return run()\n",
        ),
    ],
)
def test_a_shadowed_name_is_not_recursion(tmp_path: Path, filename: str, text: str):
    """A local binding or parameter of the same name names a value, not the
    enclosing function, so no self-edge."""
    from graphify.extract import extract

    source = _write(tmp_path / filename, text)

    result = extract([source], root=tmp_path, cache_root=tmp_path)

    assert not [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls" and edge["source"] == edge["target"]
    ]


def test_a_shadowed_self_call_is_not_parked_for_cross_file_resolution(tmp_path: Path):
    """Rejecting the shadowed call must not hand the name to the corpus-level
    resolver, which would bind it to an unrelated same-named definition."""
    from graphify.extract import extract

    shadowing = _write(
        tmp_path / "app.js",
        "function run() {\n"
        "  const run = () => 1;\n"
        "  return run();\n"
        "}\n",
    )
    elsewhere = _write(tmp_path / "lib.js", "export function run() { return 2; }\n")

    result = extract([shadowing, elsewhere], root=tmp_path, cache_root=tmp_path)

    assert ("app_run", "lib_run") not in _calls(result)


def test_a_recursive_edge_survives_graph_construction(tmp_path: Path):
    """End to end: the extracted self-edge reaches the built graph (#2038)."""
    from graphify.build import build_from_json
    from graphify.extract import extract

    source = _write(
        tmp_path / "repro.py",
        "def factorial(n):\n"
        "    return 1 if n < 2 else n * factorial(n - 1)\n",
    )

    result = extract([source], root=tmp_path, cache_root=tmp_path)
    graph = build_from_json(result)

    assert graph.has_edge("repro_factorial", "repro_factorial")
