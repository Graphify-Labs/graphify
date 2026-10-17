"""`explain`, `path` and `query` tell a script apart an answer, an ambiguous name
and a name that matches nothing, through the exit code alone.

`explain` used to exit 0 on a miss, the same as a successful answer, and the
ambiguity and miss refusals of `path` shared exit 1 with every other error.
"""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod
from graphify.cli import EXIT_AMBIGUOUS, EXIT_NOT_FOUND


def _write_graph(tmp_path):
    nodes = [
        ("src_a_alphaclient", "AlphaClient", "src/a.ts", "L1"),
        ("src_a_alphaclient_nonce", ".nonce()", "src/a.ts", "L2"),
        ("src_b_betaclient", "BetaClient", "src/b.ts", "L1"),
        ("src_b_betaclient_nonce", ".nonce()", "src/b.ts", "L2"),
        ("src_c_run", "run()", "src/c.ts", "L1"),
        ("src_d_island", "island()", "src/d.ts", "L1"),
    ]
    links = [
        ("src_c_run", "src_b_betaclient", "calls"),
        ("src_b_betaclient", "src_b_betaclient_nonce", "method"),
        ("src_a_alphaclient", "src_a_alphaclient_nonce", "method"),
    ]
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": i, "label": lbl, "source_file": sf, "source_location": loc}
            for i, lbl, sf, loc in nodes
        ],
        "links": [
            {"source": a, "target": b, "relation": rel, "confidence": "EXTRACTED"}
            for a, b, rel in links
        ],
    }))
    return p


def _run(monkeypatch, capsys, *argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", *argv])
    try:
        mainmod.main()
    except SystemExit as exc:
        captured = capsys.readouterr()
        return exc.code, captured.out + captured.err
    captured = capsys.readouterr()
    return None, captured.out + captured.err


def test_exit_codes_are_distinct_from_success_and_from_each_other():
    assert len({0, 1, EXIT_AMBIGUOUS, EXIT_NOT_FOUND}) == 4


def test_explain_answer_exits_zero(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys, "explain", "run()", "--graph", str(_write_graph(tmp_path)))
    assert code is None
    assert "ID:        src_c_run" in out


def test_explain_ambiguous_exits_ambiguous(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys, "explain", ".nonce()", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_AMBIGUOUS
    assert "Ambiguous: '.nonce()' matches 2 nodes in different files." in out


@pytest.mark.parametrize("label", ["NoSuchSymbolXyz", "src/a.ts::NotThere"])
def test_explain_miss_exits_not_found(monkeypatch, tmp_path, capsys, label):
    code, out = _run(monkeypatch, capsys, "explain", label, "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_NOT_FOUND
    assert f"No node matching '{label}' found." in out


def test_path_answer_exits_zero(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "path", "run()", "src/b.ts::.nonce()", "--graph", str(_write_graph(tmp_path)))
    assert code is None
    assert "Shortest path (2 hops):" in out


def test_path_without_route_is_an_answer(monkeypatch, tmp_path, capsys):
    """Both endpoints exist and no route joins them: that is the answer, not a miss."""
    code, out = _run(monkeypatch, capsys,
        "path", "run()", "island()", "--graph", str(_write_graph(tmp_path)))
    assert code == 0
    assert "No directed path found" in out


def test_path_ambiguous_endpoint_exits_ambiguous(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "path", "run()", ".nonce()", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_AMBIGUOUS
    assert "Ambiguous: '.nonce()'" in out


def test_path_same_node_both_ends_exits_ambiguous(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "path", "run()", "src_c_run", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_AMBIGUOUS
    assert "both resolved to the same node" in out


@pytest.mark.parametrize("endpoint", ["NoSuchSymbolXyz", "src/a.ts::NotThere"])
def test_path_missing_endpoint_exits_not_found(monkeypatch, tmp_path, capsys, endpoint):
    code, out = _run(monkeypatch, capsys,
        "path", "run()", endpoint, "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_NOT_FOUND
    assert "Shortest path" not in out


def test_query_answer_exits_zero(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys, "query", "run", "--graph", str(_write_graph(tmp_path)))
    assert code is None
    assert "NODE run()" in out


def test_query_without_any_match_exits_not_found(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "query", "zzqqxx", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_NOT_FOUND
    assert "No matching nodes found." in out


def test_query_ambiguous_name_exits_ambiguous(monkeypatch, tmp_path, capsys):
    """A bare name shared by nodes in different files is refused, not guessed (#4511)."""
    code, out = _run(monkeypatch, capsys, "query", ".nonce()", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_AMBIGUOUS
    assert "Ambiguous: '.nonce()' matches 2 nodes in different files." in out
    assert "NODE " not in out


def test_query_ambiguous_seed_exits_ambiguous(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "query", "anything", "--seed", ".nonce()", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_AMBIGUOUS
    assert "Ambiguous: '.nonce()'" in out


def test_query_missing_seed_exits_not_found(monkeypatch, tmp_path, capsys):
    code, out = _run(monkeypatch, capsys,
        "query", "anything", "--seed", "NoSuchSymbolXyz", "--graph", str(_write_graph(tmp_path)))
    assert code == EXIT_NOT_FOUND
    assert "No unique node match for --seed: NoSuchSymbolXyz" in out
