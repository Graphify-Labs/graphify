"""Contracts for optional compiler and language-server enrichment adapters."""

import json
from pathlib import Path

from graphify.semantic_adapters import (
    AdapterState,
    SemanticEnrichmentService,
    discover_semantic_adapters,
    semantic_adapter_specs,
)


def _locator(*available: str):
    paths = {name: f"/tools/{name}" for name in available}
    return paths.get


def test_registry_covers_requested_language_ecosystems():
    specs = {spec.adapter_id: spec for spec in semantic_adapter_specs()}

    assert set(specs) == {
        "clang", "jdt", "roslyn", "typescript", "gopls",
        "rust_analyzer", "pyright", "php_static_analysis",
    }
    assert {"c", "cpp"} <= specs["clang"].languages
    assert {"java", "kotlin"} <= specs["jdt"].languages
    assert {"javascript", "typescript"} <= specs["typescript"].languages
    assert specs["php_static_analysis"].languages == frozenset({"php"})


def test_discovery_requires_tool_and_project_configuration(tmp_path: Path):
    (tmp_path / "compile_commands.json").write_text("[]", encoding="utf-8")

    statuses = {
        status.adapter_id: status
        for status in discover_semantic_adapters(tmp_path, locator=_locator("clang++"))
    }

    clang = statuses["clang"]
    assert clang.state is AdapterState.READY
    assert clang.executable == "/tools/clang++"
    assert clang.project_marker == "compile_commands.json"
    assert statuses["gopls"].state is AdapterState.MISSING_TOOL


def test_installed_tool_without_project_marker_is_not_ready(tmp_path: Path):
    statuses = {
        status.adapter_id: status
        for status in discover_semantic_adapters(
            tmp_path,
            locator=_locator("pyright-langserver"),
        )
    }

    assert statuses["pyright"].state is AdapterState.MISSING_PROJECT_CONFIG
    assert statuses["pyright"].executable == "/tools/pyright-langserver"


def test_clang_discovery_reports_repository_fallback_without_compile_database(tmp_path: Path):
    """Treating a present Clang as unusable would hide safe fallback coverage."""
    statuses = {
        status.adapter_id: status
        for status in discover_semantic_adapters(tmp_path, locator=_locator("clang++"))
    }

    assert statuses["clang"].state is AdapterState.FALLBACK_READY
    assert statuses["clang"].executable == "/tools/clang++"
    assert statuses["clang"].project_marker is None


def test_discovery_accepts_ecosystem_specific_alternatives(tmp_path: Path):
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")

    statuses = {
        status.adapter_id: status
        for status in discover_semantic_adapters(
            tmp_path,
            locator=_locator("psalm", "typescript-language-server"),
        )
    }

    assert statuses["php_static_analysis"].state is AdapterState.READY
    assert statuses["php_static_analysis"].executable == "/tools/psalm"
    assert statuses["typescript"].state is AdapterState.READY


def test_service_ingests_scip_artifact_into_universal_graph_facts(tmp_path: Path):
    """Removing artifact ingestion must lose compiler-resolved call evidence."""
    artifact_dir = tmp_path / ".graphify" / "semantic"
    artifact_dir.mkdir(parents=True)
    artifact = {
        "documents": [{
            "relative_path": "src/cache.ts",
            "language": "typescript",
            "symbols": [
                {
                    "symbol": "cache#load().",
                    "kind": "method",
                    "display_name": "load",
                    "occurrences": [{"range": [3, 0, 3, 4]}],
                    "relationships": [{"symbol": "cache#read().", "is_reference": True}],
                },
                {
                    "symbol": "cache#read().",
                    "kind": "method",
                    "display_name": "read",
                    "occurrences": [{"range": [8, 0, 8, 4]}],
                },
            ],
        }],
    }
    (artifact_dir / "typescript.scip.json").write_text(json.dumps(artifact), encoding="utf-8")

    result = SemanticEnrichmentService(tmp_path).enrich({"nodes": [], "edges": []})

    assert {node["label"] for node in result["nodes"]} == {"load", "read"}
    assert len(result["edges"]) == 1
    assert result["edges"][0]["relation"] == "references"
    assert result["semantic_enrichment"]["artifacts_loaded"] == 1


def test_service_fails_soft_when_one_artifact_is_malformed(tmp_path: Path):
    """A broken analyzer output must not discard deterministic AST evidence."""
    artifact_dir = tmp_path / ".graphify" / "semantic"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "pyright.scip.json").write_text("{broken", encoding="utf-8")
    ast = {"nodes": [{"id": "ast", "label": "existing"}], "edges": []}

    result = SemanticEnrichmentService(tmp_path).enrich(ast)

    assert result["nodes"] == ast["nodes"]
    assert result["semantic_enrichment"]["artifacts_loaded"] == 0
    assert result["semantic_enrichment"]["diagnostics"]


def test_service_enriches_persisted_node_link_graph_without_losing_metadata(tmp_path: Path):
    """Post-merge enrichment must preserve the persisted graph JSON contract."""

    class EdgeEnricher:
        def enrich(self, extraction: dict) -> dict:
            result = dict(extraction)
            result["edges"] = [*extraction["edges"], {
                "source": "a", "target": "b", "relation": "calls",
            }]
            return result

    graph = {
        "directed": False,
        "multigraph": False,
        "graph": {"name": "aggregate"},
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [],
        "hyperedges": [{"id": "flow", "nodes": ["a", "b"]}],
    }

    result = SemanticEnrichmentService(tmp_path, enrichers=(EdgeEnricher(),)).enrich_node_link(
        graph,
    )

    assert result["links"] == [{"source": "a", "target": "b", "relation": "calls"}]
    assert result["graph"] == {"name": "aggregate"}
    assert result["hyperedges"] == graph["hyperedges"]
    assert "edges" not in result
