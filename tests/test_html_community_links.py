"""REQ-QML-019-AC02 distinguishes aggregate neighbors from source relationships."""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.export import to_html
from tests.test_html_initial_view import HARNESS


def inspect(content, identity):
    """Execute the production viewer script; only the external DOM/vis boundary is isolated."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the emitted inspector runtime contract")
    script = re.search(r"<script>(.*?)</script>\s*<script>", content, re.S)
    assert script
    actions = "\nshowInfo(" + json.dumps(identity) + ");\n"
    actions += "console.log(JSON.stringify({info: document.getElementById('info-content').innerHTML, "
    actions += "nodes: RAW_NODES, edges: RAW_EDGES, checked: selectAllCb.checked}));"
    result = subprocess.run([node], input=HARNESS + script[1] + actions,
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def source_graph():
    """One closed source group, two linked groups and a genuine isolated member."""
    graph = nx.Graph()
    groups = {0: ["a0", "a1", "a2"], 1: ["b0", "b1", "b2"], 2: ["peer"], 3: ["isolated"]}
    for members in groups.values():
        for identity in members:
            graph.add_node(identity, label=identity, file_type="code", source_file="public.qml")
        for source, target in zip(members, members[1:]):
            graph.add_edge(source, target, relation="contains", confidence="EXTRACTED")
    graph.add_edge("b2", "peer", relation="references", confidence="INFERRED")
    return graph, groups


def export_view(tmp_path):
    graph, groups = source_graph()
    labels = {0: "Build <&> 'group'", 1: "Connected", 2: "Peer", 3: "Isolated"}
    before = copy.deepcopy((graph, groups, labels))
    path = tmp_path / "aggregate.html"
    assert to_html(graph, groups, str(path), node_limit=4,
                   community_labels=labels, learning_overlay={})
    assert nx.utils.graphs_equal(graph, before[0]) and groups == before[1] and labels == before[2]
    return path.read_text(encoding="utf-8")


def test_req_qml019_ac02_internal_only_group_has_source_edges_despite_zero_neighbors(tmp_path):
    """A closed three-member group has two source edges and zero neighboring communities."""
    result = inspect(export_view(tmp_path), "0")
    node = next(node for node in result["nodes"] if node["id"] == "0")
    assert node["member_count"] == 3 and node["degree"] == 0
    assert node["internal_source_edges"] == 2 and node["external_source_edges"] == 0
    assert "Internal source edges: 2" in result["info"]
    assert "External source edges: 0" in result["info"]
    assert "Connected communities: 0" in result["info"] and "Degree:" not in result["info"]
    assert "internal source relationships and no links to other communities" in result["info"]
    assert "Member-level source details are not expanded in this view" in result["info"]
    assert "Build &lt;&amp;&gt; &#39;group&#39;" in result["info"]
    assert "Build <&>" not in result["info"]
    assert len(result["nodes"]) == 4 and len(result["edges"]) == 1 and result["checked"]
    assert sum(n["internal_source_edges"] for n in result["nodes"]) + sum(
        n["external_source_edges"] for n in result["nodes"]) // 2 == source_graph()[0].number_of_edges()
    assert not any(edge["from"] == edge["to"] for edge in result["edges"])


def test_req_qml019_ac02_external_source_edges_are_distinct_from_neighbor_count(tmp_path):
    """Connected group counts describe canonical source edges and distinct aggregate neighbors."""
    result = inspect(export_view(tmp_path), "1")
    node = next(node for node in result["nodes"] if node["id"] == "1")
    assert node["internal_source_edges"] == 2 and node["external_source_edges"] == 1 and node["degree"] == 1
    assert "Internal source edges: 2" in result["info"] and "External source edges: 1" in result["info"]
    assert "Connected communities: 1" in result["info"]
    assert "no links to other communities" not in result["info"]


def test_req_qml019_ac02_isolated_source_member_does_not_claim_internal_connectivity(tmp_path):
    """A real degree-zero singleton remains different from an internally connected closed group."""
    result = inspect(export_view(tmp_path), "3")
    node = next(node for node in result["nodes"] if node["id"] == "3")
    assert node["member_count"] == 1 and node["internal_source_edges"] == 0 and node["external_source_edges"] == 0
    assert "No source relationships are represented for this community" in result["info"]
    assert "internal source relationships and no links" not in result["info"]


@pytest.mark.parametrize("parallel", [False, True])
def test_req_qml019_ac02_source_edge_counts_keep_direction_parallel_edges_and_self_loops(tmp_path, parallel):
    """Counts use G.edges once per canonical edge; aggregate links never gain fake self-loops."""
    graph = nx.MultiDiGraph() if parallel else nx.DiGraph()
    graph.add_nodes_from(["a0", "a1", "b0"])
    graph.add_edges_from([("a0", "a1"), ("a1", "a0"), ("a0", "a0"), ("a0", "b0"), ("b0", "a0")])
    if parallel:
        graph.add_edge("a0", "a1")
        graph.add_edge("a1", "b0")
    before = copy.deepcopy(graph)
    path = tmp_path / "directed.html"
    assert to_html(graph, {0: ["a0", "a1"], 1: ["b0"]}, str(path), node_limit=1, learning_overlay={})
    result = inspect(path.read_text(encoding="utf-8"), "0")
    nodes = {node["id"]: node for node in result["nodes"]}
    assert nodes["0"]["internal_source_edges"] == (4 if parallel else 3)
    assert nodes["0"]["external_source_edges"] == nodes["1"]["external_source_edges"] == (3 if parallel else 2)
    assert nodes["0"]["degree"] == nodes["1"]["degree"] == 1
    assert len(result["edges"]) == 1 and nx.utils.graphs_equal(graph, before)
    assert sum(n["internal_source_edges"] for n in nodes.values()) + sum(
        n["external_source_edges"] for n in nodes.values()) // 2 == graph.number_of_edges()


def test_req_qml019_ac02_preaggregated_without_source_counts_reports_unavailable(tmp_path):
    """Manually supplied aggregate membership cannot invent missing original edge counts."""
    graph = nx.Graph()
    graph.add_edge("0", "1")
    path = tmp_path / "preaggregated.html"
    assert to_html(graph, {0: ["0"], 1: ["1"]}, str(path), member_counts={0: 4, 1: 2}, learning_overlay={})
    result = inspect(path.read_text(encoding="utf-8"), "0")
    assert "Connected communities: 1" in result["info"] and "Degree:" not in result["info"]
    assert "Internal source edges: unavailable" in result["info"]
    assert "External source edges: unavailable" in result["info"]
    assert "no links to other communities" not in result["info"]


def test_req_qml019_ac02_small_source_inspector_keeps_ordinary_degree(tmp_path):
    """A full source-node view retains its existing source location and ordinary degree label."""
    graph = nx.Graph()
    graph.add_node("source", label="Source", file_type="code", source_file="src/plain.cpp")
    graph.add_node("target", label="Target")
    graph.add_edge("source", "target")
    path = tmp_path / "small.html"
    assert to_html(graph, {0: ["source", "target"]}, str(path), learning_overlay={})
    result = inspect(path.read_text(encoding="utf-8"), "source")
    assert "Degree: 1" in result["info"] and "Source: src/plain.cpp" in result["info"]
    assert "Connected communities:" not in result["info"] and "Internal source edges:" not in result["info"]
    assert all("internal_source_edges" not in node for node in result["nodes"])


def test_req_qml019_ac02_preaggregated_neighbor_count_excludes_loops_and_duplicate_direction(tmp_path):
    """A supplied directed meta-graph has one neighboring group despite loop/reciprocal degree."""
    graph = nx.DiGraph()
    graph.add_edges_from([("0", "0"), ("0", "1"), ("1", "0")])
    before = copy.deepcopy(graph)
    path = tmp_path / "directed-meta.html"
    assert to_html(graph, {0: ["0"], 1: ["1"]}, str(path), member_counts={0: 4, 1: 2}, learning_overlay={})
    result = inspect(path.read_text(encoding="utf-8"), "0")
    node = next(node for node in result["nodes"] if node["id"] == "0")
    assert node["degree"] == 4 and node["connected_communities"] == 1
    assert "Connected communities: 1" in result["info"] and "Degree:" not in result["info"]
    assert len(result["edges"]) == 3 and nx.utils.graphs_equal(graph, before)


@pytest.mark.parametrize("invalid", [True, -1, "</div><script>bad()</script>"])
def test_req_qml019_ac02_invalid_preaggregated_source_counts_remain_unavailable(tmp_path, invalid):
    """Untrusted count attributes neither inject inspector HTML nor invent zero source edges."""
    graph = nx.Graph()
    graph.add_edge("0", "1")
    graph.nodes["0"].update(internal_source_edges=invalid, external_source_edges=invalid)
    before = copy.deepcopy(graph)
    path = tmp_path / "invalid-counts.html"
    assert to_html(graph, {0: ["0"], 1: ["1"]}, str(path), member_counts={0: 4, 1: 2}, learning_overlay={})
    result = inspect(path.read_text(encoding="utf-8"), "0")
    node = next(node for node in result["nodes"] if node["id"] == "0")
    assert "internal_source_edges" not in node and "external_source_edges" not in node
    assert "Internal source edges: unavailable" in result["info"]
    assert "External source edges: unavailable" in result["info"] and "bad()" not in result["info"]
    assert nx.utils.graphs_equal(graph, before)
