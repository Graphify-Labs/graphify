from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _nodes_by_id(r: dict) -> dict[str, dict]:
    return {n["id"]: n for n in r["nodes"]}


def _edges_by_rel(r: dict, rel: str) -> list[tuple[str, str]]:
    return [(e["source"], e["target"]) for e in r["edges"] if e.get("relation") == rel]


def test_python_same_named_nested_classes_under_different_parents(tmp_path: Path) -> None:
    """#4220: nested classes with identical names in different parent classes
    must mint distinct node IDs qualified by their parent class and must not
    collide or swallow one another."""
    py_file = tmp_path / "scheduler.py"
    py_file.write_text(
        "class Forward:\n"
        "    class Params:\n"
        "        def __init__(self, lr: float):\n"
        "            self.lr = lr\n"
        "\n"
        "class Backward:\n"
        "    class Params:\n"
        "        def __init__(self, clip: float):\n"
        "            self.clip = clip\n",
        encoding="utf-8",
    )
    result = extract([py_file], root=str(tmp_path), cache_root=tmp_path)
    nodes = _nodes_by_id(result)
    contains_edges = _edges_by_rel(result, "contains")
    method_edges = _edges_by_rel(result, "method")

    # Outer classes exist
    assert "scheduler_forward" in nodes
    assert "scheduler_backward" in nodes
    assert ("scheduler", "scheduler_forward") in contains_edges
    assert ("scheduler", "scheduler_backward") in contains_edges

    # Nested classes exist as distinct nodes with their own IDs
    assert "scheduler_forward_params" in nodes
    assert "scheduler_backward_params" in nodes
    assert nodes["scheduler_forward_params"]["label"] == "Params"
    assert nodes["scheduler_backward_params"]["label"] == "Params"

    # Containment edges source from respective enclosing classes
    assert ("scheduler_forward", "scheduler_forward_params") in contains_edges
    assert ("scheduler_backward", "scheduler_backward_params") in contains_edges
    assert ("scheduler", "scheduler_forward_params") not in contains_edges
    assert ("scheduler", "scheduler_backward_params") not in contains_edges

    # Methods attach to their respective nested classes
    assert ("scheduler_forward_params", "scheduler_forward_params_init") in method_edges
    assert ("scheduler_backward_params", "scheduler_backward_params_init") in method_edges


def test_python_deeply_nested_classes(tmp_path: Path) -> None:
    """Deeply nested classes (A.B.C) build hierarchical node IDs."""
    py_file = tmp_path / "tree.py"
    py_file.write_text(
        "class Outer:\n"
        "    class Middle:\n"
        "        class Inner:\n"
        "            def action(self):\n"
        "                pass\n",
        encoding="utf-8",
    )
    result = extract([py_file], root=str(tmp_path), cache_root=tmp_path)
    nodes = _nodes_by_id(result)
    contains = _edges_by_rel(result, "contains")
    methods = _edges_by_rel(result, "method")

    assert "tree_outer" in nodes
    assert "tree_outer_middle" in nodes
    assert "tree_outer_middle_inner" in nodes
    assert ("tree", "tree_outer") in contains
    assert ("tree_outer", "tree_outer_middle") in contains
    assert ("tree_outer_middle", "tree_outer_middle_inner") in contains
    assert ("tree_outer_middle_inner", "tree_outer_middle_inner_action") in methods


def test_python_same_name_recursive_nesting(tmp_path: Path) -> None:
    """Same-named class nesting (class Foo: class Foo) does not collide or create self-loops."""
    py_file = tmp_path / "recursive.py"
    py_file.write_text(
        "class Node:\n"
        "    class Node:\n"
        "        pass\n",
        encoding="utf-8",
    )
    result = extract([py_file], root=str(tmp_path), cache_root=tmp_path)
    nodes = _nodes_by_id(result)
    contains = _edges_by_rel(result, "contains")

    assert "recursive_node" in nodes
    assert "recursive_node_node" in nodes
    assert ("recursive", "recursive_node") in contains
    assert ("recursive_node", "recursive_node_node") in contains
