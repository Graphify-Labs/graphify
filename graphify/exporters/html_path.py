"""html_path: the path finder page written next to graph.html.

Holds every node of the graph, even when graph.html shows an aggregated
community view, so any two symbols can be connected offline.
"""
from __future__ import annotations

from pathlib import Path
import json
import math
import networkx as nx
from graphify.paths import write_text_atomic
from graphify.security import sanitize_label


PATH_PAGE_NAME = "graph-path.html"
_DATA_PLACEHOLDER = "__GRAPH_DATA__"

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>graphify - path finder</title>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"></script>
<style>
  :root {
    --bg: #0f0f1a; --panel: #1a1a2e; --border: #2a2a4e; --input-border: #3a3a5e;
    --text: #e0e0e0; --text-2: #aaa; --muted: #777; --accent: #6db89a; --node: #4E79A7; --edge-label-bg: #0f0f1a;
  }
  [data-theme="light"] {
    --bg: #ffffff; --panel: #f8f9fa; --border: #d9dee5; --input-border: #c3cad4;
    --text: #222222; --text-2: #666666; --muted: #888888; --accent: #2e8b6a; --node: #4E79A7; --edge-label-bg: #ffffff;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; min-width: 0; }
  #sidebar { width: 320px; background: var(--panel); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  #controls { padding: 12px; border-bottom: 1px solid var(--border); }
  #controls a { display: block; font-size: 12px; color: var(--accent); margin-bottom: 10px; text-decoration: none; }
  .field { position: relative; margin-bottom: 8px; }
  .field label { display: block; font-size: 11px; color: var(--text-2); margin-bottom: 3px; }
  .field input { width: 100%; background: var(--bg); border: 1px solid var(--input-border); color: var(--text); padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  .field input:focus { border-color: var(--accent); }
  .file { font-size: 11px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .results { position: absolute; z-index: 2; left: 0; right: 0; max-height: 260px; overflow-y: auto; background: var(--panel); border: 1px solid var(--input-border); border-radius: 6px; margin-top: 2px; }
  .results[hidden] { display: none; }
  .result { padding: 5px 8px; cursor: pointer; font-size: 12px; }
  .result:hover { background: var(--border); }
  .result .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  #direction { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); cursor: pointer; }
  #summary { padding: 12px; font-size: 13px; color: var(--text-2); line-height: 1.5; }
  #summary b { color: var(--accent); }
  #hops { flex: 1; overflow-y: auto; padding: 0 12px 12px; list-style: none; }
  .hop { padding: 5px 0; }
  .hop .name { font-size: 12px; font-weight: 600; overflow-wrap: anywhere; }
  .hop .edge { font-size: 11px; color: var(--text-2); padding: 4px 0 0 8px; }
  @media (max-width: 700px) {
    body { flex-direction: column; }
    #graph { flex: 1 1 50%; }
    #sidebar { width: 100%; flex: 1 1 50%; border-left: none; border-top: 1px solid var(--border); }
  }
</style>
<script>
(function () {
  var pref = null;
  try { pref = localStorage.getItem('graphify-theme'); } catch (e) {}
  var t = pref === 'light' ? 'light'
    : pref === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light'
    : 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();
</script>
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="controls">
    <a href="graph.html">&larr; Back to the full graph</a>
    <div class="field">
      <label for="from">From</label>
      <input id="from" type="text" placeholder="Search any symbol or file..." autocomplete="off">
      <div class="results" hidden></div>
    </div>
    <div class="field">
      <label for="to">To</label>
      <input id="to" type="text" placeholder="Search any symbol or file..." autocomplete="off">
      <div class="results" hidden></div>
    </div>
    <label id="direction"><input id="undirected" type="checkbox">Ignore arrow direction</label>
  </div>
  <div id="summary">Pick two nodes to see the shortest route between them.</div>
  <ol id="hops"></ol>
</div>
<script>
const GRAPH = __GRAPH_DATA__;
const MAX_RESULTS = 40;
const COLUMN_WIDTH = 260;
const ROW_HEIGHT = 200;
const ZIGZAG_OFFSET = 50;
const MIN_COLUMNS = 2;
const ENDPOINT_SIZE = 16;
const STEP_SIZE = 10;
const CONTAINS_RELATION = 'contains';

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const NODES = GRAPH.nodes.map(([label, file, location], index) => ({ index, label, file, location, lower: label.toLowerCase() }));
const EDGES = GRAPH.edges.map(([from, to, relation, confidence, score]) => ({
  from, to, relation: GRAPH.relations[relation], confidence: GRAPH.confidences[confidence], score,
}));

// Same traversal as `graphify path`: arrows are followed, and a symbol may step
// back out to the file that contains it. Unticking direction allows every edge
// both ways.
function buildAdjacency(undirected) {
  const adjacency = NODES.map(() => []);
  EDGES.forEach(e => {
    adjacency[e.from].push(e.to);
    if (undirected || e.relation === CONTAINS_RELATION) adjacency[e.to].push(e.from);
  });
  return adjacency;
}

function shortestRoute(start, goal, adjacency) {
  const parent = new Int32Array(NODES.length).fill(-1);
  parent[start] = start;
  const queue = [start];
  for (let head = 0; head < queue.length; head++) {
    const current = queue[head];
    if (current === goal) break;
    for (const next of adjacency[current]) {
      if (parent[next] === -1) {
        parent[next] = current;
        queue.push(next);
      }
    }
  }
  if (parent[goal] === -1) return null;
  const route = [goal];
  while (route[route.length - 1] !== start) route.push(parent[route[route.length - 1]]);
  return route.reverse();
}

const edgesByPair = new Map();
EDGES.forEach(e => {
  const key = `${e.from}>${e.to}`;
  if (!edgesByPair.has(key)) edgesByPair.set(key, []);
  edgesByPair.get(key).push(e);
});
const edgesBetween = (a, b) => (edgesByPair.get(`${a}>${b}`) || []).concat(edgesByPair.get(`${b}>${a}`) || []);

function edgeText(e) {
  return e.confidence === 'INFERRED' || e.confidence === 'AMBIGUOUS'
    ? `${e.relation} [${e.confidence}${e.score === null ? '' : ' ' + e.score.toFixed(2)}]`
    : e.relation;
}

const fileText = n => n.location ? `${n.file}:${n.location}` : n.file;

const selected = { from: null, to: null };
const network = new vis.Network(document.getElementById('graph'), { nodes: [], edges: [] }, {
  physics: { enabled: false },
  interaction: { hover: true, tooltipDelay: 100, keyboard: false },
  nodes: { shape: 'dot', borderWidth: 2 },
  edges: { smooth: false, arrows: { to: { enabled: true, scaleFactor: 0.6 } } },
});

// Lays the route out in rows that fold back on themselves, so a long route stays
// readable and consecutive nodes stay next to each other.
function nodePosition(step, columns) {
  const row = Math.floor(step / columns);
  const column = row % 2 === 0 ? step % columns : columns - 1 - (step % columns);
  return { x: column * COLUMN_WIDTH, y: row * ROW_HEIGHT + (step % 2 === 0 ? 0 : ZIGZAG_OFFSET) };
}

function draw(route) {
  const container = document.getElementById('graph');
  const columns = Math.max(MIN_COLUMNS, Math.floor(container.clientWidth / COLUMN_WIDTH));
  const accent = css('--accent');
  const text = css('--text');
  const nodes = route.map((index, step) => {
    const n = NODES[index];
    const endpoint = step === 0 || step === route.length - 1;
    const color = endpoint ? accent : css('--node');
    return Object.assign(nodePosition(step, columns), {
      id: index, label: n.label, title: fileText(n), size: endpoint ? ENDPOINT_SIZE : STEP_SIZE,
      color: { background: color, border: color },
      font: { color: text, size: 14, bold: endpoint },
    });
  });
  const edges = [];
  for (let step = 0; step + 1 < route.length; step++) {
    edgesBetween(route[step], route[step + 1]).forEach(e => edges.push({
      from: e.from, to: e.to, label: edgeText(e), dashes: e.confidence !== 'EXTRACTED',
      color: { color: accent, highlight: accent, hover: accent }, width: 2,
      font: { color: css('--text-2'), size: 11, strokeWidth: 0, background: css('--edge-label-bg'), align: 'middle' },
    }));
  }
  network.setData({ nodes, edges });
  network.once('afterDrawing', () => network.fit());
}

function clearRoute(message) {
  network.setData({ nodes: [], edges: [] });
  document.getElementById('summary').textContent = message;
  document.getElementById('hops').replaceChildren();
}

function listRoute(route) {
  const hops = document.getElementById('hops');
  hops.replaceChildren();
  route.forEach((index, step) => {
    const n = NODES[index];
    const item = document.createElement('li');
    item.className = 'hop';
    const name = document.createElement('div');
    name.className = 'name';
    name.textContent = n.label;
    const file = document.createElement('div');
    file.className = 'file';
    file.textContent = fileText(n);
    file.title = fileText(n);
    item.append(name, file);
    if (step + 1 < route.length) {
      edgesBetween(index, route[step + 1]).forEach(e => {
        const edge = document.createElement('div');
        edge.className = 'edge';
        edge.textContent = `${e.from === index ? '\\u2193' : '\\u2191'} ${edgeText(e)}`;
        item.append(edge);
      });
    }
    hops.append(item);
  });
}

function update() {
  if (selected.from === null || selected.to === null) return;
  if (selected.from === selected.to) {
    clearRoute('From and To are the same node.');
    return;
  }
  const undirected = document.getElementById('undirected').checked;
  const route = shortestRoute(selected.from, selected.to, buildAdjacency(undirected));
  if (route === null) {
    clearRoute(undirected
      ? 'These two nodes are not connected.'
      : 'No route follows the arrows. Tick "Ignore arrow direction" to search both ways.');
    return;
  }
  const hopCount = route.length - 1;
  const summary = document.getElementById('summary');
  const count = document.createElement('b');
  count.textContent = `${hopCount} ${hopCount === 1 ? 'hop' : 'hops'}`;
  summary.replaceChildren(count, ' \\u00b7 dashed lines are inferred, not read directly from code');
  listRoute(route);
  draw(route);
}

function matches(query) {
  const q = query.toLowerCase();
  const rank = n => n.lower === q ? 0 : n.lower.startsWith(q) ? 1 : 2;
  return NODES.filter(n => n.lower.includes(q))
    .sort((a, b) => rank(a) - rank(b) || a.label.length - b.label.length || a.file.localeCompare(b.file))
    .slice(0, MAX_RESULTS);
}

['from', 'to'].forEach(key => {
  const input = document.getElementById(key);
  const results = input.parentElement.querySelector('.results');
  input.addEventListener('input', () => {
    selected[key] = null;
    results.replaceChildren();
    const query = input.value.trim();
    if (!query) { results.hidden = true; return; }
    matches(query).forEach(n => {
      const row = document.createElement('div');
      row.className = 'result';
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = n.label;
      const file = document.createElement('div');
      file.className = 'file';
      file.textContent = fileText(n);
      row.append(name, file);
      row.addEventListener('click', () => {
        selected[key] = n.index;
        input.value = n.label;
        input.title = fileText(n);
        results.hidden = true;
        update();
      });
      results.append(row);
    });
    results.hidden = results.childElementCount === 0;
  });
  document.addEventListener('click', e => {
    if (!input.parentElement.contains(e.target)) results.hidden = true;
  });
});
document.getElementById('undirected').addEventListener('change', update);
</script>
</body>
</html>
"""


def _graph_data(G: nx.Graph) -> dict:
    """Compact node and edge tables; edges keep their true direction (_src/_tgt)."""
    node_ids = sorted(G.nodes)
    index_of = {node_id: i for i, node_id in enumerate(node_ids)}
    nodes = [
        [
            sanitize_label(str(G.nodes[n].get("label") or n)),
            sanitize_label(str(G.nodes[n].get("source_file") or "")),
            sanitize_label(str(G.nodes[n].get("source_location") or "")),
        ]
        for n in node_ids
    ]
    relations: dict[str, int] = {}
    confidences: dict[str, int] = {}
    edges = []
    for u, v, d in G.edges(data=True):
        relation = sanitize_label(str(d.get("relation") or "related"))
        confidence = sanitize_label(str(d.get("confidence") or ""))
        score = d.get("confidence_score")
        usable_score = isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score)
        edges.append([
            index_of.get(d.get("_src", u), index_of[u]),
            index_of.get(d.get("_tgt", v), index_of[v]),
            relations.setdefault(relation, len(relations)),
            confidences.setdefault(confidence, len(confidences)),
            score if usable_score else None,
        ])
    return {"nodes": nodes, "edges": edges, "relations": list(relations), "confidences": list(confidences)}


def write_path_page(G: nx.Graph, graph_html_path: str) -> None:
    """Write the path finder next to graph.html."""
    data = json.dumps(_graph_data(G), separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    target = Path(graph_html_path).with_name(PATH_PAGE_NAME)
    write_text_atomic(str(target), _PAGE.replace(_DATA_PLACEHOLDER, data))
