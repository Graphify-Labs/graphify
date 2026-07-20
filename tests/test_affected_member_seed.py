from graphify.affected import affected_nodes
from tests.native_helpers import graph_from_payload


def test_class_seed_reaches_method_bound_caller_without_reporting_member():
    graph = graph_from_payload(
        [
            {"id": "class", "label": "Service", "source_file": "service.py"},
            {"id": "method", "label": "Service.run", "source_file": "service.py"},
            {"id": "caller", "label": "Controller", "source_file": "controller.py"},
        ],
        [
            {"source": "class", "target": "method", "relation": "contains"},
            {"source": "caller", "target": "method", "relation": "calls"},
        ],
        kind="digraph",
    )
    hits = affected_nodes(graph, "class", relations={"calls", "contains"}, depth=2)
    assert "caller" in {row.node_id for row in hits}
    assert "method" not in {row.node_id for row in hits}
