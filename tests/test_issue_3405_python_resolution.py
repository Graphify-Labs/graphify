"""Tests for issue #3405: Python nested-function extraction + lexical-scope-aware local call resolution."""
import pytest
from pathlib import Path

from graphify.extract import extract


def test_python_nested_function_node_and_contains(tmp_path: Path):
    """Test 1 — Nested node + contains

    def outer():
        def inner():
            pass
    """
    f = tmp_path / "test_nested.py"
    f.write_text(
        "def outer():\n"
        "    def inner():\n"
        "        pass\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    assert "outer()" in by_label
    assert "inner()" in by_label

    outer_id = by_label["outer()"]["id"]
    inner_id = by_label["inner()"]["id"]

    assert inner_id == f"{outer_id}_inner"
    assert by_label["inner()"].get("type") in (None, "function")

    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]
    assert (outer_id, inner_id, "contains") in edges


def test_python_outer_calls_nested_function(tmp_path: Path):
    """Test 2 — Outer calls nested function

    def outer():
        def inner():
            pass
        inner()
    """
    f = tmp_path / "test_call.py"
    f.write_text(
        "def outer():\n"
        "    def inner():\n"
        "        pass\n"
        "    inner()\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    outer_id = by_label["outer()"]["id"]
    inner_id = by_label["inner()"]["id"]

    call_edges = [
        e for e in result["edges"]
        if e["source"] == outer_id and e["target"] == inner_id and e["relation"] == "calls"
    ]
    assert len(call_edges) == 1
    edge = call_edges[0]
    assert edge["confidence"] == "EXTRACTED"
    assert edge["weight"] == 1.0

    # Ensure this call does not fall through to raw_calls (unresolved cross-file)
    raw_calls = result.get("raw_calls", [])
    for rc in raw_calls:
        assert rc.get("callee") != "inner"


def test_python_nested_function_shadows_module_function(tmp_path: Path):
    """Test 3 — Nested function shadows module function

    def walk():
        pass

    def trace():
        def walk():
            pass
        walk()
    """
    f = tmp_path / "test_shadow.py"
    f.write_text(
        "def walk():\n"
        "    pass\n"
        "\n"
        "def trace():\n"
        "    def walk():\n"
        "        pass\n"
        "    walk()\n"
    )
    result = extract([f], root=tmp_path)
    trace_nodes = [n for n in result["nodes"] if n["label"] == "trace()"]
    assert len(trace_nodes) == 1
    trace_id = trace_nodes[0]["id"]

    # Locate the nested walk vs module walk
    walk_nodes = [n for n in result["nodes"] if n["label"] == "walk()"]
    assert len(walk_nodes) == 2

    nested_walk = next(n for n in walk_nodes if n["id"].startswith(trace_id))
    module_walk = next(n for n in walk_nodes if not n["id"].startswith(trace_id))

    calls = [
        (e["source"], e["target"], e["relation"], e["confidence"], e["weight"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]

    # trace must call nested_walk, NOT module_walk!
    assert (trace_id, nested_walk["id"], "calls", "EXTRACTED", 1.0) in calls
    assert (trace_id, module_walk["id"], "calls", "EXTRACTED", 1.0) not in calls

    # Ensure no raw_calls for walk
    raw_calls = result.get("raw_calls", [])
    for rc in raw_calls:
        if rc.get("caller_nid") == trace_id:
            assert rc.get("callee") != "walk"


def test_python_nested_sibling_call(tmp_path: Path):
    """Test 4 — Nested sibling call

    def outer():
        def helper():
            pass
        def worker():
            helper()
        worker()
    """
    f = tmp_path / "test_sibling.py"
    f.write_text(
        "def outer():\n"
        "    def helper():\n"
        "        pass\n"
        "    def worker():\n"
        "        helper()\n"
        "    worker()\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    outer_id = by_label["outer()"]["id"]
    helper_id = by_label["helper()"]["id"]
    worker_id = by_label["worker()"]["id"]

    calls = [
        (e["source"], e["target"], e["relation"], e["confidence"], e["weight"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]

    assert (worker_id, helper_id, "calls", "EXTRACTED", 1.0) in calls
    assert (outer_id, worker_id, "calls", "EXTRACTED", 1.0) in calls


def test_python_nested_recursion(tmp_path: Path):
    """Test 5 — Nested recursion

    def outer():
        def walk(n):
            if n:
                walk(n - 1)
        walk(10)
    """
    f = tmp_path / "test_recursion.py"
    f.write_text(
        "def outer():\n"
        "    def walk(n):\n"
        "        if n:\n"
        "            walk(n - 1)\n"
        "    walk(10)\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    outer_id = by_label["outer()"]["id"]
    walk_id = by_label["walk()"]["id"]

    calls = [
        (e["source"], e["target"], e["relation"], e["confidence"], e["weight"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]

    assert (walk_id, walk_id, "calls", "EXTRACTED", 1.0) in calls
    assert (outer_id, walk_id, "calls", "EXTRACTED", 1.0) in calls


def test_python_async_nested_function(tmp_path: Path):
    """Test 6 — Async nested function

    async def outer():
        async def fetch():
            pass
        await fetch()
    """
    f = tmp_path / "test_async.py"
    f.write_text(
        "async def outer():\n"
        "    async def fetch():\n"
        "        pass\n"
        "    await fetch()\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    assert "fetch()" in by_label
    outer_id = by_label["outer()"]["id"]
    fetch_id = by_label["fetch()"]["id"]

    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]
    assert (outer_id, fetch_id, "contains") in edges

    calls = [
        (e["source"], e["target"], e["relation"], e["confidence"], e["weight"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert (outer_id, fetch_id, "calls", "EXTRACTED", 1.0) in calls


def test_python_deep_nesting(tmp_path: Path):
    """Test 7 — Deep nesting

    def outer():
        def middle():
            def inner():
                pass
            inner()
        middle()
    """
    f = tmp_path / "test_deep.py"
    f.write_text(
        "def outer():\n"
        "    def middle():\n"
        "        def inner():\n"
        "            pass\n"
        "        inner()\n"
        "    middle()\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}

    outer_id = by_label["outer()"]["id"]
    middle_id = by_label["middle()"]["id"]
    inner_id = by_label["inner()"]["id"]

    assert middle_id == f"{outer_id}_middle"
    assert inner_id == f"{middle_id}_inner"

    edges = [(e["source"], e["target"], e["relation"]) for e in result["edges"]]
    assert (outer_id, middle_id, "contains") in edges
    assert (middle_id, inner_id, "contains") in edges

    calls = [
        (e["source"], e["target"], e["relation"], e["confidence"], e["weight"])
        for e in result["edges"]
        if e["relation"] == "calls"
    ]
    assert (middle_id, inner_id, "calls", "EXTRACTED", 1.0) in calls
    assert (outer_id, middle_id, "calls", "EXTRACTED", 1.0) in calls


def test_python_local_non_callable_suppression(tmp_path: Path):
    """Test 8 — Local non-callable binding does not become cross-file raw_call

    def outer():
        f = 123
        f()
    """
    f = tmp_path / "test_local_data.py"
    f.write_text(
        "def outer():\n"
        "    f = 123\n"
        "    f()\n"
    )
    result = extract([f], root=tmp_path)
    by_label = {n["label"]: n for n in result["nodes"]}
    outer_id = by_label["outer()"]["id"]

    # f is a local int variable, not a known callable.
    # It must NOT be added to raw_calls!
    raw_calls = result.get("raw_calls", [])
    for rc in raw_calls:
        if rc.get("caller_nid") == outer_id:
            assert rc.get("callee") != "f"
