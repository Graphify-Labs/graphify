from graphify.analyze import surprising_connections
from tests.native_helpers import make_loaded


def test_semantic_relation_is_native_label_and_analysis_property(tmp_path):
    graph = make_loaded(
        tmp_path,
        nodes=[
            {"id": "a", "label": "A", "source_file": "src/a.py"},
            {"id": "b", "label": "B", "source_file": "docs/b.md"},
        ],
        edges=[{
            "source": "a", "target": "b",
            "relation": "semantically_similar_to",
            "confidence": "INFERRED",
        }],
    ).graph
    assert graph.edges()[0].label == "semantically_similar_to"
    surprises = surprising_connections(graph, {0: ["a"], 1: ["b"]})
    assert surprises[0]["relation"] == "semantically_similar_to"
