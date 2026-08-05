from __future__ import annotations

import json
import os
from pathlib import Path
import sys


def _fake_tetra(tmp_path: Path) -> tuple[Path, Path]:
    script = tmp_path / "fake_tetra.py"
    counter = tmp_path / "calls.txt"
    script.write_text(
        """
import json
import os
import sys
from pathlib import Path

counter = Path(os.environ["TETRA_TEST_COUNTER"])
counter.write_text(counter.read_text() + "x" if counter.exists() else "x")
if len(sys.argv) > 1 and sys.argv[1] == "version":
    print("test-compiler")
    raise SystemExit(0)
root = Path(sys.argv[sys.argv.index("--root") + 1])
nodes = []
edges = []
for source in sorted(root.glob("*.tetra")) + sorted(root.glob("*.t4")):
    rel = source.relative_to(root).as_posix()
    file_id = "file::" + rel
    fn_id = rel + "::function::main"
    nodes.extend([
        {"id": file_id, "kind": "file", "name": source.name,
         "qualified_name": rel, "source_file": rel, "line": 1, "column": 1},
        {"id": fn_id, "kind": "function", "name": "main",
         "qualified_name": "main", "source_file": rel, "line": 1, "column": 1},
    ])
    edges.append({"source": file_id, "target": fn_id, "relation": "contains",
                  "source_file": rel, "line": 1, "column": 1,
                  "extraction": "extracted", "confidence": 1})
print(json.dumps({"schema": "tetra.symbol-graph.v1", "root": ".",
                  "nodes": nodes, "edges": edges, "diagnostics": []}))
""",
        encoding="utf-8",
    )
    return script, counter


def test_tetra_extensions_are_registered():
    from graphify.detect import CODE_EXTENSIONS
    from graphify.extract import _DISPATCH, _LANG_FAMILY_BY_EXT, extract_tetra

    assert {".tetra", ".t4"} <= CODE_EXTENSIONS
    assert _DISPATCH[".tetra"] is extract_tetra
    assert _DISPATCH[".t4"] is extract_tetra
    assert _LANG_FAMILY_BY_EXT[".tetra"] == "tetra"
    assert _LANG_FAMILY_BY_EXT[".t4"] == "tetra"


def test_tetra_batch_runs_once_and_maps_graph(monkeypatch, tmp_path):
    from graphify.extract import extract

    script, counter = _fake_tetra(tmp_path)
    (tmp_path / "a.tetra").write_text("func main() -> Int:\n    return 0\n")
    (tmp_path / "b.t4").write_text("func main() -> Int:\n    return 0\n")
    monkeypatch.setenv("GRAPHIFY_TETRA_BIN", f"{sys.executable} {script}")
    monkeypatch.setenv("TETRA_TEST_COUNTER", str(counter))

    result = extract(
        [tmp_path / "a.tetra", tmp_path / "b.t4"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )

    # One version probe plus one batch extraction, never one extraction per file.
    assert counter.read_text() == "xx"
    assert {node.get("language") for node in result["nodes"]} == {"tetra"}
    assert {node.get("source_file") for node in result["nodes"]} == {"a.tetra", "b.t4"}
    assert {edge["relation"] for edge in result["edges"]} == {"contains"}
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"])
    assert result["tetra"]["schema"] == "tetra.symbol-graph.v1"
    assert result["tetra"]["compiler_version"] == "test-compiler"
    assert result["tetra"]["cache"] == "miss"

    second = extract(
        [tmp_path / "a.tetra", tmp_path / "b.t4"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )
    # The second invocation only probes the compiler version; the corpus result
    # is replayed from a key containing schema, compiler version, paths and bytes.
    assert counter.read_text() == "xxx"
    assert second["tetra"]["cache"] == "hit"

    (tmp_path / "a.tetra").write_text("func changed() -> Int:\n    return 1\n")
    third = extract(
        [tmp_path / "a.tetra", tmp_path / "b.t4"],
        root=tmp_path,
        cache_root=tmp_path,
        parallel=False,
    )
    assert counter.read_text() == "xxxxx"
    assert third["tetra"]["cache"] == "miss"


def test_tetra_missing_compiler_keeps_file_anchors(monkeypatch, tmp_path):
    from graphify.extractors.tetra import extract_tetra_batch

    source = tmp_path / "main.tetra"
    source.write_text("func main() -> Int:\n    return 0\n")
    monkeypatch.delenv("GRAPHIFY_TETRA_BIN", raising=False)
    monkeypatch.setenv("PATH", "")

    result = extract_tetra_batch([source], tmp_path)

    assert len(result["nodes"]) == 1
    assert result["nodes"][0]["source_file"] == "main.tetra"
    assert result["nodes"][0]["tetra_status"] == "compiler_unavailable"
    assert result["tetra"]["failed"] == 1


def test_tetra_adapter_rejects_absolute_source_paths(monkeypatch, tmp_path):
    from graphify.extractors.tetra import convert_symbol_graph

    payload = {
        "schema": "tetra.symbol-graph.v1",
        "root": ".",
        "nodes": [{"id": "x", "kind": "file", "name": "x", "source_file": str(tmp_path / "x.tetra")}],
        "edges": [],
        "diagnostics": [],
    }
    try:
        convert_symbol_graph(payload, tmp_path)
    except ValueError as exc:
        assert "absolute source_file" in str(exc)
    else:
        raise AssertionError("absolute source path was accepted")


def test_tetra_update_handles_change_rename_and_delete(monkeypatch, tmp_path):
    from graphify.watch import _rebuild_code

    script, counter = _fake_tetra(tmp_path)
    monkeypatch.setenv("GRAPHIFY_TETRA_BIN", f"{sys.executable} {script}")
    monkeypatch.setenv("TETRA_TEST_COUNTER", str(counter))
    source = tmp_path / "a.tetra"
    source.write_text("func main() -> Int:\n    return 0\n")

    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
    assert any(node.get("source_file") == "a.tetra" for node in graph["nodes"])

    source.write_text("func changed() -> Int:\n    return 1\n")
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)

    renamed = tmp_path / "renamed.t4"
    source.rename(renamed)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
    files = {node.get("source_file") for node in graph["nodes"]}
    assert "a.tetra" not in files
    assert "renamed.t4" in files

    renamed.unlink()
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False)
    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
    assert not any(node.get("language") == "tetra" for node in graph["nodes"])
