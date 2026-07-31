"""html3d — WebGL renderer for the graph viewer (`--viz 3d`).

Consumes the same view model as the vis.js renderer in graphify.exporters.html
(nodes, edges, legend, hyperedges) and draws it with 3d-force-graph, a UMD
bundle of three.js + d3-force-3d. The canvas renderer tops out around a few
thousand nodes; WebGL pushes that an order of magnitude further, and the extra
dimension gives dense communities somewhere to spread out.

Two deliberate differences from the 2D view, both downstream of one constraint:
the bundle keeps its three.js instance private, so we cannot build custom
geometry without shipping a second copy of three.

  * Learning-overlay status is painted onto the node itself (green/amber/grey)
    instead of ringing it. A sphere has no border to tint, and the community
    colour stays legible in the legend, the search list and the info panel.
  * Hyperedges become a synthetic hub node wired to every member (the standard
    star expansion) rather than a shaded hull. Same information, and the hub is
    clickable, which the hull never was.

Labels are DOM elements projected onto the canvas each frame rather than
sprites, which keeps text crisp, keeps it escapable, and costs no extra
dependency. Only the highest-degree visible nodes plus the current selection
get one — a label per node is unreadable in 3D long before it is slow.
"""
from __future__ import annotations

from functools import lru_cache
from importlib.resources import files

from graphify.exporters.html import _html_styles, js_safe

# The exact reviewed UMD release is packaged with Graphify and embedded into
# each 3D export. This keeps the generated page usable without a network and
# avoids executing mutable CDN content. Bumping the version requires replacing
# the asset, its license/notices, and this digest together.
FORCE_GRAPH_VERSION = "1.80.0"
FORCE_GRAPH_ASSET = (
    f"vendor/3d-force-graph-{FORCE_GRAPH_VERSION}.min.js"
)
FORCE_GRAPH_ASSET_SHA384 = (
    "63b6c2d8f04abbcba3c6dbe8e7e67ad4e786752551cc5b185812b88b97672ff5"
    "3a6850d3a1d93ad6a3949137c89dac52"
)


@lru_cache(maxsize=1)
def _force_graph_source() -> str:
    """Read the packaged 3d-force-graph UMD bundle."""
    return files("graphify").joinpath(FORCE_GRAPH_ASSET).read_text(encoding="utf-8")


def _styles_3d() -> str:
    """Styles layered on top of the shared sidebar CSS from the 2D renderer."""
    return """<style>
  #graph { position: relative; overflow: hidden; }
  #webgl-error { max-width: 560px; margin: 20vh auto 0; padding: 24px;
                 border: 1px solid #3a3a5e; border-radius: 8px; color: #e0e0e0;
                 background: #17172a; font: 14px/1.6 -apple-system, BlinkMacSystemFont,
                 "Segoe UI", sans-serif; }
  #webgl-error code { color: #a5b4fc; }
  #labels { position: absolute; inset: 0; pointer-events: none; overflow: hidden; }
  .glabel { position: absolute; transform: translate(-50%, -140%); white-space: nowrap;
            font-size: 11px; color: #fff; text-shadow: 0 0 4px #000, 0 0 8px #000;
            pointer-events: none; will-change: transform, left, top; }
  .glabel.sel { font-size: 13px; font-weight: 600; }
  .gtip { font: 12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: rgba(15,15,26,0.92); border: 1px solid #3a3a5e; border-radius: 6px;
          padding: 6px 9px; color: #e0e0e0; line-height: 1.5; }
  #view-wrap { padding: 12px; border-bottom: 1px solid #2a2a4e; }
  #view-wrap h3 { font-size: 13px; color: #aaa; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  .btn-row { display: flex; gap: 6px; flex-wrap: wrap; }
  .btn { background: #0f0f1a; border: 1px solid #3a3a5e; color: #ccc; padding: 5px 9px;
         border-radius: 5px; font-size: 12px; cursor: pointer; }
  .btn:hover { border-color: #4E79A7; color: #fff; }
  .btn.on { background: #4E79A7; border-color: #4E79A7; color: #fff; }
  #focus-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: #aaa; }
  #focus-row select { background: #0f0f1a; border: 1px solid #3a3a5e; color: #e0e0e0;
                      border-radius: 5px; padding: 3px 6px; font-size: 12px; }
  #labels-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; color: #aaa; }
  #labels-row label { display: flex; align-items: center; gap: 6px; cursor: pointer; user-select: none; }
  #labels-row label:hover { color: #e0e0e0; }
  .view-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid #3a3a5e;
             border-radius: 3px; background: #0f0f1a; cursor: pointer; position: relative; flex-shrink: 0; }
  .view-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .view-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px;
                            border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #hint { padding: 8px 14px; font-size: 11px; color: #555; border-top: 1px solid #2a2a4e; line-height: 1.6; }
  kbd { background: #0f0f1a; border: 1px solid #3a3a5e; border-radius: 3px; padding: 0 4px; font-size: 10px; color: #888; }
</style>"""


# The viewer script. Kept as a plain (non-f) string so the JS can use `${...}`
# template literals and object literals without brace-doubling; the four data
# placeholders are substituted by render() below.
_SCRIPT_3D = r"""<script>
(() => {
'use strict';

function supportsWebGL() {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch (_) {
    return false;
  }
}

if (!supportsWebGL()) {
  document.getElementById('graph').innerHTML =
    '<div id="webgl-error"><b>WebGL is unavailable.</b><br>' +
    'Enable hardware acceleration or export the compatible 2D view with ' +
    '<code>graphify export html --viz 2d</code>.</div>';
  return;
}

const RAW_NODES  = /*__NODES__*/null;
const RAW_EDGES  = /*__EDGES__*/null;
const LEGEND     = /*__LEGEND__*/null;
const HYPEREDGES = /*__HYPEREDGES__*/null;

const HYPER_COLOR = '#6366f1';
const LABEL_BUDGET = 48;
// Narrowing the view (a hop focus, or an isolated community) leaves few enough
// nodes on screen that most of them can carry a name without turning back into
// the unreadable wall the budget exists to prevent.
const LABEL_BUDGET_NARROWED = 150;

// Layout tuning. The d3-force-3d defaults are built for small graphs: unbounded
// many-body repulsion blows disconnected components apart until the interesting
// structure is a handful of pixels adrift in empty space, and it takes ten-odd
// seconds of visible drift to get there. Capping the repulsion range keeps
// components that share no edge from shoving each other to the horizon, and
// running most of the simulation before the first frame means the graph is
// already spread out when it appears instead of erupting from a single dot.
//
// Gravity is deliberately weak. Turn it up and it stops being a correction and
// starts being the layout: everything packs into a uniform ball and the shape
// tells you about the force, not about the graph.
// The repulsion cap is also the cost control: it lets the Barnes-Hut traversal
// skip distant subtrees, and raising it far past the graph's own radius makes
// every warmup tick expensive enough to freeze the tab on load. Spread comes
// from the cheap levers instead — longer links and weaker gravity.
const CHARGE_STRENGTH = -75;
const CHARGE_MAX_DISTANCE = 350;
const LINK_DISTANCE = 34;
const GRAVITY_STRENGTH = 0.045;
// Most of the simulation runs before the first frame so the graph is drawn
// already spread out, and so the one-shot framing below measures a layout
// that is essentially final. The remaining cooldown ticks barely move it.
const WARMUP_TICKS = 150;
const COOLDOWN_TICKS = 60;
// How far the camera parks from a node it flies to. Close enough to read the
// neighbourhood, far enough to keep the surrounding context in frame.
const FLY_DISTANCE = 260;

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML.
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
                  .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

// ---------------------------------------------------------------- data model
// `tip` is always escaped HTML: the server pre-escapes node titles, and the
// hyperedge hubs synthesised below escape their own labels to match.
const NODES = RAW_NODES.map(n => {
  const bg = (n.color && n.color.background) || '#888888';
  const border = (n.color && n.color.border) || bg;
  return {
    id: n.id,
    label: n.label,
    tip: String(n.title || n.label).split('\n').join('<br>'),
    baseColor: bg,
    // The 2D view rings annotated nodes; here the status colour replaces the
    // node colour, since a sphere has no border to tint.
    ring: border !== bg ? border : null,
    val: Math.max(0.6, Math.pow(Math.max(n.size || 10, 1) / 10, 3)),
    community: n.community,
    communityName: n.community_name,
    sourceFile: n.source_file,
    fileType: n.file_type,
    degree: n.degree || 0,
    status: n.learning_status || '',
    kind: 'node',
  };
});

const BY_ID = new Map(NODES.map(n => [n.id, n]));
const LINKS = [];
RAW_EDGES.forEach(e => {
  if (!BY_ID.has(e.from) || !BY_ID.has(e.to)) return;
  LINKS.push({ source: e.from, target: e.to, tip: e.title,
               confidence: e.confidence, weak: !!e.dashes, kind: 'edge' });
});

// Star expansion of the hypergraph: one hub node per hyperedge, linked to each
// member. The 2D renderer shades a hull behind the members, which needs custom
// geometry we do not have here — and unlike the hull, the hub is clickable.
let hyperCount = 0;
HYPEREDGES.forEach((h, i) => {
  const members = (h.nodes || []).filter(m => BY_ID.has(m));
  if (members.length < 2) return;
  let hid = '__hyperedge_' + i;
  while (BY_ID.has(hid)) hid += '_';
  const label = h.label || 'hyperedge';
  const hub = {
    id: hid, label: label, tip: esc(label) + '<br>hyperedge &middot; ' + members.length + ' members',
    baseColor: HYPER_COLOR, ring: null, val: 1.4, community: null,
    communityName: 'Hyperedge', sourceFile: '', fileType: 'hyperedge',
    degree: members.length, status: '', kind: 'hyper',
  };
  NODES.push(hub);
  BY_ID.set(hid, hub);
  members.forEach(m => LINKS.push({ source: hid, target: m, tip: esc(label),
                                    confidence: 'HYPEREDGE', weak: true, kind: 'hyper' }));
  hyperCount++;
});

// Adjacency must be built from the raw id strings, before 3d-force-graph
// rewrites link.source/link.target into node object references.
const ADJ = new Map(NODES.map(n => [n.id, new Set()]));
LINKS.forEach(l => { ADJ.get(l.source).add(l.target); ADJ.get(l.target).add(l.source); });
const endpoint = v => (v && typeof v === 'object') ? v.id : v;

// Ranked once: the label budget always goes to the busiest nodes on screen.
const BY_DEGREE = NODES.slice().sort((a, b) => b.degree - a.degree);

// -------------------------------------------------------------------- state
const hiddenCommunities = new Set();
let showHyper = true;
// Off by default: 1500 names floating in a rotating volume is noise, and the
// hover tooltip already answers "what is this one?" without them.
let showLabels = false;
// One control, not two: the depth *is* the switch. 0 means "whole graph", any
// higher value isolates that many hops around the current selection.
let focusDepth = 0, focusSet = null;
let selectedId = null;
let hoveredCommunity = null;
let frozen = false;

function recomputeFocus() {
  focusSet = null;
  if (focusDepth < 1 || selectedId === null) return;
  const seen = new Set([selectedId]);
  let frontier = [selectedId];
  for (let d = 0; d < focusDepth; d++) {
    const next = [];
    frontier.forEach(id => (ADJ.get(id) || []).forEach(nb => {
      if (!seen.has(nb)) { seen.add(nb); next.push(nb); }
    }));
    frontier = next;
  }
  focusSet = seen;
}

function nodeVisible(n) {
  if (n.kind === 'hyper') { if (!showHyper) return false; }
  else if (hiddenCommunities.has(n.community)) return false;
  return !focusSet || focusSet.has(n.id);
}
function linkVisible(l) {
  const s = BY_ID.get(endpoint(l.source)), t = BY_ID.get(endpoint(l.target));
  return !!s && !!t && nodeVisible(s) && nodeVisible(t);
}

// -------------------------------------------------------------------- graph
const container = document.getElementById('graph');

const graph = ForceGraph3D({ controlType: 'orbit' })(container)
  .backgroundColor('#0f0f1a')
  .showNavInfo(false)
  .nodeRelSize(4)
  .nodeVal('val')
  .nodeColor(n => n.id === selectedId ? '#ffffff' : (n.ring || n.baseColor))
  .nodeOpacity(0.92)
  .nodeLabel(n => '<div class="gtip">' + n.tip + '</div>')
  .nodeVisibility(nodeVisible)
  .linkVisibility(linkVisible)
  .linkColor(l => l.kind === 'hyper' ? HYPER_COLOR : (l.weak ? '#4a5578' : '#7f8cb0'))
  .linkOpacity(0.32)
  .linkWidth(l => l.weak ? 0.4 : 1)
  .linkDirectionalArrowLength(l => l.kind === 'hyper' ? 0 : 3.2)
  .linkDirectionalArrowRelPos(1)
  .onNodeClick(n => selectNode(n.id, true))
  .onBackgroundClick(() => clearSelection())
  .warmupTicks(WARMUP_TICKS)
  .cooldownTicks(COOLDOWN_TICKS);

// A d3 force is just a function carrying an `initialize` method, so we can add
// one without the d3 bundle. This one pulls every node toward the origin: the
// stock force set has nothing that attracts across components, so a graph with
// 80-odd communities lets every island coast outward on repulsion alone until
// the structure is scattered across a mostly empty volume.
function gravityForce(strength) {
  let nodes = [];
  const force = alpha => {
    const k = strength * alpha;
    for (const n of nodes) { n.vx -= n.x * k; n.vy -= n.y * k; n.vz -= n.z * k; }
  };
  force.initialize = ns => { nodes = ns; };
  return force;
}

// Tuned before graphData() so the warmup ticks already run under these forces.
// Guarded: these reach into d3-force internals, and a layout that falls back to
// the defaults is worse-looking, not broken.
function tuneForces() {
  const charge = graph.d3Force('charge');
  if (charge) {
    if (charge.strength) charge.strength(CHARGE_STRENGTH);
    if (charge.distanceMax) charge.distanceMax(CHARGE_MAX_DISTANCE);
  }
  const link = graph.d3Force('link');
  if (link && link.distance) link.distance(LINK_DISTANCE);
  graph.d3Force('gravity', gravityForce(GRAVITY_STRENGTH));
}
tuneForces();

graph.graphData({ nodes: NODES, links: LINKS });

// Built here, not in the markup: 3d-force-graph clears the container's
// innerHTML when it initialises, which would leave a layer declared in the HTML
// detached from the document — still writable, never visible.
const labelLayer = document.createElement('div');
labelLayer.id = 'labels';
container.appendChild(labelLayer);

function resize() { graph.width(container.clientWidth).height(container.clientHeight); }
window.addEventListener('resize', resize);
resize();

// Re-assigning an accessor is how you make 3d-force-graph re-evaluate it.
// graph.refresh() also works, but it rebuilds every node object *and* snaps the
// camera back to its default position — which silently undid every fly-to.
function restyle() {
  graph.nodeColor(graph.nodeColor())
       .nodeVisibility(graph.nodeVisibility())
       .linkVisibility(graph.linkVisibility());
}

function applyFilters() {
  recomputeFocus();
  restyle();
  pickLabels();
}

// ------------------------------------------------------------------- labels
// DOM overlay rather than three.js sprites: no second bundle, crisp text, and
// the content stays escapable. Only `labelled` gets projected each frame.
let labelled = [];
const labelEls = new Map();
let labelFrame = null;

function pickLabels() {
  const picked = [];
  const seen = new Set();
  if (!showLabels) {
    labelled = [];
    labelEls.forEach(el => el.remove());
    labelEls.clear();
    return;
  }
  const take = n => { if (n && !seen.has(n.id) && nodeVisible(n)) { seen.add(n.id); picked.push(n); } };
  if (selectedId !== null) {
    take(BY_ID.get(selectedId));
    (ADJ.get(selectedId) || []).forEach(nb => take(BY_ID.get(nb)));
  }
  const budget = (focusSet || hiddenCommunities.size) ? LABEL_BUDGET_NARROWED : LABEL_BUDGET;
  for (const n of BY_DEGREE) {
    if (picked.length >= budget) break;
    take(n);
  }
  labelled = picked;
  const keep = new Set(picked.map(n => n.id));
  labelEls.forEach((el, id) => { if (!keep.has(id)) { el.remove(); labelEls.delete(id); } });
  picked.forEach(n => {
    let el = labelEls.get(n.id);
    if (!el) {
      el = document.createElement('div');
      el.className = 'glabel';
      el.textContent = n.label;
      labelLayer.appendChild(el);
      labelEls.set(n.id, el);
    }
    el.classList.toggle('sel', n.id === selectedId);
  });
}

function drawLabels() {
  labelFrame = requestAnimationFrame(drawLabels);
  if (!labelled.length || typeof graph.graph2ScreenCoords !== 'function') return;
  const cam = graph.cameraPosition();
  const ctrls = graph.controls();
  const tgt = (ctrls && ctrls.target) || { x: 0, y: 0, z: 0 };
  // Camera forward vector — a point behind the lens still projects to a
  // plausible-looking screen position, so cull by sign of the dot product.
  const fx = tgt.x - cam.x, fy = tgt.y - cam.y, fz = tgt.z - cam.z;
  const w = container.clientWidth, h = container.clientHeight;
  labelled.forEach(n => {
    const el = labelEls.get(n.id);
    if (!el) return;
    if (n.x === undefined || (fx * (n.x - cam.x) + fy * (n.y - cam.y) + fz * (n.z - cam.z)) <= 0) {
      el.style.display = 'none';
      return;
    }
    const p = graph.graph2ScreenCoords(n.x, n.y, n.z);
    if (!p || p.x < 0 || p.y < 0 || p.x > w || p.y > h) { el.style.display = 'none'; return; }
    el.style.display = '';
    el.style.left = p.x + 'px';
    el.style.top = p.y + 'px';
  });
}

// ---------------------------------------------------------------- selection
function flyTo(n) {
  if (n.x === undefined) return;
  const k = 1 + FLY_DISTANCE / (Math.hypot(n.x, n.y, n.z) || 1);
  graph.cameraPosition({ x: n.x * k, y: n.y * k, z: n.z * k }, n, 900);
}

function showInfo(nodeId) {
  const n = BY_ID.get(nodeId);
  if (!n) return;
  const neighborIds = Array.from(ADJ.get(nodeId) || []);
  const neighborItems = neighborIds.map(nid => {
    const nb = BY_ID.get(nid);
    const color = nb ? (nb.ring || nb.baseColor) : '#555';
    return `<span class="neighbor-link" style="border-left-color:${esc(color)}" data-nid="${esc(nid)}">${esc(nb ? nb.label : nid)}</span>`;
  }).join('');
  document.getElementById('info-content').innerHTML = `
    <div class="field"><b>${esc(n.label)}</b></div>
    <div class="field">Type: ${esc(n.fileType || 'unknown')}</div>
    <div class="field">Community: ${esc(n.communityName)}</div>
    <div class="field">Source: ${esc(n.sourceFile || '-')}</div>
    <div class="field">Degree: ${n.degree}</div>
    ${n.status ? `<div class="field">Status: ${esc(n.status)}</div>` : ''}
    ${neighborIds.length ? `<div class="field" style="margin-top:8px;color:#aaa;font-size:11px">Neighbors (${neighborIds.length})</div><div id="neighbors-list">${neighborItems}</div>` : ''}
  `;
}

function selectNode(nodeId, fly) {
  const n = BY_ID.get(nodeId);
  if (!n) return;
  selectedId = nodeId;
  showInfo(nodeId);
  // Focus is anchored to the selection, so re-run it before restyling.
  recomputeFocus();
  restyle();
  pickLabels();
  if (fly) flyTo(n);
}

function clearSelection() {
  selectedId = null;
  document.getElementById('info-content').innerHTML =
    '<span class="empty">Click a node to inspect it</span>';
  recomputeFocus();
  restyle();
  pickLabels();
}

// Neighbour links carry the id in an escaped data attribute read back by one
// delegated listener — never an inline onclick, which a node id containing a
// double quote could break out of to inject a handler (stored XSS, #1838).
document.addEventListener('click', e => {
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) selectNode(el.dataset.nid, true);
});

// ------------------------------------------------------------------- search
const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) { searchResults.style.display = 'none'; return; }
  const matches = NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) { searchResults.style.display = 'none'; return; }
  searchResults.style.display = 'block';
  matches.forEach(n => {
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${n.ring || n.baseColor}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {
      selectNode(n.id, true);
      searchResults.style.display = 'none';
      searchInput.value = '';
    };
    searchResults.appendChild(el);
  });
});
document.addEventListener('click', e => {
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
});

// ------------------------------------------------------------- view controls
const depthSel = document.getElementById('focus-depth');
const freezeBtn = document.getElementById('btn-freeze');
const hyperBtn = document.getElementById('btn-hyper');
const labelsCb = document.getElementById('cb-labels');

function setLabels(on) {
  showLabels = on;
  labelsCb.checked = on;
  pickLabels();
  if (showLabels && labelFrame === null) {
    labelFrame = requestAnimationFrame(drawLabels);
  } else if (!showLabels && labelFrame !== null) {
    cancelAnimationFrame(labelFrame);
    labelFrame = null;
  }
}
labelsCb.checked = showLabels;
labelsCb.addEventListener('change', () => setLabels(labelsCb.checked));

function setFocusDepth(depth) {
  focusDepth = depth;
  depthSel.value = String(depth);
  applyFilters();
}
// Blurred after use: a focused <select> swallows letter keys as native option
// typeahead, so leaving it focused made F step through the dropdown instead of
// running the focus shortcut.
depthSel.addEventListener('change', () => {
  setFocusDepth(parseInt(depthSel.value, 10));
  depthSel.blur();
});

freezeBtn.addEventListener('click', () => {
  frozen = !frozen;
  freezeBtn.classList.toggle('on', frozen);
  freezeBtn.textContent = frozen ? 'Reheat' : 'Freeze';
  if (frozen) {
    graph.cooldownTicks(0);
  } else {
    graph.cooldownTicks(COOLDOWN_TICKS);
    if (typeof graph.d3ReheatSimulation === 'function') graph.d3ReheatSimulation();
  }
});

if (hyperBtn) {
  hyperBtn.classList.toggle('on', showHyper);
  hyperBtn.addEventListener('click', () => {
    showHyper = !showHyper;
    hyperBtn.classList.toggle('on', showHyper);
    applyFilters();
  });
}

const SHORTCUT_KEYS = ['/', 'Escape', 'f', 'F', 'r', 'R', 'l', 'L', ' '];

document.addEventListener('keydown', e => {
  if (e.target === searchInput) {
    if (e.key === 'Escape') { searchInput.blur(); searchResults.style.display = 'none'; }
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  // A focused <select> treats a letter key as option typeahead. Suppress that
  // so the shortcuts keep working wherever the caret happens to be.
  if (SHORTCUT_KEYS.includes(e.key) && e.target instanceof HTMLSelectElement) e.preventDefault();
  if (e.key === '/') { e.preventDefault(); searchInput.focus(); }
  else if (e.key === 'Escape') {
    if (focusDepth > 0) setFocusDepth(0);
    else if (hiddenCommunities.size) showAllCommunities();
    else clearSelection();
  }
  // Over a community row, F isolates that community; otherwise it toggles the
  // hop focus around the selected node. The Focus button is gone, the shortcut
  // is not.
  else if (e.key === 'f' || e.key === 'F') {
    if (hoveredCommunity !== null) isolateCommunity(hoveredCommunity);
    else if (selectedId !== null) setFocusDepth(focusDepth > 0 ? 0 : 1);
  }
  else if (e.key === 'r' || e.key === 'R') { frameGraph(1.1); }
  // Over a community row, L isolates it and names it in one step — the names
  // follow the isolation, so they are that community's names.
  else if (e.key === 'l' || e.key === 'L') {
    if (hoveredCommunity !== null) setLabels(isolateCommunity(hoveredCommunity));
    else setLabels(!showLabels);
  }
  else if (e.key === ' ') { e.preventDefault(); freezeBtn.click(); }
});

// ------------------------------------------------------------------- legend
const selectAllCb = document.getElementById('select-all-cb');
// cid -> its row, so the checkbox and dimming can be driven from the keyboard
// as well as from a click.
const legendRows = new Map();

function updateSelectAllState() {
  const hidden = hiddenCommunities.size;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < LEGEND.length;
}

function setCommunityHidden(cid, hidden) {
  if (hidden) hiddenCommunities.add(cid); else hiddenCommunities.delete(cid);
  const row = legendRows.get(cid);
  if (row) {
    row.cb.checked = !hidden;
    row.item.classList.toggle('dimmed', hidden);
  }
}

function showAllCommunities() {
  LEGEND.forEach(c => setCommunityHidden(c.cid, false));
  applyFilters();
  updateSelectAllState();
}

function isCommunityIsolated(cid) {
  return !hiddenCommunities.has(cid) && hiddenCommunities.size === LEGEND.length - 1;
}

// Isolate one community; pressing again on the same one restores the rest.
// Returns whether the community ended up isolated, so a caller can follow it.
function isolateCommunity(cid) {
  const restore = isCommunityIsolated(cid);
  LEGEND.forEach(c => setCommunityHidden(c.cid, restore ? false : c.cid !== cid));
  applyFilters();
  updateSelectAllState();
  return !restore;
}

selectAllCb.addEventListener('change', () => {
  const hide = !selectAllCb.checked;
  LEGEND.forEach(c => setCommunityHidden(c.cid, hide));
  applyFilters();
  updateSelectAllState();
});

const legendEl = document.getElementById('legend');
LEGEND.forEach(c => {
  const item = document.createElement('div');
  item.className = 'legend-item';
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'legend-cb';
  cb.checked = true;
  cb.addEventListener('change', e => {
    e.stopPropagation();
    setCommunityHidden(c.cid, !cb.checked);
    applyFilters();
    updateSelectAllState();
  });
  item.innerHTML = `<div class="legend-dot" style="background:${c.color}"></div>
    <span class="legend-label">${c.label}</span>
    <span class="legend-count">${c.count}</span>`;
  item.prepend(cb);
  item.onclick = e => {
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  };
  item.addEventListener('mouseenter', () => { hoveredCommunity = c.cid; });
  item.addEventListener('mouseleave', () => {
    if (hoveredCommunity === c.cid) hoveredCommunity = null;
  });
  legendRows.set(c.cid, { item, cb });
  legendEl.appendChild(item);
});

// Frame the graph once, at startup, and never touch the camera again on its
// own. Deliberately not zoomToFit(): that animates even when asked for a
// zero-duration transition, so calling it here — or worse, on engine stop —
// shows up as the camera drifting or lurching out from under the user.
function layoutRadius() {
  return NODES.reduce((m, n) => Math.max(m, Math.hypot(n.x || 0, n.y || 0, n.z || 0)), 0);
}

function frameGraph(padding) {
  const radius = layoutRadius() || 1;
  const cam = graph.camera();
  const vFov = ((cam && cam.fov) || 50) * Math.PI / 180;
  const aspect = Math.max(container.clientWidth / (container.clientHeight || 1), 0.1);
  const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
  const dist = Math.max(radius / Math.tan(vFov / 2), radius / Math.tan(hFov / 2)) * padding;
  graph.cameraPosition({ x: 0, y: 0, z: dist }, { x: 0, y: 0, z: 0 }, 0);
}
// On the first tick that actually has positions. The warmup ticks are consumed
// inside the animation loop, not during graphData(), so anything scheduled off
// a timer runs while every node is still sitting at the origin — which framed
// the camera to a radius of zero and parked it inside the graph.
let framed = false;
graph.onEngineTick(() => {
  if (framed || layoutRadius() < 1) return;
  framed = true;
  frameGraph(1.1);
});

document.getElementById('btn-reset').addEventListener('click', () => frameGraph(1.1));

graph.onEngineStop(() => { graph.onEngineStop(() => {}); pickLabels(); });
pickLabels();
})();
</script>"""


def render(model: dict) -> str:
    """Render the shared view model as the 3d-force-graph WebGL viewer."""
    # A literal closing script tag in either graph data or a future dependency
    # release must not be able to terminate this inline block.
    force_graph_source = _force_graph_source().replace("</script", "<\\/script")
    script = (
        _SCRIPT_3D
        .replace("/*__NODES__*/null", js_safe(model["nodes"]))
        .replace("/*__EDGES__*/null", js_safe(model["edges"]))
        .replace("/*__LEGEND__*/null", js_safe(model["legend"]))
        .replace("/*__HYPEREDGES__*/null", js_safe(model["hyperedges"]))
    )
    hyper_btn = (
        '<button class="btn" id="btn-hyper">Hyperedges</button>'
        if model["hyperedges"] else ""
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify 3D - {model["title"]}</title>
<script>
{force_graph_source}
</script>
{_html_styles()}
{_styles_3d()}
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="view-wrap">
    <h3>View</h3>
    <div class="btn-row">
      <button class="btn" id="btn-reset">Reset view</button>
      <button class="btn" id="btn-freeze">Freeze</button>
      {hyper_btn}
    </div>
    <div id="focus-row">
      <span>Show</span>
      <select id="focus-depth">
        <option value="0" selected>whole graph</option>
        <option value="1">selection + 1 hop</option>
        <option value="2">selection + 2 hops</option>
        <option value="3">selection + 3 hops</option>
        <option value="4">selection + 4 hops</option>
        <option value="5">selection + 5 hops</option>
        <option value="6">selection + 6 hops</option>
      </select>
    </div>
    <div id="labels-row">
      <label><input type="checkbox" class="view-cb" id="cb-labels">Show names</label>
    </div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked>Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="hint"><kbd>/</kbd> search &middot; <kbd>F</kbd> focus node / isolate hovered community &middot; <kbd>L</kbd> names &middot; <kbd>R</kbd> reset &middot; <kbd>Space</kbd> freeze &middot; <kbd>Esc</kbd> clear</div>
  <div id="stats">{model["stats"]}</div>
</div>
{script}
</body>
</html>"""
