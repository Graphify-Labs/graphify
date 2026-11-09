"""Searching graph.html narrows the view to the found node and its neighbors.

The page script is executed in Node against a small DOM and vis-network mock, so
these tests cover what the viewer gets, not the text of the script.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.exporters.html import to_html

NODE_TIMEOUT_SECONDS = 60
STAR_LEAF_COUNT = 200
MIN_NEIGHBOR_GAP = 100
VIEW_WIDTH = 800
VIEW_HEIGHT = 600

_MOCKS = r"""
class Elem {
  constructor() {
    this._innerHTML = ''; this.children = []; this.style = {}; this.dataset = {};
    this.listeners = {}; this.hidden = false; this.value = ''; this.checked = true;
    this.textContent = ''; this.clientWidth = %(width)d; this.clientHeight = %(height)d;
    this.classList = { add() {}, remove() {}, toggle() {}, contains: () => false };
  }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(html) { this._innerHTML = html; this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); }
  addEventListener(type, listener) { (this.listeners[type] = this.listeners[type] || []).push(listener); }
  fire(type, event) { (this.listeners[type] || []).forEach(listener => listener(event)); }
  contains() { return false; }
  closest() { return null; }
  querySelector() { return new Elem(); }
  querySelectorAll() { return []; }
  setAttribute() {}
  getBoundingClientRect() { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
}

const elements = {};
const document = {
  body: new Elem(),
  documentElement: new Elem(),
  listeners: {},
  getElementById: id => elements[id] || (elements[id] = new Elem()),
  createElement: () => new Elem(),
  addEventListener(type, listener) { (this.listeners[type] = this.listeners[type] || []).push(listener); },
  fire(type, event) { (this.listeners[type] || []).forEach(listener => listener(event)); },
  querySelectorAll: () => [],
};
const window = {};
const getComputedStyle = () => ({ getPropertyValue: () => '#000000' });

class MockDataSet {
  constructor(items) {
    this.items = new Map();
    items.forEach((item, index) => this.items.set(item.id === undefined ? index : item.id, item));
  }
  get(id) { return id === undefined ? [...this.items.values()] : this.items.get(id); }
  update(updates) {
    updates.forEach(update => this.items.set(update.id, Object.assign({}, this.items.get(update.id), update)));
  }
}

class MockNetwork {
  constructor(container, data) {
    this.data = data;
    this.handlers = {};
    this.options = {};
    this.selected = [];
    this.focused = [];
    this.view = { position: { x: 11, y: 22 }, scale: 0.33 };
    this.positions = {};
    [...data.nodes.items.keys()].forEach((id, index) => {
      this.positions[id] = { x: index * 1000, y: index * -1000 };
    });
  }
  on(type, handler) { (this.handlers[type] = this.handlers[type] || []).push(handler); }
  once(type, handler) { this.on(type, handler); }
  setOptions(options) { Object.assign(this.options, options); }
  selectNodes(ids) { this.selected = ids; }
  focus(id) { this.focused.push(id); }
  getConnectedNodes(id) {
    const connected = [];
    this.data.edges.items.forEach(e => {
      if (e.from === id) connected.push(e.to);
      if (e.to === id) connected.push(e.from);
    });
    return connected;
  }
  getPositions(ids) {
    const chosen = {};
    (ids || Object.keys(this.positions)).forEach(id => {
      if (this.positions[id]) chosen[id] = Object.assign({}, this.positions[id]);
    });
    return chosen;
  }
  getPosition(id) { return Object.assign({}, this.positions[id]); }
  moveNode(id, x, y) { this.positions[id] = { x, y }; }
  getViewPosition() { return Object.assign({}, this.view.position); }
  getScale() { return this.view.scale; }
  moveTo(view) { this.view = { position: view.position, scale: view.scale }; }
}
const vis = { DataSet: MockDataSet, Network: MockNetwork };
""" % {"width": VIEW_WIDTH, "height": VIEW_HEIGHT}

_HELPERS = r"""
const t_visible = () => [...nodesDS.items.values()].filter(n => !n.hidden).map(n => n.id).sort();
function t_search(label) {
  searchInput.value = label;
  searchInput.fire('input');
  searchResults.children.find(el => el.textContent === label).onclick();
}
const t_showAll = () => document.getElementById('focus-clear').fire('click');
const t_clickNeighbor = id => document.fire('click', { target: { closest: () => ({ dataset: { nid: id } }) } });
function t_untick(label) {
  const item = document.getElementById('legend').children.find(el => el.innerHTML.includes(label));
  const checkbox = item.children[0];
  checkbox.checked = false;
  checkbox.fire('change', { stopPropagation() {} });
}
const t_emit = value => console.log('OUTPUT:' + JSON.stringify(value));
"""


def _run_page(html_path, scenario: str, tmp_path) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    html = html_path.read_text(encoding="utf-8")
    scripts = re.findall(r"<script>(.*?)</script>", html, re.DOTALL)
    assert scripts, "page scripts not found"
    harness = tmp_path / "harness.js"
    harness.write_text(_MOCKS + "\n".join(scripts) + _HELPERS + scenario, encoding="utf-8")
    proc = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, encoding="utf-8", timeout=NODE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, proc.stderr
    output = re.search(r"OUTPUT:(.*)", proc.stdout)
    assert output, proc.stdout
    return json.loads(output.group(1))


def _small_page(tmp_path, hyperedges=None):
    """Hub - N1 - Far, Hub - N2, and Lonely on its own, in two communities."""
    G = nx.Graph()
    for node_id, label in [("hub", "Hub"), ("n1", "N1"), ("n2", "N2"), ("far", "Far"), ("lonely", "Lonely")]:
        G.add_node(node_id, label=label, file_type="code", source_file=f"{node_id}.py")
    G.add_edge("hub", "n1", relation="calls", confidence="EXTRACTED")
    G.add_edge("hub", "n2", relation="calls", confidence="EXTRACTED")
    G.add_edge("n1", "far", relation="calls", confidence="EXTRACTED")
    if hyperedges:
        G.graph["hyperedges"] = hyperedges
    out = tmp_path / "graph.html"
    communities = {0: ["hub", "n1", "n2"], 1: ["far", "lonely"]}
    assert to_html(G, communities, str(out), community_labels={0: "CommunityCore", 1: "CommunityFar"}) is True
    return out


def test_search_shows_only_the_node_and_its_neighbors(tmp_path):
    result = _run_page(_small_page(tmp_path), """
t_search('Hub');
t_emit({
  visible: t_visible(),
  selected: network.selected,
  barHidden: focusBar.hidden,
  label: focusLabel.textContent,
  physics: network.options.physics,
});
""", tmp_path)
    assert result["visible"] == ["hub", "n1", "n2"]
    assert result["selected"] == ["hub"]
    assert result["barHidden"] is False
    assert result["label"] == "Hub + 2 related"
    assert result["physics"] == {"enabled": False}


def test_show_all_restores_nodes_layout_and_view(tmp_path):
    result = _run_page(_small_page(tmp_path), """
const positionsBefore = network.getPositions();
const viewBefore = { position: network.getViewPosition(), scale: network.getScale() };
t_search('Hub');
const movedDuringFocus = JSON.stringify(network.getPositions()) !== JSON.stringify(positionsBefore);
t_showAll();
t_emit({
  movedDuringFocus,
  visible: t_visible(),
  positionsRestored: JSON.stringify(network.getPositions()) === JSON.stringify(positionsBefore),
  viewRestored: JSON.stringify(network.view) === JSON.stringify(viewBefore),
  barHidden: focusBar.hidden,
});
""", tmp_path)
    assert result["movedDuringFocus"] is True
    assert result["visible"] == ["far", "hub", "lonely", "n1", "n2"]
    assert result["positionsRestored"] is True
    assert result["viewRestored"] is True
    assert result["barHidden"] is True


def test_following_a_neighbor_refocuses_and_keeps_the_original_layout(tmp_path):
    result = _run_page(_small_page(tmp_path), """
const positionsBefore = network.getPositions();
t_search('Hub');
t_clickNeighbor('n1');
const visibleAfterClick = t_visible();
const label = focusLabel.textContent;
t_showAll();
t_emit({
  visibleAfterClick,
  label,
  positionsRestored: JSON.stringify(network.getPositions()) === JSON.stringify(positionsBefore),
});
""", tmp_path)
    assert result["visibleAfterClick"] == ["far", "hub", "n1"]
    assert result["label"] == "N1 + 2 related"
    assert result["positionsRestored"] is True


def test_neighbor_link_outside_focus_only_moves_the_camera(tmp_path):
    page = _small_page(tmp_path)
    assert '<div id="focus-bar" hidden>' in page.read_text(encoding="utf-8")
    result = _run_page(page, """
focusBar.hidden = true;
t_clickNeighbor('n1');
t_emit({ visible: t_visible(), focused: network.focused, barHidden: focusBar.hidden });
""", tmp_path)
    assert result["visible"] == ["far", "hub", "lonely", "n1", "n2"]
    assert result["focused"] == ["n1"]
    assert result["barHidden"] is True


def test_show_all_keeps_an_unticked_community_hidden(tmp_path):
    result = _run_page(_small_page(tmp_path), """
t_untick('CommunityFar');
t_search('Hub');
t_showAll();
t_emit({ visible: t_visible() });
""", tmp_path)
    assert result["visible"] == ["hub", "n1", "n2"]


def test_searched_node_stays_visible_when_its_community_is_unticked(tmp_path):
    result = _run_page(_small_page(tmp_path), """
t_untick('CommunityFar');
t_search('Far');
const whileHidden = t_visible();
t_showAll();
t_emit({ whileHidden, afterShowAll: t_visible() });
""", tmp_path)
    assert result["whileHidden"] == ["far", "n1"]
    assert result["afterShowAll"] == ["hub", "n1", "n2"]


def test_unticking_a_community_during_focus_keeps_the_focus_filter(tmp_path):
    result = _run_page(_small_page(tmp_path), """
t_search('Hub');
t_untick('CommunityCore');
t_emit({ visible: t_visible() });
""", tmp_path)
    assert result["visible"] == ["hub"]


def test_node_without_neighbors_gets_a_usable_view(tmp_path):
    result = _run_page(_small_page(tmp_path), """
t_search('Lonely');
t_emit({
  visible: t_visible(),
  label: focusLabel.textContent,
  scale: network.view.scale,
  maxScale: FOCUS_MAX_SCALE,
});
""", tmp_path)
    assert result["visible"] == ["lonely"]
    assert result["label"] == "Lonely + 0 related"
    assert 0 < result["scale"] <= result["maxScale"]


def test_many_neighbors_stay_apart_and_fit_in_the_view(tmp_path):
    G = nx.Graph()
    G.add_node("hub", label="Hub", file_type="code", source_file="hub.py")
    for i in range(STAR_LEAF_COUNT):
        G.add_node(f"leaf{i}", label=f"Leaf{i}", file_type="code", source_file="leaf.py")
        G.add_edge("hub", f"leaf{i}", relation="calls", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    assert to_html(G, {0: list(G.nodes)}, str(out)) is True

    result = _run_page(out, """
const centerBefore = network.getPosition('hub');
t_search('Hub');
const points = Object.values(network.getPositions());
let closest = Infinity;
for (let i = 0; i < points.length; i++) {
  for (let j = i + 1; j < points.length; j++) {
    closest = Math.min(closest, Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y));
  }
}
const center = network.getPosition('hub');
const furthest = Math.max(...points.map(p => Math.hypot(p.x - center.x, p.y - center.y)));
t_emit({
  closest,
  furthestOnScreen: furthest * network.view.scale,
  centerMoved: JSON.stringify(center) !== JSON.stringify(centerBefore),
  viewCenter: network.view.position,
  center,
});
""", tmp_path)
    assert result["closest"] >= MIN_NEIGHBOR_GAP
    assert result["furthestOnScreen"] <= min(VIEW_WIDTH, VIEW_HEIGHT) / 2
    assert result["centerMoved"] is False
    assert result["viewCenter"] == result["center"]


def test_hyperedge_outline_skips_hidden_members(tmp_path):
    hyperedges = [{"id": "h1", "label": "Group", "nodes": ["hub", "n1", "far"]}]
    result = _run_page(_small_page(tmp_path, hyperedges=hyperedges), """
const calls = {};
const ctx = new Proxy({}, {
  get: (target, name) => name in target ? target[name] : (...args) => {
    calls[name] = (calls[name] || 0) + 1;
    return { width: 0 };
  },
  set: (target, name, value) => { target[name] = value; return true; },
});
const draw = () => {
  delete calls.beginPath;
  network.handlers.afterDrawing.forEach(handler => handler(ctx));
  return calls.beginPath || 0;
};
const unfiltered = draw();
t_search('Lonely');
t_emit({ unfiltered, focusedElsewhere: draw() });
""", tmp_path)
    assert result["unfiltered"] > 0
    assert result["focusedElsewhere"] == 0
