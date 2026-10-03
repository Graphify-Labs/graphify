"""REQ-QML-019-AC04 retains default selection, filters and source search."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.export import to_html


# External DOM/vis APIs only: emitted code owns selection and camera arithmetic.
HARNESS = r"""
class Event {
  constructor(type, options = {}) {
    Object.assign(this, {type, bubbles: true, cancelable: true, defaultPrevented: false}, options);
    this.stopped = false; this.immediate = false;
  }
  preventDefault() { if (this.cancelable) this.defaultPrevented = true; }
  stopPropagation() { this.stopped = true; }
  stopImmediatePropagation() { this.immediate = this.stopped = true; }
}
class EventTarget {
  constructor() { this.listeners = {}; this.handlers = {}; }
  addEventListener(name, fn, options = {}) {
    const capture = options === true || !!options.capture;
    (this.listeners[name] ||= []).push({fn, capture, once: !!options.once});
    this.handlers[name] = (event = {}) => this.dispatchEvent(new Event(name, event));
  }
  removeEventListener(name, fn, options = {}) {
    const capture = options === true || !!options.capture;
    this.listeners[name] = (this.listeners[name] || []).filter(x => x.fn !== fn || x.capture !== capture);
  }
  deliver(event, capture) {
    event.currentTarget = this;
    for (const listener of [...(this.listeners[event.type] || [])]) {
      if (event.immediate) break;
      if (listener.capture !== capture) continue;
      listener.fn.call(this, event);
      if (listener.once) this.removeEventListener(event.type, listener.fn, {capture});
    }
  }
  dispatchEvent(event) {
    event = event instanceof Event ? event : new Event(event.type, event);
    event.target ||= this;
    const parents = []; for (let p = this.parent; p; p = p.parent) parents.push(p);
    for (const p of [...parents].reverse()) { p.deliver(event, true); if (event.stopped) break; }
    if (!event.stopped) { this.deliver(event, true); if (!event.immediate) this.deliver(event, false); }
    if (event.bubbles && !event.stopped) for (const p of parents) {
      p.deliver(event, false); if (event.stopped) break;
    }
    return !event.defaultPrevented;
  }
}
class Element extends EventTarget {
  constructor() {
    super(); this.children = []; this.style = {}; this.innerHTML = ''; this.captures = new Set();
    this.checked = false; this.indeterminate = false; this.value = ''; this.captureLog = [];
    this.classes = new Set();
    this.classList = {add: x => this.classes.add(x), remove: x => this.classes.delete(x)};
  }
  appendChild(child) { child.parent = this; this.children.push(child); }
  prepend(child) { child.parent = this; this.children.unshift(child); }
  contains(child) { return child === this || this.children.some(x => x.contains(child)); }
  setPointerCapture(id) { this.captureLog.push(['set', id]); if (this.failCapture) throw Error('capture'); this.captures.add(id); }
  releasePointerCapture(id) { this.captureLog.push(['release', id]); if (this.failRelease) throw Error('release'); this.captures.delete(id); }
  hasPointerCapture(id) { return this.captures.has(id); }
}
const window = new EventTarget();
const document = Object.assign(new EventTarget(), {
  elements: {}, parent: window,
  getElementById(id) { if (!this.elements[id]) { this.elements[id] = new Element(); this.elements[id].parent = this; } return this.elements[id]; },
  createElement() { const element = new Element(); element.parent = this; return element; },
  querySelectorAll() { return []; }
});
class DataSet {
  constructor(items) { this.map = new Map(items.map(n => [n.id, n])); this.updates = 0; }
  get(id) { return this.map.get(id); }
  update(items) { this.updates += items.length; items.forEach(n => this.map.set(n.id, n)); }
  remove(ids) { ids.forEach(id => this.map.delete(id)); }
}
let constructed;
const focusChecks = [];
const vis = {DataSet, Network: class {
  constructor(container, data) {
    this.data = data; this.camera = {x: 100, y: -50}; this.scale = 2; this.moves = []; this.selections = [];
    constructed = {nodes: [...data.nodes.map.keys()], edges: [...data.edges.map.values()]};
  }
  once() {} on() {} setOptions() {} stabilize() {}
  selectNodes(ids) { this.selections.push(ids); }
  focus(id) { focusChecks.push({id, present: this.data.nodes.map.has(id)}); }
  getConnectedNodes() { return []; }
  getViewPosition() { if (this.failView) throw Error('view'); return {...this.camera}; }
  getScale() { if (this.failScale) throw Error('scale'); return this.scale; }
  moveTo(options) {
    if (this.failMove) throw Error('move'); this.moves.push(JSON.parse(JSON.stringify(options)));
    this.camera = {...options.position}; if ('scale' in options) this.scale = options.scale;
  }
}};
function state() {
  return {nodes: [...nodesDS.map.keys()].sort(), edges: [...edgesDS.map.values()],
    checked: document.getElementById('select-all-cb').checked,
    indeterminate: document.getElementById('select-all-cb').indeterminate,
    caption: document.getElementById('view-caption').textContent,
    checkedGroups: [...legendControls].filter(([cid, c]) => c.cb.checked).map(([cid]) => cid)};
}
"""


def execute(content: str, actions: str = "") -> dict:
    """Run the actual emitted script; constructor snapshots cannot hide full loading."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the emitted viewer runtime contract")
    assert node is not None
    script = re.search(r"<script>(.*?)</script>\s*<script>", content, re.S)
    assert script
    program = HARNESS + script[1] + "\nconst initial = state();\n" + actions
    program += "\nconsole.log(JSON.stringify({constructed, initial, final: state(), focusChecks, "
    program += "rawNodes: RAW_NODES, rawEdges: RAW_EDGES}));"
    result = subprocess.run([node], input=program, text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def write_view(tmp_path: Path, *, counts=None, reverse=False) -> tuple[str, nx.Graph]:
    """Use source-owned group nodes with literal provenance; never mock the exporter."""
    graph = nx.Graph()
    order = list(range(12))
    if reverse:
        order.reverse()
    for cid in order:
        graph.add_node(f"n{cid}", label=f"Group {cid}")
    graph.nodes["n0"].update(
        label="Deferred & <Widget>", file_type="code", source_file="src/Widget.qml",
        source_location="L3-L4",
        metadata={"qml": {"contract_version": 1, "kind": "property", "raw_name": "deferred"}},
        attributes={"public": "retained"},
    )
    for cid in range(11):
        graph.add_edge(f"n{cid}", f"n{cid + 1}", relation="references", confidence="INFERRED",
                       _src=f"n{cid + 1}", _tgt=f"n{cid}")
    before = copy.deepcopy(graph)
    path = tmp_path / "graph.html"
    assert to_html(graph, {i: [f"n{i}"] for i in range(12)}, str(path),
                   community_labels={i: f"Group {i}" for i in range(12)},
                   member_counts=counts or {i: i + 1 for i in range(12)}, learning_overlay={})
    assert dict(graph.nodes(data=True)) == dict(before.nodes(data=True))
    assert list(graph.edges(data=True)) == list(before.edges(data=True))
    return path.read_text(encoding="utf-8"), graph


def test_default_select_all_constructs_every_exported_node_and_edge_before_network(tmp_path):
    """REQ-QML-019-AC04: the exported view starts fully selected with exact endpoint facts."""
    content, _ = write_view(tmp_path)
    result = execute(content)
    assert set(result["constructed"]["nodes"]) == {n["id"] for n in result["rawNodes"]}
    assert len(result["constructed"]["edges"]) == 11
    assert {(e["from"], e["to"]) for e in result["constructed"]["edges"]} == {
        (e["from"], e["to"]) for e in result["rawEdges"]
    }
    assert result["initial"]["checkedGroups"] == list(range(12))
    assert result["initial"]["checked"] and not result["initial"]["indeterminate"]
    assert "Source communities: 12 of 12 source communities" in result["initial"]["caption"]
    assert 'id="select-all-cb" checked' in content
    assert 'id="overview-reset"' not in content and 'resetOverview' not in content
    assert len(result["rawNodes"]) == 12 and len(result["rawEdges"]) == 11


def test_req_qml019_ac04_filters_all_none_preserve_endpoint_safe_source_data(tmp_path):
    """Community filters, Select None and Select All change actual datasets."""
    content, _ = write_view(tmp_path)
    result = execute(content, """
const control = legendControls.get(0).cb;
control.checked = false; control.handlers.change({stopPropagation() {}});
if (nodesDS.get('n0') || selectAllCb.checked || !selectAllCb.indeterminate) throw Error('filter failed');
toggleAllCommunities(true);
if (nodesDS.map.size || edgesDS.map.size || selectAllCb.checked) throw Error('deselection failed');
if (!state().caption.includes('No communities selected')) throw Error('empty selection lacks guidance');
toggleAllCommunities(false);
""")
    assert set(result["final"]["nodes"]) == {f"n{i}" for i in range(12)}
    assert result["final"]["checked"] and not result["final"]["indeterminate"]
    assert len(result["final"]["edges"]) == 11
    assert all(e["from"] in result["final"]["nodes"] and e["to"] in result["final"]["nodes"]
               for e in result["final"]["edges"])


def test_req_qml019_ac04_search_restores_filtered_source_and_exact_metadata(tmp_path):
    """Filtered source evidence is restored before the real focus call."""
    content, _ = write_view(tmp_path)
    result = execute(content, """
legendControls.get(0).cb.checked = false; legendControls.get(0).cb.handlers.change();
searchInput.value = '<Widget>'; searchInput.handlers.input();
if (searchResults.children.length !== 1) throw Error('filtered search result unavailable');
searchResults.children[0].onclick();
if (!document.getElementById('info-content').innerHTML.includes('src/Widget.qml')) throw Error('source missing');
if (nodesDS.get('n0').metadata.qml.raw_name !== 'deferred') throw Error('metadata changed');
if (nodesDS.get('n0').qt_qml.qml.raw_name !== 'deferred') throw Error('public Qt projection changed');
""")
    assert result["focusChecks"] == [{"id": "n0", "present": True}]
    assert result["final"]["checked"] and not result["final"]["indeterminate"]
    assert "n0" in result["final"]["nodes"] and len(result["final"]["edges"]) == 11
    source = next(n for n in result["rawNodes"] if n["id"] == "n0")
    assert source["source_location"] == "L3-L4" and source["attributes"]["public"] == "retained"
    assert all(e["from"] in result["final"]["nodes"] and e["to"] in result["final"]["nodes"]
               for e in result["final"]["edges"])


@pytest.mark.parametrize("grouped", [False, True])
def test_small_grouped_and_ungrouped_views_default_to_select_all(tmp_path, grouped):
    """Small views retain all facts and captions appropriate to their source form."""
    graph = nx.Graph([("a", "b")])
    path = tmp_path / "small.html"
    assert to_html(graph, {0: ["a", "b"]} if grouped else {}, str(path), learning_overlay={})
    result = execute(path.read_text(encoding="utf-8"))
    assert set(result["constructed"]["nodes"]) == {"a", "b"}
    assert len(result["constructed"]["edges"]) == 1
    assert result["initial"]["checked"] and not result["initial"]["indeterminate"]
    assert ("Source communities" if grouped else "Source graph") in result["final"]["caption"]


def test_req_qml019_ac04_partial_membership_cannot_mark_hidden_ungrouped_fact_selected(tmp_path):
    """Known groups alone cannot imply full selection while an ungrouped fact is hidden."""
    graph = nx.Graph([("a", "b")])
    path = tmp_path / "partial.html"
    assert to_html(graph, {1: ["a"]}, str(path), learning_overlay={})
    result = execute(path.read_text(encoding="utf-8"), """
toggleAllCommunities(true);
legendControls.get(1).cb.checked = true; legendControls.get(1).cb.handlers.change();
if (selectAllCb.checked || !selectAllCb.indeterminate || nodesDS.get('b')) throw Error('false full selection');
focusNode('b');
if (!nodesDS.get('b') || edgesDS.map.size !== 1) throw Error('ungrouped result stranded');
""")
    assert result["constructed"]["nodes"] == ["a", "b"]
    assert len(result["constructed"]["edges"]) == 1
    assert result["initial"]["checked"] and not result["initial"]["indeterminate"]
    assert result["final"]["checked"]
    assert result["final"]["nodes"] == ["a", "b"]
    assert result["focusChecks"] == [{"id": "b", "present": True}]
