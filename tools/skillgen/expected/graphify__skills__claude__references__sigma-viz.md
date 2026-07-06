# graphify reference: Sigma.js + graphology visualization for large graphs

Load this when Step 6's `graph.html` (vis-network) would render more than ~300 nodes — either the aggregated community view on a large corpus, or the raw graph on a smaller one that still clusters into 300+ communities. vis-network runs a live, single-threaded JS forceAtlas2 physics simulation on load (canvas 2D rendering); past a few hundred nodes this stabilization pass is genuinely slow regardless of hardware. The fix is not swapping to a different JS physics engine — it's removing client-side physics entirely: precompute the layout once in Python (fast, uses networkx's optimized implementation) and render only, with sigma.js's WebGL renderer instead of vis-network's canvas 2D renderer.

Output file: `graphify-out/graph_sigma.html` (self-contained, opens directly like `graph.html`).

Beyond the raw performance fix, this view also encodes things vis-network's `graph.html` doesn't surface at a glance: each community's **dominant content kind** (code/document/paper/image/rationale/concept, drawn as a small icon), its **dominant module** (the top-level directory most of its members live under, drawn as color), a **left-side filter panel** for both entity kind and relation type, **edges colored and labeled by relation type**, **draggable nodes** for manual layout tidying, node labels rendered on their own small background box for readability over a dense tangle of edges, and a **click panel listing every source file a community represents**, filterable and scrollable, where clicking a file opens a **movable dialog with an embedded content preview** (falling back to a working `file://` link when opened on the machine that generated the graph) — so a code-heavy corpus with a handful of docs sprinkled in doesn't read as one undifferentiated blob, and clicking a community gets you to real file content, not just a label.

Good spread alone doesn't read as *structure* — a well-separated layout with every edge drawn at full opacity still looks like a hairball, because nothing visually ties related things together beyond a small color dot. Three more things address that directly: the offline layout **clusters communities by module** (a stronger pull between same-module communities than raw topology alone would produce, so color-coding and position now agree), a **soft region outline is drawn behind each module's cluster** (a translucent hull, not just individual node colors), and **edges below a weight percentile are hidden by default** (with a checkbox to show everything, and any edge touching the currently-highlighted node always shows regardless of weight) so the default view reads as "these are the load-bearing connections" instead of every single one at once.

## Step 1 — build the meta-graph and precompute layout in Python

Adjust `MIN_COMMUNITY_SIZE` (20 is a reasonable default — communities below this rarely appear in God Nodes / navigation and just add render cost) and `INPUT_PATH`/label source to match the current run.

```python
import json
import math
import subprocess
import networkx as nx
from pathlib import Path
from collections import Counter, defaultdict

g_data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))
labels = json.loads(Path('graphify-out/.graphify_labels.json').read_text(encoding='utf-8'))
# .graphify_root records the absolute scan root on THIS machine, letting the
# click panel link straight to a source file. file:// links only resolve on
# the machine that generated the graph - degrade to a plain (still useful,
# copyable) relative path when the marker is missing.
_root_marker = Path('graphify-out/.graphify_root')
SCAN_ROOT = _root_marker.read_text(encoding='utf-8').strip() if _root_marker.exists() else None
REPO_NAME = Path(SCAN_ROOT).name if SCAN_ROOT else None
# Best-effort - a scan root that isn't a git repo (or has no git binary
# available) is common enough (a docs corpus, a partial checkout) that this
# must degrade to None rather than raise; the header line below just omits
# the branch when it's unknown instead of showing a misleading placeholder.
try:
    GIT_BRANCH = subprocess.run(
        ['git', '-C', SCAN_ROOT, 'rev-parse', '--abbrev-ref', 'HEAD'],
        capture_output=True, text=True, timeout=5,
    ).stdout.strip() or None if SCAN_ROOT else None
except (OSError, subprocess.SubprocessError):
    GIT_BRANCH = None

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

PREVIEW_CAP = 8       # only the first N files (of the complete list) get embedded content
PREVIEW_CHARS = 3000  # per-file cap - this is a preview for a dialog, not a full viewer

def read_preview(source_file: str) -> "str | None":
    """Best-effort file preview for the click-panel dialog. None means
    "not attempted" (beyond PREVIEW_CAP) or "unreadable" (missing, binary,
    permission error, no SCAN_ROOT to resolve against) - the dialog falls
    back to just the file:// link in either case, never raises."""
    if not SCAN_ROOT:
        return None
    try:
        text = (Path(SCAN_ROOT) / source_file).read_text(encoding='utf-8', errors='replace')
    except (OSError, UnicodeDecodeError):
        return None
    truncated = len(text) > PREVIEW_CHARS
    return text[:PREVIEW_CHARS] + ('\n… (truncated)' if truncated else '')

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
    # Full distinct file list for the click panel - the UI renders it as a
    # scrollable, filterable list rather than truncating, so send everything
    # rather than a capped sample. Only the first PREVIEW_CAP get embedded
    # content (see read_preview) - a 300-member community's worth of full
    # file contents would bloat the HTML far more than its path list does.
    distinct_files = sorted({node_attrs[m]['source_file'] for m in members if node_attrs[m].get('source_file')})
    files_out = [
        {
            'path': f, 'url': f'file://{SCAN_ROOT}/{f}' if SCAN_ROOT else None,
            'preview': read_preview(f) if i < PREVIEW_CAP else None,
        }
        for i, f in enumerate(distinct_files)
    ]
    meta.add_node(
        cid, member_count=len(members), label=labels.get(str(cid), f'Community {cid}'),
        file_type=type_counts.most_common(1)[0][0], module=dir_counts.most_common(1)[0][0],
        files=files_out,
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

# Module clustering: boost the LAYOUT-ONLY weight (not the real edge weight,
# which still drives rendered thickness/labels) for same-module edges, so
# forceAtlas2's attraction pulls same-module communities toward each other
# more than the raw topology alone would. Without this, module color-coding
# (and the hull below) is the only thing tying a module together visually -
# nodes can be color-matched but scattered anywhere, which reads as chaotic
# even once the general bunching problem is fixed. Tuned jointly with
# scaling_ratio below, not independently - re-verify both together on a
# real multi-hundred-node corpus rather than nudging just one.
#
# A too-high boost actively backfires: it doesn't just plateau, it makes
# bunching WORSE for the largest modules specifically, because a big module
# has many more same-module edges, so the boost compounds - the two largest
# modules on the real production graph visibly collapsed into their own
# dense sub-hairball at boost=15 even though the *average* within/between
# distance ratio looked fine, and was reported as still-too-clumped against
# real output. boost=6 (down from boost=15) prioritizes breaking up that
# hairball over maximizing module separation: within/between distance ratio
# goes 0.550 -> 0.727 (modules less tightly separated, an accepted
# trade-off since the hull overlay still visually groups a module even when
# its nodes aren't packed tightly) while the fraction of nodes within 15%
# of the bounding-box center drops 0.28 -> 0.12 and the median
# nearest-neighbor spacing roughly triples (3.9 -> 10.5 units) - measured
# directly against the current corpus snapshot, not assumed from an older
# pass, since corpus growth alone can shift these numbers even with
# unchanged parameters. If module separation ever matters more than spread
# for a given corpus, raise this back toward 12-15 and re-verify the
# hairball doesn't return.
MODULE_CLUSTER_BOOST = 6
for u, v, d in meta.edges(data=True):
    same_module = meta.nodes[u]['module'] == meta.nodes[v]['module']
    d['layout_weight'] = d['weight'] * MODULE_CLUSTER_BOOST if same_module else d['weight']

# offline layout — no client-side physics needed at all.
#
# linlog=True (logarithmic attraction) plus a node_size repulsion halo
# proportional to member count spreads communities out by actual graph
# structure instead of collapsing almost everything into one dense blob
# near the centroid. The naive defaults (linear attraction, scaling_ratio=4,
# no node_size) packed the vast majority of nodes within 15% of the
# bounding-box center on a real production graph - unreadable, and exactly
# the "nodes are bunched, labels aren't readable" failure mode reported
# multiple times against real output, not a synthetic worst case.
# gravity=0.15 + scaling_ratio=100 (raised again from an earlier 80, paired
# with the MODULE_CLUSTER_BOOST=6 change above) is the current best
# verified balance - always verify spread AND module separation together,
# visually in a real browser, before tuning either further; a purely
# numeric spread proxy has under-predicted "good enough" before, and
# pushing scaling_ratio up alone (without lowering the module boost) trades
# away module separation for less bunching rather than improving both.
# scaling_ratio is raised so far past its default (2.0) specifically to
# compensate for linlog's gentler pull once nodes spread out - lowering it
# re-collapses the layout fast at intermediate values.
max_members = max((meta.nodes[n]['member_count'] for n in meta.nodes), default=1)
node_size = {n: 3 + 12 * (meta.nodes[n]['member_count'] / max_members) ** 0.5 for n in meta.nodes}
pos = nx.forceatlas2_layout(
    meta, max_iter=1000, gravity=0.15, scaling_ratio=100.0, linlog=True,
    node_size=node_size, seed=42, weight='layout_weight',
)
# A "RuntimeWarning: invalid value encountered in divide" from networkx's
# linlog attraction calculation is expected and benign (transient zero-
# distance case during iteration) - verified it does not produce NaN/Inf in
# the final positions on a real 342-node production graph. Don't treat it as
# a failure signal.

degrees = dict(meta.degree())
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
        'files': meta.nodes[n]['files'],
    })
edges_out = [
    {'source': str(u), 'target': str(v), 'weight': int(d.get('weight', 1)), 'buckets': d.get('buckets', {})}
    for u, v, d in meta.edges(data=True)
]

def _convex_hull(points):
    """Andrew's monotone chain, pure stdlib - avoids adding scipy as a
    dependency of this doc just for one shape per module."""
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]

# Module hull shading: a soft region outline behind each module's cluster,
# reinforcing the module-clustering boost above with an explicit visual
# boundary rather than relying on the viewer to infer "these dots are all
# the same color, therefore a group" in a dense view. Expand outward from
# the hull's own centroid so the shape has breathing room around the actual
# node positions instead of hugging them exactly.
HULL_MARGIN = 30
by_module_points = defaultdict(list)
for n in meta.nodes():
    by_module_points[meta.nodes[n]['module']].append(scaled[n])
hulls_out = {}
for module, points in by_module_points.items():
    hull = _convex_hull(points)
    if len(hull) < 3:
        continue  # 1-2 communities in this module - no polygon to draw
    cx = sum(p[0] for p in hull) / len(hull)
    cy = sum(p[1] for p in hull) / len(hull)
    expanded = []
    for x, y in hull:
        dx, dy = x - cx, y - cy
        dist = math.hypot(dx, dy) or 1
        expanded.append([round(x + dx / dist * HULL_MARGIN, 2), round(y + dy / dist * HULL_MARGIN, 2)])
    hulls_out[module] = expanded

Path('graphify-out/.graphify_sigma_data.json').write_text(
    json.dumps({
        'nodes': nodes_out, 'edges': edges_out, 'hulls': hulls_out,
        'repoName': REPO_NAME, 'scanRoot': SCAN_ROOT, 'gitBranch': GIT_BRANCH,
    }, ensure_ascii=False), encoding='utf-8')
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
- **Edges are colored AND labeled by their dominant relation bucket** (the same six buckets the filter panel uses), not a flat gray — pick the bucket with the highest count in the edge's `buckets` breakdown, set `color` to a per-bucket color and `label` to the bucket's human-readable name as plain edge attributes (`renderEdgeLabels: true` on the constructor is what actually draws them; the label/color attributes alone do nothing without it). Keep edge colors at moderate opacity (not solid) — a real corpus renders 1000+ edges simultaneously at the default zoom, and solid colors at that density read as noise rather than a legible signal. Edge label visibility is NOT independently configurable the way node labels are (there is no `edgeLabelRenderedSizeThreshold`) — sigma only shows an edge's label when at least one endpoint is hovered/highlighted, or when both endpoints already have their own node labels showing (which IS gated by `labelRenderedSizeThreshold`). This is a feature, not a limitation to work around: it means edge labels progressively reveal as you zoom in or click a node, instead of 1000+ labels overlapping into unreadable clutter at the initial fit-all view.
- **Layout spread**: a fixed `scaling_ratio` with linear attraction and no repulsion halo packs almost every node within a small radius of the centroid once a real corpus produces 300+ communities — unreadable and impossible to label. Step 1's `linlog=True` + a `node_size` repulsion halo (proportional to member count) + a much higher `scaling_ratio` than the networkx default fixes this at the source (see Step 1's comment for the exact numbers and why they're calibrated together, not independently tunable).
- **Module clustering**: spread alone isn't structure — Step 1 boosts the LAYOUT-ONLY edge weight (a separate `layout_weight` attribute, not the real `weight` that drives rendered edge thickness) for same-module edges before running forceAtlas2, so communities in the same module pull toward each other more than raw topology alone would produce. This trades off directly against the layout-spread goal above: too high a boost re-clumps the largest modules specifically (they have the most same-module edges, so the boost compounds), which was reported as still-too-bunched even after the general spread fix. Both are tuned together — see Step 1's comment for the current numbers and why a too-high boost was reverted rather than kept.
- **Module hulls**: a soft, translucent polygon drawn behind each module's node cluster, computed with a small pure-Python convex-hull implementation in Step 1 (Andrew's monotone chain — not worth adding scipy as a dependency for one shape per module) and rendered on a separate 2D canvas positioned behind sigma's own WebGL canvas via `z-index` in the stylesheet. Redraw on every sigma `afterRender` event (fires on pan/zoom/drag) using `renderer.graphToViewport(...)` — NOT `framedGraphToViewport`, since hull points are stored in the same raw graph coordinate space as node `x`/`y`, not sigma's internal normalized space — so the hulls stay aligned with the nodes as the camera moves. On a window resize, the hull redraw is deliberately gated behind the SAME `afterRender` firing that follows the camera re-fit (see the resize handler below), not drawn eagerly right after mutating the camera — otherwise the hull canvas (a plain synchronous 2D draw) briefly reflects the new camera state a frame before sigma's own WebGL node/edge canvases catch up, which reads as the hull and the graph visibly disagreeing with each other.
- **Resizing the browser window after the page has loaded** re-fits the camera via `fitViewportToNodes` + `renderer.setCustomBBox`, but only from inside a `renderer.on("afterRender", ...)` handler gated by a `pendingViewportRefit` flag set on the raw `resize` event — never synchronously in the resize handler itself, and not from a bare `requestAnimationFrame` either. Sigma's own resize handling re-normalizes node coordinates on its own next scheduled render, not synchronously; reading node display data before that finishes returns stale, un-normalized coordinates and points the camera far outside the graph (a blank canvas — worse than the dead-space bug this fixes). A bare `requestAnimationFrame` merely assumes it runs after sigma's own internal one; that held in most manual tests but is not guaranteed, and failed specifically when the window was resized in the first instants after the page loaded, or resized rapidly (dragging a window edge fires many resize events in quick succession, not one at the end). `afterRender` is the reliable signal, since sigma only emits it once a render pass — including any pending re-normalization — has actually finished.
- **Edges below a weight percentile are hidden by default**, with a "show all edges" checkbox to opt back in and an exception for whatever's connected to the currently-highlighted node (which always shows in full regardless of weight, since a user who picked a specific node wants completeness for it, not a curated subset). This declutter logic lives in the shared `edgeReducer`, which means it's only actually applied once `applyReducers()` runs — an explicit initial call to `applyReducers()` is required for this reason (previously, nothing called it until the first user interaction, which was harmless when every reducer was a no-op identity function at its default state, but isn't harmless now that hiding-by-weight is a real default-view behavior, not a no-op).
- **Nodes are draggable** — the precomputed layout is a starting point for exploration, not a constraint; some real corpora warrant manual tidying that no automatic layout gets right for every viewer. See the `downNode`/`moveBody`/`upNode`/`upStage` handlers and `renderer.setCustomBBox(renderer.getBBox())` in the script — the frozen custom bbox is required, not optional: without it, sigma recomputes its normalization extent from live node positions on every reindex (even with `autoRescale: false`, which only fixes scale/aspect, not this recentering), so dragging one node toward the edge of the current extent visibly pans every OTHER node too. `originalPositions` is captured at load so the reset button can undo dragging, not just filters/highlight.
- **Click panel lists every one of the community's actual source files**, not a capped sample — Step 1 collects each significant community's complete distinct `source_file` list. The panel renders it as a filter textbox + a scrollable list rather than truncating with "+N more", since a 300-member community can legitimately have dozens of files and there's no good way to guess which ones matter to a given user in advance.
- **Clicking a file opens a movable dialog with an embedded content preview**, not just a link. Step 1 reads and embeds a bounded preview (`PREVIEW_CHARS`, currently 3000 characters) for only the first `PREVIEW_CAP` files (currently 8) of each community's complete list — embedding full content for every file in every community would bloat the self-contained HTML far more than paths alone do, so files beyond the cap show their path and, when available, a working `file://` link (built from `graphify-out/.graphify_root`, which only resolves on the machine that generated the graph) without an inline preview. The dialog itself is a plain DOM element dragged via its header (`mousedown`/`mousemove`/`mouseup` on screen-pixel `left`/`top` CSS, NOT `viewportToGraph` — this is unrelated to sigma's graph/camera coordinate spaces, unlike node dragging above).
- **Node labels get their own small background box, not bare canvas text.** Sigma's built-in label renderer (`drawDiscNodeLabel` in its own source) is a plain `fillText` with no background, which is illegible over a dense, colorful tangle of edges — and there is no settings-level "add a background" toggle. `defaultDrawNodeLabel` is sigma's documented override point for a fully custom label-drawing function; use it to fill a small rect (sized from `context.measureText`) behind the text before drawing it.
- Include: click → highlight neighbors + dim the rest (`nodeReducer`/`edgeReducer`), a text search box that filters by label (respecting active filters) and pans the camera to the match, a left-side panel with checkboxes for entity kind and bucketed relation type, and a clickable module legend that doubles as an isolate/hide-by-module toggle. Filtering and highlighting share one pair of reducers (`applyReducers`) so they compose instead of one clobbering the other's `setSetting` call.
- **The header shows which repo/branch this graph is of** — a repo name (the last path segment of `.graphify_root`), its full scan-root path, and the git branch (`git rev-parse --abbrev-ref HEAD` run in Step 1, best-effort). This matters once someone has more than one `graph_sigma.html` open (e.g. comparing two branches, or a stale copy from a previous run) — nothing else on the page identifies which checkout it came from. Both the branch and the repo name/path degrade independently and silently: a non-git corpus just omits the branch, and a `graph.json` missing `.graphify_root` entirely (moved from another machine, or generated without the marker) omits the whole row rather than showing a misleading blank.
- **Camera-pan targets must come from `renderer.getNodeDisplayData(key)`, not the raw data's `x`/`y`.** Sigma's `Camera` operates in its own normalized display space, not the raw graph coordinates you fed it — panning with the raw values silently targets the wrong point. This is the same pattern sigma's own demo search field uses (`packages/demo/src/views/SearchField.tsx`).
- **Escape any label before it goes through `innerHTML`.** Community labels are LLM-generated from indexed corpus content, and module names come from real directory names — both can legally contain `<`/`>`/`"`. `graphify-out/` is meant to be committed and shared with a team (per the README), so an unescaped label is a stored-XSS path for whoever opens the HTML next. Escape with a small helper before interpolating into `innerHTML`; the search-results list already does this correctly by using `textContent` instead. Source-file paths in the click panel are filesystem-derived, not corpus content, so they're a much lower XSS risk — still escaped for consistency and because a pathological filename could in principle contain HTML metacharacters on some filesystems.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Codebase Knowledge Graph (Sigma.js)</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%; background: #0b0d12; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #e6e6e6; }
  #container { position: absolute; inset: 0; z-index: 2; }
  #hullLayer { position: absolute; inset: 0; z-index: 1; pointer-events: none; }
  /* position: fixed, not absolute - the panel must anchor to the actual
     viewport regardless of any page-level scroll (e.g. from the file
     dialog or a tall corpus), or top/left and the max-height's 100vh
     calculation drift out of sync with what's actually visible, which
     reads as "the panel is truncated on my laptop" on a short screen. */
  /* height, not max-height - the sidebar should always span the full
     viewport (like a real sidebar), not shrink to whatever its current
     content happens to need. overflow-y:auto still scrolls internally
     when content exceeds that height. */
  #ui { position: fixed; top: 12px; left: 12px; z-index: 10; background: rgba(20,22,28,0.92); border: 1px solid #2a2d36; border-radius: 8px; padding: 10px 12px; width: 300px; height: calc(100vh - 24px); overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.4); }
  #ui::-webkit-scrollbar { width: 8px; }
  #ui::-webkit-scrollbar-thumb { background: #3a3d46; border-radius: 4px; }
  #ui::-webkit-scrollbar-track { background: transparent; }
  #ui h1 { font-size: 13px; margin: 0 0 8px; font-weight: 600; color: #fff; }
  #ui .meta { font-size: 11px; color: #9aa0ab; margin-bottom: 8px; }
  #ui .source { font-size: 11px; color: #6b7280; margin: 2px 0 8px; overflow-wrap: break-word; }
  #ui .source .branch { color: #9aa0ab; }
  #ui h2 { font-size: 11px; margin: 14px 0 6px; color: #9aa0ab; text-transform: uppercase; letter-spacing: 0.04em; border-top: 1px solid #262932; padding-top: 10px; }
  #search { width: 100%; box-sizing: border-box; padding: 6px 8px; border-radius: 6px; border: 1px solid #3a3d46; background: #14161c; color: #fff; font-size: 12px; outline: none; }
  #search:focus { border-color: #5b8def; }
  #results { max-height: 160px; overflow-y: auto; margin-top: 6px; font-size: 11px; }
  #results div { padding: 3px 4px; border-radius: 4px; cursor: pointer; }
  #results div:hover { background: #23262f; }
  .filter-row, .legend-row { display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 2px 0; cursor: pointer; user-select: none; }
  /* TYPE_ICONS are solid black, meant to be tinted by NodePictogramProgram in
     WebGL at render time - shown raw as an <img> against this dark panel
     background they're nearly invisible, so force them to white here. */
  .filter-row img { width: 12px; height: 12px; flex: none; filter: invert(1); }
  .filter-row .swatch, .legend-row .swatch { width: 12px; height: 12px; flex: none; border-radius: 50%; }
  .legend-row.is-off, .filter-row.is-off { opacity: 0.4; }
  .legend-row .count { color: #6b7280; margin-left: auto; }
  /* #info lives inside #ui now (same sidebar, same width, one scroll) rather
     than floating as its own fixed-position box - that's what was getting
     truncated by the viewport edge independently of the main panel. */
  #info { margin-top: 10px; padding-top: 10px; border-top: 1px solid #262932; font-size: 12px; display: none; }
  #info b { color: #fff; font-size: 13px; }
  #info .stat { color: #9aa0ab; margin-top: 4px; }
  .file-filter { width: 100%; box-sizing: border-box; padding: 5px 7px; margin-top: 4px; border-radius: 5px; border: 1px solid #3a3d46; background: #14161c; color: #fff; font-size: 11px; outline: none; }
  .file-filter:focus { border-color: #5b8def; }
  .file-list { max-height: 130px; overflow-y: auto; margin-top: 4px; border-top: 1px solid #262932; padding-top: 4px; }
  .file-list .file-link { padding: 3px 2px; font-size: 11px; overflow-wrap: anywhere; color: #8fb2f5; cursor: pointer; border-radius: 4px; }
  .file-list .file-link:hover { background: #23262f; color: #aecbff; }
  .file-list .file-empty { color: #6b7280; font-size: 11px; padding: 3px 2px; }
  a.reset { color: #5b8def; cursor: pointer; font-size: 11px; }
  #fileDialog { display: none; position: fixed; width: 520px; max-width: 90vw; max-height: 70vh; background: #14161c; border: 1px solid #2a2d36; border-radius: 8px; box-shadow: 0 12px 40px rgba(0,0,0,0.5); z-index: 20; flex-direction: column; overflow: hidden; }
  .file-dialog-header { display: flex; align-items: center; gap: 10px; padding: 8px 10px; background: #1b1e26; border-bottom: 1px solid #2a2d36; cursor: move; user-select: none; }
  .file-dialog-title { flex: 1; font-size: 12px; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .file-dialog-open { color: #5b8def; font-size: 11px; text-decoration: none; white-space: nowrap; }
  .file-dialog-open:hover { text-decoration: underline; }
  .file-dialog-close { cursor: pointer; color: #9aa0ab; font-size: 16px; line-height: 1; padding: 0 2px; }
  .file-dialog-close:hover { color: #fff; }
  .file-dialog-body { margin: 0; padding: 10px 12px; overflow: auto; font-size: 11px; color: #d8dbe2; white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
</style>
</head>
<body>
<canvas id="hullLayer"></canvas>
<div id="container"></div>
<div id="ui">
  <h1>Codebase Knowledge Graph</h1>
  <div class="source" id="sourceLine"></div>
  <div class="meta" id="metaLine"></div>
  <input id="search" type="text" placeholder="Search communities...">
  <div id="results"></div>
  <h2>Entity kind</h2>
  <div id="typeFilters"></div>
  <h2>Relation type</h2>
  <div id="bucketFilters"></div>
  <h2>Modules (click to isolate)</h2>
  <div id="moduleLegend"></div>
  <label class="filter-row" style="margin-top:10px;"><input type="checkbox" id="showAllEdges"><span>Show all edges (default: hide the weakest)</span></label>
  <div style="margin-top:6px;"><a class="reset" id="resetBtn">reset view / filters / highlight</a></div>
  <div id="info"></div>
</div>

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
// doc_ref (an ADR/RFC citation pulled out of a code comment) isn't part of
// the six-value file_type enum the LLM extraction schema declares, but a
// newer AST feature emits it anyway - alias it to the document glyph rather
// than let it silently fall back to the code icon.
TYPE_ICONS.doc_ref = TYPE_ICONS.document;
const BUCKET_LABELS = {
  calls: "Calls / invocation", structure: "Structure", imports: "Imports / dependencies",
  references: "References / bindings", docs: "Documentation & concepts", groups: "Groups", other: "Other",
};
// One color per relation bucket, so an edge's color tells you what kind of
// relationship it is at a glance instead of every edge being the same gray.
// Kept at moderate opacity (not solid) since a real corpus renders 1000+
// edges simultaneously at the default zoom - solid colors at that density
// read as visual noise rather than a legible category signal.
const BUCKET_EDGE_COLORS = {
  calls: "rgba(91,141,239,0.4)", structure: "rgba(224,162,58,0.4)", imports: "rgba(95,184,122,0.4)",
  references: "rgba(155,107,214,0.4)", docs: "rgba(224,122,155,0.4)", groups: "rgba(58,183,191,0.4)",
  other: "rgba(150,155,165,0.3)",
};
// Same hues as BUCKET_EDGE_COLORS, solid - the translucent edge colors read
// as too faint for a small UI swatch, so the filter panel gets its own
// fully-opaque version of the same palette rather than trying to parse
// opacity back out of an rgba() string.
const BUCKET_SWATCH_COLORS = {
  calls: "#5b8def", structure: "#e0a23a", imports: "#5fb87a",
  references: "#9b6bd6", docs: "#e07a9b", groups: "#3ab7bf", other: "#7a8fa6",
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

// repoName/scanRoot are only present when .graphify_root existed at
// generation time (see Step 1) - a corpus scanned without it (or a graph.json
// moved from a different machine) simply omits this row rather than showing
// a misleading blank/placeholder. gitBranch is independently optional even
// when the other two are present (a non-git corpus, or `git` unavailable).
const sourceLine = document.getElementById('sourceLine');
if (DATA.repoName) {
  const branch = DATA.gitBranch ? ` <span class="branch">(${escapeHtml(DATA.gitBranch)})</span>` : '';
  sourceLine.innerHTML = `${escapeHtml(DATA.repoName)}${branch}<br>${escapeHtml(DATA.scanRoot || '')}`;
} else {
  sourceLine.style.display = 'none';
}

document.getElementById('metaLine').textContent =
  `${DATA.nodes.length} communities · ${DATA.edges.length} cross-community edges · WebGL, precomputed layout`;

// Rank modules by member count so the most common ones get the most
// visually distinct colors; anything past the palette's length shares gray.
const moduleCounts = new Map();
for (const n of DATA.nodes) moduleCounts.set(n.module, (moduleCounts.get(n.module) || 0) + 1);
const rankedModules = [...moduleCounts.keys()].sort((a, b) => moduleCounts.get(b) - moduleCounts.get(a));
const moduleColor = new Map(rankedModules.map((m, i) => [m, i < MODULE_PALETTE.length ? MODULE_PALETTE[i] : OTHER_MODULE_COLOR]));

// Original positions, kept so "reset view" can undo manual dragging, not
// just recenter the camera.
const originalPositions = new Map(DATA.nodes.map(n => [n.key, { x: n.x, y: n.y }]));

const graph = new Graph();
for (const n of DATA.nodes) {
  graph.addNode(n.key, {
    label: n.label, x: n.x, y: n.y, size: n.size, type: "pictogram",
    color: moduleColor.get(n.module) || OTHER_MODULE_COLOR,
    image: TYPE_ICONS[n.fileType] || TYPE_ICONS.code,
    fileType: n.fileType, module: n.module, members: n.members, degree: n.degree,
    files: n.files || [],
  });
}
function dominantBucket(buckets) {
  const entries = Object.entries(buckets || {});
  if (!entries.length) return null;
  return entries.sort((a, b) => b[1] - a[1])[0][0];
}
for (const e of DATA.edges) {
  if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
    const bucket = dominantBucket(e.buckets);
    graph.addEdge(e.source, e.target, {
      size: Math.min(0.3 + Math.log2(1 + e.weight) * 0.35, 4),
      color: bucket ? BUCKET_EDGE_COLORS[bucket] : BUCKET_EDGE_COLORS.other,
      label: bucket ? BUCKET_LABELS[bucket] : "",
      weight: e.weight, buckets: e.buckets || {},
    });
  }
}

// Sigma's built-in label renderer (drawDiscNodeLabel in sigma's own source)
// is a bare fillText with no background - illegible over a dense, colorful
// tangle of edges. There is no settings-level "add a background" option;
// defaultDrawNodeLabel is the documented override point for a fully custom
// label renderer, so give each label its own small filled box.
function drawNodeLabelWithBackground(context, data, settings) {
  if (!data.label) return;
  const size = settings.labelSize, font = settings.labelFont, weight = settings.labelWeight;
  context.font = `${weight} ${size}px ${font}`;
  const textWidth = context.measureText(data.label).width;
  const x = data.x + data.size + 3, y = data.y + size / 3;
  const padX = 4, padY = 2;
  // A near-black background (matching the canvas's #0b0d12) is indistinguishable
  // from the canvas itself - use the same visibly-lighter panel tone the UI
  // chrome uses elsewhere so the box actually reads as a background, not nothing.
  context.fillStyle = "rgba(30,33,40,0.9)";
  context.fillRect(x - padX, y - size, textWidth + padX * 2, size + padY * 2);
  context.fillStyle = settings.labelColor.color || "#d8dbe2";
  context.fillText(data.label, x, y);
}

const renderer = new Sigma(graph, document.getElementById("container"), {
  renderLabels: true, labelRenderedSizeThreshold: 8, defaultDrawNodeLabel: drawNodeLabelWithBackground,
  labelFont: "-apple-system, BlinkMacSystemFont, sans-serif", labelColor: { color: "#d8dbe2" }, labelSize: 12,
  renderEdgeLabels: true, edgeLabelSize: 10, edgeLabelColor: { color: "#9aa0ab" },
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

// Freeze the normalization bounding box so dragging one node doesn't shift
// every other node's rendered position. Sigma recomputes its node extent
// from LIVE positions on every reindex even with autoRescale:false (that
// setting only fixes scale/aspect, not this recentering) - without a frozen
// customBBox, moving one node toward the edge of the current extent would
// visibly pan the whole graph. This is the same call sigma's own drag-nodes
// example uses (packages/storybook/stories/2-advanced-usecases/mouse-manipulations).
renderer.setCustomBBox(renderer.getBBox());

// --- module hull shading: a soft region outline behind each module's node
// cluster, drawn on a plain 2D canvas BEHIND sigma's WebGL canvas (z-index
// in the stylesheet), redrawn on every sigma render so it stays in sync
// with pan/zoom/drag. graphToViewport (not framedGraphToViewport) is the
// correct conversion here since hull points are raw graph coordinates, the
// same space node x/y are in - not sigma's internal normalized space. ---
const hullCanvas = document.getElementById("hullLayer");
const hullCtx = hullCanvas.getContext("2d");
function resizeHullCanvas() {
  const dpr = window.devicePixelRatio || 1;
  hullCanvas.width = window.innerWidth * dpr;
  hullCanvas.height = window.innerHeight * dpr;
  hullCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function drawHulls() {
  hullCtx.clearRect(0, 0, hullCanvas.width, hullCanvas.height);
  for (const [moduleName, points] of Object.entries(DATA.hulls || {})) {
    if (points.length < 3 || !activeModules.has(moduleName)) continue;
    const color = moduleColor.get(moduleName) || OTHER_MODULE_COLOR;
    hullCtx.beginPath();
    points.forEach(([x, y], i) => {
      const vp = renderer.graphToViewport({ x, y });
      if (i === 0) hullCtx.moveTo(vp.x, vp.y); else hullCtx.lineTo(vp.x, vp.y);
    });
    hullCtx.closePath();
    hullCtx.fillStyle = color + "1a";   // 8-digit hex alpha, ~10% opacity fill
    hullCtx.fill();
    hullCtx.strokeStyle = color + "55"; // ~33% opacity outline
    hullCtx.lineWidth = 1.5;
    hullCtx.stroke();
  }
}
resizeHullCanvas();
// Sigma's own internal resize listener (registered inside its constructor, so
// it runs before this one) resizes its CANVAS/WebGL viewport to match the
// container automatically - but that resize is NOT synchronous: it flags the
// renderer dirty and re-normalizes node coordinates on its own next scheduled
// render pass. Without an explicit re-fit here, growing the browser window
// just reveals more dead space around the same old camera framing, which
// reads as "the viewport doesn't expand to the window" even though the
// canvas itself did resize correctly.
//
// The re-fit must NOT run synchronously in this handler, nor even in a bare
// requestAnimationFrame: both read node display data before sigma's own
// pending re-normalization pass has necessarily finished, occasionally
// getting back stale, un-normalized graph coordinates (e.g. a camera
// centered around the raw ~1000-unit layout extent instead of the expected
// 0-1 range) - pointing the camera far outside the graph and rendering a
// blank canvas, a strictly worse regression than the dead-space bug this is
// fixing. A bare rAF merely assumes it will run after sigma's own internal
// one, which held in most manual tests but is not guaranteed - it raced and
// failed when the window was resized in the first moments after the page
// loaded. The reliable signal is sigma's own `afterRender` event, which by
// definition fires only once a render pass (including any pending
// normalization) has actually completed: set a flag on resize, act on it the
// next time `afterRender` fires, so the re-fit is tied to sigma's real
// lifecycle instead of a guessed frame count. This does mean a manual
// zoom/pan gets reset on every resize - an intentional tradeoff, since
// leaving dead space is a worse default than occasionally re-centering.
//
// Mutating the camera (fitViewportToNodes) and the extent (setCustomBBox)
// both call sigma's own `scheduleRender()` - they do NOT repaint the
// WebGL node/edge canvases synchronously. Drawing the hulls in this same
// callback, right after those calls, would use the brand-new camera state
// (graphToViewport reads it live) while the node/edge canvases still show
// the OLD framing until that scheduled render actually runs - hulls and
// graph visibly out of sync with each other for a frame. `return` here
// instead of falling through to `drawHulls()`, and let the render that
// fitViewportToNodes/setCustomBBox just scheduled fire its OWN afterRender
// once nodes/edges are repainted with the new camera - that is what
// finally calls drawHulls, so hulls are never drawn against a camera state
// the node/edge canvases haven't caught up to yet.
let pendingViewportRefit = false;
window.addEventListener("resize", () => {
  resizeHullCanvas();
  pendingViewportRefit = true;
});
renderer.on("afterRender", () => {
  if (pendingViewportRefit) {
    pendingViewportRefit = false;
    fitViewportToNodes(renderer, graph.nodes(), { animate: false });
    renderer.setCustomBBox(renderer.getBBox());
    return;
  }
  drawHulls();
});

// --- drag nodes to manually reposition them (precomputed layout is a
// starting point, not a constraint - some corpora warrant manual tidying).
// Exact event names (downNode/moveBody/upNode/upStage) and the
// preventSigmaDefault()+stopPropagation() combo (which stops sigma from
// ALSO panning the camera while a node drags) match sigma's own official
// example: packages/storybook/stories/2-advanced-usecases/mouse-manipulations. ---
let draggedNode = null;
let isDragging = false;
renderer.on("downNode", ({ node }) => {
  isDragging = true;
  draggedNode = node;
});
renderer.on("moveBody", ({ event }) => {
  if (!isDragging || !draggedNode) return;
  const pos = renderer.viewportToGraph(event);
  graph.setNodeAttribute(draggedNode, "x", pos.x);
  graph.setNodeAttribute(draggedNode, "y", pos.y);
  event.preventSigmaDefault();
  event.original.preventDefault();
  event.original.stopPropagation();
});
function stopDragging() {
  isDragging = false;
  draggedNode = null;
}
renderer.on("upNode", stopDragging);
renderer.on("upStage", stopDragging);

// --- filter + highlight state, combined into one pair of reducers so they compose ---
const activeTypes = new Set(DATA.nodes.map(n => n.fileType));
const activeModules = new Set(rankedModules);
const presentBuckets = new Set();
for (const e of DATA.edges) for (const b of Object.keys(e.buckets || {})) presentBuckets.add(b);
const activeBuckets = new Set(presentBuckets);
let highlightedNode = null;

// Declutter by default: with every edge drawn at once, a real corpus reads
// as a solid tangle regardless of how well-spread the nodes are. Hide edges
// below a weight percentile unless the user opts back in (checkbox) or an
// edge is connected to the currently-highlighted node - highlighting a node
// always shows ALL of its real edges, weak ones included, since a user who
// picked a specific node wants completeness, not a curated view.
const EDGE_DECLUTTER_PERCENTILE = 0.6;
const sortedWeights = DATA.edges.map(e => e.weight).sort((a, b) => a - b);
const edgeWeightThreshold = sortedWeights.length
  ? sortedWeights[Math.floor(sortedWeights.length * EDGE_DECLUTTER_PERCENTILE)]
  : 0;
let showAllEdges = false;

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
    const isHighlightedEdge = highlightedNode && (s === highlightedNode || t === highlightedNode);
    if (!showAllEdges && !isHighlightedEdge && data.weight < edgeWeightThreshold) return { ...data, hidden: true };
    if (highlightedNode) {
      return isHighlightedEdge
        ? { ...data, color: "rgba(230,230,230,0.55)", size: Math.max(data.size, 1) }
        : { ...data, color: "rgba(150,155,165,0.03)" };
    }
    return data;
  });
  renderer.refresh();
}
document.getElementById("showAllEdges").addEventListener("change", (ev) => {
  showAllEdges = ev.target.checked;
  applyReducers();
});

// source_file paths come from the filesystem, not LLM/corpus content, so
// they're not an XSS vector the way labels are - still escaped for
// consistency and because a pathological filename could in principle
// contain HTML metacharacters on some filesystems.
function renderFileList(container, files, query) {
  const q = query.trim().toLowerCase();
  const filtered = q ? files.filter(f => f.path.toLowerCase().includes(q)) : files;
  container.innerHTML = filtered.length
    ? filtered.map(f => `<div class="file-link">${escapeHtml(f.path)}</div>`).join("")
    : `<div class="file-empty">No matching files</div>`;
  container.querySelectorAll(".file-link").forEach((el, i) => {
    el.addEventListener("click", () => openFileDialog(filtered[i]));
  });
}

function highlightNode(key) {
  highlightedNode = key;
  applyReducers();
  const attrs = graph.getNodeAttributes(key);
  const info = document.getElementById("info");
  info.style.display = "block";
  const files = attrs.files || [];
  info.innerHTML = `<b>${escapeHtml(attrs.label)}</b><div class="stat">${attrs.members} member node${attrs.members===1?"":"s"}</div><div class="stat">${attrs.degree} connected communit${attrs.degree===1?"y":"ies"}</div>` +
    (files.length
      ? `<div class="stat">Files (${files.length}):</div><input class="file-filter" type="text" placeholder="Filter files..."><div class="file-list"></div>`
      : "");
  if (files.length) {
    const filterInput = info.querySelector(".file-filter");
    const fileListEl = info.querySelector(".file-list");
    renderFileList(fileListEl, files, "");
    filterInput.addEventListener("input", () => renderFileList(fileListEl, files, filterInput.value));
  }
}

// --- draggable file-preview dialog, created lazily on first use ---
let fileDialogEl = null;
function ensureFileDialog() {
  if (fileDialogEl) return fileDialogEl;
  const dialog = document.createElement("div");
  dialog.id = "fileDialog";
  dialog.innerHTML = `
    <div class="file-dialog-header">
      <span class="file-dialog-title"></span>
      <a class="file-dialog-open" target="_blank" rel="noopener">Open file</a>
      <span class="file-dialog-close">&times;</span>
    </div>
    <pre class="file-dialog-body"></pre>`;
  document.body.appendChild(dialog);
  // Drag-by-header: a plain DOM element position drag, unrelated to sigma's
  // graph/camera coordinate spaces - no viewportToGraph conversion needed
  // here, just CSS left/top in screen pixels.
  const header = dialog.querySelector(".file-dialog-header");
  let dragging = false, offsetX = 0, offsetY = 0;
  header.addEventListener("mousedown", (e) => {
    if (e.target.classList.contains("file-dialog-close")) return;
    dragging = true;
    const rect = dialog.getBoundingClientRect();
    offsetX = e.clientX - rect.left;
    offsetY = e.clientY - rect.top;
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    dialog.style.left = `${e.clientX - offsetX}px`;
    dialog.style.top = `${e.clientY - offsetY}px`;
  });
  window.addEventListener("mouseup", () => { dragging = false; });
  dialog.querySelector(".file-dialog-close").addEventListener("click", () => { dialog.style.display = "none"; });
  fileDialogEl = dialog;
  return dialog;
}
function openFileDialog(file) {
  const dialog = ensureFileDialog();
  dialog.querySelector(".file-dialog-title").textContent = file.path;
  const openLink = dialog.querySelector(".file-dialog-open");
  if (file.url) { openLink.href = file.url; openLink.style.display = ""; } else { openLink.style.display = "none"; }
  dialog.querySelector(".file-dialog-body").textContent = file.preview || "(no preview embedded for this file - use Open file instead)";
  const wasPositioned = !!dialog.style.left;
  dialog.style.display = "flex";
  if (!wasPositioned) {
    dialog.style.left = `${Math.max(0, (window.innerWidth - dialog.offsetWidth) / 2)}px`;
    dialog.style.top = `${Math.max(0, (window.innerHeight - dialog.offsetHeight) / 2)}px`;
  }
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
  const swatchColor = BUCKET_SWATCH_COLORS[b] || BUCKET_SWATCH_COLORS.other;
  row.innerHTML = `<input type="checkbox" checked><span class="swatch" style="background:${swatchColor}"></span><span>${escapeHtml(BUCKET_LABELS[b] || b)}</span>`;
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

// Without this, the custom reducers (which is what the edge-decluttering
// above actually depends on) only ever get installed reactively, on the
// first checkbox/click/highlight interaction - the initial render would use
// sigma's plain defaults, showing every edge regardless of weight, until
// the user touched something. Filters/highlight happened to be harmless to
// skip here before (their initial state is a no-op identity reducer), but
// the weight declutter is not a no-op, so this call is now required, not cosmetic.
applyReducers();

document.getElementById("resetBtn").addEventListener("click", () => {
  activeTypes.clear(); DATA.nodes.forEach(n => activeTypes.add(n.fileType));
  activeModules.clear(); rankedModules.forEach(m => activeModules.add(m));
  activeBuckets.clear(); presentBuckets.forEach(b => activeBuckets.add(b));
  document.querySelectorAll('.filter-row, .legend-row').forEach(el => { el.classList.remove('is-off'); const cb = el.querySelector('input'); if (cb) cb.checked = true; });
  // showAllEdges shares the .filter-row class for consistent styling, but its
  // default is the OPPOSITE of every other filter (unchecked = decluttered,
  // which IS the reset state) - the generic sweep above just checked it, so
  // explicitly override back to unchecked rather than adding a one-off
  // selector exclusion just for this.
  showAllEdges = false;
  document.getElementById("showAllEdges").checked = false;
  clearHighlight();
  // Undo manual dragging too, not just filters/highlight - a silent partial
  // reset (filters cleared but nodes still wherever they were dragged to)
  // would be confusing. Recompute the frozen bbox from the restored
  // positions before re-fitting, or the frozen (pre-restore) bbox would
  // frame the WRONG layout.
  for (const [key, p] of originalPositions) {
    graph.setNodeAttribute(key, "x", p.x);
    graph.setNodeAttribute(key, "y", p.y);
  }
  renderer.setCustomBBox(renderer.getBBox());
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
import re
from pathlib import Path

data = json.loads(Path('graphify-out/.graphify_sigma_data.json').read_text(encoding='utf-8'))
html = Path('graphify-out/graph_sigma.html').read_text(encoding='utf-8')
payload = json.dumps(data, ensure_ascii=False)
# A community label OR an embedded file preview containing a literal
# </script (any case - HTML tag names are case-insensitive) would prematurely
# close the page's own <script> block and corrupt it. File previews make
# this a routine occurrence, not a rare edge case: any previewed HTML/JS/XML
# file (a Vite index.html, a <script> tag in a template, ...) will trigger
# it. Escape unconditionally with the standard JSON-in-HTML technique rather
# than checking after the fact and hoping it wasn't needed.
payload = re.sub(r'</script', '<\\/script', payload, flags=re.IGNORECASE)
html = html.replace('__GRAPH_DATA__', payload)
Path('graphify-out/graph_sigma.html').write_text(html, encoding='utf-8')
Path('graphify-out/.graphify_sigma_data.json').unlink()
```

**Before telling the user it's done**, verify the escape actually worked:

```bash
grep -io '</script' graphify-out/graph_sigma.html | wc -l   # must be exactly 1 (the real closing tag)
```

If it's more than 1, the regex substitution above didn't run (e.g. Step 3 was edited or skipped) — re-run Step 3, don't hand-patch the output file.

## Notes

- This produces a *separate* file (`graph_sigma.html`) alongside vis-network's `graph.html` — don't delete the latter, some users may still want the full uncapped view or the vis-network-specific features (community filter dropdown, confidence-styled edges) that this lighter template doesn't replicate.
- The `MIN_COMMUNITY_SIZE` filter mirrors the same tradeoff as the labeling threshold in Step 5 — communities below it are real but rarely load-bearing for architecture navigation. State the cutoff and the dropped count to the user rather than silently filtering.
- Icon and module-color are both *dominant-vote* approximations at the community level — a community that's 60% code and 40% docs shows only the code icon. This is a reasonable simplification for the aggregated view; it is not accurate for a single mixed-content community and shouldn't be read as "this community contains only code".
- The relation-bucket filter operates on the meta-edge's aggregated bucket breakdown, not individual original edges — unchecking "Calls / invocation" hides a meta-edge only if *none* of the original edges it aggregates fall in a still-checked bucket. A meta-edge that's 90% imports and 10% calls stays visible if either bucket is checked.
- If no community reaches `MIN_COMMUNITY_SIZE`, Step 1 falls back to showing every community rather than producing an empty (and crashing) meta-graph — tell the user this happened rather than silently showing an unfiltered view.
- The "Groups" relation bucket comes from graphify's hyperedges (`participate_in`/`implement`/`form`), which have no `source`/`target` and live in graph.json's separate top-level `hyperedges` array — they're remapped to community-pairs the same way `graphify/export.py`'s vis-network aggregated view already does, so this bucket has real content instead of being permanently empty.
- The click panel's `file://` links only resolve on the machine that generated the graph (they're built from `.graphify_root`'s absolute path) — sharing `graph_sigma.html` with a teammate gives them the correct relative path as text, but the link itself won't open on their machine unless the repo happens to be checked out at the identical absolute path. If the HTML is served over `http://` instead of opened via `file://` (e.g. for local testing through a dev server), some browsers block a same-page navigation from `http:` to `file:` for security reasons — the link is still present and copyable, just not clickable in that mode.
- Dragging a node is a purely local, in-memory repositioning — it is not written back to `graph.json`, `.graphify_labels.json`, or any other output. Reloading `graph_sigma.html` restores the precomputed layout; the reset button restores it without a reload.
- File previews are capped (`PREVIEW_CAP` files per community, `PREVIEW_CHARS` per file) specifically to bound the self-contained HTML's size — a corpus with many large communities and no cap could produce a multi-hundred-MB file. Raise these in Step 1 for a smaller corpus where completeness matters more than file size; the complete path *list* (not the preview content) is never capped regardless.
- Module hulls go stale after manual node dragging — they're computed once in Step 1 from the precomputed layout and don't recompute as a node moves, so a heavily-dragged node can end up visually outside its own module's hull. This is a deliberate simplification (recomputing a hull live on every drag frame is unnecessary complexity for what's meant as a big-picture visual aid, not a precise boundary) — the reset button restores both node positions and, implicitly, hull accuracy.
- The edge-weight declutter threshold (`EDGE_DECLUTTER_PERCENTILE`, currently 0.6) is a blunt global cutoff, not per-module or per-relation-type — a corpus where every edge happens to have similar weight will decluttered to roughly the same degree everywhere, while one with a few very heavy hub edges and many light ones will hide a larger fraction. Check the result against a specific corpus and adjust the percentile if the default view still feels either too sparse or too busy.
