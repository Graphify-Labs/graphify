"""Viewer filtering is language-neutral, reversible, and never edits graph evidence."""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.exporters.html import to_html


def _render(tmp_path):
    graph = nx.MultiDiGraph()
    for name, suffix in (("a", "cpp"), ("b", "py"), ("c", "rs"), ("d", "java")):
        graph.add_node(name, label=name, source_file=f"{name}.{suffix}", file_type="code")
    graph.add_edge("a", "b", relation="calls", confidence="EXTRACTED",
                   source_file="a.cpp", source_location="L9",
                   metadata={"cpp_conditions": [{"group_line": 7, "branch": 0}]})
    graph.add_edge("a", "b", relation="references", confidence="INFERRED")
    graph.add_edge("b", "c", relation="imports", confidence="EXTRACTED")
    graph.add_edge("c", "a", relation="custom relation", confidence="AMBIGUOUS")
    before = copy.deepcopy(graph)
    target = tmp_path / "graph.html"
    assert to_html(graph, {0: ["a", "b"], 1: ["c", "d"]}, str(target),
                   community_labels={0: "Core", 1: "Other"}, learning_overlay={})
    assert nx.utils.graphs_equal(graph, before)
    return target.read_text(encoding="utf-8")


def _raw(html, name):
    return json.loads(re.search(rf"const {name} = (.*);", html).group(1))


def test_controls_preserve_all_language_relationships_and_parallel_edges(tmp_path):
    html = _render(tmp_path)
    assert '<label for="relation-filter">Relationship</label>' in html
    assert '<label for="confidence-filter">Evidence</label>' in html
    edges = _raw(html, "RAW_EDGES")
    assert len(edges) == 4
    assert {edge["label"] for edge in edges} == {"calls", "references", "imports", "custom relation"}
    assert [(edge["from"], edge["to"]) for edge in edges].count(("a", "b")) == 2


def test_tooltips_show_source_and_conditional_evidence_without_claiming_execution(tmp_path):
    html = _render(tmp_path)
    edge = next(edge for edge in _raw(html, "RAW_EDGES") if edge["label"] == "calls")
    assert "a.cpp:L9" in edge["title"]
    assert "cpp_conditions" in edge["title"]
    assert "group_line" in edge["title"]
    assert "branch" in edge["title"]


def test_edge_tooltip_evidence_cannot_inject_html_or_script(tmp_path):
    graph = nx.Graph()
    graph.add_edge("a", "b", relation="</script><img src=x onerror=alert(1)>",
                   source_file='<img src=x onerror=alert(2)>',
                   metadata={"condition": "<!-- <script>alert(3)</script>"})
    target = tmp_path / "hostile.html"
    assert to_html(graph, {}, str(target), learning_overlay={})
    html = target.read_text(encoding="utf-8")
    assert html.count("<script") == html.count("</script")
    assert "<img" not in html
    # vis-network renders string titles as text; keep characters unchanged after
    # JSON decoding, while the HTML script container must remain escaped.
    assert "<img" in _raw(html, "RAW_EDGES")[0]["title"]
    assert "&lt;img" not in _raw(html, "RAW_EDGES")[0]["title"]


def test_filter_logic_handles_composition_empty_results_and_reset(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the exported viewer filter logic")
    html = _render(tmp_path)
    script = re.search(r"(function graphVisibility\(.*?\n\})\n", html, re.S)
    assert script, "test the actual exported JavaScript, not a parallel Python implementation"
    js = script.group(1) + "\nconst nodes = " + json.dumps(_raw(html, "RAW_NODES")) + ";\n"
    js += "const edges = " + json.dumps(_raw(html, "RAW_EDGES")) + ";\n"
    js += """
const assert = require('node:assert/strict');
const frozen = JSON.stringify([nodes, edges]);
const view = (hidden=[], relation=null, confidence=null) => {
  const result = graphVisibility(nodes, edges, new Set(hidden), relation, confidence);
  return {nodes: [...result.nodes].sort(), edges: [...result.edges].sort()};
};
assert.deepEqual(view().nodes, ['a', 'b', 'c', 'd']);
assert.equal(view().edges.length, 4);
assert.deepEqual(view([], 'calls'), {nodes: ['a', 'b'], edges: [0]});
assert.deepEqual(view([], 'references', 'INFERRED'), {nodes: ['a', 'b'], edges: [1]});
assert.deepEqual(view([], 'calls', 'INFERRED'), {nodes: [], edges: []});
assert.deepEqual(view([0], 'imports'), {nodes: [], edges: []});
assert.deepEqual(view([1], 'calls'), {nodes: ['a', 'b'], edges: [0]});
assert.deepEqual(view([0]).nodes, ['c', 'd']);
assert.deepEqual(view([0, 1]), {nodes: [], edges: []});
assert.equal(view().edges.length, 4);
assert.equal(JSON.stringify([nodes, edges]), frozen);
// Empty and unknown relationships remain selectable; arbitrary labels are data.
const extra = [{from:'a', to:'b', label:'', confidence:'UNKNOWN'}];
assert.deepEqual([...graphVisibility(nodes, extra, new Set(), '', null).edges], [0]);
assert.deepEqual([...graphVisibility([], [], new Set(), null, null).nodes], []);
"""
    result = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
