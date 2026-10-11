"""`graphify benchmark --questions`: is the right file in what query_graph shows?"""
from __future__ import annotations

import json
import subprocess
import sys

import networkx as nx
import pytest
from networkx.readwrite import json_graph

from graphify.benchmark import _answer_files, load_benchmark_questions, run_answer_benchmark


def _graph(tmp_path):
    G = nx.DiGraph()
    G.add_node("redirects", label="resolve_redirects()", source_file="pkg/sessions.py", source_location="L10")
    G.add_node("location", label="get_redirect_target()", source_file="pkg/utils.py", source_location="L5")
    G.add_node("cookies", label="merge_cookies()", source_file="pkg/cookies.py", source_location="L1")
    G.add_edge("redirects", "location", relation="calls", confidence="EXTRACTED")
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    return path


def test_questions_load_from_a_json_list_or_json_lines(tmp_path):
    as_list = tmp_path / "q.json"
    as_list.write_text(json.dumps([{"question": "a", "files": ["./pkg\\a.py"]}]), encoding="utf-8")
    as_lines = tmp_path / "q.jsonl"
    as_lines.write_text('{"question": "a", "files": ["pkg/a.py"]}\n\n{"question": "b", "files": ["b.py"]}\n',
                        encoding="utf-8")
    assert load_benchmark_questions(as_list) == [{"question": "a", "files": ["pkg/a.py"]}]
    assert [q["question"] for q in load_benchmark_questions(as_lines)] == ["a", "b"]


@pytest.mark.parametrize("item", [{"files": ["a.py"]}, {"question": "", "files": ["a.py"]},
                                  {"question": "a", "files": []}, {"question": "a"}, ["a"]])
def test_a_question_without_text_or_files_is_rejected(tmp_path, item):
    path = tmp_path / "q.json"
    path.write_text(json.dumps([item]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_benchmark_questions(path)


def test_answer_files_are_read_in_shown_order_once():
    text = ("Traversal: BFS depth=3 | Start: ['x'] | 3 nodes found\n\n"
            "NODE x() [src=pkg/b.py loc=L1 community=0]\n"
            "NODE y() [src=pkg\\a.py loc=L2 community=0]\n"
            "NODE z() [src=pkg/b.py loc=L9 community=0]\n"
            "EDGE x() --calls [EXTRACTED]--> y() at=pkg/c.py:L3\n")
    assert _answer_files(text) == ["pkg/b.py", "pkg/a.py"]


def test_rank_and_hits_of_the_expected_files(tmp_path):
    result = run_answer_benchmark(str(_graph(tmp_path)), [
        {"question": "resolve redirects", "files": ["pkg/sessions.py"]},
        {"question": "resolve redirects", "files": ["pkg/utils.py"]},
        {"question": "resolve redirects", "files": ["pkg/cookies.py"]},
    ])
    assert [p["rank"] for p in result["per_question"]] == [0, 1, None]
    assert (result["hit_at_1"], result["hit_at_3"], result["hit_at_5"], result["found"]) == (1, 2, 2, 2)
    assert result["questions"] == 3 and result["over_budget"] == 0


def _cli(*args):
    return subprocess.run([sys.executable, "-m", "graphify", "benchmark", *args],
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_questions_json_output(tmp_path):
    questions = tmp_path / "q.jsonl"
    questions.write_text('{"question": "resolve redirects", "files": ["pkg/sessions.py"]}\n', encoding="utf-8")
    run = _cli(str(_graph(tmp_path)), "--questions", str(questions), "--json", "--budget", "500")
    assert run.returncode == 0, run.stderr
    data = json.loads(run.stdout)
    assert data["hit_at_1"] == 1 and data["token_budget"] == 500


def test_cli_rejects_a_bad_questions_file_and_unknown_options(tmp_path):
    bad = tmp_path / "q.json"
    bad.write_text("[{}]", encoding="utf-8")
    graph = str(_graph(tmp_path))
    run = _cli(graph, "--questions", str(bad))
    assert run.returncode == 1 and "--questions" in run.stderr
    run = _cli(graph, "--qestions", str(bad))
    assert run.returncode == 1 and "unknown option" in run.stderr


def test_cli_without_questions_is_still_the_token_benchmark(tmp_path):
    # the sample questions match nothing in this tiny graph: the token benchmark's own message
    run = _cli(str(_graph(tmp_path)))
    assert run.returncode == 0, run.stderr
    assert "sample questions" in run.stdout and "answer benchmark" not in run.stdout
