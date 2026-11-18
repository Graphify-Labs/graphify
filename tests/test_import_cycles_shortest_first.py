"""find_import_cycles lists two-file cycles first, even when longer ones are plentiful.

The enumeration stops after ``top_n * 10`` cycles to bound the cost on dense
graphs (#1196), but it used to stop *before* sorting by length. On a graph where
networkx happens to yield many longer cycles first, the cap filled up with them
and a two-file mutual import - the tightest coupling, which the docstring
promises comes first - never made it into the result.
"""

from __future__ import annotations

import networkx as nx
import pytest

from graphify.analyze import find_import_cycles


def _imp(G: nx.DiGraph, a: str, b: str) -> None:
    for name in (a, b):
        G.add_node(name, source_file=name, label=name)
    G.add_edge(a, b, relation="imports_from", source_file=a)


def _dense_ring(G: nx.DiGraph) -> None:
    """Four layers of four files, each importing every file of the next layer,
    the last layer importing the first: 256 distinct 4-file cycles."""
    layers = [[f"pkg/l{i}_{j}.py" for j in range(4)] for i in range(4)]
    for i, layer in enumerate(layers):
        for a in layer:
            for b in layers[(i + 1) % 4]:
                _imp(G, a, b)


def _two_file_cycle(G: nx.DiGraph) -> None:
    _imp(G, "a.py", "b.py")
    _imp(G, "b.py", "a.py")


@pytest.mark.parametrize("two_file_first", [True, False])
def test_two_file_cycle_survives_many_longer_cycles(two_file_first):
    G = nx.DiGraph()
    if two_file_first:
        _two_file_cycle(G)
        _dense_ring(G)
    else:
        _dense_ring(G)
        _two_file_cycle(G)

    cycles = find_import_cycles(G)

    assert cycles[0]["length"] == 2
    assert set(cycles[0]["cycle"]) == {"a.py", "b.py"}
    assert [c["length"] for c in cycles] == sorted(c["length"] for c in cycles)


def test_two_file_cycles_fill_the_result_before_longer_ones():
    """With more two-file cycles than fit, every returned cycle is a two-file one."""
    G = nx.DiGraph()
    _dense_ring(G)  # 256 four-file cycles
    for i in range(25):  # 25 two-file cycles: more than top_n=20
        _imp(G, f"m{i}/a.py", f"m{i}/b.py")
        _imp(G, f"m{i}/b.py", f"m{i}/a.py")

    cycles = find_import_cycles(G, top_n=20)

    assert len(cycles) == 20
    assert {c["length"] for c in cycles} == {2}


def test_max_cycle_length_below_two_reports_no_two_file_cycle():
    G = nx.DiGraph()
    _two_file_cycle(G)

    assert find_import_cycles(G, max_cycle_length=1) == []


def test_cap_still_bounds_the_result():
    G = nx.DiGraph()
    _dense_ring(G)

    cycles = find_import_cycles(G, top_n=5)

    assert len(cycles) == 5
    assert {c["length"] for c in cycles} == {4}
