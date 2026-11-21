"""`affected` returns the same hits, ranked: distance, then link strength, then path.

Nothing new is imported at module level, so on a tree without the ranking the
order tests fail one by one instead of the file erroring at collection.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.affected import affected_nodes

# seed file core.py. Depth 1: a.py (1 edge in), m.py and z.py (3 edges each:
# a tie broken by path). Depth 2: b.py (1 edge into a.py), y.py (2 edges into z.py).
NODES = {
    "core": ("core.py", "core.py", "L1"),
    "f": ("f()", "core.py", "L3"),
    "a": ("a.py", "a.py", "L1"),
    "z": ("z.py", "z.py", "L1"),
    "z_g": ("g()", "z.py", "L9"),
    "m": ("m.py", "m.py", "L1"),
    "m_h": ("h()", "m.py", "L7"),
    "b": ("b.py", "b.py", "L1"),
    "y": ("y.py", "y.py", "L1"),
}
EDGES = [  # (source, target, relation): source depends on target
    ("a", "core", "imports_from"),
    ("z", "core", "imports_from"), ("z_g", "f", "calls"), ("z", "f", "references"),
    ("m", "core", "imports_from"), ("m_h", "f", "calls"), ("m", "f", "references"),
    ("b", "a", "imports_from"),
    ("y", "z", "imports_from"), ("y", "z_g", "calls"),
]


def _graph(reverse: bool = False) -> nx.DiGraph:
    g = nx.DiGraph()
    nodes = list(NODES.items())
    edges = list(EDGES)
    if reverse:
        nodes.reverse()
        edges.reverse()
    for nid, (label, sf, loc) in nodes:
        g.add_node(nid, label=label, source_file=sf, source_location=loc)
    for nid in ("core",):
        g.add_edge("core", "f", relation="contains")
    for s, t, r in edges:
        g.add_edge(s, t, relation=r, source_file=NODES[s][1], source_location=NODES[s][2])
    return g


def _order(g: nx.DiGraph) -> list[tuple[str, int]]:
    return [(h.node_id, h.depth) for h in affected_nodes(g, "core", depth=2)]


EXPECTED = [
    # depth 1: m.py and z.py both have 3 links into core.py -> path order; a.py has 1
    ("m", 1), ("m_h", 1),  # same file: by line
    ("z", 1), ("z_g", 1),
    ("a", 1),
    # depth 2: y.py has 2 links into z.py, b.py 1 link into a.py
    ("y", 2),
    ("b", 2),
]


def test_hits_are_ranked_by_distance_then_link_strength_then_path():
    assert _order(_graph()) == EXPECTED


def test_the_result_set_and_depths_are_unchanged():
    # guard: ranking may only reorder. Same (node, depth, relation) triples as
    # the breadth-first walk has always produced.
    hits = affected_nodes(_graph(), "core", depth=2)
    assert {(h.node_id, h.depth, h.via_relation) for h in hits} == {
        ("a", 1, "imports_from"), ("z", 1, "imports_from"), ("z_g", 1, "calls"),
        ("m", 1, "imports_from"), ("m_h", 1, "calls"),
        ("b", 2, "imports_from"), ("y", 2, "imports_from"),
    }
    assert len(hits) == 7


def test_order_does_not_depend_on_how_the_graph_was_built():
    assert _order(_graph(reverse=True)) == _order(_graph()) == EXPECTED


def test_rank_hits_keeps_every_hit_and_is_idempotent():
    from graphify.affected import rank_hits

    g = _graph()
    hits = affected_nodes(g, "core", depth=2)
    again = rank_hits(g, "core", list(reversed(hits)))
    assert again == hits
    assert rank_hits(g, "core", hits[:1]) == hits[:1]


def test_same_order_across_hash_seeds(tmp_path):
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(_graph(), edges="links")), encoding="utf-8")
    code = ("import sys; from graphify.affected import load_graph, affected_nodes; "
            "g = load_graph(__import__('pathlib').Path(sys.argv[1])); "
            "print([h.node_id for h in affected_nodes(g, 'core', depth=2)])")
    outs = {subprocess.run([sys.executable, "-c", code, str(gp)], capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": seed}).stdout for seed in ("0", "1", "999")}
    assert outs == {str([n for n, _ in EXPECTED]) + "\n"}


def test_cli_text_lists_hits_in_ranked_order(tmp_path, monkeypatch, capsys):
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(_graph(), edges="links")), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "affected", "core.py", "--graph", str(gp)])
    mainmod.main()
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("- ")]
    assert [ln.split(" [")[0][2:] for ln in lines] == ["m.py", "h()", "z.py", "g()", "a.py", "y.py", "b.py"]


def test_a_seed_without_a_file_does_not_count_links_to_unfiled_nodes():
    g = nx.DiGraph()
    g.add_node("s", label="seed")  # no source_file
    g.add_node("u", label="other")  # unrelated, also no source_file
    g.add_node("a1", label="a1()", source_file="a.py", source_location="L1")
    for n in ("b1", "b2", "b3"):
        g.add_node(n, label=f"{n}()", source_file="b.py", source_location=f"L{n[1]}")
    g.add_edge("a1", "s", relation="calls")
    g.add_edge("b1", "s", relation="calls")
    g.add_edge("b2", "u", relation="calls")
    g.add_edge("b3", "u", relation="calls")
    hits = affected_nodes(g, "s", depth=1)
    assert [h.node_id for h in hits] == ["a1", "b1"]  # tie broken by path, not by b.py's calls to "u"
