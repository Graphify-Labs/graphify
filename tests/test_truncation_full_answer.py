"""A truncated answer says how to get all of it: `explain --all`, and the exact
token budget that returns the complete `query` / get_neighbors output.
"""
from __future__ import annotations

import json
import re

import networkx as nx

import graphify.__main__ as mainmod
from graphify.serve import _cut_lines_to_budget, _subgraph_to_text


def _write_hub_graph(tmp_path, n_callers=25):
    nodes = [{"id": "hub", "label": "hub()", "source_file": "lib/hub.py"}]
    links = []
    for i in range(n_callers):
        fpath = f"app/mod{i % 3}.py"
        nodes.append({"id": f"caller_{i}", "label": f"caller_{i}()", "source_file": fpath})
        links.append({"source": f"caller_{i}", "target": "hub", "relation": "calls",
                      "confidence": "EXTRACTED", "source_file": fpath,
                      "source_location": f"L{10 + i}"})
    p = tmp_path / "graph.json"
    p.write_text(json.dumps({"directed": False, "multigraph": False, "graph": {},
                             "nodes": nodes, "links": links}))
    return p


def _explain(monkeypatch, capsys, graph_path, *extra):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "hub", "--graph", str(graph_path), *extra])
    mainmod.main()
    return capsys.readouterr().out


def test_explain_cut_names_the_total_and_the_option(monkeypatch, tmp_path, capsys):
    out = _explain(monkeypatch, capsys, _write_hub_graph(tmp_path))
    assert "Connections (25):" in out
    assert "... and 5 more (--all lists all 25)" in out


def test_explain_all_lists_every_connection(monkeypatch, tmp_path, capsys):
    out = _explain(monkeypatch, capsys, _write_hub_graph(tmp_path), "--all")
    listed = [l for l in out.splitlines() if l.startswith("  <-- caller_")]
    assert len(listed) == 25
    assert "more" not in out
    assert "Grouped by file:" not in out


def _budget_hint(text: str) -> int:
    m = re.search(r"token budget to (\d+)", text)
    assert m, f"no budget hint in: {text[:300]!r}"
    return int(m.group(1))


def _chain_graph(n=60):
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"node_number_{i}", source_file=f"src/f{i}.py",
                   source_location="L1", community=0)
        if i:
            G.add_edge(f"n{i - 1}", f"n{i}", relation="calls", confidence="EXTRACTED")
    return G


def test_query_truncation_gives_the_exact_budget_for_the_full_answer():
    G = _chain_graph()
    nodes, edges = set(G.nodes), list(G.edges())
    cut = _subgraph_to_text(G, nodes, edges, token_budget=50, seeds=["n0"])
    assert cut.startswith("[!] TRUNCATED")
    needed = _budget_hint(cut)
    assert f"--budget {needed}" in cut and f"token_budget={needed}" in cut
    full = _subgraph_to_text(G, nodes, edges, token_budget=needed, seeds=["n0"])
    assert "TRUNCATED" not in full
    assert full.count("\nNODE ") + full.startswith("NODE ") == 60
    assert full.count("\nEDGE ") == 59
    # The smallest such budget: one token less still cuts.
    assert _subgraph_to_text(G, nodes, edges, token_budget=needed - 1, seeds=["n0"]).startswith(
        "[!] TRUNCATED")


def test_line_list_truncation_gives_the_exact_budget_for_the_full_answer():
    lines = [f"  --> node{i} [calls] [EXTRACTED]" for i in range(200)]
    cut = _cut_lines_to_budget(lines, token_budget=20, narrow_hint="use relation_filter")
    needed = _budget_hint(cut)
    assert f"token_budget={needed}" in cut
    assert _cut_lines_to_budget(lines, token_budget=needed, narrow_hint="x") == "\n".join(lines)
    assert _cut_lines_to_budget(lines, token_budget=needed - 1, narrow_hint="x").startswith(
        "[!] TRUNCATED")
