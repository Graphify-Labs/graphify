import pytest
import networkx as nx
from pathlib import Path
from graphify.heal.engine import (
    FailureTarget,
    extract_blast_radius_subgraph,
    resolve_remediation_target,
    build_healing_prompt,
    extract_code_patch,
    apply_patch_to_file,
    execute_and_capture_test_failure
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

def test_resolve_remediation_target_prefers_implementation(tmp_path):
    impl_file = tmp_path / "service.py"
    impl_file.write_text("def run(): pass\n")
    test_file = tmp_path / "test_service.py"
    test_file.write_text("def test_run(): pass\n")

    fail = FailureTarget(str(test_file), "test_run", "AssertionError")
    blast_slice = {
        "nodes": [
            {"id": "service", "file": str(impl_file), "type": "module"},
            {"id": "test_service", "file": str(test_file), "type": "module"}
        ]
    }
    target = resolve_remediation_target(fail, blast_slice)
    assert target == impl_file

def test_build_healing_prompt():
    target = FailureTarget("tests/test_foo.py", "test_bar", "AssertionError: 1 != 2")
    graph_context = {
        "nodes": [{"id": "foo", "label": "foo_fn", "type": "function", "file": "foo.py"}],
        "relationships": [{"source": "test_bar", "target": "foo", "relation": "CALLS"}]
    }
    prompt = build_healing_prompt(target, graph_context, "def foo(): return 1", "foo.py")
    assert "test_foo.py::test_bar" in prompt
    assert "AssertionError: 1 != 2" in prompt
    assert "foo_fn" in prompt
    assert "def foo(): return 1" in prompt

def test_extract_code_patch_valid():
    markdown_output = "Here is the fix:\n```python\ndef foo():\n    return 2\n```\nDone."
    clean_code = extract_code_patch(markdown_output)
    assert clean_code == "def foo():\n    return 2\n"

def test_extract_code_patch_rejects_raw_prose():
    with pytest.raises(ValueError, match="did not contain a valid code block"):
        extract_code_patch("I cannot solve this issue without more information.")

def test_apply_patch_to_file(tmp_path):
    target_file = tmp_path / "broken.py"
    target_file.write_text("def run(): return False\n")
    apply_patch_to_file(target_file, "def run(): return True\n")
    assert target_file.read_text() == "def run(): return True\n"

def test_non_zero_exit_with_unparseable_output_caught():
    failures = execute_and_capture_test_failure("python3 -c 'import sys; sys.exit(2)'")
    assert len(failures) == 1
    assert failures[0].test_node == "execution_error"
