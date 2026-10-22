import pytest
import networkx as nx
from pathlib import Path
from graphify.heal.engine import (
    FailureTarget,
    extract_blast_radius_subgraph,
    build_healing_prompt,
    extract_code_patch,
    apply_patch_to_file
)

def test_extract_blast_radius_subgraph():
    G = nx.DiGraph()
    G.add_node("router.py", source_file="router.py", label="router", node_type="module")
    G.add_node("auth.py", source_file="auth.py", label="auth", node_type="module")
    G.add_node("test_route", source_file="tests/test_router.py", label="test_route", node_type="function")

    G.add_edge("test_route", "router.py", relation="CALLS")
    G.add_edge("router.py", "auth.py", relation="IMPORTS")

    slice_data = extract_blast_radius_subgraph(G, "router.py", depth=1)

    assert slice_data["focal_file"] == "router.py"
    node_ids = [n["id"] for n in slice_data["nodes"]]
    assert "router.py" in node_ids
    assert "test_route" in node_ids
    assert "auth.py" in node_ids

def test_build_healing_prompt():
    target = FailureTarget("tests/test_foo.py", "test_bar", "AssertionError: 1 != 2")
    graph_context = {
        "nodes": [{"id": "foo", "label": "foo_fn", "type": "function", "file": "foo.py"}],
        "relationships": [{"source": "test_bar", "target": "foo", "relation": "CALLS"}]
    }
    prompt = build_healing_prompt(target, graph_context, "def foo(): return 1")
    assert "test_foo.py::test_bar" in prompt
    assert "AssertionError: 1 != 2" in prompt
    assert "foo_fn" in prompt
    assert "def foo(): return 1" in prompt

def test_extract_code_patch():
    markdown_output = "Here is the fix:\n```python\ndef foo():\n    return 2\n```\nDone."
    clean_code = extract_code_patch(markdown_output)
    assert clean_code == "def foo():\n    return 2\n"

def test_apply_patch_to_file(tmp_path):
    target_file = tmp_path / "broken.py"
    target_file.write_text("def run(): return False\n")
    apply_patch_to_file(target_file, "def run(): return True\n")
    assert target_file.read_text() == "def run(): return True\n"
