"""Large-graph Canvas renderer for ``graph.html``.

The vis-network renderer is excellent for the common case, but it keeps the
whole graph in a browser-side physics simulation and a DOM/SVG layer.  A
20k-node graph makes that path unusable: the first paint blocks while the
force layout runs, and every interaction re-renders far more than the
viewport needs.

This module is used only when a graph is both above the normal viz limit and
explicitly allowed to render at node level (``--node-limit`` / env override).
It emits a single self-contained HTML file that:

* embeds a compact binary payload (base64) instead of a multi-megabyte JS
  object graph, so ``file://`` keeps working without sidecar fetches;
* computes a deterministic community-packed layout in Python, so the browser
  never runs a force simulation;
* renders on Canvas 2D with viewport culling, community batching, sparse
  edges at low zoom and labels only for the most useful nodes;
* uses a spatial grid for hover/click hit-testing and a small CSR-like
  adjacency list for the inspector.

The public entry point is :func:`to_large_html`, called from
``graphify.exporters.html.to_html``.  Small graphs keep the existing
vis-network output byte-for-byte.
"""
from __future__ import annotations

import array
import base64
import html as _html
import json
import math
import struct
import sys
from collections import defaultdict
from typing import Any

import networkx as nx

from graphify.analyze import _node_community_map
from graphify.exporters.base import COMMUNITY_COLORS
from graphify.paths import write_text_atomic
from graphify.security import sanitize_label

_CONFIDENCE_CODES = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}
_LEARNING_NONE = 0
_LEARNING_PREFERRED = 1
_LEARNING_CONTESTED = 2
_LEARNING_OTHER = 3
_LEARNING_STALE_BIT = 4

# Layout constants (world units).  The camera fits them to the viewport, so
# these only control relative spacing / cluster density.
_NODE_SPACING = 10.0
_COMMUNITY_PAD = 2.0 * _NODE_SPACING
_ROW_WIDTH_FACTOR = 1.15


def _pack(typecode: str, values: list[Any]) -> bytes:
    """Pack a typed array as little-endian bytes on every host."""
    arr = array.array(typecode, values)
    if sys.byteorder == "big":
        arr.byteswap()
    return arr.tobytes()


def _large_layout(
    G: nx.Graph,
    node_community: dict[Any, Any],
) -> dict[Any, tuple[float, float]]:
    """Deterministic community-packed layout, O(nodes + communities).

    Communities are sorted by size and shelf-packed as padded squares.  Nodes
    inside a community use a golden-angle spiral, which gives an even,
    non-overlapping cluster without a force simulation.  Cross-community edges
    therefore become chords between clusters, while each cluster stays
    readable at low zoom.
    """
    members_by_cid: dict[Any, list[Any]] = defaultdict(list)
    for node_id in G.nodes():
        members_by_cid[node_community.get(node_id, 0)].append(node_id)

    order = sorted(
        members_by_cid.items(),
        key=lambda item: (-len(item[1]), str(item[0])),
    )
    boxes: list[tuple[Any, list[Any], float]] = []
    for cid, members in order:
        n = max(1, len(members))
        side = 2.0 * _NODE_SPACING * math.sqrt(n) + _COMMUNITY_PAD
        boxes.append((cid, members, side))

    total_area = sum(side * side for _, _, side in boxes)
    row_width = max(40.0 * _NODE_SPACING, math.sqrt(total_area) * _ROW_WIDTH_FACTOR)

    centers: dict[Any, tuple[float, float]] = {}
    x = y = 0.0
    row_h = 0.0
    for cid, _members, side in boxes:
        if x > 0.0 and x + side > row_width:
            x = 0.0
            y += row_h + _COMMUNITY_PAD
            row_h = 0.0
        centers[cid] = (x + side / 2.0, y + side / 2.0)
        x += side + _COMMUNITY_PAD
        row_h = max(row_h, side)

    positions: dict[Any, tuple[float, float]] = {}
    for cid, members, _side in boxes:
        cx, cy = centers[cid]
        n = len(members)
        for i, node_id in enumerate(members):
            if n == 1:
                positions[node_id] = (cx, cy)
                continue
            radius = _NODE_SPACING * 0.72 * math.sqrt(i + 0.5)
            angle = i * 2.399963229728653  # golden angle
            positions[node_id] = (
                cx + radius * math.cos(angle),
                cy + radius * math.sin(angle),
            )
    return positions


def _learning_code(entry: dict[str, Any] | None) -> int:
    if not entry:
        return _LEARNING_NONE
    status = str(entry.get("status", "")).lower()
    if status == "preferred":
        code = _LEARNING_PREFERRED
    elif status == "contested":
        code = _LEARNING_CONTESTED
    elif status:
        code = _LEARNING_OTHER
    else:
        code = _LEARNING_NONE
    if entry.get("stale"):
        code |= _LEARNING_STALE_BIT
    return code


def _build_large_assets(
    G: nx.Graph,
    communities: dict[Any, list[Any]],
    community_labels: dict[Any, str] | None = None,
    member_counts: dict[Any, int] | None = None,
    learning_overlay: dict | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """Return ``(meta_json, payload_base64, meta)`` for the Canvas renderer."""
    node_community = _node_community_map(communities)
    nodes = list(G.nodes())
    node_index = {node_id: i for i, node_id in enumerate(nodes)}
    positions = _large_layout(G, node_community)

    members_by_cid: dict[Any, list[Any]] = defaultdict(list)
    for node_id in nodes:
        members_by_cid[node_community.get(node_id, 0)].append(node_id)

    # Binary community IDs must be contiguous uint32 values.  Keep the original
    # ids only for label lookup while building the legend.
    original_cids = sorted(
        set(members_by_cid) | set((community_labels or {}).keys()),
        key=lambda cid: str(cid),
    )
    cid_to_u32 = {cid: i for i, cid in enumerate(original_cids)}

    labels: list[str] = []
    pos_values: list[float] = []
    comm_values: list[int] = []
    degree_values: list[int] = []
    source_values: list[int] = []
    file_type_values: list[int] = []
    learning_values: list[int] = []
    label_offsets: list[int] = [0]
    label_blob = bytearray()

    sources: list[str] = [""]
    source_ids: dict[str, int] = {"": 0}
    file_types: list[str] = [""]
    file_type_ids: dict[str, int] = {"": 0}
    relations: list[str] = [""]
    relation_ids: dict[str, int] = {"": 0}

    degree = dict(G.degree())
    for node_id in nodes:
        data = G.nodes[node_id]
        label = sanitize_label(str(data.get("label", node_id))) or str(node_id)
        labels.append(label)
        encoded = label.encode("utf-8")
        label_blob.extend(encoded)
        label_offsets.append(len(label_blob))

        x, y = positions.get(node_id, (0.0, 0.0))
        pos_values.extend((float(x), float(y)))
        comm_values.append(cid_to_u32.get(node_community.get(node_id, 0), 0))
        degree_values.append(int(degree.get(node_id, 0)))

        source = sanitize_label(str(data.get("source_file") or ""))
        if source not in source_ids:
            source_ids[source] = len(sources)
            sources.append(source)
        source_values.append(source_ids[source])

        file_type = sanitize_label(str(data.get("file_type") or ""))
        if file_type not in file_type_ids:
            file_type_ids[file_type] = len(file_types)
            file_types.append(file_type)
        file_type_values.append(file_type_ids[file_type])

        entry = learning_overlay.get(str(node_id)) if learning_overlay else None
        learning_values.append(_learning_code(entry))

    edge_src: list[int] = []
    edge_tgt: list[int] = []
    edge_relation: list[int] = []
    edge_confidence: list[int] = []
    for u, v, data in G.edges(data=True):
        true_src = data.get("_src", u)
        true_tgt = data.get("_tgt", v)
        iu = node_index.get(true_src, node_index.get(u))
        iv = node_index.get(true_tgt, node_index.get(v))
        if iu is None or iv is None:
            continue
        edge_src.append(iu)
        edge_tgt.append(iv)
        relation = sanitize_label(str(data.get("relation") or ""))
        if relation not in relation_ids:
            relation_ids[relation] = len(relations)
            relations.append(relation)
        edge_relation.append(relation_ids[relation])
        confidence = str(data.get("confidence", "EXTRACTED")).upper()
        edge_confidence.append(_CONFIDENCE_CODES.get(confidence, 2))

    n = len(nodes)
    m = len(edge_src)

    # Hyperedges are cheap to include when the semantic pass produced only a
    # handful.  Omit them for pathological counts; the stats line records it.
    hyperedges: list[dict[str, Any]] = []
    hyperedges_omitted = False
    total_members = 0
    raw_hyperedges = getattr(G, "graph", {}).get("hyperedges", []) or []
    for he in raw_hyperedges:
        members: list[int] = []
        seen: set[int] = set()
        for member in (he.get("nodes") or []):
            idx = node_index.get(member)
            if idx is not None and idx not in seen:
                seen.add(idx)
                members.append(idx)
        if len(members) < 2:
            continue
        label = sanitize_label(
            str(he.get("label") or he.get("relation") or "")
        ).replace("_", " ")
        hyperedges.append({"label": label, "nodes": members})
        total_members += len(members)
        if len(hyperedges) > 200 or total_members > 5000:
            hyperedges = []
            hyperedges_omitted = True
            break

    legend: list[dict[str, Any]] = []
    for cid in original_cids:
        u32 = cid_to_u32[cid]
        count = (
            member_counts.get(cid, len(members_by_cid.get(cid, [])))
            if member_counts
            else len(members_by_cid.get(cid, []))
        )
        label = sanitize_label(
            str((community_labels or {}).get(cid, f"Community {cid}"))
        )
        legend.append(
            {
                "cid": u32,
                "color": COMMUNITY_COLORS[u32 % len(COMMUNITY_COLORS)],
                "label": label,
                "count": int(count),
            }
        )
    legend.sort(key=lambda item: (-item["count"], item["cid"]))

    buf = bytearray(b"GFY1")
    buf.extend(struct.pack("<II", n, m))
    sections: dict[str, int] = {}

    def add_section(name: str, data: bytes, align: int = 4) -> None:
        if align > 1:
            while len(buf) % align:
                buf.append(0)
        sections[name] = len(buf)
        buf.extend(data)

    add_section("positions", _pack("f", pos_values))
    add_section("community", _pack("I", comm_values))
    add_section("degree", _pack("I", degree_values))
    add_section("source", _pack("I", source_values))
    add_section("file_type", _pack("H", file_type_values), align=2)
    add_section("learning", _pack("B", learning_values), align=1)
    add_section("label_offsets", _pack("I", label_offsets))
    add_section("label_blob", bytes(label_blob), align=1)
    add_section("edge_src", _pack("I", edge_src))
    add_section("edge_tgt", _pack("I", edge_tgt))
    add_section("edge_relation", _pack("H", edge_relation), align=2)
    add_section("edge_confidence", _pack("B", edge_confidence), align=1)

    meta: dict[str, Any] = {
        "version": 1,
        "renderer": "canvas-large",
        "node_count": n,
        "edge_count": m,
        "community_count": len(legend),
        "sections": sections,
        "label_blob_len": len(label_blob),
        "sources": sources,
        "file_types": file_types,
        "relations": relations,
        "legend": legend,
        "hyperedges": hyperedges,
        "hyperedges_omitted": hyperedges_omitted,
    }
    meta_json = json.dumps(
        meta, ensure_ascii=False, separators=(",", ":")
    ).replace("<", "\\u003c")
    payload_b64 = base64.b64encode(bytes(buf)).decode("ascii")
    return meta_json, payload_b64, meta


_LARGE_EXTRA_STYLES = """
  #graph { position: relative; overflow: hidden; background: var(--bg); }
  #graph-canvas, #overlay-canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  #overlay-canvas { pointer-events: none; }
  #graph canvas { touch-action: none; cursor: grab; }
  #graph canvas:active { cursor: grabbing; }
  #graph-toolbar { position: absolute; top: 12px; left: 12px; z-index: 6; display: flex; gap: 6px; }
  #graph-toolbar button {
    background: var(--panel); color: var(--text-2); border: 1px solid var(--input-border);
    border-radius: 5px; padding: 5px 9px; font-size: 12px; cursor: pointer;
  }
  #graph-toolbar button:hover { color: var(--text); }
  #graph-toolbar button[aria-pressed="true"] { background: #4E79A7; border-color: #4E79A7; color: #fff; }
  #loading {
    position: absolute; inset: 0; z-index: 9; display: flex; align-items: center; justify-content: center;
    background: var(--bg); color: var(--text-2); font-size: 13px; letter-spacing: 0.03em;
  }
  #loading.hidden { display: none; }
  #render-note { color: var(--muted); font-size: 10px; }
"""


_LARGE_SCRIPT = r"""
(async function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;
  const startedAt = performance.now();
  const canvas = $('graph-canvas');
  const overlay = $('overlay-canvas');
  const loading = $('loading');
  if (!canvas || !overlay) return;
  const ctx = canvas.getContext && canvas.getContext('2d');
  const octx = overlay.getContext && overlay.getContext('2d');
  if (!ctx || !octx) {
    if (loading) loading.textContent = 'Canvas 2D is not supported in this browser.';
    return;
  }

  function fail(err) {
    console.error(err);
    if (loading) {
      loading.classList.remove('hidden');
      loading.textContent = 'Could not load the graph: ' + (err && err.message ? err.message : err);
    }
  }

  function decodeBase64(text) {
    const bin = atob(text);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return bytes.buffer;
  }

  // Let the loading overlay paint before the synchronous base64 decode.
  // The timeout is a fallback for background tabs / headless captures where
  // requestAnimationFrame can be throttled; it also keeps the decoder from
  // hanging forever when a frame callback never arrives.
  await new Promise((resolve) => {
    let done = false;
    const finish = () => { if (!done) { done = true; resolve(); } };
    requestAnimationFrame(() => requestAnimationFrame(finish));
    setTimeout(finish, 50);
  });

  if (loading) loading.textContent = 'Decoding graph payload…';

  const meta = JSON.parse($('graphify-meta').textContent);
  const buffer = decodeBase64($('graphify-payload').textContent.trim());
  const head = new DataView(buffer);
  const magic = new TextDecoder().decode(new Uint8Array(buffer, 0, 4));
  if (magic !== 'GFY1') throw new Error('bad payload magic');
  const n = head.getUint32(4, true);
  const m = head.getUint32(8, true);
  if (n !== meta.node_count || m !== meta.edge_count) throw new Error('payload count mismatch');

  const S = meta.sections;
  const pos = new Float32Array(buffer, S.positions, n * 2);
  const community = new Uint32Array(buffer, S.community, n);
  const degree = new Uint32Array(buffer, S.degree, n);
  const sourceIds = new Uint32Array(buffer, S.source, n);
  const fileTypeIds = new Uint16Array(buffer, S.file_type, n);
  const learning = new Uint8Array(buffer, S.learning, n);
  const labelOffsets = new Uint32Array(buffer, S.label_offsets, n + 1);
  const labelBytes = new Uint8Array(buffer, S.label_blob, meta.label_blob_len);
  const edgeSrc = new Uint32Array(buffer, S.edge_src, m);
  const edgeTgt = new Uint32Array(buffer, S.edge_tgt, m);
  const edgeRelation = new Uint16Array(buffer, S.edge_relation, m);
  const edgeConfidence = new Uint8Array(buffer, S.edge_confidence, m);

  const decoder = new TextDecoder();
  const labels = new Array(n);
  const lowerLabels = new Array(n);
  for (let i = 0; i < n; i++) {
    const label = decoder.decode(labelBytes.subarray(labelOffsets[i], labelOffsets[i + 1]));
    labels[i] = label;
    lowerLabels[i] = label.toLowerCase();
  }
  if (loading) loading.textContent = 'Building spatial index…';

  const sources = meta.sources || [''];
  const fileTypes = meta.file_types || [''];
  const relations = meta.relations || [''];
  const legend = meta.legend || [];
  const colorByCid = new Map();
  const nameByCid = new Map();
  for (const item of legend) {
    colorByCid.set(item.cid, item.color);
    nameByCid.set(item.cid, item.label);
  }

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  let maxDeg = 1;
  for (let i = 0; i < n; i++) {
    const x = pos[i * 2], y = pos[i * 2 + 1];
    if (x < minX) minX = x;
    if (x > maxX) maxX = x;
    if (y < minY) minY = y;
    if (y > maxY) maxY = y;
    if (degree[i] > maxDeg) maxDeg = degree[i];
  }
  if (!Number.isFinite(minX)) { minX = minY = 0; maxX = maxY = 1; }

  const membersByCommunity = new Map();
  for (let i = 0; i < n; i++) {
    const cid = community[i];
    let members = membersByCommunity.get(cid);
    if (!members) { members = []; membersByCommunity.set(cid, members); }
    members.push(i);
  }

  // Community centres, used for the low-zoom labels.
  const centerX = new Map();
  const centerY = new Map();
  const centerN = new Map();
  for (let i = 0; i < n; i++) {
    const cid = community[i];
    centerX.set(cid, (centerX.get(cid) || 0) + pos[i * 2]);
    centerY.set(cid, (centerY.get(cid) || 0) + pos[i * 2 + 1]);
    centerN.set(cid, (centerN.get(cid) || 0) + 1);
  }
  for (const cid of centerX.keys()) {
    centerX.set(cid, centerX.get(cid) / centerN.get(cid));
    centerY.set(cid, centerY.get(cid) / centerN.get(cid));
  }

  // Adjacency list for the inspector.  Store edge indices so each neighbor
  // can be shown with its relation (and direction) without a second lookup.
  const adj = new Array(n);
  for (let i = 0; i < n; i++) adj[i] = [];
  for (let e = 0; e < m; e++) {
    const a = edgeSrc[e], b = edgeTgt[e];
    adj[a].push(e);
    if (b !== a) adj[b].push(e);
  }

  // Spatial grid for hover/click.  Cell size is in world units; at fit the
  // query is 3x3 cells, at deep zoom 1 cell.
  const GRID = 48;
  const grid = new Map();
  const cellKey = (x, y) => x + ',' + y;
  for (let i = 0; i < n; i++) {
    const gx = Math.floor(pos[i * 2] / GRID);
    const gy = Math.floor(pos[i * 2 + 1] / GRID);
    const key = cellKey(gx, gy);
    let bucket = grid.get(key);
    if (!bucket) { bucket = []; grid.set(key, bucket); }
    bucket.push(i);
  }

  const topNodes = Array.from({ length: n }, (_, i) => i)
    .sort((a, b) => (degree[b] - degree[a]) || (a - b));

  const camera = { x: (minX + maxX) / 2, y: (minY + maxY) / 2, scale: 1 };
  let dpr = 1;
  let fitted = false;
  let hovered = -1;
  let selected = -1;
  let showEdges = true;
  let showLabels = true;
  const hiddenCommunities = new Set();

  const TAU = Math.PI * 2;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function screenX(x) {
    return (x - camera.x) * camera.scale + canvas.clientWidth / 2;
  }
  function screenY(y) {
    return (y - camera.y) * camera.scale + canvas.clientHeight / 2;
  }
  function worldX(sx) {
    return (sx - canvas.clientWidth / 2) / camera.scale + camera.x;
  }
  function worldY(sy) {
    return (sy - canvas.clientHeight / 2) / camera.scale + camera.y;
  }

  function theme() {
    const light = root.getAttribute('data-theme') === 'light';
    return light
      ? {
          bg: '#ffffff',
          label: '#222222',
          edgeStrong: 'rgba(70, 80, 100, 0.42)',
          edgeWeak: 'rgba(70, 80, 100, 0.16)',
          ring: '#111111',
        }
      : {
          bg: '#0f0f1a',
          label: '#e0e0e0',
          edgeStrong: 'rgba(200, 210, 240, 0.42)',
          edgeWeak: 'rgba(190, 200, 230, 0.16)',
          ring: '#ffffff',
        };
  }

  function nodeRadius(i) {
    const z = clamp(camera.scale, 0.25, 3.0);
    const base = 1.2 + 3.8 * Math.sqrt(degree[i] / maxDeg);
    return clamp(base * z, 1.3, 9.0);
  }

  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) { setTimeout(resize, 50); return; }
    dpr = window.devicePixelRatio || 1;
    for (const c of [canvas, overlay]) {
      c.width = Math.max(1, Math.round(w * dpr));
      c.height = Math.max(1, Math.round(h * dpr));
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    octx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!fitted) fit(); else requestDraw();
  }

  function fit() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (!w || !h) return;
    const pad = 64;
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    camera.scale = clamp(Math.min((w - pad * 2) / spanX, (h - pad * 2) / spanY), 0.002, 8);
    camera.x = (minX + maxX) / 2;
    camera.y = (minY + maxY) / 2;
    fitted = true;
    requestDraw();
  }

  let rafPending = false;
  function requestDraw() {
    if (rafPending) return;
    rafPending = true;
    let done = false;
    const run = () => {
      if (done) return;
      done = true;
      rafPending = false;
      draw();
    };
    // rAF keeps interaction frames aligned; the timeout is the headless /
    // background-tab fallback so the first paint always lands.
    requestAnimationFrame(run);
    setTimeout(run, 30);
  }

  function drawEdges(t) {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const margin = 48;
    const scale = camera.scale;
    const minWorldX = worldX(-margin);
    const maxWorldX = worldX(w + margin);
    const minWorldY = worldY(-margin);
    const maxWorldY = worldY(h + margin);
    // Low zoom: only cross-community edges.  At 25k nodes this is the
    // difference between ~4k and ~50k line segments per frame.  Requiring a
    // little more zoom before drawing intra-community edges keeps the overview
    // readable instead of turning it into a white mesh.
    const allEdges = scale >= 0.75 || membersByCommunity.size <= 2;
    // Overview: sample the cross-community edges.  Once the user zooms in
    // past the threshold, every edge in the viewport is drawn.
    const sample = allEdges ? 1 : Math.max(1, Math.round(m / 12000));

    for (let pass = 0; pass < 2; pass++) {
      ctx.beginPath();
      let drawn = 0;
      for (let e = 0; e < m; e++) {
        if (sample > 1 && (e % sample) !== 0) continue;
        const conf = edgeConfidence[e];
        const extracted = conf === 0;
        if ((pass === 0) !== extracted) continue;
        const a = edgeSrc[e], b = edgeTgt[e];
        if (hiddenCommunities.size &&
            (hiddenCommunities.has(community[a]) || hiddenCommunities.has(community[b]))) continue;
        if (!allEdges && community[a] === community[b]) continue;
        const ax = pos[a * 2], ay = pos[a * 2 + 1];
        const bx = pos[b * 2], by = pos[b * 2 + 1];
        if ((ax < minWorldX && bx < minWorldX) || (ax > maxWorldX && bx > maxWorldX) ||
            (ay < minWorldY && by < minWorldY) || (ay > maxWorldY && by > maxWorldY)) continue;
        ctx.moveTo(screenX(ax), screenY(ay));
        ctx.lineTo(screenX(bx), screenY(by));
        drawn++;
      }
      ctx.strokeStyle = pass === 0 ? t.edgeStrong : t.edgeWeak;
      ctx.globalAlpha = scale < 0.75 ? 0.6 : 1;
      ctx.lineWidth = pass === 0
        ? clamp(scale * 0.45, 0.45, 1.2)
        : clamp(scale * 0.3, 0.35, 0.9);
      if (drawn) ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  function drawNodes(t) {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const minWorldX = worldX(-20);
    const maxWorldX = worldX(w + 20);
    const minWorldY = worldY(-20);
    const maxWorldY = worldY(h + 20);
    const z = clamp(camera.scale, 0.25, 3);

    for (const [cid, members] of membersByCommunity) {
      if (hiddenCommunities.has(cid)) continue;
      ctx.fillStyle = colorByCid.get(cid) || '#888888';
      ctx.beginPath();
      for (const i of members) {
        const x = pos[i * 2], y = pos[i * 2 + 1];
        if (x < minWorldX || x > maxWorldX || y < minWorldY || y > maxWorldY) continue;
        const sx = screenX(x), sy = screenY(y);
        const r = nodeRadius(i);
        if (r <= 1.7) {
          ctx.rect(sx - r, sy - r, r * 2, r * 2);
        } else {
          ctx.moveTo(sx + r, sy);
          ctx.arc(sx, sy, r, 0, TAU);
        }
      }
      ctx.fill();
    }

    // Learning rings are sparse (only annotated nodes), so a second pass is
    // cheaper than carrying the state into the batched fill above.
    if (z >= 0.3) {
      for (let pass = 0; pass < 2; pass++) {
        ctx.beginPath();
        let found = false;
        for (let i = 0; i < n; i++) {
          const code = learning[i];
          const status = code & 3;
          if (status === 0 || (pass === 0 ? status !== 1 : status !== 2)) continue;
          if (hiddenCommunities.has(community[i])) continue;
          const x = pos[i * 2], y = pos[i * 2 + 1];
          if (x < minWorldX || x > maxWorldX || y < minWorldY || y > maxWorldY) continue;
          const sx = screenX(x), sy = screenY(y);
          const r = nodeRadius(i) + 2;
          ctx.moveTo(sx + r, sy);
          ctx.arc(sx, sy, r, 0, TAU);
          found = true;
        }
        if (found) {
          ctx.strokeStyle = pass === 0 ? '#22c55e' : '#f59e0b';
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      }
    }
  }

  function drawLabels(t) {
    // At the overview scale, cluster labels carry the structure.  Node labels
    // appear once the user zooms in, where they no longer overlap into noise.
    if (camera.scale < 0.55) return;
    const maxLabels = camera.scale < 1.2 ? 180 : 500;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const minWorldX = worldX(0);
    const maxWorldX = worldX(w);
    const minWorldY = worldY(0);
    const maxWorldY = worldY(h);
    ctx.font = '11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = t.label;
    let drawn = 0;
    for (const i of topNodes) {
      if (drawn >= maxLabels) break;
      if (hiddenCommunities.has(community[i])) continue;
      const x = pos[i * 2], y = pos[i * 2 + 1];
      if (x < minWorldX || x > maxWorldX || y < minWorldY || y > maxWorldY) continue;
      const sx = screenX(x), sy = screenY(y);
      ctx.fillText(labels[i], sx, sy - nodeRadius(i) - 2);
      drawn++;
    }
  }

  function drawCommunityLabels(t) {
    const maxLabels = camera.scale < 0.55 ? 10 : camera.scale < 1.2 ? 30 : 80;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const minWorldX = worldX(0);
    const maxWorldX = worldX(w);
    const minWorldY = worldY(0);
    const maxWorldY = worldY(h);
    ctx.font = 'bold 11px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    let drawn = 0;
    const placed = [];
    for (const item of legend) {
      if (drawn >= maxLabels) break;
      if (hiddenCommunities.has(item.cid)) continue;
      const cx = centerX.get(item.cid);
      const cy = centerY.get(item.cid);
      if (cx === undefined || cy === undefined) continue;
      if (cx < minWorldX || cx > maxWorldX || cy < minWorldY || cy > maxWorldY) continue;
      const px = screenX(cx);
      const py = screenY(cy);
      const width = ctx.measureText(item.label).width + 8;
      const left = px - width / 2;
      const top = py - 8;
      const right = left + width;
      const bottom = top + 16;
      // Largest communities are first (legend is count-sorted); skip a label
      // that would overlap one already placed on screen instead of stacking a
      // row of unreadable pills.
      if (placed.some((r) => !(right < r.left || left > r.right || bottom < r.top || top > r.bottom))) continue;
      placed.push({ left, top, right, bottom });
      ctx.globalAlpha = 0.72;
      ctx.fillStyle = t.bg;
      ctx.fillRect(left, top, width, 16);
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = item.color;
      ctx.fillText(item.label, px, py);
      drawn++;
    }
    ctx.globalAlpha = 1;
  }

  function convexHull(points) {
    if (points.length < 3) return points.slice();
    const p = points.slice().sort((a, b) => (a.x - b.x) || (a.y - b.y));
    const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
    const build = (seq) => {
      const out = [];
      for (const q of seq) {
        while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], q) <= 0) out.pop();
        out.push(q);
      }
      out.pop();
      return out;
    };
    const hull = build(p).concat(build(p.slice().reverse()));
    return hull.length >= 3 ? hull : p;
  }

  function drawHyperedges() {
    if (!meta.hyperedges || !meta.hyperedges.length || camera.scale < 0.4) return;
    const limit = Math.min(meta.hyperedges.length, 100);
    for (let h = 0; h < limit; h++) {
      const he = meta.hyperedges[h];
      const points = [];
      for (const i of he.nodes) {
        if (hiddenCommunities.has(community[i])) continue;
        points.push({ x: pos[i * 2], y: pos[i * 2 + 1] });
      }
      if (points.length < 2) continue;
      const hull = convexHull(points);
      if (hull.length < 3) continue;
      const cx = points.reduce((s, p) => s + p.x, 0) / points.length;
      const cy = points.reduce((s, p) => s + p.y, 0) / points.length;
      ctx.beginPath();
      ctx.moveTo(screenX(hull[0].x), screenY(hull[0].y));
      for (let i = 1; i < hull.length; i++) ctx.lineTo(screenX(hull[i].x), screenY(hull[i].y));
      ctx.closePath();
      ctx.fillStyle = 'rgba(99, 102, 241, 0.10)';
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.45)';
      ctx.lineWidth = 1.5;
      ctx.fill();
      ctx.stroke();
      if (he.label) {
        ctx.fillStyle = '#6366f1';
        ctx.font = 'bold 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(he.label, screenX(cx), screenY(cy));
      }
    }
  }

  function draw() {
    const t = theme();
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = t.bg;
    ctx.fillRect(0, 0, w, h);
    if (showEdges) drawEdges(t);
    drawNodes(t);
    drawHyperedges();
    if (showLabels) {
      drawLabels(t);
      drawCommunityLabels(t);
    }
    drawOverlay();
    if (loading) loading.classList.add('hidden');
    root.dataset.graphifyReady = '1';
    root.dataset.graphifyLoadMs = String(Math.round(performance.now() - startedAt));
  }

  function drawOverlay() {
    const t = theme();
    const w = overlay.clientWidth;
    const h = overlay.clientHeight;
    octx.clearRect(0, 0, w, h);
    const ids = new Set();
    if (hovered >= 0) ids.add(hovered);
    if (selected >= 0) ids.add(selected);
    if (!ids.size) return;
    for (const i of ids) {
      if (hiddenCommunities.has(community[i])) continue;
      const sx = screenX(pos[i * 2]);
      const sy = screenY(pos[i * 2 + 1]);
      const r = nodeRadius(i) + (i === selected ? 4 : 3);
      octx.beginPath();
      octx.arc(sx, sy, r, 0, TAU);
      octx.strokeStyle = i === selected ? t.ring : (colorByCid.get(community[i]) || '#888');
      octx.lineWidth = i === selected ? 2.5 : 2;
      octx.stroke();
      if (i === hovered) {
        octx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        octx.textAlign = 'center';
        octx.textBaseline = 'bottom';
        octx.fillStyle = t.label;
        octx.fillText(labels[i], sx, sy - r - 4);
      }
    }
    // Mirror the vis-network edge tooltip: while a node is hovered or
    // selected, name the relationships of its edges on the map.
    const focus = selected >= 0 ? selected : hovered;
    if (focus >= 0 && !hiddenCommunities.has(community[focus])) {
      drawFocusedEdgeLabels(t, focus);
    }
  }

  function drawFocusedEdgeLabels(t, i) {
    // Only once the user has zoomed in enough for the text to be readable
    // without covering the whole cluster.
    if (camera.scale < 0.9) return;
    const incident = adj[i] || [];
    if (!incident.length) return;
    octx.font = '10px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    octx.textAlign = 'center';
    octx.textBaseline = 'middle';
    const placed = [];
    let drawn = 0;
    const ax = screenX(pos[i * 2]);
    const ay = screenY(pos[i * 2 + 1]);
    for (const e of incident) {
      if (drawn >= 40) break;
      const rel = relations[edgeRelation[e]] || '';
      if (!rel) continue;
      const nb = edgeSrc[e] === i ? edgeTgt[e] : edgeSrc[e];
      if (hiddenCommunities.has(community[nb])) continue;
      const bx = screenX(pos[nb * 2]);
      const by = screenY(pos[nb * 2 + 1]);
      if (Math.hypot(bx - ax, by - ay) < 34) continue;
      const mx = (ax + bx) / 2;
      const my = (ay + by) / 2;
      if (mx < 0 || mx > overlay.clientWidth || my < 0 || my > overlay.clientHeight) continue;
      const width = octx.measureText(rel).width + 6;
      const rect = { left: mx - width / 2, top: my - 7, right: mx + width / 2, bottom: my + 7 };
      if (placed.some((r) => !(rect.right < r.left || rect.left > r.right || rect.bottom < r.top || rect.top > r.bottom))) continue;
      placed.push(rect);
      octx.globalAlpha = 0.78;
      octx.fillStyle = t.bg;
      octx.fillRect(rect.left, rect.top, width, 14);
      octx.globalAlpha = 0.95;
      octx.fillStyle = t.label;
      octx.fillText(rel, mx, my);
      drawn++;
    }
    octx.globalAlpha = 1;
  }

  function pick(mx, my) {
    const wx = worldX(mx), wy = worldY(my);
    const gx = Math.floor(wx / GRID), gy = Math.floor(wy / GRID);
    const reach = Math.min(8, Math.ceil(Math.max(10 / camera.scale, 8) / GRID));
    let best = -1;
    let bestD = Infinity;
    for (let dx = -reach; dx <= reach; dx++) {
      for (let dy = -reach; dy <= reach; dy++) {
        const bucket = grid.get(cellKey(gx + dx, gy + dy));
        if (!bucket) continue;
        for (const i of bucket) {
          if (hiddenCommunities.has(community[i])) continue;
          const ddx = pos[i * 2] - wx;
          const ddy = pos[i * 2 + 1] - wy;
          const d2 = ddx * ddx + ddy * ddy;
          if (d2 < bestD) { bestD = d2; best = i; }
        }
      }
    }
    if (best < 0) return -1;
    const hitWorld = Math.max(8, nodeRadius(best) + 4) / camera.scale;
    return bestD <= hitWorld * hitWorld ? best : -1;
  }

  function showInfo(i) {
    const box = $('info-content');
    if (!box) return;
    box.replaceChildren();
    const add = (name, value) => {
      const row = document.createElement('div');
      row.className = 'field';
      const b = document.createElement('b');
      b.textContent = name;
      row.append(b, document.createTextNode(' ' + String(value)));
      box.append(row);
    };
    add('Node:', labels[i]);
    add('Type:', fileTypes[fileTypeIds[i]] || 'unknown');
    add('Community:', nameByCid.get(community[i]) || 'Community ' + community[i]);
    const source = sources[sourceIds[i]] || '-';
    add('Source:', source);
    add('Degree:', degree[i]);
    const learn = learning[i] & 3;
    if (learn) {
      const status = learn === 1 ? 'preferred' : learn === 2 ? 'contested' : 'annotated';
      add('Learning:', status + ((learning[i] & 4) ? ' (stale)' : ''));
    }
    const incident = adj[i] || [];
    if (incident.length) {
      const heading = document.createElement('div');
      heading.className = 'field';
      heading.style.cssText = 'margin-top:8px;color:var(--text-2);font-size:11px';
      heading.textContent = 'Neighbors (' + incident.length + ')';
      box.append(heading);
      const list = document.createElement('div');
      list.id = 'neighbors-list';
      const seen = new Set();
      for (const e of incident) {
        const nb = edgeSrc[e] === i ? edgeTgt[e] : edgeSrc[e];
        const relation = relations[edgeRelation[e]] || '';
        // Keep parallel edges that carry different relations: dedupe per
        // neighbor+relation pair, not per neighbor.
        const key = nb + '\u0000' + relation;
        if (seen.has(key)) continue;
        seen.add(key);
        if (seen.size > 80) break;
        const link = document.createElement('span');
        link.className = 'neighbor-link';
        link.style.borderLeftColor = colorByCid.get(community[nb]) || '#555';
        link.dataset.idx = String(nb);
        const arrow = relation ? (edgeSrc[e] === i ? '\u2192 ' : '\u2190 ') : '';
        link.textContent = relation
          ? labels[nb] + '  ' + arrow + relation
          : labels[nb];
        link.title = relation ? labels[nb] + ' \u2014 ' + relation : labels[nb];
        list.append(link);
      }
      box.append(list);
    }
  }

  function focusIndex(i) {
    if (i < 0 || i >= n) return;
    const x = pos[i * 2], y = pos[i * 2 + 1];
    camera.x = x;
    camera.y = y;
    camera.scale = Math.max(camera.scale, 1.2);
    selected = i;
    showInfo(i);
    requestDraw();
  }

  // Pointer / wheel interaction.
  let dragging = false;
  let dragMoved = false;
  let lastX = 0;
  let lastY = 0;
  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId);
    dragging = true;
    dragMoved = false;
    lastX = e.clientX;
    lastY = e.clientY;
  });
  canvas.addEventListener('pointermove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    if (dragging) {
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      if (Math.abs(dx) + Math.abs(dy) > 2) dragMoved = true;
      camera.x -= dx / camera.scale;
      camera.y -= dy / camera.scale;
      lastX = e.clientX;
      lastY = e.clientY;
      requestDraw();
      return;
    }
    const next = pick(mx, my);
    if (next !== hovered) {
      hovered = next;
      canvas.style.cursor = hovered >= 0 ? 'pointer' : 'grab';
      drawOverlay();
    }
  });
  canvas.addEventListener('pointerup', (e) => {
    dragging = false;
    if (dragMoved) return;
    const rect = canvas.getBoundingClientRect();
    const i = pick(e.clientX - rect.left, e.clientY - rect.top);
    if (i >= 0) {
      selected = i;
      showInfo(i);
      drawOverlay();
    }
  });
  canvas.addEventListener('pointerleave', () => {
    if (dragging) return;
    if (hovered !== -1) { hovered = -1; drawOverlay(); }
  });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const beforeX = worldX(mx), beforeY = worldY(my);
    const factor = Math.exp(-e.deltaY * 0.0015);
    camera.scale = clamp(camera.scale * factor, 0.002, 24);
    const afterX = worldX(mx), afterY = worldY(my);
    camera.x += beforeX - afterX;
    camera.y += beforeY - afterY;
    requestDraw();
  }, { passive: false });
  canvas.addEventListener('dblclick', () => fit());
  window.addEventListener('resize', resize);

  // Search.
  const searchInput = $('search');
  const searchResults = $('search-results');
  let searchTimer = null;
  if (searchInput && searchResults) {
    searchInput.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => {
        const q = searchInput.value.toLowerCase().trim();
        searchResults.replaceChildren();
        if (!q) { searchResults.style.display = 'none'; return; }
        const matches = [];
        for (let i = 0; i < n && matches.length < 20; i++) {
          if (lowerLabels[i].includes(q)) matches.push(i);
        }
        if (!matches.length) { searchResults.style.display = 'none'; return; }
        searchResults.style.display = 'block';
        for (const i of matches) {
          const el = document.createElement('div');
          el.className = 'search-item';
          el.textContent = labels[i];
          el.style.borderLeft = '3px solid ' + (colorByCid.get(community[i]) || '#555');
          el.style.paddingLeft = '8px';
          el.addEventListener('click', () => {
            focusIndex(i);
            searchResults.style.display = 'none';
            searchInput.value = '';
          });
          searchResults.append(el);
        }
      }, 80);
    });
    document.addEventListener('click', (e) => {
      if (!searchResults.contains(e.target) && e.target !== searchInput) {
        searchResults.style.display = 'none';
      }
    });
  }

  // Neighbor links.
  document.addEventListener('click', (e) => {
    const el = e.target.closest && e.target.closest('.neighbor-link');
    if (el && el.dataset.idx !== undefined) focusIndex(Number(el.dataset.idx));
  });

  // Legend.
  const legendEl = $('legend');
  const selectAllCb = $('select-all-cb');
  function updateSelectAllState() {
    if (!selectAllCb) return;
    const total = legend.length;
    const hidden = hiddenCommunities.size;
    selectAllCb.checked = hidden === 0;
    selectAllCb.indeterminate = hidden > 0 && hidden < total;
  }
  function toggleAllCommunities(hide) {
    document.querySelectorAll('.legend-item').forEach((item) => {
      hide ? item.classList.add('dimmed') : item.classList.remove('dimmed');
    });
    document.querySelectorAll('.legend-cb').forEach((cb) => { cb.checked = !hide; });
    for (const item of legend) {
      if (hide) hiddenCommunities.add(item.cid); else hiddenCommunities.delete(item.cid);
    }
    updateSelectAllState();
    requestDraw();
  }
  if (selectAllCb) {
    selectAllCb.addEventListener('change', () => toggleAllCommunities(!selectAllCb.checked));
  }
  if (legendEl) {
    for (const item of legend) {
      const row = document.createElement('div');
      row.className = 'legend-item';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.className = 'legend-cb';
      cb.checked = true;
      cb.addEventListener('change', (e) => {
        e.stopPropagation();
        if (cb.checked) {
          hiddenCommunities.delete(item.cid);
          row.classList.remove('dimmed');
        } else {
          hiddenCommunities.add(item.cid);
          row.classList.add('dimmed');
        }
        updateSelectAllState();
        requestDraw();
      });
      const dot = document.createElement('div');
      dot.className = 'legend-dot';
      dot.style.background = item.color;
      const label = document.createElement('span');
      label.className = 'legend-label';
      label.textContent = item.label;
      const count = document.createElement('span');
      count.className = 'legend-count';
      count.textContent = String(item.count);
      row.append(cb, dot, label, count);
      row.addEventListener('click', (e) => {
        if (e.target === cb) return;
        cb.checked = !cb.checked;
        cb.dispatchEvent(new Event('change'));
      });
      legendEl.append(row);
    }
  }
  updateSelectAllState();

  // Theme toggle, same storage key as the vis-network renderer.
  const THEME_KEY = 'graphify-theme';
  const themeMQ = window.matchMedia ? window.matchMedia('(prefers-color-scheme: light)') : null;
  function themePref() {
    let p = null;
    try { p = localStorage.getItem(THEME_KEY); } catch (e) {}
    return (p === 'light' || p === 'dark' || p === 'system') ? p : null;
  }
  function applyTheme(pref) {
    const t = pref === 'light' ? 'light' : (pref === 'system' && themeMQ && themeMQ.matches) ? 'light' : 'dark';
    root.setAttribute('data-theme', t);
    document.querySelectorAll('[data-theme-choice]').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.themeChoice === (pref || 'dark')));
    });
    requestDraw();
  }
  document.querySelectorAll('[data-theme-choice]').forEach((b) => {
    b.addEventListener('click', () => {
      const pref = b.dataset.themeChoice;
      try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}
      applyTheme(pref);
    });
  });
  if (themeMQ) {
    const onChange = () => { if (themePref() === 'system') applyTheme('system'); };
    if (themeMQ.addEventListener) themeMQ.addEventListener('change', onChange);
    else if (themeMQ.addListener) themeMQ.addListener(onChange);
  }
  applyTheme(themePref());

  // Toolbar.
  $('fit-btn').addEventListener('click', () => fit());
  const edgesBtn = $('edges-btn');
  edgesBtn.addEventListener('click', () => {
    showEdges = !showEdges;
    edgesBtn.setAttribute('aria-pressed', String(showEdges));
    requestDraw();
  });
  const labelsBtn = $('labels-btn');
  labelsBtn.addEventListener('click', () => {
    showLabels = !showLabels;
    labelsBtn.setAttribute('aria-pressed', String(showLabels));
    requestDraw();
  });

  // Initial paint.  resize() calls fit() on the first successful layout.
  resize();
})().catch((err) => {
  console.error(err);
  const loading = document.getElementById('loading');
  if (loading) {
    loading.classList.remove('hidden');
    loading.textContent = 'Could not load the graph: ' + (err && err.message ? err.message : err);
  }
});
"""


def to_large_html(
    G: nx.Graph,
    communities: dict[Any, list[Any]],
    output_path: str,
    community_labels: dict[Any, str] | None = None,
    member_counts: dict[Any, int] | None = None,
    learning_overlay: dict | None = None,
    title: str | None = None,
) -> bool:
    """Write the self-contained Canvas renderer for a large graph."""
    from graphify.exporters.html import _html_document_title, _html_styles

    if title is None:
        title = _html_document_title(str(output_path))
    meta_json, payload_b64, meta = _build_large_assets(
        G,
        communities,
        community_labels=community_labels,
        member_counts=member_counts,
        learning_overlay=learning_overlay,
    )
    n = meta["node_count"]
    m = meta["edge_count"]
    communities_n = meta["community_count"]
    title_html = _html.escape(sanitize_label(title))
    stats = (
        f"{n:,} nodes &middot; {m:,} edges &middot; {communities_n:,} communities"
        f'<br><span id="render-note">Canvas renderer &middot; binary payload'
        f'{" &middot; hyperedges omitted" if meta["hyperedges_omitted"] else ""}</span>'
    )

    html = f"""<!DOCTYPE html>
<html lang="en" data-graphify-renderer="canvas-large">
<head>
<meta charset="UTF-8">
<title>graphify - {title_html}</title>
{_html_styles()}
<style>{_LARGE_EXTRA_STYLES}</style>
<script id="graphify-theme-init">
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
<div id="graph">
  <canvas id="graph-canvas" aria-label="Graph canvas"></canvas>
  <canvas id="overlay-canvas" aria-hidden="true"></canvas>
  <div id="graph-toolbar">
    <button type="button" id="fit-btn">Fit</button>
    <button type="button" id="edges-btn" aria-pressed="true">Edges</button>
    <button type="button" id="labels-btn" aria-pressed="true">Labels</button>
  </div>
  <div id="loading">Decoding {n:,} nodes / {m:,} edges&hellip;</div>
</div>
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
      <label><input type="checkbox" id="select-all-cb" checked>Select All</label>
    </div>
    <div id="legend"></div>
  </div>
  <div id="stats">{stats}</div>
</div>
<script id="graphify-meta" type="application/json">{meta_json}</script>
<script id="graphify-payload" type="application/octet-stream">{payload_b64}</script>
<script>{_LARGE_SCRIPT}</script>
</body>
</html>"""

    write_text_atomic(output_path, html)
    return True
