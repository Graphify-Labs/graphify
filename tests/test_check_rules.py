from __future__ import annotations

import json

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.rules import check_rules, load_rules, to_sarif


def _graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("view", label="render()", source_file="src/ui/view.py")
    G.add_node("repo", label="save()", source_file="src/db/repo.py")
    G.add_node("svc", label="handle()", source_file="src/svc/service.py")
    G.add_node("a", label="a.py", source_file="src/a.py")
    G.add_node("b", label="b.py", source_file="src/b.py")
    G.add_edge("view", "repo", relation="calls", confidence="EXTRACTED", source_location="L12")
    G.add_edge("view", "svc", relation="calls", confidence="EXTRACTED", source_location="L13")
    G.add_edge("svc", "repo", relation="calls", confidence="AMBIGUOUS", source_location="L3")
    G.add_edge("a", "b", relation="imports_from", source_file="src/a.py")
    G.add_edge("b", "a", relation="imports_from", source_file="src/b.py")
    return G


def test_forbidden_dependency_is_reported_with_its_line():
    rules = {"forbid": [{"from": "src/ui/*", "to": "src/db/*"}]}
    [v] = check_rules(_graph(), rules)
    assert v["file"] == "src/ui/view.py"
    assert v["line"] == 12
    assert "src/db/repo.py" in v["message"]


def test_ambiguous_edges_never_fail_the_gate():
    rules = {"forbid": [{"from": "src/svc/*", "to": "src/db/*"}], "include_inferred": True}
    assert check_rules(_graph(), rules) == []


def test_inferred_edges_count_only_when_opted_in():
    G = _graph()
    G.add_edge("svc", "repo", relation="calls", confidence="INFERRED", source_location="L3")
    rules: dict = {"forbid": [{"from": "src/svc/*", "to": "src/db/*"}]}
    assert check_rules(G, rules) == []
    rules["include_inferred"] = True
    assert len(check_rules(G, rules)) == 1


def test_document_mentions_are_not_dependencies():
    G = _graph()
    G.add_node("readme", label="README", source_file="src/ui/README.md", file_type="document")
    G.add_edge("readme", "repo", relation="references", confidence="EXTRACTED")
    assert len(check_rules(G, {"forbid": [{"from": "src/ui/*", "to": "src/db/*"}]})) == 1  # only view.py


def test_relation_filter_limits_the_rule():
    rules = {"forbid": [{"from": "src/ui/*", "to": "src/db/*", "relations": ["imports_from"]}]}
    assert check_rules(_graph(), rules) == []


def test_import_cycles_are_reported_when_enabled():
    [v] = check_rules(_graph(), {"no_import_cycles": True})
    assert v["rule"] == "graphify/import-cycle"
    assert "src/a.py" in v["message"] and "src/b.py" in v["message"]


@pytest.mark.parametrize("bad", [
    [],
    {"forbid": [{"from": "x"}]},
    {"forbid": [{"from": "x", "to": "y", "relations": "calls"}]},
    {"no_import_cycles": "yes"},
    {"include_inferred": 1},
    {"max_cycle_length": 1},
    {"forbidd": []},
])
def test_invalid_rules_are_rejected(tmp_path, bad):
    p = tmp_path / "r.json"
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError):
        load_rules(p)


def test_sarif_shape():
    v = check_rules(_graph(), {"forbid": [{"from": "src/ui/*", "to": "src/db/*"}]})
    sarif = to_sarif(v, "0.0.0")
    assert sarif["version"] == "2.1.0"
    [result] = sarif["runs"][0]["results"]
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "src/ui/view.py"
    assert loc["region"]["startLine"] == 12


def _run(monkeypatch, capsys, tmp_path, rules, *extra):
    out = tmp_path / "graphify-out"
    out.mkdir(exist_ok=True)
    gp = out / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(_graph(), edges="links")), encoding="utf-8")
    (tmp_path / "graphify-rules.json").write_text(json.dumps(rules), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "check", "--graph", str(gp), *extra])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    return exc.value.code, capsys.readouterr()


def test_cli_exits_1_on_violations_and_finds_rules_next_to_the_root(monkeypatch, capsys, tmp_path):
    code, cap = _run(monkeypatch, capsys, tmp_path, {"forbid": [{"from": "src/ui/*", "to": "src/db/*"}]})
    assert code == 1
    assert "1 violation" in cap.out


def test_cli_exits_0_when_clean_and_writes_sarif(monkeypatch, capsys, tmp_path):
    sarif_path = tmp_path / "out.sarif"
    code, _ = _run(monkeypatch, capsys, tmp_path, {"forbid": []}, "--sarif", str(sarif_path))
    assert code == 0
    assert json.loads(sarif_path.read_text(encoding="utf-8"))["runs"][0]["results"] == []


def test_cli_exits_2_on_bad_rules(monkeypatch, capsys, tmp_path):
    code, cap = _run(monkeypatch, capsys, tmp_path, {"forbid": "nope"})
    assert code == 2
    assert "'forbid' must be a list" in cap.err


def test_cli_exits_2_when_rules_path_is_unreadable(monkeypatch, capsys, tmp_path):
    rules_dir = tmp_path / "rules-as-dir"
    rules_dir.mkdir()
    code, cap = _run(monkeypatch, capsys, tmp_path, {"forbid": []}, "--rules", str(rules_dir))
    assert code == 2
    assert "cannot read rules file" in cap.err


def test_cli_exits_2_when_sarif_cannot_be_written(monkeypatch, capsys, tmp_path):
    sarif_dir = tmp_path / "sarif-as-dir"
    sarif_dir.mkdir()
    code, cap = _run(monkeypatch, capsys, tmp_path, {"forbid": []}, "--sarif", str(sarif_dir))
    assert code == 2
    assert "cannot write SARIF" in cap.err


def test_undirected_graph_json_keeps_dependency_direction(monkeypatch, capsys, tmp_path):
    # graphify's default graph.json is undirected; to_json writes each link's true
    # direction into source/target and load_graph reads it back directed.
    data = json_graph.node_link_data(_graph(), edges="links")
    data["directed"] = False
    out = tmp_path / "graphify-out"
    out.mkdir()
    gp = out / "graph.json"
    gp.write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "graphify-rules.json").write_text(
        json.dumps({"forbid": [{"from": "src/db/*", "to": "src/ui/*"}]}), encoding="utf-8"
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "check", "--graph", str(gp)])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0  # view -> repo is not repo -> view


def test_in_memory_undirected_graph_uses_true_edge_direction():
    G = nx.Graph()  # build()'s default; edge order follows node insertion, not direction
    G.add_node("repo", source_file="src/db/repo.py")  # inserted first, so stored as (repo, view)
    G.add_node("view", source_file="src/ui/view.py")
    G.add_edge("view", "repo", relation="calls", confidence="EXTRACTED", _src="view", _tgt="repo")
    assert list(G.edges()) == [("repo", "view")]
    assert len(check_rules(G, {"forbid": [{"from": "src/ui/*", "to": "src/db/*"}]})) == 1
    assert check_rules(G, {"forbid": [{"from": "src/db/*", "to": "src/ui/*"}]}) == []  # not reversed
