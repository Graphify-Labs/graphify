"""_walk_python_tree yields identical preorder, iteratively (#perf).

The recursive ``yield from`` form built one generator frame per tree level and
re-propagated every node up the chain — ~25M frame resumptions on a 364-file
corpus for ~2.8M nodes. The iterative rewrite must yield the exact same nodes
in the exact same preorder; only the frame overhead goes away.
"""

import pytest

tspython = pytest.importorskip("tree_sitter_python")
from tree_sitter import Language, Parser  # noqa: E402

from graphify.extractors.resolution import _walk_python_tree


def _reference_preorder(node):
    """The pre-optimization recursive walk, verbatim."""
    yield node
    for child in node.children:
        yield from _reference_preorder(child)


def _parse(src: str):
    parser = Parser(Language(tspython.language()))
    return parser.parse(src.encode()).root_node


SOURCES = [
    "x = 1\n",
    (
        "import os\n"
        "from a.b import c, d\n\n"
        "class Foo(Base):\n"
        "    attr: int = 0\n"
        "    def method(self, x):\n"
        "        def inner():\n"
        "            return [i for i in range(x) if i % 2]\n"
        "        return inner()\n\n"
        "async def bar():\n"
        "    async with ctx() as c:\n"
        "        await c.run(lambda z: z + 1)\n"
    ),
    "",  # empty module
]


@pytest.mark.parametrize("src", SOURCES)
def test_matches_recursive_preorder(src):
    root = _parse(src)
    got = list(_walk_python_tree(root))
    expected = list(_reference_preorder(root))
    # Identity, not just equality: same node objects, same order.
    assert [id(n) for n in got] == [id(n) for n in expected]


def test_visits_every_node_once():
    root = _parse(SOURCES[1])
    got = list(_walk_python_tree(root))
    assert len(got) == len(set(id(n) for n in got))
    assert got[0] is root  # preorder: root first


def test_deeply_nested_does_not_recurse():
    """A pathologically deep tree that would overflow the recursion limit for
    the old form walks fine iteratively."""
    depth = 2000
    src = "x = " + "(" * depth + "1" + ")" * depth + "\n"
    root = _parse(src)
    count = sum(1 for _ in _walk_python_tree(root))
    assert count > depth
