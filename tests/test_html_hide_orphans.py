"""graph.html "Hide orphans" toggle."""
import json
import re

import networkx as nx

from graphify.export import to_html


def _render(tmp_path):
    G = nx.Graph()
    G.add_node("a", label="Alpha", source_file="a.py", file_type="code")
    G.add_node("b", label="Beta", source_file="b.py", file_type="code")
    G.add_node("lone", label="Lone", source_file="c.py", file_type="code")
    G.add_edge("a", "b", relation="calls", confidence="EXTRACTED")
    out = tmp_path / "graph.html"
    to_html(G, {0: ["a", "b", "lone"]}, str(out), community_labels={0: "Core"})
    return out.read_text(encoding="utf-8")


def _raw_nodes(html):
    m = re.search(r"const RAW_NODES = (\[.*?\]);\n", html)
    assert m, "missing RAW_NODES"
    return {n["id"]: n for n in json.loads(m.group(1))}


def test_orphan_has_zero_degree_and_connected_nodes_do_not(tmp_path):
    nodes = _raw_nodes(_render(tmp_path))
    assert nodes["lone"]["degree"] == 0
    assert nodes["a"]["degree"] == 1
    assert nodes["b"]["degree"] == 1


def test_toggle_is_off_by_default(tmp_path):
    html = _render(tmp_path)
    m = re.search(r'<input type="checkbox" id="hide-orphans-cb"[^>]*>', html)
    assert m, "missing Hide orphans checkbox"
    assert not re.search(r"\schecked[\s>]", m.group(0))
    assert 'onchange="setHideOrphans(this.checked)"' in m.group(0)
    assert "let hideOrphans = false;" in html


def test_community_filter_and_orphan_filter_share_one_predicate(tmp_path):
    html = _render(tmp_path)
    assert "hiddenCommunities.has(n.community) || (hideOrphans && n.degree === 0)" in html
    # Re-showing a community must not un-hide its orphans while the toggle is on,
    # so every visibility update goes through isNodeHidden().
    assert "hidden: hide }" not in html
    assert "hidden: !cb.checked" not in html
    assert html.count("hidden: isNodeHidden(n)") == 3
