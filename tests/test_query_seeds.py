"""`graphify query --seed`: explicit start nodes chosen by the caller (an external ranker) instead of the question's
keyword matches. A seed resolves exactly as `affected` resolves its seed, and fails closed when it does not."""
from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.serve import _query_graph_text


def _graph():
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="pkg/extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="pkg/cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="pkg/build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="pkg/report.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="EXTRACTED", context="call")
    G.add_edge("n3", "n4", relation="imports", confidence="EXTRACTED", context="import")
    return G


def _write(tmp_path, G):
    out = tmp_path / "graphify-out"
    out.mkdir()
    graph_path = out / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")))
    return graph_path


def test_given_seed_replaces_keyword_seeds():
    G = _graph()
    plain = _query_graph_text(G, "extract", depth=1)
    assert "Start: ['extract']" in plain and "NODE build" not in plain
    seeded = _query_graph_text(G, "extract", depth=1, seeds=["build"])
    assert "Start (given): ['build']" in seeded
    assert "NODE build" in seeded and "NODE report" in seeded       # traversal from the given node
    assert "NODE extract" not in seeded                              # the keyword match is not used


def test_seed_by_file_path_and_by_id_dedupes_in_order():
    G = _graph()
    text = _query_graph_text(G, "anything", depth=1, seeds=["pkg/build.py", "n1", "n3"])
    assert "Start (given): ['build', 'extract']" in text             # n3 is pkg/build.py: kept once, first


def test_unresolved_seed_is_reported_and_skipped():
    G = _graph()
    text = _query_graph_text(G, "anything", depth=1, seeds=["no_such_node", "cluster"])
    assert "Start (given): ['cluster']" in text
    assert "Unresolved seeds (skipped): ['no_such_node']" in text


def test_no_resolvable_seed_fails_closed():
    G = _graph()
    text = _query_graph_text(G, "extract", depth=1, seeds=["no_such_node"])
    assert text == "No unique node match for --seed: no_such_node"   # no fallback to the keyword seeds


def test_absolute_path_seed_resolves_against_the_graph_root(tmp_path):
    G = _graph()
    text = _query_graph_text(G, "anything", depth=1, seeds=[str(tmp_path / "pkg" / "report.py")], seed_root=tmp_path)
    assert "Start (given): ['report']" in text


def test_query_cli_seed_flag_is_repeatable(monkeypatch, tmp_path, capsys):
    graph_path = _write(tmp_path, _graph())
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "query", "extract", "--seed", "build", "--seed=pkg/cluster.py",
                                              "--graph", str(graph_path)])
    mainmod.main()
    out = capsys.readouterr().out
    assert "Start (given): ['build', 'cluster']" in out


def test_query_cli_absolute_seed_uses_the_graph_location_not_cwd(monkeypatch, tmp_path, capsys):
    graph_path = _write(tmp_path, _graph())
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "query", "q", "--seed", str(tmp_path / "pkg" / "build.py"),
                                              "--graph", str(graph_path)])
    mainmod.main()
    assert "Start (given): ['build']" in capsys.readouterr().out


def test_duplicate_unresolved_seed_is_reported_once():
    G = _graph()
    text = _query_graph_text(G, "anything", depth=1, seeds=["nope", "cluster", "nope"])
    assert "Unresolved seeds (skipped): ['nope']" in text


def test_callable_name_seed_resolves_with_or_without_parentheses():
    G = _graph()
    G.add_node("n5", label="refresh_token()", source_file="pkg/auth.py", source_location="L7", community=3)
    for value in ("refresh_token", "refresh_token()"):
        text = _query_graph_text(G, "anything", depth=1, seeds=[value])
        assert "Start (given): ['refresh_token()']" in text, value


def test_seed_combines_with_the_context_filter():
    G = _graph()
    G.add_edge("n3", "n2", relation="calls", confidence="EXTRACTED", context="call")   # build calls cluster
    kept = _query_graph_text(G, "anything", depth=1, seeds=["build"], context_filters=["call"])
    assert "Start (given): ['build']" in kept and "Context: call (explicit)" in kept
    assert "NODE cluster" in kept and "NODE report" not in kept                        # the import edge is filtered


def test_query_cli_seed_without_a_value_fails_closed(monkeypatch, tmp_path, capsys):
    import pytest
    graph_path = _write(tmp_path, _graph())
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    for argv in (["graphify", "query", "extract", "--graph", str(graph_path), "--seed"],
                 ["graphify", "query", "extract", "--seed=", "--graph", str(graph_path)]):
        monkeypatch.setattr(mainmod.sys, "argv", argv)
        with pytest.raises(SystemExit) as exc:
            mainmod.main()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "--seed needs a value" in captured.err and "Start" not in captured.out    # no keyword query ran


def test_query_cli_logs_the_seeds(monkeypatch, tmp_path, capsys):
    graph_path = _write(tmp_path, _graph())
    log = tmp_path / "queries.log"
    monkeypatch.delenv("GRAPHIFY_QUERY_LOG_DISABLE", raising=False)
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "query", "q", "--seed", "build", "--graph", str(graph_path)])
    mainmod.main()
    capsys.readouterr()
    record = json.loads(log.read_text().strip().splitlines()[-1])
    assert record.get("seeds") == ["build"]
