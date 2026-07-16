import random
from itertools import product
from textwrap import dedent

import pytest

import networkx as nx


def test_generate_network_text_forest_directed():
    # Create a directed forest with labels
    graph = nx.balanced_tree(r=2, h=2, create_using=nx.DiGraph)
    for node in graph.nodes:
        graph.nodes[node]["label"] = "node_" + chr(ord("a") + node)

    node_target = dedent(
        """
        ╙── 0
            ├─╼ 1
            │   ├─╼ 3
            │   └─╼ 4
            └─╼ 2
                ├─╼ 5
                └─╼ 6
        """
    ).strip()

    label_target = dedent(
        """
        ╙── node_a
            ├─╼ node_b
            │   ├─╼ node_d
            │   └─╼ node_e
            └─╼ node_c
                ├─╼ node_f
                └─╼ node_g
        """
    ).strip()

    # Basic node case
    ret = nx.generate_network_text(graph, with_labels=False)
    assert "\n".join(ret) == node_target

    # Basic label case
    ret = nx.generate_network_text(graph, with_labels=True)
    assert "\n".join(ret) == label_target


def test_write_network_text_empty_graph():
    def _graph_str(g, **kw):
        printbuf = []
        nx.write_network_text(g, printbuf.append, end="", **kw)
        return "\n".join(printbuf)

    assert _graph_str(nx.DiGraph()) == "╙"
    assert _graph_str(nx.Graph()) == "╙"
    assert _graph_str(nx.DiGraph(), ascii_only=True) == "+"
    assert _graph_str(nx.Graph(), ascii_only=True) == "+"


def test_write_network_text_within_forest_glyph():
    g = nx.DiGraph()
    g.add_nodes_from([1, 2, 3, 4])
    g.add_edge(2, 4)
    lines = []
    write = lines.append
    nx.write_network_text(g, path=write, end="")
    nx.write_network_text(g, path=write, ascii_only=True, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╟── 1
        ╟── 2
        ╎   └─╼ 4
        ╙── 3
        +-- 1
        +-- 2
        :   L-> 4
        +-- 3
        """
    ).strip()
    assert text == target


def test_generate_network_text_directed_multi_tree():
    tree1 = nx.balanced_tree(r=2, h=2, create_using=nx.DiGraph)
    tree2 = nx.balanced_tree(r=2, h=2, create_using=nx.DiGraph)
    forest = nx.disjoint_union_all([tree1, tree2])
    ret = "\n".join(nx.generate_network_text(forest))

    target = dedent(
        """
        ╟── 0
        ╎   ├─╼ 1
        ╎   │   ├─╼ 3
        ╎   │   └─╼ 4
        ╎   └─╼ 2
        ╎       ├─╼ 5
        ╎       └─╼ 6
        ╙── 7
            ├─╼ 8
            │   ├─╼ 10
            │   └─╼ 11
            └─╼ 9
                ├─╼ 12
                └─╼ 13
        """
    ).strip()
    assert ret == target

    tree3 = nx.balanced_tree(r=2, h=2, create_using=nx.DiGraph)
    forest = nx.disjoint_union_all([tree1, tree2, tree3])
    ret = "\n".join(nx.generate_network_text(forest, sources=[0, 14, 7]))

    target = dedent(
        """
        ╟── 0
        ╎   ├─╼ 1
        ╎   │   ├─╼ 3
        ╎   │   └─╼ 4
        ╎   └─╼ 2
        ╎       ├─╼ 5
        ╎       └─╼ 6
        ╟── 14
        ╎   ├─╼ 15
        ╎   │   ├─╼ 17
        ╎   │   └─╼ 18
        ╎   └─╼ 16
        ╎       ├─╼ 19
        ╎       └─╼ 20
        ╙── 7
            ├─╼ 8
            │   ├─╼ 10
            │   └─╼ 11
            └─╼ 9
                ├─╼ 12
                └─╼ 13
        """
    ).strip()
    assert ret == target

    ret = "\n".join(
        nx.generate_network_text(forest, sources=[0, 14, 7], ascii_only=True)
    )

    target = dedent(
        """
        +-- 0
        :   |-> 1
        :   |   |-> 3
        :   |   L-> 4
        :   L-> 2
        :       |-> 5
        :       L-> 6
        +-- 14
        :   |-> 15
        :   |   |-> 17
        :   |   L-> 18
        :   L-> 16
        :       |-> 19
        :       L-> 20
        +-- 7
            |-> 8
            |   |-> 10
            |   L-> 11
            L-> 9
                |-> 12
                L-> 13
        """
    ).strip()
    assert ret == target


def test_generate_network_text_undirected_multi_tree():
    tree1 = nx.balanced_tree(r=2, h=2, create_using=nx.Graph)
    tree2 = nx.balanced_tree(r=2, h=2, create_using=nx.Graph)
    tree2 = nx.relabel_nodes(tree2, {n: n + len(tree1) for n in tree2.nodes})
    forest = nx.union(tree1, tree2)
    ret = "\n".join(nx.generate_network_text(forest, sources=[0, 7]))

    target = dedent(
        """
        ╟── 0
        ╎   ├── 1
        ╎   │   ├── 3
        ╎   │   └── 4
        ╎   └── 2
        ╎       ├── 5
        ╎       └── 6
        ╙── 7
            ├── 8
            │   ├── 10
            │   └── 11
            └── 9
                ├── 12
                └── 13
        """
    ).strip()
    assert ret == target

    ret = "\n".join(nx.generate_network_text(forest, sources=[0, 7], ascii_only=True))

    target = dedent(
        """
        +-- 0
        :   |-- 1
        :   |   |-- 3
        :   |   L-- 4
        :   L-- 2
        :       |-- 5
        :       L-- 6
        +-- 7
            |-- 8
            |   |-- 10
            |   L-- 11
            L-- 9
                |-- 12
                L-- 13
        """
    ).strip()
    assert ret == target


def test_generate_network_text_forest_undirected():
    # Create a directed forest
    graph = nx.balanced_tree(r=2, h=2, create_using=nx.Graph)

    node_target0 = dedent(
        """
        ╙── 0
            ├── 1
            │   ├── 3
            │   └── 4
            └── 2
                ├── 5
                └── 6
        """
    ).strip()

    # defined starting point
    ret = "\n".join(nx.generate_network_text(graph, sources=[0]))
    assert ret == node_target0

    # defined starting point
    node_target2 = dedent(
        """
        ╙── 2
            ├── 0
            │   └── 1
            │       ├── 3
            │       └── 4
            ├── 5
            └── 6
        """
    ).strip()
    ret = "\n".join(nx.generate_network_text(graph, sources=[2]))
    assert ret == node_target2


def test_generate_network_text_overspecified_sources():
    """
    When sources are directly specified, we won't be able to determine when we
    are in the last component, so there will always be a trailing, leftmost
    pipe.
    """
    graph = nx.disjoint_union_all(
        [
            nx.balanced_tree(r=2, h=1, create_using=nx.DiGraph),
            nx.balanced_tree(r=1, h=2, create_using=nx.DiGraph),
            nx.balanced_tree(r=2, h=1, create_using=nx.DiGraph),
        ]
    )

    # defined starting point
    target1 = dedent(
        """
        ╟── 0
        ╎   ├─╼ 1
        ╎   └─╼ 2
        ╟── 3
        ╎   └─╼ 4
        ╎       └─╼ 5
        ╟── 6
        ╎   ├─╼ 7
        ╎   └─╼ 8
        """
    ).strip()

    target2 = dedent(
        """
        ╟── 0
        ╎   ├─╼ 1
        ╎   └─╼ 2
        ╟── 3
        ╎   └─╼ 4
        ╎       └─╼ 5
        ╙── 6
            ├─╼ 7
            └─╼ 8
        """
    ).strip()

    got1 = "\n".join(nx.generate_network_text(graph, sources=graph.nodes))
    got2 = "\n".join(nx.generate_network_text(graph))
    assert got1 == target1
    assert got2 == target2


def test_write_network_text_iterative_add_directed_edges():
    """
    Walk through the cases going from a disconnected to fully connected graph
    """
    graph = nx.DiGraph()
    graph.add_nodes_from([1, 2, 3, 4])
    lines = []
    write = lines.append
    write("--- initial state ---")
    nx.write_network_text(graph, path=write, end="")
    for i, j in product(graph.nodes, graph.nodes):
        write(f"--- add_edge({i}, {j}) ---")
        graph.add_edge(i, j)
        nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    # defined starting point
    target = dedent(
        """
        --- initial state ---
        ╟── 1
        ╟── 2
        ╟── 3
        ╙── 4
        --- add_edge(1, 1) ---
        ╟── 1 ╾ 1
        ╎   └─╼  ...
        ╟── 2
        ╟── 3
        ╙── 4
        --- add_edge(1, 2) ---
        ╟── 1 ╾ 1
        ╎   ├─╼ 2
        ╎   └─╼  ...
        ╟── 3
        ╙── 4
        --- add_edge(1, 3) ---
        ╟── 1 ╾ 1
        ╎   ├─╼ 2
        ╎   ├─╼ 3
        ╎   └─╼  ...
        ╙── 4
        --- add_edge(1, 4) ---
        ╙── 1 ╾ 1
            ├─╼ 2
            ├─╼ 3
            ├─╼ 4
            └─╼  ...
        --- add_edge(2, 1) ---
        ╙── 2 ╾ 1
            └─╼ 1 ╾ 1
                ├─╼ 3
                ├─╼ 4
                └─╼  ...
        --- add_edge(2, 2) ---
        ╙── 1 ╾ 1, 2
            ├─╼ 2 ╾ 2
            │   └─╼  ...
            ├─╼ 3
            ├─╼ 4
            └─╼  ...
        --- add_edge(2, 3) ---
        ╙── 1 ╾ 1, 2
            ├─╼ 2 ╾ 2
            │   ├─╼ 3 ╾ 1
            │   └─╼  ...
            ├─╼ 4
            └─╼  ...
        --- add_edge(2, 4) ---
        ╙── 1 ╾ 1, 2
            ├─╼ 2 ╾ 2
            │   ├─╼ 3 ╾ 1
            │   ├─╼ 4 ╾ 1
            │   └─╼  ...
            └─╼  ...
        --- add_edge(3, 1) ---
        ╙── 2 ╾ 1, 2
            ├─╼ 1 ╾ 1, 3
            │   ├─╼ 3 ╾ 2
            │   │   └─╼  ...
            │   ├─╼ 4 ╾ 2
            │   └─╼  ...
            └─╼  ...
        --- add_edge(3, 2) ---
        ╙── 3 ╾ 1, 2
            ├─╼ 1 ╾ 1, 2
            │   ├─╼ 2 ╾ 2, 3
            │   │   ├─╼ 4 ╾ 1
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- add_edge(3, 3) ---
        ╙── 1 ╾ 1, 2, 3
            ├─╼ 2 ╾ 2, 3
            │   ├─╼ 3 ╾ 1, 3
            │   │   └─╼  ...
            │   ├─╼ 4 ╾ 1
            │   └─╼  ...
            └─╼  ...
        --- add_edge(3, 4) ---
        ╙── 1 ╾ 1, 2, 3
            ├─╼ 2 ╾ 2, 3
            │   ├─╼ 3 ╾ 1, 3
            │   │   ├─╼ 4 ╾ 1, 2
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- add_edge(4, 1) ---
        ╙── 2 ╾ 1, 2, 3
            ├─╼ 1 ╾ 1, 3, 4
            │   ├─╼ 3 ╾ 2, 3
            │   │   ├─╼ 4 ╾ 1, 2
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- add_edge(4, 2) ---
        ╙── 3 ╾ 1, 2, 3
            ├─╼ 1 ╾ 1, 2, 4
            │   ├─╼ 2 ╾ 2, 3, 4
            │   │   ├─╼ 4 ╾ 1, 3
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- add_edge(4, 3) ---
        ╙── 4 ╾ 1, 2, 3
            ├─╼ 1 ╾ 1, 2, 3
            │   ├─╼ 2 ╾ 2, 3, 4
            │   │   ├─╼ 3 ╾ 1, 3, 4
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- add_edge(4, 4) ---
        ╙── 1 ╾ 1, 2, 3, 4
            ├─╼ 2 ╾ 2, 3, 4
            │   ├─╼ 3 ╾ 1, 3, 4
            │   │   ├─╼ 4 ╾ 1, 2, 4
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_iterative_add_undirected_edges():
    """
    Walk through the cases going from a disconnected to fully connected graph
    """
    graph = nx.Graph()
    graph.add_nodes_from([1, 2, 3, 4])
    lines = []
    write = lines.append
    write("--- initial state ---")
    nx.write_network_text(graph, path=write, end="")
    for i, j in product(graph.nodes, graph.nodes):
        if i == j:
            continue
        write(f"--- add_edge({i}, {j}) ---")
        graph.add_edge(i, j)
        nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- initial state ---
        ╟── 1
        ╟── 2
        ╟── 3
        ╙── 4
        --- add_edge(1, 2) ---
        ╟── 3
        ╟── 4
        ╙── 1
            └── 2
        --- add_edge(1, 3) ---
        ╟── 4
        ╙── 2
            └── 1
                └── 3
        --- add_edge(1, 4) ---
        ╙── 2
            └── 1
                ├── 3
                └── 4
        --- add_edge(2, 1) ---
        ╙── 2
            └── 1
                ├── 3
                └── 4
        --- add_edge(2, 3) ---
        ╙── 4
            └── 1
                ├── 2
                │   └── 3 ─ 1
                └──  ...
        --- add_edge(2, 4) ---
        ╙── 3
            ├── 1
            │   ├── 2 ─ 3
            │   │   └── 4 ─ 1
            │   └──  ...
            └──  ...
        --- add_edge(3, 1) ---
        ╙── 3
            ├── 1
            │   ├── 2 ─ 3
            │   │   └── 4 ─ 1
            │   └──  ...
            └──  ...
        --- add_edge(3, 2) ---
        ╙── 3
            ├── 1
            │   ├── 2 ─ 3
            │   │   └── 4 ─ 1
            │   └──  ...
            └──  ...
        --- add_edge(3, 4) ---
        ╙── 1
            ├── 2
            │   ├── 3 ─ 1
            │   │   └── 4 ─ 1, 2
            │   └──  ...
            └──  ...
        --- add_edge(4, 1) ---
        ╙── 1
            ├── 2
            │   ├── 3 ─ 1
            │   │   └── 4 ─ 1, 2
            │   └──  ...
            └──  ...
        --- add_edge(4, 2) ---
        ╙── 1
            ├── 2
            │   ├── 3 ─ 1
            │   │   └── 4 ─ 1, 2
            │   └──  ...
            └──  ...
        --- add_edge(4, 3) ---
        ╙── 1
            ├── 2
            │   ├── 3 ─ 1
            │   │   └── 4 ─ 1, 2
            │   └──  ...
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_iterative_add_random_directed_edges():
    """
    Walk through the cases going from a disconnected to fully connected graph
    """

    rng = random.Random(724466096)
    graph = nx.DiGraph()
    graph.add_nodes_from([1, 2, 3, 4, 5])
    possible_edges = list(product(graph.nodes, graph.nodes))
    rng.shuffle(possible_edges)
    graph.add_edges_from(possible_edges[0:8])
    lines = []
    write = lines.append
    write("--- initial state ---")
    nx.write_network_text(graph, path=write, end="")
    for i, j in possible_edges[8:12]:
        write(f"--- add_edge({i}, {j}) ---")
        graph.add_edge(i, j)
        nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- initial state ---
        ╙── 3 ╾ 5
            └─╼ 2 ╾ 2
                ├─╼ 4 ╾ 4
                │   ├─╼ 5
                │   │   ├─╼ 1 ╾ 1
                │   │   │   └─╼  ...
                │   │   └─╼  ...
                │   └─╼  ...
                └─╼  ...
        --- add_edge(4, 1) ---
        ╙── 3 ╾ 5
            └─╼ 2 ╾ 2
                ├─╼ 4 ╾ 4
                │   ├─╼ 5
                │   │   ├─╼ 1 ╾ 1, 4
                │   │   │   └─╼  ...
                │   │   └─╼  ...
                │   └─╼  ...
                └─╼  ...
        --- add_edge(2, 1) ---
        ╙── 3 ╾ 5
            └─╼ 2 ╾ 2
                ├─╼ 4 ╾ 4
                │   ├─╼ 5
                │   │   ├─╼ 1 ╾ 1, 4, 2
                │   │   │   └─╼  ...
                │   │   └─╼  ...
                │   └─╼  ...
                └─╼  ...
        --- add_edge(5, 2) ---
        ╙── 3 ╾ 5
            └─╼ 2 ╾ 2, 5
                ├─╼ 4 ╾ 4
                │   ├─╼ 5
                │   │   ├─╼ 1 ╾ 1, 4, 2
                │   │   │   └─╼  ...
                │   │   └─╼  ...
                │   └─╼  ...
                └─╼  ...
        --- add_edge(1, 5) ---
        ╙── 3 ╾ 5
            └─╼ 2 ╾ 2, 5
                ├─╼ 4 ╾ 4
                │   ├─╼ 5 ╾ 1
                │   │   ├─╼ 1 ╾ 1, 4, 2
                │   │   │   └─╼  ...
                │   │   └─╼  ...
                │   └─╼  ...
                └─╼  ...

        """
    ).strip()
    assert target == text


def test_write_network_text_nearly_forest():
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(1, 5)
    g.add_edge(2, 3)
    g.add_edge(3, 4)
    g.add_edge(5, 6)
    g.add_edge(6, 7)
    g.add_edge(6, 8)
    orig = g.copy()
    g.add_edge(1, 8)  # forward edge
    g.add_edge(4, 2)  # back edge
    g.add_edge(6, 3)  # cross edge
    lines = []
    write = lines.append
    write("--- directed case ---")
    nx.write_network_text(orig, path=write, end="")
    write("--- add (1, 8), (4, 2), (6, 3) ---")
    nx.write_network_text(g, path=write, end="")
    write("--- undirected case ---")
    nx.write_network_text(orig.to_undirected(), path=write, sources=[1], end="")
    write("--- add (1, 8), (4, 2), (6, 3) ---")
    nx.write_network_text(g.to_undirected(), path=write, sources=[1], end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- directed case ---
        ╙── 1
            ├─╼ 2
            │   └─╼ 3
            │       └─╼ 4
            └─╼ 5
                └─╼ 6
                    ├─╼ 7
                    └─╼ 8
        --- add (1, 8), (4, 2), (6, 3) ---
        ╙── 1
            ├─╼ 2 ╾ 4
            │   └─╼ 3 ╾ 6
            │       └─╼ 4
            │           └─╼  ...
            ├─╼ 5
            │   └─╼ 6
            │       ├─╼ 7
            │       ├─╼ 8 ╾ 1
            │       └─╼  ...
            └─╼  ...
        --- undirected case ---
        ╙── 1
            ├── 2
            │   └── 3
            │       └── 4
            └── 5
                └── 6
                    ├── 7
                    └── 8
        --- add (1, 8), (4, 2), (6, 3) ---
        ╙── 1
            ├── 2
            │   ├── 3
            │   │   ├── 4 ─ 2
            │   │   └── 6
            │   │       ├── 5 ─ 1
            │   │       ├── 7
            │   │       └── 8 ─ 1
            │   └──  ...
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_complete_graph_ascii_only():
    graph = nx.generators.complete_graph(5, create_using=nx.DiGraph)
    lines = []
    write = lines.append
    write("--- directed case ---")
    nx.write_network_text(graph, path=write, ascii_only=True, end="")
    write("--- undirected case ---")
    nx.write_network_text(graph.to_undirected(), path=write, ascii_only=True, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- directed case ---
        +-- 0 <- 1, 2, 3, 4
            |-> 1 <- 2, 3, 4
            |   |-> 2 <- 0, 3, 4
            |   |   |-> 3 <- 0, 1, 4
            |   |   |   |-> 4 <- 0, 1, 2
            |   |   |   |   L->  ...
            |   |   |   L->  ...
            |   |   L->  ...
            |   L->  ...
            L->  ...
        --- undirected case ---
        +-- 0
            |-- 1
            |   |-- 2 - 0
            |   |   |-- 3 - 0, 1
            |   |   |   L-- 4 - 0, 1, 2
            |   |   L--  ...
            |   L--  ...
            L--  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_with_labels():
    graph = nx.generators.complete_graph(5, create_using=nx.DiGraph)
    for n in graph.nodes:
        graph.nodes[n]["label"] = f"Node(n={n})"
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, with_labels=True, ascii_only=False, end="")
    text = "\n".join(lines)
    # Non trees with labels can get somewhat out of hand with network text
    # because we need to immediately show every non-tree edge to the right
    target = dedent(
        """
        ╙── Node(n=0) ╾ Node(n=1), Node(n=2), Node(n=3), Node(n=4)
            ├─╼ Node(n=1) ╾ Node(n=2), Node(n=3), Node(n=4)
            │   ├─╼ Node(n=2) ╾ Node(n=0), Node(n=3), Node(n=4)
            │   │   ├─╼ Node(n=3) ╾ Node(n=0), Node(n=1), Node(n=4)
            │   │   │   ├─╼ Node(n=4) ╾ Node(n=0), Node(n=1), Node(n=2)
            │   │   │   │   └─╼  ...
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_complete_graphs():
    lines = []
    write = lines.append
    for k in [0, 1, 2, 3, 4, 5]:
        g = nx.generators.complete_graph(k)
        write(f"--- undirected k={k} ---")
        nx.write_network_text(g, path=write, end="")

    for k in [0, 1, 2, 3, 4, 5]:
        g = nx.generators.complete_graph(k, nx.DiGraph)
        write(f"--- directed k={k} ---")
        nx.write_network_text(g, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- undirected k=0 ---
        ╙
        --- undirected k=1 ---
        ╙── 0
        --- undirected k=2 ---
        ╙── 0
            └── 1
        --- undirected k=3 ---
        ╙── 0
            ├── 1
            │   └── 2 ─ 0
            └──  ...
        --- undirected k=4 ---
        ╙── 0
            ├── 1
            │   ├── 2 ─ 0
            │   │   └── 3 ─ 0, 1
            │   └──  ...
            └──  ...
        --- undirected k=5 ---
        ╙── 0
            ├── 1
            │   ├── 2 ─ 0
            │   │   ├── 3 ─ 0, 1
            │   │   │   └── 4 ─ 0, 1, 2
            │   │   └──  ...
            │   └──  ...
            └──  ...
        --- directed k=0 ---
        ╙
        --- directed k=1 ---
        ╙── 0
        --- directed k=2 ---
        ╙── 0 ╾ 1
            └─╼ 1
                └─╼  ...
        --- directed k=3 ---
        ╙── 0 ╾ 1, 2
            ├─╼ 1 ╾ 2
            │   ├─╼ 2 ╾ 0
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- directed k=4 ---
        ╙── 0 ╾ 1, 2, 3
            ├─╼ 1 ╾ 2, 3
            │   ├─╼ 2 ╾ 0, 3
            │   │   ├─╼ 3 ╾ 0, 1
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- directed k=5 ---
        ╙── 0 ╾ 1, 2, 3, 4
            ├─╼ 1 ╾ 2, 3, 4
            │   ├─╼ 2 ╾ 0, 3, 4
            │   │   ├─╼ 3 ╾ 0, 1, 4
            │   │   │   ├─╼ 4 ╾ 0, 1, 2
            │   │   │   │   └─╼  ...
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_multiple_sources():
    g = nx.DiGraph()
    g.add_edge(1, 2)
    g.add_edge(1, 3)
    g.add_edge(2, 4)
    g.add_edge(3, 5)
    g.add_edge(3, 6)
    g.add_edge(5, 4)
    g.add_edge(4, 1)
    g.add_edge(1, 5)
    lines = []
    write = lines.append
    # Use each node as the starting point to demonstrate how the representation
    # changes.
    nodes = sorted(g.nodes())
    for n in nodes:
        write(f"--- source node: {n} ---")
        nx.write_network_text(g, path=write, sources=[n], end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- source node: 1 ---
        ╙── 1 ╾ 4
            ├─╼ 2
            │   └─╼ 4 ╾ 5
            │       └─╼  ...
            ├─╼ 3
            │   ├─╼ 5 ╾ 1
            │   │   └─╼  ...
            │   └─╼ 6
            └─╼  ...
        --- source node: 2 ---
        ╙── 2 ╾ 1
            └─╼ 4 ╾ 5
                └─╼ 1
                    ├─╼ 3
                    │   ├─╼ 5 ╾ 1
                    │   │   └─╼  ...
                    │   └─╼ 6
                    └─╼  ...
        --- source node: 3 ---
        ╙── 3 ╾ 1
            ├─╼ 5 ╾ 1
            │   └─╼ 4 ╾ 2
            │       └─╼ 1
            │           ├─╼ 2
            │           │   └─╼  ...
            │           └─╼  ...
            └─╼ 6
        --- source node: 4 ---
        ╙── 4 ╾ 2, 5
            └─╼ 1
                ├─╼ 2
                │   └─╼  ...
                ├─╼ 3
                │   ├─╼ 5 ╾ 1
                │   │   └─╼  ...
                │   └─╼ 6
                └─╼  ...
        --- source node: 5 ---
        ╙── 5 ╾ 3, 1
            └─╼ 4 ╾ 2
                └─╼ 1
                    ├─╼ 2
                    │   └─╼  ...
                    ├─╼ 3
                    │   ├─╼ 6
                    │   └─╼  ...
                    └─╼  ...
        --- source node: 6 ---
        ╙── 6 ╾ 3
        """
    ).strip()
    assert target == text


def test_write_network_text_star_graph():
    graph = nx.star_graph(5, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 1
            └── 0
                ├── 2
                ├── 3
                ├── 4
                └── 5
        """
    ).strip()
    assert target == text


def test_write_network_text_path_graph():
    graph = nx.path_graph(3, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 0
            └── 1
                └── 2
        """
    ).strip()
    assert target == text


def test_write_network_text_lollipop_graph():
    graph = nx.lollipop_graph(4, 2, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 5
            └── 4
                └── 3
                    ├── 0
                    │   ├── 1 ─ 3
                    │   │   └── 2 ─ 0, 3
                    │   └──  ...
                    └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_wheel_graph():
    graph = nx.wheel_graph(7, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 1
            ├── 0
            │   ├── 2 ─ 1
            │   │   └── 3 ─ 0
            │   │       └── 4 ─ 0
            │   │           └── 5 ─ 0
            │   │               └── 6 ─ 0, 1
            │   └──  ...
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_circular_ladder_graph():
    graph = nx.circular_ladder_graph(4, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 0
            ├── 1
            │   ├── 2
            │   │   ├── 3 ─ 0
            │   │   │   └── 7
            │   │   │       ├── 6 ─ 2
            │   │   │       │   └── 5 ─ 1
            │   │   │       │       └── 4 ─ 0, 7
            │   │   │       └──  ...
            │   │   └──  ...
            │   └──  ...
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_dorogovtsev_goltsev_mendes_graph():
    graph = nx.dorogovtsev_goltsev_mendes_graph(4, create_using=nx.Graph)
    lines = []
    write = lines.append
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        ╙── 15
            ├── 0
            │   ├── 1 ─ 15
            │   │   ├── 2 ─ 0
            │   │   │   ├── 4 ─ 0
            │   │   │   │   ├── 9 ─ 0
            │   │   │   │   │   ├── 22 ─ 0
            │   │   │   │   │   └── 38 ─ 4
            │   │   │   │   ├── 13 ─ 2
            │   │   │   │   │   ├── 34 ─ 2
            │   │   │   │   │   └── 39 ─ 4
            │   │   │   │   ├── 18 ─ 0
            │   │   │   │   ├── 30 ─ 2
            │   │   │   │   └──  ...
            │   │   │   ├── 5 ─ 1
            │   │   │   │   ├── 12 ─ 1
            │   │   │   │   │   ├── 29 ─ 1
            │   │   │   │   │   └── 40 ─ 5
            │   │   │   │   ├── 14 ─ 2
            │   │   │   │   │   ├── 35 ─ 2
            │   │   │   │   │   └── 41 ─ 5
            │   │   │   │   ├── 25 ─ 1
            │   │   │   │   ├── 31 ─ 2
            │   │   │   │   └──  ...
            │   │   │   ├── 7 ─ 0
            │   │   │   │   ├── 20 ─ 0
            │   │   │   │   └── 32 ─ 2
            │   │   │   ├── 10 ─ 1
            │   │   │   │   ├── 27 ─ 1
            │   │   │   │   └── 33 ─ 2
            │   │   │   ├── 16 ─ 0
            │   │   │   ├── 23 ─ 1
            │   │   │   └──  ...
            │   │   ├── 3 ─ 0
            │   │   │   ├── 8 ─ 0
            │   │   │   │   ├── 21 ─ 0
            │   │   │   │   └── 36 ─ 3
            │   │   │   ├── 11 ─ 1
            │   │   │   │   ├── 28 ─ 1
            │   │   │   │   └── 37 ─ 3
            │   │   │   ├── 17 ─ 0
            │   │   │   ├── 24 ─ 1
            │   │   │   └──  ...
            │   │   ├── 6 ─ 0
            │   │   │   ├── 19 ─ 0
            │   │   │   └── 26 ─ 1
            │   │   └──  ...
            │   └──  ...
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_tree_max_depth():
    orig = nx.balanced_tree(r=1, h=3, create_using=nx.DiGraph)
    lines = []
    write = lines.append
    write("--- directed case, max_depth=0 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=0)
    write("--- directed case, max_depth=1 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=1)
    write("--- directed case, max_depth=2 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=2)
    write("--- directed case, max_depth=3 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=3)
    write("--- directed case, max_depth=4 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=4)
    write("--- undirected case, max_depth=0 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=0)
    write("--- undirected case, max_depth=1 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=1)
    write("--- undirected case, max_depth=2 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=2)
    write("--- undirected case, max_depth=3 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=3)
    write("--- undirected case, max_depth=4 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=4)
    text = "\n".join(lines)
    target = dedent(
        """
        --- directed case, max_depth=0 ---
        ╙ ...
        --- directed case, max_depth=1 ---
        ╙── 0
            └─╼  ...
        --- directed case, max_depth=2 ---
        ╙── 0
            └─╼ 1
                └─╼  ...
        --- directed case, max_depth=3 ---
        ╙── 0
            └─╼ 1
                └─╼ 2
                    └─╼  ...
        --- directed case, max_depth=4 ---
        ╙── 0
            └─╼ 1
                └─╼ 2
                    └─╼ 3
        --- undirected case, max_depth=0 ---
        ╙ ...
        --- undirected case, max_depth=1 ---
        ╙── 0 ─ 1
            └──  ...
        --- undirected case, max_depth=2 ---
        ╙── 0
            └── 1 ─ 2
                └──  ...
        --- undirected case, max_depth=3 ---
        ╙── 0
            └── 1
                └── 2 ─ 3
                    └──  ...
        --- undirected case, max_depth=4 ---
        ╙── 0
            └── 1
                └── 2
                    └── 3
        """
    ).strip()
    assert target == text


def test_write_network_text_graph_max_depth():
    orig = nx.erdos_renyi_graph(10, 0.15, directed=True, seed=40392)
    lines = []
    write = lines.append
    write("--- directed case, max_depth=None ---")
    nx.write_network_text(orig, path=write, end="", max_depth=None)
    write("--- directed case, max_depth=0 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=0)
    write("--- directed case, max_depth=1 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=1)
    write("--- directed case, max_depth=2 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=2)
    write("--- directed case, max_depth=3 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=3)
    write("--- undirected case, max_depth=None ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=None)
    write("--- undirected case, max_depth=0 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=0)
    write("--- undirected case, max_depth=1 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=1)
    write("--- undirected case, max_depth=2 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=2)
    write("--- undirected case, max_depth=3 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=3)
    text = "\n".join(lines)
    target = dedent(
        """
        --- directed case, max_depth=None ---
        ╟── 4
        ╎   ├─╼ 0 ╾ 3
        ╎   ├─╼ 5 ╾ 7
        ╎   │   └─╼ 3
        ╎   │       ├─╼ 1 ╾ 9
        ╎   │       │   └─╼ 9 ╾ 6
        ╎   │       │       ├─╼ 6
        ╎   │       │       │   └─╼  ...
        ╎   │       │       ├─╼ 7 ╾ 4
        ╎   │       │       │   ├─╼ 2
        ╎   │       │       │   └─╼  ...
        ╎   │       │       └─╼  ...
        ╎   │       └─╼  ...
        ╎   └─╼  ...
        ╙── 8
        --- directed case, max_depth=0 ---
        ╙ ...
        --- directed case, max_depth=1 ---
        ╟── 4
        ╎   └─╼  ...
        ╙── 8
        --- directed case, max_depth=2 ---
        ╟── 4
        ╎   ├─╼ 0 ╾ 3
        ╎   ├─╼ 5 ╾ 7
        ╎   │   └─╼  ...
        ╎   └─╼ 7 ╾ 9
        ╎       └─╼  ...
        ╙── 8
        --- directed case, max_depth=3 ---
        ╟── 4
        ╎   ├─╼ 0 ╾ 3
        ╎   ├─╼ 5 ╾ 7
        ╎   │   └─╼ 3
        ╎   │       └─╼  ...
        ╎   └─╼ 7 ╾ 9
        ╎       ├─╼ 2
        ╎       └─╼  ...
        ╙── 8
        --- undirected case, max_depth=None ---
        ╟── 8
        ╙── 2
            └── 7
                ├── 4
                │   ├── 0
                │   │   └── 3
                │   │       ├── 1
                │   │       │   └── 9 ─ 7
                │   │       │       └── 6
                │   │       └── 5 ─ 4, 7
                │   └──  ...
                └──  ...
        --- undirected case, max_depth=0 ---
        ╙ ...
        --- undirected case, max_depth=1 ---
        ╟── 8
        ╙── 2 ─ 7
            └──  ...
        --- undirected case, max_depth=2 ---
        ╟── 8
        ╙── 2
            └── 7 ─ 4, 5, 9
                └──  ...
        --- undirected case, max_depth=3 ---
        ╟── 8
        ╙── 2
            └── 7
                ├── 4 ─ 0, 5
                │   └──  ...
                ├── 5 ─ 4, 3
                │   └──  ...
                └── 9 ─ 1, 6
                    └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_clique_max_depth():
    orig = nx.complete_graph(5, nx.DiGraph)
    lines = []
    write = lines.append
    write("--- directed case, max_depth=None ---")
    nx.write_network_text(orig, path=write, end="", max_depth=None)
    write("--- directed case, max_depth=0 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=0)
    write("--- directed case, max_depth=1 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=1)
    write("--- directed case, max_depth=2 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=2)
    write("--- directed case, max_depth=3 ---")
    nx.write_network_text(orig, path=write, end="", max_depth=3)
    write("--- undirected case, max_depth=None ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=None)
    write("--- undirected case, max_depth=0 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=0)
    write("--- undirected case, max_depth=1 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=1)
    write("--- undirected case, max_depth=2 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=2)
    write("--- undirected case, max_depth=3 ---")
    nx.write_network_text(orig.to_undirected(), path=write, end="", max_depth=3)
    text = "\n".join(lines)
    target = dedent(
        """
        --- directed case, max_depth=None ---
        ╙── 0 ╾ 1, 2, 3, 4
            ├─╼ 1 ╾ 2, 3, 4
            │   ├─╼ 2 ╾ 0, 3, 4
            │   │   ├─╼ 3 ╾ 0, 1, 4
            │   │   │   ├─╼ 4 ╾ 0, 1, 2
            │   │   │   │   └─╼  ...
            │   │   │   └─╼  ...
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- directed case, max_depth=0 ---
        ╙ ...
        --- directed case, max_depth=1 ---
        ╙── 0 ╾ 1, 2, 3, 4
            └─╼  ...
        --- directed case, max_depth=2 ---
        ╙── 0 ╾ 1, 2, 3, 4
            ├─╼ 1 ╾ 2, 3, 4
            │   └─╼  ...
            ├─╼ 2 ╾ 1, 3, 4
            │   └─╼  ...
            ├─╼ 3 ╾ 1, 2, 4
            │   └─╼  ...
            └─╼ 4 ╾ 1, 2, 3
                └─╼  ...
        --- directed case, max_depth=3 ---
        ╙── 0 ╾ 1, 2, 3, 4
            ├─╼ 1 ╾ 2, 3, 4
            │   ├─╼ 2 ╾ 0, 3, 4
            │   │   └─╼  ...
            │   ├─╼ 3 ╾ 0, 2, 4
            │   │   └─╼  ...
            │   ├─╼ 4 ╾ 0, 2, 3
            │   │   └─╼  ...
            │   └─╼  ...
            └─╼  ...
        --- undirected case, max_depth=None ---
        ╙── 0
            ├── 1
            │   ├── 2 ─ 0
            │   │   ├── 3 ─ 0, 1
            │   │   │   └── 4 ─ 0, 1, 2
            │   │   └──  ...
            │   └──  ...
            └──  ...
        --- undirected case, max_depth=0 ---
        ╙ ...
        --- undirected case, max_depth=1 ---
        ╙── 0 ─ 1, 2, 3, 4
            └──  ...
        --- undirected case, max_depth=2 ---
        ╙── 0
            ├── 1 ─ 2, 3, 4
            │   └──  ...
            ├── 2 ─ 1, 3, 4
            │   └──  ...
            ├── 3 ─ 1, 2, 4
            │   └──  ...
            └── 4 ─ 1, 2, 3
        --- undirected case, max_depth=3 ---
        ╙── 0
            ├── 1
            │   ├── 2 ─ 0, 3, 4
            │   │   └──  ...
            │   ├── 3 ─ 0, 2, 4
            │   │   └──  ...
            │   └── 4 ─ 0, 2, 3
            └──  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_custom_label():
    # Create a directed forest with labels
    graph = nx.erdos_renyi_graph(5, 0.4, directed=True, seed=359222358)
    for node in graph.nodes:
        graph.nodes[node]["label"] = f"Node({node})"
        graph.nodes[node]["chr"] = chr(node + ord("a") - 1)
        if node % 2 == 0:
            graph.nodes[node]["part"] = chr(node + ord("a"))

    lines = []
    write = lines.append
    write("--- when with_labels=True, uses the 'label' attr ---")
    nx.write_network_text(graph, path=write, with_labels=True, end="", max_depth=None)
    write("--- when with_labels=False, uses str(node) value ---")
    nx.write_network_text(graph, path=write, with_labels=False, end="", max_depth=None)
    write("--- when with_labels is a string, use that attr ---")
    nx.write_network_text(graph, path=write, with_labels="chr", end="", max_depth=None)
    write("--- fallback to str(node) when the attr does not exist ---")
    nx.write_network_text(graph, path=write, with_labels="part", end="", max_depth=None)

    text = "\n".join(lines)
    target = dedent(
        """
        --- when with_labels=True, uses the 'label' attr ---
        ╙── Node(1)
            └─╼ Node(3) ╾ Node(2)
                ├─╼ Node(0)
                │   ├─╼ Node(2) ╾ Node(3), Node(4)
                │   │   └─╼  ...
                │   └─╼ Node(4)
                │       └─╼  ...
                └─╼  ...
        --- when with_labels=False, uses str(node) value ---
        ╙── 1
            └─╼ 3 ╾ 2
                ├─╼ 0
                │   ├─╼ 2 ╾ 3, 4
                │   │   └─╼  ...
                │   └─╼ 4
                │       └─╼  ...
                └─╼  ...
        --- when with_labels is a string, use that attr ---
        ╙── a
            └─╼ c ╾ b
                ├─╼ `
                │   ├─╼ b ╾ c, d
                │   │   └─╼  ...
                │   └─╼ d
                │       └─╼  ...
                └─╼  ...
        --- fallback to str(node) when the attr does not exist ---
        ╙── 1
            └─╼ 3 ╾ c
                ├─╼ a
                │   ├─╼ c ╾ 3, e
                │   │   └─╼  ...
                │   └─╼ e
                │       └─╼  ...
                └─╼  ...
        """
    ).strip()
    assert target == text


def test_write_network_text_vertical_chains():
    graph1 = nx.lollipop_graph(4, 2, create_using=nx.Graph)
    graph1.add_edge(0, -1)
    graph1.add_edge(-1, -2)
    graph1.add_edge(-2, -3)

    graph2 = graph1.to_directed()
    graph2.remove_edges_from([(u, v) for u, v in graph2.edges if v > u])

    lines = []
    write = lines.append
    write("--- Undirected UTF ---")
    nx.write_network_text(graph1, path=write, end="", vertical_chains=True)
    write("--- Undirected ASCI ---")
    nx.write_network_text(
        graph1, path=write, end="", vertical_chains=True, ascii_only=True
    )
    write("--- Directed UTF ---")
    nx.write_network_text(graph2, path=write, end="", vertical_chains=True)
    write("--- Directed ASCI ---")
    nx.write_network_text(
        graph2, path=write, end="", vertical_chains=True, ascii_only=True
    )

    text = "\n".join(lines)
    target = dedent(
        """
        --- Undirected UTF ---
        ╙── 5
            │
            4
            │
            3
            ├── 0
            │   ├── 1 ─ 3
            │   │   │
            │   │   2 ─ 0, 3
            │   ├── -1
            │   │   │
            │   │   -2
            │   │   │
            │   │   -3
            │   └──  ...
            └──  ...
        --- Undirected ASCI ---
        +-- 5
            |
            4
            |
            3
            |-- 0
            |   |-- 1 - 3
            |   |   |
            |   |   2 - 0, 3
            |   |-- -1
            |   |   |
            |   |   -2
            |   |   |
            |   |   -3
            |   L--  ...
            L--  ...
        --- Directed UTF ---
        ╙── 5
            ╽
            4
            ╽
            3
            ├─╼ 0 ╾ 1, 2
            │   ╽
            │   -1
            │   ╽
            │   -2
            │   ╽
            │   -3
            ├─╼ 1 ╾ 2
            │   └─╼  ...
            └─╼ 2
                └─╼  ...
        --- Directed ASCI ---
        +-- 5
            !
            4
            !
            3
            |-> 0 <- 1, 2
            |   !
            |   -1
            |   !
            |   -2
            |   !
            |   -3
            |-> 1 <- 2
            |   L->  ...
            L-> 2
                L->  ...
        """
    ).strip()
    assert target == text


def test_collapse_directed():
    graph = nx.balanced_tree(r=2, h=3, create_using=nx.DiGraph)
    lines = []
    write = lines.append
    write("--- Original ---")
    nx.write_network_text(graph, path=write, end="")
    graph.nodes[1]["collapse"] = True
    write("--- Collapse Node 1 ---")
    nx.write_network_text(graph, path=write, end="")
    write("--- Add alternate path (5, 3) to collapsed zone")
    graph.add_edge(5, 3)
    nx.write_network_text(graph, path=write, end="")
    write("--- Collapse Node 0 ---")
    graph.nodes[0]["collapse"] = True
    nx.write_network_text(graph, path=write, end="")
    text = "\n".join(lines)
    target = dedent(
        """
        --- Original ---
        ╙── 0
            ├─╼ 1
            │   ├─╼ 3
            │   │   ├─╼ 7
            │   │   └─╼ 8
            │   └─╼ 4
            │       ├─╼ 9
            │       └─╼ 10
            └─╼ 2
                ├─╼ 5
                │   ├─╼ 11
                │   └─╼ 12
                └─╼ 6
                    ├─╼ 13
                    └─╼ 14
        --- Collapse Node 1 ---
        ╙── 0
            ├─╼ 1
            │   └─╼  ...
            └─╼ 2
                ├─╼ 5
                │   ├─╼ 11
                │   └─╼ 12
                └─╼ 6
                    ├─╼ 13
                    └─╼ 14
        --- Add alternate path (5, 3) to collapsed zone
        ╙── 0
            ├─╼ 1
            │   └─╼  ...
            └─╼ 2
                ├─╼ 5
                │   ├─╼ 11
                │   ├─╼ 12
                │   └─╼ 3 ╾ 1
                │       ├─╼ 7
                │       └─╼ 8
                └─╼ 6
                    ├─╼ 13
                    └─╼ 14
        --- Collapse Node 0 ---
        ╙── 0
            └─╼  ...
        """
    ).strip()
    assert target == text


def test_collapse_undirected():
    graph = nx.balanced_tree(r=2, h=3, create_using=nx.Graph)
    lines = []
    write = lines.append
    write("--- Original ---")
    nx.write_network_text(graph, path=write, end="", sources=[0])
    graph.nodes[1]["collapse"] = True
    write("--- Collapse Node 1 ---")
    nx.write_network_text(graph, path=write, end="", sources=[0])
    write("--- Add alternate path (5, 3) to collapsed zone")
    graph.add_edge(5, 3)
    nx.write_network_text(graph, path=write, end="", sources=[0])
    write("--- Collapse Node 0 ---")
    graph.nodes[0]["collapse"] = True
    nx.write_network_text(graph, path=write, end="", sources=[0])
    text = "\n".join(lines)
    target = dedent(
        """
        --- Original ---
        ╙── 0
            ├── 1
            │   ├── 3
            │   │   ├── 7
            │   │   └── 8
            │   └── 4
            │       ├── 9
            │       └── 10
            └── 2
                ├── 5
                │   ├── 11
                │   └── 12
                └── 6
                    ├── 13
                    └── 14
        --- Collapse Node 1 ---
        ╙── 0
            ├── 1 ─ 3, 4
            │   └──  ...
            └── 2
                ├── 5
                │   ├── 11
                │   └── 12
                └── 6
                    ├── 13
                    └── 14
        --- Add alternate path (5, 3) to collapsed zone
        ╙── 0
            ├── 1 ─ 3, 4
            │   └──  ...
            └── 2
                ├── 5
                │   ├── 11
                │   ├── 12
                │   └── 3 ─ 1
                │       ├── 7
                │       └── 8
                └── 6
                    ├── 13
                    └── 14
        --- Collapse Node 0 ---
        ╙── 0 ─ 1, 2
            └──  ...
        """
    ).strip()
    assert target == text


def generate_test_graphs():
    """
    Generate a gauntlet of different test graphs with different properties
    """
    import random

    rng = random.Random(976689776)
    num_randomized = 3

    for directed in [0, 1]:
        cls = nx.DiGraph if directed else nx.Graph

        for num_nodes in range(17):
            # Disconnected graph
            graph = cls()
            graph.add_nodes_from(range(num_nodes))
            yield graph

            # Randomize graphs
            if num_nodes > 0:
                for p in [0.1, 0.3, 0.5, 0.7, 0.9]:
                    for seed in range(num_randomized):
                        graph = nx.erdos_renyi_graph(
                            num_nodes, p, directed=directed, seed=rng
                        )
                        yield graph

                yield nx.complete_graph(num_nodes, cls)

        yield nx.path_graph(3, create_using=cls)
        yield nx.balanced_tree(r=1, h=3, create_using=cls)
        if not directed:
            yield nx.circular_ladder_graph(4, create_using=cls)
            yield nx.star_graph(5, create_using=cls)
            yield nx.lollipop_graph(4, 2, create_using=cls)
            yield nx.wheel_graph(7, create_using=cls)
            yield nx.dorogovtsev_goltsev_mendes_graph(4, create_using=cls)


@pytest.mark.parametrize(
    ("vertical_chains", "ascii_only"),
    tuple(
        [
            (vertical_chains, ascii_only)
            for vertical_chains in [0, 1]
            for ascii_only in [0, 1]
        ]
    ),
)
def test_network_text_round_trip(vertical_chains, ascii_only):
    """
    Write the graph to network text format, then parse it back in, assert it is
    the same as the original graph. Passing this test is strong validation of
    both the format generator and parser.
    """
    from networkx.readwrite.text import _parse_network_text

    for graph in generate_test_graphs():
        graph = nx.relabel_nodes(graph, {n: str(n) for n in graph.nodes})
        lines = list(
            nx.generate_network_text(
                graph, vertical_chains=vertical_chains, ascii_only=ascii_only
            )
        )
        new = _parse_network_text(lines)
        try:
            assert new.nodes == graph.nodes
            assert new.edges == graph.edges
        except Exception:
            nx.write_network_text(graph)
            raise
