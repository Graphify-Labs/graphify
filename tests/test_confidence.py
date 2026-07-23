from graphify.helix.access import first_edge_attributes
from tests.native_helpers import graph_from_payload


def test_confidence_and_weight_round_trip_natively():
    graph = graph_from_payload(
        [{"id": "a"}, {"id": "b"}],
        [{"source": "a", "target": "b", "relation": "calls", "confidence": "AMBIGUOUS", "weight": 0.2}],
    )
    attrs = first_edge_attributes(graph, "a", "b")
    assert attrs["confidence"] == "AMBIGUOUS"
    assert attrs["weight"] == 0.2
