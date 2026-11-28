"""A natural-language question leads with the best node of its best-matching file.

The single best-scoring node of a long question is often a test, or a same-named helper in another file, while the
file the question is about matches it through several nodes at once. `_lead_by_file` ranks the files of the
best-scored candidates by their summed scores, and `_query_graph_text` puts the best node of the best file first.
Short queries (identifier lookups) keep their exact match first, and a test file leads only when the question asks
about tests or nothing else matches."""
from __future__ import annotations

import networkx as nx

from graphify.serve import _LEAD_FILE_CANDIDATES, _lead_by_file, _query_graph_text

_TERMS = ["parse", "duration", "string", "seconds"]


def _graph(files: dict[str, str]) -> nx.Graph:
    G = nx.Graph()
    for nid, src in files.items():
        G.add_node(nid, label=f"{nid}()", source_file=src, source_location="L1")
    return G


def test_the_file_with_the_best_summed_score_leads_over_the_single_best_node():
    G = _graph({"lone": "utils/legacy.py", "a": "utils/dateparse.py", "b": "utils/dateparse.py", "c": "utils/dateparse.py"})
    ranked = [(10.0, "lone"), (6.0, "a"), (5.0, "b"), (4.0, "c")]
    assert _lead_by_file(G, ranked, _TERMS) == "a"     # dateparse.py sums 15 > 10; its best node leads


def test_a_short_query_keeps_its_exact_match_first():
    G = _graph({"lone": "utils/legacy.py", "a": "utils/dateparse.py", "b": "utils/dateparse.py"})
    ranked = [(10.0, "lone"), (6.0, "a"), (5.0, "b")]
    assert _lead_by_file(G, ranked, ["parse", "duration"]) is None


def test_a_test_file_does_not_lead_unless_the_question_asks_about_tests():
    G = _graph({"t1": "tests/test_dateparse.py", "t2": "tests/test_dateparse.py", "a": "utils/dateparse.py"})
    ranked = [(9.0, "t1"), (8.0, "t2"), (5.0, "a")]
    assert _lead_by_file(G, ranked, _TERMS) == "a"
    assert _lead_by_file(G, ranked, ["test", *_TERMS]) == "t1"


def test_a_test_file_still_leads_when_only_test_files_match():
    G = _graph({"t1": "tests/test_dateparse.py", "t2": "tests/test_other.py"})
    ranked = [(9.0, "t1"), (8.0, "t2")]
    assert _lead_by_file(G, ranked, _TERMS) == "t1"


def test_equal_totals_break_by_path():
    G = _graph({"z": "pkg/zeta.py", "a": "pkg/alpha.py"})
    ranked = [(5.0, "z"), (5.0, "a")]
    assert _lead_by_file(G, ranked, _TERMS) == "a"
    assert _lead_by_file(G, list(reversed(ranked)), _TERMS) == "a"


def test_nodes_without_a_file_or_outside_the_graph_are_skipped():
    G = _graph({"a": "pkg/alpha.py"})
    G.add_node("concept", label="duration concept")       # no source_file
    ranked = [(50.0, "concept"), (40.0, "ghost"), (1.0, "a")]
    assert _lead_by_file(G, ranked, _TERMS) == "a"
    assert _lead_by_file(G, [(50.0, "concept")], _TERMS) is None


def test_only_the_best_scored_candidates_count():
    files = {"lone": "pkg/lone.py"}
    files.update({f"n{i}": f"pkg/filler_{i}.py" for i in range(_LEAD_FILE_CANDIDATES - 1)})
    files.update({f"late{i}": "pkg/late.py" for i in range(5)})
    G = _graph(files)
    ranked = [(10.0, "lone")] + [(1.0, f"n{i}") for i in range(_LEAD_FILE_CANDIDATES - 1)]
    ranked += [(9.0, f"late{i}") for i in range(5)]     # past the cut: late.py's 45 is never summed
    assert _lead_by_file(G, ranked, _TERMS) == "lone"


def _dateparse_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("t1", label="test_parse_duration_seconds_string()", source_file="tests/test_dateparse.py",
               source_location="L10")
    G.add_node("h1", label="duration_seconds_string()", source_file="utils/legacy.py", source_location="L3")
    G.add_node("d1", label="parse_duration()", source_file="utils/dateparse.py", source_location="L40")
    G.add_node("d2", label="duration_string()", source_file="utils/dateparse.py", source_location="L70")
    G.add_node("d3", label="seconds_to_duration()", source_file="utils/dateparse.py", source_location="L90")
    G.add_edge("t1", "d1")
    G.add_edge("d1", "d2")
    G.add_edge("d2", "d3")
    return G


def _start(text: str) -> str:
    return text.split("Start: ", 1)[1].split("]", 1)[0]


def test_query_leads_with_the_best_matching_file():
    # duration_seconds_string() in legacy.py is the best single match; dateparse.py matches through three nodes.
    text = _query_graph_text(_dateparse_graph(), "parse duration string seconds", mode="bfs", depth=1)
    assert _start(text).startswith("['parse_duration()'"), _start(text)
    assert text == _query_graph_text(_dateparse_graph(), "parse duration string seconds", mode="bfs", depth=1)


def test_query_with_two_terms_is_unchanged():
    text = _query_graph_text(_dateparse_graph(), "duration seconds", mode="bfs", depth=1)
    assert _start(text).startswith("['duration_seconds_string()'"), _start(text)


def test_query_about_tests_leads_with_the_test():
    text = _query_graph_text(_dateparse_graph(), "test parse duration string seconds", mode="bfs", depth=1)
    assert _start(text).startswith("['test_parse_duration_seconds_string()'"), _start(text)
