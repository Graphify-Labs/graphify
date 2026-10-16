"""Regression tests for direction and parallel relations in the generated
``/graphify explain`` fallback (#4471)."""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph


REPO_ROOT = Path(__file__).resolve().parent.parent
QUERY_FRAGMENT = REPO_ROOT / "tools/skillgen/fragments/references/query/default.md"
FALLBACK_OPEN = '$(cat graphify-out/.graphify_python) -c "\n'
# The path fallback right above this one in the fragment shares the same
# first four lines (import json, sys / import networkx as nx / from
# networkx.readwrite import json_graph / from pathlib import Path), so the
# locator must reach into the explain fallback's own first body line to
# land on the right one.
EXPLAIN_LOCATOR = (
    FALLBACK_OPEN
    + "import json, sys\nimport networkx as nx\nfrom networkx.readwrite "
    + "import json_graph\nfrom pathlib import Path\n\n"
    + "data = json.loads(Path('graphify-out/graph.json').read_text(encoding='utf-8'))\n"
    + "if 'links' not in data and 'edges' in data:"
)
FALLBACK_END = '\n"\n```'


def _explain_fallback_script() -> str:
    fragment = QUERY_FRAGMENT.read_text(encoding="utf-8")
    start = fragment.index(EXPLAIN_LOCATOR) + len(FALLBACK_OPEN)
    end = fragment.index(FALLBACK_END, start)
    return fragment[start:end]


def _run_explain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, graph: nx.Graph, *, term: str
) -> str:
    try:
        data = json_graph.node_link_data(graph, edges="links")
    except TypeError:  # NetworkX before the ``edges`` keyword.
        data = json_graph.node_link_data(graph)
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text(json.dumps(data), encoding="utf-8")

    script = _explain_fallback_script()
    # The payload is embedded in a double-quoted shell argument. Unescape the
    # quotes that the shell would remove before compiling its Python body.
    script = script.replace(chr(92) + '"', '"')
    script = script.replace("term = 'NODE_NAME'", f"term = {term!r}")
    assert "'NODE_NAME'" not in script

    monkeypatch.chdir(tmp_path)
    output = io.StringIO()
    with redirect_stdout(output):
        exec(compile(script, str(QUERY_FRAGMENT), "exec"), {"__name__": "__main__"})
    return output.getvalue()


def _canonical_graph(*edges: tuple[str, str, str]) -> nx.Graph:
    """A canonical export: `directed: false`, as `graphify export` writes it.

    Stores the arc exactly as given -- real canonical exports can carry a
    flipped arc order from undirected canonicalization, covered separately
    by the `_src` test below, not simulated here.
    """
    graph = nx.MultiGraph()
    graph.add_node("caller", label="Caller")
    graph.add_node("center", label="Center")
    for u, v, relation in edges:
        graph.add_edge(u, v, relation=relation, confidence="EXTRACTED")
    return graph


def test_explain_fallback_follows_stored_direction_not_arc_order(tmp_path, monkeypatch):
    """#4471: a canonical (undirected) export must not make every connection
    print as outgoing just because the loader builds an undirected graph."""
    graph = _canonical_graph(("caller", "center", "calls"))

    output = _run_explain(tmp_path, monkeypatch, graph, term="Center")

    assert "<--calls-- Caller" in output
    assert "-->" not in output


def test_explain_fallback_keeps_every_parallel_relation(tmp_path, monkeypatch):
    """#4471: two relations between the same pair must both be reported, not
    just the first one a plain `G[u][v]` lookup happens to return."""
    graph = _canonical_graph(
        ("caller", "center", "calls"), ("caller", "center", "uses")
    )

    output = _run_explain(tmp_path, monkeypatch, graph, term="Center")

    assert "<--calls-- Caller" in output
    assert "<--uses-- Caller" in output


def test_explain_fallback_reports_a_self_loop_once(tmp_path, monkeypatch):
    """#4471: a self loop is both a successor and a predecessor of its own
    node; walking both must not report it twice."""
    graph = _canonical_graph(
        ("caller", "center", "calls"), ("center", "center", "recurses")
    )

    output = _run_explain(tmp_path, monkeypatch, graph, term="Center")

    assert output.count("recurses") == 1
    assert "--recurses--> Center" in output


def test_explain_fallback_honours_the_src_marker_over_arc_order(tmp_path, monkeypatch):
    """A link whose arc was canonicalized by undirected storage carries its
    true direction in `_src` (#2309); the fallback must defer to it instead
    of assuming the stored source is the true caller."""
    graph_data = {
        "directed": False,
        "multigraph": True,
        "graph": {},
        "nodes": [{"id": "caller", "label": "Caller"}, {"id": "center", "label": "Center"}],
        "links": [
            {
                "source": "center", "target": "caller", "key": 0,
                "relation": "calls", "confidence": "EXTRACTED",
                "_src": "caller", "_tgt": "center",
            },
        ],
    }
    output_dir = tmp_path / "graphify-out"
    output_dir.mkdir()
    (output_dir / "graph.json").write_text(json.dumps(graph_data), encoding="utf-8")

    script = _explain_fallback_script().replace(chr(92) + '"', '"')
    script = script.replace("term = 'NODE_NAME'", "term = 'Center'")
    monkeypatch.chdir(tmp_path)
    output = io.StringIO()
    with redirect_stdout(output):
        exec(compile(script, str(QUERY_FRAGMENT), "exec"), {"__name__": "__main__"})
    output = output.getvalue()

    assert "<--calls-- Caller" in output, (
        f"caller must still read as the true source via _src, got: {output!r}"
    )


def test_explain_fallback_shows_the_edges_own_source_location(tmp_path, monkeypatch):
    """#4471: the printed location must come from the relationship's call
    site (the edge), not be silently borrowed from the neighbor's file."""
    graph = nx.MultiDiGraph()
    graph.add_node("caller", label="Caller", source_file="caller.py")
    graph.add_node("center", label="Center", source_file="center.py")
    graph.add_edge(
        "caller", "center", relation="calls", confidence="EXTRACTED",
        source_file="caller.py", source_location="L12",
    )

    output = _run_explain(tmp_path, monkeypatch, graph, term="Center")
    connections = output.split("CONNECTIONS:")[1]

    assert "caller.py:L12" in connections
    assert "center.py" not in connections
