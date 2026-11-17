from __future__ import annotations

import json

import networkx as nx
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.deadcode import dead_code_candidates


def _fn(G, nid, label, src="app.py", line=1, **attrs):
    G.add_node(nid, label=label, source_file=src, source_location=f"L{line}",
               file_type="code", _origin="ast", _callable=True, **attrs)


def _graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("file", label="app.py", source_file="app.py", file_type="code", _origin="ast")
    _fn(G, "used", "used()", line=2)
    _fn(G, "unused", "unused()", line=5)
    _fn(G, "island_a", "island_a()", line=8)  # only called by island_b, which nobody calls
    _fn(G, "island_b", "island_b()", line=9)
    _fn(G, "nested", "helper()", line=3)
    _fn(G, "main", "main()", line=20)
    _fn(G, "test", "test_it()", src="tests/test_app.py")
    _fn(G, "Cls", "Cls", line=30, _callable_class=True)
    _fn(G, "meth", ".run()", line=31)
    G.add_node("doc", label="README", source_file="README.md", file_type="document")
    G.add_edge("file", "used", relation="calls")
    G.add_edge("file", "Cls", relation="calls")
    G.add_edge("file", "unused", relation="contains")  # containment is not usage
    G.add_edge("island_b", "island_a", relation="calls")
    G.add_edge("used", "nested", relation="contains")
    G.add_edge("Cls", "meth", relation="method")
    G.add_edge("doc", "unused", relation="references")  # a doc mention does not make code live
    return G


def test_unreached_callables_and_islands_are_candidates():
    labels = [c["label"] for c in dead_code_candidates(_graph())]
    assert labels == ["unused()", "island_a()", "island_b()"]


def test_entry_points_tests_nested_and_methods_of_live_classes_are_not():
    labels = {c["label"] for c in dead_code_candidates(_graph())}
    assert not labels & {"main()", "test_it()", "helper()", ".run()", "used()", "Cls"}


def test_overriding_methods_are_never_candidates():
    G = _graph()
    _fn(G, "Base", "Base", line=40, _callable_class=True)
    _fn(G, "Child", "Child", line=50, _callable_class=True)
    _fn(G, "base_run", ".go()", line=41)
    _fn(G, "child_run", ".go()", line=51)
    G.add_edge("Base", "base_run", relation="method")
    G.add_edge("Child", "child_run", relation="method")
    G.add_edge("Child", "Base", relation="inherits")
    labels = [c["id"] for c in dead_code_candidates(G)]
    assert "child_run" not in labels
    assert "Child" in labels  # the unreached class itself is still reported


def test_dead_code_cli_json(monkeypatch, capsys, tmp_path):
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(_graph(), edges="links")), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "dead-code", "--graph", str(gp), "--json"])

    mainmod.main()

    result = json.loads(capsys.readouterr().out)
    assert [c["label"] for c in result] == ["unused()", "island_a()", "island_b()"]
