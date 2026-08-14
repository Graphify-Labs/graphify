from __future__ import annotations

import networkx as nx
import pytest

from graphify.affected import affected_nodes, format_affected, resolve_seed


def _add_node(graph: nx.DiGraph, node_id: str, path: str, *, label: str | None = None) -> None:
    graph.add_node(
        node_id,
        label=label or f"{node_id}()",
        source_file=path,
        source_location="L1",
    )


@pytest.mark.parametrize("query", ["readDocStrict", "readDocStrict()"])
def test_resolve_seed_prefers_one_production_definition_over_test_mocks(query: str) -> None:
    graph = nx.DiGraph()
    _add_node(graph, "production", "src/settings/document_store.ts", label="readDocStrict()")
    _add_node(graph, "test-mock", "tests/settings.test.ts", label="readDocStrict()")
    _add_node(graph, "nested-mock", "src/__tests__/settings.ts", label="readDocStrict()")

    assert resolve_seed(graph, query) == "production"


def test_resolve_seed_remains_ambiguous_with_two_production_definitions() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "production-a", "src/a.ts", label="readDocStrict()")
    _add_node(graph, "production-b", "src/b.ts", label="readDocStrict()")
    _add_node(graph, "test-mock", "tests/settings.test.ts", label="readDocStrict()")

    assert resolve_seed(graph, "readDocStrict") is None


def test_resolve_seed_test_only_duplicates_remain_ambiguous() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "test-a", "tests/a.ts", label="readDocStrict()")
    _add_node(graph, "test-b", "src/__tests__/b.ts", label="readDocStrict()")

    assert resolve_seed(graph, "readDocStrict") is None


def test_resolve_seed_does_not_treat_unknown_source_as_production() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "unknown", "", label="readDocStrict()")
    _add_node(graph, "test-mock", "tests/settings.test.ts", label="readDocStrict()")

    assert resolve_seed(graph, "readDocStrict") is None


def test_resolve_seed_keeps_non_string_ids_ambiguous_without_error() -> None:
    graph = nx.DiGraph()
    graph.add_node(1, label="readDocStrict()")
    graph.add_node(2, label="readDocStrict()")

    assert resolve_seed(graph, "readDocStrict") is None
    assert format_affected(graph, "readDocStrict") == (
        "No unique node match for readDocStrict"
    )


def test_resolve_seed_does_not_treat_docs_as_production() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "docs", "docs/example.ts", label="readDocStrict()")
    _add_node(graph, "test-mock", "tests/settings.test.ts", label="readDocStrict()")

    assert resolve_seed(graph, "readDocStrict") is None


def test_resolve_seed_preserves_explicit_node_id() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "explicit-test-id", "tests/settings.test.ts", label="readDocStrict()")
    _add_node(graph, "production", "src/settings.ts", label="readDocStrict()")

    assert resolve_seed(graph, "explicit-test-id") == "explicit-test-id"


@pytest.mark.parametrize(
    "path",
    [
        "tests/caller.py",
        "src/__tests__/caller.ts",
        "src/caller.test.ts",
        "eval/caller.py",
        "docs/caller.py",
        "",
    ],
)
def test_production_only_excludes_nonproduction_paths(path: str) -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py")
    _add_node(graph, "caller", path)
    graph.add_edge("caller", "seed", relation="calls")

    assert affected_nodes(graph, "seed", production_only=True) == []


@pytest.mark.parametrize(
    "path",
    ["src/contest.py", "src/latest/x.py", "src/document_service.py"],
)
def test_production_only_keeps_similar_production_names(path: str) -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py")
    _add_node(graph, "caller", path)
    graph.add_edge("caller", "seed", relation="calls")

    assert [hit.node_id for hit in affected_nodes(graph, "seed", production_only=True)] == [
        "caller"
    ]


def test_production_only_does_not_traverse_excluded_nodes() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py")
    _add_node(graph, "test-bridge", "tests/bridge.py")
    _add_node(graph, "production-caller", "src/caller.py")
    graph.add_edge("test-bridge", "seed", relation="calls")
    graph.add_edge("production-caller", "test-bridge", relation="calls")

    assert affected_nodes(graph, "seed", depth=2, production_only=True) == []


def test_production_only_excludes_nonproduction_edge_call_site() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py")
    _add_node(graph, "production-caller", "src/caller.py")
    graph.add_edge(
        "production-caller",
        "seed",
        relation="calls",
        source_file="tests/caller.test.py",
        source_location="L7",
    )

    assert affected_nodes(graph, "seed", production_only=True) == []


def test_production_only_does_not_seed_excluded_members() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/service.py")
    _add_node(graph, "test-member", "tests/service.py")
    _add_node(graph, "production-caller", "src/caller.py")
    graph.add_edge("seed", "test-member", relation="method")
    graph.add_edge("production-caller", "test-member", relation="calls")

    assert affected_nodes(graph, "seed", production_only=True) == []


def test_default_traversal_behavior_is_unchanged() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py")
    _add_node(graph, "test-caller", "tests/caller.py")
    graph.add_edge("test-caller", "seed", relation="calls")

    assert [hit.node_id for hit in affected_nodes(graph, "seed")] == ["test-caller"]


def test_format_affected_contains_no_excluded_paths_in_production_mode() -> None:
    graph = nx.DiGraph()
    _add_node(graph, "seed", "src/target.py", label="target()")
    _add_node(graph, "production", "src/caller.py")
    _add_node(graph, "test", "tests/caller.py")
    _add_node(graph, "docs", "docs/caller.py")
    graph.add_edge("production", "seed", relation="calls")
    graph.add_edge("test", "seed", relation="calls")
    graph.add_edge("docs", "seed", relation="calls")

    output = format_affected(graph, "target", production_only=True)

    assert "src/caller.py" in output
    assert "tests/caller.py" not in output
    assert "docs/caller.py" not in output
