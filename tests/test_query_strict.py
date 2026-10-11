"""`query --strict` starts only from a node the question names outright, and refuses
otherwise instead of seeding the traversal from loose keyword matches.

Without the flag, `query` keeps searching by keywords (unchanged).
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
        ("src_c_listing", "listing", "src/c.ts", "L1"),
        ("src_c_page", "page()", "src/c.ts", "L4"),
        ("src_d_database", "DATABASES", "src/d.ts", "L1"),
    ]
    links = [
        ("src_b_betaclient", "src_b_betaclient_nonce", "method"),
        ("src_a_alphaclient", "src_a_alphaclient_nonce", "method"),
        ("src_c_page", "src_c_listing", "calls"),
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


def _query(monkeypatch, capsys, graph_path, *argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "query", *argv, "--graph", str(graph_path)])
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code, capsys.readouterr().out
    return None, capsys.readouterr().out


_QUESTION = "how does a listing page reach the database"


def test_default_query_still_searches_by_keywords(monkeypatch, tmp_path, capsys):
    code, out = _query(monkeypatch, capsys, _write_graph(tmp_path), _QUESTION)
    assert code is None
    assert "NODE " in out


def test_strict_refuses_a_question_that_names_no_node(monkeypatch, tmp_path, capsys):
    code, out = _query(monkeypatch, capsys, _write_graph(tmp_path), _QUESTION, "--strict")
    assert code == EXIT_NOT_FOUND
    assert "NODE " not in out
    assert f"No node is named exactly '{_QUESTION}'." in out
    assert 'graphify explain "<path>::<Symbol>"' in out
    assert 'graphify path "<A>" "<B>"' in out


def test_strict_refuses_an_ambiguous_name(monkeypatch, tmp_path, capsys):
    code, out = _query(monkeypatch, capsys, _write_graph(tmp_path), ".nonce()", "--strict")
    assert code == EXIT_AMBIGUOUS
    assert "NODE " not in out
    assert "Ambiguous: '.nonce()' matches 2 nodes in different files." in out
    assert "src_a_alphaclient_nonce" in out and "src_b_betaclient_nonce" in out


@pytest.mark.parametrize("name", ["src/b.ts::.nonce()", "src_b_betaclient_nonce"])
def test_strict_starts_from_the_named_node_only(monkeypatch, tmp_path, capsys, name):
    code, out = _query(monkeypatch, capsys, _write_graph(tmp_path), name, "--strict")
    assert code is None
    assert "Start: ['.nonce()']" in out
    assert "NODE BetaClient" in out
    assert "AlphaClient" not in out


def test_strict_refuses_a_file_scoped_miss(monkeypatch, tmp_path, capsys):
    code, out = _query(monkeypatch, capsys, _write_graph(tmp_path), "src/a.ts::NotThere", "--strict")
    assert code == EXIT_NOT_FOUND
    assert "NODE " not in out
    assert "src/a.ts defines no 'NotThere'" in out
