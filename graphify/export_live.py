# write graph to HTML, JSON, SVG, GraphML, Obsidian vault, and Neo4j Cypher
from __future__ import annotations
import hashlib
import html as _html
import json
import math
import os
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label
from graphify.analyze import _node_community_map
from graphify.build import edge_data


# Artifacts worth preserving across rebuilds (non-regenerable without LLM or curation).
_BACKUP_ARTIFACTS = [
    "graph.json",
    "GRAPH_REPORT.md",
    ".graphify_labels.json",
    ".graphify_analysis.json",
    "manifest.json",
    ".graphify_semantic_marker",
    "cost.json",
]


def backup_if_protected(out_dir: Path) -> "Path | None":
    """Snapshot graph artifacts to a dated subfolder before an overwrite.

    Triggers when graph.json exists AND either:
    - .graphify_semantic_marker is present (graph cost real LLM tokens), or
    - .graphify_labels.json contains at least one non-default community label
      (graph has been curated by a human or skill).

    Returns the backup folder path, or None if no backup was taken.
    Never raises — backup failure prints a warning but never blocks the write.
    Set GRAPHIFY_NO_BACKUP=1 to disable.
    """
    if os.environ.get("GRAPHIFY_NO_BACKUP"):
        return None
    out = Path(out_dir)
    if not (out / "graph.json").exists():
        return None

    is_semantic = (out / ".graphify_semantic_marker").exists()
    is_curated = False
    labels_file = out / ".graphify_labels.json"
    if labels_file.exists():
        try:
            labels = json.loads(labels_file.read_text(encoding="utf-8"))
            is_curated = any(v != f"Community {k}" for k, v in labels.items())
        except Exception:
            pass

    if not is_semantic and not is_curated:
        return None

    reason = "+".join(filter(None, ["semantic" if is_semantic else "", "curated" if is_curated else ""]))
    today = date.today().isoformat()
    backup_dir = out / today
    graph_src = out / "graph.json"

    # Skip re-copying if today's backup already has identical graph.json content.
    # If content differs (graph changed since the last backup today), overwrite
    # the backup in place — one folder per day, always the latest pre-overwrite state.
    if backup_dir.exists() and (backup_dir / "graph.json").exists():
        src_hash = hashlib.sha256(graph_src.read_bytes()).hexdigest()
        bak_hash = hashlib.sha256((backup_dir / "graph.json").read_bytes()).hexdigest()
        if src_hash == bak_hash:
            return backup_dir  # identical content, nothing to do

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for name in _BACKUP_ARTIFACTS:
            src = out / name
            if src.exists():
                try:
                    shutil.copy2(src, backup_dir / name)
                    copied += 1
                except Exception:
                    pass
        if copied:
            print(f"[graphify] backed up {reason} graph ({copied} files) -> {backup_dir.name}/")
        return backup_dir
    except Exception as exc:
        import sys
        print(f"[graphify] warning: backup failed ({exc}) - continuing with overwrite", file=sys.stderr)
        return None

def _obsidian_tag(name: str) -> str:
    """Sanitize a community name for use as an Obsidian tag.

    Obsidian tags only allow alphanumerics, hyphens, underscores, and slashes.
    Spaces become underscores; everything else is stripped.
    """
    return re.sub(r"[^a-zA-Z0-9_\-/]", "", name.replace(" ", "_"))


def _strip_diacritics(text: str | None) -> str:
    import unicodedata
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _yaml_str(s: str) -> str:
    """Escape a value for safe embedding in a YAML double-quoted scalar (F-009).

    See `graphify.ingest._yaml_str` for the full rationale; duplicated here to
    avoid pulling the URL-fetching `ingest` module into export's dependency
    graph. Handles backslash, double-quote, all line breaks (\\n, \\r,
    U+2028, U+2029), tab, NUL, and other C0/DEL control characters that
    would otherwise let a hostile `source_file` / `community` / etc. break
    out of the YAML scalar and inject sibling keys.
    """
    if s is None:
        return ""
    out: list[str] = []
    for ch in str(s):
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\0":
            out.append("\\0")
        elif cp == 0x2028:
            out.append("\\L")
        elif cp == 0x2029:
            out.append("\\P")
        elif cp < 0x20 or cp == 0x7F:
            out.append(f"\\x{cp:02x}")
        else:
            out.append(ch)
    return "".join(out)


COMMUNITY_COLORS = [
    "#4E79A7", "#F28E2B", "#E15759", "#76B7B2", "#59A14F",
    "#EDC948", "#B07AA1", "#FF9DA7", "#9C755F", "#BAB0AC",
    "#6366f1", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
    "#06b6d4", "#d946ef", "#22c55e", "#eab308", "#64748b",
]

MAX_NODES_FOR_VIZ = 5_000


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
    --bg-primary: #07070d;
    --bg-secondary: #0c0c1a;
    --surface: rgba(255,255,255,0.04);
    --surface-hover: rgba(255,255,255,0.08);
    --surface-active: rgba(255,255,255,0.12);
    --border: rgba(255,255,255,0.06);
    --border-hover: rgba(255,255,255,0.12);
    --text-primary: rgba(255,255,255,0.92);
    --text-secondary: rgba(255,255,255,0.55);
    --text-tertiary: rgba(255,255,255,0.30);
    --accent: #6366f1;
    --accent-glow: rgba(99,102,241,0.3);
    --radius: 10px;
    --radius-sm: 6px;
    --radius-lg: 16px;
    --sidebar-w: 340px;
    --font: -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif;
    --font-mono: "SF Mono","Fira Code","Cascadia Code",monospace;
    --transition: 0.2s cubic-bezier(0.4,0,0.2,1);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { width: 100%; height: 100%; overflow: hidden; background: var(--bg-primary); color: var(--text-primary); font-family: var(--font); -webkit-font-smoothing: antialiased; }
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

  #app { display: flex; width: 100%; height: 100%; position: relative; }
  #graph-container { flex: 1; position: relative; overflow: hidden; }
  #graph-canvas { width: 100%; height: 100%; display: block; }

  #loading-screen {
    position: fixed; inset: 0; z-index: 9999;
    background: var(--bg-primary);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    transition: opacity 0.8s ease, visibility 0.8s ease;
  }
  #loading-screen.hidden { opacity: 0; visibility: hidden; pointer-events: none; }
  #loading-screen .logo { font-size: 28px; font-weight: 700; letter-spacing: -0.03em; background: linear-gradient(135deg,#6366f1,#a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 24px; }
  #loading-screen .steps { display: flex; flex-direction: column; gap: 8px; min-width: 240px; }
  #loading-screen .step { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--text-secondary); transition: var(--transition); }
  #loading-screen .step.active { color: var(--text-primary); }
  #loading-screen .step.done { color: #22c55e; }
  #loading-screen .step-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; transition: var(--transition); }
  #loading-screen .step.active .step-dot { box-shadow: 0 0 8px currentColor; }
  #loading-screen .progress-bar { width: 240px; height: 2px; background: var(--border); border-radius: 2px; margin-top: 20px; overflow: hidden; }
  #loading-screen .progress-fill { height: 100%; background: linear-gradient(90deg,#6366f1,#a855f7); border-radius: 2px; transition: width 0.5s ease; width: 0%; }

  #sidebar {
    width: var(--sidebar-w); height: 100%; background: var(--bg-secondary);
    border-left: 1px solid var(--border); display: flex; flex-direction: column;
    flex-shrink: 0; position: relative; transition: transform var(--transition), opacity var(--transition);
    z-index: 100;
  }
  #sidebar.collapsed { transform: translateX(100%); opacity: 0; width: 0; overflow: hidden; border: none; }
  #sidebar-header { padding: 16px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
  #sidebar-header h2 { font-size: 15px; font-weight: 600; letter-spacing: -0.02em; }
  #sidebar-close { background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; transition: var(--transition); }
  #sidebar-close:hover { background: var(--surface-hover); color: var(--text-primary); }

  #search-wrap { padding: 12px 18px; position: relative; flex-shrink: 0; }
  #search {
    width: 100%; background: var(--surface); border: 1px solid var(--border);
    color: var(--text-primary); padding: 8px 12px 8px 36px; border-radius: var(--radius);
    font-size: 13px; outline: none; transition: var(--transition); font-family: var(--font);
  }
  #search:focus { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-glow); }
  #search::placeholder { color: var(--text-tertiary); }
  #search-icon { position: absolute; left: 28px; top: 50%; transform: translateY(-50%); color: var(--text-tertiary); pointer-events: none; font-size: 14px; }
  #search-results {
    position: absolute; top: 100%; left: 18px; right: 18px; max-height: 280px;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    overflow-y: auto; display: none; z-index: 50; box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  }
  .search-item { padding: 8px 12px; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 8px; transition: var(--transition); }
  .search-item:hover { background: var(--surface-hover); }
  .search-item .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .search-item .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .search-item .badge { font-size: 10px; color: var(--text-tertiary); font-family: var(--font-mono); }

  #info-panel { padding: 14px 18px; border-bottom: 1px solid var(--border); min-height: 120px; flex-shrink: 0; }
  #info-panel h3 { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 10px; font-weight: 600; }
  #info-content { font-size: 13px; line-height: 1.6; }
  #info-content .empty { color: var(--text-tertiary); font-style: italic; font-size: 12px; }
  .info-row { display: flex; justify-content: space-between; align-items: center; padding: 3px 0; }
  .info-row .label { color: var(--text-secondary); font-size: 12px; }
  .info-row .value { color: var(--text-primary); font-size: 12px; font-weight: 500; }
  .info-title { font-size: 14px; font-weight: 600; margin-bottom: 6px; }
  .info-tag { display: inline-block; padding: 1px 8px; border-radius: 4px; font-size: 10px; font-weight: 500; background: var(--surface); color: var(--text-secondary); margin-right: 4px; margin-bottom: 4px; }
  .neighbor-link { display: flex; align-items: center; gap: 6px; padding: 4px 8px; margin: 2px 0; border-radius: var(--radius-sm); cursor: pointer; font-size: 12px; transition: var(--transition); }
  .neighbor-link:hover { background: var(--surface-hover); }
  .neighbor-link .ndot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
  #neighbors-list { max-height: 140px; overflow-y: auto; margin-top: 4px; }

  #legend-wrap { flex: 1; overflow-y: auto; padding: 14px 18px; }
  #legend-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  #legend-header h3 { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.1em; font-weight: 600; }
  #legend-controls { display: flex; align-items: center; gap: 6px; }
  #legend-controls label { display: flex; align-items: center; gap: 4px; cursor: pointer; font-size: 11px; color: var(--text-secondary); user-select: none; transition: var(--transition); }
  #legend-controls label:hover { color: var(--text-primary); }
  .legend-cb { appearance: none; -webkit-appearance: none; width: 14px; height: 14px; border: 1.5px solid var(--border); border-radius: 3px; background: var(--surface); cursor: pointer; position: relative; flex-shrink: 0; transition: var(--transition); }
  .legend-cb:checked { background: var(--accent); border-color: var(--accent); }
  .legend-cb:checked::after { content: ''; position: absolute; left: 3.5px; top: 1px; width: 4px; height: 7px; border: solid #fff; border-width: 0 2px 2px 0; transform: rotate(45deg); }
  .legend-item { display: flex; align-items: center; gap: 8px; padding: 5px 6px; cursor: pointer; border-radius: var(--radius-sm); font-size: 12px; transition: var(--transition); }
  .legend-item:hover { background: var(--surface-hover); }
  .legend-item.dimmed { opacity: 0.3; }
  .legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; box-shadow: 0 0 6px currentColor; }
  .legend-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-count { color: var(--text-tertiary); font-size: 11px; font-family: var(--font-mono); }

  #stats { padding: 10px 18px; border-top: 1px solid var(--border); display: flex; gap: 16px; flex-wrap: wrap; flex-shrink: 0; }
  .stat-item { display: flex; flex-direction: column; align-items: center; min-width: 48px; }
  .stat-value { font-size: 16px; font-weight: 700; font-family: var(--font-mono); color: var(--text-primary); letter-spacing: -0.02em; }
  .stat-label { font-size: 9px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.08em; margin-top: 1px; }

  #toolbar {
    position: absolute; top: 16px; left: 16px; display: flex; gap: 6px; z-index: 50;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 4px; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  }
  .toolbar-btn {
    background: none; border: none; color: var(--text-secondary); cursor: pointer;
    padding: 6px 8px; border-radius: var(--radius-sm); font-size: 13px;
    transition: var(--transition); display: flex; align-items: center; gap: 4px;
    font-family: var(--font);
  }
  .toolbar-btn:hover { background: var(--surface-hover); color: var(--text-primary); }
  .toolbar-btn.active { background: var(--surface-active); color: var(--accent); }
  .toolbar-btn .kbd { font-size: 9px; color: var(--text-tertiary); font-family: var(--font-mono); padding: 1px 4px; background: var(--surface); border-radius: 3px; }

  #minimap {
    position: absolute; bottom: 16px; right: 16px; width: 160px; height: 100px;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden; z-index: 50; cursor: pointer; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  }
  #minimap canvas { width: 100%; height: 100%; display: block; }
  #minimap .viewport { position: absolute; border: 1px solid rgba(255,255,255,0.3); border-radius: 2px; pointer-events: none; }

  #context-menu {
    position: fixed; z-index: 9998; min-width: 180px;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 4px; box-shadow: 0 20px 60px rgba(0,0,0,0.5); display: none;
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  }
  .ctx-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; cursor: pointer; border-radius: var(--radius-sm); font-size: 12px; transition: var(--transition); color: var(--text-secondary); }
  .ctx-item:hover { background: var(--surface-hover); color: var(--text-primary); }
  .ctx-separator { height: 1px; background: var(--border); margin: 4px 8px; }
  .ctx-item .icon { font-size: 14px; width: 18px; text-align: center; }
  .ctx-item .shortcut { margin-left: auto; color: var(--text-tertiary); font-size: 10px; font-family: var(--font-mono); }

  #toast-container { position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 9999; display: flex; flex-direction: column; gap: 8px; align-items: center; pointer-events: none; }
  .toast { padding: 8px 16px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius); font-size: 12px; color: var(--text-primary); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); animation: toastIn 0.3s ease, toastOut 0.3s ease 2.5s forwards; pointer-events: auto; }
  @keyframes toastIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
  @keyframes toastOut { from { opacity: 1; } to { opacity: 0; } }

  #timeline-bar {
    position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
    display: none; align-items: center; gap: 10px; z-index: 50;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 8px 14px; backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
  }
  #timeline-bar.visible { display: flex; }
  .tl-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 4px; border-radius: 4px; font-size: 16px; transition: var(--transition); display: flex; align-items: center; }
  .tl-btn:hover { background: var(--surface-hover); color: var(--text-primary); }
  #timeline-slider { -webkit-appearance: none; width: 200px; height: 4px; background: var(--border); border-radius: 2px; outline: none; }
  #timeline-slider::-webkit-slider-thumb { -webkit-appearance: none; width: 12px; height: 12px; border-radius: 50%; background: var(--accent); cursor: pointer; box-shadow: 0 0 8px var(--accent-glow); }
  #timeline-label { font-size: 11px; color: var(--text-secondary); font-family: var(--font-mono); min-width: 60px; text-align: center; }

  #legend-toggle {
    position: absolute; top: 16px; right: 16px; z-index: 50;
    background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 8px; cursor: pointer; color: var(--text-secondary); font-size: 16px;
    transition: var(--transition); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    display: flex; align-items: center; justify-content: center; display: none;
  }
  #legend-toggle:hover { background: var(--surface-hover); color: var(--text-primary); }

  @media (max-width: 768px) {
    #sidebar { position: fixed; right: 0; top: 0; width: 100%; max-width: 340px; box-shadow: -10px 0 40px rgba(0,0,0,0.5); }
    #legend-toggle { display: flex; }
    #sidebar.collapsed + #legend-toggle { display: flex; }
  }

  .badge-node { display: inline-flex; align-items: center; gap: 4px; padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 500; background: var(--surface); }

  #focus-mode-indicator { position: absolute; top: 60px; left: 16px; z-index: 50; display: none; font-size: 11px; color: var(--text-secondary); background: var(--bg-secondary); border: 1px solid var(--border); border-radius: var(--radius); padding: 6px 12px; align-items: center; gap: 6px; backdrop-filter: blur(20px); }
  #focus-mode-indicator .btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; padding: 2px 6px; border-radius: 4px; font-size: 11px; }
  #focus-mode-indicator .btn:hover { background: var(--surface-hover); color: var(--text-primary); }
</style>"""


def _hyperedge_script(hyperedges_json: str) -> str:
    if hyperedges_json.strip() in ("[]", "null", ""):
        return ""
    return f"""
const RAW_HYPEREDGES = {hyperedges_json};
"""


def _d3_source() -> str:
    """Read the embedded D3.js library from the package static directory."""
    pkg_dir = Path(__file__).resolve().parent
    d3_path = pkg_dir / "static" / "d3.min.js"
    if d3_path.exists():
        return d3_path.read_text(encoding="utf-8")
    # fallback: try relative to assets
    fallback = pkg_dir.parent / "static" / "d3.min.js"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"D3.js library not found at {d3_path}. "
        "Reinstall the package or run: "
        "curl -sL https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js -o graphify/static/d3.min.js"
    )


def _html_script(nodes_json: str, edges_json: str, legend_json: str) -> str:
    return """<script>__D3_SOURCE__</script>
<script>
const RAW_NODES = __NODES_JSON__;
const RAW_EDGES = __EDGES_JSON__;
const LEGEND = __LEGEND_JSON__;

if (typeof d3 === 'undefined') {
  document.getElementById('loading-screen').innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;"><h2>Failed to load D3.js</h2><p>Reinstall graphify or check that the D3 library is bundled correctly.</p></div>';
  throw new Error('D3.js not loaded');
}

const CFG = {
  nodeMinRadius: 2.5, nodeMaxRadius: 14, edgeBaseWidth: 1, edgeMaxWidth: 4,
  particleCount: 150, floatAmplitude: 0.6, simulationAlpha: 0.3, simulationAlphaMin: 0.01,
  simulationDecay: 0.02, labelMinScale: 1.8, glowIntensity: 0.6, communityHaloOpacity: 0.06,
};

const state = {
  nodes: [], edges: [], nodeMap: new Map(), communities: [], communityColors: new Map(),
  selectedNode: null, hoveredNode: null, hiddenCommunities: new Set(),
  simulation: null, transform: d3.zoomIdentity, time: 0, running: true, focusMode: false,
  particlePositions: [], initialized: false, loadStep: 0,
};

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function colorAlpha(hex, a) { return hex + Math.round(a*255).toString(16).padStart(2,'0'); }
function dist(x1,y1,x2,y2) { return Math.hypot(x2-x1,y2-y1); }
function cross(o,a,b) { return (a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]); }

function processData() {
  const maxDeg = Math.max(1, ...RAW_NODES.map(n => n.degree || 1));
  const legendColorMap = new Map(LEGEND.map(l => [l.cid, l.color]));
  state.nodes = RAW_NODES.map(n => ({
    id: n.id, label: n.label, community: n.community,
    community_name: n.community_name || 'Community ' + n.community,
    source_file: n.source_file || '', file_type: n.file_type || 'unknown',
    degree: n.degree || 1,
    radius: CFG.nodeMinRadius + (CFG.nodeMaxRadius - CFG.nodeMinRadius) * Math.sqrt((n.degree || 1) / maxDeg),
    color: legendColorMap.get(n.community) || '#64748b',
    x: (Math.random() - 0.5) * 200, y: (Math.random() - 0.5) * 200, vx: 0, vy: 0, opacity: 0, scale: 0,
  }));
  state.nodeMap = new Map(state.nodes.map(n => [n.id, n]));
  state.edges = RAW_EDGES.map((e, i) => ({
    source: e.from || e.source, target: e.to || e.target,
    relation: e.label || e.relation || '', confidence: e.confidence || 'EXTRACTED',
    weight: e.weight || 1,
    sourceNode: state.nodeMap.get(e.from || e.source),
    targetNode: state.nodeMap.get(e.to || e.target),
    opacity: 0, width: 1,
  })).filter(e => e.sourceNode && e.targetNode);

  const commMap = new Map();
  state.nodes.forEach(n => {
    const c = n.community;
    if (!commMap.has(c)) commMap.set(c, { cid: c, label: n.community_name, color: n.color, nodes: [], count: 0 });
    commMap.get(c).nodes.push(n);
    commMap.get(c).count++;
  });
  state.communities = Array.from(commMap.values());
  state.communityColors = new Map(state.communities.map(c => [c.cid, c.color]));
  state.particlePositions = [];
  if (state.edges.length > 0) {
    for (let i = 0; i < CFG.particleCount; i++) {
      const edge = state.edges[Math.floor(Math.random() * state.edges.length)];
      state.particlePositions.push({ edgeIdx: state.edges.indexOf(edge), t: Math.random(), speed: 0.003 + Math.random() * 0.005 });
    }
  }
}

function createSimulation() {
  const sim = d3.forceSimulation(state.nodes)
    .force('center', d3.forceCenter(0, 0).strength(0.02))
    .force('charge', d3.forceManyBody().strength(-80).distanceMax(400))
    .force('link', d3.forceLink(state.edges).id(d => d.id).distance(60).strength(0.3))
    .force('collision', d3.forceCollide().radius(d => d.radius * 1.5).strength(0.5))
    .alpha(1).alphaDecay(0.02)
    .on('tick', () => { if (!state.simulation) return; render(); })
    .stop();
  state.simulation = sim;
  return sim;
}

let canvas, ctx, minimapCanvas, minimapCtx, zoom, quadtree;

function setupDOM() {
  canvas = document.createElement('canvas');
  canvas.id = 'graph-canvas';
  const graphContainer = document.getElementById('graph-container');
  if (!graphContainer) throw new Error('Graph container not found');
  graphContainer.appendChild(canvas);
  ctx = canvas.getContext('2d');
  minimapCanvas = document.createElement('canvas');
  const minimapEl = document.getElementById('minimap');
  if (minimapEl) minimapEl.appendChild(minimapCanvas);
  minimapCtx = minimapCanvas.getContext('2d');
  zoom = d3.zoom().scaleExtent([0.05, 20]).on('zoom', (event) => {
    state.transform = event.transform; render(); updateMinimapViewport();
  });
  d3.select(canvas).call(zoom);
  quadtree = d3.quadtree();

  mouseX = 0; mouseY = 0;
  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    mouseX = e.clientX - rect.left; mouseY = e.clientY - rect.top;
    const node = findNodeAt(mouseX, mouseY);
    if (node !== state.hoveredNode) {
      state.hoveredNode = node; canvas.style.cursor = node ? 'pointer' : 'default';
      if (node) highlightConnected(node.id); else clearHighlight();
      render();
    }
  });
  canvas.addEventListener('mouseleave', () => { state.hoveredNode = null; canvas.style.cursor = 'default'; clearHighlight(); render(); });
  canvas.addEventListener('click', (e) => {
    if (e.detail === 2) return;
    const rect = canvas.getBoundingClientRect();
    const node = findNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (node) { state.selectedNode = node; showInfo(node.id); render(); }
    else { state.selectedNode = null; document.getElementById('info-content').innerHTML = '<span class="empty">Click a node to inspect it</span>'; }
  });
  canvas.addEventListener('dblclick', (e) => {
    const rect = canvas.getBoundingClientRect();
    const node = findNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    if (node) { focusNodeOn(node.id, 2.5); document.getElementById('focus-mode-indicator').style.display = 'flex'; state.focusMode = true; }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'F11') { e.preventDefault(); toggleFullscreen(); return; }
    const key = e.key === ' ' ? 'Space' : e.key;
    const combo = e.ctrlKey ? 'ctrl+'+key.toLowerCase() : key.toLowerCase();
    if (SHORTCUTS[combo]) { e.preventDefault(); SHORTCUTS[combo](); }
  });
  canvas.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const node = findNodeAt(e.clientX - rect.left, e.clientY - rect.top);
    showContextMenu(e, node);
  });
}

function resizeCanvas() {
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  canvas.style.width = rect.width + 'px'; canvas.style.height = rect.height + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}
function resizeMinimap() {
  const rect = document.getElementById('minimap').getBoundingClientRect();
  const w = rect.width || 160, h = rect.height || 100;
  const dpr = window.devicePixelRatio || 1;
  minimapCanvas.width = w * dpr; minimapCanvas.height = h * dpr;
  minimapCanvas.style.width = w + 'px'; minimapCanvas.style.height = h + 'px';
  minimapCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function focusNodeOn(nodeId, scale) {
  const node = state.nodeMap.get(nodeId);
  if (!node) return;
  const cx = canvas.parentElement.clientWidth / 2, cy = canvas.parentElement.clientHeight / 2;
  const s = scale || 2;
  const t = d3.zoomIdentity.translate(cx - node.x * s, cy - node.y * s).scale(s);
  d3.select(canvas).transition().duration(600).ease(d3.easeCubicInOut).call(zoom.transform, t);
  state.selectedNode = node; showInfo(nodeId);
}
function fitGraph() {
  if (!state.nodes.length) return;
  const padding = 80; let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  state.nodes.forEach(n => { if (n.x < x0) x0 = n.x; if (n.y < y0) y0 = n.y; if (n.x > x1) x1 = n.x; if (n.y > y1) y1 = n.y; });
  const dx = x1 - x0 || 1, dy = y1 - y0 || 1;
  const cw = canvas.parentElement.clientWidth, ch = canvas.parentElement.clientHeight;
  const s = Math.min((cw - padding * 2) / dx, (ch - padding * 2) / dy);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const t = d3.zoomIdentity.translate(cw / 2 - cx * s, ch / 2 - cy * s).scale(s);
  d3.select(canvas).transition().duration(800).ease(d3.easeCubicInOut).call(zoom.transform, t);
}
function resetView() {
  d3.select(canvas).transition().duration(600).ease(d3.easeCubicInOut).call(zoom.transform, d3.zoomIdentity);
  state.focusMode = false; document.getElementById('focus-mode-indicator').style.display = 'none';
}

function rebuildQuadtree() {
  quadtree = d3.quadtree().x(d => d.x).y(d => d.y);
  state.nodes.forEach(n => { if (!state.hiddenCommunities.has(n.community)) quadtree.add(n); });
}
function findNodeAt(mx, my) {
  const t = state.transform, gx = (mx - t.x) / t.k, gy = (my - t.y) / t.k;
  const threshold = Math.max(8 / t.k, 3); let best = null, bestD = Infinity;
  quadtree.visit((node, x0, y0, x1, y1) => {
    if (!node) return true;
    if (!node.length) {
      const n = node.data;
      if (n) { const d = dist(gx, gy, n.x, n.y); if (d < threshold + n.radius && d < bestD) { best = n; bestD = d; } }
      return true;
    }
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    return (gx - cx) * (gx - cx) + (gy - cy) * (gy - cy) > (threshold + (x1 - x0)) * (threshold + (y1 - y0));
  });
  return best;
}

function render() {
  if (!state.initialized || !state.nodes.length) return;
  const cw = canvas.parentElement.clientWidth, ch = canvas.parentElement.clientHeight;
  ctx.clearRect(0, 0, cw, ch); ctx.save();
  ctx.translate(state.transform.x, state.transform.y);
  ctx.scale(state.transform.k, state.transform.k);
  drawCommunityHalos(ctx); drawEdges(ctx); drawNodes(ctx);
  drawEdgeParticles(ctx); drawLabels(ctx); drawHyperedges(ctx);
  ctx.restore(); drawMinimap();
}

function drawCommunityHalos(ctx) {
  const scale = state.transform.k;
  if (scale < 0.3) return;
  state.communities.forEach(comm => {
    if (state.hiddenCommunities.has(comm.cid) || comm.nodes.length < 3) return;
    const pts = comm.nodes.map(n => [n.x, n.y]);
    const sorted = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    if (sorted[0][0] === sorted[sorted.length-1][0] && sorted[0][1] === sorted[sorted.length-1][1]) return;
    const lower = [], upper = [];
    for (const p of sorted) { while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop(); lower.push(p); }
    for (let i = sorted.length-1; i >= 0; i--) { const p = sorted[i]; while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop(); upper.push(p); }
    lower.pop(); upper.pop(); const hull = lower.concat(upper);
    if (hull.length < 3) return;
    ctx.save(); ctx.globalAlpha = CFG.communityHaloOpacity * Math.min(1, scale / 1.5);
    ctx.fillStyle = comm.color; ctx.beginPath(); ctx.moveTo(hull[0][0], hull[0][1]);
    for (let i = 1; i < hull.length; i++) ctx.lineTo(hull[i][0], hull[i][1]);
    ctx.closePath(); ctx.fill(); ctx.restore();
  });
}

function drawEdges(ctx) {
  const scale = state.transform.k, cw = canvas.parentElement.clientWidth, ch = canvas.parentElement.clientHeight;
  state.edges.forEach(e => {
    if (state.hiddenCommunities.has(e.sourceNode.community) || state.hiddenCommunities.has(e.targetNode.community)) return;
    const sn = e.sourceNode, tn = e.targetNode, sx = sn.x, sy = sn.y, tx = tn.x, ty = tn.y;
    const mx = (sx+tx)/2, my = (sy+ty)/2;
    const vx = mx - state.transform.x/state.transform.k, vy = my - state.transform.y/state.transform.k;
    const hw = cw/(2*state.transform.k)+50, hh = ch/(2*state.transform.k)+50;
    if (Math.abs(vx) > hw || Math.abs(vy) > hh) return;
    const w = (CFG.edgeBaseWidth + e.weight * 0.5) * Math.min(1, scale * 0.8);
    const fade = Math.min(1, scale * 2); let alpha = 0.15 * fade * e.opacity;
    if (state.hoveredNode) {
      if (sn.id === state.hoveredNode.id || tn.id === state.hoveredNode.id) alpha = 0.5 * fade;
      else alpha *= 0.15;
    }
    ctx.save(); ctx.globalAlpha = alpha;
    ctx.strokeStyle = state.communityColors.get(e.sourceNode.community) || '#64748b';
    ctx.lineWidth = w; ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(tx, ty); ctx.stroke(); ctx.restore();
  });
}

function drawNodes(ctx) {
  const scale = state.transform.k;
  state.nodes.forEach(n => {
    if (state.hiddenCommunities.has(n.community)) return;
    const fl = CFG.floatAmplitude * Math.sin(state.time * 0.001 + n.x * 0.01 + n.y * 0.01);
    const x = n.x + fl, y = n.y + fl * 0.7;
    const r = n.radius * n.scale * Math.min(1, scale * 0.5 + 0.5);
    if (n.opacity < 0.01 || r < 0.5) return;
    const isHovered = state.hoveredNode && state.hoveredNode.id === n.id;
    const isSelected = state.selectedNode && state.selectedNode.id === n.id;
    const glow = isHovered ? 1 : isSelected ? 0.8 : 0.3;
    ctx.save(); ctx.globalAlpha = n.opacity;
    if (scale > 0.3) {
      const grad = ctx.createRadialGradient(x, y, 0, x, y, r * 4);
      grad.addColorStop(0, colorAlpha(n.color, 0.3 * glow));
      grad.addColorStop(1, colorAlpha(n.color, 0));
      ctx.fillStyle = grad; ctx.beginPath(); ctx.arc(x, y, r * 4, 0, Math.PI * 2); ctx.fill();
    }
    ctx.shadowColor = n.color; ctx.shadowBlur = isHovered ? 20 : isSelected ? 15 : 8;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fillStyle = isHovered ? '#fff' : n.color; ctx.fill();
    ctx.shadowBlur = 0;
    const inner = ctx.createRadialGradient(x - r*0.3, y - r*0.3, 0, x, y, r);
    inner.addColorStop(0, 'rgba(255,255,255,0.4)'); inner.addColorStop(0.5, 'rgba(255,255,255,0.1)'); inner.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = inner; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
    if (isSelected || isHovered) {
      ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(x, y, r + 1.5, 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
  });
}

function drawEdgeParticles(ctx) {
  const scale = state.transform.k;
  if (scale < 0.5 || !state.edges.length) return;
  ctx.save();
  state.particlePositions.forEach(p => {
    const edge = state.edges[p.edgeIdx];
    if (!edge || state.hiddenCommunities.has(edge.sourceNode.community) || state.hiddenCommunities.has(edge.targetNode.community)) return;
    const t = p.t, x = edge.sourceNode.x + (edge.targetNode.x - edge.sourceNode.x) * t;
    const y = edge.sourceNode.y + (edge.targetNode.y - edge.sourceNode.y) * t;
    const size = 2 * Math.min(1, scale);
    const grad = ctx.createRadialGradient(x, y, 0, x, y, size * 3);
    grad.addColorStop(0, colorAlpha(edge.sourceNode.color, 0.6));
    grad.addColorStop(1, colorAlpha(edge.sourceNode.color, 0));
    ctx.fillStyle = grad; ctx.globalAlpha = 0.6;
    ctx.beginPath(); ctx.arc(x, y, size * 3, 0, Math.PI * 2); ctx.fill();
    ctx.globalAlpha = 0.9; ctx.fillStyle = '#fff';
    ctx.beginPath(); ctx.arc(x, y, size * 0.5, 0, Math.PI * 2); ctx.fill();
  });
  ctx.restore();
}

function drawLabels(ctx) {
  const scale = state.transform.k;
  if (scale < CFG.labelMinScale * 0.5) return;
  ctx.save();
  const fontSize = Math.min(12, Math.max(8, 12 * scale / CFG.labelMinScale));
  ctx.font = fontSize + 'px system-ui, -apple-system, sans-serif';
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  state.nodes.forEach(n => {
    if (state.hiddenCommunities.has(n.community) || n.opacity < 0.3) return;
    const fl = CFG.floatAmplitude * Math.sin(state.time * 0.001 + n.x * 0.01 + n.y * 0.01);
    const x = n.x + fl, y = n.y + fl * 0.7;
    const isHovered = state.hoveredNode && state.hoveredNode.id === n.id;
    const isSelected = state.selectedNode && state.selectedNode.id === n.id;
    if (!isHovered && !isSelected && scale <= CFG.labelMinScale) return;
    const alpha = Math.min(1, n.opacity * (isHovered ? 1 : (scale - CFG.labelMinScale * 0.5) / (CFG.labelMinScale * 0.5)));
    if (alpha < 0.1) return;
    ctx.globalAlpha = alpha;
    const yOff = n.radius * n.scale * Math.min(1, scale * 0.5 + 0.5) + fontSize + 2;
    const tw = ctx.measureText(n.label).width;
    ctx.fillStyle = 'rgba(7,7,13,0.7)'; const pad = 4, rx = 3, bw = tw + pad * 2, bh = fontSize + pad;
    const bx = x - bw/2, by = y + yOff - bh/2;
    ctx.beginPath(); ctx.moveTo(bx+rx, by); ctx.lineTo(bx+bw-rx, by);
    ctx.quadraticCurveTo(bx+bw, by, bx+bw, by+rx); ctx.lineTo(bx+bw, by+bh-rx);
    ctx.quadraticCurveTo(bx+bw, by+bh, bx+bw-rx, by+bh); ctx.lineTo(bx+rx, by+bh);
    ctx.quadraticCurveTo(bx, by+bh, bx, by+bh-rx); ctx.lineTo(bx, by+rx);
    ctx.quadraticCurveTo(bx, by, bx+rx, by); ctx.closePath(); ctx.fill();
    ctx.fillStyle = isHovered ? '#fff' : 'rgba(255,255,255,0.85)';
    ctx.fillText(n.label, x, y + yOff);
  });
  ctx.restore();
}

function drawHyperedges(ctx) {
  if (!window.RAW_HYPEREDGES || !RAW_HYPEREDGES.length) return;
  RAW_HYPEREDGES.forEach(h => {
    const positions = h.nodes.map(nid => { const n = state.nodeMap.get(nid); return n ? [n.x, n.y] : null; }).filter(p => p);
    if (positions.length < 2) return;
    const cx = positions.reduce((s,p) => s+p[0],0)/positions.length;
    const cy = positions.reduce((s,p) => s+p[1],0)/positions.length;
    const expanded = positions.map(p => [cx+(p[0]-cx)*1.15, cy+(p[1]-cy)*1.15]);
    ctx.save(); ctx.globalAlpha = 0.08; ctx.fillStyle = '#6366f1'; ctx.strokeStyle = '#6366f1'; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(expanded[0][0], expanded[0][1]);
    expanded.slice(1).forEach(p => ctx.lineTo(p[0], p[1])); ctx.closePath(); ctx.fill();
    ctx.globalAlpha = 0.3; ctx.stroke(); ctx.globalAlpha = 0.7;
    ctx.fillStyle = '#8b5cf6'; ctx.font = 'bold 10px system-ui, sans-serif';
    ctx.textAlign = 'center'; ctx.fillText(h.label || '', cx, cy - 6); ctx.restore();
  });
}

function drawMinimap() {
  const rect = document.getElementById('minimap').getBoundingClientRect();
  const mw = rect.width, mh = rect.height;
  if (mw === 0 || mh === 0) return;
  minimapCtx.clearRect(0, 0, mw, mh);
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  state.nodes.forEach(n => { if (n.x<x0) x0=n.x; if (n.y<y0) y0=n.y; if (n.x>x1) x1=n.x; if (n.y>y1) y1=n.y; });
  const gx=x0-10,gy=y0-10,gw=(x1-x0)+20||1,gh=(y1-y0)+20||1;
  const sc = Math.min(mw/gw, mh/gh);
  const ox = (mw - gw*sc)/2, oy = (mh - gh*sc)/2;
  state.nodes.forEach(n => {
    if (state.hiddenCommunities.has(n.community)) return;
    const x = ox + (n.x - gx) * sc, y = oy + (n.y - gy) * sc;
    minimapCtx.fillStyle = n.color; minimapCtx.globalAlpha = 0.6;
    minimapCtx.beginPath(); minimapCtx.arc(x, y, Math.max(1, n.radius * 0.5 * sc), 0, Math.PI * 2); minimapCtx.fill();
  });
  minimapCtx.globalAlpha = 1;
  const t = state.transform;
  const vx = ox + (-t.x/t.k - gx) * sc, vy = oy + (-t.y/t.k - gy) * sc;
  const vw = (canvas.parentElement.clientWidth / t.k) * sc, vh = (canvas.parentElement.clientHeight / t.k) * sc;
  minimapCtx.strokeStyle = 'rgba(255,255,255,0.4)'; minimapCtx.lineWidth = 1;
  minimapCtx.strokeRect(vx, vy, vw, vh);
}
function updateMinimapViewport() {
  const el = document.getElementById('minimap');
  const rect = el.getBoundingClientRect(); const mw = rect.width, mh = rect.height;
  if (mw === 0 || mh === 0) return;
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  state.nodes.forEach(n => { if (n.x<x0) x0=n.x; if (n.y<y0) y0=n.y; if (n.x>x1) x1=n.x; if (n.y>y1) y1=n.y; });
  const sc = Math.min(mw/((x1-x0)+20||1), mh/((y1-y0)+20||1));
  const ox = (mw - ((x1-x0)+20) * sc)/2, oy = (mh - ((y1-y0)+20) * sc)/2;
  const t = state.transform;
  const vx = ox + (-t.x/t.k - (x0-10)) * sc, vy = oy + (-t.y/t.k - (y0-10)) * sc;
  const vw = (canvas.parentElement.clientWidth / t.k) * sc, vh = (canvas.parentElement.clientHeight / t.k) * sc;
  const vp = el.querySelector('.viewport') || document.createElement('div');
  vp.className = 'viewport'; vp.style.cssText = 'left:'+vx+'px;top:'+vy+'px;width:'+vw+'px;height:'+vh+'px;';
  if (!el.querySelector('.viewport')) el.appendChild(vp);
}

function highlightConnected(nodeId) {
  const connected = new Set();
  state.edges.forEach(e => { if (e.sourceNode.id === nodeId) connected.add(e.targetNode.id); if (e.targetNode.id === nodeId) connected.add(e.sourceNode.id); });
  state.nodes.forEach(n => { n._dimmed = (n.id !== nodeId && !connected.has(n.id)); });
}
function clearHighlight() { state.nodes.forEach(n => n._dimmed = false); }

function buildCommunityList() {
  const el = document.getElementById('legend'); el.innerHTML = '';
  state.communities.forEach(comm => {
    const item = document.createElement('div'); item.className = 'legend-item';
    const cb = document.createElement('input'); cb.type = 'checkbox'; cb.className = 'legend-cb';
    cb.checked = !state.hiddenCommunities.has(comm.cid);
    cb.addEventListener('change', () => {
      if (cb.checked) state.hiddenCommunities.delete(comm.cid); else state.hiddenCommunities.add(comm.cid);
      item.classList.toggle('dimmed', !cb.checked); rebuildQuadtree(); updateSelectAllState(); render();
    });
    item.innerHTML = '<div class="legend-dot" style="background:'+comm.color+';color:'+comm.color+'"></div><span class="legend-label">'+comm.label+'</span><span class="legend-count">'+comm.count+'</span>';
    item.prepend(cb);
    item.addEventListener('click', (e) => { if (e.target !== cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); } });
    el.appendChild(item);
  });
  updateSelectAllState();
}
function updateSelectAllState() {
  const total = state.communities.length, hidden = state.hiddenCommunities.size;
  const cb = document.getElementById('select-all-cb'); cb.checked = hidden === 0; cb.indeterminate = hidden > 0 && hidden < total;
}
function toggleAllCommunities(hide) {
  document.querySelectorAll('.legend-item').forEach(item => item.classList.toggle('dimmed', hide));
  document.querySelectorAll('.legend-cb').forEach(cb => cb.checked = !hide);
  state.communities.forEach(c => { if (hide) state.hiddenCommunities.add(c.cid); else state.hiddenCommunities.delete(c.cid); });
  rebuildQuadtree(); updateSelectAllState(); render();
}

function setupSearch() {
  const input = document.getElementById('search'), results = document.getElementById('search-results');
  input.addEventListener('input', () => {
    const q = input.value.toLowerCase().trim(); results.innerHTML = '';
    if (!q) { results.style.display = 'none'; return; }
    const matches = state.nodes.filter(n => n.label.toLowerCase().includes(q)).slice(0, 20);
    if (!matches.length) { results.style.display = 'none'; return; }
    results.style.display = 'block';
    matches.forEach(n => {
      const el = document.createElement('div'); el.className = 'search-item';
      el.innerHTML = '<span class="dot" style="background:'+n.color+'"></span><span class="name">'+esc(n.label)+'</span><span class="badge">'+n.file_type+'</span>';
      el.addEventListener('click', () => { focusNodeOn(n.id, 2.5); state.selectedNode = n; results.style.display = 'none'; input.value = ''; render(); });
      results.appendChild(el);
    });
  });
  document.addEventListener('click', (e) => { if (!results.contains(e.target) && e.target !== input) results.style.display = 'none'; });
}

function showInfo(nodeId) {
  const n = state.nodeMap.get(nodeId); if (!n) return;
  const neighborItems = [];
  state.edges.forEach(e => {
    let nb = null;
    if (e.sourceNode.id === nodeId) nb = e.targetNode;
    if (e.targetNode.id === nodeId) nb = e.sourceNode;
    if (nb) neighborItems.push('<div class="neighbor-link" data-id="'+esc(nb.id)+'"><span class="ndot" style="background:'+nb.color+'"></span>'+esc(nb.label)+'<span style="color:var(--text-tertiary);font-size:10px;margin-left:auto">'+e.relation+'</span></div>');
  });
  const relCount = neighborItems.length;
  const neighborsHtml = relCount ? '<div style="margin-top:8px;color:var(--text-tertiary);font-size:10px;text-transform:uppercase;letter-spacing:0.08em">Connected Nodes</div><div id="neighbors-list">'+neighborItems.join('')+'</div>' : '';
  document.getElementById('info-content').innerHTML = '<div class="info-title">'+esc(n.label)+'</div><div><span class="info-tag">'+n.file_type+'</span><span class="info-tag" style="background:'+n.color+'20;color:'+n.color+'">'+n.community_name+'</span></div><div class="info-row"><span class="label">File</span><span class="value">'+esc(n.source_file||'-')+'</span></div><div class="info-row"><span class="label">Degree</span><span class="value">'+n.degree+'</span></div><div class="info-row"><span class="label">Relationships</span><span class="value">'+relCount+'</span></div>'+neighborsHtml;
  document.querySelectorAll('.neighbor-link').forEach(el => {
    el.addEventListener('click', () => { const id = el.dataset.id; focusNodeOn(id, 2); state.selectedNode = state.nodeMap.get(id); render(); });
  });
}

let statsAnimated = false;
function animateStats() {
  if (statsAnimated) return; statsAnimated = true;
  const counts = {
    nodes: state.nodes.length, edges: state.edges.length,
    communities: state.communities.length,
    files: new Set(state.nodes.filter(n => n.file_type === 'code').map(n => n.source_file)).size,
    types: new Set(state.nodes.map(n => n.file_type)).size,
  };
  Object.entries(counts).forEach(([key, target]) => {
    const el = document.getElementById('stat-' + key); if (!el) return;
    const duration = 1200, start = performance.now();
    function update() {
      const t = Math.min(1, (performance.now() - start) / duration);
      el.textContent = Math.floor((1 - Math.pow(1 - t, 3)) * target);
      if (t < 1) requestAnimationFrame(update); else el.textContent = target;
    }
    update();
  });
}

function setupTimeline() {
  const bar = document.getElementById('timeline-bar'), playBtn = document.getElementById('tl-play');
  const slider = document.getElementById('timeline-slider'), label = document.getElementById('timeline-label');
  let playing = false, animId = null;
  playBtn.addEventListener('click', () => { playing = !playing; playBtn.textContent = playing ? '\u23F8' : '\u25B6'; if (playing) animateTimeline(); });
  slider.addEventListener('input', () => { const t = parseFloat(slider.value); label.textContent = Math.round(t*100)+'%'; setTimelineProgress(t); });
  function animateTimeline() {
    if (!playing) return;
    const val = parseFloat(slider.value) + 0.005;
    if (val >= 1) { playing = false; playBtn.textContent = '\u21BB'; slider.value = 1; label.textContent = '100%'; setTimelineProgress(1); return; }
    slider.value = val; label.textContent = Math.round(val*100)+'%'; setTimelineProgress(val);
    animId = requestAnimationFrame(animateTimeline);
  }
  function setTimelineProgress(t) {
    state.nodes.forEach((n, i) => { n.opacity = Math.min(1, (t * state.nodes.length - i + 10) / 10); n.scale = Math.min(1, (t * state.nodes.length - i + 5) / 5); });
    state.edges.forEach((e, i) => { e.opacity = Math.min(1, (t * state.edges.length - i + 5) / 5); });
    render();
  }
  window.showTimeline = () => { bar.classList.add('visible'); };
  window.hideTimeline = () => { bar.classList.remove('visible'); playing = false; if (animId) cancelAnimationFrame(animId); };
}

const SHORTCUTS = {
  'f': () => fitGraph(), 'r': () => resetView(), 's': () => document.getElementById('search').focus(),
  'Escape': () => { resetView(); document.getElementById('search').blur(); document.getElementById('search-results').style.display = 'none'; },
  't': () => document.getElementById('timeline-bar').classList.toggle('visible'),
  'b': () => document.getElementById('sidebar').classList.toggle('collapsed'),
  'p': () => exportPNG(),
  '?': () => showShortcuts(),
};
function showShortcuts() {
  const items = [['F','Fit graph'],['R','Reset view'],['S','Search'],['Esc','Reset & close'],['T','Toggle timeline'],['B','Toggle sidebar'],['F11','Fullscreen'],['P','Export PNG'],['?','Show shortcuts']];
  const html = '<div style="min-width:200px"><div style="font-weight:600;margin-bottom:8px;font-size:13px">Keyboard Shortcuts</div>'+items.map(([k,d]) => '<div style="display:flex;justify-content:space-between;padding:3px 0;font-size:12px"><span>'+d+'</span><span style="color:var(--text-tertiary);font-family:var(--font-mono)">'+k+'</span></div>').join('')+'</div>';
  showToast(html, 5000);
}

function showContextMenu(e, node) {
  const menu = document.getElementById('context-menu');
  const items = node ? [
    ['\u25C9', 'Focus node', function() { focusNodeOn(node.id, 2.5); }],
    ['\u229E', 'Fit to node', function() { focusNodeOn(node.id, 2.5); }],
    null,
    ['\u2B07', 'Export PNG', exportPNG],
    ['📄', 'Export SVG', exportSVG],
  ] : [
    ['\u229E', 'Fit graph', fitGraph],
    ['\u27F2', 'Reset view', resetView],
    ['\u26F6', 'Fullscreen', toggleFullscreen],
    null,
    ['\u2B07', 'Export PNG', exportPNG],
    ['📄', 'Export SVG', exportSVG],
    null,
    ['\u2600', 'Toggle theme', toggleTheme],
  ];
  menu.innerHTML = items.map(item => {
    if (!item) return '<div class="ctx-separator"></div>';
    return '<div class="ctx-item"><span class="icon">'+item[0]+'</span>'+item[1]+'</div>';
  }).join('');
  menu.style.display = 'block';
  menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
  menu.style.top = Math.min(e.clientY, window.innerHeight - 200) + 'px';
  Array.from(menu.querySelectorAll('.ctx-item')).forEach((el, i) => {
    const realIdx = items.filter(Boolean).length <= i ? -1 : items.filter(item => item !== null).indexOf(items.filter(item => item !== null)[i]);
    const item = items.filter(item => item !== null)[i];
    if (item) el.addEventListener('click', function() { menu.style.display = 'none'; item[2](); });
  });
  document.addEventListener('click', function handler() { menu.style.display = 'none'; document.removeEventListener('click', handler); }, { once: true });
}
function toggleTheme() {
  const root = document.documentElement;
  const isDark = root.style.getPropertyValue('--bg-primary') !== '#ffffff';
  if (isDark) {
    root.style.setProperty('--bg-primary', '#ffffff'); root.style.setProperty('--bg-secondary', '#f8f8fb');
    root.style.setProperty('--surface','rgba(0,0,0,0.03)'); root.style.setProperty('--surface-hover','rgba(0,0,0,0.06)'); root.style.setProperty('--surface-active','rgba(0,0,0,0.1)');
    root.style.setProperty('--border','rgba(0,0,0,0.08)'); root.style.setProperty('--border-hover','rgba(0,0,0,0.15)');
    root.style.setProperty('--text-primary','rgba(0,0,0,0.92)'); root.style.setProperty('--text-secondary','rgba(0,0,0,0.55)'); root.style.setProperty('--text-tertiary','rgba(0,0,0,0.30)');
    canvas.style.background = '#ffffff'; showToast('Light theme');
  } else {
    root.style.setProperty('--bg-primary','#07070d'); root.style.setProperty('--bg-secondary','#0c0c1a');
    root.style.setProperty('--surface','rgba(255,255,255,0.04)'); root.style.setProperty('--surface-hover','rgba(255,255,255,0.08)'); root.style.setProperty('--surface-active','rgba(255,255,255,0.12)');
    root.style.setProperty('--border','rgba(255,255,255,0.06)'); root.style.setProperty('--border-hover','rgba(255,255,255,0.12)');
    root.style.setProperty('--text-primary','rgba(255,255,255,0.92)'); root.style.setProperty('--text-secondary','rgba(255,255,255,0.55)'); root.style.setProperty('--text-tertiary','rgba(255,255,255,0.30)');
    canvas.style.background = '#07070d'; showToast('Dark theme');
  }
}

function showToast(msg, duration) {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = msg;
  container.appendChild(el);
  setTimeout(() => el.remove(), duration || 3000);
}

function exportPNG() {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.width / dpr, h = canvas.height / dpr;
  const offscreen = document.createElement('canvas');
  offscreen.width = canvas.width; offscreen.height = canvas.height;
  const offCtx = offscreen.getContext('2d');
  offCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  offCtx.fillStyle = '#07070d'; offCtx.fillRect(0, 0, w, h);
  offCtx.save();
  offCtx.translate(state.transform.x, state.transform.y);
  offCtx.scale(state.transform.k, state.transform.k);
  state.edges.forEach(e => {
    if (state.hiddenCommunities.has(e.sourceNode.community)) return;
    offCtx.globalAlpha = 0.2;
    const col = state.communityColors.get(e.sourceNode.community) || '#64748b';
    offCtx.strokeStyle = col; offCtx.lineWidth = 1;
    offCtx.beginPath(); offCtx.moveTo(e.sourceNode.x, e.sourceNode.y); offCtx.lineTo(e.targetNode.x, e.targetNode.y); offCtx.stroke();
  });
  state.nodes.forEach(n => {
    if (state.hiddenCommunities.has(n.community)) return;
    offCtx.globalAlpha = n.opacity; offCtx.fillStyle = n.color;
    offCtx.beginPath(); offCtx.arc(n.x, n.y, n.radius * n.scale, 0, Math.PI * 2); offCtx.fill();
  });
  offCtx.restore();
  const link = document.createElement('a');
  link.download = 'graphify-export.png'; link.href = offscreen.toDataURL('image/png'); link.click();
  showToast('Exported PNG');
}

function exportSVG() {
  let svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="-500 -500 1000 1000">';
  state.edges.forEach(e => {
    if (state.hiddenCommunities.has(e.sourceNode.community)) return;
    const col = state.communityColors.get(e.sourceNode.community) || '#64748b';
    svg += '<line x1="'+e.sourceNode.x+'" y1="'+e.sourceNode.y+'" x2="'+e.targetNode.x+'" y2="'+e.targetNode.y+'" stroke="'+col+'" opacity="0.15" stroke-width="0.5"/>';
  });
  state.nodes.forEach(n => {
    if (state.hiddenCommunities.has(n.community)) return;
    svg += '<circle cx="'+n.x+'" cy="'+n.y+'" r="'+(n.radius * n.scale)+'" fill="'+n.color+'" opacity="'+n.opacity+'"/>';
  });
  svg += '</svg>';
  const blob = new Blob([svg], { type: 'image/svg+xml' });
  const link = document.createElement('a');
  link.download = 'graphify-export.svg'; link.href = URL.createObjectURL(blob); link.click();
  URL.revokeObjectURL(link.href);
  showToast('Exported SVG');
}

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen();
}

function setQuality(level) {
  if (level === 'low') { CFG.particleCount = 0; CFG.glowIntensity = 0; CFG.communityHaloOpacity = 0; }
  else if (level === 'medium') { CFG.particleCount = 50; CFG.glowIntensity = 0.3; CFG.communityHaloOpacity = 0.03; }
  else { CFG.particleCount = 150; CFG.glowIntensity = 0.6; CFG.communityHaloOpacity = 0.06; }
  showToast('Quality: '+level);
}

function setLoadStep(n) {
  state.loadStep = n;
  const steps = document.querySelectorAll('.step');
  steps.forEach((s, i) => {
    s.classList.remove('active', 'done');
    if (i < n) s.classList.add('done');
    else if (i === n) s.classList.add('active');
  });
  document.querySelector('.progress-fill').style.width = (n / 7) * 100 + '%';
}

function animate(time) {
  if (!state.running) return;
  state.time = time;
  if (CFG.particleCount > 0) {
    state.particlePositions.forEach(p => {
      p.t += p.speed;
      if (p.t > 1) {
        p.t = 0;
        const edge = state.edges[Math.floor(Math.random() * state.edges.length)];
        if (edge) p.edgeIdx = state.edges.indexOf(edge);
      }
    });
  }
  render();
  requestAnimationFrame(animate);
}

function init() {
  try {
    setupDOM();
  } catch (e) {
    document.getElementById('loading-screen').innerHTML = '<div style="text-align:center;padding:40px;color:#ef4444;"><h2>Failed to initialize</h2><p style="font-family:monospace;font-size:13px;background:#1e293b;padding:12px;border-radius:6px;color:#e2e8f0;">' + esc(e.message) + '</p><p>Try opening via HTTP server: <code style="background:#1e293b;padding:3px 8px;border-radius:4px;color:#e2e8f0;">python -m http.server 8080</code></p></div>';
    return;
  }
  setLoadStep(0);
  setTimeout(() => {
    setLoadStep(1); processData();
    setLoadStep(2); createSimulation();
    setLoadStep(3); resizeCanvas(); resizeMinimap(); rebuildQuadtree();
    setLoadStep(4); buildCommunityList(); setupSearch(); setupTimeline();
    setLoadStep(5);
    state.simulation.restart();
    let stabilized = false;
    state.simulation.on('end', () => {
      if (stabilized) return; stabilized = true;
      setLoadStep(6); state.initialized = true;
      state.nodes.forEach((n, i) => { setTimeout(() => { n.opacity = 1; n.scale = 1; }, i * 8); });
      state.edges.forEach((e, i) => { setTimeout(() => { e.opacity = 1; }, i * 4 + 200); });
      setTimeout(() => {
        setLoadStep(7); fitGraph(); animateStats();
        setTimeout(() => { document.getElementById('loading-screen').classList.add('hidden'); }, 500);
      }, state.nodes.length * 8 + 400);
      requestAnimationFrame(animate);
    });
    setTimeout(() => { if (state.simulation) state.simulation.alphaTarget(0).stop(); }, 4000);
  }, 300);
}

window.addEventListener('resize', () => { resizeCanvas(); resizeMinimap(); render(); });
window.addEventListener('load', init);
window.fitGraph = fitGraph; window.resetView = resetView;
window.toggleFullscreen = toggleFullscreen; window.exportPNG = exportPNG;
window.exportSVG = exportSVG; window.toggleAllCommunities = toggleAllCommunities;
window.focusNodeOn = focusNodeOn; window.showInfo = showInfo; window.setQuality = setQuality;
</script>""".replace('__D3_SOURCE__', _d3_source()).replace('__NODES_JSON__', nodes_json).replace('__EDGES_JSON__', edges_json).replace('__LEGEND_JSON__', legend_json)


_CONFIDENCE_SCORE_DEFAULTS = {"EXTRACTED": 1.0, "INFERRED": 0.5, "AMBIGUOUS": 0.2}


def attach_hyperedges(G: nx.Graph, hyperedges: list) -> None:
    """Store hyperedges in the graph's metadata dict."""
    existing = G.graph.get("hyperedges", [])
    seen_ids = {h["id"] for h in existing}
    for h in hyperedges:
        if h.get("id") and h["id"] not in seen_ids:
            existing.append(h)
            seen_ids.add(h["id"])
    G.graph["hyperedges"] = existing


def _git_head() -> str | None:
    """Return the current git HEAD commit hash, or None if not in a git repo."""
    import subprocess as _sp
    try:
        r = _sp.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def to_json(G: nx.Graph, communities: dict[int, list[str]], output_path: str, *, force: bool = False, built_at_commit: str | None = None, community_labels: dict[int, str] | None = None) -> bool:
    # Safety check: refuse to silently shrink an existing graph (#479)
    existing_path = Path(output_path)
    if not force and existing_path.exists():
        try:
            from graphify.security import check_graph_file_size_cap
            check_graph_file_size_cap(existing_path)
            existing_data = json.loads(existing_path.read_text(encoding="utf-8"))
            existing_n = len(existing_data.get("nodes", []))
            new_n = G.number_of_nodes()
            if new_n < existing_n:
                import sys as _sys
                print(
                    f"[graphify] WARNING: new graph has {new_n} nodes but existing "
                    f"graph.json has {existing_n} (net -{existing_n - new_n}). "
                    f"Refusing to overwrite. Possible causes: missing chunk files from "
                    f"a previous session, or fuzzy dedup collapsed same-named symbols "
                    f"across files during an --update on an already-current graph. "
                    f"Run a full rebuild (/graphify .) to be safe, or pass force=True "
                    f"only if you have verified the reduction is legitimate.",
                    file=_sys.stderr,
                )
                return False
        except Exception:
            pass  # unreadable existing file — proceed with write

    node_community = _node_community_map(communities)
    _labels: dict[int, str] = {int(k): v for k, v in (community_labels or {}).items()}
    try:
        data = json_graph.node_link_data(G, edges="links")
    except TypeError:
        data = json_graph.node_link_data(G)
    for node in data["nodes"]:
        cid = node_community.get(node["id"])
        node["community"] = cid
        if cid is not None and _labels:
            node["community_name"] = _labels.get(cid, f"Community {cid}")
        node["norm_label"] = _strip_diacritics(node.get("label", "")).lower()
    for link in data["links"]:
        if "confidence_score" not in link:
            conf = link.get("confidence", "EXTRACTED")
            link["confidence_score"] = _CONFIDENCE_SCORE_DEFAULTS.get(conf, 1.0)
        # Restore original edge direction. Undirected NetworkX storage may
        # canonicalize endpoint order, flipping `calls` and other directional
        # edges in graph.json. The build path stashes the true endpoints in
        # _src/_tgt for exactly this purpose (#563).
        true_src = link.pop("_src", None)
        true_tgt = link.pop("_tgt", None)
        if true_src is not None and true_tgt is not None:
            link["source"] = true_src
            link["target"] = true_tgt
    data["hyperedges"] = getattr(G, "graph", {}).get("hyperedges", [])
    commit = built_at_commit if built_at_commit is not None else _git_head()
    if commit:
        data["built_at_commit"] = commit
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        json.dump(data, f, indent=2)
    return True


def prune_dangling_edges(graph_data: dict) -> tuple[dict, int]:
    """Remove edges whose source or target node is not in the node set.

    Returns the cleaned graph_data dict and the number of pruned edges.
    """
    node_ids = {n["id"] for n in graph_data["nodes"]}
    links_key = "links" if "links" in graph_data else "edges"
    before = len(graph_data[links_key])
    graph_data[links_key] = [
        e for e in graph_data[links_key]
        if e["source"] in node_ids and e["target"] in node_ids
    ]
    return graph_data, before - len(graph_data[links_key])


def _cypher_escape(s: str) -> str:
    """Escape a string for safe embedding in a Cypher single-quoted literal.

    Handles all characters that could prematurely terminate the literal or
    inject control sequences:
      - `\\` and `'` (literal terminators)
      - newlines/CRs (would break the per-line statement framing)
      - NUL/control bytes (defensive — Neo4j errors on raw NULs)

    Also strips any leading/trailing whitespace that would let an attacker
    break the `;`-terminated statement boundary used by `cypher-shell`.
    Closing `}` and `)` are NOT special inside a single-quoted Cypher string,
    so escaping the quote and backslash correctly is sufficient (a `}` inside
    a properly-closed `'...'` literal is just a character) — but we previously
    missed `\\n` / `\\r` which DO let a payload break out of the statement
    line and inject a fresh MATCH/DELETE on the following line. See F-008.
    """
    # First normalise: drop NUL and other C0 control chars except tab.
    s = "".join(ch for ch in s if ch >= " " or ch == "\t")
    return (
        s.replace("\\", "\\\\")
         .replace("'", "\\'")
         .replace("\n", "\\n")
         .replace("\r", "\\r")
    )


# Restrict identifier-position values (labels and relationship types are NOT
# quoted in Cypher and so cannot be safely escaped — they must be allowlisted).
_CYPHER_IDENT_RE = re.compile(r"[^A-Za-z0-9_]")


def _cypher_label(raw: str, fallback: str) -> str:
    """Sanitise a value used in identifier position (node label / rel type).

    Cypher does not provide a way to escape `:Foo` label syntax, so we must
    strip everything except `[A-Za-z0-9_]` and require the result to start
    with a letter; otherwise we fall back to a safe constant.
    """
    cleaned = _CYPHER_IDENT_RE.sub("", raw or "")
    if not cleaned or not cleaned[0].isalpha():
        return fallback
    return cleaned


def to_cypher(G: nx.Graph, output_path: str) -> None:
    lines = ["// Neo4j Cypher import - generated by /graphify", ""]
    for node_id, data in G.nodes(data=True):
        label = _cypher_escape(data.get("label", node_id))
        node_id_esc = _cypher_escape(node_id)
        ftype = _cypher_label(
            (data.get("file_type", "unknown") or "unknown").capitalize(),
            "Entity",
        )
        lines.append(f"MERGE (n:{ftype} {{id: '{node_id_esc}', label: '{label}'}});")
    lines.append("")
    for u, v, data in G.edges(data=True):
        rel = _cypher_label(
            (data.get("relation", "RELATES_TO") or "RELATES_TO").upper(),
            "RELATES_TO",
        )
        conf = _cypher_escape(data.get("confidence", "EXTRACTED"))
        u_esc = _cypher_escape(u)
        v_esc = _cypher_escape(v)
        lines.append(
            f"MATCH (a {{id: '{u_esc}'}}), (b {{id: '{v_esc}'}}) "
            f"MERGE (a)-[:{rel} {{confidence: '{conf}'}}]->(b);"
        )
    with open(output_path, "w", encoding="utf-8") as f:  # nosec
        f.write("\n".join(lines))


def to_html(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    member_counts: dict[int, int] | None = None,
    node_limit: int | None = None,
) -> None:
    """Generate an interactive vis.js HTML visualization of the graph.

    Features: node size by degree, click-to-inspect panel, search box,
    community filter, physics clustering by community, confidence-styled edges.
    Raises ValueError if graph exceeds MAX_NODES_FOR_VIZ.

    If member_counts is provided (aggregated community view), node sizes are
    based on community member counts rather than graph degree.

    If node_limit is set and the graph exceeds it, automatically builds an
    aggregated community-level meta-graph instead of raising ValueError.
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
                return
            meta_communities = {cid: [str(cid)] for cid in communities}
            mc = {cid: len(members) for cid, members in communities.items()}
            # Remap hyperedges from semantic node IDs to community IDs
            raw_hyperedges = G.graph.get("hyperedges", [])
            if raw_hyperedges:
                remapped = []
                for he in raw_hyperedges:
                    he_members = he.get("nodes") or he.get("members") or []
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
            to_html(meta, meta_communities, output_path,
                    community_labels=community_labels, member_counts=mc)
            print(f"graph.html written (aggregated: {meta.number_of_nodes()} community nodes, {meta.number_of_edges()} cross-community edges)")
            print("Tip: run with --obsidian for full node-level detail.")
            return
        raise ValueError(
            f"Graph has {G.number_of_nodes()} nodes - too large for HTML viz "
            f"(limit: {limit}). Use --no-viz, raise GRAPHIFY_VIZ_NODE_LIMIT, "
            f"or reduce input size."
        )

    node_community = _node_community_map(communities)
    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1
    max_mc = (max(member_counts.values(), default=1) or 1) if member_counts else 1

    # Build nodes list for vis.js
    vis_nodes = []
    for node_id, data in G.nodes(data=True):
        cid = node_community.get(node_id, 0)
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
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
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "community": cid,
            "community_name": sanitize_label((community_labels or {}).get(cid, f"Community {cid}")),
            "source_file": sanitize_label(str(data.get("source_file") or "")),
            "source_location": sanitize_label(str(data.get("source_location", "") or "")),
            "file_type": data.get("file_type", ""),
            "degree": deg,
        })

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
            "relation": relation,
            "confidence": confidence,
            "weight": data.get("weight", 1.0),
        })

    # Build community legend data
    legend_data = []
    all_cids = set()
    for n in vis_nodes:
        if n["community"] is not None:
            all_cids.add(n["community"])
    for cid in sorted(all_cids):
        color = COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)]
        lbl = _html.escape(sanitize_label((community_labels or {}).get(cid, f"Community {cid}")))
        n = member_counts.get(cid, len(communities.get(cid, []))) if member_counts else len(communities.get(cid, []))
        legend_data.append({"cid": cid, "color": color, "label": lbl, "count": n})

    # Escape </script> sequences so embedded JSON cannot break out of the script tag
    def _js_safe(obj) -> str:
        return json.dumps(obj).replace("</", "<\\/")

    nodes_json = _js_safe(vis_nodes)
    edges_json = _js_safe(vis_edges)
    legend_json = _js_safe(legend_data)
    hyperedges_json = _js_safe(getattr(G, "graph", {}).get("hyperedges", []))
    title = _html.escape(sanitize_label(str(output_path)))
    stats = f"{G.number_of_nodes()} nodes &middot; {G.number_of_edges()} edges &middot; {len(communities)} communities"

    file_type_counts = Counter(n.get("file_type", "unknown") for n in vis_nodes)
    stats_data = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "files": len({n.get("source_file", "") for n in vis_nodes if n.get("source_file")}),
        "types": len(file_type_counts),
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>graphify — knowledge graph</title>
{_html_styles()}
</head>
<body>
<div id="app">

  <div id="loading-screen">
    <div class="logo">graphify</div>
    <div class="steps">
      <div class="step active"><span class="step-dot"></span> Loading graph data</div>
      <div class="step"><span class="step-dot"></span> Processing nodes & edges</div>
      <div class="step"><span class="step-dot"></span> Running physics simulation</div>
      <div class="step"><span class="step-dot"></span> Building visualization</div>
      <div class="step"><span class="step-dot"></span> Preparing UI components</div>
      <div class="step"><span class="step-dot"></span> Stabilizing layout</div>
      <div class="step"><span class="step-dot"></span> Animating entrance</div>
      <div class="step"><span class="step-dot"></span> Ready</div>
    </div>
    <div class="progress-bar"><div class="progress-fill"></div></div>
  </div>

  <div id="graph-container">
    <div id="toolbar">
      <button class="toolbar-btn" onclick="fitGraph()" title="Fit graph [F]">⊞ <span class="kbd">F</span></button>
      <button class="toolbar-btn" onclick="resetView()" title="Reset view [R]">⟲ <span class="kbd">R</span></button>
      <button class="toolbar-btn" onclick="toggleFullscreen()" title="Fullscreen [F11]">⛶ <span class="kbd">F11</span></button>
      <button class="toolbar-btn" onclick="exportPNG()" title="Export PNG [P]">⬇ <span class="kbd">P</span></button>
      <button class="toolbar-btn" onclick="document.getElementById('sidebar').classList.toggle('collapsed')" title="Toggle sidebar [B]">☰ <span class="kbd">B</span></button>
    </div>

    <div id="focus-mode-indicator">
      Focus mode
      <button class="btn" onclick="resetView()">Exit</button>
    </div>

    <div id="minimap"></div>

    <div id="timeline-bar">
      <button class="tl-btn" id="tl-play" title="Play/Pause">▶</button>
      <input type="range" id="timeline-slider" min="0" max="1" step="0.001" value="0">
      <span id="timeline-label">0%</span>
      <button class="tl-btn" onclick="hideTimeline()" title="Close">✕</button>
    </div>

    <div id="toast-container"></div>
  </div>

  <div id="sidebar">
    <div id="sidebar-header">
      <h2>Knowledge Graph</h2>
      <button id="sidebar-close" onclick="this.closest('#sidebar').classList.add('collapsed')">✕</button>
    </div>
    <div id="search-wrap">
      <span id="search-icon">⌕</span>
      <input id="search" type="text" placeholder="Search nodes..." autocomplete="off">
      <div id="search-results"></div>
    </div>
    <div id="info-panel">
      <h3>Node Info</h3>
      <div id="info-content"><span class="empty">Click a node to inspect it</span></div>
    </div>
    <div id="legend-wrap">
      <div id="legend-header">
        <h3>Communities</h3>
        <div id="legend-controls">
          <label><input type="checkbox" id="select-all-cb" checked onchange="toggleAllCommunities(!this.checked)">All</label>
        </div>
      </div>
      <div id="legend"></div>
    </div>
    <div id="stats">
      <div class="stat-item"><span class="stat-value" id="stat-nodes">0</span><span class="stat-label">Nodes</span></div>
      <div class="stat-item"><span class="stat-value" id="stat-edges">0</span><span class="stat-label">Edges</span></div>
      <div class="stat-item"><span class="stat-value" id="stat-communities">0</span><span class="stat-label">Communities</span></div>
      <div class="stat-item"><span class="stat-value" id="stat-files">0</span><span class="stat-label">Files</span></div>
      <div class="stat-item"><span class="stat-value" id="stat-types">0</span><span class="stat-label">Types</span></div>
    </div>
  </div>

  <div id="context-menu"></div>
</div>
{_html_script(nodes_json, edges_json, legend_json)}
{_hyperedge_script(hyperedges_json)}
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")  # nosec


# Keep backward-compatible alias - skill.md calls generate_html
generate_html = to_html


def _cap_filename(s: str, limit: int = 200) -> str:
    """Cap a filename stem to ``limit`` UTF-8 bytes so it stays under the 255-byte
    filesystem limit even after the ``.md`` extension and dedup suffix are added
    (#1094). The cap is on BYTES, not chars, because a label of multibyte
    characters (CJK, accented) can exceed 255 bytes well under 255 chars. When
    truncation happens, an 8-char hash of the full label is appended so two
    distinct labels sharing a long prefix produce distinct, deterministic
    filenames instead of colliding."""
    b = s.encode("utf-8")
    if len(b) <= limit:
        return s
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]  # nosec - not security
    keep = limit - 9  # "_" + 8 hex chars
    truncated = b[:keep].decode("utf-8", "ignore")  # "ignore" drops a split trailing char
    return f"{truncated}_{digest}"


def to_obsidian(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_dir: str,
    community_labels: dict[int, str] | None = None,
    cohesion: dict[int, float] | None = None,
) -> int:
    """Export graph as an Obsidian vault - one .md file per node with [[wikilinks]],
    plus one _COMMUNITY_name.md overview note per community (sorted to top by underscore prefix).

    Open the output directory as a vault in Obsidian to get an interactive
    graph view with community colors and full-text search over node metadata.

    Returns the number of node notes + community notes written.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    node_community = _node_community_map(communities)

    # Map node_id → safe filename so wikilinks stay consistent.
    # Deduplicate: if two nodes produce the same filename, append a numeric suffix.
    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        # Strip trailing .md/.mdx/.markdown so "CLAUDE.md" doesn't become "CLAUDE.md.md"
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
        # A stem of only punctuation (e.g. "@", "*", "#") survives the unsafe-char
        # strip above but is empty once a downstream tool re-slugs on word chars
        # (e.g. qmd's handelize() reduces "@" -> "" and raises, aborting the whole
        # `qmd update`). Require at least one word char; else fall back so we never
        # emit a "@.md"-style filename. (#1409)
        if not re.search(r"\w", cleaned, flags=re.UNICODE):
            return "unnamed"
        return _cap_filename(cleaned)

    node_filename: dict[str, str] = {}
    seen_names: dict[str, int] = {}
    for node_id, data in G.nodes(data=True):
        base = safe_name(data.get("label", node_id))
        if base in seen_names:
            seen_names[base] += 1
            node_filename[node_id] = f"{base}_{seen_names[base]}"
        else:
            seen_names[base] = 0
            node_filename[node_id] = base

    # Helper: compute dominant confidence for a node across all its edges
    def _dominant_confidence(node_id: str) -> str:
        confs = []
        for u, v, edata in G.edges(node_id, data=True):
            confs.append(edata.get("confidence", "EXTRACTED"))
        if not confs:
            return "EXTRACTED"
        return Counter(confs).most_common(1)[0][0]

    # Map file_type → graphify tag
    _FTYPE_TAG = {
        "code": "graphify/code",
        "document": "graphify/document",
        "paper": "graphify/paper",
        "image": "graphify/image",
    }

    # Write one .md file per node
    for node_id, data in G.nodes(data=True):
        label = data.get("label", node_id)
        cid = node_community.get(node_id)
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )

        # Build tags for this node
        ftype = data.get("file_type", "")
        ftype_tag = _FTYPE_TAG.get(ftype, f"graphify/{ftype}" if ftype else "graphify/document")
        dom_conf = _dominant_confidence(node_id)
        conf_tag = f"graphify/{dom_conf}"
        comm_tag = f"community/{_obsidian_tag(community_name)}"
        node_tags = [ftype_tag, conf_tag, comm_tag]

        lines: list[str] = []

        # YAML frontmatter - readable in Obsidian's properties panel.
        # All scalars pass through _yaml_str so a hostile source_file or
        # community label cannot break out and inject sibling keys (F-009).
        lines += [
            "---",
            f'source_file: "{_yaml_str(data.get("source_file", ""))}"',
            f'type: "{_yaml_str(ftype)}"',
            f'community: "{_yaml_str(community_name)}"',
        ]
        if data.get("source_location"):
            lines.append(f'location: "{_yaml_str(str(data["source_location"]))}"')
        # Add tags list to frontmatter
        lines.append("tags:")
        for tag in node_tags:
            lines.append(f"  - {tag}")
        lines += ["---", "", f"# {label}", ""]

        # Outgoing edges as wikilinks
        neighbors = list(G.neighbors(node_id))
        if neighbors:
            lines.append("## Connections")
            for neighbor in sorted(neighbors, key=lambda n: G.nodes[n].get("label", n)):
                edata = edge_data(G, node_id, neighbor)
                neighbor_label = node_filename[neighbor]
                relation = edata.get("relation", "")
                confidence = edata.get("confidence", "EXTRACTED")
                lines.append(f"- [[{neighbor_label}]] - `{relation}` [{confidence}]")
            lines.append("")

        # Inline tags at bottom of note body (for Obsidian tag panel)
        inline_tags = " ".join(f"#{t}" for t in node_tags)
        lines.append(inline_tags)

        fname = node_filename[node_id] + ".md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")  # nosec

    # Write one _COMMUNITY_name.md overview note per community
    # Build inter-community edge counts for "Connections to other communities"
    inter_community_edges: dict[int, dict[int, int]] = {}
    for cid in communities:
        inter_community_edges[cid] = {}
    for u, v in G.edges():
        cu = node_community.get(u)
        cv = node_community.get(v)
        if cu is not None and cv is not None and cu != cv:
            inter_community_edges.setdefault(cu, {})
            inter_community_edges.setdefault(cv, {})
            inter_community_edges[cu][cv] = inter_community_edges[cu].get(cv, 0) + 1
            inter_community_edges[cv][cu] = inter_community_edges[cv].get(cu, 0) + 1

    # Precompute per-node community reach (number of distinct communities a node connects to)
    def _community_reach(node_id: str) -> int:
        neighbor_cids = {
            node_community[nb]
            for nb in G.neighbors(node_id)
            if nb in node_community and node_community[nb] != node_community.get(node_id)
        }
        return len(neighbor_cids)

    community_notes_written = 0
    for cid, all_members in communities.items():
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        # A community's member list can contain ids with no backing node in G
        # (e.g. pruned nodes, stale community assignments from a prior run, or
        # synthesized/merge-artifact ids). Dereferencing those via G.nodes[n] or
        # node_filename[n] raises KeyError and aborts the whole vault export, so
        # skip dangling members rather than crashing (issue #1236).
        members = [m for m in all_members if m in G and m in node_filename]
        n_members = len(members)
        coh_value = cohesion.get(cid) if cohesion else None

        lines: list[str] = []

        # YAML frontmatter
        lines.append("---")
        lines.append("type: community")
        if coh_value is not None:
            lines.append(f"cohesion: {coh_value:.2f}")
        lines.append(f"members: {n_members}")
        lines.append("---")
        lines.append("")
        lines.append(f"# {community_name}")
        lines.append("")

        # Cohesion + member count summary
        if coh_value is not None:
            cohesion_desc = (
                "tightly connected" if coh_value >= 0.7
                else "moderately connected" if coh_value >= 0.4
                else "loosely connected"
            )
            lines.append(f"**Cohesion:** {coh_value:.2f} - {cohesion_desc}")
        lines.append(f"**Members:** {n_members} nodes")
        lines.append("")

        # Members section
        lines.append("## Members")
        for node_id in sorted(members, key=lambda n: G.nodes[n].get("label", n)):
            data = G.nodes[node_id]
            node_label = node_filename[node_id]
            ftype = data.get("file_type", "")
            source = data.get("source_file", "")
            entry = f"- [[{node_label}]]"
            if ftype:
                entry += f" - {ftype}"
            if source:
                entry += f" - {source}"
            lines.append(entry)
        lines.append("")

        # Dataview live query (improvement 2)
        comm_tag_name = _obsidian_tag(community_name)
        lines.append("## Live Query (requires Dataview plugin)")
        lines.append("")
        lines.append("```dataview")
        lines.append(f"TABLE source_file, type FROM #community/{comm_tag_name}")
        lines.append("SORT file.name ASC")
        lines.append("```")
        lines.append("")

        # Connections to other communities
        cross = inter_community_edges.get(cid, {})
        if cross:
            lines.append("## Connections to other communities")
            for other_cid, edge_count in sorted(cross.items(), key=lambda x: -x[1]):
                other_name = (
                    community_labels.get(other_cid, f"Community {other_cid}")
                    if community_labels and other_cid is not None
                    else f"Community {other_cid}"
                )
                other_safe = safe_name(other_name)
                lines.append(f"- {edge_count} edge{'s' if edge_count != 1 else ''} to [[_COMMUNITY_{other_safe}]]")
            lines.append("")

        # Top bridge nodes - highest degree nodes that connect to other communities
        bridge_nodes = [
            (node_id, G.degree(node_id), _community_reach(node_id))
            for node_id in members
            if _community_reach(node_id) > 0
        ]
        bridge_nodes.sort(key=lambda x: (-x[2], -x[1]))
        top_bridges = bridge_nodes[:5]
        if top_bridges:
            lines.append("## Top bridge nodes")
            for node_id, degree, reach in top_bridges:
                node_label = node_filename[node_id]
                lines.append(
                    f"- [[{node_label}]] - degree {degree}, connects to {reach} "
                    f"{'community' if reach == 1 else 'communities'}"
                )

        community_safe = safe_name(community_name)
        fname = f"_COMMUNITY_{community_safe}.md"
        (out / fname).write_text("\n".join(lines), encoding="utf-8")  # nosec
        community_notes_written += 1

    # Improvement 4: write .obsidian/graph.json to color nodes by community in graph view
    obsidian_dir = out / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    graph_config = {
        "colorGroups": [
            {
                "query": f"tag:#community/{label.replace(' ', '_')}",
                "color": {"a": 1, "rgb": int(COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)].lstrip('#'), 16)}
            }
            for cid, label in sorted((community_labels or {}).items())
        ]
    }
    (obsidian_dir / "graph.json").write_text(json.dumps(graph_config, indent=2), encoding="utf-8")  # nosec

    return G.number_of_nodes() + community_notes_written


def to_canvas(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    node_filenames: dict[str, str] | None = None,
) -> None:
    """Export graph as an Obsidian Canvas file - communities as groups, nodes as cards.

    Generates a structured layout: communities arranged in a grid, nodes within
    each community arranged in rows. Edges shown between connected nodes.
    Opens in Obsidian as an infinite canvas with community groupings visible.
    """
    # Obsidian canvas color codes (cycle through for communities)
    CANVAS_COLORS = ["1", "2", "3", "4", "5", "6"]  # red, orange, yellow, green, cyan, purple

    def safe_name(label: str) -> str:
        cleaned = re.sub(r'[\\/*?:"<>|#^[\]]', "", label.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")).strip()
        cleaned = re.sub(r"\.(md|mdx|qmd|markdown)$", "", cleaned, flags=re.IGNORECASE)
        # A stem of only punctuation (e.g. "@", "*", "#") survives the unsafe-char
        # strip above but is empty once a downstream tool re-slugs on word chars
        # (e.g. qmd's handelize() reduces "@" -> "" and raises, aborting the whole
        # `qmd update`). Require at least one word char; else fall back so we never
        # emit a "@.md"-style filename. (#1409)
        if not re.search(r"\w", cleaned, flags=re.UNICODE):
            return "unnamed"
        return _cap_filename(cleaned)

    # Build node_filenames if not provided (same dedup logic as to_obsidian)
    if node_filenames is None:
        node_filenames = {}
        seen_names: dict[str, int] = {}
        for node_id, data in G.nodes(data=True):
            base = safe_name(data.get("label", node_id))
            if base in seen_names:
                seen_names[base] += 1
                node_filenames[node_id] = f"{base}_{seen_names[base]}"
            else:
                seen_names[base] = 0
                node_filenames[node_id] = base

    # Fallback: with no community data (e.g. --no-cluster builds or a missing
    # analysis sidecar) the grid below produces nothing and the canvas is written
    # as an empty 32-byte shell on an otherwise populated graph. Emit every node
    # into one synthetic community so the canvas always reflects the graph (#1324).
    if not communities and G.number_of_nodes() > 0:
        communities = {0: [str(n) for n in G.nodes()]}

    num_communities = len(communities)
    cols = math.ceil(math.sqrt(num_communities)) if num_communities > 0 else 1
    rows = math.ceil(num_communities / cols) if num_communities > 0 else 1

    canvas_nodes: list[dict] = []
    canvas_edges: list[dict] = []

    # Lay out communities in a grid
    gap = 80
    group_x_offsets: list[int] = []
    group_y_offsets: list[int] = []

    # Precompute group sizes so we can calculate offsets
    sorted_cids = sorted(communities.keys())
    group_sizes: dict[int, tuple[int, int]] = {}
    for cid in sorted_cids:
        members = communities[cid]
        n = len(members)
        w = max(600, 220 * math.ceil(math.sqrt(n)) if n > 0 else 600)
        h = max(400, 100 * math.ceil(n / 3) + 120 if n > 0 else 400)
        group_sizes[cid] = (w, h)

    # Compute cumulative row heights and col widths for grid placement
    # Each grid cell uses the max width/height in its col/row
    col_widths: list[int] = []
    row_heights: list[int] = []
    for col_idx in range(cols):
        max_w = 0
        for row_idx in range(rows):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                w, _ = group_sizes[cid]
                max_w = max(max_w, w)
        col_widths.append(max_w)

    for row_idx in range(rows):
        max_h = 0
        for col_idx in range(cols):
            linear = row_idx * cols + col_idx
            if linear < len(sorted_cids):
                cid = sorted_cids[linear]
                _, h = group_sizes[cid]
                max_h = max(max_h, h)
        row_heights.append(max_h)

    # Map from cid → (group_x, group_y, group_w, group_h)
    group_layout: dict[int, tuple[int, int, int, int]] = {}
    for idx, cid in enumerate(sorted_cids):
        col_idx = idx % cols
        row_idx = idx // cols
        gx = sum(col_widths[:col_idx]) + col_idx * gap
        gy = sum(row_heights[:row_idx]) + row_idx * gap
        gw, gh = group_sizes[cid]
        group_layout[cid] = (gx, gy, gw, gh)

    # Build set of all node_ids in canvas for edge filtering
    all_canvas_nodes: set[str] = set()
    for members in communities.values():
        all_canvas_nodes.update(members)

    # Generate group and node canvas entries
    for idx, cid in enumerate(sorted_cids):
        members = communities[cid]
        community_name = (
            community_labels.get(cid, f"Community {cid}")
            if community_labels and cid is not None
            else f"Community {cid}"
        )
        gx, gy, gw, gh = group_layout[cid]
        canvas_color = CANVAS_COLORS[idx % len(CANVAS_COLORS)]

        # Group node
        canvas_nodes.append({
            "id": f"g{cid}",
            "type": "group",
            "label": community_name,
            "x": gx,
            "y": gy,
            "width": gw,
            "height": gh,
            "color": canvas_color,
        })

        # Node cards inside the group - rows of 3
        sorted_members = sorted(members, key=lambda n: G.nodes[n].get("label", n))
        for m_idx, node_id in enumerate(sorted_members):
            col = m_idx % 3
            row = m_idx // 3
            nx_x = gx + 20 + col * (180 + 20)
            nx_y = gy + 80 + row * (60 + 20)
            fname = node_filenames.get(node_id, safe_name(G.nodes[node_id].get("label", node_id)))
            canvas_nodes.append({
                "id": f"n_{node_id}",
                "type": "file",
                "file": f"{fname}.md",
                "x": nx_x,
                "y": nx_y,
                "width": 180,
                "height": 60,
            })

    # Generate edges - only between nodes both in canvas, cap at 200 highest-weight
    all_edges_weighted: list[tuple[float, str, str, str]] = []
    for u, v, edata in G.edges(data=True):
        if u in all_canvas_nodes and v in all_canvas_nodes:
            weight = edata.get("weight", 1.0)
            relation = edata.get("relation", "")
            conf = edata.get("confidence", "EXTRACTED")
            label = f"{relation} [{conf}]" if relation else f"[{conf}]"
            all_edges_weighted.append((weight, u, v, label))

    all_edges_weighted.sort(key=lambda x: -x[0])
    for weight, u, v, label in all_edges_weighted[:200]:
        canvas_edges.append({
            "id": f"e_{u}_{v}",
            "fromNode": f"n_{u}",
            "toNode": f"n_{v}",
            "label": label,
        })

    canvas_data = {"nodes": canvas_nodes, "edges": canvas_edges}
    Path(output_path).write_text(json.dumps(canvas_data, indent=2), encoding="utf-8")  # nosec


def push_to_neo4j(
    G: nx.Graph,
    uri: str,
    user: str,
    password: str,
    communities: dict[int, list[str]] | None = None,
) -> dict[str, int]:
    """Push graph directly to a running Neo4j instance via the Python driver.

    Requires: pip install neo4j

    Uses MERGE so re-running is safe - nodes and edges are upserted, not duplicated.
    Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from neo4j import GraphDatabase
    except ImportError as e:
        raise ImportError(
            "neo4j driver not installed. Run: pip install neo4j"
        ) from e

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a Neo4j node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    driver = GraphDatabase.driver(uri, auth=(user, password))
    nodes_pushed = 0
    edges_pushed = 0

    with driver.session() as session:
        for node_id, data in G.nodes(data=True):
            props = {
                k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
            }
            props["id"] = node_id
            cid = node_community.get(node_id)
            if cid is not None:
                props["community"] = cid
            ftype = _safe_label(data.get("file_type", "Entity").capitalize())
            session.run(
                f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
                id=node_id,
                props=props,
            )
            nodes_pushed += 1

        for u, v, data in G.edges(data=True):
            rel = _safe_rel(data.get("relation", "RELATED_TO"))
            props = {
                k: v for k, v in data.items()
                if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
            }
            session.run(
                f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
                f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
                src=u,
                tgt=v,
                props=props,
            )
            edges_pushed += 1

    driver.close()
    return {"nodes": nodes_pushed, "edges": edges_pushed}


def push_to_falkordb(
    G: nx.Graph,
    uri: str,
    user: str | None = None,
    password: str | None = None,
    communities: dict[int, list[str]] | None = None,
    graph_name: str = "graphify",
) -> dict[str, int]:
    """Push graph directly to a running FalkorDB instance via the Python SDK.

    Requires: pip install falkordb

    FalkorDB is OpenCypher-compatible, so the MERGE/SET upsert queries are
    identical to push_to_neo4j. Differences from the Neo4j path:
      - connects with FalkorDB(host, port, username, password) instead of a bolt
        driver; only the host/port are read from the URI, so the scheme is
        informational - "falkordb://localhost:6379", "redis://localhost:6379"
        and a bare "localhost:6379" are all equivalent (default port 6379).
      - a named graph is selected via db.select_graph(graph_name) (default
        "graphify"); FalkorDB keys each graph by name in the same instance.
      - queries run via graph.query(cypher, params) - there is no session object.
      - auth is optional (FalkorDB runs without credentials by default), so user
        and password may be None.
      - no APOC: the Neo4j path does not use APOC either, so nothing to port.

    Uses MERGE so re-running is safe - nodes and edges are upserted, not
    duplicated. Returns a dict with counts of nodes and edges pushed.
    """
    try:
        from falkordb import FalkorDB
    except ImportError as e:
        raise ImportError(
            "falkordb SDK not installed. Run: pip install falkordb"
        ) from e

    from urllib.parse import urlparse

    node_community = _node_community_map(communities) if communities else {}

    def _safe_rel(relation: str) -> str:
        return re.sub(r"[^A-Z0-9_]", "_", relation.upper().replace(" ", "_").replace("-", "_")) or "RELATED_TO"

    def _safe_label(label: str) -> str:
        """Sanitize a FalkorDB node label to prevent Cypher injection."""
        sanitized = re.sub(r"[^A-Za-z0-9_]", "", label)
        return sanitized if sanitized else "Entity"

    parsed = urlparse(uri if "://" in uri else f"redis://{uri}")
    # FalkorDB auth is optional. Only send credentials when a password is
    # provided; otherwise connect anonymously and ignore any bolt-style default
    # username (e.g. Neo4j's "neo4j"), which FalkorDB rejects as an unknown ACL
    # user. Credentials embedded in the URI take precedence over the args.
    connect_user = parsed.username or (user if password else None)
    connect_password = parsed.password or (password or None)
    db = FalkorDB(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        username=connect_user,
        password=connect_password,
    )
    graph = db.select_graph(graph_name)
    nodes_pushed = 0
    edges_pushed = 0

    for node_id, data in G.nodes(data=True):
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        props["id"] = node_id
        cid = node_community.get(node_id)
        if cid is not None:
            props["community"] = cid
        ftype = _safe_label(data.get("file_type", "Entity").capitalize())
        graph.query(
            f"MERGE (n:{ftype} {{id: $id}}) SET n += $props",
            {"id": node_id, "props": props},
        )
        nodes_pushed += 1

    for u, v, data in G.edges(data=True):
        rel = _safe_rel(data.get("relation", "RELATED_TO"))
        props = {
            k: v for k, v in data.items()
            if isinstance(v, (str, int, float, bool)) and not k.startswith("_")
        }
        graph.query(
            f"MATCH (a {{id: $src}}), (b {{id: $tgt}}) "
            f"MERGE (a)-[r:{rel}]->(b) SET r += $props",
            {"src": u, "tgt": v, "props": props},
        )
        edges_pushed += 1

    return {"nodes": nodes_pushed, "edges": edges_pushed}


def to_graphml(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
) -> None:
    """Export graph as GraphML - opens in Gephi, yEd, and any GraphML-compatible tool.

    Community IDs are written as a node attribute so Gephi can colour by community.
    Edge confidence (EXTRACTED/INFERRED/AMBIGUOUS) is preserved as an edge attribute.
    """
    H = G.copy()
    node_community = _node_community_map(communities)
    for node_id in H.nodes():
        H.nodes[node_id]["community"] = node_community.get(node_id, -1)
    # Drop internal markers (e.g. the AST-provenance "_origin" tag, #1116, and
    # the "_src"/"_tgt" direction markers) — they are persistence/runtime details,
    # not graph data, and should not leak into the exported file.
    for _, attrs in H.nodes(data=True):
        for k in [k for k in attrs if k.startswith("_")]:
            del attrs[k]
    for _, _, attrs in H.edges(data=True):
        for k in [k for k in attrs if k.startswith("_")]:
            del attrs[k]
    nx.write_graphml(H, output_path)


def to_svg(
    G: nx.Graph,
    communities: dict[int, list[str]],
    output_path: str,
    community_labels: dict[int, str] | None = None,
    figsize: tuple[int, int] = (20, 14),
) -> None:
    """Export graph as an SVG file using matplotlib + spring layout.

    Lightweight and embeddable - works in Obsidian notes, Notion, GitHub READMEs,
    and any markdown renderer. No JavaScript required.

    Node size scales with degree. Community colors match the HTML output.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError as e:
        raise ImportError("matplotlib not installed. Run: pip install matplotlib") from e

    node_community = _node_community_map(communities)

    fig, ax = plt.subplots(figsize=figsize, facecolor="#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.axis("off")

    pos = nx.spring_layout(G, seed=42, k=2.0 / (G.number_of_nodes() ** 0.5 + 1))

    degree = dict(G.degree())
    max_deg = max(degree.values(), default=1) or 1

    node_colors = [COMMUNITY_COLORS[node_community.get(n, 0) % len(COMMUNITY_COLORS)] for n in G.nodes()]
    node_sizes = [300 + 1200 * (degree.get(n, 1) / max_deg) for n in G.nodes()]

    # Draw edges - dashed for non-EXTRACTED
    for u, v, data in G.edges(data=True):
        conf = data.get("confidence", "EXTRACTED")
        style = "solid" if conf == "EXTRACTED" else "dashed"
        alpha = 0.6 if conf == "EXTRACTED" else 0.3
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        ax.plot([x0, x1], [y0, y1], color="#aaaaaa", linewidth=0.8,
                linestyle=style, alpha=alpha, zorder=1)

    nx.draw_networkx_nodes(G, pos, ax=ax, node_color=node_colors,
                           node_size=node_sizes, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax,
                            labels={n: G.nodes[n].get("label", n) for n in G.nodes()},
                            font_size=7, font_color="white")

    # Legend
    if community_labels:
        patches = [
            mpatches.Patch(
                color=COMMUNITY_COLORS[cid % len(COMMUNITY_COLORS)],
                label=f"{label} ({len(communities.get(cid, []))})",
            )
            for cid, label in sorted(community_labels.items())
        ]
        ax.legend(handles=patches, loc="upper left", framealpha=0.7,
                  facecolor="#2a2a4e", labelcolor="white", fontsize=8)

    plt.tight_layout()
    plt.savefig(output_path, format="svg", bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
