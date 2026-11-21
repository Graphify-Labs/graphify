"""graph.html and GRAPH_TREE.html light/dark/system theme toggle (#3894, #5358)."""
import json
import re

import networkx as nx

from graphify import html_theme, tree_html
from graphify.export import to_html
from graphify.tree_html import write_tree_html

# Page-chrome colors graph.html hardcoded before #3894. The dark defaults must
# keep these exact values so the out-of-the-box look does not change.
DARK_DEFAULTS = {
    "--bg": "#0f0f1a",
    "--panel": "#1a1a2e",
    "--border": "#2a2a4e",
    "--input-border": "#3a3a5e",
    "--text": "#e0e0e0",
    "--text-2": "#aaa",
    "--text-3": "#ccc",
    "--muted": "#555",
    "--count": "#666",
    "--neighbor-border": "#333",
    "--node-label": "#ffffff",
}


def _render(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="a.py", file_type="code")
    G.add_node("b", label="Beta", source_file="b.py", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    to_html(G, {0: ["a", "b"]}, str(out), community_labels={0: "Core"})
    return out.read_text(encoding="utf-8")


def _block(html, selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", html)
    assert m, f"missing CSS block {selector}"
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1)))


def _blocks(html, selector):
    """Merge every matching CSS block (a view may split its variables)."""
    merged = {}
    for m in re.finditer(re.escape(selector) + r"\s*\{([^}]*)\}", html):
        merged.update(dict(re.findall(r"(--[\w-]+):\s*([^;]+);", m.group(1))))
    assert merged, f"missing CSS block {selector}"
    return merged


def _luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _expected_tree_palette_vars():
    index = tree_html.tree_palette_index()
    names = [index["root"], index["phaseDefault"], *index["dirs"], *index["levels"].values()]
    return {
        f"{name}-{kind}"
        for name in names
        for kind in ("fill", "stroke", "collapsed")
    }


def test_dark_defaults_match_previous_hardcoded_colors(tmp_path):
    root = _block(_render(tmp_path), ":root")
    for name, value in DARK_DEFAULTS.items():
        assert root.get(name) == value, name


def test_light_override_defines_every_variable(tmp_path):
    light = _block(_render(tmp_path), '[data-theme="light"]')
    assert set(light) == set(DARK_DEFAULTS)
    assert light["--bg"] != DARK_DEFAULTS["--bg"]


def test_chrome_styles_use_variables_not_hardcoded_dark_colors(tmp_path):
    html = _render(tmp_path)
    styles = html.split("</style>")[0].split("[data-theme=\"light\"]")[1].split("}", 1)[1]
    for color in ("#0f0f1a", "#1a1a2e", "#2a2a4e", "#3a3a5e", "#e0e0e0"):
        assert color not in styles, color
    assert "background: var(--bg)" in styles
    assert "background: var(--panel)" in styles


def test_toggle_control_and_persistence(tmp_path):
    html = _render(tmp_path)
    for choice in ("light", "dark", "system"):
        assert f'data-theme-choice="{choice}"' in html
    assert "graphify-theme" in html
    assert "try { pref = localStorage.getItem('graphify-theme'); } catch (e) {}" in html
    assert "try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}" in html
    assert "prefers-color-scheme: light" in html
    assert "addEventListener('change'" in html


def test_theme_applied_in_head_before_first_paint(tmp_path):
    html = _render(tmp_path)
    head = html.split("</head>")[0]
    assert "setAttribute('data-theme'" in head
    # Unsaved preference falls back to dark, not the OS setting.
    assert ": 'dark';" in head


def test_output_is_deterministic(tmp_path):
    a = _render(tmp_path)
    b = _render(tmp_path)
    assert a == b


def _render_tree(tmp_path):
    graph = {
        "nodes": [
            {"id": "a", "label": "Alpha", "source_file": "pkg/a.py"},
            {"id": "b", "label": "Beta", "source_file": "pkg/b.py"},
        ],
        "links": [{"source": "a", "target": "b", "relation": "calls"}],
    }
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    out = tmp_path / "GRAPH_TREE.html"
    write_tree_html(graph_path, out)
    return out.read_text(encoding="utf-8")


def test_tree_dark_defaults_match_shared_palette(tmp_path):
    root = _blocks(_render_tree(tmp_path), ":root")
    for name, value in DARK_DEFAULTS.items():
        assert root.get(name) == value, name


def test_tree_light_override_defines_every_variable(tmp_path):
    light = _blocks(_render_tree(tmp_path), '[data-theme="light"]')
    for name, value in DARK_DEFAULTS.items():
        assert name in light, name
    assert light["--bg"] != DARK_DEFAULTS["--bg"]


def test_tree_chrome_styles_use_variables(tmp_path):
    html = _render_tree(tmp_path)
    styles = html.split("</style>")[0]
    assert "background: var(--bg)" in styles
    assert "background: var(--panel)" in styles
    assert "color: var(--text)" in styles


def test_tree_toggle_control_and_persistence(tmp_path):
    html = _render_tree(tmp_path)
    for choice in ("light", "dark", "system"):
        assert f'data-theme-choice="{choice}"' in html
    assert "graphify-theme" in html
    assert "try { pref = localStorage.getItem('graphify-theme'); } catch (e) {}" in html
    assert "try { localStorage.setItem(THEME_KEY, pref); } catch (e) {}" in html
    assert "prefers-color-scheme: light" in html
    assert "addEventListener('change'" in html


def test_tree_theme_applied_in_head_before_first_paint(tmp_path):
    html = _render_tree(tmp_path)
    head = html.split("</head>")[0]
    assert "setAttribute('data-theme'" in head
    assert ": 'dark';" in head


def test_tree_font_stack_matches_graph_html(tmp_path):
    html = _render_tree(tmp_path)
    assert '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' in html


def test_tree_output_is_deterministic(tmp_path):
    a = _render_tree(tmp_path)
    b = _render_tree(tmp_path)
    assert a == b


def test_both_views_are_rendered_from_the_shared_module(tmp_path):
    graph_html = _render(tmp_path)
    tree_html = _render_tree(tmp_path)
    for asset in (
        html_theme.THEME_CSS_VARS,
        html_theme.THEME_INIT_SCRIPT,
        html_theme.THEME_TOGGLE_CSS,
        html_theme.THEME_TOGGLE_HTML,
        html_theme.THEME_TOGGLE_JS,
    ):
        assert asset in graph_html
        assert asset in tree_html


def test_both_views_share_identical_chrome_palettes(tmp_path):
    graph_dark = _block(_render(tmp_path), ":root")
    tree_dark = _blocks(_render_tree(tmp_path), ":root")
    graph_light = _block(_render(tmp_path), '[data-theme="light"]')
    tree_light = _blocks(_render_tree(tmp_path), '[data-theme="light"]')
    for name in DARK_DEFAULTS:
        assert tree_dark[name] == graph_dark[name], name
        assert tree_light[name] == graph_light[name], name
    # The tree owns extra variables; it must not redefine the shared ones.
    assert {n for n in tree_dark if not n.startswith("--tree-")} == set(DARK_DEFAULTS)


def test_tree_palette_is_defined_in_both_themes(tmp_path):
    html = _render_tree(tmp_path)
    dark = _blocks(html, ":root")
    light = _blocks(html, '[data-theme="light"]')
    for name in _expected_tree_palette_vars():
        assert name in dark, name
        assert name in light, name
    assert "--tree-count" in dark and "--tree-count" in light
    assert dark["--tree-count"] != light["--tree-count"]


def test_tree_dark_palette_keeps_nodes_and_links_visible(tmp_path):
    """The light-tuned palette was ~1.5:1 on the dark panel (#5358)."""
    root = _blocks(_render_tree(tmp_path), ":root")
    panel = root["--panel"]
    palette = {
        name: value
        for name, value in root.items()
        if name.rsplit("-", 1)[-1] in ("fill", "stroke", "collapsed")
    }
    strokes = {n: v for n, v in palette.items() if n.endswith("-stroke")}
    fills = {n: v for n, v in palette.items() if n.endswith("-fill")}
    assert strokes and fills
    for name, value in strokes.items():
        assert _contrast(value, panel) >= 3.0, (name, value)
    for name, value in fills.items():
        assert _contrast(value, panel) >= 2.0, (name, value)


def test_tree_light_palette_matches_pre_theming_colors(tmp_path):
    """Light mode must keep the colours the tree shipped before #5358."""
    light = _blocks(_render_tree(tmp_path), '[data-theme="light"]')
    expected = {
        "--tree-root-fill": "#4A4A4A",
        "--tree-root-stroke": "#333333",
        "--tree-root-collapsed": "#6C757D",
        "--tree-phase-default-fill": "#BDC3C7",
        "--tree-phase-default-stroke": "#95A5A6",
        "--tree-phase-default-collapsed": "#ECF0F1",
        "--tree-d2-fill": "#6ab04c",
        "--tree-d3-fill": "#f0932b",
        "--tree-d4-fill": "#be2edd",
        "--tree-d5-fill": "#00a8ff",
        "--tree-d6-fill": "#e55039",
        "--tree-dx-fill": "#747d8c",
        "--tree-dx-stroke": "#57606f",
        "--tree-l1-0-fill": "#3498DB",
        "--tree-l1-0-stroke": "#2980B9",
        "--tree-l1-6-stroke": "#1B2631",
        "--tree-l1-14-collapsed": "#D2B4DE",
        "--tree-count": "#0056b3",
    }
    for name, value in expected.items():
        assert light[name] == value, name


def test_tree_palette_is_wired_through_css_not_literals(tmp_path):
    html = _render_tree(tmp_path)
    script = html.split("<script>", 1)[1]
    literals = {
        color
        for dark in (False, True)
        for _, triple in tree_html.tree_palette_names(dark)
        for color in triple
    }
    assert literals
    for color in literals:
        assert color not in script, color
    assert '"var(" + name + "-fill)"' in script
