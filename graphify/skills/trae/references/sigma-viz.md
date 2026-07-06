# graphify reference: Sigma.js + graphology visualization for large graphs

Load this when Step 6's `graph.html` (vis-network) would render more than ~300 nodes — either the aggregated community view on a large corpus, or the raw graph on a smaller one that still clusters into 300+ communities. vis-network runs a live, single-threaded JS forceAtlas2 physics simulation on load (canvas 2D rendering); past a few hundred nodes this stabilization pass is genuinely slow regardless of hardware. The fix is not swapping to a different JS physics engine — it's removing client-side physics entirely: precompute the layout once in Python (fast, uses networkx's optimized implementation) and render only, with sigma.js's WebGL renderer instead of vis-network's canvas 2D renderer.

Output file: `graphify-out/graph_sigma.html` (self-contained, opens directly like `graph.html`).

## Step 1 — build the meta-graph and precompute layout in Python

Adjust `MIN_COMMUNITY_SIZE` (20 is a reasonable default — communities below this rarely appear in God Nodes / navigation and just add render cost) and `INPUT_PATH`/label source to match the current run.

```python
import json
import networkx as nx
from pathlib import Path
from collections import Counter, defaultdict

g_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
labels = json.loads(Path('graphify-out/.graphify_labels.json').read_text(encoding='utf-8'))

MIN_COMMUNITY_SIZE = 20
comms = defaultdict(list)
for n in g_data['nodes']:
    comms[n['community']].append(n['id'])

significant = {cid: members for cid, members in comms.items() if len(members) >= MIN_COMMUNITY_SIZE}
node_to_community = {m: cid for cid, members in significant.items() for m in members}

meta = nx.Graph()
for cid, members in significant.items():
    meta.add_node(cid, member_count=len(members), label=labels.get(str(cid), f'Community {cid}'))

edge_counts = Counter()
for link in g_data['links']:
    cu, cv = node_to_community.get(link['source']), node_to_community.get(link['target'])
    if cu is not None and cv is not None and cu != cv:
        edge_counts[(min(cu, cv), max(cu, cv))] += 1
for (cu, cv), w in edge_counts.items():
    meta.add_edge(cu, cv, weight=w)

# offline layout — no client-side physics needed at all
pos = nx.forceatlas2_layout(meta, max_iter=800, gravity=1.0, scaling_ratio=4.0, seed=42, weight='weight')

degrees = dict(meta.degree())
max_deg = max(degrees.values()) if degrees else 1
max_members = max((meta.nodes[n]['member_count'] for n in meta.nodes), default=1)
xs = [float(p[0]) for p in pos.values()]
ys = [float(p[1]) for p in pos.values()]
xr, yr = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1

nodes_out = []
for n in meta.nodes():
    x, y = float(pos[n][0]), float(pos[n][1])
    deg, mc = int(degrees.get(n, 0)), int(meta.nodes[n]['member_count'])
    nodes_out.append({
        'key': str(n), 'label': meta.nodes[n]['label'],
        'x': round((x - min(xs)) / xr * 1000, 2), 'y': round((y - min(ys)) / yr * 1000, 2),
        'size': round(3 + 12 * (mc / max_members) ** 0.5, 2),
        't': round(deg / max_deg if max_deg else 0, 3),
        'members': mc, 'degree': deg,
    })
edges_out = [{'source': str(u), 'target': str(v), 'weight': int(d.get('weight', 1))}
             for u, v, d in meta.edges(data=True)]

Path('graphify-out/.graphify_sigma_data.json').write_text(
    json.dumps({'nodes': nodes_out, 'edges': edges_out}, ensure_ascii=False), encoding='utf-8')
print(f'meta graph: {len(nodes_out)} nodes, {len(edges_out)} edges — layout precomputed')
```

**Important**: cast every numpy value (`forceatlas2_layout` returns numpy floats) to plain Python `float`/`int` before `json.dumps` — numpy scalars aren't JSON-serializable and will raise `TypeError: Object of type float32 is not JSON serializable`.

## Step 2 — write the HTML template

Write this template to `graphify-out/graph_sigma.html`, with a literal `__GRAPH_DATA__` placeholder where the data goes (substituted in Step 3 — do NOT try to embed the JSON directly while authoring the template, string-templating that much escaping inline is error-prone).

Key implementation notes:
- **Library loading**: sigma@3 ships CJS/ESM only, no browser UMD global. Load both libraries as ES modules from `esm.sh` (`https://esm.sh/sigma@3.0.3`, `https://esm.sh/graphology@0.25.4`) via `<script type="module">` — this works fine even when the HTML is opened via `file://`, because the CORS restriction on `file://` only blocks *local relative* fetches, not remote `https://` module imports.
- **No physics**: node `x`/`y` come straight from the precomputed data; sigma just renders and handles pan/zoom/click natively via WebGL — no `stabilizationIterationsDone` wait, no lag.
- **Node size must scale with zoom**: sigma's default is `itemSizesReference: "screen"` with `zoomToSizeRatioFunction: Math.sqrt` — sizes stay roughly constant on screen regardless of zoom (dampened sqrt scaling), which reads as "not scaling at all" to users expecting a map-like zoom. Set `itemSizesReference: "positions"` + `zoomToSizeRatioFunction: (ratio) => ratio` on the `Sigma` constructor so node size scales directly with the graph's own coordinate system, matching how the layout itself zooms (confirmed against sigma.js's own docs: https://www.sigmajs.org/docs/advanced/sizes/).
- Include: hover/click → highlight neighbors + dim the rest (`nodeReducer`/`edgeReducer`), a text search box that filters by label and pans the camera to the match, and a legend explaining the degree-based color scale.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Codebase Knowledge Graph (Sigma.js)</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; background: #0b0d12; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #e6e6e6; }
  #container { position: absolute; inset: 0; }
  #ui { position: absolute; top: 12px; left: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 10px 12px; width: 300px; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
  #ui h1 { font-size: 13px; margin: 0 0 8px; font-weight: 600; color: #fff; }
  #ui .meta { font-size: 11px; color: #9aa0ab; margin-bottom: 8px; }
  #search { width: 100%; box-sizing: border-box; padding: 6px 8px; border-radius: 6px; border: 1px solid #3a3d46; background: #14161c; color: #fff; font-size: 12px; outline: none; }
  #search:focus { border-color: #5b8def; }
  #results { max-height: 160px; overflow-y: auto; margin-top: 6px; font-size: 11px; }
  #results div { padding: 3px 4px; border-radius: 4px; cursor: pointer; }
  #results div:hover { background: #23262f; }
  #info { position: absolute; bottom: 12px; left: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 10px 12px; max-width: 380px; font-size: 12px; display: none; }
  #info b { color: #fff; font-size: 13px; }
  #info .stat { color: #9aa0ab; margin-top: 4px; }
  #legend { position: absolute; bottom: 12px; right: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 8px 10px; font-size: 10px; color: #9aa0ab; }
  #legend .bar { width: 120px; height: 8px; border-radius: 4px; margin: 4px 0; background: linear-gradient(90deg, #4a7fd6, #e0a23a, #d64550); }
  a.reset { color: #5b8def; cursor: pointer; font-size: 11px; }
</style>
</head>
<body>
<div id="container"></div>
<div id="ui">
  <h1>Codebase Knowledge Graph</h1>
  <div class="meta" id="metaLine"></div>
  <input id="search" type="text" placeholder="Search communities...">
  <div id="results"></div>
  <div style="margin-top:8px;"><a class="reset" id="resetBtn">reset view / clear highlight</a></div>
</div>
<div id="info"></div>
<div id="legend">Node color = connectivity (degree)<div class="bar"></div>low &rarr; high</div>

<script type="module">
import Graph from "https://esm.sh/graphology@0.25.4";
import Sigma from "https://esm.sh/sigma@3.0.3";

const DATA = __GRAPH_DATA__;
document.getElementById('metaLine').textContent =
  `${DATA.nodes.length} communities · ${DATA.edges.length} cross-community edges · WebGL, precomputed layout`;

function lerpColor(t) {
  const stops = [[74,127,214],[224,162,58],[214,69,80]];
  const seg = t <= 0.5 ? 0 : 1;
  const localT = t <= 0.5 ? t / 0.5 : (t - 0.5) / 0.5;
  const a = stops[seg], b = stops[seg + 1];
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*localT)},${Math.round(a[1]+(b[1]-a[1])*localT)},${Math.round(a[2]+(b[2]-a[2])*localT)})`;
}

const graph = new Graph();
for (const n of DATA.nodes) {
  graph.addNode(n.key, { label: n.label, x: n.x, y: n.y, size: n.size, color: lerpColor(n.t), members: n.members, degree: n.degree });
}
for (const e of DATA.edges) {
  if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
    graph.addEdge(e.source, e.target, { size: Math.min(0.3 + Math.log2(1 + e.weight) * 0.35, 4), color: "rgba(150,155,165,0.18)", weight: e.weight });
  }
}

const renderer = new Sigma(graph, document.getElementById("container"), {
  renderLabels: true, labelRenderedSizeThreshold: 8,
  labelFont: "-apple-system, BlinkMacSystemFont, sans-serif", labelColor: { color: "#d8dbe2" }, labelSize: 12,
  defaultEdgeColor: "rgba(150,155,165,0.18)", minCameraRatio: 0.05, maxCameraRatio: 3,
  itemSizesReference: "positions", zoomToSizeRatioFunction: (ratio) => ratio,
});

function clearHighlight() {
  renderer.setSetting("nodeReducer", null);
  renderer.setSetting("edgeReducer", null);
  document.getElementById("info").style.display = "none";
  renderer.refresh();
}
function highlightNode(key) {
  const neighbors = new Set(graph.neighbors(key)); neighbors.add(key);
  renderer.setSetting("nodeReducer", (node, data) => neighbors.has(node) ? data : { ...data, color: "#22242c", label: "", zIndex: 0 });
  renderer.setSetting("edgeReducer", (edge, data) => {
    const [s, t] = graph.extremities(edge);
    return (s === key || t === key) ? { ...data, color: "rgba(230,230,230,0.55)", size: Math.max(data.size, 1) } : { ...data, color: "rgba(150,155,165,0.03)" };
  });
  const attrs = graph.getNodeAttributes(key);
  const info = document.getElementById("info");
  info.style.display = "block";
  info.innerHTML = `<b>${attrs.label}</b><div class="stat">${attrs.members} member node${attrs.members===1?"":"s"}</div><div class="stat">${attrs.degree} connected communit${attrs.degree===1?"y":"ies"}</div>`;
  renderer.refresh();
}
renderer.on("clickNode", ({ node }) => highlightNode(node));
renderer.on("clickStage", clearHighlight);
document.getElementById("resetBtn").addEventListener("click", clearHighlight);

const searchInput = document.getElementById("search");
const resultsBox = document.getElementById("results");
searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim().toLowerCase();
  resultsBox.innerHTML = "";
  if (!q) return;
  for (const m of DATA.nodes.filter(n => n.label.toLowerCase().includes(q)).slice(0, 25)) {
    const div = document.createElement("div");
    div.textContent = `${m.label} (${m.members})`;
    div.addEventListener("click", () => {
      highlightNode(m.key);
      renderer.getCamera().animate({ x: m.x, y: m.y, ratio: 0.15 }, { duration: 400 });
    });
    resultsBox.appendChild(div);
  }
});
</script>
</body>
</html>
```

## Step 3 — inject the data and clean up

```python
import json
from pathlib import Path

data = json.loads(Path('graphify-out/.graphify_sigma_data.json').read_text(encoding='utf-8'))
html = Path('graphify-out/graph_sigma.html').read_text(encoding='utf-8')
html = html.replace('__GRAPH_DATA__', json.dumps(data, ensure_ascii=False))
Path('graphify-out/graph_sigma.html').write_text(html, encoding='utf-8')
Path('graphify-out/.graphify_sigma_data.json').unlink()
```

**Before telling the user it's done**, sanity-check the embedded JSON didn't break the `<script>` tag: a community label containing the literal substring `</script` would prematurely close the script block and corrupt the page. Check with:

```bash
grep -o '</script' graphify-out/graph_sigma.html | wc -l   # must be exactly 1 (the real closing tag)
```

If it's more than 1, a node/edge label contains `</script` — fix by replacing `json.dumps(data, ...)` output's `</script` substring with `<\\/script` (a standard JSON-in-HTML escape) before writing.

## Notes

- This produces a *separate* file (`graph_sigma.html`) alongside vis-network's `graph.html` — don't delete the latter, some users may still want the full uncapped view or the vis-network-specific features (community filter dropdown, confidence-styled edges) that this lighter template doesn't replicate.
- The `MIN_COMMUNITY_SIZE` filter mirrors the same tradeoff as the labeling threshold in Step 5 — communities below it are real but rarely load-bearing for architecture navigation. State the cutoff and the dropped count to the user rather than silently filtering.
