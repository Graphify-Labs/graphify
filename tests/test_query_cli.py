"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import json

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


# --- work-memory overlay: lesson annotations in CLI query output ---------------


def _write_sidecar(tmp_path, nodes: dict) -> None:
    """A .graphify_learning.json next to graph.json, in the writer's shape."""
    (tmp_path / ".graphify_learning.json").write_text(
        json.dumps({"version": 1, "generated_at": "2026-01-01T00:00:00+00:00",
                    "nodes": nodes}),
        encoding="utf-8",
    )


def test_query_cli_annotates_nodes_with_learning_status(monkeypatch, tmp_path, capsys):
    """`graphify query` must merge the learning sidecar into NODE lines with the
    same learning=<status> form the MCP server renders — the docs promise
    lessons surface in `query` output, not only in `explain`/MCP."""
    graph_path = _write_graph(tmp_path)
    _write_sidecar(tmp_path, {"n1": {"status": "preferred"}})
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "learning=preferred]" in out
    # Only the annotated node carries the suffix.
    assert out.count("learning=") == 1


def test_query_cli_marks_stale_learning_entries(monkeypatch, tmp_path, capsys):
    """An entry whose cited code changed (or vanished) since the verdict must
    carry the :stale marker, matching the MCP annotation form."""
    graph_path = _write_graph(tmp_path)
    _write_sidecar(
        tmp_path,
        {"n1": {"status": "tentative", "source_file": "gone.py",
                "code_fingerprint": "0123abcd"}},
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "learning=tentative:stale]" in out


def test_query_cli_without_sidecar_stays_unannotated(monkeypatch, tmp_path, capsys):
    """No sidecar -> no learning= anywhere; un-annotated output is unchanged."""
    graph_path = _write_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "query", "extract", "--graph", str(graph_path)],
    )
    mainmod.main()
    out = capsys.readouterr().out
    assert "learning=" not in out
