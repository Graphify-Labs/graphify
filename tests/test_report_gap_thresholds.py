"""GRAPH_REPORT's headline numbers must agree with themselves (#3148, #3548).

The Summary and Communities headers counted thin communities against the
caller's --min-community-size, while the Knowledge Gaps section counted
against a hardcoded 3 - beside label text that already printed
min_community_size. And the "isolated node(s)" figure excludes file,
concept and rationale nodes without saying so, so a plain degree<=1 recount
from graph.json never matched it. Also the #2129 residual: "shown" was
total-minus-thin, which counted zero-real-node communities the render loop
skips.

#3548: fixing the #2129 residual by computing "shown" directly (instead of
total-minus-thin) then left "thin" itself undercounting - a `0 <` guard
excluded a zero-real-node community from "thin" too, so a community the
render loop also skips went uncounted anywhere. `shown + thin` no longer
summed to the total. Both thresholds below now count the all-file-node
community ("onlyfile") as thin at every positive min_community_size, since
0 is always less than it.
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
    # At min=5: "mid" (4 real) and "onlyfile" (0 real) are both thin; "big"
    # (6 real) is shown.
    text = _report(5)
    assert "(1 shown, 2 thin omitted)" in text
    m = re.search(r"\*\*(\d+) thin communit\w+ \(<(\d+) nodes\) omitted", text)
    assert m, text
    assert m.group(1) == "2" and m.group(2) == "5", m.group(0)


def test_at_the_default_threshold_only_the_zero_real_community_is_thin():
    # At min=3: "mid" (4 real) clears the threshold and is shown; "onlyfile"
    # (0 real) is still thin at any positive threshold (#3548).
    text = _report(3)
    assert "1 thin omitted" in text
    if "## Knowledge Gaps" in text:
        gaps = text.split("## Knowledge Gaps")[-1].split("## ")[0]
        assert "1 thin communit" in gaps


def test_shown_counts_only_what_the_render_loop_renders():
    """`shown + thin` must sum to the total community count (#3548): the
    zero-real-node community is never shown (the render loop skips it), so
    it must be counted as thin rather than going uncounted anywhere."""
    text = _report(5)
    header = re.search(r"## Communities \((\d+) total, (\d+) thin omitted\)", text)
    assert header and header.group(1) == "3" and header.group(2) == "2"
    assert "(1 shown, 2 thin omitted)" in text
    rendered = len(re.findall(r"### Community ", text))
    assert rendered <= 1 or rendered == int(re.search(r"\((\d+) shown", text).group(1))


def test_shown_plus_thin_equals_total_communities_and_matches_render_count():
    # The two invariants #3548's own report suggested as a regression check,
    # checked at both thresholds used elsewhere in this file.
    for min_size in (3, 5):
        text = _report(min_size)
        summary = re.search(
            r"\((\d+) shown, (\d+) thin omitted\)", text
        )
        assert summary, text
        shown, thin = int(summary.group(1)), int(summary.group(2))
        rendered = len(re.findall(r"### Community \d+ - ", text))
        assert shown == rendered, (min_size, shown, rendered)
        assert shown + thin == 3, (min_size, shown, thin)  # 3 communities total


def test_isolated_count_is_auditable_against_the_raw_graph():
    text = _report(3)
    assert "isolated node(s):" in text
    assert "Counts symbols only" in text
    m = re.search(r"(\d+) node\(s\) total have ≤1 connection", text)
    assert m
    G, _ = _graph_and_communities()
    assert int(m.group(1)) == sum(1 for n in G.nodes() if G.degree(n) <= 1)


def test_undocumented_components_omitted_without_a_semantic_layer():
    """#3801: "undocumented components" only means anything when a semantic
    layer (document/paper/image nodes) exists to be undocumented. This
    fixture is code + concept only, so the reason offered for an isolated
    node must not claim a possibility the graph structurally cannot have."""
    text = _report(3)
    assert "isolated node(s):" in text
    gaps = text.split("## Knowledge Gaps")[-1].split("## ")[0]
    assert "possible missing edges" in gaps
    assert "undocumented components" not in gaps


def test_undocumented_components_offered_when_a_semantic_layer_exists():
    """The flip side of #3801: once the graph has at least one
    document/paper/image node anywhere, "undocumented components" is a real
    possibility again and the reason should still offer it."""
    G, communities = _graph_and_communities()
    G.add_node("doc1", label="doc1.md", file_type="document", source_file="docs/doc1.md")
    text = generate(
        G, communities, {}, {}, [], [],
        {"total_files": 4, "total_words": 100}, {},
        root="proj", min_community_size=3,
    )
    gaps = text.split("## Knowledge Gaps")[-1].split("## ")[0]
    assert "possible missing edges or undocumented components" in gaps
