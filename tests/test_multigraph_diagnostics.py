from graphify.diagnostics import diagnose_extraction, format_diagnostic_json, format_diagnostic_report


def test_diagnostics_measure_raw_parallel_edges_before_native_ingestion():
    payload = {
        "directed": True,
        "multigraph": True,
        "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        "edges": [
            {"source": "a", "target": "b", "key": "one", "relation": "calls"},
            {"source": "a", "target": "b", "key": "two", "relation": "uses"},
            {"source": "a", "target": "a", "key": "self", "relation": "recursive"},
        ],
    }
    summary = diagnose_extraction(payload)
    assert summary["directed_same_endpoint_collapsed_edges"] == 1
    assert summary["relation_variant_groups"] == 1
    assert summary["self_loop_edges"] == 1
    assert summary["post_build_graph_type"] == "multidigraph"
    assert "raw_edges: 3" in format_diagnostic_report(summary)
    assert format_diagnostic_json(summary)["schema_version"] == 1
