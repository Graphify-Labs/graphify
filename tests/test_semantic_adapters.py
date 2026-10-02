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


def test_service_rejects_json_without_scip_documents(tmp_path: Path):
    artifact_dir = tmp_path / ".graphify" / "semantic"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "pyright.scip.json").write_text("{}", encoding="utf-8")

    result = SemanticEnrichmentService(tmp_path).enrich({"nodes": [], "edges": []})

    assert result["semantic_enrichment"]["artifacts_loaded"] == 0
    assert any("documents" in item for item in result["semantic_enrichment"]["diagnostics"])


def test_service_fails_soft_on_deeply_nested_artifact_json(tmp_path: Path):
    artifact_dir = tmp_path / ".graphify" / "semantic"
    artifact_dir.mkdir(parents=True)
    nesting = 2000
    (artifact_dir / "pyright.scip.json").write_text(
        "[" * nesting + "]" * nesting,
        encoding="utf-8",
    )

    result = SemanticEnrichmentService(tmp_path).enrich({"nodes": [], "edges": []})

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


def test_selected_non_clang_tool_reports_unsupported_output_without_artifact(tmp_path: Path):
    """Installed language servers must not be reported as graph translators."""
    (tmp_path / "pyrightconfig.json").write_text("{}", encoding="utf-8")
    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("pyright",),
        executable_locator=_locator("pyright"),
    ).enrich({"nodes": [], "edges": []})

    assert result["semantic_enrichment"]["adapters"]["pyright"]["state"] == (
        "unsupported_output"
    )
    assert "artifact" in result["semantic_enrichment"]["adapters"]["pyright"]["detail"]


def test_selected_missing_tool_reports_unavailable_without_losing_ast(tmp_path: Path):
    ast = {"nodes": [{"id": "ast", "label": "baseline"}], "edges": []}

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("gopls",),
        executable_locator=_locator(),
    ).enrich(ast)

    assert result["nodes"] == ast["nodes"]
    assert result["semantic_enrichment"]["adapters"]["gopls"]["state"] == "unavailable"


def test_loaded_artifact_overrides_selected_tool_capability_status(tmp_path: Path):
    artifact_dir = tmp_path / ".graphify" / "semantic"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "typescript.scip.json").write_text(
        json.dumps({"documents": []}),
        encoding="utf-8",
    )

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("typescript",),
        executable_locator=_locator("typescript-language-server"),
    ).enrich({"nodes": [], "edges": []})

    status = result["semantic_enrichment"]["adapters"]["typescript"]
    assert status["state"] == "artifact_loaded"
    assert status["artifact"] == ".graphify/semantic/typescript.scip.json"


def test_selected_clang_reports_executed_when_enricher_boundary_runs(tmp_path: Path):
    class RecordingEnricher:
        def enrich(self, extraction: dict) -> dict:
            result = dict(extraction)
            result["semantic_enrichment"] = {
                "clang": {"candidate_calls": 1, "analyzer_runs": 1},
            }
            return result

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("clang",),
        enrichers=(RecordingEnricher(),),
    ).enrich({"nodes": [], "edges": []})

    assert result["semantic_enrichment"]["adapters"]["clang"]["state"] == "executed"


def test_selected_clang_without_analyzer_run_is_not_reported_as_executed(tmp_path: Path):
    class NoOpEnricher:
        def enrich(self, extraction: dict) -> dict:
            result = dict(extraction)
            result["semantic_enrichment"] = {
                "clang": {"candidate_calls": 0, "analyzer_runs": 0},
            }
            return result

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("clang",),
        enrichers=(NoOpEnricher(),),
    ).enrich({"nodes": [], "edges": []})

    status = result["semantic_enrichment"]["adapters"]["clang"]
    assert status["state"] == "unavailable"
    assert "did not run" in status["detail"]


def test_service_does_not_execute_clang_without_explicit_selection(tmp_path: Path):
    executed = False

    def runner(command, cwd, timeout):
        nonlocal executed
        executed = True
        raise AssertionError("unselected analyzer reached process boundary")

    result = SemanticEnrichmentService(
        tmp_path,
        executable_locator=_locator("clang++"),
        process_runner=runner,
    ).enrich({"nodes": [], "edges": []})

    assert executed is False
    assert result["semantic_enrichment"]["adapters"] == {}


def test_discovery_rejects_repository_controlled_executables(tmp_path: Path):
    """A repository-local PATH entry must not turn into automatic code execution."""
    malicious = tmp_path / "clang++"
    malicious.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    statuses = {
        status.adapter_id: status
        for status in discover_semantic_adapters(
            tmp_path,
            locator=lambda name: str(malicious) if name == "clang++" else None,
        )
    }

    assert statuses["clang"].state is AdapterState.MISSING_TOOL


def test_failed_direct_adapter_is_not_reported_as_executed(tmp_path: Path):
    class FailingEnricher:
        def enrich(self, extraction: dict) -> dict:
            raise RuntimeError("failed safely")

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("clang",),
        enrichers=(FailingEnricher(),),
    ).enrich({"nodes": [], "edges": []})

    status = result["semantic_enrichment"]["adapters"]["clang"]
    assert status["state"] == "unavailable"
    assert "failed" in status["detail"]


def test_service_never_executes_repository_controlled_clang(tmp_path: Path):
    malicious = tmp_path / "clang++"
    malicious.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executed = False

    def runner(command, cwd, timeout):
        nonlocal executed
        executed = True
        raise AssertionError("repository executable reached process boundary")

    result = SemanticEnrichmentService(
        tmp_path,
        enabled_adapters=("clang",),
        executable_locator=lambda name: str(malicious) if name == "clang++" else None,
        process_runner=runner,
    ).enrich({"nodes": [], "edges": []})

    assert executed is False
    assert result["semantic_enrichment"]["adapters"]["clang"]["state"] == "unavailable"
