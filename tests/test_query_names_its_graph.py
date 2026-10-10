"""A query answer must say which graph it came from.

`graphify-out/` resolves against the CWD. Running `graphify query` from a parent
project while thinking about a vendored subproject answers from the parent's
graph — and the answer is well-formed, confident, and wrong. Nothing in the
output named the graph file, the scan root, or the node count, so the only way to
notice was recognising community labels you had not assigned (#2789).

The header now leads with the graph. It is shown relative to the CWD when it
sits underneath it (the ordinary case, and short) and absolute when it does not,
which is exactly the case worth noticing. The node count travels with it because
"355 nodes" against "3178 nodes" is often the first thing that looks wrong.
"""
import os
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.serve import _display_graph_path, _query_graph_text


def _graph(n=2):
    nodes = [{"id": f"n{i}", "label": f"Symbol{i}", "file_type": "code",
              "source_file": f"src/m{i}.py"} for i in range(n)]
    edges = [{"source": f"n{i}", "target": f"n{i+1}", "relation": "calls",
              "confidence": "EXTRACTED", "source_file": f"src/m{i}.py"}
             for i in range(n - 1)]
    return build_from_json({"nodes": nodes, "edges": edges, "hyperedges": []})


def _header(G, **kw):
    return _query_graph_text(G, "Symbol0", **kw).splitlines()[0]


# ---------------------------------------------------------------------------
# The header
# ---------------------------------------------------------------------------

def test_header_names_the_graph_and_its_size(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    gp = tmp_path / "graphify-out" / "graph.json"
    gp.parent.mkdir(parents=True)
    gp.write_text("{}", encoding="utf-8")
    header = _header(_graph(4), graph_path=str(gp))
    assert header.startswith("Graph: graphify-out/graph.json (4 nodes) | ")
    assert "Traversal:" in header


def test_a_graph_outside_the_cwd_is_shown_in_full(tmp_path, monkeypatch):
    """The case the issue is about: the answer came from somewhere else."""
    here = tmp_path / "parent"
    other = tmp_path / "elsewhere" / "graphify-out"
    here.mkdir()
    other.mkdir(parents=True)
    gp = other / "graph.json"
    gp.write_text("{}", encoding="utf-8")
    monkeypatch.chdir(here)
    header = _header(_graph(), graph_path=str(gp))
    assert "elsewhere" in header, header
    assert Path(header.split("Graph: ")[1].split(" (")[0]).is_absolute()


def test_header_is_unchanged_when_no_path_is_supplied():
    """Callers that do not know their graph path keep the old header exactly."""
    header = _header(_graph())
    assert header.startswith("Traversal:")
    assert "Graph:" not in header


def test_the_node_count_is_the_graphs_not_the_traversals():
    """`N nodes found` at the end is the traversal result; the count next to the
    graph is the whole corpus. Conflating them would hide the mismatch this is
    meant to surface."""
    G = _graph(6)
    header = _header(G, graph_path="graphify-out/graph.json")
    assert "(6 nodes)" in header
    assert G.number_of_nodes() == 6


# ---------------------------------------------------------------------------
# _display_graph_path
# ---------------------------------------------------------------------------

def test_display_is_relative_under_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "graphify-out" / "graph.json"
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    assert _display_graph_path(str(p)) == "graphify-out/graph.json"


def test_display_uses_posix_separators(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = tmp_path / "a" / "b" / "graph.json"
    p.parent.mkdir(parents=True)
    p.write_text("{}", encoding="utf-8")
    shown = _display_graph_path(str(p))
    assert "\\" not in shown, shown
    assert shown == "a/b/graph.json"


def test_display_is_absolute_outside_cwd(tmp_path, monkeypatch):
    here = tmp_path / "here"
    there = tmp_path / "there"
    here.mkdir()
    there.mkdir()
    monkeypatch.chdir(here)
    shown = _display_graph_path(str(there / "graph.json"))
    assert Path(shown).is_absolute()
    assert "there" in shown


def test_display_never_raises_on_a_hostile_path():
    """A display helper must not be the reason a query fails."""
    for bad in ["", "\x00bad", "?" * 300, "://not/a/path"]:
        assert isinstance(_display_graph_path(bad), str)


def test_two_projects_produce_distinguishable_headers(tmp_path, monkeypatch):
    """The end-to-end point: the parent and the subproject must not look alike."""
    parent = tmp_path / "Proj"
    sub = parent / "Sub"
    (parent / "graphify-out").mkdir(parents=True)
    (sub / "graphify-out").mkdir(parents=True)
    for d in (parent, sub):
        (d / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    monkeypatch.chdir(parent)
    h_parent = _header(_graph(9), graph_path=str(parent / "graphify-out" / "graph.json"))
    h_sub = _header(_graph(3), graph_path=str(sub / "graphify-out" / "graph.json"))
    assert h_parent != h_sub
    assert "(9 nodes)" in h_parent and "(3 nodes)" in h_sub
    assert "Sub/graphify-out/graph.json" in h_sub
