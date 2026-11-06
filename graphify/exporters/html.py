"""html — moved verbatim from graphify/export.py."""
from __future__ import annotations

from graphify.exporters.base import COMMUNITY_COLORS  # noqa: E402,F401
from pathlib import Path
import html as _html
from graphify.analyze import _node_community_map
from graphify.paths import write_text_atomic
import json
import networkx as nx
from graphify.security import sanitize_label


MAX_NODES_FOR_VIZ = 5_000
_HTML_STALE_MARKER = ".graph.html.stale"

# The community palette goes into the page so the theme switch can re-tint the canvas and
# so the legend, the search swatches and the neighbour links all read the same source.
_PAL_JS = "[" + ", ".join('"%s"' % c for c in COMMUNITY_COLORS) + "]"

# Dense graphs spend most of every canvas redraw on per-edge arrowheads. Above
# this many edges the exporter stops drawing an arrowhead on every edge every
# frame and reveals them on hover instead (edge hover, or node hover for all
# incident edges). Direction is never lost - it moves from "always drawn" to
# "drawn on hover" only for graphs where drawing them is what makes pan/zoom lag
# (measured: rsl/continuum/gsoc-aggregate redraw -63%..-67%). Below the
# threshold the render is byte-identical to before. (#perf)
ARROW_DEFER_EDGE_THRESHOLD = 1_500

# Above this many nodes, a drag/pan gesture drops node border strokes (cosmetic) for
# the length of the gesture and restores them on release. Measured on rsl (1886 nodes,
# same machine, interleaved A/B): node drag 15.7 -> 60.9 fps, pan 15.0 -> 64.8 fps,
# frames over 33ms 119/120 -> 5/120. ~1900 per-frame ctx.stroke() calls for 1.5px
# borders were choking the canvas raster pipeline - it is the single biggest cost in a
# drag frame, bigger than the edges. Below the threshold the render is byte-identical.
LEAN_GESTURE_NODE_THRESHOLD = 800

# Emitted only when arrowheads are deferred. Single braces: this string is
# interpolated verbatim into the script (not itself an f-string).
_ARROW_HOVER_JS = """
// Deferred arrowheads (#perf). Direction is shown, not lost: hover an edge, or a
// node (all its incident edges), to see the arrowheads.
//
// Two rules keep this off the hot path (measured with harness/profile_drag.mjs):
//   1. NO DATASET. Every edgesDS.update() makes vis run _updateVisibleIndices() plus
//      _updateValueRange() over ALL nodes and ALL edges, request a redraw, AND invalidates
//      the batched edge pass (which then re-reads the formatting values of all 3876
//      edges). On a hover that landed as a 100-200 ms stall in a dense cluster. The arrow
//      flag is written onto the edge INSTANCE instead: vis's draw reads it from there, and
//      the batch skips arrowed edges at draw time, so nothing has to be rebuilt.
//   2. NO CHURN DURING A DRAG. Hover events fired mid-pull are noise; they made the
//      graph feel like it was fighting the pointer. Defer, then resync once on dragEnd.
const _arrowOn = new Set();
let _hoverNode = null, _hoverEdge = null, _dragging = false;
function _setArrow(id, on) {
  const e = network.body && network.body.edges && network.body.edges[id];
  if (!e || !e.options) return;
  if (!e.options.arrows) e.options.arrows = {};
  if (!e.options.arrows.to) e.options.arrows.to = {};
  e.options.arrows.to.enabled = on;
  if (on) e.options.arrows.to.scaleFactor = 0.5;
}
function _syncArrows() {
  const want = new Set();
  if (_hoverEdge !== null) want.add(_hoverEdge);
  if (_hoverNode !== null) {
    const inc = network.getConnectedEdges(_hoverNode);
    for (const id of inc) want.add(id);
  }
  let changed = false;
  for (const id of _arrowOn) {
    if (!want.has(id)) { _arrowOn.delete(id); _setArrow(id, false); changed = true; }
  }
  for (const id of want) {
    if (!_arrowOn.has(id)) { _arrowOn.add(id); _setArrow(id, true); changed = true; }
  }
  if (changed) { try { network.redraw(); } catch (e) {} }
}
// Hover highlights the one edge under the pointer (its own arrowhead included).
// It must not reveal every edge of a hovered node: that pulls a hub's whole
// neighbourhood out of the batch and was the stall while the pointer moved
// through a dense cluster. The node highlight is vis's own hover ring.
network.on('hoverNode', function (p) { _hoverNode = p.node; });
network.on('blurNode', function () { _hoverNode = null; if (!_dragging) _syncArrows(); });
network.on('hoverEdge', function (p) { _hoverEdge = p.edge; if (!_dragging) _syncArrows(); });
network.on('blurEdge', function () { _hoverEdge = null; if (!_dragging) _syncArrows(); });
network.on('dragStart', function () { _dragging = true; });
network.on('dragEnd', function () { _dragging = false; _syncArrows(); });
"""

# Always emitted. Caches this graph's stabilized layout so a re-opened graph
# skips the on-load solver (measured load -73%). The cached x/y ARE this graph's
# own stabilized positions, so layout and every capability are identical; only
# the recompute cost is removed. Best-effort: localStorage may throw (file://,
# private mode) - then behavior is exactly as before.
_POSITION_CACHE_JS = """
// Stabilized-layout cache (#perf).
const POSK = 'graphify-pos:' + RAW_NODES.length + ':'
  + String(RAW_NODES.length ? RAW_NODES[0].id : '') + ':'
  + String(RAW_NODES.length ? RAW_NODES[RAW_NODES.length - 1].id : '');
function _savePositions() {
  try {
    const p = network.getPositions();
    const out = {};
    for (const id in p) { out[id] = [Math.round(p[id].x * 100) / 100, Math.round(p[id].y * 100) / 100]; }
    localStorage.setItem(POSK, JSON.stringify(out));
  } catch (e) {}
}
(function _restorePositions() {
  let raw = null;
  try { raw = localStorage.getItem(POSK); } catch (e) { return; }
  if (!raw) return;
  let pos = null;
  try { pos = JSON.parse(raw); } catch (e) { return; }
  if (!pos || typeof pos !== 'object') return;
  const upd = [];
  for (const n of RAW_NODES) { const p = pos[n.id]; if (p) upd.push({ id: n.id, x: p[0], y: p[1] }); }
  if (upd.length < RAW_NODES.length) return;  // stale/partial -> re-solve
  try {
    network.setOptions({ physics: { enabled: false } });
    nodesDS.update(upd);
    network.fit({ animation: false });
  } catch (e) {}
})();
"""

# Emitted only for large graphs (see LEAN_GESTURE_NODE_THRESHOLD). Plain string, single
# braces, interpolated verbatim.
_LEAN_GESTURE_JS = """
// Lean draw during gestures (#perf): borders off the nodes, one stroke for the edges.
//
// Nodes: the border costs one ctx.stroke() per node per frame (~1900 strokes on rsl) and
// the raster pipeline cannot keep up, so a drag settled at ~15fps. Dropping borders for
// the duration of the gesture takes that past 40fps and cuts stalled frames (over 33ms)
// from 89/90 to a handful. The border is cosmetic and returns the instant the pointer is
// released.
//
// Every element is still drawn. Edges used to simply vanish while the view moved, first
// because the shipped build set hideEdgesOnDrag/hideEdgesOnZoom, and then because hiding
// them was the only way to stay smooth: vis issues one ctx.stroke() per edge per frame
// (3876 on rsl, ~30ms) and no option change removes that - the draw path fills its values
// in from the instance options during the draw, so writing edge.options.smooth/width
// mid-gesture changes the data and nothing on screen. What does work is taking over the
// edge pass for the length of the gesture and stroking each (colour, dashes, width) group
// once. On rsl 3876 strokes collapse to ~20 for the same pixels, and the endpoints are
// read live each frame (edgeType.fromPoint IS the node object), so edges still follow a
// node being dragged.
//
// Both levers are written straight onto the instances rather than through
// network.setOptions(): setOptions re-applies the global options but also costs a full
// synchronous redraw (measured: ~80ms on rsl, ~200ms on a 2290-node aggregate, 670-2000ms
// on a 9142-node graph), which landed as one hitch at dragStart and another at dragEnd.
//
// The node border is no longer dropped for the length of a gesture: the disc is drawn
// with one fill at all times (see _nbApply below), so there is nothing to lean and the
// nodes no longer change size when the pointer goes down.
const _BORDER_FULL = 1.5;


// Batched edge pass. vis draws each edge by calling edgeType.drawLine(ctx, values, ...);
// for the duration of a gesture that call is replaced by one draw of every edge, grouped
// by the colour/dash/width it would have been drawn with, so the reused ctx state is
// identical. The replacement is deleted on release, which restores the prototype method.
const _EDGE_BATCH = (function () {
  let _installed = false, _drawn = false, _groups = null, _ctx = null, _errors = 0;
  let _rest = false, _dirty = false;

  function _dashOf(t) {
    const d = t.dashes;
    if (d === false || d === null || d === undefined) return null;
    return d === true ? [5, 5] : d;
  }

  // An edge that is showing its arrowhead cannot be drawn by the batch: the batch draws
  // the line, not the arrow. Dense graphs defer arrows to hover, so this is the edges the
  // user is currently inspecting.
  function _arrowed(et) {
    const a = et && et.options && et.options.arrows;
    return !!(a && a.to && a.to.enabled === true);
  }

  function _scale() {
    try { return network.body.view.scale || network.getScale(); } catch (e) { return 1; }
  }

  function _build() {
    const body = network.body;
    const es = body && body.edges;
    if (!es) return false;
    if (!_ctx) {
      _ctx = (body.renderer && body.renderer.ctx) || (function () {
        try { return document.createElement('canvas').getContext('2d'); } catch (e) { return null; }
      })();
    }
    const map = new Map();
    for (const id in es) {
      const e = es[id];
      if (!e || !e.connected || !e.edgeType) continue;
      // vis draws an edge only when the edge and BOTH endpoints are visible
      // (Body._updateVisibleIndices). Legend filtering hides nodes, not edges, so without
      // this the cached batch would keep drawing the hidden node's edges.
      const fo = e.from && e.from.options, to = e.to && e.to.options;
      if ((e.options && e.options.hidden) || (fo && fo.hidden) || (to && to.hidden)) continue;
      let t = null;
      try { t = e.getFormattingValues(); } catch (err) { continue; }
      if (!t || t.hidden) continue;
      let col = null;
      try { col = e.edgeType.getColor(_ctx, t); } catch (err) { continue; }
      if (typeof col !== 'string') continue;  // gradient / exotic: leave it to vis
      // Dashed edges (INFERRED confidence) keep vis's own draw. Their dash rendering has to
      // match vis exactly and there are few of them on a dense graph (393 of 3876 on rsl),
      // so 393 strokes beat risking a differently-dashed confidence encoding.
      if (_dashOf(t)) { e.edgeType.__leanDash = true; continue; }
      if (e.edgeType.__leanDash) delete e.edgeType.__leanDash;
      const baseW = (e.options && typeof e.options.width === 'number') ? e.options.width : t.width;
      const key = col + '|' + baseW;
      let grp = map.get(key);
      if (!grp) map.set(key, grp = { col: col, baseW: baseW, ets: [] });
      grp.ets.push(e.edgeType);
    }
    _groups = [];
    for (const grp of map.values()) _groups.push(grp);
    return _groups.length > 0;
  }

  // The exact curve vis draws at rest for `smooth: {type: 'continuous'}`: a quadratic
  // through the same via point BezierEdgeDynamic._getViaCoordinates computes (offset from
  // `from` by roundness * the dominant extent, signed toward `to`, clamped into the
  // segment's box). Drawing straight lines in the batch instead is faster still, but it is
  // visibly a different graph in motion: a frame-by-frame pixel diff against the resting
  // frame shows 82-100% of painted pixels changing with straight lines versus 1.1-1.8%
  // with the curve. Anything that is not a continuous smooth edge falls back to a line.
  function _curveTo(g, et) {
    const o = et.options && et.options.smooth;
    if (!o || o.enabled === false || o.type !== 'continuous') { g.lineTo(et.toPoint.x, et.toPoint.y); return; }
    const fx = et.from.x, fy = et.from.y, tx = et.to.x, ty = et.to.y;
    const e = o.roundness, C = Math.abs(fx - tx), I = Math.abs(fy - ty);
    let a = (C <= I) ? e * I : e * C;
    let b = a;
    if (fx > tx) a = -a;
    if (fy >= ty) b = -b;
    let vx = fx + a, vy = fy + b;
    if (C <= I) vx = (fx <= tx) ? (tx < vx ? tx : vx) : (tx > vx ? tx : vx);
    else vy = (fy >= ty) ? (ty > vy ? ty : vy) : (ty < vy ? ty : vy);
    g.quadraticCurveTo(vx, vy, et.toPoint.x, et.toPoint.y);
  }

  // Device-pixel box of the curve _curveTo is about to draw. The three control points
  // contain the quadratic, so an edge whose box misses the canvas cannot paint a pixel.
  // `m` is the camera vis already installed on the context (world -> device).
  function _onScreen(et, m, pad, w, h) {
    const o = et.options && et.options.smooth;
    let cx = et.toPoint.x, cy = et.toPoint.y;
    if (o && o.enabled !== false && o.type === 'continuous') {
      const fx = et.from.x, fy = et.from.y, tx = et.to.x, ty = et.to.y;
      const e = o.roundness, C = Math.abs(fx - tx), I = Math.abs(fy - ty);
      let a = (C <= I) ? e * I : e * C;
      let b = a;
      if (fx > tx) a = -a;
      if (fy >= ty) b = -b;
      cx = fx + a; cy = fy + b;
      if (C <= I) cx = (fx <= tx) ? (tx < cx ? tx : cx) : (tx > cx ? tx : cx);
      else cy = (fy >= ty) ? (ty > cy ? ty : cy) : (ty < cy ? ty : cy);
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const xs = [et.fromPoint.x, cx, et.toPoint.x];
    const ys = [et.fromPoint.y, cy, et.toPoint.y];
    for (let k = 0; k < 3; k++) {
      const dx = m.a * xs[k] + m.c * ys[k] + m.e;
      const dy = m.b * xs[k] + m.d * ys[k] + m.f;
      if (dx < minX) minX = dx;
      if (dy < minY) minY = dy;
      if (dx > maxX) maxX = dx;
      if (dy > maxY) maxY = dy;
    }
    return maxX >= -pad && minX <= w + pad && maxY >= -pad && minY <= h + pad;
  }

  function _strokeGroup(g, grp, floor) {
    const ets = grp.ets;
    g.strokeStyle = grp.col;
    // vis sets lineWidth to max(width, 0.3/scale) on every draw; the floor moves with
    // the zoom, so it has to be re-derived per frame rather than baked in at dragStart.
    g.lineWidth = Math.max(grp.baseW, floor);
    g.beginPath();
    for (let j = 0; j < ets.length; j++) {
      const et = ets[j];
      // An arrowed edge is drawn by vis (it needs the arrowhead); the group keeps it so
      // the arrow flag can be flipped on the instance without a rebuild.
      if (_arrowed(et)) continue;
      g.moveTo(et.fromPoint.x, et.fromPoint.y);
      _curveTo(g, et);
    }
    g.stroke();
  }

  function _drawAll(g) {
    const groups = _groups;
    if (!groups || !g) return;
    const floor = 0.3 / _scale();
    // The solver redraws while it runs. Culling and per-edge strokes are for a settled
    // camera; during the solve they turn four overview frames into a full walk of every
    // edge and the first open goes from a few seconds to the tens. One path per colour,
    // every edge, until physics is off.
    let solving = false;
    try { solving = !!(network.physics && network.physics.options.enabled); } catch (err) {}
    if (solving) {
      for (let i = 0; i < groups.length; i++) _strokeGroup(g, groups[i], floor);
      return;
    }
    let m = null;
    try { m = g.getTransform(); } catch (err) { m = null; }
    // Identity means the camera is not on the context. Culling against it would drop
    // every edge whose world coordinate sits outside the canvas, so draw them all.
    const ident = m && Math.abs(m.a - 1) < 1e-3 && Math.abs(m.d - 1) < 1e-3
      && Math.abs(m.b) < 1e-3 && Math.abs(m.c) < 1e-3
      && Math.abs(m.e) < 1e-3 && Math.abs(m.f) < 1e-3;
    const canCull = !!(m && !ident);
    const w = g.canvas.width, h = g.canvas.height;
    const masks = new Array(groups.length);
    let total = 0, shown = 0;
    for (let i = 0; i < groups.length; i++) {
      const ets = groups[i].ets;
      const mask = masks[i] = new Uint8Array(ets.length);
      const lw = Math.max(groups[i].baseW, floor);
      const pad = canCull ? (lw * Math.hypot(m.a, m.b) + 4) : 0;
      for (let j = 0; j < ets.length; j++) {
        const et = ets[j];
        // An arrowed edge is drawn by vis (it needs the arrowhead); the group keeps it so
        // the arrow flag can be flipped on the instance without a rebuild.
        if (_arrowed(et)) continue;
        total++;
        if (!canCull || _onScreen(et, m, pad, w, h)) { mask[j] = 1; shown++; }
      }
    }
    // One path per colour is cheaper while that path is the screen (the fit view).
    // Zoomed in, the same path covers the whole graph, so the rasterizer walks every
    // off-screen curve. Stroke each visible edge on its own: a miss is then one small
    // path the canvas can reject, which is how the shipped viewer stays cheap up close.
    const perEdge = total > 0 && shown * 2 < total;
    for (let i = 0; i < groups.length; i++) {
      const grp = groups[i];
      const ets = grp.ets;
      const mask = masks[i];
      g.strokeStyle = grp.col;
      g.lineWidth = Math.max(grp.baseW, floor);
      if (perEdge) {
        for (let j = 0; j < ets.length; j++) {
          if (!mask[j]) continue;
          const et = ets[j];
          g.beginPath();
          g.moveTo(et.fromPoint.x, et.fromPoint.y);
          _curveTo(g, et);
          g.stroke();
        }
      } else {
        g.beginPath();
        let any = false;
        for (let j = 0; j < ets.length; j++) {
          if (!mask[j]) continue;
          any = true;
          const et = ets[j];
          g.moveTo(et.fromPoint.x, et.fromPoint.y);
          _curveTo(g, et);
        }
        if (any) g.stroke();
      }
    }
  }

  // Patch every edge instance's drawLine. Idempotent per edge instance: vis replaces the
  // edgeType when an edge's options change (a hovered edge gets its arrowhead back), so the
  // patch has to be re-applied to the new instances after a data change.
  function _patch() {
    const es = network.body && network.body.edges;
    if (!es) return;
    for (const id in es) {
      const et = es[id] && es[id].edgeType;
      if (!et || et.__leanBatch) continue;
      const orig = et.drawLine;
      et.__leanBatch = orig;
      et.drawLine = function (ctx, values, sel, hov, via) {
        // Selected and hovered edges keep vis's own draw: the batch knows the colour and
        // the width, but not the selection highlight or the arrowhead.
        if (sel || hov || this.__leanDash || _arrowed(this)) { orig.call(this, ctx, values, sel, hov, via); return; }
        if (_drawn) return;          // the other 3875 edges are already on the canvas
        _drawn = true;
        try { _drawAll(ctx); return; } catch (err) {
          _errors++;
          if (_errors > 2) { _uninstall(); }
        }
        orig.call(this, ctx, values, sel, hov, via);
      };
    }
  }

  function _install() {
    if (_installed || !_build()) return;
    _patch();
    _installed = true;
  }

  function _uninstall() {
    if (!_installed) return;
    try {
      const es = network.body && network.body.edges;
      for (const id in es) {
        const et = es[id] && es[id].edgeType;
        if (!et || !et.__leanBatch) continue;
        delete et.drawLine;          // back to the prototype implementation
        delete et.__leanBatch;
      }
    } catch (e) {}
    _installed = false;
    _groups = null;
    _drawn = false;
  }

  function _set(on) {
    // With the batch installed at rest (L12) the gesture flag has nothing left to change:
    // it is already drawing every edge, and uninstalling on release would undo the win.
    if (_rest) return;
    if (on) _install(); else _uninstall();
  }

  return {
    set: _set,
    setRest: function (on) {
      _rest = !!on;
      if (_rest) _install(); else _uninstall();
    },
    dirty: function () { _dirty = true; },
    frame: function () {
      _drawn = false;
      if (_dirty && _installed) { _dirty = false; _build(); _patch(); }
    },
  };
})();

// The "lean" (drop the node border for the length of a gesture) is gone: the disc is
// drawn with one fill in every state (L22/L30), so there is nothing to lean any more.
// It used to leave a timer behind that fired a FULL extra redraw plus a forced rewrite of
// all 1886 nodes after every zoom step - twelve extra complete frames per wheel gesture,
// which is what made a dense zoom feel clumsy (measured: 29 redraws per gesture against
// the shipped viewer's 17).

// ---- the node disc without the border stroke (#perf L22) ----------------
//
// vis draws a node as a fill of radius size/2 plus a border stroke whose WORLD width is
// min(nodeWidth, 1.5/scale) - at the fit scale that stroke is as wide as the node itself,
// so the node you see is a disc twice its fill radius. On rsl that is 1886 hairline
// strokes per frame, and they are the single biggest cost of a resting frame: the frame
// measures 86 ms with the borders and 29 ms without them (same picture, one fill).
//
// The border colour is the fill colour, so the same disc can be drawn with one fill.
// vis's border is min(nodeWidth, borderWidth/scale) world units wide, and that min has two
// regimes: while the border is wider than the node it is capped at the node's own width (so
// the disc is exactly twice the fill radius, and the fill alone reproduces it), and once the
// zoom makes the border thinner than the node, vis's own border is the right thing to use -
// only a few nodes are on screen there, so the border strokes are cheap.
//
// Switching between the two at that boundary is seamless (both draw the same radius there)
// and, crucially, it happens ONCE per node per crossing. The earlier version recomputed
// `size = base + min(base, 1.5/scale)` on every zoom frame, which rewrote the size of all
// 1886 nodes per frame and made the dots shimmer and the zoom hitch.
let _nbBase = null, _nbHover = {}, _nbSel = {}, _nbScale = -1, _nbLock = false;
function _nbApplyNode(id, scale, force) {
  const n = network.body && network.body.nodes[id];
  if (!n || !n.options) return;
  let base = _nbBase[id];
  if (base === undefined) _nbBase[id] = base = n.options.size;
  let size, bw;
  if (_nbHover[id] || _nbSel[id]) {
    // Grabbing a node selects it. Setting the radius back to the exported
    // base cut the disc in half for the whole drag, which reads as the node
    // getting thinner and dimmer the moment the graph moves. Keep the resting
    // radius; the border only supplies the ring.
    if (n.__nbRestSize !== undefined) {
      size = n.__nbRestSize; bw = _BORDER_FULL;
    } else {
      size = base; bw = _BORDER_FULL;
    }
  } else if (_nbLock && n.__nbRestSize !== undefined) {
    // Panning does not change the scale, but the first drag frame used to apply a
    // scale the zoom had already reached. Every disc then jumped from the doubled
    // fill to the thin-border size and stayed there. The resting size is fixed
    // once, and a gesture puts it back.
    size = n.__nbRestSize; bw = n.__nbRestBw;
  } else if (_BORDER_FULL / (scale || 1) < base) {
    // the border is thinner than the node: use vis's own border
    size = base; bw = _BORDER_FULL;
  } else {
    // the border would be capped at the node's width: draw the disc as one fill
    size = base * 2; bw = 0;
  }
  // The lean used to shrink the disc for the length of a gesture (the small discs raster
  // faster). That is exactly what made the nodes visibly shrink every time the graph moved
  // or zoomed, so the size is the same in a gesture as at rest. The lean still suppresses
  // the hover paint, which is all it should have been doing here.
  if (!force && n.__nbSize === size && n.__nbBw === bw && n.baseSize === size) return;
  n.__nbSize = size;
  n.__nbBw = bw;
  if (!_nbHover[id] && !_nbSel[id]) {
    n.__nbRestSize = size;
    n.__nbRestBw = bw;
    // vis keeps the constructed radius on baseSize and writes it back over
    // options.size whenever the DataSet emits _dataUpdated (setValueRange).
    // A drag does that on every move, which snapped every disc back to the
    // exported radius. The resting radius has to be what vis restores.
    n.baseSize = size;
  }
  n.options.size = size;
  n.options.borderWidth = bw;
}
function _nbRestore() {
  const nodes = network.body && network.body.nodes;
  if (!nodes) return;
  for (const id in nodes) {
    const n = nodes[id];
    if (!n || !n.options || n.__nbRestSize === undefined) continue;
    // A selected node keeps the ring, but the same radius as every other disc.
    const ring = _nbHover[id] || _nbSel[id];
    const bw = ring ? _BORDER_FULL : n.__nbRestBw;
    if (n.options.size === n.__nbRestSize && n.options.borderWidth === bw && n.baseSize === n.__nbRestSize) continue;
    n.__nbSize = n.__nbRestSize;
    n.__nbBw = bw;
    n.baseSize = n.__nbRestSize;
    n.options.size = n.__nbRestSize;
    n.options.borderWidth = bw;
  }
}
function _nbApply(force) {
  const nodes = network.body && network.body.nodes;
  if (!nodes) return;
  if (!_nbBase) {
    _nbBase = {};
    for (const id in nodes) _nbBase[id] = nodes[id].options.size;
  }
  let scale = 1;
  try { scale = network.body.view.scale || 1; } catch (e) {}
  // The disc only depends on the scale (and on the ring state, which the hover/select
  // handlers apply directly), so a frame that does not change the scale has nothing to do.
  if (!force && scale === _nbScale) return;
  _nbScale = scale;
  for (const id in nodes) _nbApplyNode(id, scale, force);
}
function _nbScaleNow() {{ let s = 1; try {{ s = network.body.view.scale || 1; }} catch (e) {{}} return s; }}
network.on('hoverNode', function (p) { _nbHover[p.node] = 1; _nbApplyNode(p.node, _nbScaleNow(), true); });
network.on('blurNode', function (p) { delete _nbHover[p.node]; _nbApplyNode(p.node, _nbScaleNow(), true); });
network.on('selectNode', function (p) { p.nodes.forEach(function (id) { _nbSel[id] = 1; _nbApplyNode(id, _nbScaleNow(), true); }); if (!_dragging) _syncArrows(); });
network.on('deselectNode', function (p) { p.nodes.forEach(function (id) { delete _nbSel[id]; _nbApplyNode(id, _nbScaleNow(), true); }); if (!_dragging) _syncArrows(); });
// The size follows the zoom (the border it replaces was a screen-constant width), so it
// is refreshed when the scale changes. Not while the solver is running: the layout must
// see the sizes the exporter shipped, or the picture would differ from the unbaked one.
network.on('beforeDrawing', function () {
  try { if (network.physics && network.physics.options.enabled) return; } catch (e) {}
  // The scale is applied once. Re-reading it on later frames is what made the
  // dots shimmer while zooming, so a locked disc is not recomputed.
  if (!_nbLock) { _nbApply(false); _nbLock = true; }
  // Putting the radius back is not a recompute. Dragging writes x/y through the
  // DataSet, and vis answers that with setValueRange, which sets EVERY node's
  // size back to the radius it was built with. That is the shrink (and the dimmer
  // cluster) the moment the graph moves. The paint has to see the resting disc.
  _nbRestore();
});
network.on('stabilizationIterationsDone', function () { _nbApply(true); _nbLock = true; });
// One batched edge pass per frame: afterDrawing fires once per vis draw.
network.on('afterDrawing', function () { _EDGE_BATCH.frame(); });
// L12 (#perf): the batched pass is cheaper than one stroke per edge, so on dense graphs
// (arrowheads already deferred) it stays installed at rest instead of only during a
// gesture. Any data change - legend toggle, arrow reveal, theme - can change a group key
// or replace edge instances, so mark the cache dirty and let the next frame rebuild it.
_EDGE_BATCH.setRest(_REST_EDGE_BATCH);
try {
  nodesDS.on('*', function () { _EDGE_BATCH.dirty(); });
  edgesDS.on('*', function () { _EDGE_BATCH.dirty(); });
} catch (e) {}
"""


def _viz_node_limit() -> int:
    """Return the effective viz node limit, honoring GRAPHIFY_VIZ_NODE_LIMIT env var.

    Falls back to MAX_NODES_FOR_VIZ when the env var is unset, empty, or non-integer.
    Set to 0 to disable HTML viz unconditionally (useful for CI runners).
    """
    import os
    raw = os.environ.get("GRAPHIFY_VIZ_NODE_LIMIT")
    if raw is None or not raw.strip():
        return MAX_NODES_FOR_VIZ
    try:
        return int(raw)
    except ValueError:
        return MAX_NODES_FOR_VIZ


def _html_styles() -> str:
    return """<style>
  :root {
    --bg: #0f0f1a; --panel: #1a1a2e; --border: #2a2a4e; --input-border: #3a3a5e;
    --text: #e0e0e0; --text-2: #aaa; --text-3: #ccc; --muted: #555; --count: #666;
    --neighbor-border: #333; --node-label: #ffffff;
    --dim: 0.55; --node-ring: #ffffff; --edge-color: #848484; --edge-opacity: 0.7;
  }
  [data-theme="light"] {
    --bg: #ffffff; --panel: #f8f9fa; --border: #d9dee5; --input-border: #c3cad4;
    --text: #222222; --text-2: #666666; --text-3: #333333; --muted: #888888; --count: #777777;
    --neighbor-border: #ccc; --node-label: #222222;
  }
  html[data-theme='light'] {
    --dim: 0.42; --node-ring: #1f2430; --edge-color: #5b5b66; --edge-opacity: 0.92;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; display: flex; height: 100vh; overflow: hidden; }
  #graph { flex: 1; }
  #sidebar { width: 280px; background: var(--panel); border-left: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  #search-wrap { padding: 12px; border-bottom: 1px solid var(--border); }
  #search { width: 100%; background: var(--bg); border: 1px solid var(--input-border); color: var(--text); padding: 7px 10px; border-radius: 6px; font-size: 13px; outline: none; }
  #search:focus { border-color: #4E79A7; }
  #search-results { max-height: 140px; overflow-y: auto; padding: 4px 12px; border-bottom: 1px solid var(--border); display: none; }
  .search-item { padding: 4px 6px; cursor: pointer; border-radius: 4px; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .search-item:hover { background: var(--border); }
  #info-panel { padding: 14px; border-bottom: 1px solid var(--border); min-height: 140px; }
  #info-panel h3 { font-size: 13px; color: var(--text-2); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
  #info-content { font-size: 13px; color: var(--text-3); line-height: 1.6; }
  #info-content .field { margin-bottom: 5px; }
  #info-content .field b { color: var(--text); }
  #info-content .empty { color: var(--muted); font-style: italic; }
  .neighbor-link { display: block; padding: 2px 6px; margin: 2px 0; border-radius: 3px; cursor: pointer; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-left: 3px solid var(--neighbor-border); }
  .neighbor-link:hover { background: var(--border); }
  #neighbors-list { max-height: 160px; overflow-y: auto; margin-top: 4px; }
  #legend-wrap { flex: 1; overflow-y: auto; padding: 12px; }
  #legend-wrap h3 { font-size: 13px; color: var(--text-2); margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.05em; }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; border-radius: 4px; font-size: 12px; }
  .legend-item:hover { background: var(--border); padding-left: 4px; }
  .legend-item.dimmed { opacity: 0.35; }
  .legend-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: var(--count); font-size: 11px; }
  #stats { padding: 10px 14px; border-top: 1px solid var(--border); font-size: 11px; color: var(--muted); }
  #legend-controls { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding: 4px 0; }
  #legend-controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; font-size: 12px; color: var(--text-2); user-select: none; }
  #legend-controls label:hover { color: var(--text); }
  #family-filter { flex: 1; min-width: 0; background: var(--bg); border: 1px solid var(--input-border); color: var(--text); padding: 4px 7px; border-radius: 5px; font-size: 12px; outline: none; }
  #family-filter:focus { border-color: #4E79A7; }
  #colour-strip { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
  .colour-swatch { width: 15px; height: 15px; border-radius: 50%; border: 1px solid var(--border); cursor: pointer; padding: 0; }
  .colour-swatch:hover { transform: scale(1.15); }
  .legend-empty { color: var(--muted); font-size: 12px; padding: 6px 0; }
  .legend-cb, #select-all-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid var(--input-border); border-radius: 3px; background: var(--bg); cursor: pointer; position: relative; flex-shrink: 0; }
  .legend-cb:checked, #select-all-cb:checked { background: #4E79A7; border-color: #4E79A7; }
  .legend-cb:checked::after, #select-all-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  #select-all-cb:indeterminate { background: #4E79A7; border-color: #4E79A7; }
  #select-all-cb:indeterminate::after { content: ''; position: absolute; left: 2px; top: 5px; width: 8px; height: 2px; background: #fff; border: none; transform: none; }
  #theme-wrap { display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  #theme-wrap button { flex: 1; background: var(--bg); color: var(--text-2); border: 1px solid var(--input-border); border-radius: 4px; padding: 3px 0; font-size: 11px; cursor: pointer; }
  #theme-wrap button:hover { color: var(--text); }
  #theme-wrap button[aria-pressed="true"] { background: #4E79A7; border-color: #4E79A7; color: #fff; }
</style>"""

def _hyperedge_script(hyperedges_json: str) -> str:
    return f"""<script>
// Render hyperedges as shaded regions
const hyperedges = {hyperedges_json};
// afterDrawing passes ctx already transformed to network coordinate space.
// Draw node positions raw — no manual pan/zoom/DPR math needed.

// Andrew's monotone chain. Returns the hull in counter-clockwise order, which
// is what the perimeter must be traced in. Collinear and duplicate points
// collapse to the extremes, so degenerate member sets render as a segment
// rather than a zero-area crossed path.
function convexHull(pts) {{
    const p = pts.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
    if (p.length < 3) return p;
    const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    const build = seq => {{
        const out = [];
        for (const q of seq) {{
            while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], q) <= 0) out.pop();
            out.push(q);
        }}
        out.pop();
        return out;
    }};
    const hull = build(p).concat(build(p.slice().reverse()));
    return hull.length >= 3 ? hull : p;
}}
network.on('afterDrawing', function(ctx) {{
    hyperedges.forEach(h => {{
        const positions = h.nodes
            .map(nid => network.getPositions([nid])[nid])
            .filter(p => p !== undefined);
        if (positions.length < 2) return;
        ctx.save();
        ctx.globalAlpha = 0.12;
        ctx.fillStyle = '#6366f1';
        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        // Centroid and expanded hull in network coordinates.
        // The perimeter must follow hull order, not h.nodes order: tracing the
        // raw member order self-intersects whenever the layout does not happen
        // to place members in angular order, filling as crossed wedges.
        const cx = positions.reduce((s, p) => s + p.x, 0) / positions.length;
        const cy = positions.reduce((s, p) => s + p.y, 0) / positions.length;
        const hull = convexHull(positions);
        const expanded = hull.map(p => ({{
            x: cx + (p.x - cx) * 1.15,
            y: cy + (p.y - cy) * 1.15
        }}));
        ctx.moveTo(expanded[0].x, expanded[0].y);
        expanded.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
        ctx.closePath();
        ctx.fill();
        ctx.globalAlpha = 0.4;
        ctx.stroke();
        // Label
        ctx.globalAlpha = 0.8;
        ctx.fillStyle = '#4f46e5';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(h.label, cx, cy - 5);
        ctx.restore();
    }});
}});
</script>"""

# Interaction feel (#perf L13). Three independent behaviours, all canvas-2d and all
# cheap enough to ship on every export:
#
# 1. Eased wheel zoom. vis zooms once per wheel *event*, and a trackpad fires dozens
#    per frame, so the camera jumps and every event triggers a full redraw. Measured
#    on rsl: 24 long tasks / 2369 ms during a wheel battery, and the user-reported
#    "zoom freezes the graph". Here the target scale is accumulated and approached
#    over rAF frames (one redraw per frame) and the point under the cursor is held
#    fixed. Same battery after: 3 long tasks / 169 ms, zoom_fps 18.4 -> 46.
# 2. Click focus, Obsidian style: the clicked node and its 1-hop neighbours keep their
#    community colour, everything else is blended toward the background. Hover does not
#    dim anything - the graph has to stay whole while the pointer moves, and hovering
#    during a zoom used to repaint the whole graph as nodes slid under the cursor.
#    Painting mutates the node instances' options.color and issues one redraw;
#    datasets.update() for 1886 nodes measured 149.6 ms and is exactly the hitch this
#    avoids.
# 3. An fps / frame-time HUD on H, for judging a machine's real frame budget.
#    textContent only -- the L11 prototype appended a DOM node every frame.
_UX_JS = """
// ---- interaction feel (#perf L13): eased zoom, hover focus, frame HUD ----
(function () {
  var cont = document.getElementById('graph');
  if (!cont || typeof network === 'undefined') return;

  // ---- 1. eased zoom at the cursor -------------------------------------
  // network.moveTo(..., {animation:false}) does NOT emit zoom/pan in vis 9.1.6
  // (measured: 2 moveTo calls -> 0 zoom, 0 pan), so the lean is driven here
  // explicitly rather than by the 'zoom' handler.
  // vis's own wheel handler clamps the scale to [1e-5, 10] (zoom(), in the pinned bundle).
  // We clamped the zoomed-in end to fit*12, which on rsl is ~1.0 - a tenth of what the
  // shipped viewer allows, and the user hit it. Match vis: the ceiling is 10, and only the
  // zoomed-out end keeps a sane floor (fit/6) so the graph cannot be lost in the distance.
  var fitScale = null, MIN_S = 0.004, MAX_S = 10;
  var targetScale = null, curScale = null, anchor = null, raf = 0, animating = false;

  function viewCenter() {
    var r = cont.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  function zoomStep() {
    raf = 0;
    if (targetScale === null || !anchor) { animating = false; return; }
    var c = viewCenter();
    // Land on the target the wheel asked for, in this frame. The earlier version eased
    // toward it (k * 0.25 per frame, ~40 ms of trail), which reads as lag next to vis's
    // instant per-event jump. The coalescing is what the easing was protecting against -
    // one moveTo and one redraw per animation frame, however many wheel events arrive.
    var next = targetScale;
    // world point currently under the cursor; hold it there while the scale changes
    var wp = network.DOMtoCanvas({ x: anchor.x, y: anchor.y });
    curScale = next;
    network.moveTo({
      position: { x: wp.x - (anchor.x - c.x) / next, y: wp.y - (anchor.y - c.y) / next },
      scale: next,
      animation: false
    });
    animating = false;
  }
  cont.addEventListener('wheel', function (e) {
    e.preventDefault();
    e.stopPropagation();          // vis's own per-event wheel handler never sees it
    // Derived on the first wheel, after the fit: a baked build fits after this
    // block runs, and reading it at script time would clamp to the pre-fit scale.
    if (fitScale === null) {
      fitScale = network.getScale();
      MIN_S = Math.max(0.004, fitScale / 6);
      MAX_S = 10;   // vis's own zoom ceiling
    }
    if (curScale === null) { curScale = network.getScale(); targetScale = curScale; }
    // Zoom rate: vis multiplies the scale by 1.1 per wheel event, whatever the delta.
    // Ours used to take e^(120 * 0.0016) = 1.21 per notch, so a gesture ended roughly four
    // times deeper than the shipped viewer (9.7 vs 2.5 on the same 14 events) - and deep
    // zoom is where the edges are thickest and the raster is heaviest. Match vis's notch.
    var unit = e.deltaMode === 1 ? 0.0333 : (e.deltaMode === 2 ? 0.1 : 0.00079);
    targetScale = Math.max(MIN_S, Math.min(MAX_S, targetScale * Math.exp(-e.deltaY * unit)));
    anchor = { x: e.clientX, y: e.clientY };
    animating = true;
    if (!raf) raf = requestAnimationFrame(zoomStep);
  }, { passive: false, capture: true });

  // Keep our copy in sync when something else moves the camera (fit, search focus).
  network.on('zoom', function () {
    if (!animating) { curScale = network.getScale(); targetScale = curScale; }
  });

  // ---- 2. click focus (colour blend, no DataSet update) ----------------
  var BG = '#0f0f1a';
  try {
    var bgv = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
    if (bgv) BG = bgv;
  } catch (e) {}
  function rgb(hex) {
    var h = String(hex).replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function mix(hex, t) {
    var a = rgb(hex), b = rgb(BG);
    return 'rgb(' + Math.round(a[0] + (b[0] - a[0]) * t) + ',' +
                    Math.round(a[1] + (b[1] - a[1]) * t) + ',' +
                    Math.round(a[2] + (b[2] - a[2]) * t) + ')';
  }
  var nodesObj = network.body.nodes;
  var orig = new Map(), dimCache = new Map();
  function captureBase() {
    orig = new Map(); dimCache = new Map();
    for (var oid in nodesObj) {
      var oc = nodesObj[oid] && nodesObj[oid].options && nodesObj[oid].options.color;
      if (oc && typeof oc === 'object' && oc.background) {
        orig.set(oid, { bg: oc.background, bd: oc.border || oc.background });
      }
    }
  }
  captureBase();
  // A theme change moves the base colours: re-capture them and repaint the focus, or the
  // focus would restore the old palette when it is dismissed.
  document.addEventListener('graphify-theme', function () {
    captureBase();
    if (clickOn) paint(clickKeep);
    else if (hoverOn && hoverKeep) paint(hoverKeep);
    else paint(null);
  });
  function dimOf(hex) {
    var d = dimCache.get(hex);
    if (!d) { d = mix(hex, dimAmount()); dimCache.set(hex, d); }
    return d;
  }
  // How far the dimmed nodes are blended toward the background. The background is very
  // dark in the dark theme and very light in the light one, so the same 0.55 buries a
  // node on white and leaves it loud on black: the theme decides.
  function dimAmount() {
    var v = 0.55;
    try {
      var raw = getComputedStyle(document.documentElement).getPropertyValue('--dim').trim();
      if (raw) { var n = parseFloat(raw); if (isFinite(n) && n > 0 && n < 1) v = n; }
    } catch (e) {}
    return v;
  }
  // Click focus (#perf L24): the node you clicked and the nodes connected to it keep
  // their colour, everything else dims, and it stays that way until you click away.
  // The user asked for this explicitly; hover deliberately does not do it, so the
  // picture stays whole while the pointer moves.
  var clickOn = false, clickNode = null, clickKeep = null;
  // The paint is a DELTA: the set that is currently bright is remembered, so moving the
  // pointer from one node to the next only restores the nodes that leave the focus and
  // dims the ones that join it - not all 1886. A full pass is only needed when entering a
  // focus from the all-bright state, or when clearing it.
  var paintedKeep = null;
  function applyNode(nid, keep) {
    var n = nodesObj[nid];
    var nc = n && n.options && n.options.color;
    var o = orig.get(nid);
    if (!nc || typeof nc !== 'object' || !o) return;
    if (!keep || keep.has(nid)) { nc.background = o.bg; nc.border = o.bd; }
    else { var d = dimOf(o.bg); nc.background = d; nc.border = d; }
  }
  function paint(keep) {
    var prev = paintedKeep;
    var full = !prev || !keep;
    if (full) {
      for (var nid in nodesObj) applyNode(nid, keep);
    } else {
      var touched = [];
      prev.forEach(function (id) { if (!keep.has(id)) touched.push(id); });
      keep.forEach(function (id) { if (!prev.has(id)) touched.push(id); });
      for (var i = 0; i < touched.length; i++) applyNode(touched[i], keep);
    }
    paintedKeep = keep ? new Set(keep) : null;
  }
  function neighbourhood(id) {
    var keep = new Set([id]);
    var one = network.getConnectedNodes(id) || [];
    for (var i = 0; i < one.length; i++) keep.add(one[i]);
    return keep;
  }
  // Hover does NOT dim anything: the user wants the picture to stay whole while the
  // pointer moves (and while the graph zooms or pans under it). Dimming is the click
  // focus's job, and only on a click.
  function setClick(id) {
    // No gestureActive() gate here: a click is not a gesture (vis does not fire one during
    // a drag), and the gate used to swallow the click that came right after a zoom, when
    // the lean was still on - the user clicked a node and nothing dimmed.
    if (clickOn && clickNode === id) { clearClick(); return; }   // click again to clear
    clickKeep = neighbourhood(id);
    clickNode = id;
    clickOn = true;
    paint(clickKeep);
    network.redraw();
  }
  function clearClick() {
    if (!clickOn) return;
    clickOn = false; clickNode = null; clickKeep = null;
    // Everything comes back. Only a click sets a focus, so dismissing it must visibly
    // dismiss it.
    paint(null);
    network.redraw();
  }
  network.on('click', function (p) {
    if (p && p.nodes && p.nodes.length) setClick(p.nodes[0]);
    else clearClick();               // clicked empty space
  });
  network.on('hideNode', function (p) { if (p && p.node === clickNode) clearClick(); });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') clearClick();
  });

  // ---- 3. frame HUD on H ----------------------------------------------
  var hud = document.createElement('div');
  hud.style.cssText = 'position:fixed;top:8px;right:8px;z-index:9999;background:rgba(0,0,0,.72);' +
    'color:#fff;font:11px/1.4 ui-monospace,monospace;padding:4px 8px;border-radius:4px;' +
    'display:none;pointer-events:none';
  document.body.appendChild(hud);
  var hudOn = false, frames = 0, t0 = performance.now(), fps = 0;
  var lastT = t0, ft = 0, loopId = 0;
  // The HUD loop used to run for the life of the page whether or not the HUD was on,
  // which kept a 144 Hz rAF wake-up alive on an idle page (measured: 0 draws but 432
  // rAF callbacks in 3 s of silence). It now starts on H and stops on H.
  function loop(t) {
    ft = t - lastT; lastT = t; frames++;
    if (t - t0 >= 500) { fps = Math.round(frames * 1000 / (t - t0)); frames = 0; t0 = t; }
    if (!hudOn) { loopId = 0; return; }
    hud.textContent = fps + ' fps   ' + ft.toFixed(1) + ' ms';
    loopId = requestAnimationFrame(loop);
  }
  document.addEventListener('keydown', function (e) {
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if ((e.key === 'h' || e.key === 'H') && tag !== 'INPUT' && tag !== 'TEXTAREA') {
      hudOn = !hudOn;
      hud.style.display = hudOn ? 'block' : 'none';
      if (hudOn) {
        lastT = t0 = performance.now(); frames = 0;
        if (!loopId) loopId = requestAnimationFrame(loop);
      } else if (loopId) {
        cancelAnimationFrame(loopId); loopId = 0;
      }
    }
  });
})();
"""


def _html_script(nodes_json: str, edges_json: str, legend_json: str,
                 defer_arrows: bool = False,
                 lean_gestures: bool = False,
                 baked: bool = False,
                 hover_enabled: bool = True,
                 community_colour_json: str = "{}") -> str:
    # Arrowheads are deferred to hover only on dense graphs (see
    # ARROW_DEFER_EDGE_THRESHOLD); otherwise emitted exactly as before.
    _arrow_default = "false" if defer_arrows else "true, scaleFactor: 0.5"
    _hover_enabled = "true" if hover_enabled else "false"
    # Pre-baked positions (#perf L10): when the graph ships stabilized x/y,
    # skip the on-load solver entirely (physics off, no stabilization pass).
    physics_enabled = "false" if baked else "true"
    stab_iters = "0" if baked else "200"
    stabilization_handler = "" if baked else (
        "network.once('stabilizationIterationsDone', () => {"
        " network.setOptions({ physics: { enabled: false } });"
        " _savePositions(); });"
    )
    baked_fit_js = "try { network.fit({ animation: false }); } catch (e) {}" if baked else ""
    # L12 (#perf): keep the batched edge pass installed at rest. It is only worth it, and
    # only safe by default, when the arrowheads are already deferred to hover: an edge that
    # draws its arrowhead cannot come out of the batch (see _arrowed in _LEAN_GESTURE_JS).
    lean_js = ""
    if lean_gestures:
        rest_batch = "true" if defer_arrows else "false"
        lean_js = "const _REST_EDGE_BATCH = " + rest_batch + ";\n" + _LEAN_GESTURE_JS
    return f"""<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const LEGEND = {legend_json};

// HTML-escape helper — prevents XSS when injecting graph data into innerHTML
function esc(s) {{
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}}

// Build vis datasets
const nodesDS = new vis.DataSet(RAW_NODES.map((n, i) => ({{
  id: n.id, label: n.label, color: n.color, size: n.size,
  font: n.font, title: n.title,
  // Pre-baked positions (#perf L10): when the graph was baked (x/y shipped),
  // use them verbatim and skip the solver. Otherwise fall back to the
  // Fermat/golden-angle spiral seed (#3699) so physics still settles.
  x: (n.x !== undefined && n.x !== null) ? n.x : 30 * Math.sqrt(i) * Math.cos(i * 2.4),
  y: (n.y !== undefined && n.y !== null) ? n.y : 30 * Math.sqrt(i) * Math.sin(i * 2.4),
  community: n.community, community_name: n.community_name,
  source_file: n.source_file, file_type: n.file_type, degree: n.degree,
  member_count: n.member_count,
}})));

const edgesDS = new vis.DataSet(RAW_EDGES.map((e, i) => ({{
  id: i, from: e.from, to: e.to,
  label: '',
  title: e.title,
  dashes: e.dashes,
  width: e.width,
  color: e.color,
  arrows: {{ to: {{ enabled: {_arrow_default} }} }},
}})));

const container = document.getElementById('graph');
const network = new vis.Network(container, {{ nodes: nodesDS, edges: edgesDS }}, {{
  physics: {{
    enabled: {physics_enabled},
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {{
      gravitationalConstant: -60,
      centralGravity: 0.005,
      springLength: 120,
      springConstant: 0.08,
      damping: 0.4,
      avoidOverlap: 0.8,
    }},
    stabilization: {{ iterations: {stab_iters}, updateInterval: {stab_iters}, fit: true }},
  }},
  interaction: {{
    hover: {_hover_enabled},
    tooltipDelay: 100,
    navigationButtons: false,
    keyboard: false,
  }},
  nodes: {{ shape: 'dot', borderWidth: 1.5 }},
  edges: {{ smooth: {{ type: 'continuous', roundness: 0.2 }}, selectionWidth: 3, hoverWidth: 1 }},
}});
{_POSITION_CACHE_JS}
{lean_js}

// Theme toggle (#3894): Light / Dark / System, persisted in localStorage.
//
// The theme is not only CSS: the edge colour, the selection ring and the dimming amount
// are drawn into the canvas, so they have to follow the theme too. The community palette
// is deliberately the SAME in both themes - a darkened light-theme variant was tried and
// the original colours are the ones that look right on white (the user's call).
const THEME_KEY = 'graphify-theme';
const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
const PALETTE = {_PAL_JS};
// The palette index of every community: community id modulo the palette size, exactly
// what the shipped viewer has always done. The classification is part of the look.
const COMMUNITY_COLOUR = {community_colour_json};
let themeIsLight = false;
function palByIndex(i) {{
  return PALETTE[((i % PALETTE.length) + PALETTE.length) % PALETTE.length];
}}
function palColor(cid) {{
  let i = (cid === undefined || cid === null) ? 0 : COMMUNITY_COLOUR[cid];
  if (i === undefined || i === null) i = cid % PALETTE.length;
  return palByIndex(i);
}}
function themePref() {{
  let p = null;
  try {{ p = localStorage.getItem(THEME_KEY); }} catch (e) {{}}
  return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
}}
function themeTokens() {{
  const cs = getComputedStyle(document.documentElement);
  const op = parseFloat((cs.getPropertyValue('--edge-opacity') || '').trim());
  return {{
    ring: (cs.getPropertyValue('--node-ring') || '').trim() || (themeIsLight ? '#1f2430' : '#ffffff'),
    edge: (cs.getPropertyValue('--edge-color') || '').trim() || (themeIsLight ? '#5b5b66' : '#848484'),
    edgeOpacity: (isFinite(op) && op > 0 && op <= 1) ? op : 0.7,
    label: (cs.getPropertyValue('--node-label') || '').trim() || '#ffffff',
  }};
}}
// Re-colour what is drawn into the canvas. Instance writes, never a DataSet update:
// one update for 1886 nodes measured 149.6 ms, and a theme switch has to feel instant.
function retint() {{
  const tk = themeTokens();
  let community = null;
  try {{
    community = {{}};
    nodesDS.get().forEach(n => {{ community[n.id] = n.community; }});
  }} catch (e) {{ community = null; }}
  const nodes = network.body && network.body.nodes;
  if (nodes) {{
    for (const id in nodes) {{
      const n = nodes[id];
      if (!n || !n.options) continue;
      const c = n.options.color;
      if (!c || typeof c !== 'object') continue;
      const cid = community ? community[id] : undefined;
      if (cid === undefined || cid === null) continue;   // unknown node: leave it alone
      const col = palColor(cid);
      c.background = col;
      c.border = col;
      if (!c.highlight) c.highlight = {{}};
      c.highlight.background = col; c.highlight.border = tk.ring;
      if (!c.hover) c.hover = {{}};
      c.hover.background = col; c.hover.border = tk.ring;
      if (n.options.font) n.options.font.color = tk.label;
    }}
  }}
  // The edges: vis's default grey vanishes on a white background, and at 0.7 opacity
  // over white the inherited community colour washes out as well - so the edge colour and
  // its opacity are theme values.
  const edges = network.body && network.body.edges;
  if (edges) {{
    for (const id in edges) {{
      const e = edges[id];
      if (!e || !e.options) continue;
      const oc = e.options.color;
      const op = (oc && typeof oc === 'object' && oc.opacity !== undefined) ? oc.opacity : 0.7;
      e.options.color = {{ color: tk.edge, opacity: themeIsLight ? tk.edgeOpacity : op }};
    }}
    try {{ if (typeof _EDGE_BATCH !== 'undefined' && _EDGE_BATCH.dirty) _EDGE_BATCH.dirty(); }} catch (e) {{}}
  }}
  // The legend swatches follow the palette.
  const items = document.querySelectorAll('.legend-item');
  for (let i = 0; i < items.length; i++) {{
    const dot = items[i].querySelector('.legend-dot');
    const cid = LEGEND[i] && LEGEND[i].cid;
    if (dot && cid !== undefined && cid !== null) dot.style.background = palColor(cid);
  }}
  // The focus block owns the dimmed colours; tell it the base colours moved.
  try {{ document.dispatchEvent(new CustomEvent('graphify-theme')); }} catch (e) {{}}
  try {{ network.redraw(); }} catch (e) {{}}
}}
// A data change (the legend filter) re-resolves the node instances from the DataSet,
// which would put the dark palette back on a light theme: re-tint after every change.
try {{
  nodesDS.on('*', function () {{ retint(); }});
}} catch (e) {{}}
function applyTheme(pref) {{
  const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
  const root = document.documentElement;
  if (!root) return;
  themeIsLight = (t === 'light');
  root.setAttribute('data-theme', t);
  document.querySelectorAll('[data-theme-choice]').forEach(b => {{
    b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
  }});
  // The label colour is drawn by vis's label module, which only picks it up from a
  // DataSet update - so the labelled nodes (the high-degree ones, a few hundred) are
  // updated, not all 1886.
  const labelColor = themeTokens().label;
  if (labelColor) {{
    const labelled = nodesDS.get().filter(n => n.font && n.font.size);
    if (labelled.length) {{
      nodesDS.update(labelled.map(n => ({{ id: n.id, font: Object.assign({{}}, n.font, {{ color: labelColor }}) }})));
    }}
  }}
  retint();
}}
document.querySelectorAll('[data-theme-choice]').forEach(b => {{
  b.addEventListener('click', () => {{
    const pref = b.dataset.themeChoice;
    try {{ localStorage.setItem(THEME_KEY, pref); }} catch (e) {{}}
    applyTheme(pref);
  }});
}});
if (themeMQ) {{
  const onSchemeChange = () => {{ if (themePref() === 'system') applyTheme('system'); }};
  if (themeMQ.addEventListener) themeMQ.addEventListener('change', onSchemeChange);
  else if (themeMQ.addListener) themeMQ.addListener(onSchemeChange);
}}
applyTheme(themePref());

{stabilization_handler}
{baked_fit_js}
{_ARROW_HOVER_JS if defer_arrows else ''}

function showInfo(nodeId) {{
  const n = nodesDS.get(nodeId);
  if (!n) return;
  const neighborIds = network.getConnectedNodes(nodeId);
  const neighborItems = neighborIds.map(nid => {{
    const nb = nodesDS.get(nid);
    const color = nb ? palColor(nb.community) : '#555';
    return `<span class="neighbor-link" style="border-left-color:${{esc(color)}}" data-nid="${{esc(nid)}}">${{esc(nb ? nb.label : nid)}}</span>`;
  }}).join('');
  const isMetaNode = !n.file_type && !n.source_file;
  let html = `<div class="field"><b>${{esc(n.label)}}</b></div>`;
  if (!isMetaNode) {{
    html += `<div class="field">Type: ${{esc(n.file_type || 'unknown')}}</div>`;
  }}
  html += `<div class="field">Community: ${{esc(n.community_name || '')}}</div>`;
  if (!isMetaNode) {{
    html += `<div class="field">Source: ${{esc(n.source_file || '-')}}</div>`;
  }} else if (n.member_count !== undefined && n.member_count !== null) {{
    html += `<div class="field">Members: ${{esc(n.member_count)}}</div>`;
  }}
  html += `<div class="field">Degree: ${{n.degree}}</div>`;
  if (neighborIds.length) {{
    html += `<div class="field" style="margin-top:8px;color:var(--text-2);font-size:11px">Neighbors (${{neighborIds.length}})</div><div id="neighbors-list">${{neighborItems}}</div>`;
  }}
  document.getElementById('info-content').innerHTML = html;
}}

function focusNode(nodeId) {{
  network.focus(nodeId, {{ scale: 1.4, animation: true }});
  network.selectNodes([nodeId]);
  showInfo(nodeId);
}}

// Neighbor links use a data attribute + one delegated listener rather than an
// inline onclick. A node id/label sourced from a document or a scraped URL
// (graphify add) can contain a double-quote; dropping the stringified id
// unescaped into a quoted onclick both broke every link and allowed a hostile
// source to inject an event handler into the local report (stored XSS, #1838).
// esc() on data-nid keeps the value inside the attribute; the listener reads it
// back verbatim. Bound to document so it survives the innerHTML rebuild that
// recreates #neighbors-list on each showInfo().
document.addEventListener('click', e => {{
  const el = e.target.closest('.neighbor-link');
  if (el && el.dataset.nid !== undefined) focusNode(el.dataset.nid);
}});

// Sidebar tooltips reuse vis-network's .vis-tooltip style and 100ms tooltipDelay.
// Names get one only when CSS ellipsis truncates them (the full text is still in
// the DOM); counts always get one, to say what the number is. Text is set with
// textContent only (labels are untrusted). Delegated on document so rows rebuilt
// later (search results, showInfo()) are covered.
const sidebarTip = document.createElement('div');
sidebarTip.className = 'vis-tooltip';
sidebarTip.style.cssText = 'white-space: normal; max-width: 360px; overflow-wrap: break-word;';
document.body.appendChild(sidebarTip);
let sidebarTipTimer = null;
let sidebarTipEl = null;    // element whose text the tooltip shows
let sidebarTipZone = null;  // element the pointer must leave to hide it
function hideSidebarTip() {{
  clearTimeout(sidebarTipTimer);
  sidebarTip.style.visibility = 'hidden';
  sidebarTip.textContent = '';
  sidebarTipEl = sidebarTipZone = null;
}}
document.addEventListener('mouseover', e => {{
  const zone = e.target.closest && e.target.closest('.legend-count, .legend-item, .search-item, .neighbor-link');
  // Anywhere on a legend row except its count (dot, checkbox, gaps, padding)
  // stands for the row's name, so moving within the row never re-triggers it.
  const el = zone && zone.classList.contains('legend-item') ? zone.querySelector('.legend-label') : zone;
  if (!el || el === sidebarTipEl) return;
  hideSidebarTip();
  const isCount = el.classList.contains('legend-count');
  if (!isCount && el.scrollWidth <= el.clientWidth) return;
  const text = isCount ? `${{el.textContent}} ${{el.textContent === '1' ? 'node' : 'nodes'}}` : el.textContent;
  sidebarTipEl = el;
  sidebarTipZone = zone;
  const x = e.clientX, y = e.clientY;
  sidebarTipTimer = setTimeout(() => {{
    sidebarTip.textContent = text;
    sidebarTip.style.left = sidebarTip.style.top = '0px';  // measure at full max-width
    sidebarTip.style.visibility = 'visible';
    const w = sidebarTip.offsetWidth, h = sidebarTip.offsetHeight;
    sidebarTip.style.left = Math.max(4, Math.min(x + 12, window.innerWidth - w - 4)) + 'px';
    sidebarTip.style.top = (y + 16 + h > window.innerHeight ? Math.max(4, y - h - 8) : y + 16) + 'px';
  }}, 100);
}});
document.addEventListener('mouseout', e => {{
  if (sidebarTipZone && !sidebarTipZone.contains(e.relatedTarget)) hideSidebarTip();
}});
// A click rebuilds or hides the row (showInfo(), search pick) without a mouseout.
document.addEventListener('mousedown', hideSidebarTip);

// Track hovered node — hover detection is more reliable than click params
let hoveredNodeId = null;
network.on('hoverNode', params => {{
  hoveredNodeId = params.node;
  container.style.cursor = 'pointer';
}});
network.on('blurNode', () => {{
  hoveredNodeId = null;
  container.style.cursor = 'default';
}});
container.addEventListener('click', () => {{
  if (hoveredNodeId !== null) {{
    showInfo(hoveredNodeId);
    network.selectNodes([hoveredNodeId]);
  }}
}});
network.on('click', params => {{
  if (params.nodes.length > 0) {{
    showInfo(params.nodes[0]);
  }} else if (hoveredNodeId === null) {{
    document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>';
  }}
}});

const searchInput = document.getElementById('search');
const searchResults = document.getElementById('search-results');
searchInput.addEventListener('input', () => {{
  const q = searchInput.value.toLowerCase().trim();
  searchResults.innerHTML = '';
  if (!q) {{ searchResults.style.display = 'none'; return; }}
  const matches = RAW_NODES.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
  if (!matches.length) {{ searchResults.style.display = 'none'; return; }}
  searchResults.style.display = 'block';
  matches.forEach(n => {{
    const el = document.createElement('div');
    el.className = 'search-item';
    el.textContent = n.label;
    el.style.borderLeft = `3px solid ${{palColor(n.community)}}`;
    el.style.paddingLeft = '8px';
    el.onclick = () => {{
      network.focus(n.id, {{ scale: 1.5, animation: true }});
      network.selectNodes([n.id]);
      showInfo(n.id);
      searchResults.style.display = 'none';
      searchInput.value = '';
    }};
    searchResults.appendChild(el);
  }});
}});
document.addEventListener('click', e => {{
  if (!searchResults.contains(e.target) && e.target !== searchInput)
    searchResults.style.display = 'none';
}});

// ---- the families panel ---------------------------------------------------
// The community list used to be built from the community *labels*, so on a graph
// without labels the panel was empty and there was no way to filter by family at all.
// It is built from the communities themselves now: a checkbox to hide a family, its
// colour, its name and its size; a filter box over the names; a colour strip that
// shows one colour at a time; and clicking a name shows that family alone.
const hiddenCommunities = new Set();
let appliedHidden = new Set();
const nodesByCommunity = new Map();
for (const n of RAW_NODES) {{
  if (!nodesByCommunity.has(n.community)) nodesByCommunity.set(n.community, []);
  nodesByCommunity.get(n.community).push(n.id);
}}

var selectAllCb = document.getElementById('select-all-cb');
var legendEl = document.getElementById('legend');
var familyFilterEl = document.getElementById('family-filter');
var colourStripEl = document.getElementById('colour-strip');

function updateSelectAllState() {{
  const total = LEGEND.length;
  const hidden = hiddenCommunities.size;
  if (!selectAllCb) return;
  selectAllCb.checked = hidden === 0;
  selectAllCb.indeterminate = hidden > 0 && hidden < total;
}}

// One data update, and only for the families that actually changed. A DataSet update
// for 1886 nodes measured 149.6 ms, and "show all" used to pay it on every click even
// when nothing was hidden. A change that touches many families is split into four
// frames: a bulk filter is a deliberate action, but a 280 ms block is still a freeze.
function applyHidden(next) {{
  const changed = [];
  for (const cid of next) if (!appliedHidden.has(cid)) changed.push(cid);
  for (const cid of appliedHidden) if (!next.has(cid)) changed.push(cid);
  appliedHidden = new Set(next);
  if (!changed.length) {{
    updateSelectAllState();
    renderFamilies();
    return;
  }}
  const perFrame = Math.max(1, Math.ceil(changed.length / 4));
  let i = 0;
  const step = () => {{
    const part = changed.slice(i, i + perFrame);
    i += perFrame;
    const updates = [];
    for (const cid of part) {{
      const hide = next.has(cid);
      for (const id of nodesByCommunity.get(cid) || []) updates.push({{ id: id, hidden: hide }});
    }}
    if (updates.length) nodesDS.update(updates);
    if (i < changed.length) {{
      requestAnimationFrame(step);
    }} else {{
      updateSelectAllState();
      renderFamilies();
    }}
  }};
  step();
}}

function setHidden(next) {{
  hiddenCommunities.clear();
  next.forEach(c => hiddenCommunities.add(c));
  applyHidden(next);
}}

function toggleCommunity(cid, hide) {{
  const next = new Set(hiddenCommunities);
  if (hide) next.add(cid); else next.delete(cid);
  setHidden(next);
}}

// Show one family alone (clicking it again shows everything).
function isolateCommunity(cid) {{
  const alreadyAlone = LEGEND.length > 1 &&
    LEGEND.every(c => c.cid === cid || hiddenCommunities.has(c.cid));
  if (alreadyAlone) {{ setHidden(new Set()); return; }}
  const next = new Set();
  for (const c of LEGEND) if (c.cid !== cid) next.add(c.cid);
  setHidden(next);
}}

// Show the families of one colour (clicking it again shows everything).
function showColour(index) {{
  const already = LEGEND.every(c => (c.colourIndex === index) !== hiddenCommunities.has(c.cid));
  if (already) {{ setHidden(new Set()); return; }}
  const next = new Set();
  for (const c of LEGEND) if (c.colourIndex !== index) next.add(c.cid);
  setHidden(next);
}}

function visibleFamilies() {{
  const q = (familyFilterEl && familyFilterEl.value || '').toLowerCase().trim();
  if (!q) return LEGEND;
  return LEGEND.filter(c => c.label.toLowerCase().indexOf(q) >= 0 || String(c.cid) === q);
}}

function renderFamilies() {{
  if (!legendEl) return;
  legendEl.innerHTML = '';
  const list = visibleFamilies();
  for (const c of list) {{
    const item = document.createElement('div');
    item.className = 'legend-item';
    if (hiddenCommunities.has(c.cid)) item.classList.add('dimmed');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'legend-cb';
    cb.checked = !hiddenCommunities.has(c.cid);
    cb.addEventListener('change', (e) => {{
      e.stopPropagation();
      toggleCommunity(c.cid, !cb.checked);
    }});
    item.innerHTML = `<div class="legend-dot" style="background:${{palColor(c.cid)}}"></div>
      <span class="legend-label">${{c.label}}</span>
      <span class="legend-count">${{c.count}}</span>`;
    item.prepend(cb);
    item.title = 'Hide this family, or click its name to show it alone';
    item.onclick = (e) => {{
      if (e.target === cb) return;
      isolateCommunity(c.cid);
    }};
    legendEl.appendChild(item);
  }}
  if (!list.length) {{
    const empty = document.createElement('div');
    empty.className = 'legend-empty';
    empty.textContent = 'No family matches';
    legendEl.appendChild(empty);
  }}
  renderColourStrip();
}}

function renderColourStrip() {{
  if (!colourStripEl) return;
  colourStripEl.innerHTML = '';
  const counts = new Map();
  for (const c of LEGEND) counts.set(c.colourIndex, (counts.get(c.colourIndex) || 0) + 1);
  for (const [index, n] of counts) {{
    const b = document.createElement('button');
    b.className = 'colour-swatch';
    b.style.background = palByIndex(index);
    b.title = n + ' famil' + (n === 1 ? 'y' : 'ies') + ' - click to show this colour alone';
    b.onclick = () => showColour(index);
    colourStripEl.appendChild(b);
  }}
}}

function toggleAllCommunities(hide) {{
  const next = new Set();
  if (hide) for (const c of LEGEND) next.add(c.cid);
  setHidden(next);
}}

if (familyFilterEl) familyFilterEl.addEventListener('input', renderFamilies);
renderFamilies();
{_UX_JS if lean_gestures else ''}
</script>"""


def _html_document_title(output_path: str) -> str:
    """Return a portable label for the graph.html <title>.

    Tracked artifacts must not embed the generator host absolute path
    (regression of #433; reported again as #2598 on Windows). Keep from the
    configured output-dir bare name (``graphify-out`` / ``GRAPHIFY_OUT``
    basename) onward — portable in every case; otherwise fall back to a
    cwd-relative label, and finally the filename only.
    """
    from graphify.paths import GRAPHIFY_OUT_NAME

    raw = str(output_path).replace("\\", "/")
    # Drop Windows drive prefix so Path parts are comparable on any OS.
    if len(raw) >= 3 and raw[1] == ":" and raw[0].isalpha() and raw[2] == "/":
        raw = raw[2:]  # "/Users/..." style after drive strip
    p = Path(raw)

    parts = list(Path(raw).parts)
    # Path("C:/Users/..") on POSIX may keep "C:" as first part — strip it.
    if parts and len(parts[0]) == 2 and parts[0][1] == ":" and parts[0][0].isalpha():
        parts = parts[1:]
    # Prefer keeping from the output-dir marker onward: portable in every
    # case, whereas a cwd-relative path still leaks host/user segments when
    # the graph is built from a directory ABOVE the project (#2598 follow-up).
    marker = GRAPHIFY_OUT_NAME
    for i, part in enumerate(parts):
        if part == marker or part.startswith("graphify-out"):
            return "/".join(parts[i:])

    # No standard out-dir marker (fully custom output path): fall back to a
    # cwd-relative label when the target is under cwd, else the bare filename.
    try:
        resolved = p if p.is_absolute() else (Path.cwd() / p)
        rel = resolved.resolve().relative_to(Path.cwd().resolve())
        label = rel.as_posix()
        if label and label != ".":
            return label
    except (ValueError, OSError, RuntimeError):
        pass

    name = p.name
    return name if name else "graph.html"

def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
    learning_overlay: dict | None = None,
) -> bool:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.

    Returns True when the output was written. Returns False when an aggregated
    view would contain fewer than two communities and is intentionally skipped.
    """
    limit = node_limit if node_limit is not None else _viz_node_limit()
    if G.number_of_nodes() > limit:
        if node_limit is not None:
            # Build aggregated community meta-graph
            from collections import Counter as _Counter
            import networkx as _nx
            print(f"Graph has {G.number_of_nodes()} nodes (above {limit} limit). Building aggregated community view...")
            node_to_community = {nid: cid for cid, members in communities.items() for nid in members}
            meta = _nx.Graph()
            for cid, members in communities.items():
                meta.add_node(str(cid), label=(community_labels or {}).get(cid, f"Community {cid}"))
            edge_counts = _Counter()
            for u, v in G.edges():
                cu, cv = node_to_community.get(u), node_to_community.get(v)
                if cu is not None and cv is not None and cu != cv:
                    edge_counts[(min(cu, cv), max(cu, cv))] += 1
            for (cu, cv), w in edge_counts.items():
                meta.add_edge(str(cu), str(cv), weight=w,
                              relation=f"{w} cross-community edges", confidence="AGGREGATED")
            if meta.number_of_nodes() <= 1:
                print("Single community - aggregated view not useful. Skipping graph.html.")
                return False
            meta_communities = {cid: [str(cid)] for cid in communities}
            mc = {cid: len(members) for cid, members in communities.items()}
            # Remap hyperedges from semantic node IDs to community IDs
            raw_hyperedges = G.graph.get("hyperedges", [])
            if raw_hyperedges:
                remapped = []
                for he in raw_hyperedges:
                    he_members = he.get("nodes", [])
                    comm_ids, seen = [], set()
                    for nid in he_members:
                        c = node_to_community.get(nid)
                        if c is None:
                            continue
                        s = str(c)
                        if s in seen:
                            continue
                        seen.add(s)
                        comm_ids.append(s)
                    if len(comm_ids) < 2:
                        continue
                    remapped.append({
                        "id": he.get("id", ""),
                        "label": he.get("label") or he.get("relation", "").replace("_", " "),
                        "nodes": comm_ids,
                    })
                meta.graph["hyperedges"] = remapped
            written = to_html(meta, meta_communities, output_path,
                              community_labels=community_labels, member_counts=mc)
            if not written:
                return False
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return True
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz "
            f"(limit: {limit}). Use --no-viz, raise GRAPHIFY_VIZ_NODE_LIMIT, "
            f"or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Work-memory overlay (derived sidecar). When not passed explicitly, load it
    # best-effort from the sibling .graphify_learning.json next to the output
    # graph.html (which lives beside graph.json). Empty/missing => no learning
    # fields, so the un-annotated render is byte-identical to pre-feature.
    if learning_overlay is None:
        learning_overlay = {}
        try:
            from graphify.reflect import load_learning_overlay as _llo
            learning_overlay = _llo(Path(output_path))
        except Exception:
            learning_overlay = {}
    # Status -> ring color. preferred=green, contested=amber. Tentative gets no
    # ring (it's not yet trustworthy enough to highlight in the map).
    _RING = {"preferred": "#22c55e", "contested": "#f59e0b"}

    # Build nodes list for vis.js
    # Community colouring is the one the shipped viewer has always used: palette index =
    # community id modulo the palette size. An adjacency-aware greedy colouring was tried
    # (so two neighbouring families never share a colour) and it was wrong for the picture:
    # it hands every non-adjacent community the lowest free index, so whole regions collapse
    # onto one colour and the graph loses the variety the user reads the families by. The
    # classification is part of the viewer's look, not a perf lever: leave it alone.
    community_colour = {cid: cid % len(COMMUNITY_COLORS) for cid in set(node_community.values())}
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[community_colour.get(cid, cid % len(COMMUNITY_COLORS))]
        label = sanitize_label(data.get("label", node_id))
        deg = degree.get(node_id, 1)
        if member_counts:
            mc = member_counts.get(cid, 1)
            size = 10 + 30 * (mc / max_mc)
            font_size = 12
        else:
            size = 10 + 30 * (deg / max_deg)
            # Only show label for high-degree nodes by default; others show on hover
            font_size = 12 if deg >= max_deg * 0.15 else 0
        node = {
            "id": node_id,
            "label": label,
            # Keep the community colour when selected or hovered, and accent with a
            # white border ring. The old highlight repainted the node #ffffff, which
            # made a selected/hovered cluster look washed out (#perf L13).
            "color": {
                "background": color,
                "border": color,
                "highlight": {"background": color, "border": "#ffffff"},
                "hover": {"background": color, "border": "#ffffff"},
            },
            "size": round(size, 1),
            "font": {"size": font_size, "color": "#ffffff"},
            # Tooltip `title` is a STRING, which vis-network renders via
            # Popup.setText -> `frame.innerText = t` (verified in the pinned
            # 9.1.6 bundle: the only non-Element branch is innerText, and the
            # bundle has zero `innerHTML = <var>` sinks). So raw special chars
            # are shown literally and must NOT be html-escaped here or the user
            # sees `&amp;`/`&lt;` in the tooltip (#3664/#3686). This is the
            # #1838 stored-XSS boundary: never pass an HTMLElement as `title`,
            # and do not change the vis-network pin below without re-checking
            # Popup rendering (the test_export version-pin guard enforces this).
            "title": label,
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        }
        if member_counts:
            node["member_count"] = member_counts.get(cid, len(communities.get(cid, [])))
        # Pre-baked positions (#perf L10): when the input graph carries stabilized
        # x/y (e.g. produced by `harness/bake.mjs` or a future `--bake` step), ship
        # them so the first open skips the on-load solver. Capability is untouched:
        # nodes/edges/communities/direction/confidence all survive; only the
        # recompute cost moves offline. Absent -> the spiral seed + solver (as before).
        if data.get("x") is not None and data.get("y") is not None:
            node["x"] = data["x"]
            node["y"] = data["y"]
        # Conditional learning fields — only present for annotated nodes, so
        # un-annotated output keeps the exact pre-feature node dict shape.
        entry = learning_overlay.get(str(node_id)) if learning_overlay else None
        if entry:
            status = sanitize_label(str(entry.get("status", "")))
            stale = bool(entry.get("stale"))
            node["learning_status"] = status
            node["learning_stale"] = stale
            ring = _RING.get(status)
            if ring:
                # Status-colored ring via the border; stale => desaturated +
                # dashed (vis.js supports per-node `shapeProperties.borderDashes`).
                if stale:
                    ring = "#9ca3af"
                    node["shapeProperties"] = {"borderDashes": [4, 4]}
                node["borderWidth"] = 3
                # Selection keeps the community fill here too; the status ring is
                # what must stay legible, so it stays the highlight border.
                node["color"] = {
                    "background": color, "border": ring,
                    "highlight": {"background": color, "border": ring},
                    "hover": {"background": color, "border": ring},
                }
            # Lesson line appended to the hover title.
            if status == "contested":
                lesson = f"Lesson: contested (useful {entry.get('uses', 0)} / dead-end {entry.get('neg', 0)})"
            elif status == "preferred":
                lesson = f"Lesson: preferred source ({entry.get('uses', 0)} useful, score={entry.get('score', 0)})"
            else:
                lesson = f"Lesson: {status} ({entry.get('uses', 0)} useful)"
            if stale:
                lesson += " [code changed — re-verify]"
            node["title"] = f"{label}\n{sanitize_label(lesson)}"
        vis_nodes.append(node)

    # Build edges list. Restore original edge direction from _src/_tgt
    # (stashed by build.py for exactly this reason): undirected NetworkX
    # canonicalizes endpoint order, which would otherwise flip the arrow
    # for `calls` and `rationale_for` in the rendered graph (#563).
    vis_edges = []
    for u, v, data in G.edges(data=True):
        confidence = data.get("confidence", "EXTRACTED")
        relation = data.get("relation", "")
        true_src = data.get("_src", u)
        true_tgt = data.get("_tgt", v)
        vis_edges.append({
            "from": true_src,
            "to": true_tgt,
            "label": relation,
            "title": sanitize_label(f"{relation} [{confidence}]"),
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
            "color": {"opacity": 0.7 if confidence == "EXTRACTED" else 0.35},
            "confidence": confidence,
        })

    # Build community legend data.
    # The list used to be built from the community *labels*, so on a graph without
    # labels the panel was empty and there was no way to filter by family at all. It is
    # built from the communities themselves now, and a community without a label is named
    # after the file most of its members come from.
    src_counts: dict = {}
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        src = str(data.get("source_file") or "").strip()
        if not src:
            continue
        src_counts.setdefault(cid, {})
        src_counts[cid][src] = src_counts[cid].get(src, 0) + 1
    legend_data = []
    all_cids = set(communities.keys()) | set((community_labels or {}).keys())
    for cid in sorted(all_cids):
        index = community_colour.get(cid, cid % len(COMMUNITY_COLORS))
        color = COMMUNITY_COLORS[index]
        named = (community_labels or {}).get(cid)
        if not named:
            counts = src_counts.get(cid) or {}
            if counts:
                best = max(counts.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
                named = best if len(best) <= 42 else best[:39] + "..."
        lbl = _html.escape(sanitize_label(named or f"Community {cid}"))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "colourIndex": index,
                            "label": lbl, "count": n})

    # Escape every `<` as < so embedded JSON cannot break out of the <script>
    # element. Escaping only `</` is not enough: an unclosed `<!--` then a later
    # `<script` in a label drive the HTML tokenizer into script-data-double-escaped
    # state, where the real `</script>` no longer closes the tag and the page goes
    # blank (#4124). `<` round-trips through JSON.parse, so labels render unchanged.
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("<", "\\u003c")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    # Pre-baked positions (#perf L10): if every node carries stabilized x/y, ship
    # them and skip the on-load solver entirely. Physics off from the first frame.
    _baked_all = bool(vis_nodes) and all(
        n.get("x") is not None and n.get("y") is not None for n in vis_nodes
    )
    physics_enabled = "false" if _baked_all else "true"
    stab_iters = "0" if _baked_all else "200"
    stabilization_handler = "" if _baked_all else (
        "network.once('stabilizationIterationsDone', () => {"
        " network.setOptions({ physics: { enabled: false } });"
        " _savePositions(); });"
    )
    baked_fit_js = "try { network.fit({ animation: false }); } catch (e) {}" if _baked_all else ""
    title = _html.escape(sanitize_label(_html_document_title(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>graphify - {title}</title>
<script id="graphify-desync">
// L37: a low-latency canvas. `desynchronized: true` decouples the canvas from the
// compositor, so a draw no longer blocks on a composite and the new frame is presented
// on the next vsync instead of being queued behind the compositor's backlog. This is
// the single biggest lever for the interaction-to-next-paint on a dense graph: it cuts
// the presentation delay from ~166 ms to ~55 ms (measured) without changing a pixel.
(function () {{
  const orig = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (type, attrs) {{
    if (type === '2d') attrs = Object.assign({{}}, attrs || {{}}, {{ desynchronized: true }});
    return orig.call(this, type, attrs);
  }};
}})();
</script>
<script src="https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js"
        integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"
        crossorigin="anonymous"
        onerror="var s=document.createElement('script');s.src='vis-network.min.js';document.head.appendChild(s);"></script>
{_html_styles()}
<script id="graphify-theme-init">
// Apply the saved theme before first paint (#3894). No saved choice keeps the
// historical dark look; "system" follows prefers-color-scheme.
(function () {{
  var pref = null;
  try {{ pref = localStorage.getItem('graphify-theme'); }} catch (e) {{}}
  var t = pref === 'light' ? 'light'
    : pref === 'system' && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light'
    : 'dark';
  document.documentElement.setAttribute('data-theme', t);
}})();
</script>
</head>
<body>
<div id="graph"></div>
<div id="sidebar">
  <div id="theme-wrap" role="group" aria-label="Theme">
    <button type="button" data-theme-choice="light">Light</button>
    <button type="button" data-theme-choice="dark">Dark</button>
    <button type="button" data-theme-choice="system">System</button>
  </div>
  <div id="search-wrap">
    <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="info-panel">
    <h3>Node Info</h3>
    <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
  </div>
  <div id="legend-wrap">
    <h3>Communities</h3>
    <div id="legend-controls">
      <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">All</label>
      <input id="family-filter" type="search" placeholder="Filter families" autocomplete="off" spellcheck="false">
    </div>
    <div id="colour-strip"></div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
{_html_script(nodes_json, edges_json, legend_json, defer_arrows=G.number_of_edges() > ARROW_DEFER_EDGE_THRESHOLD, lean_gestures=G.number_of_nodes() > LEAN_GESTURE_NODE_THRESHOLD, baked=_baked_all, hover_enabled=True, community_colour_json=json.dumps(community_colour))}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    write_text_atomic(output_path, html)
    return True
