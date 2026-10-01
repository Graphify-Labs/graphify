from __future__ import annotations

from graphify_semantic_providers.contracts import ProviderRun, ProviderStatus
from graphify_semantic_providers.merge import merge_runs


def _run(nodes, edges=()):
    return ProviderRun(
        provider="test-lsp",
        status=ProviderStatus.COMPLETED,
        nodes=list(nodes),
        edges=list(edges),
    )


def test_unique_native_symbol_is_enriched_not_duplicated() -> None:
    base = {
        "nodes": [
            {
                "id": "native_run",
                "label": "run",
                "source_file": "src/app.ts",
                "file_type": "code",
            }
        ],
        "links": [],
        "graph": {},
    }
    run = _run(
        [
            {
                "id": "semantic_run",
                "label": "run",
                "source_file": "src/app.ts",
                "source_location": "L7",
                "file_type": "code",
                "metadata": {"semantic_kind": "method"},
            }
        ]
    )
    merged = merge_runs(base, [run])
    assert [node["id"] for node in merged["nodes"]] == ["native_run"]
    evidence = merged["nodes"][0]["semantic_evidence"]
    assert len(evidence) == 1
    assert evidence[0]["provider"] == "test-lsp"
    assert evidence[0]["provider_kind"] == "semantic"
    assert evidence[0]["run_id"]
    assert evidence[0]["timestamp"]
    assert evidence[0]["source_location"] == "L7"
    assert evidence[0]["kind"] == "method"


def test_ambiguous_native_match_keeps_semantic_node_separate() -> None:
    base = {
        "nodes": [
            {"id": "a", "label": "run", "source_file": "src/app.ts", "file_type": "code"},
            {"id": "b", "label": "run", "source_file": "src/app.ts", "file_type": "code"},
        ],
        "edges": [],
    }
    run = _run([{"id": "s", "label": "run", "source_file": "src/app.ts", "file_type": "code"}])
    merged = merge_runs(base, [run])
    assert {node["id"] for node in merged["nodes"]} == {"a", "b", "s"}


def test_edges_are_remapped_to_reconciled_native_nodes() -> None:
    base = {
        "nodes": [
            {"id": "native", "label": "run", "source_file": "src/app.ts", "file_type": "code"}
        ],
        "edges": [],
    }
    run = _run(
        [
            {"id": "semantic", "label": "run", "source_file": "src/app.ts", "file_type": "code"},
            {"id": "helper", "label": "helper", "source_file": "src/help.ts", "file_type": "code"},
        ],
        [{"source": "semantic", "target": "helper", "relation": "calls"}],
    )
    merged = merge_runs(base, [run])
    assert merged["edges"] == [{"source": "native", "target": "helper", "relation": "calls"}]


def test_generator_of_runs_is_not_consumed_before_edges_and_metadata() -> None:
    run = _run(
        [
            {"id": "source", "label": "source", "source_file": "src/app.py"},
            {"id": "target", "label": "target", "source_file": "src/app.py"},
        ],
        [{"source": "source", "target": "target", "relation": "calls"}],
    )

    merged = merge_runs(
        {"nodes": [], "edges": [], "graph": {}},
        (value for value in [run]),
    )

    assert merged["edges"][0]["relation"] == "calls"
    assert merged["graph"]["semantic_providers"] == ["test-lsp"]
