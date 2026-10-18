from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

import graphify.__main__ as mainmod
from graphify.cochange import cochange_analysis, git_commit_files


def _graph() -> nx.DiGraph:
    G = nx.DiGraph()
    for f in ("a.py", "b.py", "c.py", "cfg.toml"):
        G.add_node(f, label=f, source_file=f)
    G.add_edge("a.py", "b.py", relation="imports")
    return G


def test_unlinked_pair_is_hidden_coupling_linked_pair_is_not():
    commits = [["a.py", "b.py", "c.py", "cfg.toml"]] * 3 + [["c.py"]]
    result = cochange_analysis(_graph(), commits, Path("."), min_count=3)
    pairs = [h["files"] for h in result["hidden_coupling"]]
    assert ["a.py", "b.py"] not in pairs  # graph edge explains it
    assert ["c.py", "cfg.toml"] in pairs
    hit = next(h for h in result["hidden_coupling"] if h["files"] == ["c.py", "cfg.toml"])
    assert hit["commits"] == 3
    assert hit["confidence"] == 1.0  # every cfg.toml change also touched c.py


def test_bulk_commits_and_unknown_files_are_ignored():
    bulk = [f"gen/{i}.py" for i in range(40)] + ["c.py", "cfg.toml"]
    commits = [sorted(bulk)] * 5 + [["c.py", "not_in_graph.py"]] * 5
    result = cochange_analysis(_graph(), commits, Path("."), min_count=3, max_files_per_commit=30)
    assert result["commits_skipped"] == 5
    assert result["hidden_coupling"] == []


def test_hotspots_rank_churn_times_linked_files():
    result = cochange_analysis(_graph(), [["a.py"]] * 4 + [["b.py"]], Path("."))
    assert [h["file"] for h in result["hotspots"]] == ["a.py", "b.py"]
    assert result["hotspots"][0]["score"] == 4


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
         "-C", str(repo), *args],
        check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(var, raising=False)
    _git(tmp_path, "init", "-q")
    sub = tmp_path / "src"
    sub.mkdir()
    for i in range(3):
        for f in ("c.py", "cfg.toml"):
            (sub / f).write_text(str(i), encoding="utf-8")
        (tmp_path / "outside.txt").write_text(str(i), encoding="utf-8")
        _git(tmp_path, "add", "-A")
        _git(tmp_path, "commit", "-q", "-m", f"c{i}")
    return sub


def test_git_paths_are_relative_to_a_subdirectory_scan_root(repo):
    commits = git_commit_files(repo)
    assert commits == [["c.py", "cfg.toml"]] * 3  # outside.txt is out of scope


def test_cochange_cli_end_to_end(repo, monkeypatch, capsys):
    out_dir = repo / "graphify-out"
    out_dir.mkdir()
    graph_path = out_dir / "graph.json"
    graph_path.write_text(json.dumps(json_graph.node_link_data(_graph(), edges="links")), encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "cochange", "--graph", str(graph_path), "--json"])

    mainmod.main()

    result = json.loads(capsys.readouterr().out)
    assert result["hidden_coupling"][0]["files"] == ["c.py", "cfg.toml"]


def test_windows_style_source_files_match_git_paths():
    G = nx.DiGraph()
    G.add_node("c", source_file=r"src\c.py")
    G.add_node("cfg", source_file=r"src\cfg.toml")
    result = cochange_analysis(G, [["src/c.py", "src/cfg.toml"]] * 3, Path("."))
    assert result["hidden_coupling"][0]["files"] == ["src/c.py", "src/cfg.toml"]


def test_missing_git_binary_is_a_runtime_error(monkeypatch, tmp_path):
    def boom(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr("graphify.cochange.subprocess.run", boom)
    with pytest.raises(RuntimeError, match="cannot run git"):
        git_commit_files(tmp_path)
