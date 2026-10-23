"""get_node names what a function calls and what calls it (#985).

It used to return only the node's own file and start line, so an agent tracing
a call chain read the file to find callers and callees the graph already had.
"""
import networkx as nx

from graphify.serve import _node_call_lines


def _graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("run", label="run()", source_file="pkg/core.py", source_location="L10")
    G.add_node("parse", label="parse()", source_file="pkg/core.py", source_location="L40")
    G.add_node("render", label="render()", source_file="pkg/out.py", source_location="L5")
    G.add_node("main", label="main()", source_file="pkg/cli.py", source_location="L3")
    G.add_node("test_run", label="test_run()", source_file="tests/test_core.py", source_location="L7")
    G.add_node("core", label="core.py", source_file="pkg/core.py", source_location="L1")
    # Call sites out of alphabetical order: render() is called before parse().
    G.add_edge("run", "render", relation="calls", confidence="EXTRACTED", source_location="L12")
    G.add_edge("run", "parse", relation="calls", confidence="INFERRED", source_location="L15")
    G.add_edge("main", "run", relation="calls", confidence="EXTRACTED", source_location="L4")
    G.add_edge("test_run", "run", relation="calls", confidence="EXTRACTED", source_location="L8")
    G.add_edge("core", "run", relation="contains", confidence="EXTRACTED")
    return G


def test_lists_callees_in_call_order_and_callers_with_tests_counted():
    assert _node_call_lines(_graph(), "run") == [
        "  Calls (2): render() [pkg/out.py:L5], parse() [pkg/core.py:L40, inferred]",
        "  Called by (2): main() [pkg/cli.py:L3], 1 test",
    ]


def test_ignores_non_call_edges_and_omits_empty_lines():
    G = _graph()
    assert _node_call_lines(G, "core") == []  # only `contains` edges
    assert _node_call_lines(G, "render") == ["  Called by (1): run() [pkg/core.py:L10]"]


def test_caps_long_lists():
    G = _graph()
    for i in range(20):
        G.add_node(f"h{i}", label=f"h{i}()", source_file="pkg/h.py", source_location=f"L{i + 1}")
        G.add_edge("run", f"h{i}", relation="calls", confidence="EXTRACTED", source_location=f"L{20 + i}")
    (calls,) = [line for line in _node_call_lines(G, "run") if line.startswith("  Calls")]
    assert calls.startswith("  Calls (22): render() [pkg/out.py:L5], parse()")
    assert calls.endswith(", +10 more")
