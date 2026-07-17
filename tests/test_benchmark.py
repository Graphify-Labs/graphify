from graphify.benchmark import _estimate_tokens, _query_subgraph_tokens, print_benchmark, run_benchmark
from tests.native_helpers import make_loaded


def _loaded(tmp_path):
    return make_loaded(
        tmp_path,
        nodes=[
            {"id": "auth", "label": "Authentication", "source_file": "auth.py"},
            {"id": "token", "label": "Token Validator", "source_file": "token.py"},
            {"id": "main", "label": "Main Entry", "source_file": "main.py"},
        ],
        edges=[
            {"source": "auth", "target": "token", "relation": "calls"},
            {"source": "main", "target": "auth", "relation": "uses"},
        ],
    )


def test_token_estimate_and_native_query(tmp_path):
    loaded = _loaded(tmp_path)
    assert _estimate_tokens("abcdefgh") == 2
    assert _query_subgraph_tokens(loaded.graph, "authentication", depth=2) > 0
    assert _query_subgraph_tokens(loaded.graph, "xyzzy plugh") == 0


def test_run_benchmark_uses_native_store(tmp_path):
    loaded = _loaded(tmp_path)
    result = run_benchmark(
        str(loaded.store_path),
        corpus_words=10_000,
        questions=["authentication", "main entry"],
    )
    assert result["nodes"] == 3 and result["edges"] == 2
    assert result["reduction_ratio"] > 1
    assert len(result["per_question"]) == 2


def test_print_benchmark_handles_success_and_error(tmp_path, capsys):
    result = run_benchmark(str(_loaded(tmp_path).store_path), corpus_words=1000,
                           questions=["authentication"])
    print_benchmark(result)
    assert "Reduction" in capsys.readouterr().out
    print_benchmark({"error": "empty"})
    assert "Benchmark error" in capsys.readouterr().out
