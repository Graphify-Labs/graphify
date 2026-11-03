"""`graphify benchmark`."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def benchmark() -> None:
    """`graphify benchmark` (moved verbatim from dispatch_command)."""
    from graphify.benchmark import run_benchmark, print_benchmark
    from graphify.cli import _default_graph_path, _enforce_graph_size_cap_or_exit

    graph_path = sys.argv[2] if len(sys.argv) > 2 else _default_graph_path()
    _enforce_graph_size_cap_or_exit(Path(graph_path))
    # Try to load corpus_words from detect output
    corpus_words = None
    detect_path = Path(".graphify_detect.json")
    if detect_path.exists():
        try:
            detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
            corpus_words = detect_data.get("total_words")
        except Exception:
            pass
    result = run_benchmark(graph_path, corpus_words=corpus_words)
    print_benchmark(result)
