"""Regression test for issue #1236: to_obsidian must not crash with KeyError
when a community's member list contains an id that has no backing node in G
(e.g. pruned nodes, stale community assignments, or synthesized/merge-artifact
ids). Such dangling members must be skipped, not abort the whole vault export."""
import networkx as nx

from graphify.export import to_obsidian


def _graph_with_dangling_member():
    """Two real nodes plus a community that references a third, non-existent id."""
    G = nx.Graph()
    G.add_node("n0", label="Alpha", file_type="code", source_file="a.py")
    G.add_node("n1", label="Beta", file_type="code", source_file="b.py")
    G.add_edge("n0", "n1", relation="calls", confidence="EXTRACTED")
    # 'agents_doc' is a synthesized member id with no backing node in G.
    communities = {0: ["n0", "n1", "agents_doc"]}
    return G, communities


def test_obsidian_dangling_community_member_does_not_crash(tmp_path):
    G, comms = _graph_with_dangling_member()
    # Before the fix this raised KeyError: 'agents_doc'.
    n = to_obsidian(G, comms, str(tmp_path))
    assert n > 0

    # The community note is still written for the surviving members.
    comm_notes = list(tmp_path.glob("_COMMUNITY_*.md"))
    assert len(comm_notes) == 1
    body = comm_notes[0].read_text(encoding="utf-8")

    # Real members appear in the Members section; the dangling id does not.
    assert "[[Alpha]]" in body
    assert "[[Beta]]" in body
    assert "agents_doc" not in body

    # Member count reflects only the real (resolvable) members.
    assert "**Members:** 2 nodes" in body


def test_obsidian_community_of_only_dangling_members(tmp_path):
    """A community whose members are all dangling should still not crash."""
    G = nx.Graph()
    G.add_node("n0", label="Alpha", file_type="code", source_file="a.py")
    comms = {0: ["n0"], 1: ["ghost_a", "ghost_b"]}
    n = to_obsidian(G, comms, str(tmp_path))
    assert n > 0
    ghost_note = tmp_path / "_COMMUNITY_Community 1.md"
    assert ghost_note.exists()
    assert "**Members:** 0 nodes" in ghost_note.read_text(encoding="utf-8")


def test_canvas_dangling_community_member_does_not_crash(tmp_path):
    """#1236 follow-up: the fix landed in to_obsidian but not to_canvas, so
    `graphify export obsidian` (which also writes graph.canvas) still crashed
    with KeyError in to_canvas on a dangling member. The same guard now applies
    to both the box-sizing loop and the card-layout loop."""
    import json
    from graphify.export import to_canvas

    G, comms = _graph_with_dangling_member()
    out = tmp_path / "graph.canvas"
    to_canvas(G, comms, str(out))  # before the fix: KeyError: 'agents_doc'
    assert out.exists()

    canvas = json.loads(out.read_text(encoding="utf-8"))
    node_ids = {n.get("id") for n in canvas.get("nodes", [])}
    # real members get cards; the dangling id does not
    assert "n_n0" in node_ids and "n_n1" in node_ids
    assert "n_agents_doc" not in node_ids
