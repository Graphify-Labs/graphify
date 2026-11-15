"""`explain` / get_node refuse a name several nodes of ONE file carry, as `path` does.

The cross-file case was already refused; within one file, `_find_node`'s winning
tier was split by graph iteration order and one node presented as the answer.
"""
from __future__ import annotations

import json

import networkx as nx
import pytest

import graphify.__main__ as mainmod
from graphify.cli import EXIT_AMBIGUOUS
from graphify.serve import _resolve_single_node


_NODES = [
    ("src_x", "x.ts", "src/x.ts", "L1"),
    ("src_x_run", "run()", "src/x.ts", "L3"),
    ("src_x_alphaclient", "AlphaClient", "src/x.ts", "L5"),
    ("src_x_alphaclient_nonce", ".nonce()", "src/x.ts", "L6"),
    ("src_x_betaclient", "BetaClient", "src/x.ts", "L9"),
    ("src_x_betaclient_nonce", ".nonce()", "src/x.ts", "L10"),
    # Sourceless stubs: two files each import the same external interface.
    ("tests_a_php_entitymanagerinterface", "EntityManagerInterface", "", ""),
    ("tests_b_php_entitymanagerinterface", "EntityManagerInterface", "", ""),
]
_LINKS = [
    ("src_x", "src_x_run", "contains"),
    ("src_x_run", "src_x_alphaclient", "calls"),
    ("src_x_run", "src_x_betaclient", "calls"),
    ("src_x_alphaclient", "src_x_alphaclient_nonce", "method"),
    ("src_x_betaclient", "src_x_betaclient_nonce", "method"),
]


def _graph_data(reverse: bool = False) -> dict:
    nodes = [
        {"id": i, "label": lbl, "source_file": sf, "source_location": loc}
        for i, lbl, sf, loc in _NODES
    ]
    return {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": list(reversed(nodes)) if reverse else nodes,
        "links": [
            {"source": a, "target": b, "relation": rel, "confidence": "EXTRACTED"}
            for a, b, rel in _LINKS
        ],
    }


def _write(tmp_path, reverse: bool = False):
    p = tmp_path / ("graph_rev.json" if reverse else "graph.json")
    p.write_text(json.dumps(_graph_data(reverse)))
    return p


def _explain(monkeypatch, capsys, graph_path, label):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    try:
        mainmod.main()
    except SystemExit as exc:
        return capsys.readouterr().out, exc.code
    return capsys.readouterr().out, None


@pytest.mark.parametrize("label", [".nonce()", "src/x.ts::.nonce()"])
def test_explain_refuses_same_file_twins(monkeypatch, tmp_path, capsys, label):
    out, code = _explain(monkeypatch, capsys, _write(tmp_path), label)
    assert f"Ambiguous: '{label}' matches 2 nodes in src/x.ts." in out
    assert "src_x_alphaclient_nonce" in out
    assert "src_x_betaclient_nonce" in out
    assert "Node: .nonce()" not in out
    assert code == EXIT_AMBIGUOUS


def test_explain_refuses_sourceless_stubs(monkeypatch, tmp_path, capsys):
    out, code = _explain(monkeypatch, capsys, _write(tmp_path), "EntityManagerInterface")
    assert out.startswith("Ambiguous: 'EntityManagerInterface' matches 2 nodes")
    assert "tests_a_php_entitymanagerinterface" in out
    assert "tests_b_php_entitymanagerinterface" in out
    assert "Node: EntityManagerInterface" not in out
    assert code == EXIT_AMBIGUOUS


def test_explain_refusal_does_not_depend_on_node_order(monkeypatch, tmp_path, capsys):
    forward, _ = _explain(monkeypatch, capsys, _write(tmp_path), ".nonce()")
    reverse, _ = _explain(monkeypatch, capsys, _write(tmp_path, reverse=True), ".nonce()")
    ids = lambda out: sorted(l.strip() for l in out.splitlines() if l.strip().startswith("id:"))
    assert ids(forward) == ids(reverse) == [
        "id: src_x_alphaclient_nonce", "id: src_x_betaclient_nonce",
    ]


def test_explain_node_id_still_names_one_twin(monkeypatch, tmp_path, capsys):
    out, code = _explain(monkeypatch, capsys, _write(tmp_path), "src_x_betaclient_nonce")
    assert "ID:        src_x_betaclient_nonce" in out
    assert "Ambiguous" not in out
    assert code is None


def test_explain_file_path_still_resolves_to_the_file_node(monkeypatch, tmp_path, capsys):
    """A file path matches the file node and its members: precedence, not a tie."""
    out, code = _explain(monkeypatch, capsys, _write(tmp_path), "src/x.ts")
    assert "ID:        src_x\n" in out
    assert "Ambiguous" not in out
    assert code is None


def test_get_node_resolver_refuses_same_file_twins():
    """get_node / get_neighbors share `_resolve_single_node` with the same refusal."""
    G = nx.node_link_graph({**_graph_data(), "directed": True}, edges="links")
    nid, err = _resolve_single_node(G, ".nonce()")
    assert nid is None
    assert err is not None and err.startswith("Ambiguous: '.nonce()' matches 2 nodes in src/x.ts.")
    nid, err = _resolve_single_node(G, "src_x_alphaclient_nonce")
    assert (nid, err) == ("src_x_alphaclient_nonce", None)
