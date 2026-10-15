"""`compact` writes the same query answer in fewer tokens.

_compact_answer is a pure pass over the output of _subgraph_to_text, applied by _render_query only when compact is
asked for, so the budget cut, the notices and the node order are the default ones. It rewrites the NODE lines, each
source file once with its nodes beneath, and a reader finds the same files in the same order. _subgraph_to_text and
the default output are unchanged."""
from __future__ import annotations

import re

import networkx as nx

from graphify.serve import _compact_answer, _query_graph_text, _subgraph_to_text


def _graph():
    G = nx.Graph()
    G.add_node("query_py", label="query.py", source_file="db/models/query.py", source_location="L1")
    G.add_node("qs", label="QuerySet", source_file="db/models/query.py", source_location="L280")
    G.add_node("flt", label="filter()", source_file="db/models/query.py", source_location="L1203")
    G.add_node("excl", label="_filter_or_exclude()", source_file="db/models/query.py", source_location="L1219")
    G.add_node("where", label="WhereNode", source_file="db/models/sql/where.py", source_location="L14")
    G.add_node("q", label="Q", source_file="db/models/query_utils.py", source_location="L35")
    G.add_node("os", label="os", source_file="", source_location="")
    for a, b in (("query_py", "qs"), ("qs", "flt"), ("flt", "excl"), ("excl", "where"), ("excl", "q"), ("qs", "os")):
        G.add_edge(a, b, relation="calls", confidence="EXTRACTED")
    return G


def _render(G, compact, budget=2000, seeds=None):
    text = _subgraph_to_text(G, set(G.nodes), list(G.edges), budget, seeds=seeds)
    return _compact_answer(text, budget) if compact else text


def _files_default(text):
    files = []
    for p in re.findall(r"(?m)^NODE .*?\[src=([^ \]]*)", text):
        p = p or "(none)"
        if p not in files:
            files.append(p)
    return files


def _files_compact(text):
    return re.findall(r"(?m)^FILE (.+?)(?: community=.*)?$", text)


def test_compact_false_is_the_default_answer():
    G = _graph()
    assert _query_graph_text(G, "filter QuerySet", mode="bfs", depth=3) == \
        _query_graph_text(G, "filter QuerySet", mode="bfs", depth=3, compact=False)


def test_compact_keeps_the_same_files_in_the_same_order_and_is_shorter():
    G = _graph()
    default = _query_graph_text(G, "filter QuerySet", mode="bfs", depth=3)
    compact = _query_graph_text(G, "filter QuerySet", mode="bfs", depth=3, compact=True)
    assert _files_compact(compact) == _files_default(default)
    assert len(compact) < len(default)
    assert "NODE " not in compact and "[src=" not in compact
    assert compact.splitlines()[0] == default.splitlines()[0]          # the header line is kept as is


def test_each_node_keeps_its_label_and_location_and_empty_fields_are_dropped():
    compact = _render(_graph(), compact=True)
    assert "  filter() L1203" in compact and "  WhereNode L14" in compact
    assert "community=" not in compact                                  # every community is empty here
    assert "FILE (none)" in compact and "  os" in compact               # a node with no file is still shown


def test_a_files_own_node_is_dropped_because_the_file_line_names_it():
    compact = _render(_graph(), compact=True)
    assert "FILE db/models/query.py" in compact
    assert "  query.py" not in compact


def test_a_file_carries_its_shared_community_once_and_a_node_names_only_a_different_one():
    G = _graph()
    for n in ("query_py", "qs", "flt"):
        G.nodes[n]["community_name"] = "Query API"
    G.nodes["excl"]["community_name"] = "Filtering"
    compact = _render(G, compact=True)
    assert "FILE db/models/query.py community=Query API" in compact
    assert "  QuerySet L280\n" in compact and "  filter() L1203\n" in compact     # the shared one is not repeated
    assert "  _filter_or_exclude() L1219 community=Filtering" in compact
    assert "  query.py" not in compact                                           # same community as its file


def test_a_files_own_node_with_a_community_of_its_own_is_kept():
    G = _graph()
    for n in ("qs", "flt", "excl"):
        G.nodes[n]["community_name"] = "Query API"
    G.nodes["query_py"]["community_name"] = "Module Index"
    assert "  query.py L1 community=Module Index" in _render(G, compact=True)


def test_a_truncated_answer_compacts_exactly_the_nodes_the_default_shows():
    G = nx.Graph()
    for i in range(400):
        G.add_node(f"n{i}", label=f"handler_{i}", source_file=f"pkg/mod_{i % 37}.py", source_location=f"L{10 + i}")
        if i:
            G.add_edge("n0", f"n{i}", relation="calls", confidence="EXTRACTED")
    default = _render(G, compact=False, budget=300, seeds=["n0"])
    compact = _render(G, compact=True, budget=300, seeds=["n0"])
    assert default.startswith("[!] TRUNCATED") and compact.startswith("[!] TRUNCATED")
    assert compact.splitlines()[0] == default.splitlines()[0]          # the same notice, the same counts
    by_file_default: dict[str, list[str]] = {}
    for label, src in re.findall(r"(?m)^NODE (\S+) \[src=(\S+)", default):
        by_file_default.setdefault(src, []).append(label)
    by_file_compact: dict[str, list[str]] = {}
    current = None
    for line in compact.splitlines():
        if line.startswith("FILE "):
            current = line[5:].split(" community=")[0]
        elif current and line.startswith("  handler_"):
            by_file_compact.setdefault(current, []).append(line.split()[0])
    assert by_file_compact == by_file_default                          # the same nodes, each file's in its order
    assert _files_compact(compact) == _files_default(default)          # and the files in the same order
    assert len(compact) < len(default)


def test_learning_and_attrs_annotations_survive_compaction():
    text = 'Traversal: BFS depth=2\n\nNODE handler [src=pkg/a.py loc=L9 community= learning=useful attrs={kind="route"}]'
    assert _compact_answer(text, 2000).endswith('FILE pkg/a.py\n  handler L9 learning=useful attrs={kind="route"}')


def test_a_node_line_that_does_not_parse_leaves_the_answer_unchanged():
    text = "NODE odd label with no fields\nNODE handler [src=pkg/a.py loc=L9 community=]"
    assert _compact_answer(text, 2000) == text


def test_text_without_node_lines_is_returned_unchanged():
    assert _compact_answer("No matching nodes found.", 2000) == "No matching nodes found."
