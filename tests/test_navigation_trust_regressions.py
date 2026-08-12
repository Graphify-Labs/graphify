from __future__ import annotations

from pathlib import Path

from graphify.build import build
from graphify.export import to_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1
    return matches[0]


def _edge_pairs(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels[edge["source"]], labels[edge["target"]])
        for edge in result["edges"]
        if edge.get("relation") == relation
        and edge["source"] in labels
        and edge["target"] in labels
    }


def test_absolute_import_from_scanned_package_root_reaches_internal_endpoint(tmp_path: Path):
    package = tmp_path / "package"
    init = _write(package / "__init__.py", "")
    model = _write(package / "model.py", "class Payload:\n    pass\n")
    consumer = _write(
        package / "consumer.py",
        "from package.model import Payload\n\n"
        "def build():\n"
        "    return Payload()\n",
    )

    result = extract(
        [init, model, consumer],
        root=package,
        cache_root=tmp_path,
        parallel=False,
    )
    node_ids = {node["id"] for node in result["nodes"]}
    import_edges = [
        edge
        for edge in result["edges"]
        if edge.get("relation") in {"imports", "imports_from", "re_exports"}
    ]

    assert import_edges
    assert all(edge["source"] in node_ids and edge["target"] in node_ids for edge in import_edges)
    assert any(
        edge["source"] == _node_id(result, "consumer.py", "consumer.py")
        and edge["target"] == _node_id(result, "Payload", "model.py")
        for edge in import_edges
    )


def test_import_accounting_separates_internal_and_external_edges(tmp_path: Path):
    model = _write(tmp_path / "model.py", "class Payload:\n    pass\n")
    consumer = _write(
        tmp_path / "consumer.py",
        "from model import Payload\n"
        "from third_party import Client\n",
    )

    result = extract([model, consumer], root=tmp_path, cache_root=tmp_path, parallel=False)

    assert result["import_accounting"] == {
        "total": 2,
        "internal": 1,
        "internal_resolved": 1,
        "internal_unresolved": 0,
        "external": 1,
    }


def test_import_accounting_survives_graph_export(tmp_path: Path):
    model = _write(tmp_path / "model.py", "class Payload:\n    pass\n")
    consumer = _write(tmp_path / "consumer.py", "from model import Payload\n")
    result = extract([model, consumer], root=tmp_path, cache_root=tmp_path, parallel=False)
    result["import_accounting"]["complete"] = True
    graph = build([result], root=tmp_path)
    output = tmp_path / "graph.json"

    assert to_json(graph, {}, str(output), force=True)

    import json

    exported = json.loads(output.read_text(encoding="utf-8"))
    assert exported["import_accounting"] == {
        "total": 1,
        "internal": 1,
        "internal_resolved": 1,
        "internal_unresolved": 0,
        "external": 0,
        "complete": True,
    }


def test_python_inferred_uses_belong_to_narrowest_lexical_owner(tmp_path: Path):
    model = _write(
        tmp_path / "model.py",
        "class InputKind:\n"
        "    pass\n\n"
        "class ExecutionTiming:\n"
        "    pass\n",
    )
    consumer = _write(
        tmp_path / "consumer.py",
        "from model import InputKind, ExecutionTiming\n\n"
        "class _PiRpcConnection:\n"
        "    pass\n\n"
        "class PacPiInterpreter:\n"
        "    def execute(self, kind: InputKind) -> ExecutionTiming:\n"
        "        return ExecutionTiming()\n",
    )

    result = extract([model, consumer], root=tmp_path, cache_root=tmp_path, parallel=False)
    uses = _edge_pairs(result, "uses")

    assert ("PacPiInterpreter", "InputKind") in uses
    assert ("PacPiInterpreter", "ExecutionTiming") in uses
    assert ("_PiRpcConnection", "InputKind") not in uses
    assert ("_PiRpcConnection", "ExecutionTiming") not in uses
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    attributed = [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "uses"
        and labels.get(edge["source"]) == "PacPiInterpreter"
        and labels.get(edge["target"]) in {"InputKind", "ExecutionTiming"}
    ]
    assert attributed
    assert all(edge["confidence"] == "INFERRED" for edge in attributed)


def test_unused_import_does_not_create_construct_level_use(tmp_path: Path):
    model = _write(tmp_path / "model.py", "class Payload:\n    pass\n")
    consumer = _write(
        tmp_path / "consumer.py",
        "from model import Payload\n\n"
        "class ToolResultStore:\n"
        "    pass\n",
    )

    result = extract([model, consumer], root=tmp_path, cache_root=tmp_path, parallel=False)

    assert ("ToolResultStore", "Payload") not in _edge_pairs(result, "uses")
