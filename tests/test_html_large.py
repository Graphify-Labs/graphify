"""Tests for the large-graph Canvas renderer.

Small graphs must keep the existing vis-network output; graphs above the
comfort threshold with an explicit node limit must use the compact binary +
Canvas path and never instantiate a browser-side force simulation.
"""
from __future__ import annotations

import base64
import json
import math
import re

import networkx as nx
import pytest

from graphify.exporters.html import to_html
from graphify.exporters.html_large import _large_layout, to_large_html


def _large_graph(n: int = 6001):
    G = nx.Graph()
    for i in range(n):
        G.add_node(
            f"n{i}",
            label=f"Node {i}",
            source_file=f"src/file{i % 50}.py",
            file_type="code",
        )
    for i in range(n):
        G.add_edge(
            f"n{i}",
            f"n{(i * 7 + 1) % n}",
            relation="calls",
            confidence="EXTRACTED" if i % 2 else "INFERRED",
        )
    communities = {
        i: [f"n{j}" for j in range(i * 100, min(n, (i + 1) * 100))]
        for i in range((n + 99) // 100)
    }
    labels = {cid: f"Community {cid}" for cid in communities}
    return G, communities, labels


def _meta_and_payload(html: str):
    meta_match = re.search(
        r'<script id="graphify-meta" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    payload_match = re.search(
        r'<script id="graphify-payload" type="application/octet-stream">(.*?)</script>',
        html,
        flags=re.S,
    )
    assert meta_match and payload_match
    meta = json.loads(meta_match.group(1))
    payload = base64.b64decode(payload_match.group(1).strip())
    return meta, payload


def _canvas_html(tmp_path, n: int = 6001) -> str:
    G, communities, labels = _large_graph(n)
    out = tmp_path / "graph.html"
    assert to_html(
        G,
        communities,
        str(out),
        community_labels=labels,
        node_limit=len(G),
    ) is True
    return out.read_text(encoding="utf-8")


def _js_function(html: str, name: str) -> str:
    """Return the source of one top-level function in the Canvas script."""
    start = html.index(f"function {name}(")
    end = html.index("\n  function ", start + 1)
    return html[start:end]


def test_large_graph_uses_canvas_binary_renderer(tmp_path):
    G, communities, labels = _large_graph()
    out = tmp_path / "graph.html"
    assert to_html(
        G,
        communities,
        str(out),
        community_labels=labels,
        node_limit=len(G),
    ) is True
    html = out.read_text(encoding="utf-8")
    assert 'data-graphify-renderer="canvas-large"' in html
    assert "new vis.Network" not in html
    assert 'id="graphify-payload"' in html

    meta, payload = _meta_and_payload(html)
    assert meta["node_count"] == len(G)
    assert meta["edge_count"] == G.number_of_edges()
    assert meta["community_count"] == len(communities)
    assert payload[:4] == b"GFY1"
    assert int.from_bytes(payload[4:8], "little") == len(G)
    assert int.from_bytes(payload[8:12], "little") == G.number_of_edges()
    assert len(meta["sections"]) == 12


def test_large_graph_loads_learning_sidecar(tmp_path):
    """The Canvas path must read .graphify_learning.json beside graph.html.

    Without the sidecar load, every learning byte stays 0 and the rings
    disappear on large graphs.
    """
    G, communities, labels = _large_graph()
    out_dir = tmp_path / "graphify-out"
    out_dir.mkdir()
    (out_dir / ".graphify_learning.json").write_text(
        json.dumps(
            {
                "version": 1,
                "nodes": {
                    "n0": {"status": "preferred", "uses": 2, "score": 3, "source_file": ""},
                    "n1": {"status": "contested", "uses": 1, "neg": 1, "source_file": ""},
                },
            }
        ),
        encoding="utf-8",
    )
    out = out_dir / "graph.html"
    assert to_html(G, communities, str(out), community_labels=labels, node_limit=len(G)) is True
    meta, payload = _meta_and_payload(out.read_text(encoding="utf-8"))
    offset = meta["sections"]["learning"]
    codes = payload[offset:offset + meta["node_count"]]
    assert codes[0] == 1  # preferred -> green ring
    assert codes[1] == 2  # contested -> amber ring
    assert codes[2] == 0  # unannotated


def test_hidden_communities_hide_their_edges(tmp_path):
    html = _canvas_html(tmp_path)
    draw_edges = _js_function(html, "drawEdges")
    assert "hiddenCommunities.has(community[a])" in draw_edges
    assert "hiddenCommunities.has(community[b])" in draw_edges


def test_large_graph_exposes_edge_relations(tmp_path):
    html = _canvas_html(tmp_path)
    meta, _payload = _meta_and_payload(html)
    assert "calls" in meta["relations"]

    show_info = _js_function(html, "showInfo")
    assert "relations[edgeRelation[e]]" in show_info
    # The inspected node's edge relations are also drawn on the map.
    assert "relations[edgeRelation[e]]" in _js_function(html, "drawFocusedEdgeLabels")
    assert "drawFocusedEdgeLabels(" in _js_function(html, "drawOverlay")


def test_to_html_without_node_limit_raises_above_default(tmp_path, monkeypatch):
    """A bare to_html() call keeps the strict pre-existing contract: no
    explicit node_limit means an oversized graph raises instead of silently
    aggregating (the CLI always passes its 5000 default explicitly)."""
    monkeypatch.delenv("GRAPHIFY_VIZ_NODE_LIMIT", raising=False)
    G, communities, _labels = _large_graph(5001)
    with pytest.raises(ValueError, match="too large for HTML viz"):
        to_html(G, communities, str(tmp_path / "graph.html"))


def test_large_graph_payload_escapes_html_breakout(tmp_path):
    G = nx.Graph()
    evil = "x</script><script>alert(1)</script>"
    G.add_node("a", label=evil, source_file="a.py", file_type="code")
    G.add_node("b", label="normal", source_file="b.py", file_type="code")
    G.add_edge("a", "b", relation="imports", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    to_large_html(
        G,
        {0: ["a"], 1: ["b"]},
        str(out),
        community_labels={0: "Community </script>", 1: "Normal"},
        title="test",
    )
    html = out.read_text(encoding="utf-8")
    assert "</script><script>alert(1)</script>" not in html
    assert "Community </script>" not in html
    # The community label goes through the JSON escaping path.
    assert "\\u003c" in html
    meta, payload = _meta_and_payload(html)
    assert meta["node_count"] == 2
    assert payload[:4] == b"GFY1"


def test_small_graph_keeps_vis_network(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="a", file_type="code", source_file="a.py")
    G.add_node("b", label="b", file_type="code", source_file="b.py")
    G.add_edge("a", "b", relation="imports")
    out = tmp_path / "graph.html"
    to_html(G, {0: ["a", "b"]}, str(out))
    html = out.read_text(encoding="utf-8")
    assert "vis-network" in html
    assert "new vis.Network" in html
    assert 'data-graphify-renderer="canvas-large"' not in html


def test_graph_above_limit_still_aggregates(tmp_path, capsys):
    G, communities, labels = _large_graph()
    out = tmp_path / "graph.html"
    to_html(
        G,
        communities,
        str(out),
        community_labels=labels,
        node_limit=100,
    )
    captured = capsys.readouterr()
    assert "Building aggregated community view" in captured.out
    html = out.read_text(encoding="utf-8")
    assert "vis-network" in html
    assert 'data-graphify-renderer="canvas-large"' not in html


def test_large_layout_is_deterministic_and_finite():
    G, _communities, _labels = _large_graph(501)
    node_community = {f"n{i}": (0 if i < 251 else 1) for i in range(501)}
    first = _large_layout(G, node_community)
    second = _large_layout(G, node_community)
    assert first == second
    assert len(first) == G.number_of_nodes()
    for x, y in first.values():
        assert math.isfinite(x)
        assert math.isfinite(y)
