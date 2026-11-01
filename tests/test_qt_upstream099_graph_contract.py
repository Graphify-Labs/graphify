"""INC-QML-60: upstream graph corrections preserve Qt cleanup restrictions."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from graphify.build import (
    _lost_saved_semantic_nodes,
    build_from_json,
    finalize_raw_graph_endpoints,
)
from graphify.export import to_json
from graphify.paths import load_node_link_graph


FIELD = "qt_import_retention"


def _mixed_alias_data():
    """A real header alias coexists with a separately protected native orphan."""
    return {
        "nodes": [
            {"id": "kit_event_toolevent", "label": "ToolEvent.h", "file_type": "code",
             "source_file": "Kit/Event/ToolEvent.h", "_origin": "ast", "source_location": "L1"},
            {"id": "kit_holder", "label": "Holder.h", "file_type": "code",
             "source_file": "Kit/Holder.h", "_origin": "ast", "source_location": "L1"},
            {"id": "missing", "label": "missing", "file_type": "concept", "type": "external",
             "external": True, "source_file": ""},
        ],
        "links": [{"source": "kit_holder", "target": "toolevent", "relation": "imports",
                   "source_file": "Kit/Holder.h", "source_location": "L2", "confidence": "EXTRACTED"}],
        "graph": {FIELD: {"schema": 1, "ids": ["missing"]}},
    }


@pytest.mark.parametrize("boundary", ["raw", "clustered"])
def test_req_qml010_ac02_qml018_ac04_alias_and_retained_import_survive_roundtrip(
        tmp_path, boundary):
    """Alias resolution precedes stub minting without sweeping protected imports."""
    data = _mixed_alias_data()
    if boundary == "raw":
        finalize_raw_graph_endpoints(data)
        graph = load_node_link_graph(data)
    else:
        graph = build_from_json(data)
    expected_ids = {"kit_holder", "kit_event_toolevent", "missing"}
    assert set(graph) == expected_ids
    assert graph.has_edge("kit_holder", "kit_event_toolevent")
    assert graph.degree("missing") == 0
    assert graph.graph[FIELD] == {"schema": 1, "ids": ["missing"]}

    output = tmp_path / "graph.json"
    assert to_json(graph, {0: sorted(graph)}, str(output))
    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert {(edge["source"], edge["target"]) for edge in persisted["links"]} == {
        ("kit_holder", "kit_event_toolevent"),
    }
    restored = load_node_link_graph(output)
    assert set(restored) == expected_ids
    assert restored.graph[FIELD] == {"schema": 1, "ids": ["missing"]}
    assert restored.degree("missing") == 0


def test_req_qml018_ac06_raw_retention_rejection_precedes_alias_mutation():
    """Corrupt reserved ownership cannot be healed by an alias/stub pass."""
    data = _mixed_alias_data()
    data["graph"][FIELD]["ids"] = ["absent"]
    # This edge would be folded/repointed during ordinary raw finalization.
    data["links"][0]["relationship"] = data["links"][0].pop("relation")
    before = deepcopy(data)
    with pytest.raises(ValueError, match="QT_IMPORT_RETENTION_INVALID"):
        finalize_raw_graph_endpoints(data)
    assert data == before


def test_req_qml018_ac06_semantic_fold_does_not_excuse_authored_external_loss():
    """Real AST twins fold, but an authored external-looking record remains protected."""
    canonical = _mixed_alias_data()["nodes"][-1]
    authored = {**canonical, "id": "authored", "label": "", "_origin": "semantic"}
    semantic = {"id": "semantic_run", "label": "run()", "file_type": "code",
                "source_file": "Backend.cpp", "_origin": "semantic"}
    ast_twin = {"id": "backend_run", "label": "run()", "file_type": "code",
                "source_file": "Backend.cpp", "source_location": "L5", "_origin": "ast"}
    folded = {}
    lost = _lost_saved_semantic_nodes([semantic, canonical, authored], [ast_twin], folded=folded)
    assert folded == {"semantic_run": "backend_run"}
    assert lost == [authored]


def test_req_qml014_ac03_csharp_labels_and_qt_retention_both_finalize():
    """The two final graph passes retain both type-qualified labels and cleanup context."""
    data = _mixed_alias_data()
    data["nodes"].extend([
        {"id": "report_report", "label": "Report", "file_type": "code", "type": "class",
         "source_file": "Report.cs", "source_location": "L2", "_origin": "ast"},
        {"id": "report_report_run", "label": ".Run()", "file_type": "code", "type": "function",
         "source_file": "Report.cs", "source_location": "L3", "_origin": "ast"},
    ])
    data["links"].append({"source": "report_report", "target": "report_report_run",
                          "relation": "method", "confidence": "EXTRACTED", "source_file": "Report.cs"})
    graph = build_from_json(data)
    assert graph.nodes["report_report_run"]["label"] == "Report.Run()"
    assert graph.has_edge("report_report", "report_report_run")
    assert graph.graph[FIELD] == {"schema": 1, "ids": ["missing"]}
    assert graph.degree("missing") == 0
