"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import json

import pytest

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", context="call")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED", context="import")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_query_cli_explicit_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--context", "call", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (explicit)" in out
    assert "cluster" in out
    assert "build" not in out


def test_query_cli_heuristic_context_filter(monkeypatch, tmp_path, capsys):
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "who calls extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "Context: call (heuristic)" in out
    assert "cluster" in out
    assert "build" not in out


def _write_calls_graph(tmp_path):
    """A single directed `calls` edge on an (on-disk) undirected graph.json,

    the standard `graphify extract`/`update` output shape (`"directed":
    false`, direction implied only by each link's source/target).
    """
    G = nx.Graph()
    G.add_node("caller", label="caller_fn", source_file="a.py", source_location="L1", community=0)
    G.add_node("callee", label="callee_fn", source_file="b.py", source_location="L1", community=1)
    G.add_edge("caller", "callee", relation="calls", confidence="EXTRACTED", context="call")
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_query_cli_preserves_calls_direction_when_seeded_on_callee(monkeypatch, tmp_path, capsys):
    """`graphify query` must render `calls` edges caller->callee regardless of
    which endpoint the query term matches first.

    The graph `query` loads is undirected (so BFS/DFS can explore both
    callers and callees of the seed), so `G.neighbors()` returns `caller_fn`
    as a neighbor of `callee_fn` with no direction of its own. Before the
    fix, the renderer assumed the BFS/DFS visit order (u, v) was the edge's
    (source, target), so seeding on the callee printed the edge backwards:
    "callee_fn --calls--> caller_fn". graph.json's `source`/`target` for this
    edge stay correct on disk either way; only the query rendering was wrong.
    """
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "callee_fn", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "caller_fn --calls" in out
    assert "callee_fn --calls" not in out


def test_query_cli_preserves_calls_direction_when_seeded_on_caller(monkeypatch, tmp_path, capsys):
    """Same edge, seeded from the caller side — must stay correct too."""
    graph_path = _write_calls_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "caller_fn", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "caller_fn --calls" in out
    assert "callee_fn --calls" not in out


def test_query_cli_rejects_oversized_graph(monkeypatch, tmp_path, capsys):
    """#F4: query CLI must refuse to parse a graph.json that exceeds the cap."""
    import pytest

    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr("graphify.security._MAX_GRAPH_FILE_BYTES", 16)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    err = capsys.readouterr().err
    assert "exceeds" in err
    assert "byte cap" in err


def test_query_cli_lone_help_flag_prints_usage(monkeypatch, tmp_path, capsys):
    """`graphify query --help`/`-h` with nothing else shows usage instead of
    running a literal query for the text "--help" (#TBD)."""
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    for flag in ("--help", "-h"):
        monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "query", flag, "--graph", str(graph_path)][:3])
        mainmod.main()
        out = capsys.readouterr().out
        assert out.startswith("Usage: graphify query")
        assert "extract" not in out
        assert "cluster" not in out


def test_query_cli_question_containing_help_text_still_runs(monkeypatch, tmp_path, capsys):
    """A genuine free-text question that merely contains "--help" as a
    substring must still run as a literal query, not be swallowed as a help
    request - only an *exact*, standalone "--help"/"-h" is intercepted."""
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "how do I get --help for extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "cluster" in out
    assert not out.startswith("Usage: graphify query")


def test_explain_cli_lone_help_flag_prints_usage(monkeypatch, tmp_path, capsys):
    """`graphify explain --help`/`-h` with nothing else shows usage instead of
    running a literal node lookup for the text "--help" (#4830 extended): explain
    is a free-text command with the same standalone-help gap as query."""
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    for flag in ("--help", "-h"):
        monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "explain", flag, "--graph", str(graph_path)][:3])
        mainmod.main()
        out = capsys.readouterr().out
        assert out.startswith("Usage: graphify explain")
        assert "No node matching" not in out


def test_explain_cli_node_containing_help_text_still_runs(monkeypatch, tmp_path, capsys):
    """A genuine explain target that merely contains "--help" as a substring must
    still run as a literal lookup, not be swallowed as a help request. The
    unresolvable label exits not-found (proving it reached the lookup), and never
    prints usage."""
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "explain", "a node named --help here", "--graph", str(graph_path)],
    )
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert not out.startswith("Usage: graphify explain")
