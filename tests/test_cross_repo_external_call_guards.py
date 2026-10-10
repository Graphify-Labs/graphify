"""Regression tests for cross-repo calls on externally resolved C# types (#3360)."""
from __future__ import annotations

from pathlib import Path

import networkx as nx
import pytest

from graphify.build import prefix_graph_for_global
from graphify.cross_repo_calls import CROSS_REPO_CALL_MARKER, link_cross_repo_member_calls
from graphify.extract import extract


def _graph(*, using_namespace: str, target_namespace: str) -> nx.Graph:
    graph = nx.Graph()
    graph.add_node(
        "app::file",
        label="OrderService.cs",
        source_file="src/OrderService.cs",
        file_type="code",
        repo="app",
    )
    graph.add_node(
        "app::run",
        label=".Run()",
        source_file="src/OrderService.cs",
        file_type="code",
        repo="app",
        metadata={
            "unresolved_calls": [{
                "callee": "ValidateAsync",
                "receiver_type": "IValidator",
                "lang": "csharp",
                "line": "L13",
            }],
        },
    )
    graph.add_edge(
        "app::file",
        "app::using",
        relation="imports",
        metadata={"using_kind": "namespace", "target_fqn": using_namespace},
    )
    graph.add_node(
        "lib::type",
        label="IValidator",
        source_file="src/IValidator.cs",
        file_type="code",
        repo="lib",
        _callable_class=True,
        _callable=True,
        metadata={"namespace": target_namespace},
    )
    graph.add_node(
        "lib::method",
        label=".ValidateAsync()",
        source_file="src/IValidator.cs",
        file_type="code",
        repo="lib",
        _callable=True,
    )
    graph.add_edge("lib::type", "lib::method", relation="method")
    return graph


@pytest.mark.parametrize(
    ("using_namespace", "target_namespace", "expected"),
    [
        ("FluentValidation", "Lib.Domain.Interfaces", 0),
        ("Lib.Domain.Interfaces", "Lib.Domain.Interfaces", 1),
    ],
)
def test_cross_repo_calls_honor_csharp_using_visibility(
    using_namespace: str, target_namespace: str, expected: int
) -> None:
    graph = _graph(using_namespace=using_namespace, target_namespace=target_namespace)

    assert link_cross_repo_member_calls(graph) == expected
    assert sum(
        data.get(CROSS_REPO_CALL_MARKER, False)
        for _, _, data in graph.edges(data=True)
    ) == expected


def test_real_csharp_external_receiver_does_not_bind_to_unrelated_repo_type(
    tmp_path: Path,
) -> None:
    app = tmp_path / "app" / "src" / "OrderService.cs"
    library = tmp_path / "library" / "src" / "IValidator.cs"
    app.parent.mkdir(parents=True)
    library.parent.mkdir(parents=True)
    app.write_text(
        "using FluentValidation;\n"
        "namespace App.Services;\n"
        "public class OrderService {\n"
        "    private readonly IValidator _validator;\n"
        "    public void Create() { _validator.ValidateAsync(); }\n"
        "}\n",
        encoding="utf-8",
    )
    library.write_text(
        "namespace Lib.Domain.Interfaces;\n"
        "public class IValidator { public void ValidateAsync() {} }\n",
        encoding="utf-8",
    )

    def as_graph(result: dict) -> nx.Graph:
        graph = nx.Graph()
        graph.add_nodes_from((node["id"], node) for node in result["nodes"])
        graph.add_edges_from(
            (edge["source"], edge["target"], edge) for edge in result["edges"]
        )
        return graph

    app_result = extract(
        [app], root=tmp_path / "app", cache_root=tmp_path / "app" / "out"
    )
    library_result = extract(
        [library], root=tmp_path / "library", cache_root=tmp_path / "library" / "out"
    )
    assert any(
        entry.get("receiver_type") == "IValidator"
        for node in app_result["nodes"]
        for entry in node.get("metadata", {}).get("unresolved_calls", [])
    )
    assert any(
        node.get("label") == "IValidator" and node.get("_callable_class")
        for node in library_result["nodes"]
    )
    assert any(node.get("label") == ".ValidateAsync()" for node in library_result["nodes"])

    merged = nx.compose(
        prefix_graph_for_global(as_graph(app_result), "app"),
        prefix_graph_for_global(as_graph(library_result), "library"),
    )
    assert link_cross_repo_member_calls(merged) == 0
    assert not any(data.get(CROSS_REPO_CALL_MARKER) for _, _, data in merged.edges(data=True))
