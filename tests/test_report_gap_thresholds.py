"""GRAPH_REPORT's headline numbers must agree with themselves (#3148).

The Summary and Communities headers counted thin communities against the
caller's --min-community-size, while the Knowledge Gaps section counted
against a hardcoded 3 - beside label text that already printed
min_community_size. And the "isolated node(s)" figure excludes file,
concept and rationale nodes without saying so, so a plain degree<=1 recount
from graph.json never matched it. Also the #2129 residual: "shown" was
total-minus-thin, which counted zero-real-node communities the render loop
skips.
"""
from __future__ import annotations

import re

import networkx as nx

from graphify.report import generate


def _graph_and_communities():
    G = nx.Graph()
    # community 0: 6 real symbol nodes (rendered at every threshold used here)
    big = [f"big{i}" for i in range(6)]
    # community 1: 4 real nodes - thin at min=5, NOT thin at the hardcoded 3
    mid = [f"mid{i}" for i in range(4)]
    for n in big + mid:
        G.add_node(n, label=n, file_type="code", source_file=f"src/{n}.py",
                   source_location="L1")
    for group in (big, mid):
        for a, b in zip(group, group[1:]):
            G.add_edge(a, b, relation="calls", confidence="EXTRACTED")
    # community 2: only a file node - the render loop skips it entirely
    G.add_node("onlyfile", label="onlyfile.py", file_type="code", source_file="onlyfile.py")
    # a lonely concept node: degree 0, excluded from the symbol-isolated list
    G.add_node("lonely_concept", label="Lonely", file_type="concept", source_file="d.md")
    communities = {0: big, 1: mid, 2: ["onlyfile"]}
    return G, communities


def _report(min_size):
    G, communities = _graph_and_communities()
    return generate(
        G, communities, {}, {}, [], [],
        {"total_files": 3, "total_words": 100}, {},
        root="proj", min_community_size=min_size,
    )


def test_summary_and_gaps_count_thin_with_the_same_threshold():
    text = _report(5)
    assert "(1 shown, 1 thin omitted)" in text
    m = re.search(r"\*\*(\d+) thin communit\w+ \(<(\d+) nodes\) omitted", text)
    assert m, text
    assert m.group(1) == "1" and m.group(2) == "5", m.group(0)


def test_at_the_default_threshold_nothing_is_thin():
    text = _report(3)
    assert "0 thin omitted" in text
    if "## Knowledge Gaps" in text:
        gaps = text.split("## Knowledge Gaps")[-1].split("## ")[0]
        assert "thin communit" not in gaps


def test_shown_counts_only_what_the_render_loop_renders():
    """The zero-real-node community is neither shown nor thin (#2129 residual):
    shown must be 1 (the big community), not total-minus-thin = 2."""
    text = _report(5)
    header = re.search(r"## Communities \((\d+) total, (\d+) thin omitted\)", text)
    assert header and header.group(2) == "1"
    assert "(1 shown, 1 thin omitted)" in text
    rendered = len(re.findall(r"### Community ", text))
    assert rendered <= 1 or rendered == int(re.search(r"\((\d+) shown", text).group(1))


def test_isolated_count_is_auditable_against_the_raw_graph():
    text = _report(3)
    assert "isolated node(s):" in text
    assert "Counts symbols only" in text
    m = re.search(r"(\d+) node\(s\) total have ≤1 connection", text)
    assert m
    G, _ = _graph_and_communities()
    assert int(m.group(1)) == sum(1 for n in G.nodes() if G.degree(n) <= 1)
