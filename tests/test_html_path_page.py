"""graph-path.html finds a route between any two nodes, offline, next to graph.html.

Routes are checked by running the page script in Node against a small DOM mock.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import subprocess

import networkx as nx
import pytest

import graphify.__main__ as mainmod
from graphify.exporters.html import to_html
from graphify.exporters.html_path import PATH_PAGE_NAME, write_path_page

NODE_TIMEOUT_SECONDS = 60
CROSS_CHECK_SEED = 7
CROSS_CHECK_NODE_COUNT = 10
CROSS_CHECK_EDGE_COUNT = 14
CROSS_CHECK_RELATIONS = ["calls", "contains", "references"]
MANY_MATCHES = 60
DANGEROUS_LABELS = [
    "foo <!-- bar components the panel",
    "code:vue (<script setup>)",
    "end </script> tail",
]

_MOCKS = r"""
class Elem {
  constructor() {
    this._text = ''; this.children = []; this.listeners = {}; this.hidden = false;
    this.value = ''; this.checked = false; this.title = ''; this.clientWidth = 800;
  }
  get textContent() { return this._text; }
  set textContent(text) { this._text = text; this.children = []; }
  get childElementCount() { return this.children.length; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  addEventListener(type, listener) { (this.listeners[type] = this.listeners[type] || []).push(listener); }
  fire(type, event) { (this.listeners[type] || []).forEach(listener => listener(event)); }
}

const elements = {};
function makeField() {
  const input = new Elem();
  const results = new Elem();
  input.results = results;
  input.parentElement = { querySelector: () => results, contains: () => false };
  return input;
}
const document = {
  documentElement: {},
  getElementById(id) {
    if (!elements[id]) elements[id] = id === 'from' || id === 'to' ? makeField() : new Elem();
    return elements[id];
  },
  createElement: () => new Elem(),
  addEventListener() {},
};
const getComputedStyle = () => ({ getPropertyValue: () => '#000000' });
const vis = {
  Network: class {
    constructor() { this.data = { nodes: [], edges: [] }; }
    setData(data) { this.data = data; }
    once() {}
    fit() {}
  },
};
"""

_HELPERS = r"""
const t_text = el => typeof el === 'string' ? el : el.children.length ? el.children.map(t_text).join('') : el.textContent;
function t_type(key, query) {
  const input = document.getElementById(key);
  input.value = query;
  input.fire('input');
  return input.results.children;
}
function t_pick(key, label) {
  t_type(key, label).find(row => row.children[0].textContent === label).fire('click');
}
function t_route(from, to) {
  t_pick('from', from);
  t_pick('to', to);
}
function t_ignoreDirection() {
  const checkbox = document.getElementById('undirected');
  checkbox.checked = true;
  checkbox.fire('change');
}
const t_state = () => ({
  summary: t_text(document.getElementById('summary')),
  hops: document.getElementById('hops').children.map(li => li.children[0].textContent),
  files: document.getElementById('hops').children.map(li => li.children[1].textContent),
  edgeTexts: document.getElementById('hops').children.flatMap(li => li.children.slice(2).map(e => e.textContent)),
  drawnNodes: network.data.nodes.map(n => n.label),
  drawnEdges: network.data.edges.map(e => ({ label: e.label, dashes: e.dashes })),
});
const t_emit = value => console.log('OUTPUT:' + JSON.stringify(value));
"""


def _run_page(page_path, scenario: str, tmp_path) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    html = page_path.read_text(encoding="utf-8")
    script = re.search(r"<script>\s*(const GRAPH = .*?)</script>", html, re.DOTALL)
    assert script, "page script not found"
    harness = tmp_path / "harness.js"
    harness.write_text(_MOCKS + script.group(1) + _HELPERS + scenario, encoding="utf-8")
    proc = subprocess.run(
        [node, str(harness)], capture_output=True, text=True, encoding="utf-8", timeout=NODE_TIMEOUT_SECONDS,
    )
    assert proc.returncode == 0, proc.stderr
    output = re.search(r"OUTPUT:(.*)", proc.stdout)
    assert output, proc.stdout
    return json.loads(output.group(1))


def _embedded_graph(page_path) -> dict:
    html = page_path.read_text(encoding="utf-8")
    data = re.search(r"const GRAPH = (.*?);\nconst MAX_RESULTS", html, re.DOTALL)
    assert data, "embedded graph not found"
    return json.loads(data.group(1))


def _graph(edges, graph_type=nx.DiGraph):
    """edges: (source, target, relation[, extra edge attributes])."""
    G = graph_type()
    for source, target, relation, *extra in edges:
        for node_id in (source, target):
            if node_id not in G:
                G.add_node(node_id, label=node_id.upper(), source_file=f"{node_id}.py", source_location="L1")
        G.add_edge(source, target, relation=relation, confidence="EXTRACTED", **(extra[0] if extra else {}))
    return G


def _page(tmp_path, G):
    write_path_page(G, str(tmp_path / "graph.html"))
    return tmp_path / PATH_PAGE_NAME


def _html_graph():
    G = nx.Graph()
    for node_id in ("a", "b", "c", "d"):
        G.add_node(node_id, label=node_id.upper(), file_type="code", source_file=f"{node_id}.py")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    G.add_edge("b", "c", relation="calls", confidence="EXTRACTED")
    G.add_edge("c", "d", relation="calls", confidence="EXTRACTED")
    return G, {0: ["a", "b"], 1: ["c", "d"]}


def test_to_html_writes_the_page_and_links_to_it(tmp_path):
    G, communities = _html_graph()
    out = tmp_path / "graph.html"
    assert to_html(G, communities, str(out)) is True
    assert f'href="{PATH_PAGE_NAME}"' in out.read_text(encoding="utf-8")
    assert len(_embedded_graph(tmp_path / PATH_PAGE_NAME)["nodes"]) == G.number_of_nodes()
    assert 'href="graph.html"' in (tmp_path / PATH_PAGE_NAME).read_text(encoding="utf-8")


def test_aggregated_view_still_gets_every_node_on_the_page(tmp_path):
    G, communities = _html_graph()
    out = tmp_path / "graph.html"
    assert to_html(G, communities, str(out), node_limit=2) is True
    html = out.read_text(encoding="utf-8")
    assert "cross-community edges" in html
    assert f'href="{PATH_PAGE_NAME}"' in html
    graph = _embedded_graph(tmp_path / PATH_PAGE_NAME)
    assert sorted(node[0] for node in graph["nodes"]) == ["A", "B", "C", "D"]
    assert len(graph["edges"]) == G.number_of_edges()


def test_no_page_when_the_graph_is_too_large_to_export(tmp_path, monkeypatch):
    G, communities = _html_graph()
    monkeypatch.setenv("GRAPHIFY_VIZ_NODE_LIMIT", "1")
    with pytest.raises(ValueError):
        to_html(G, communities, str(tmp_path / "graph.html"))
    assert not (tmp_path / PATH_PAGE_NAME).exists()


def test_no_page_when_aggregation_is_not_useful(tmp_path):
    G, _ = _html_graph()
    out = tmp_path / "graph.html"
    assert to_html(G, {0: list(G.nodes)}, str(out), node_limit=2) is False
    assert not (tmp_path / PATH_PAGE_NAME).exists()


def test_undirected_storage_keeps_the_true_edge_direction(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_edge("a", "b", relation="calls", _src="b", _tgt="a")
    graph = _embedded_graph(_page(tmp_path, G))
    labels = [node[0] for node in graph["nodes"]]
    source, target = graph["edges"][0][:2]
    assert (labels[source], labels[target]) == ("B", "A")


def test_multigraph_keeps_parallel_edges(tmp_path):
    G = _graph([("a", "b", "calls"), ("a", "b", "references")], nx.MultiDiGraph)
    graph = _embedded_graph(_page(tmp_path, G))
    assert len(graph["edges"]) == 2
    assert sorted(graph["relations"]) == ["calls", "references"]


def test_stale_direction_falls_back_to_the_edge_endpoints(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="A")
    G.add_node("b", label="B")
    G.add_edge("a", "b", relation="calls", _src="merged_away", _tgt="b")
    graph = _embedded_graph(_page(tmp_path, G))
    labels = [node[0] for node in graph["nodes"]]
    source, target = graph["edges"][0][:2]
    assert (labels[source], labels[target]) == ("A", "B")


@pytest.mark.parametrize("score", [float("nan"), float("inf"), True, "0.5", None])
def test_unusable_score_is_dropped(tmp_path, score):
    G = _graph([("a", "b", "calls", {"confidence_score": score})])
    graph = _embedded_graph(_page(tmp_path, G))
    assert graph["edges"][0][4] is None


def test_missing_label_falls_back_to_the_id(tmp_path):
    G = nx.Graph()
    G.add_node("only_id")
    graph = _embedded_graph(_page(tmp_path, G))
    assert graph["nodes"] == [["only_id", "", ""]]


def test_labels_cannot_break_out_of_the_script(tmp_path):
    G = nx.Graph()
    for i, label in enumerate(DANGEROUS_LABELS):
        G.add_node(f"n{i}", label=label, source_file=label, source_location=label)
    page = _page(tmp_path, G)
    html = page.read_text(encoding="utf-8")
    assert "<!--" not in html
    assert "<script setup" not in html
    assert "</script> tail" not in html
    assert html.count("<script") == html.count("</script")
    assert sorted(node[0] for node in _embedded_graph(page)["nodes"]) == sorted(DANGEROUS_LABELS)


def test_route_follows_the_arrows_and_takes_the_shortest_way(tmp_path):
    G = _graph([("a", "b", "calls"), ("b", "c", "calls"), ("a", "x", "calls"), ("x", "y", "calls"), ("y", "c", "calls")])
    result = _run_page(_page(tmp_path, G), "t_route('A', 'C'); t_emit(t_state());", tmp_path)
    assert result["hops"] == ["A", "B", "C"]
    assert result["summary"].startswith("2 hops")
    assert "·" in result["summary"]
    assert result["files"] == ["a.py:L1", "b.py:L1", "c.py:L1"]
    assert result["edgeTexts"] == ["↓ calls", "↓ calls"]
    assert result["drawnNodes"] == ["A", "B", "C"]


def test_single_hop_summary_is_singular(tmp_path):
    result = _run_page(_page(tmp_path, _graph([("a", "b", "calls")])), "t_route('A', 'B'); t_emit(t_state());", tmp_path)
    assert result["summary"].startswith("1 hop ")


def test_going_against_the_arrows_needs_the_checkbox(tmp_path):
    G = _graph([("a", "b", "calls"), ("b", "c", "calls")])
    result = _run_page(_page(tmp_path, G), """
t_route('C', 'A');
const blocked = t_state();
t_ignoreDirection();
t_emit({ blocked, allowed: t_state() });
""", tmp_path)
    assert "No route follows the arrows" in result["blocked"]["summary"]
    assert result["blocked"]["hops"] == []
    assert result["blocked"]["drawnNodes"] == []
    assert result["allowed"]["hops"] == ["C", "B", "A"]
    assert result["allowed"]["edgeTexts"] == ["↑ calls", "↑ calls"]


def test_a_symbol_can_step_back_to_the_file_that_contains_it(tmp_path):
    G = _graph([("file", "symbol", "contains"), ("file", "sibling", "contains")])
    result = _run_page(_page(tmp_path, G), "t_route('SYMBOL', 'SIBLING'); t_emit(t_state());", tmp_path)
    assert result["hops"] == ["SYMBOL", "FILE", "SIBLING"]


def test_unconnected_and_identical_endpoints_explain_themselves(tmp_path):
    G = _graph([("a", "b", "calls"), ("x", "y", "calls")])
    result = _run_page(_page(tmp_path, G), """
t_ignoreDirection();
t_route('A', 'X');
const unconnected = t_state();
t_route('A', 'A');
t_emit({ unconnected, identical: t_state() });
""", tmp_path)
    assert result["unconnected"]["summary"] == "These two nodes are not connected."
    assert result["identical"]["summary"] == "From and To are the same node."


def test_changing_an_endpoint_clears_it_until_a_new_one_is_picked(tmp_path):
    G = _graph([("a", "b", "calls"), ("b", "c", "calls"), ("c", "a", "calls")])
    result = _run_page(_page(tmp_path, G), """
t_route('A', 'C');
t_type('to', 'B');
t_ignoreDirection();
const whileTyping = t_state();
t_pick('to', 'B');
t_emit({ whileTyping, picked: t_state() });
""", tmp_path)
    assert result["whileTyping"]["hops"] == ["A", "B", "C"]
    assert result["picked"]["hops"] == ["A", "B"]


def test_inferred_edges_are_dashed_and_show_their_score(tmp_path):
    G = _graph([("a", "b", "calls")])
    G.add_node("c", label="C", source_file="c.py")
    G.add_edge("b", "c", relation="uses", confidence="INFERRED", confidence_score=0.5)
    result = _run_page(_page(tmp_path, G), "t_route('A', 'C'); t_emit(t_state());", tmp_path)
    assert result["drawnEdges"] == [
        {"label": "calls", "dashes": False},
        {"label": "uses [INFERRED 0.50]", "dashes": True},
    ]


def test_location_is_left_out_when_the_node_has_none(tmp_path):
    G = nx.DiGraph()
    G.add_node("a", label="A", source_file="a.py")
    G.add_node("b", label="B")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    result = _run_page(_page(tmp_path, G), "t_route('A', 'B'); t_emit(t_state());", tmp_path)
    assert result["files"] == ["a.py", ""]


def test_search_ranks_exact_then_prefix_and_caps_the_list(tmp_path):
    G = nx.DiGraph()
    for i in range(MANY_MATCHES):
        G.add_node(f"n{i}", label=f"xfoo{i}", source_file="a.py")
    G.add_node("prefix", label="foobar", source_file="a.py")
    G.add_node("exact", label="foo", source_file="a.py")
    result = _run_page(_page(tmp_path, G), """
const rows = t_type('from', 'FOO');
t_emit({
  labels: rows.map(row => row.children[0].textContent),
  maxResults: MAX_RESULTS,
  resultsHidden: document.getElementById('from').results.hidden,
  noMatches: t_type('from', 'nothing matches this').length,
  hiddenWithoutMatches: document.getElementById('from').results.hidden,
});
""", tmp_path)
    assert result["labels"][:2] == ["foo", "foobar"]
    assert len(result["labels"]) == result["maxResults"]
    assert result["resultsHidden"] is False
    assert result["noMatches"] == 0
    assert result["hiddenWithoutMatches"] is True


def test_hop_counts_match_the_path_command(tmp_path, monkeypatch, capsys):
    rng = random.Random(CROSS_CHECK_SEED)
    labels = [f"Symbol{chr(ord('A') + i)}" for i in range(CROSS_CHECK_NODE_COUNT)]
    links = []
    for _ in range(CROSS_CHECK_EDGE_COUNT):
        source, target = rng.sample(labels, 2)
        links.append({
            "source": source, "target": target,
            "relation": rng.choice(CROSS_CHECK_RELATIONS), "confidence": "EXTRACTED",
        })
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"id": label, "label": label, "source_file": "a.py", "community": 0} for label in labels],
        "links": links,
    }), encoding="utf-8")

    G = nx.MultiDiGraph()
    G.add_nodes_from((label, {"label": label, "source_file": "a.py"}) for label in labels)
    G.add_edges_from((link["source"], link["target"], link) for link in links)
    page_hops = _run_page(_page(tmp_path, G), """
const adjacency = buildAdjacency(false);
const hops = {};
NODES.forEach(a => NODES.forEach(b => {
  if (a.index === b.index) return;
  const route = shortestRoute(a.index, b.index, adjacency);
  hops[`${a.label}>${b.label}`] = route === null ? null : route.length - 1;
}));
t_emit(hops);
""", tmp_path)

    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    reachable = 0
    for source in labels:
        for target in labels:
            if source == target:
                continue
            monkeypatch.setattr(
                mainmod.sys, "argv", ["graphify", "path", source, target, "--graph", str(graph_path)],
            )
            try:
                mainmod.main()
            except SystemExit:
                pass
            found = re.search(r"Shortest path \((\d+) hops\)", capsys.readouterr().out)
            command_hops = int(found.group(1)) if found else None
            reachable += command_hops is not None
            assert page_hops[f"{source}>{target}"] == command_hops, f"{source} to {target}"
    assert reachable > 0
