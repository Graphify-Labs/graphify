"""Offline parser boundary fakes and real persistence snapshots for QML gates."""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


def healthy_qml(path: Path) -> dict:
    """A complete parser contribution with a containment edge to preserve."""
    file_id = _make_id(str(path))
    component_id = _make_id(_file_stem(path), "component")
    common = {"source_file": str(path), "file_type": "code", "source_location": "L1"}
    return {
        "nodes": [
            {**common, "id": file_id, "label": path.name},
            {**common, "id": component_id, "label": "Main"},
        ],
        "edges": [{"source": file_id, "target": component_id, "relation": "contains",
                   "confidence": "EXTRACTED", "source_file": str(path), "source_location": "L1"}],
    }


def failing_qml(kind: str, *, extra_nodes: int = 0):
    """Inject parser failure, including surviving nodes that hide an edge loss."""
    errors = {
        "missing": "QML_PARSER_MISSING: tree-sitter-language-pack not installed",
        "incompatible": "QML_PARSER_LOAD: QML grammar failed to load",
        "read": "QML_SOURCE_READ: source could not be read",
        "partial": "QML_PARSE_PARTIAL: syntax recovery lost a declaration",
    }

    def extract(path):
        result = healthy_qml(path)
        result["edges"] = []
        for i in range(extra_nodes):
            result["nodes"].append({
                "id": f"replacement_{i}", "label": f"replacement{i}", "file_type": "code",
                "source_file": str(path), "source_location": "L1",
            })
        result["error"] = errors[kind]
        return result

    return extract


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "Main.qml").write_text("import QtQuick\nItem { property int count: 1 }\n", encoding="utf-8")
    (project / "keep.py").write_text("def retained(): return 1\n", encoding="utf-8")
    return project


def protected_snapshot(out: Path) -> dict[str, bytes]:
    """Measure completed durable products, excluding retryable cache/lock files."""
    return {
        p.name: p.read_bytes() for p in out.iterdir()
        if p.name in {"graph.json", "manifest.json", "GRAPH_REPORT.md", "graph.html",
                      ".graphify_root", ".graphify_labels.json", "callflow.html"}
    }
