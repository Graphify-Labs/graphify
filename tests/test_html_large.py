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
    """Return the source of one function in the Canvas script.

    Matches the closing brace instead of scanning for the next ``function``
    declaration, so a function at the end of the script (or with different
    indentation) is still extracted.
    """
    match = re.search(rf"(?m)^[ \t]*function\s+{re.escape(name)}\s*\(", html)
    assert match, f"function {name} not found"
    i = html.index("{", match.end())
    depth = 0
    quote = None
    while i < len(html):
        char = html[i]
        if quote:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in "'\"`":
            quote = char
        elif char == "/" and html.startswith("//", i):
            newline = html.find("\n", i + 2)
            i = len(html) if newline < 0 else newline
            continue
        elif char == "/" and html.startswith("/*", i):
            end = html.find("*/", i + 2)
            i = len(html) if end < 0 else end + 1
            continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return html[match.start():i + 1]
        i += 1
    raise AssertionError(f"function {name} is unterminated")


def _run_node(script: str) -> str:
    """Execute a Node.js harness and return stdout, skipping without node."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    proc = subprocess.run(
        [node, "-e", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, f"Node script failed ({proc.returncode}): {proc.stderr}"
    return proc.stdout


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


def test_large_graph_relation_display_executes(tmp_path):
    """Execute the inspector and map-label code so a broken relation display
    is caught even when the source still mentions ``relations``."""
    html = _canvas_html(tmp_path)
    harness = (
        """
function mockEl(tag) {
  return {
    tag, className: '', textContent: '', title: '', style: {}, dataset: {}, children: [],
    append(...kids) { this.children.push(...kids); },
    appendChild(kid) { this.children.push(kid); },
    replaceChildren() { this.children.length = 0; },
  };
}
const infoBox = mockEl('div');
const document = { createElement: mockEl, createTextNode: (text) => ({ text: String(text) }) };
const $ = (id) => (id === 'info-content' ? infoBox : null);
const labels = ['Alpha', 'Beta'];
const fileTypes = ['code'];
const fileTypeIds = [0, 0];
const nameByCid = new Map([[0, 'Core']]);
const community = [0, 0];
const sources = ['src/a.py'];
const sourceIds = [0, 0];
const degree = [1, 1];
const learning = [0, 0];
const adj = [[0], [0]];
const edgeSrc = [0];
const edgeTgt = [1];
const edgeRelation = [1];
const relations = ['', 'calls'];
const colorByCid = new Map([[0, '#123456']]);
"""
        + _js_function(html, "showInfo")
        + """
showInfo(0);
const flat = (el) => {
  if (el == null) return '';
  if (typeof el === 'string') return el;
  if (Object.prototype.hasOwnProperty.call(el, 'text')) return el.text;
  if (el.textContent) return el.textContent;
  return (el.children || []).map(flat).join('');
};
const rows = infoBox.children.map(flat);

const drawn = [];
const octx = {
  font: '', textAlign: '', textBaseline: '', globalAlpha: 1, fillStyle: '',
  measureText: (text) => ({ width: text.length * 6 }),
  fillRect() {},
  fillText: (text) => { drawn.push(text); },
};
const overlay = { clientWidth: 800, clientHeight: 600 };
const camera = { x: 0, y: 0, scale: 1 };
const canvas = { clientWidth: 800, clientHeight: 600 };
const pos = [0, 0, 200, 0];
const screenX = (x) => (x - camera.x) * camera.scale + canvas.clientWidth / 2;
const screenY = (y) => (y - camera.y) * camera.scale + canvas.clientHeight / 2;
const hiddenCommunities = new Set();
"""
        + _js_function(html, "drawFocusedEdgeLabels")
        + """
drawFocusedEdgeLabels({ bg: '#fff', label: '#000' }, 0);
console.log(JSON.stringify({ rows, drawn }));
"""
    )
    result = json.loads(_run_node(harness))
    assert any("\u2192 calls" in row for row in result["rows"]), result["rows"]
    assert result["drawn"] == ["calls"]


def test_stale_learning_rings_are_desaturated_and_dashed(tmp_path):
    """Execute drawNodes: stale preferred/contested annotations must land in
    the gray dashed batch, never the current green/amber one."""
    html = _canvas_html(tmp_path)
    harness = (
        """
const strokes = [];
const ctx = {
  fillStyle: '', strokeStyle: '', lineWidth: 0, globalAlpha: 1, dash: [], arcs: 0,
  beginPath() { this.dash = []; this.arcs = 0; },
  rect() { this.arcs += 1; },
  moveTo() {},
  arc() { this.arcs += 1; },
  fill() {},
  stroke() {
    strokes.push({ style: this.strokeStyle, width: this.lineWidth, dash: this.dash.slice(), arcs: this.arcs });
  },
  setLineDash(dash) { this.dash = dash.slice(); },
};
const canvas = { clientWidth: 800, clientHeight: 600 };
const overlay = { clientWidth: 800, clientHeight: 600 };
const camera = { x: 0, y: 0, scale: 1 };
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const screenX = (x) => (x - camera.x) * camera.scale + canvas.clientWidth / 2;
const screenY = (y) => (y - camera.y) * camera.scale + canvas.clientHeight / 2;
const worldX = (sx) => (sx - canvas.clientWidth / 2) / camera.scale + camera.x;
const worldY = (sy) => (sy - canvas.clientHeight / 2) / camera.scale + camera.y;
const nodeRadius = () => 5;
const pos = [0, 0, 20, 0, 0, 20, 20, 20];
const community = [0, 0, 0, 0];
const learning = [1, 2, 5, 6];
const n = 4;
const TAU = Math.PI * 2;
const membersByCommunity = new Map([[0, [0, 1, 2, 3]]]);
const hiddenCommunities = new Set();
const colorByCid = new Map([[0, '#123456']]);
"""
        + _js_function(html, "drawNodes")
        + """
drawNodes({});
console.log(JSON.stringify(strokes));
"""
    )
    strokes = json.loads(_run_node(harness))
    assert len(strokes) == 3
    by_style = {item["style"]: item for item in strokes}
    assert by_style["#22c55e"]["arcs"] == 1
    assert by_style["#22c55e"]["dash"] == []
    assert by_style["#f59e0b"]["arcs"] == 1
    assert by_style["#f59e0b"]["dash"] == []
    assert by_style["#9ca3af"]["arcs"] == 2
    assert by_style["#9ca3af"]["dash"] == [4, 4]


def test_js_function_handles_last_function(tmp_path):
    """The helper must not depend on another function following the target."""
    html = _canvas_html(tmp_path)
    source = _js_function(html, "applyTheme")
    assert source.lstrip().startswith("function applyTheme(")
    assert source.rstrip().endswith("}")
    assert "requestDraw" in source


def test_js_function_scans_balanced_braces():
    """Braces inside strings and comments must not end the function early."""
    fake = "    function last(a) {\n      if (a) { return '}'; }\n      // }\n    }"
    assert _js_function(fake, "last").strip() == fake.strip()


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
