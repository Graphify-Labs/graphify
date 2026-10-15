"""`learned` lets the work memory steer a query: nodes that past useful answers to a similar question cited become
start nodes, ahead of the keyword seeds.

The memory is `graphify save-result --outcome useful` plus `graphify reflect --graph`, which writes the
.graphify_learning.json sidecar. A past question counts when the new question covers at least
_LEARNED_MIN_OVERLAP of its query terms. Only preferred and tentative, non-stale lessons count, and only their useful
provenance. No embeddings. Default (learned=False) output is unchanged."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from networkx.readwrite import json_graph

from graphify.ingest import save_query_result
from graphify.reflect import load_learning_overlay, reflect
from graphify.serve import _learned_seeds, _query_graph_text


def _graph():
    G = nx.Graph()
    G.add_node("bp", label="blueprints.py", source_file="src/flask/blueprints.py", source_location="L1")
    G.add_node("bp_init", label="Blueprint.__init__()", source_file="src/flask/blueprints.py", source_location="L180")
    G.add_node("app", label="Flask", source_file="src/flask/app.py", source_location="L100")
    G.add_node("route", label="route()", source_file="src/flask/scaffold.py", source_location="L400")
    G.add_node("cli", label="FlaskGroup", source_file="src/flask/cli.py", source_location="L520")
    for a, b in (("bp", "bp_init"), ("app", "route"), ("app", "bp"), ("cli", "app")):
        G.add_edge(a, b, relation="calls", confidence="EXTRACTED")
    return G


def _lesson(question, status="tentative", outcome="useful", stale=False, score=1.0):
    return {"status": status, "score": score, "stale": stale,
            "provenance": [{"q": question, "date": "2026-10-01T00:00:00+00:00", "outcome": outcome}]}


def test_a_question_in_other_words_finds_the_node_a_past_useful_answer_cited():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("Raise error when blueprint name contains a dot")}
    assert _learned_seeds(G, "registering a blueprint whose name has a dot in it should raise an error") == ["bp"]


def test_an_unrelated_question_gets_no_learned_node():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("Raise error when blueprint name contains a dot")}
    assert _learned_seeds(G, "the CLI group ignores the app factory") == []


def test_a_single_shared_term_is_not_enough():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("blueprint registration order")}
    assert _learned_seeds(G, "blueprint docs typo") == []              # 1 of 3 shared: below the overlap


def test_stale_contested_and_non_useful_lessons_do_not_count():
    G = _graph()
    q = "Raise error when blueprint name contains a dot"
    G.graph["_learning_overlay"] = {
        "bp": _lesson(q, stale=True),                       # the code changed since the lesson
        "bp_init": _lesson(q, status="contested"),
        "app": _lesson(q, outcome="dead_end"),
        "ghost": _lesson(q),                                # not in the graph any more
    }
    assert _learned_seeds(G, q) == []


def test_learned_nodes_rank_by_overlap_then_score_and_are_capped():
    G = _graph()
    G.graph["_learning_overlay"] = {
        "bp": _lesson("blueprint name dot error"),
        "bp_init": _lesson("blueprint name dot validation", score=5.0),
        "app": _lesson("blueprint name", score=9.0),
        "route": _lesson("blueprint dot", score=1.0),
    }
    got = _learned_seeds(G, "blueprint name dot error", max_k=3)
    assert got[0] == "bp"                                   # full coverage, four shared terms
    assert got[1:] == ["app", "route"]                      # full coverage, two shared terms, by score
    assert len(got) == 3


def test_query_starts_from_the_learned_node_and_says_so():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("Raise error when blueprint name contains a dot")}
    text = _query_graph_text(G, "blueprint name with a dot should raise an error", mode="bfs", depth=2, learned=True)
    assert "Learned (past useful answers): ['blueprints.py']" in text
    assert text.split("NODE ", 1)[1].startswith("blueprints.py")      # its node is rendered first


def test_learned_false_is_the_default_answer_even_with_a_memory():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("Raise error when blueprint name contains a dot")}
    q = "blueprint name with a dot should raise an error"
    assert _query_graph_text(G, q, mode="bfs", depth=2) == _query_graph_text(G, q, mode="bfs", depth=2, learned=False)
    assert "Learned" not in _query_graph_text(G, q, mode="bfs", depth=2)


def test_explicit_seeds_are_never_overridden_by_learning():
    G = _graph()
    G.graph["_learning_overlay"] = {"bp": _lesson("Raise error when blueprint name contains a dot")}
    text = _query_graph_text(G, "blueprint name dot error", mode="bfs", depth=2, seeds=["FlaskGroup"], learned=True)
    assert "Start (given): ['FlaskGroup']" in text and "Learned" not in text


def test_the_real_pipeline_save_result_reflect_then_query(tmp_path: Path):
    G = _graph()
    root = tmp_path / "repo"
    (root / "src" / "flask").mkdir(parents=True)
    for f in ("blueprints.py", "app.py", "scaffold.py", "cli.py"):
        (root / "src" / "flask" / f).write_text(f"# {f}\n", encoding="utf-8")
    out = root / "graphify-out"
    out.mkdir()
    gp = out / "graph.json"
    gp.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    memory = out / "memory"
    save_query_result(question="Raise error when blueprint name contains a dot", answer="see blueprints.py",
                      memory_dir=memory, source_nodes=["bp"], outcome="useful")
    reflect(memory, out / "reflections" / "LESSONS.md", graph_path=gp)
    G.graph["_learning_overlay"] = load_learning_overlay(gp)
    assert G.graph["_learning_overlay"]["bp"]["status"] == "tentative"
    text = _query_graph_text(G, "a blueprint name containing a dot must raise an error", mode="bfs", depth=2, learned=True)
    assert "Learned (past useful answers): ['blueprints.py']" in text
