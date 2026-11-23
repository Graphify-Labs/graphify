import json
import subprocess
import sys
from pathlib import Path

import networkx as nx

from graphify.analyze import file_level_graph


def test_file_projection_preserves_import_timing_and_evidence() -> None:
    graph = nx.DiGraph()
    graph.add_nodes_from([
        ("a", {"source_file": "a.ts"}), ("a_symbol", {"source_file": "a.ts"}),
        ("b", {"source_file": "b.ts"}), ("b_symbol", {"source_file": "b.ts"}),
        ("external", {"source_file": "", "external": True}),
    ])
    graph.add_edge("a", "b", relation="imports_from", confidence="EXTRACTED",
                   source_file="a.ts", source_location="L1")
    graph.add_edge("a_symbol", "b_symbol", relation="imports_from", confidence="INFERRED",
                   source_file="a.ts", source_location="L2")
    graph.add_edge("a", "b_symbol", relation="imports_from", confidence="EXTRACTED",
                   source_file="a.ts", source_location="L3", deferred=True)
    graph.add_edge("b", "a", relation="imports_from", source_file="b.ts", source_location="L1")
    graph.add_edge("a", "a_symbol", relation="contains", source_file="a.ts")
    graph.add_edge("a", "external", relation="imports_from", source_file="a.ts")

    projected = file_level_graph(graph)

    assert set(projected) == {"a.ts", "b.ts"}
    assert projected.number_of_edges() == 3
    assert projected.has_edge("b.ts", "a.ts")
    forward = list(projected["a.ts"]["b.ts"].values())
    deferred = next(edge for edge in forward if edge.get("deferred"))
    immediate = next(edge for edge in forward if not edge.get("deferred"))
    assert deferred["weight"] == 1
    assert immediate["weight"] == 2
    assert immediate["confidence"] == "INFERRED"
    assert immediate["source_location"] == "L2"
    assert immediate["also_seen"][0]["source_location"] == "L1"


def test_file_only_extract_writes_weighted_json_and_html_without_replacing_symbols(
    tmp_path: Path,
) -> None:
    (tmp_path / "library.py").write_text(
        "def first(): pass\ndef second(): pass\n", encoding="utf-8",
    )
    (tmp_path / "app.py").write_text(
        "from library import first, second\n\ndef run():\n    first()\n    second()\n",
        encoding="utf-8",
    )
    (tmp_path / "isolated.py").write_text("def alone(): pass\n", encoding="utf-8")
    command = [sys.executable, "-m", "graphify", "extract", str(tmp_path), "--code-only"]
    subprocess.run(command, check=True, capture_output=True, text=True)
    output = tmp_path / "graphify-out"
    original = (output / "graph.json").read_bytes()

    subprocess.run([*command, "--file-only"], check=True, capture_output=True, text=True)

    view = output / "file-only"
    data = json.loads((view / "graph.json").read_text(encoding="utf-8"))
    assert (output / "graph.json").read_bytes() == original
    assert data["directed"]
    assert sorted(node["source_file"] for node in data["nodes"]) == [
        "app.py", "isolated.py", "library.py",
    ]
    call = next(edge for edge in data["links"] if edge["relation"] == "calls")
    assert (call["source"], call["target"], call["weight"]) == ("app.py", "library.py", 2)
    assert "calls (2)" in (view / "graph.html").read_text(encoding="utf-8")

    (tmp_path / "isolated.py").unlink()
    subprocess.run([*command, "--file-only", "--no-cluster"], check=True, capture_output=True, text=True)
    rebuilt = json.loads((view / "graph.json").read_text(encoding="utf-8"))
    assert sorted(node["source_file"] for node in rebuilt["nodes"]) == ["app.py", "library.py"]
    assert (output / "graph.json").read_bytes() == original
