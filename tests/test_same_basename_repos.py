"""Same-named files from two repos of a merged graph are not one file (#4512).

A merged graph keeps `source_file` relative to each repo, so `web/dup.py` and `ml/dup.py` both
read `dup.py`. The same-file check used that bare path and called them one file.
"""
from __future__ import annotations

import json

import pytest

import graphify.__main__ as mainmod
from graphify.cli import EXIT_AMBIGUOUS
from graphify.serve import _load_graph, _resolve_single_node


def _dup_graph(tmp_path, tagged=True):
    """Two `Config` nodes in `dup.py`, one per repo. Untagged graphs carry no `repo` attribute."""
    nodes = []
    for nid, community, repo in (("web::dup_config", 0, "web"), ("ml::dup_config", 1, "ml")):
        node = {"id": nid, "label": "Config", "source_file": "dup.py",
                "source_location": "L1", "community": community}
        if tagged:
            node["repo"] = repo
        nodes.append(node)
    path = tmp_path / "graph.json"
    path.write_text(json.dumps({"directed": False, "multigraph": False, "graph": {},
                                "nodes": nodes, "links": []}))
    return _load_graph(str(path))


def test_explain_names_both_repos_not_one_file(tmp_path):
    G = _dup_graph(tmp_path)
    nid, refusal = _resolve_single_node(G, "Config")
    assert nid is None
    assert "web/dup.py" in refusal and "ml/dup.py" in refusal
    assert "in dup.py" not in refusal


def test_explain_hint_gives_the_full_node_id_for_same_basename(tmp_path):
    _nid, refusal = _resolve_single_node(_dup_graph(tmp_path), "Config")
    assert "web::dup_config" in refusal and "ml::dup_config" in refusal
    assert "the same path exists in more than one repo" in refusal


def test_full_node_id_still_resolves(tmp_path):
    G = _dup_graph(tmp_path)
    assert _resolve_single_node(G, "web::dup_config") == ("web::dup_config", None)


def test_path_endpoint_names_both_repos(monkeypatch, tmp_path, capsys):
    _dup_graph(tmp_path)
    graph_path = tmp_path / "graph.json"
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
                        ["graphify", "path", "Config", "Config", "--graph", str(graph_path)])
    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()
    assert exc_info.value.code == EXIT_AMBIGUOUS
    err = capsys.readouterr().err
    assert "web/dup.py" in err and "ml/dup.py" in err


def test_same_repo_wording_is_unchanged(tmp_path):
    """No `repo` attribute (a single-repo graph): both nodes are one file, as before."""
    G = _dup_graph(tmp_path, tagged=False)
    nid, refusal = _resolve_single_node(G, "Config")
    assert nid is None and "in dup.py" in refusal
