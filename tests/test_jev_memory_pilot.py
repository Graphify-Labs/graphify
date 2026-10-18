"""Offline contract tests for the Jev memory pilot."""

import json
import subprocess
from pathlib import Path

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from tools.jev_memory_pilot import (
    apply_decisions,
    candidate_pool,
    load_case,
    main,
    query_with_decisions,
    read_sidecar,
)


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


def test_apply_decisions_promotes_only_supported_relevant_pairs():
    candidates = [{"node_id": "a", "baseline_rank": 1},
                  {"node_id": "b", "baseline_rank": 2}]
    observations = [{"id": "o1"}]
    no_op, suggestions = apply_decisions(
        candidates, observations, {}, eligible_node_ids={"a", "b"}, threshold=0.8,
    )
    assert no_op == candidates and suggestions == []

    answers = {("a", "o1"): {"choice": "unrelated", "probability": 0.99},
               ("b", "o1"): {"choice": "relevant", "probability": 0.9}}
    ordered, suggestions = apply_decisions(
        candidates, observations, answers, eligible_node_ids={"a", "b"}, threshold=0.8,
    )
    assert [item["node_id"] for item in ordered] == ["b", "a"]
    assert [(item["node_id"], item["observation_id"]) for item in suggestions] == [("b", "o1")]

    tied = {("a", "o1"): {"choice": "relevant", "probability": 0.9},
            ("b", "o1"): {"choice": "relevant", "probability": 0.9}}
    ordered, _ = apply_decisions(
        candidates, observations, tied, eligible_node_ids={"a", "b"}, threshold=0.8,
    )
    assert [item["node_id"] for item in ordered] == ["a", "b"]
    insufficient = {("a", "o1"): {"choice": "insufficient_evidence", "probability": 0.99},
                    ("b", "o1"): {"choice": "unrelated", "probability": 0.99}}
    ordered, suggestions = apply_decisions(
        candidates, observations, insufficient, eligible_node_ids={"a", "b"}, threshold=0.8,
    )
    assert ordered == candidates and suggestions == []

    for invalid in (
        {("b", "o1"): answers[("b", "o1")]},
        {**answers, ("unknown", "o1"): answers[("b", "o1")]},
        {**answers, ("b", "o1"): {"choice": "relevant", "probability": float("nan")}},
    ):
        ordered, suggestions = apply_decisions(
            candidates, observations, invalid, eligible_node_ids={"a", "b"}, threshold=0.8,
        )
        assert ordered == candidates and suggestions == []


def test_query_fallback_matches_original_and_does_not_mutate_graph(pilot_repo, tmp_path, monkeypatch):
    repo, graph_path, _ = pilot_repo
    import hashlib
    import os
    import sys

    question = "same_label why"
    learning = graph_path.parent / ".graphify_learning.json"
    learning.write_text("{}")
    graph_before = hashlib.sha256(graph_path.read_bytes()).hexdigest()
    learning_before = hashlib.sha256(learning.read_bytes()).hexdigest()
    baseline = subprocess.run(
        [sys.executable, "-m", "graphify", "query", question, "--graph", str(graph_path)],
        check=True, capture_output=True, text=True,
        env={**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"},
    ).stdout
    log_path = tmp_path / "private-query-log.jsonl"
    monkeypatch.setenv("GRAPHIFY_QUERY_LOG", str(log_path))
    pool = candidate_pool(graph_path, repo, question)
    case = {"id": "q1", "question": question,
            "observations": [{"id": "o1", "source_ref": "synthetic-o1",
                              "summary": "secret-canary-do-not-write"}]}
    result = query_with_decisions(
        graph_path, repo, case, pool, {}, eligible_node_ids=set(), threshold=0.8,
    )
    assert result == baseline
    assert hashlib.sha256(graph_path.read_bytes()).hexdigest() == graph_before
    assert hashlib.sha256(learning.read_bytes()).hexdigest() == learning_before
    assert not log_path.exists()
    sidecar = graph_path.parent / "jev-memory-decisions.json"
    metadata = read_sidecar(sidecar, graph_path, subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True,
    ).strip())
    assert "secret-canary-do-not-write" not in sidecar.read_text()
    assert question not in sidecar.read_text()
    assert metadata["observation_ids"] == ["o1"]
    with pytest.raises(ValueError, match="stale"):
        read_sidecar(sidecar, graph_path, "0" * 40)
    graph_path.write_bytes(graph_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="stale"):
        read_sidecar(sidecar, graph_path, metadata["head"])


def test_query_uses_seeds_only_after_top_three_change(pilot_repo, monkeypatch):
    repo, graph_path, _ = pilot_repo
    pool = candidate_pool(graph_path, repo, "same_label")
    case = {"id": "q2", "question": "same_label",
            "observations": [{"id": "o1", "source_ref": "synthetic-o1",
                              "summary": "synthetic summary"}]}
    first, second = (item["node_id"] for item in pool)
    answers = {(first, "o1"): {"choice": "unrelated", "probability": 0.99},
               (second, "o1"): {"choice": "relevant", "probability": 0.91}}
    real_run = subprocess.run
    seen = []

    def capture(args, **kwargs):
        seen.append(args)
        return real_run(args, **kwargs)

    monkeypatch.setattr("tools.jev_memory_pilot.subprocess.run", capture)
    output = query_with_decisions(
        graph_path, repo, case, pool, answers,
        eligible_node_ids={first, second}, threshold=0.8, model_id="test-jev",
    )
    assert seen[0][-4:] == ["--seed", second, "--seed", first]
    assert f"Suggested memory link: {second}" in output
    sidecar = read_sidecar(graph_path.parent / "jev-memory-decisions.json", graph_path,
                           subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                   cwd=repo, text=True).strip())
    assert sidecar["model"] == "test-jev"
    assert len(sidecar["decisions"]) == 2


def test_offline_cli_reads_synthetic_decisions(pilot_repo, tmp_path, capsys):
    repo, graph_path, _ = pilot_repo
    pool = candidate_pool(graph_path, repo, "same_label")
    first, second = (item["node_id"] for item in pool)
    corpus = tmp_path / "corpus.json"
    corpus.write_text(json.dumps({
        "observations": [{"id": "o1", "project": "demo", "date": "2026-10-17",
                          "summary": "Synthetic note.", "source_ref": "synthetic-o1"}],
        "cases": [{"id": "q1", "question": "same_label", "relevant_node_ids": [second],
                   "relevant_pairs": [[second, "o1"]], "observation_ids": ["o1"]}],
    }))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"decisions": [
        {"node_id": first, "observation_id": "o1", "choice": "unrelated", "probability": 0.9},
        {"node_id": second, "observation_id": "o1", "choice": "relevant", "probability": 0.9},
    ]}))
    assert main(["--repo", str(repo), "--graph", str(graph_path), "--corpus", str(corpus),
                 "--case-id", "q1", "--project", "demo", "--decisions", str(decisions)]) == 0
    assert f"Suggested memory link: {second}" in capsys.readouterr().out
