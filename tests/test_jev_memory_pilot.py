"""Offline contract tests for the Jev memory pilot."""

import json
import subprocess
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from tools.jev_memory_pilot import candidate_pool, load_case


@pytest.fixture
def pilot_repo(tmp_path: Path) -> tuple[Path, Path, dict]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    for name in ("a.py", "b.py"):
        (repo / name).write_text("def same_label(): pass\n")
    subprocess.run(["git", "add", "a.py", "b.py"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
         "commit", "-qm", "fixture"], cwd=repo, check=True,
    )
    graph = nx.Graph()
    for name in ("a.py", "b.py"):
        graph.add_node(f"{name}::same_label", label="same_label", type="function",
                       source_file=name, source_location="L1")
    data = json_graph.node_link_data(graph, edges="links")
    data["built_at_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
    ).strip()
    graph_path = repo / "graphify-out" / "graph.json"
    graph_path.parent.mkdir()
    graph_path.write_text(json.dumps(data))
    return repo, graph_path, data


def test_candidate_pool_preserves_same_label_ids_and_rejects_stale_source(pilot_repo):
    repo, graph_path, data = pilot_repo
    pool = candidate_pool(graph_path, repo, "same_label")
    assert len(pool) == 2
    assert {row["node_id"] for row in pool} == {"a.py::same_label", "b.py::same_label"}
    assert [row["baseline_rank"] for row in pool] == [1, 2]

    data["built_at_commit"] = "0" * 40
    graph_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="graph commit differs"):
        candidate_pool(graph_path, repo, "same_label")

    data["built_at_commit"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
    ).strip()
    graph_path.write_text(json.dumps(data))
    (repo / "a.py").write_text("def edited(): pass\n")
    with pytest.raises(ValueError, match="source has uncommitted edits"):
        candidate_pool(graph_path, repo, "same_label")


def test_candidate_pool_rejects_untracked_source(pilot_repo):
    repo, graph_path, data = pilot_repo
    (repo / "c.py").write_text("def same_label(): pass\n")
    data["nodes"].append({"id": "c.py::same_label", "label": "same_label",
                          "type": "function", "source_file": "c.py", "source_location": "L1"})
    graph_path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="not tracked"):
        candidate_pool(graph_path, repo, "same_label")


def test_load_case_checks_full_graph_not_candidate_pool(tmp_path):
    path = tmp_path / "cases.json"
    data = {
        "observations": [{"id": "o1", "project": "demo", "date": "2026-10-17",
                          "summary": "Synthetic memory.", "source_ref": "synthetic-o1"}],
        "cases": [{"id": "q1", "question": "Where is the handler?",
                   "relevant_node_ids": ["node-outside-top-ten"],
                   "relevant_pairs": [["node-outside-top-ten", "o1"]],
                   "observation_ids": ["o1"]}],
    }
    path.write_text(json.dumps(data))
    case = load_case(path, "q1", {"node-outside-top-ten", "candidate"}, "demo")
    assert case["relevant_node_ids"] == ["node-outside-top-ten"]
    assert case["observations"][0]["id"] == "o1"
    with pytest.raises(ValueError, match="unknown node"):
        load_case(path, "q1", {"candidate"}, "demo")
    with pytest.raises(ValueError, match="project"):
        load_case(path, "q1", {"node-outside-top-ten"}, "other")


@pytest.mark.parametrize(
    "corpus, message",
    [
        ({"cases": []}, "observation and case lists"),
        ({"observations": [{"id": "o1"}, {"id": "o1"}], "cases": []}, "duplicate"),
        ({"observations": [], "cases": [{"id": "q1", "question": "x",
                                       "relevant_node_ids": [], "relevant_pairs": [],
                                       "observation_ids": ["missing"]}]}, "unknown observation"),
        ({"observations": [], "cases": [{"id": "q1", "question": "x",
                                       "relevant_node_ids": [], "relevant_pairs": [],
                                       "observation_ids": ["a", "b", "c", "d"]}]},
         "invalid observation selection"),
    ],
)
def test_load_case_rejects_invalid_corpus(tmp_path, corpus, message):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(corpus))
    with pytest.raises(ValueError, match=message):
        load_case(path, "q1", set(), "demo")
