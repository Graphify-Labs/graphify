"""Tests for graphify query CLI context filtering."""
from __future__ import annotations

import graphify.__main__ as mainmod

_NODES = [
    {"id": "n1", "label": "extract", "source_file": "extract.py", "source_location": "L10", "community": 0, "file_type": "code"},
    {"id": "n2", "label": "cluster", "source_file": "cluster.py", "source_location": "L5", "community": 0, "file_type": "code"},
    {"id": "n3", "label": "build", "source_file": "build.py", "source_location": "L1", "community": 1, "file_type": "code"},
]
_LINKS = [
    {"source": "n1", "target": "n2", "relation": "calls", "confidence": "EXTRACTED", "context": "call"},
    {"source": "n2", "target": "n3", "relation": "imports", "confidence": "EXTRACTED", "context": "import"},
]


def test_query_cli_explicit_context_filter(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    graph_path = tmp_path / "graph.json"
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


def test_query_cli_heuristic_context_filter(monkeypatch, tmp_path, capsys, seed_graph):
    seed_graph(tmp_path, _NODES, _LINKS)
    graph_path = tmp_path / "graph.json"
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


_CALLS_NODES = [
    {"id": "caller", "label": "caller_fn", "source_file": "a.py", "source_location": "L1", "community": 0},
    {"id": "callee", "label": "callee_fn", "source_file": "b.py", "source_location": "L1", "community": 1},
]
_CALLS_LINKS = [
    {"source": "caller", "target": "callee", "relation": "calls",
     "confidence": "EXTRACTED", "context": "call"},
]


def test_query_cli_preserves_calls_direction_when_seeded_on_callee(monkeypatch, tmp_path, capsys, seed_graph):
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
    seed_graph(tmp_path, _CALLS_NODES, _CALLS_LINKS)
    graph_path = tmp_path / "graph.json"
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


def test_query_cli_preserves_calls_direction_when_seeded_on_caller(monkeypatch, tmp_path, capsys, seed_graph):
    """Same edge, seeded from the caller side — must stay correct too."""
    seed_graph(tmp_path, _CALLS_NODES, _CALLS_LINKS)
    graph_path = tmp_path / "graph.json"
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


def test_query_cli_rejects_oversized_graph(monkeypatch, tmp_path, capsys, _require_falkordb):
    """#F4: the graph.json back-compat import must refuse a file over the cap.

    No seed_graph here on purpose: with an empty store, `query` falls back to
    importing graph.json, which is the one path that still parses an arbitrary
    file and so must still enforce the size cap.
    """
    import json

    import pytest

    graph_path = tmp_path / "graph.json"
    graph_path.write_text(json.dumps(
        {"directed": True, "multigraph": False, "graph": {},
         "nodes": _NODES, "links": _LINKS}
    ))
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
