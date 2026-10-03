"""Execute the written viewer's initial selection and deferred dataset lifecycle."""
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


HARNESS = r"""
class Element {
  constructor() {
    this.children = []; this.handlers = {}; this.style = {}; this.innerHTML = '';
    this.checked = false; this.indeterminate = false; this.value = '';
    this.classes = new Set();
    this.classList = {add: x => this.classes.add(x), remove: x => this.classes.delete(x)};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  appendChild(child) { this.children.push(child); }
  prepend(child) { this.children.unshift(child); }
  contains(child) { return this.children.includes(child); }
  dispatchEvent(event) { this.handlers[event.type](event); }
}
const document = {
  elements: {},
  getElementById(id) { return this.elements[id] ||= new Element(); },
  createElement() { return new Element(); },
  addEventListener() {}, querySelectorAll() { return []; }
};
class DataSet {
  constructor(items) { this.map = new Map(items.map(n => [n.id, n])); }
  get(id) { return this.map.get(id); }
  update(items) { items.forEach(n => this.map.set(n.id, n)); }
  remove(ids) { ids.forEach(id => this.map.delete(id)); }
}
let constructed;
const focusChecks = [];
const vis = {DataSet, Network: class {
  constructor(container, data) {
    this.data = data;
    constructed = {nodes: [...data.nodes.map.keys()], edges: [...data.edges.map.values()]};
  }
  once() {} on() {} setOptions() {} stabilize() {}
  selectNodes() {}
  focus(id) { focusChecks.push({id, present: this.data.nodes.map.has(id)}); }
  getConnectedNodes() { return []; }
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


def test_initial_overview_constructs_only_ten_largest_groups_before_network(tmp_path):
    """REQ-QML-019-AC04: initial physics sees only selected groups, never hidden full data."""
    content, _ = write_view(tmp_path)
    result = execute(content)
    assert set(result["constructed"]["nodes"]) == {f"n{i}" for i in range(2, 12)}
    assert len(result["constructed"]["edges"]) == 9
    assert result["initial"]["checkedGroups"] == list(range(2, 12))
    assert not result["initial"]["checked"] and not result["initial"]["indeterminate"]
    assert "Architecture overview: 10 of 12 source communities" in result["initial"]["caption"]
    assert 'id="select-all-cb" checked' not in content
    assert len(result["rawNodes"]) == 12 and len(result["rawEdges"]) == 11


def test_initial_overview_ties_use_numeric_community_ids_independent_of_insertion(tmp_path):
    """Equal-sized groups select stable numeric IDs rather than graph insertion order."""
    content, _ = write_view(tmp_path, counts={i: 2 for i in range(12)}, reverse=True)
    result = execute(content)
    assert set(result["constructed"]["nodes"]) == {f"n{i}" for i in range(10)}
    assert not result["initial"]["checked"]


def test_filters_add_and_remove_real_datasets_and_reset_explicit_full_selection(tmp_path):
    """Filters defer nodes and endpoint-safe edges; reset restores an unchecked overview."""
    content, _ = write_view(tmp_path)
    actions = """
const control = legendControls.get(0).cb;
control.checked = true; control.handlers.change({stopPropagation() {}});
if (!nodesDS.get('n0')) throw Error('checked deferred group was not loaded');
control.checked = false; control.handlers.change({stopPropagation() {}});
if (nodesDS.get('n0')) throw Error('unchecked group stayed active');
toggleAllCommunities(false);
if (nodesDS.map.size !== 12 || !selectAllCb.checked) throw Error('explicit full selection failed');
toggleAllCommunities(true);
if (nodesDS.map.size || edgesDS.map.size) throw Error('deselection left active data');
if (!state().caption.includes('No communities selected')) throw Error('empty selection lacks guidance');
resetOverview();
"""
    result = execute(content, actions)
    assert result["final"] == result["initial"]
    assert all(e["from"] in result["final"]["nodes"] and e["to"] in result["final"]["nodes"]
               for e in result["final"]["edges"])


def test_search_reveals_deferred_group_before_focus_with_exact_source_metadata(tmp_path):
    """Hidden Qt facts remain searchable; selecting a result restores evidence before focus."""
    content, _ = write_view(tmp_path)
    result = execute(content, """
searchInput.value = '<Widget>'; searchInput.handlers.input();
if (searchResults.children.length !== 1) throw Error('deferred search result unavailable');
searchResults.children[0].onclick();
if (!document.getElementById('info-content').innerHTML.includes('src/Widget.qml'))
  throw Error('revealed source evidence missing');
if (nodesDS.get('n0').metadata.qml.raw_name !== 'deferred') throw Error('metadata changed');
if (nodesDS.get('n0').qt_qml.qml.raw_name !== 'deferred') throw Error('public Qt projection changed');
""")
    assert result["focusChecks"] == [{"id": "n0", "present": True}]
    assert "n0" in result["final"]["nodes"]
    assert not result["final"]["checked"] and result["final"]["indeterminate"]
    source = next(n for n in result["rawNodes"] if n["id"] == "n0")
    assert source["source_location"] == "L3-L4"
    assert source["attributes"]["public"] == "retained"
    assert all(e["from"] in result["final"]["nodes"] and e["to"] in result["final"]["nodes"]
               for e in result["final"]["edges"])


@pytest.mark.parametrize("grouped", [False, True])
def test_small_view_stays_usable_with_select_all_unchecked(tmp_path, grouped):
    """An overview may contain every small group without implying explicit Select All."""
    graph = nx.Graph()
    graph.add_node("a", label="A")
    graph.add_node("b", label="B")
    path = tmp_path / "small.html"
    assert to_html(graph, {0: ["a", "b"]} if grouped else {}, str(path), learning_overlay={})
    result = execute(path.read_text(encoding="utf-8"))
    assert set(result["constructed"]["nodes"]) == {"a", "b"}
    assert not result["initial"]["checked"] and not result["initial"]["indeterminate"]
    assert ("Architecture overview" if grouped else "Source graph") in result["initial"]["caption"]


def test_partial_small_membership_keeps_ungrouped_facts_recoverable(tmp_path):
    """Explicit selection and search must not strand a node absent from the legend."""
    graph = nx.Graph()
    graph.add_node("a", label="Grouped")
    graph.add_node("b", label="Ungrouped")
    graph.add_edge("a", "b", relation="uses")
    path = tmp_path / "partial.html"
    assert to_html(graph, {1: ["a"]}, str(path), learning_overlay={})
    content = path.read_text(encoding="utf-8")
    result = execute(content, """
focusNode('b');
if (!nodesDS.get('b') || edgesDS.map.size !== 1) throw Error('ungrouped result was stranded');
resetOverview();
toggleAllCommunities(false);
""")
    assert result["constructed"]["nodes"] == ["a"]
    assert result["final"]["nodes"] == ["a", "b"]
    assert result["final"]["checked"]
    assert result["focusChecks"] == [{"id": "b", "present": True}]
