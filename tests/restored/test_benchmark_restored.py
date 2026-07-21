"""Tests for graphify/benchmark.py."""
from __future__ import annotations
from graphify.benchmark import run_benchmark, print_benchmark, _query_subgraph_tokens, _SAMPLE_QUESTIONS, _safe, _hr
from graphify.helix.model import edge_attributes, graphify_attributes
from tests.native_helpers import graph_from_payload, make_loaded


def _make_graph():
    return graph_from_payload(
        [
            {"id": "n1", "label": "authentication", "source_file": "auth.py", "source_location": "L1", "community": 0},
            {"id": "n2", "label": "api_handler", "source_file": "api.py", "source_location": "L5", "community": 0},
            {"id": "n3", "label": "main_entry", "source_file": "main.py", "source_location": "L1", "community": 1},
            {"id": "n4", "label": "error_handler", "source_file": "errors.py", "source_location": "L1", "community": 1},
            {"id": "n5", "label": "database_layer", "source_file": "db.py", "source_location": "L1", "community": 2},
        ],
        [
            {"source": "n1", "target": "n2", "relation": "calls", "confidence": "INFERRED"},
            {"source": "n2", "target": "n3", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "n3", "target": "n4", "relation": "uses", "confidence": "EXTRACTED"},
            {"source": "n5", "target": "n2", "relation": "provides", "confidence": "EXTRACTED"},
        ],
    )


def _write_graph(G, path):
    loaded = make_loaded(
        path.parent,
        nodes=[{"id": node.id, **graphify_attributes(node.attributes)} for node in G.nodes()],
        edges=[{"source": edge.source, "target": edge.target, **edge_attributes(edge)} for edge in G.edges()],
        kind="digraph" if G.directed else "graph",
    )
    return loaded.store_path


# --- _query_subgraph_tokens ---

def test_query_returns_positive_for_matching_question():
    G = _make_graph()
    tokens = _query_subgraph_tokens(G, "how does authentication work")
    assert tokens > 0

def test_query_returns_zero_for_no_match():
    G = _make_graph()
    tokens = _query_subgraph_tokens(G, "xyzzy plugh zorkmid")
    assert tokens == 0

def test_query_bfs_expands_neighbors():
    G = _make_graph()
    # "authentication" matches n1, BFS depth=3 should reach n2, n3, n4
    tokens_deep = _query_subgraph_tokens(G, "authentication", depth=3)
    tokens_shallow = _query_subgraph_tokens(G, "authentication", depth=1)
    assert tokens_deep >= tokens_shallow


def test_query_keeps_short_non_english_terms():
    G = graph_from_payload([{"id": "frontend", "label": "前端", "source_file": "docs/前端.md", "source_location": "L1", "community": 0}])
    tokens = _query_subgraph_tokens(G, "前端", depth=1)
    assert tokens > 0


# --- run_benchmark ---

def test_run_benchmark_returns_reduction(tmp_path):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=10_000)
    assert "reduction_ratio" in result
    assert result["reduction_ratio"] > 1.0

def test_run_benchmark_corpus_tokens_proportional(tmp_path):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    r1 = run_benchmark(str(graph_file), corpus_words=1_000)
    r2 = run_benchmark(str(graph_file), corpus_words=10_000)
    # corpus_tokens scales linearly with corpus_words (within integer-division rounding)
    assert abs(r2["corpus_tokens"] - r1["corpus_tokens"] * 10) <= r1["corpus_tokens"]

def test_run_benchmark_per_question_list(tmp_path):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=5_000,
                           questions=["how does authentication work", "what is the main entry"])
    assert len(result["per_question"]) >= 1
    for p in result["per_question"]:
        assert "question" in p
        assert "query_tokens" in p
        assert "reduction" in p

def test_run_benchmark_estimates_corpus_if_no_words(tmp_path):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=None)
    assert result["corpus_words"] > 0

def test_run_benchmark_error_on_empty_graph(tmp_path):
    G = graph_from_payload([])
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=1_000)
    assert "error" in result

def test_run_benchmark_includes_node_edge_counts(tmp_path):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=5_000)
    assert result["nodes"] == G.node_count
    assert result["edges"] == G.edge_count


# --- print_benchmark ---

def test_print_benchmark_no_crash(tmp_path, capsys):
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=5_000)
    print_benchmark(result)
    out = capsys.readouterr().out
    assert "reduction" in out.lower()
    assert "x" in out

def test_print_benchmark_error_message(capsys):
    print_benchmark({"error": "test error message"})
    out = capsys.readouterr().out
    assert "test error message" in out


# --- cp1252 / Windows-console encoding compatibility (regression for #?) ---
# print_benchmark previously crashed on Windows consoles (cp1252) because it
# unconditionally printed U+2500 and U+2192. _safe() falls back to ASCII when
# stdout cannot encode the glyph.

def test_safe_returns_unicode_when_encodable():
    import io, sys
    real_stdout = sys.stdout
    try:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        assert _safe("→", "->") == "→"
        assert _hr(5) == "─" * 5
    finally:
        sys.stdout = real_stdout

def test_safe_falls_back_when_unencodable():
    import io, sys
    real_stdout = sys.stdout
    try:
        sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        assert _safe("→", "->") == "->"
        assert _hr(5) == "-" * 5
    finally:
        sys.stdout = real_stdout

def test_print_benchmark_survives_cp1252_stdout(tmp_path, monkeypatch, capsys):
    """Regression: U+2500 / U+2192 used to crash with UnicodeEncodeError on cp1252."""
    import io, sys
    G = _make_graph()
    graph_file = _write_graph(G, tmp_path / "graph.helix")
    result = run_benchmark(str(graph_file), corpus_words=5_000)

    # Replace stdout with a strict cp1252 stream — same behaviour as the
    # legacy Windows console that surfaced this bug.
    cp1252_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", cp1252_stdout)
    print_benchmark(result)  # must not raise UnicodeEncodeError
    cp1252_stdout.flush()
    written = cp1252_stdout.buffer.getvalue().decode("cp1252")
    assert "reduction" in written.lower()
    # ASCII fallbacks must be present, fancy glyphs must not.
    assert "─" not in written
    assert "→" not in written
