"""The inline `/graphify query` fallback must render every edge between visited
nodes (#4314).

The fallback recorded an edge only when BFS/DFS discovered an *unvisited*
neighbour, so its result was a traversal tree rather than the induced subgraph
over the node set it reports. The clearest casualty is an edge between two seed
nodes: both endpoints render, the edge between them does not. `graphify query`
had the same defect and fixed it in #2323 (`graphify.serve._complete_induced_edges`);
the inline fallback now mirrors that completion.

These tests extract the shipped fallback source from the generated artifacts and
the authoritative reference fragment, and execute it against a real
`graphify-out/graph.json`, so they guard the actual artifact rather than a
re-implementation.
"""
from __future__ import annotations

import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Every file that ships the inline fallback: the shared reference fragment (the
#: source for all split platforms), the two generated monolith skills, and the
#: generated codex reference the issue names. A fix that lands in one but not the
#: others is caught here. The monolith entries point at the shipped artifacts
#: rather than their fragments so a hand-edit of a shipped file is caught too.
FALLBACK_SOURCES = {
    "reference_fragment": REPO_ROOT / "tools/skillgen/fragments/references/query/default.md",
    "aider_artifact": REPO_ROOT / "graphify/skill-aider.md",
    "devin_artifact": REPO_ROOT / "graphify/skill-devin.md",
    "codex_artifact": REPO_ROOT / "graphify/skills/codex/references/query.md",
}


def _extract_fallback(md_text: str) -> str:
    """Pull the traversal Python out of its ```bash `-c "..."` fence."""
    text = md_text.replace("\r\n", "\n")
    for block in re.findall(r"```bash\n(.*?)\n```", text, re.S):
        if "subgraph_edges = []" not in block:
            continue
        lines = block.split("\n")
        assert lines[0].rstrip().endswith('-c "'), lines[0]
        assert lines[-1].strip() == '"', lines[-1]
        # only \" is escaped inside the bash double-quoted body
        return "\n".join(lines[1:-1]).replace('\\"', '"')
    raise AssertionError("inline traversal fallback block not found")


@pytest.fixture(params=sorted(FALLBACK_SOURCES), ids=lambda key: key)
def fallback_src(request) -> str:
    path = FALLBACK_SOURCES[request.param]
    src = _extract_fallback(path.read_text(encoding="utf-8"))
    # The completion is the fix under test; fail loudly if a source lacks it.
    assert "G.edges(sorted(subgraph_nodes))" in src, f"{path} has no induced-edge completion"
    return src


def _run(src, G, question, mode, tmp_path, monkeypatch, budget=2000) -> str:
    out_dir = tmp_path / "graphify-out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "graph.json").write_text(
        json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    code = (
        src.replace("'QUESTION'", repr(question))
        .replace("'MODE'", repr(mode))
        .replace("BUDGET", str(budget))
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        exec(compile(code, "<fallback>", "exec"), {"__name__": "__fallback__"})
    return buf.getvalue()


def _edges(output: str) -> set[tuple[str, str]]:
    found = set()
    for line in output.splitlines():
        match = re.match(r"\s*EDGE (.+?) --.*--> (.+?)\s*$", line)
        if match:
            found.add((match.group(1), match.group(2)))
    return found


def _undirected(output: str) -> set[frozenset[str]]:
    """Edge set for undirected graphs, where the fallback may print either endpoint first."""
    return {frozenset(edge) for edge in _edges(output)}


def _add(G, *names):
    for name in names:
        G.add_node(name, label=name, source_file=f"{name}.py", source_location="L1")


def _link(G, a, b, relation="calls", confidence="EXTRACTED"):
    G.add_edge(a, b, relation=relation, confidence=confidence)


# --- the reported case: every endpoint is a seed ----------------------------


def test_seeded_nodes_emit_edge_between_them(fallback_src, tmp_path, monkeypatch):
    """The reporter's repro: all three nodes are seeds, so none discovers another."""
    G = nx.MultiDiGraph()
    _add(G, "checkout_flow", "checkout_gate", "checkout_ledger")
    _link(G, "checkout_flow", "checkout_gate")
    _link(G, "checkout_gate", "checkout_ledger")
    _link(G, "checkout_flow", "checkout_ledger")

    out = _run(fallback_src, G, "checkout", "bfs", tmp_path, monkeypatch)

    assert _edges(out) == {
        ("checkout_flow", "checkout_gate"),
        ("checkout_gate", "checkout_ledger"),
        ("checkout_flow", "checkout_ledger"),
    }


# --- cross-links discovered during traversal --------------------------------


def test_bfs_cross_link_between_discovered_nodes(fallback_src, tmp_path, monkeypatch):
    """The n2-n3 chord closes the triangle but discovers nothing, so it was dropped."""
    G = nx.Graph()
    _add(G, "circle", "ring_b", "ring_c")
    _link(G, "circle", "ring_b")
    _link(G, "circle", "ring_c")
    _link(G, "ring_b", "ring_c")

    out = _run(fallback_src, G, "circle", "bfs", tmp_path, monkeypatch)

    assert _undirected(out) == {
        frozenset(("circle", "ring_b")),
        frozenset(("circle", "ring_c")),
        frozenset(("ring_b", "ring_c")),
    }


def test_dfs_cross_link_between_discovered_nodes(fallback_src, tmp_path, monkeypatch):
    G = nx.Graph()
    _add(G, "circle", "ring_b", "ring_c")
    _link(G, "circle", "ring_b")
    _link(G, "circle", "ring_c")
    _link(G, "ring_b", "ring_c")

    out = _run(fallback_src, G, "circle", "dfs", tmp_path, monkeypatch)

    assert _undirected(out) == {
        frozenset(("circle", "ring_b")),
        frozenset(("circle", "ring_c")),
        frozenset(("ring_b", "ring_c")),
    }


# --- cycles -----------------------------------------------------------------


def test_cycle_renders_every_arc(fallback_src, tmp_path, monkeypatch):
    G = nx.DiGraph()
    _add(G, "loop_a", "loop_b", "loop_c")
    _link(G, "loop_a", "loop_b")
    _link(G, "loop_b", "loop_c")
    _link(G, "loop_c", "loop_a")

    out = _run(fallback_src, G, "loop", "bfs", tmp_path, monkeypatch)

    assert _edges(out) == {("loop_a", "loop_b"), ("loop_b", "loop_c"), ("loop_c", "loop_a")}


# --- direction + de-duplication ---------------------------------------------


def test_directed_edge_direction_is_preserved(fallback_src, tmp_path, monkeypatch):
    G = nx.DiGraph()
    _add(G, "dnode_a", "dnode_b", "dnode_c")
    _link(G, "dnode_a", "dnode_b")
    _link(G, "dnode_b", "dnode_c")
    _link(G, "dnode_a", "dnode_c")

    out = _run(fallback_src, G, "dnode", "bfs", tmp_path, monkeypatch)

    assert _edges(out) == {
        ("dnode_a", "dnode_b"),
        ("dnode_b", "dnode_c"),
        ("dnode_a", "dnode_c"),
    }


def test_parallel_edges_are_not_duplicated(fallback_src, tmp_path, monkeypatch):
    G = nx.MultiDiGraph()
    _add(G, "multi_x", "multi_y")
    _link(G, "multi_x", "multi_y")
    _link(G, "multi_x", "multi_y")

    out = _run(fallback_src, G, "multi", "bfs", tmp_path, monkeypatch)

    edge_lines = [line for line in out.splitlines() if line.strip().startswith("EDGE")]
    assert len(edge_lines) == 1
    assert _edges(out) == {("multi_x", "multi_y")}
