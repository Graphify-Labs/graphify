# graphify reference: Sigma.js + graphology visualization for large graphs

Load this when Step 6's `graph.html` (vis-network) would render more than ~300 nodes — either the aggregated community view on a large corpus, or the raw graph on a smaller one that still clusters into 300+ communities. vis-network runs a live, single-threaded JS forceAtlas2 physics simulation on load (canvas 2D rendering); past a few hundred nodes this stabilization pass is genuinely slow regardless of hardware. The fix is not swapping to a different JS physics engine — it's removing client-side physics entirely: precompute the layout once in Python (fast, uses networkx's optimized implementation) and render only, with sigma.js's WebGL renderer instead of vis-network's canvas 2D renderer.

Output file: `graphify-out/graph_sigma.html` (self-contained, opens directly like `graph.html`).

Beyond the raw performance fix, this view also encodes three things vis-network's `graph.html` doesn't surface at a glance: each community's **dominant content kind** (code/document/paper/image/rationale/concept, drawn as a small icon), its **dominant module** (the top-level directory most of its members live under, drawn as color), and a **left-side filter panel** for both entity kind and relation type — so a code-heavy corpus with a handful of docs sprinkled in doesn't read as one undifferentiated blob.

## Step 1 — build the meta-graph and precompute layout in Python

Adjust `MIN_COMMUNITY_SIZE` (20 is a reasonable default — communities below this rarely appear in God Nodes / navigation and just add render cost) and `INPUT_PATH`/label source to match the current run.

```python
import json
import math
import networkx as nx
from pathlib import Path
from collections import Counter, defaultdict

g_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
labels = json.loads(Path('graphify-out/.graphify_labels.json').read_text(encoding='utf-8'))

# Maps every relation graphify emits (AST-structural and LLM-semantic alike) to
# one of six buckets the filter panel toggles as a group. Keep this in sync
# with the relation vocabulary in graphify/extract.py if new relations are
# added there — an unmapped relation falls into 'other' rather than crashing.
RELATION_BUCKETS = {
    'calls': 'calls', 'indirect_call': 'calls', 'instantiates': 'calls',
    'contains': 'structure', 'defines': 'structure', 'method': 'structure',
    'implements': 'structure', 'inherits': 'structure',
    'imports': 'imports', 'imports_from': 'imports', 'dynamic_import': 'imports',
    're_exports': 'imports', 'depends_on': 'imports', 'crate_depends_on': 'imports',
    'requires_env': 'imports',
    'references': 'references', 'references_constant': 'references', 'uses': 'references',
    'uses_static_prop': 'references', 'bound_to': 'references', 'listened_by': 'references',
    'cites': 'docs', 'conceptually_related_to': 'docs', 'shares_data_with': 'docs',
    'semantically_similar_to': 'docs', 'rationale_for': 'docs',
    'participate_in': 'groups', 'implement': 'groups', 'form': 'groups',
}

def top_level_dir(source_file: str) -> str:
    if not source_file or '/' not in source_file:
        return '(root)'
    return source_file.split('/')[0]

MIN_COMMUNITY_SIZE = 20
node_attrs = {n['id']: n for n in g_data['nodes']}
comms = defaultdict(list)
for n in g_data['nodes']:
    comms[n['community']].append(n['id'])

significant = {cid: members for cid, members in comms.items() if len(members) >= MIN_COMMUNITY_SIZE}
dropped = len(comms) - len(significant)
if not significant:
    # Every community is below the threshold (plausible on a corpus that
    # clusters into many small communities) - fall back to all of them
    # rather than crashing on an empty meta-graph downstream.
    largest = max((len(m) for m in comms.values()), default=0)
    print(f'No community reaches MIN_COMMUNITY_SIZE={MIN_COMMUNITY_SIZE} (largest: {largest}) - showing all {len(comms)} communities instead.')
    significant = comms
    dropped = 0
node_to_community = {m: cid for cid, members in significant.items() for m in members}

meta = nx.Graph()
for cid, members in significant.items():
    # Dominant file_type (majority vote) drives the icon; dominant top-level
    # directory drives the color. Both are approximations at the community
    # level — a mixed community shows its majority kind/module, not a blend.
    type_counts = Counter(node_attrs[m].get('file_type', 'code') for m in members)
    dir_counts = Counter(top_level_dir(node_attrs[m].get('source_file', '')) for m in members)
    meta.add_node(
        cid, member_count=len(members), label=labels.get(str(cid), f'Community {cid}'),
        file_type=type_counts.most_common(1)[0][0], module=dir_counts.most_common(1)[0][0],
    )

edge_counts = Counter()
edge_buckets = defaultdict(Counter)
# NetworkX <= 3.1 serializes edges as 'links'; some older graph.json files use
# 'edges' instead (same compatibility hazard graphify/build.py and
# graphify/affected.py already guard against) - accept either.
links_key = 'links' if 'links' in g_data else 'edges'
for link in g_data[links_key]:
    cu, cv = node_to_community.get(link['source']), node_to_community.get(link['target'])
    if cu is not None and cv is not None and cu != cv:
        key = (min(cu, cv), max(cu, cv))
        edge_counts[key] += 1
        edge_buckets[key][RELATION_BUCKETS.get(link.get('relation', ''), 'other')] += 1

# Hyperedges (3+ node group relations - participate_in/implement/form) carry
# no source/target, so they never appear in the loop above. Remap each to the
# distinct communities its members span and count it into every pairwise
# combination, mirroring how graphify/export.py's vis-network aggregated view
# remaps hyperedges to community IDs - otherwise 'groups' in RELATION_BUCKETS
# is unreachable and the filter panel's "Groups" checkbox always no-ops.
for he in g_data.get('hyperedges', []):
    he_communities = sorted({node_to_community[m] for m in he.get('nodes', []) if m in node_to_community})
    for i in range(len(he_communities)):
        for j in range(i + 1, len(he_communities)):
            key = (he_communities[i], he_communities[j])
            edge_counts[key] += 1
            edge_buckets[key][RELATION_BUCKETS.get(he.get('relation', ''), 'groups')] += 1

for (cu, cv), w in edge_counts.items():
    meta.add_edge(cu, cv, weight=w, buckets=dict(edge_buckets[(cu, cv)]))

# offline layout — no client-side physics needed at all
pos = nx.forceatlas2_layout(meta, max_iter=800, gravity=1.0, scaling_ratio=4.0, seed=42, weight='weight')

degrees = dict(meta.degree())
max_members = max((meta.nodes[n]['member_count'] for n in meta.nodes), default=1)
xs = [float(p[0]) for p in pos.values()]
ys = [float(p[1]) for p in pos.values()]
xr, yr = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
scaled = {n: ((float(pos[n][0]) - min(xs)) / xr * 1000, (float(pos[n][1]) - min(ys)) / yr * 1000) for n in meta.nodes()}

# Density-aware sizing: a fixed absolute size range (e.g. "3 to 15") looks
# fine at a few dozen communities but overlaps into an unreadable blob once
# forceAtlas2 packs 300+ communities into the same normalized space — the
# same size value covers a much larger *fraction* of the available room as
# node count grows. Calibrate against the layout's own median nearest-
# neighbor distance instead, so sizes stay legible regardless of density.
def _nearest_neighbor_dists(points):
    dists = []
    for i, (x1, y1) in enumerate(points):
        best = min((math.hypot(x1 - x2, y1 - y2) for j, (x2, y2) in enumerate(points) if j != i), default=None)
        if best is not None:
            dists.append(best)
    return dists

nn = _nearest_neighbor_dists(list(scaled.values()))
median_nn = sorted(nn)[len(nn) // 2] if nn else 30.0
SIZE_MIN = max(2.0, median_nn * 0.12)
SIZE_MAX = max(SIZE_MIN * 2, median_nn * 0.45)

nodes_out = []
for n in meta.nodes():
    x, y = scaled[n]
    deg, mc = int(degrees.get(n, 0)), int(meta.nodes[n]['member_count'])
    nodes_out.append({
        'key': str(n), 'label': meta.nodes[n]['label'],
        'x': round(x, 2), 'y': round(y, 2),
        'size': round(SIZE_MIN + (SIZE_MAX - SIZE_MIN) * (mc / max_members) ** 0.5, 2),
        'degree': deg, 'members': mc,
        'fileType': meta.nodes[n]['file_type'], 'module': meta.nodes[n]['module'],
    })
edges_out = [
    {'source': str(u), 'target': str(v), 'weight': int(d.get('weight', 1)), 'buckets': d.get('buckets', {})}
    for u, v, d in meta.edges(data=True)
]

Path('graphify-out/.graphify_sigma_data.json').write_text(
    json.dumps({'nodes': nodes_out, 'edges': edges_out}, ensure_ascii=False), encoding='utf-8')
print(f'meta graph: {len(nodes_out)} nodes, {len(edges_out)} edges — layout precomputed, size range {SIZE_MIN:.1f}-{SIZE_MAX:.1f}, {dropped} communities below MIN_COMMUNITY_SIZE={MIN_COMMUNITY_SIZE} dropped')
```

**Important**: cast every numpy value (`forceatlas2_layout` returns numpy floats) to plain Python `float`/`int` before `json.dumps` — numpy scalars aren't JSON-serializable and will raise `TypeError: Object of type float32 is not JSON serializable`.

## Step 2 — write the HTML template

Write this template to `graphify-out/graph_sigma.html`, with a literal `__GRAPH_DATA__` placeholder where the data goes (substituted in Step 3 — do NOT try to embed the JSON directly while authoring the template, string-templating that much escaping inline is error-prone).

Key implementation notes:
- **Library loading**: sigma@3 ships CJS/ESM only, no browser UMD global. Load libraries as ES modules from `esm.sh` (`https://esm.sh/sigma@3.0.3`, `https://esm.sh/graphology@0.25.4`, `https://esm.sh/@sigma/node-image@3.0.0?deps=sigma@3.0.3`, `https://esm.sh/@sigma/utils@3.0.0?deps=sigma@3.0.3`) via `<script type="module">` — this works fine even when the HTML is opened via `file://`, because the CORS restriction on `file://` only blocks *local relative* fetches, not remote `https://` module imports. **The `?deps=sigma@3.0.3` query parameter on the two `@sigma/*` companion packages is required, not optional.** Without it, esm.sh resolves their `sigma` peer dependency (declared as a range like `>=3.0.0-beta.10`) to a literal broken module path instead of the concrete pinned version — the browser console shows `The requested module '/sigma@>=3.0.0-beta.10/...' does not provide an export named 'NodeProgram'`, that `import` statement throws, and because it's at the top of the module, the ENTIRE script fails before any of your code runs — Sigma is never constructed, the filter panel never populates, and the page renders as a plain black screen with only the (empty) left panel visible. This reproduces even on a small, otherwise-correct example graph — it is not a data-size or layout issue. Verified by actually loading a generated file in a real browser (Chrome via Playwright) and reading the console: the import resolves cleanly once both companion packages carry the matching `?deps=` pin.
- **No physics**: node `x`/`y` come straight from the precomputed data; sigma just renders and handles pan/zoom/click natively via WebGL — no `stabilizationIterationsDone` wait, no lag.
- **Set `autoRescale: false` alongside `itemSizesReference: "positions"`, not just `zoomToSizeRatioFunction`.** These are three independent settings: `zoomToSizeRatioFunction: (ratio) => ratio` alone is what makes size scale *linearly* with zoom rather than by square root. But `autoRescale` (on by default) separately auto-fits/centers the graph's positions in the viewport on load — leaving it on while sizes are position-referenced means the one-time auto-fit repositions the graph without symmetrically adjusting the size scale, so sizes stop being anchored to the coordinate frame you actually laid out (oversized/overlapping nodes, inconsistent-looking zoom response). Sigma's own `fit-sizes-to-positions` example (`packages/storybook/stories/2-advanced-usecases/fit-sizes-to-positions`) combines all three settings together for exactly this reason — do the same: `itemSizesReference: "positions"` + `zoomToSizeRatioFunction: (ratio) => ratio` + `autoRescale: false` on the `Sigma` constructor (https://www.sigmajs.org/docs/advanced/sizes/).
- **`autoRescale: false` also disables sigma's automatic "fit the camera to the graph" behavior on load — you must replace it with an explicit fit, or the page renders as a blank/black screen with nothing visible.** Without `autoRescale`, the camera stays at its default state (near the origin, ratio 1) regardless of where the actual nodes are; since Step 1 lays nodes out over a 0-1000 range, the camera ends up pointed at empty space, not a badly-framed graph. Call `fitViewportToNodes(renderer, graph.nodes(), { animate: false })` from `@sigma/utils` (the same package sigma's own demo uses for this) immediately after constructing the `Sigma` instance, and again — with `animate: true` — anywhere the camera needs to reframe the whole graph (e.g. the reset button). Do NOT use `camera.animatedReset()` for that: it resets to sigma's default state, the exact "pointed at empty space" position this exists to fix. `maxCameraRatio: 10` (rather than a tighter bound like `3`) gives this fit headroom on a small/narrow viewport — the fitted ratio for a 0-1000-unit layout is roughly `1000 / min(viewportWidth, viewportHeight)`, which can exceed a tight bound on a short window and clip the fit.
- **Icons by content kind**: `NodePictogramProgram` (from `@sigma/node-image`) renders each node as a small monochrome glyph tinted by the node's `color` attribute — set `type: "pictogram"` and an `image` data URI per `fileType` (code/document/paper/image/rationale/concept) on every node, and register `nodeProgramClasses: { pictogram: NodePictogramProgram }` on the `Sigma` constructor. **Every icon SVG must declare explicit `width`/`height` attributes, not just `viewBox`.** `@sigma/node-image` dispatches data-URI images through its raster-image path (not the dedicated SVG path, which keys off a literal `.svg` file extension that a data URI never has), and that path sizes the icon from the `<img>` element's intrinsic dimensions — an SVG with only a `viewBox` has no intrinsic size in some browsers, which silently rasterizes to a zero-size (fully transparent, invisible) texture. `viewBox='0 0 24 24' width='24' height='24'` is sufficient; the exact value doesn't matter since sizing at render time comes from the node's `size` attribute, not the icon's own dimensions.
- **Color by module, not degree**: with the icon now carrying "what kind of thing is this", color is free to carry "which part of the codebase is this from" — tint each node by its dominant top-level directory (`module`) using a fixed categorical palette, ranked so the most common modules get the most visually distinct colors and the long tail collapses into one muted gray. This also becomes a clickable legend (see below) — a lightweight grouping tool without a separate library.
- Include: click → highlight neighbors + dim the rest (`nodeReducer`/`edgeReducer`), a text search box that filters by label (respecting active filters) and pans the camera to the match, a left-side panel with checkboxes for entity kind and bucketed relation type, and a clickable module legend that doubles as an isolate/hide-by-module toggle. Filtering and highlighting share one pair of reducers (`applyReducers`) so they compose instead of one clobbering the other's `setSetting` call.
- **Camera-pan targets must come from `renderer.getNodeDisplayData(key)`, not the raw data's `x`/`y`.** Sigma's `Camera` operates in its own normalized display space, not the raw graph coordinates you fed it — panning with the raw values silently targets the wrong point. This is the same pattern sigma's own demo search field uses (`packages/demo/src/views/SearchField.tsx`).
- **Escape any label before it goes through `innerHTML`.** Community labels are LLM-generated from indexed corpus content, and module names come from real directory names — both can legally contain `<`/`>`/`"`. `graphify-out/` is meant to be committed and shared with a team (per the README), so an unescaped label is a stored-XSS path for whoever opens the HTML next. Escape with a small helper before interpolating into `innerHTML`; the search-results list already does this correctly by using `textContent` instead.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Codebase Knowledge Graph (Sigma.js)</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; background: #0b0d12; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #e6e6e6; }
  #container { position: absolute; inset: 0; }
  #ui { position: absolute; top: 12px; left: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 10px 12px; width: 300px; max-height: calc(100vh - 24px); overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
  #ui h1 { font-size: 13px; margin: 0 0 8px; font-weight: 600; color: #fff; }
  #ui .meta { font-size: 11px; color: #9aa0ab; margin-bottom: 8px; }
  #ui h2 { font-size: 11px; margin: 14px 0 6px; color: #9aa0ab; text-transform: uppercase; letter-spacing: 0.04em; border-top: 1px solid #262932; padding-top: 10px; }
  #search { width: 100%; box-sizing: border-box; padding: 6px 8px; border-radius: 6px; border: 1px solid #3a3d46; background: #14161c; color: #fff; font-size: 12px; outline: none; }
  #search:focus { border-color: #5b8def; }
  #results { max-height: 160px; overflow-y: auto; margin-top: 6px; font-size: 11px; }
  #results div { padding: 3px 4px; border-radius: 4px; cursor: pointer; }
  #results div:hover { background: #23262f; }
  .filter-row, .legend-row { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 2px 0; cursor: pointer; user-select: none; }
  .filter-row img, .legend-row .swatch { width: 12px; height: 12px; flex: none; }
  .legend-row .swatch { border-radius: 50%; }
  .legend-row.is-off, .filter-row.is-off { opacity: 0.4; }
  .legend-row .count { color: #6b7280; margin-left: auto; }
  #info { position: absolute; bottom: 12px; left: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 10px 12px; max-width: 380px; font-size: 12px; display: none; }
  #info b { color: #fff; font-size: 13px; }
  #info .stat { color: #9aa0ab; margin-top: 4px; }
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
  <h2>Entity kind</h2>
  <div id="typeFilters"></div>
  <h2>Relation type</h2>
  <div id="bucketFilters"></div>
  <h2>Modules (click to isolate)</h2>
  <div id="moduleLegend"></div>
  <div style="margin-top:10px;"><a class="reset" id="resetBtn">reset view / filters / highlight</a></div>
</div>
<div id="info"></div>

<script type="module">
import Graph from "https://esm.sh/graphology@0.25.4";
import Sigma from "https://esm.sh/sigma@3.0.3";
import { NodePictogramProgram } from "https://esm.sh/@sigma/node-image@3.0.0?deps=sigma@3.0.3";
import { fitViewportToNodes } from "https://esm.sh/@sigma/utils@3.0.0?deps=sigma@3.0.3";

const DATA = __GRAPH_DATA__;

// Material-style monochrome glyphs (alpha-masked, tinted by node color via
// NodePictogramProgram) — one per graphify file_type. `code` unmapped types
// fall back to the code glyph.
const TYPE_ICONS = {
  code: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6zm5.2 0L19.2 12l-4.6-4.6L16 6l6 6-6 6z'/></svg>",
  document: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M6 2c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6H6zm7 7V3.5L18.5 9H13z'/></svg>",
  paper: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M12 2L1 8l11 6 9-4.91V17h2V8L12 2zM5 13.18v4L12 21l7-3.82v-4L12 17l-7-3.82z'/></svg>",
  image: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z'/></svg>",
  rationale: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z'/></svg>",
  concept: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' width='24' height='24'><path fill='black' d='M12 2l2.9 6.26L22 9.27l-5 4.87L18.18 21 12 17.27 5.82 21 7 14.14 2 9.27l7.1-1.01L12 2z'/></svg>",
};
const BUCKET_LABELS = {
  calls: "Calls / invocation", structure: "Structure", imports: "Imports / dependencies",
  references: "References / bindings", docs: "Documentation & concepts", groups: "Groups", other: "Other",
};
const MODULE_PALETTE = ["#4a7fd6","#e0a23a","#d64550","#5fb87a","#9b6bd6","#3ab7bf","#d68a3a","#7a8fa6","#c4548a","#6bbf59"];
const OTHER_MODULE_COLOR = "#5a5f6b";

// Community labels are LLM-generated from indexed corpus content and module
// names are real directory names - both can legally contain HTML metachars.
// Escape before any innerHTML interpolation (textContent is used wherever
// escaping isn't needed instead).
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.getElementById('metaLine').textContent =
  `${DATA.nodes.length} communities · ${DATA.edges.length} cross-community edges · WebGL, precomputed layout`;

// Rank modules by member count so the most common ones get the most
// visually distinct colors; anything past the palette's length shares gray.
const moduleCounts = new Map();
for (const n of DATA.nodes) moduleCounts.set(n.module, (moduleCounts.get(n.module) || 0) + 1);
const rankedModules = [...moduleCounts.keys()].sort((a, b) => moduleCounts.get(b) - moduleCounts.get(a));
const moduleColor = new Map(rankedModules.map((m, i) => [m, i < MODULE_PALETTE.length ? MODULE_PALETTE[i] : OTHER_MODULE_COLOR]));

const graph = new Graph();
for (const n of DATA.nodes) {
  graph.addNode(n.key, {
    label: n.label, x: n.x, y: n.y, size: n.size, type: "pictogram",
    color: moduleColor.get(n.module) || OTHER_MODULE_COLOR,
    image: TYPE_ICONS[n.fileType] || TYPE_ICONS.code,
    fileType: n.fileType, module: n.module, members: n.members, degree: n.degree,
  });
}
for (const e of DATA.edges) {
  if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
    graph.addEdge(e.source, e.target, {
      size: Math.min(0.3 + Math.log2(1 + e.weight) * 0.35, 4),
      color: "rgba(150,155,165,0.18)", weight: e.weight, buckets: e.buckets || {},
    });
  }
}

const renderer = new Sigma(graph, document.getElementById("container"), {
  renderLabels: true, labelRenderedSizeThreshold: 8,
  labelFont: "-apple-system, BlinkMacSystemFont, sans-serif", labelColor: { color: "#d8dbe2" }, labelSize: 12,
  defaultEdgeColor: "rgba(150,155,165,0.18)", minCameraRatio: 0.05, maxCameraRatio: 10,
  itemSizesReference: "positions", zoomToSizeRatioFunction: (ratio) => ratio, autoRescale: false,
  defaultNodeType: "pictogram", nodeProgramClasses: { pictogram: NodePictogramProgram },
});

// autoRescale: false (above) trades away sigma's automatic "fit the camera to
// the graph on load" behavior in exchange for sizes staying anchored to the
// real coordinate frame. Without this, the camera sits at its default state
// (roughly the origin, ratio 1) while the actual nodes live wherever Step 1's
// 0-1000 layout put them - which renders as a black screen with nothing
// visible, not a wrong-looking graph. fitViewportToNodes (from @sigma/utils,
// the same package sigma's own demo uses for this) computes the camera state
// that frames every node and applies it once, instantly (no animation, since
// there's nothing to animate from - this is the initial frame).
fitViewportToNodes(renderer, graph.nodes(), { animate: false });

// --- filter + highlight state, combined into one pair of reducers so they compose ---
const activeTypes = new Set(DATA.nodes.map(n => n.fileType));
const activeModules = new Set(rankedModules);
const presentBuckets = new Set();
for (const e of DATA.edges) for (const b of Object.keys(e.buckets || {})) presentBuckets.add(b);
const activeBuckets = new Set(presentBuckets);
let highlightedNode = null;

function isNodeVisible(attrs) {
  return activeTypes.has(attrs.fileType) && activeModules.has(attrs.module);
}
function edgeMatchesActiveBuckets(edgeAttrs) {
  const buckets = Object.keys(edgeAttrs.buckets || {});
  if (!buckets.length) return true; // no bucket breakdown recorded - never hidden by relation filter
  return buckets.some(b => activeBuckets.has(b));
}

function applyReducers() {
  renderer.setSetting("nodeReducer", (node, data) => {
    if (!isNodeVisible(data)) return { ...data, hidden: true };
    if (highlightedNode) {
      const neighbors = new Set(graph.neighbors(highlightedNode)); neighbors.add(highlightedNode);
      if (!neighbors.has(node)) return { ...data, color: "#22242c", label: "", zIndex: 0 };
    }
    return data;
  });
  renderer.setSetting("edgeReducer", (edge, data) => {
    const [s, t] = graph.extremities(edge);
    const endpointsVisible = isNodeVisible(graph.getNodeAttributes(s)) && isNodeVisible(graph.getNodeAttributes(t));
    if (!endpointsVisible || !edgeMatchesActiveBuckets(data)) return { ...data, hidden: true };
    if (highlightedNode) {
      return (s === highlightedNode || t === highlightedNode)
        ? { ...data, color: "rgba(230,230,230,0.55)", size: Math.max(data.size, 1) }
        : { ...data, color: "rgba(150,155,165,0.03)" };
    }
    return data;
  });
  renderer.refresh();
}

function highlightNode(key) {
  highlightedNode = key;
  applyReducers();
  const attrs = graph.getNodeAttributes(key);
  const info = document.getElementById("info");
  info.style.display = "block";
  info.innerHTML = `<b>${escapeHtml(attrs.label)}</b><div class="stat">${attrs.members} member node${attrs.members===1?"":"s"}</div><div class="stat">${attrs.degree} connected communit${attrs.degree===1?"y":"ies"}</div>`;
}
function clearHighlight() {
  highlightedNode = null;
  applyReducers();
  document.getElementById("info").style.display = "none";
}
renderer.on("clickNode", ({ node }) => highlightNode(node));
renderer.on("clickStage", clearHighlight);

// --- entity-kind (file_type) filter checkboxes ---
const typeFiltersEl = document.getElementById("typeFilters");
for (const t of [...activeTypes].sort()) {
  const row = document.createElement("label");
  row.className = "filter-row";
  row.innerHTML = `<input type="checkbox" checked><img src="${TYPE_ICONS[t] || TYPE_ICONS.code}"><span>${escapeHtml(t)}</span>`;
  row.querySelector("input").addEventListener("change", (ev) => {
    ev.target.checked ? activeTypes.add(t) : activeTypes.delete(t);
    row.classList.toggle("is-off", !ev.target.checked);
    applyReducers();
  });
  typeFiltersEl.appendChild(row);
}

// --- relation-bucket filter checkboxes (only buckets actually present) ---
const bucketFiltersEl = document.getElementById("bucketFilters");
for (const b of [...presentBuckets].sort()) {
  const row = document.createElement("label");
  row.className = "filter-row";
  row.innerHTML = `<input type="checkbox" checked><span>${BUCKET_LABELS[b] || b}</span>`;
  row.querySelector("input").addEventListener("change", (ev) => {
    ev.target.checked ? activeBuckets.add(b) : activeBuckets.delete(b);
    row.classList.toggle("is-off", !ev.target.checked);
    applyReducers();
  });
  bucketFiltersEl.appendChild(row);
}

// --- module legend, doubling as an isolate/hide-by-module toggle ---
const moduleLegendEl = document.getElementById("moduleLegend");
for (const m of rankedModules) {
  const row = document.createElement("div");
  row.className = "legend-row";
  row.innerHTML = `<span class="swatch" style="background:${moduleColor.get(m)}"></span><span>${escapeHtml(m)}</span><span class="count">${moduleCounts.get(m)}</span>`;
  row.addEventListener("click", () => {
    activeModules.has(m) ? activeModules.delete(m) : activeModules.add(m);
    row.classList.toggle("is-off", !activeModules.has(m));
    applyReducers();
  });
  moduleLegendEl.appendChild(row);
}

document.getElementById("resetBtn").addEventListener("click", () => {
  activeTypes.clear(); DATA.nodes.forEach(n => activeTypes.add(n.fileType));
  activeModules.clear(); rankedModules.forEach(m => activeModules.add(m));
  activeBuckets.clear(); presentBuckets.forEach(b => activeBuckets.add(b));
  document.querySelectorAll('.filter-row, .legend-row').forEach(el => { el.classList.remove('is-off'); const cb = el.querySelector('input'); if (cb) cb.checked = true; });
  clearHighlight();
  // NOT animatedReset() - that resets to sigma's default camera state, which
  // is the same "pointed at empty space" position fitViewportToNodes exists
  // to fix in the first place (see the comment where it's first called).
  fitViewportToNodes(renderer, graph.nodes(), { animate: true });
});

const searchInput = document.getElementById("search");
const resultsBox = document.getElementById("results");
searchInput.addEventListener("input", () => {
  const q = searchInput.value.trim().toLowerCase();
  resultsBox.innerHTML = "";
  if (!q) return;
  for (const m of DATA.nodes.filter(n => isNodeVisible(n) && n.label.toLowerCase().includes(q)).slice(0, 25)) {
    const div = document.createElement("div");
    div.textContent = `${m.label} (${m.members})`;
    div.addEventListener("click", () => {
      highlightNode(m.key);
      // Camera targets live in sigma's own normalized display space, not the
      // raw data coordinates - getNodeDisplayData() is the same pattern
      // sigma's own demo search field uses (SearchField.tsx).
      const display = renderer.getNodeDisplayData(m.key);
      renderer.getCamera().animate({ x: display.x, y: display.y, ratio: 0.15 }, { duration: 400 });
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
grep -io '</script' graphify-out/graph_sigma.html | wc -l   # must be exactly 1 (the real closing tag)
```

HTML tag names are case-insensitive, so a label containing `</SCRIPT` or `</Script` would corrupt the page exactly the same way — the `-i` flag is required, not cosmetic.

If it's more than 1, a node/edge label contains `</script` — fix by replacing `json.dumps(data, ...)` output's `</script` substring with `<\\/script` (a standard JSON-in-HTML escape) before writing.

## Notes

- This produces a *separate* file (`graph_sigma.html`) alongside vis-network's `graph.html` — don't delete the latter, some users may still want the full uncapped view or the vis-network-specific features (community filter dropdown, confidence-styled edges) that this lighter template doesn't replicate.
- The `MIN_COMMUNITY_SIZE` filter mirrors the same tradeoff as the labeling threshold in Step 5 — communities below it are real but rarely load-bearing for architecture navigation. State the cutoff and the dropped count to the user rather than silently filtering.
- Icon and module-color are both *dominant-vote* approximations at the community level — a community that's 60% code and 40% docs shows only the code icon. This is a reasonable simplification for the aggregated view; it is not accurate for a single mixed-content community and shouldn't be read as "this community contains only code".
- The relation-bucket filter operates on the meta-edge's aggregated bucket breakdown, not individual original edges — unchecking "Calls / invocation" hides a meta-edge only if *none* of the original edges it aggregates fall in a still-checked bucket. A meta-edge that's 90% imports and 10% calls stays visible if either bucket is checked.
- If no community reaches `MIN_COMMUNITY_SIZE`, Step 1 falls back to showing every community rather than producing an empty (and crashing) meta-graph — tell the user this happened rather than silently showing an unfiltered view.
- The "Groups" relation bucket comes from graphify's hyperedges (`participate_in`/`implement`/`form`), which have no `source`/`target` and live in graph.json's separate top-level `hyperedges` array — they're remapped to community-pairs the same way `graphify/export.py`'s vis-network aggregated view already does, so this bucket has real content instead of being permanently empty.
