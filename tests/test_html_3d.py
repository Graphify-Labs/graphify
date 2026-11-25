"""3D graph.html viewer (default renderer) and its per-node descriptions."""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import networkx as nx
import pytest

from graphify.exporters.html import _FORCE_GRAPH_3D_SRI, _viz_mode, to_html
from graphify.exporters.node_info import build_node_info


def _graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="a.py", file_type="code")
    G.add_node("b", label="Beta", source_file="b.py", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED", _src="a", _tgt="b")
    return G


def _render(tmp_path, G=None, **kw) -> str:
    out = tmp_path / "graph.html"
    G = G if G is not None else _graph()
    comms = kw.pop("communities", {0: list(G.nodes)})
    to_html(G, comms, str(out), community_labels=kw.pop("community_labels", {0: "Core"}), **kw)
    return out.read_text(encoding="utf-8")


def _node_info(html: str) -> dict:
    m = re.search(r"const NODE_INFO = (\{.*?\});\n", html, re.DOTALL)
    assert m, "NODE_INFO not found"
    return json.loads(m.group(1))


# ---- renderer selection -----------------------------------------------------

def test_default_is_3d_with_pinned_sri(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_VIZ_MODE", raising=False)
    html = _render(tmp_path)
    assert "https://unpkg.com/3d-force-graph@1.73.4/dist/3d-force-graph.min.js" in html
    assert f'integrity="{_FORCE_GRAPH_3D_SRI}"' in html
    assert 'crossorigin="anonymous"' in html
    assert "vis-network" not in html
    assert "ForceGraph3D" in html
    assert '<div id="node-card"' in html
    # Same embedded data contract as the 2D page.
    for name in ("RAW_NODES", "RAW_EDGES", "LEGEND", "HYPEREDGES", "NODE_INFO"):
        assert f"const {name} = " in html


def test_env_selects_2d_and_unknown_values_fall_back_to_3d(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_VIZ_MODE", "2d")
    assert "vis-network@9.1.6" in _render(tmp_path)
    monkeypatch.setenv("GRAPHIFY_VIZ_MODE", "bogus")
    assert _viz_mode(None) == "3d"
    # An explicit argument beats the environment.
    monkeypatch.setenv("GRAPHIFY_VIZ_MODE", "2d")
    assert "3d-force-graph" in _render(tmp_path, mode="3d")


def test_3d_output_is_deterministic(tmp_path):
    assert _render(tmp_path) == _render(tmp_path)


def test_aggregated_view_renders_in_3d(tmp_path):
    G = nx.Graph()
    for i in range(6):
        G.add_node(f"n{i}", label=f"n{i}", file_type="code", source_file="x.py")
    G.add_edge("n0", "n3", relation="calls", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    assert to_html(G, {0: ["n0", "n1", "n2"], 1: ["n3", "n4", "n5"]}, str(out),
                   community_labels={0: "A", 1: "B"}, node_limit=2, mode="3d")
    html = out.read_text(encoding="utf-8")
    assert "3d-force-graph" in html
    assert _node_info(html) == {}  # community meta-nodes have no source


# ---- node descriptions --------------------------------------------------------

def _project(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "mod.py").write_text(
        '"""Module docstring here."""\n'
        "\n"
        "def helper(\n"
        "    x: int,\n"
        "    y: int,\n"
        ") -> int:\n"
        '    """Add two numbers.\n'
        "\n"
        "    Longer text that is not the summary.\n"
        '    """\n'
        "    return x + y\n"
        "\n"
        "def bare():\n"
        "    pass\n",
        encoding="utf-8",
    )
    (root / "src" / "lib.rs").write_text(
        "//! Crate header.\n"
        "\n"
        "/// Fetches a page.\n"
        "/// Retries twice.\n"
        "#[inline]\n"
        "pub fn fetch(url: &str) -> Result<String, String> {\n"
        "    todo!()\n"
        "}\n"
        'pub const BASE: &str = "https://example.org"; // the API host\n',
        encoding="utf-8",
    )
    (root / "src" / "app.ts").write_text(
        "/**\n"
        " * Renders the widget.\n"
        " * @param el target\n"
        " */\n"
        "export function render(el: HTMLElement): void {\n"
        "}\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text(
        "# Project\n\nIntro paragraph.\n\n## Setup\n\nRun the installer.\nThen restart.\n",
        encoding="utf-8",
    )
    (root / "run.sh").write_text("#!/bin/sh\n# Starts the server.\nexec ./server\n", encoding="utf-8")
    return root


def _described(tmp_path):
    root = _project(tmp_path)
    G = nx.Graph()
    G.add_node("py_mod", label="mod.py", source_file="src/mod.py", source_location="L1", file_type="code")
    G.add_node("py_helper", label="helper()", source_file="src/mod.py", source_location="L3", file_type="code")
    G.add_node("py_bare", label="bare()", source_file="src/mod.py", source_location="L13", file_type="code")
    G.add_node("rs_lib", label="src/lib.rs", source_file="src/lib.rs", source_location="L1", file_type="code")
    # Drifted line number: the declaration is found by name nearby.
    G.add_node("rs_fetch", label="fetch()", source_file="src/lib.rs", source_location="L2", file_type="code")
    G.add_node("rs_base", label="BASE", source_file="src/lib.rs", source_location="L9", file_type="code")
    G.add_node("ts_render", label="render()", source_file="src/app.ts", source_location="L5", file_type="code")
    G.add_node("md_setup", label="Setup", source_file="README.md", source_location="L5",
               file_type="document", node_kind="heading")
    G.add_node("sh", label="run.sh", source_file="run.sh", source_location="L1", file_type="code")
    G.add_node("ext", label="Vec", file_type="code", type="external")
    G.add_node("concept", label="Idea", file_type="concept", rationale="Because reasons.")
    return root, G, build_node_info(G, root)


def test_python_docstrings_and_multiline_signature(tmp_path):
    _, _, info = _described(tmp_path)
    assert info["py_mod"] == {"k": "Python module", "d": "Module docstring here.", "l": "src/mod.py:1"}
    h = info["py_helper"]
    assert h["k"] == "Function"
    assert h["s"] == "def helper(x: int, y: int) -> int"
    assert h["d"] == "Add two numbers."
    assert "d" not in info["py_bare"]


def test_rust_doc_comments_header_and_trailing_comment(tmp_path):
    _, _, info = _described(tmp_path)
    assert info["rs_lib"]["k"] == "Rust source file"
    assert info["rs_lib"]["d"] == "Crate header."
    f = info["rs_fetch"]
    assert f["k"] == "Function"
    assert f["s"] == "pub fn fetch(url: &str) -> Result<String, String>"
    assert f["d"] == "Fetches a page. Retries twice."
    # `//` inside a string literal is not a comment; the trailing one is.
    assert info["rs_base"]["s"] == 'pub const BASE: &str = "https://example.org"'
    assert info["rs_base"]["d"] == "the API host"


def test_jsdoc_markdown_shell_and_non_source_nodes(tmp_path):
    _, _, info = _described(tmp_path)
    assert info["ts_render"]["d"] == "Renders the widget."  # stops at @param
    assert info["ts_render"]["k"] == "Function"
    assert info["md_setup"] == {"k": "Document section", "s": "Setup",
                                "d": "Run the installer. Then restart.", "l": "README.md:5"}
    assert info["sh"]["k"] == "Shell script"
    assert info["sh"]["d"] == "Starts the server."
    assert info["ext"] == {"k": "External item (library)"}
    assert info["concept"] == {"k": "Concept", "d": "Because reasons."}


def test_files_outside_the_project_root_are_not_read(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    secret = tmp_path / "secret.py"
    secret.write_text("# TOP SECRET\ndef leak():\n    pass\n", encoding="utf-8")
    G = nx.Graph()
    G.add_node("rel", label="leak()", source_file="../secret.py", source_location="L2", file_type="code")
    G.add_node("abs", label="leak()", source_file=str(secret), source_location="L2", file_type="code")
    info = build_node_info(G, root)
    for nid in ("rel", "abs"):
        assert "d" not in info[nid] and "s" not in info[nid]


def test_to_html_embeds_descriptions_from_source_root(tmp_path):
    root, G, _ = _described(tmp_path)
    html = _render(tmp_path, G, source_root=root)
    info = _node_info(html)
    assert info["py_helper"]["d"] == "Add two numbers."


def test_hostile_source_comment_cannot_break_out_of_script(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "x.py").write_text(
        '# </script><script>alert(1)</script> <!--\ndef f():\n    pass\n', encoding="utf-8")
    G = nx.Graph()
    G.add_node("f", label="f()", source_file="x.py", source_location="L2", file_type="code")
    html = _render(tmp_path, G, source_root=root)
    assert "alert(1)</script>" not in html
    assert "<!--" not in html
    assert html.count("<script") == html.count("</script")
    assert "<script>alert" in _node_info(html)["f"]["d"]  # round-trips as data


# ---- runtime: run the viewer script in Node with a mocked DOM -----------------

_DOM = r"""
const mk = (id) => ({ id, innerHTML: '', textContent: '', style: {}, children: [], listeners: {},
  dataset: {}, scrollTop: 0, offsetWidth: 200, offsetHeight: 100, clientWidth: 800, clientHeight: 600,
  classList: { s: new Set(), add(...c) { c.forEach(x => this.s.add(x)); }, remove(...c) { c.forEach(x => this.s.delete(x)); },
               toggle(c, on) { (on ?? !this.s.has(c)) ? this.s.add(c) : this.s.delete(c); }, contains(c) { return this.s.has(c); } },
  appendChild(c) { this.children.push(c); }, prepend() {}, setAttribute() {},
  addEventListener(t, f) { this.listeners[t] = f; }, closest() { return null; } });
const els = {};
const document = { body: mk('body'), listeners: {},
  documentElement: { attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; } },
  getElementById: id => els[id] || (els[id] = mk(id)), createElement: () => mk(null),
  addEventListener(t, f) { this.listeners[t] = f; }, querySelectorAll: () => [] };
const window = { addEventListener() {}, innerWidth: 1280, innerHeight: 800 };
const getComputedStyle = () => ({ getPropertyValue: () => '' });
const requestAnimationFrame = () => 1, cancelAnimationFrame = () => {};
class Event { constructor(t) { this.type = t; } }
"""


def _run_viewer(html: str, epilogue: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not available")
    body = html.split("<body>", 1)[1]
    scripts = re.findall(r"<script>(.*?)</script>", body, re.DOTALL)
    assert len(scripts) == 2, "expected a data script and a viewer script"
    src = _DOM + "\n".join(scripts) + "\n" + epilogue
    proc = subprocess.run([node, "-e", src], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_runtime_card_shows_kind_description_signature_and_relations(tmp_path):
    root, G, _ = _described(tmp_path)
    G.add_edge("py_helper", "py_bare", relation="calls", confidence="EXTRACTED", _src="py_helper", _tgt="py_bare")
    G.add_edge("py_mod", "py_helper", relation="contains", confidence="EXTRACTED", _src="py_mod", _tgt="py_helper")
    html = _render(tmp_path, G, source_root=root)
    out = _run_viewer(html, """
showInfo('py_helper', true); const full = document.getElementById('info-content').innerHTML;
showInfo('py_helper', false); const hover = document.getElementById('info-content').innerHTML;
showInfo('py_bare', true); const auto = document.getElementById('info-content').innerHTML;
console.log(JSON.stringify({ full, hover, auto, viewerError: document.getElementById('viewer-error').style.display }));
""")
    full = out["full"]
    assert '<b>helper()</b> <span class="kind-chip">Function</span>' in full
    assert '<div class="desc">Add two numbers.</div>' in full
    assert '<pre class="sig">def helper(x: int, y: int) -&gt; int</pre>' in full
    assert 'src/mod.py:3' in full
    assert '<div class="rel-head">Defined in (1)</div>' in full
    assert '<div class="rel-head">Calls (1)</div>' in full
    assert 'data-nid="py_bare"' in full
    assert "card-close" in full and "card-close" not in out["hover"]
    assert "click for details" in out["hover"]
    # No comment in the source: plain-language summary built from the graph.
    assert 'class="desc auto"' in out["auto"]
    assert "Called from helper()." in out["auto"]
    # Without the CDN library (no ForceGraph3D) the page explains instead of crashing.
    assert out["viewerError"] == "flex"


def test_runtime_escapes_labels_and_does_not_double_escape_legend(tmp_path):
    G = nx.Graph()
    G.add_node("x\"y", label='<img src=x onerror=alert(1)>', file_type="code", source_file="q.py")
    html = _render(tmp_path, G, community_labels={0: "A & B"})
    out = _run_viewer(html, """
showInfo('x"y', true);
console.log(JSON.stringify({ card: document.getElementById('info-content').innerHTML,
  legend: document.getElementById('legend').children.map(c => c.innerHTML) }));
""")
    assert "<img" not in out["card"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in out["card"]
    assert '<span class="legend-label">A &amp; B</span>' in out["legend"][0]
    assert "&amp;amp;" not in out["legend"][0]


def test_runtime_learning_overlay_lesson_on_card(tmp_path):
    G = _graph()
    overlay = {"a": {"status": "preferred", "uses": 3, "score": 2.4, "stale": False}}
    html = _render(tmp_path, G, learning_overlay=overlay)
    out = _run_viewer(html, """
showInfo('a', true);
console.log(JSON.stringify(document.getElementById('info-content').innerHTML));
""")
    assert 'class="lesson" style="border-left-color:#22c55e"' in out
    assert "Lesson: preferred source (3 useful, score=2.4)" in out
