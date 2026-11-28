"""Tests for per-file extension caching in build_from_json's edge guard."""
from unittest.mock import patch

from graphify import build

_SOURCE_FILES = ("pkg/a.py", "pkg/b.py", "web/c.ts")


def _make_extraction(num_same_lang_edges: int) -> dict:
    nodes = (
        [
            {"id": f"a_{i}", "label": f"fn_{i}()", "source_file": "pkg/a.py", "file_type": "code"}
            for i in range(10)
        ]
        + [
            {"id": f"b_{i}", "label": f"fn_{i}()", "source_file": "pkg/b.py", "file_type": "code"}
            for i in range(10)
        ]
        + [{"id": "ts_0", "label": "ts_0()", "source_file": "web/c.ts", "file_type": "code"}]
    )
    edges = [
        {
            "source": f"a_{idx // 10}",
            "target": f"b_{idx % 10}",
            "relation": "calls",
            "confidence": "EXTRACTED",
            "source_file": "pkg/a.py",
        }
        for idx in range(num_same_lang_edges)
    ] + [
        {
            "source": "a_0",
            "target": "ts_0",
            "relation": "calls",
            "confidence": "INFERRED",
            "source_file": "pkg/a.py",
        }
    ]
    return {"nodes": nodes, "edges": edges}


def _run_and_count_path_calls(num_same_lang_edges: int) -> tuple[int, int]:
    extraction = _make_extraction(num_same_lang_edges)
    with patch("graphify.build.Path", wraps=build.Path) as path_spy:
        G = build.build_from_json(extraction)
    assert G.number_of_edges() == num_same_lang_edges
    assert not G.has_edge("a_0", "ts_0")
    suffix_calls = [
        c for c in path_spy.call_args_list if c.args and str(c.args[0]) in _SOURCE_FILES
    ]
    return len(suffix_calls), G.number_of_edges()


def test_build_from_json_caches_edge_source_file_suffixes() -> None:
    """build_from_json resolves each distinct source_file suffix once regardless of edge count."""
    calls_10, _ = _run_and_count_path_calls(10)
    calls_100, _ = _run_and_count_path_calls(100)

    # At least one Path() call per distinct source_file on the base run, and zero
    # additional Path() calls when scaling from 10 to 100 edges over the same 3 files.
    assert calls_10 >= 3
    assert calls_100 - calls_10 == 0
