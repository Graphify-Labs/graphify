"""graph.html light/dark/system theme toggle (#3894)."""
import re

import networkx as nx

from graphify.export import to_html

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
