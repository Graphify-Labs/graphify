"""Regression tests for the performance changes verified by Hermes QA.

Covers:
- _walk_python_tree: iterative pre-order DFS must yield the identical node set
  and order as the previous recursive generator (tree shape preserved).
- _source_key: memoization must not change the resolved key, and repeat calls
  must hit the cache (same result).
"""
from pathlib import Path

import graphify.extractors.resolution as res
from graphify.extractors.resolution import _walk_python_tree


def _simple_node(name="n", children=()):
    class _N:
        def __init__(self, name, children):
            self.name = name
            self.children = tuple(children)

        def __repr__(self):
            return f"<{self.name}>"

    return _N(name, children)


def _walk_recursive(node):
    """Reference: the pre-change recursive generator implementation."""
    yield node
    for child in node.children:
        yield from _walk_recursive(child)


def test_walk_python_tree_pre_order_identical_to_recursive():
    # Build a 3-level tree with a wide middle row.
    leaves = [_simple_node(f"l{i}") for i in range(4)]
    mid = [
        _simple_node("m0", (leaves[0], leaves[1])),
        _simple_node("m1", (leaves[2],)),
        _simple_node("m2", (leaves[3],)),
    ]
    root = _simple_node("root", mid)

    iterative = list(_walk_python_tree(root))
    recursive = list(_walk_recursive(root))

    # Same total node count and same membership.
    assert len(iterative) == len(recursive) == 8
    ids_iter = [n.name for n in iterative]
    ids_rec = [n.name for n in recursive]
    # Pre-order on the given tree: root, m0, l0, l1, m1, l2, m2, l3.
    assert ids_iter == ["root", "m0", "l0", "l1", "m1", "l2", "m2", "l3"]
    assert ids_iter == ids_rec


def test_source_key_memoized_and_stable(tmp_path):
    """reset cache, two distinct source files resolve once; repeat calls identical."""
    res._SOURCE_KEY_CACHE.clear()
    (tmp_path / "a.py").write_text("x = 1")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.py").write_text("y = 2")

    k_a1 = res._source_key(str(tmp_path / "a.py"), tmp_path)
    k_a2 = res._source_key(str(tmp_path / "a.py"), tmp_path)
    k_b = res._source_key(str(tmp_path / "sub" / "b.py"), tmp_path)

    assert k_a1 == k_a2 == "a.py"
    assert k_b == "sub/b.py"
    # Memoization populated the cache.
    assert res._SOURCE_KEY_CACHE.get((str(tmp_path / "a.py"), tmp_path)) == k_a1
    res._SOURCE_KEY_CACHE.clear()