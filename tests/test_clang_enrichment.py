"""Behavioral tests for bounded Clang semantic call enrichment."""

from pathlib import Path
import json
import shutil

from graphify.clang_enrichment import (
    ClangSemanticEnricher,
    ProcessResult,
    run_clang_command,
)
import pytest
from graphify.semantic_adapters import SemanticEnrichmentService


def _graph_with_pending_cpp_call() -> dict:
    return {
        "nodes": [
            {
                "id": "src_main_c",
                "label": "main.C",
                "file_type": "code",
                "source_file": "src/main.C",
                "source_location": "L1",
            },
            {
                "id": "process",
                "label": "process()",
                "file_type": "code",
                "source_file": "src/main.C",
                "source_location": "L8",
                "metadata": {
                    "unresolved_calls": [{
                        "callee": "run",
                        "receiver_type": "Worker",
                        "lang": "cpp",
                        "line": "L10",
                    }],
                },
            },
            {
                "id": "worker",
                "label": "Worker",
                "file_type": "code",
                "source_file": "include/worker.h",
                "source_location": "L1",
            },
            {
                "id": "worker_run",
                "label": ".run()",
                "file_type": "code",
                "source_file": "include/worker.h",
                "source_location": "L2",
            },
        ],
        "edges": [
            {"source": "src_main_c", "target": "process", "relation": "contains"},
            {"source": "worker", "target": "worker_run", "relation": "method"},
        ],
    }


def _clang_ast() -> dict:
    return {
        "id": "tu",
        "kind": "TranslationUnitDecl",
        "inner": [
            {
                "id": "worker_decl",
                "kind": "CXXRecordDecl",
                "name": "Worker",
                "loc": {"file": "include/worker.h", "line": 1},
                "inner": [{
                    "id": "run_decl",
                    "kind": "CXXMethodDecl",
                    "name": "run",
                    "loc": {"file": "include/worker.h", "line": 2},
                }],
            },
            {
                "id": "process_decl",
                "kind": "FunctionDecl",
                "name": "process",
                "loc": {"file": "src/main.C", "line": 8},
                "inner": [{
                    "kind": "CompoundStmt",
                    "inner": [{
                        "kind": "CXXMemberCallExpr",
                        "range": {
                            "begin": {"file": "src/main.C", "line": 10},
                            "end": {"file": "src/main.C", "line": 10},
                        },
                        "inner": [{
                            "kind": "MemberExpr",
                            "name": "run",
                            "referencedMemberDecl": "run_decl",
                        }],
                    }],
                }],
            },
        ],
    }


def test_clang_adds_only_compiler_confirmed_edge_between_grounded_nodes(tmp_path: Path):
    """Removing exact AST validation must make this unresolved call disappear."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text("// parsed by the injected compiler boundary\n", encoding="utf-8")

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=_clang_ast(), stderr="")

    result = ClangSemanticEnricher(
        tmp_path,
        executable="/tools/clang++",
        runner=runner,
    ).enrich(_graph_with_pending_cpp_call())

    assert result["nodes"] == _graph_with_pending_cpp_call()["nodes"]
    assert result["edges"][-1] == {
        "source": "process",
        "target": "worker_run",
        "relation": "calls",
        "context": "compiler_resolved_call",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": "src/main.C",
        "source_location": "L10",
        "weight": 1.0,
        "semantic_provider": "clang",
    }
    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1


def test_clang_prefers_compile_database_but_drops_executable_plugin_flags(tmp_path: Path):
    """Ignoring the compile DB or forwarding plugin flags must break this boundary."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text("// compile-db fixture\n", encoding="utf-8")
    build = tmp_path / "build"
    build.mkdir()
    (tmp_path / "compile_commands.json").write_text(json.dumps([{
        "directory": str(build),
        "file": str(source),
        "arguments": [
            "g++", "-I../include", "-DMODE=1", "-fplugin=evil.so",
            "-fpass-plugin=evil-pass.so",
            "-c", str(source), "-o", "main.o",
        ],
    }]), encoding="utf-8")

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        assert cwd == build
        assert "-DMODE=1" in command
        assert "-I../include" in command
        assert not any(
            arg.startswith(("-fplugin", "-fpass-plugin"))
            for arg in command
        )
        assert "-c" not in command and "-o" not in command and "main.o" not in command
        return ProcessResult(returncode=0, stdout=_clang_ast(), stderr="")

    result = ClangSemanticEnricher(
        tmp_path,
        executable="/tools/clang++",
        runner=runner,
    ).enrich(_graph_with_pending_cpp_call())

    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1
    assert result["semantic_enrichment"]["clang"]["compile_database_translation_units"] == 1


def test_semantic_service_runs_compiler_enrichers_before_artifact_merge(tmp_path: Path):
    """Disconnecting executable enrichers from extraction must lose the call edge."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text("// service fixture\n", encoding="utf-8")

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=_clang_ast(), stderr="")

    clang = ClangSemanticEnricher(
        tmp_path,
        executable="/tools/clang++",
        runner=runner,
    )
    result = SemanticEnrichmentService(tmp_path, enrichers=(clang,)).enrich(
        _graph_with_pending_cpp_call(),
    )

    assert any(
        edge.get("source") == "process"
        and edge.get("target") == "worker_run"
        and edge.get("semantic_provider") == "clang"
        for edge in result["edges"]
    )
    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1
    assert result["semantic_enrichment"]["artifacts_loaded"] == 0


def test_semantic_service_automatically_activates_available_clang(tmp_path: Path):
    """Requiring a prebuilt SCIP artifact must not disable local Clang evidence."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text("// automatic service fixture\n", encoding="utf-8")

    def locator(name: str) -> str | None:
        return "/tools/clang++" if name == "clang++" else None

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=_clang_ast(), stderr="")

    result = SemanticEnrichmentService(
        tmp_path,
        executable_locator=locator,
        process_runner=runner,
    ).enrich(_graph_with_pending_cpp_call())

    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1


def test_clang_fallback_infers_unambiguous_repository_include_root(tmp_path: Path):
    """Dropping inferred include roots must prevent repository headers from resolving."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text('#include <api/worker.h>\n', encoding="utf-8")
    header = tmp_path / "include" / "api" / "worker.h"
    header.parent.mkdir(parents=True)
    header.write_text("struct Worker { void run(); };\n", encoding="utf-8")
    graph = _graph_with_pending_cpp_call()
    for node in graph["nodes"]:
        if node["id"] in {"worker", "worker_run"}:
            node["source_file"] = "include/api/worker.h"
    ast = _clang_ast()
    worker_decl = ast["inner"][0]
    worker_decl["loc"]["file"] = "include/api/worker.h"
    worker_decl["inner"][0]["loc"]["file"] = "include/api/worker.h"

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        assert f"-I{tmp_path / 'include'}" in command
        return ProcessResult(returncode=0, stdout=ast, stderr="")

    result = ClangSemanticEnricher(
        tmp_path,
        executable="/tools/clang++",
        runner=runner,
    ).enrich(graph)

    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1


def test_real_clang_confirms_a_repository_member_call(tmp_path: Path):
    """Actual Clang JSON shape must resolve the same edge as the contract fixture."""
    executable = shutil.which("clang++") or shutil.which("clang")
    if executable is None:
        pytest.skip("Clang is not installed")
    include = tmp_path / "include"
    include.mkdir()
    (include / "worker.h").write_text(
        "struct Worker { void run(); };\n",
        encoding="utf-8",
    )
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text(
        '#include "worker.h"\n\nvoid process(Worker& worker) {\n  worker.run();\n}\n',
        encoding="utf-8",
    )
    graph = {
        "nodes": [
            {
                "id": "process", "label": "process()", "file_type": "code",
                "source_file": "src/main.C", "source_location": "L3",
                "metadata": {"unresolved_calls": [{
                    "callee": "run", "receiver_type": "Worker", "lang": "cpp", "line": "L4",
                }]},
            },
            {
                "id": "worker", "label": "Worker", "file_type": "code",
                "source_file": "include/worker.h", "source_location": "L1",
            },
            {
                "id": "worker_run", "label": ".run()", "file_type": "code",
                "source_file": "include/worker.h", "source_location": "L1",
            },
        ],
        "edges": [{"source": "worker", "target": "worker_run", "relation": "method"}],
    }

    result = ClangSemanticEnricher(
        tmp_path,
        executable=executable,
        runner=run_clang_command,
    ).enrich(graph)

    assert result["semantic_enrichment"]["clang"]["resolved_calls"] == 1
    assert result["edges"][-1]["semantic_provider"] == "clang"


def test_clang_upgrades_inferred_call_in_merged_node_link_graph(tmp_path: Path):
    """Compiler proof should strengthen, rather than duplicate, a merge-time edge."""
    source = tmp_path / "src" / "main.C"
    source.parent.mkdir()
    source.write_text("// merged graph fixture\n", encoding="utf-8")
    merged = _graph_with_pending_cpp_call()
    merged["links"] = merged.pop("edges")
    merged["links"].append({
        "source": "process",
        "target": "worker_run",
        "relation": "calls",
        "context": "cross_partition",
        "confidence": "INFERRED",
        "confidence_score": 0.8,
        "source_location": "L10",
        "_partition_call": True,
    })
    merged.update({"directed": False, "multigraph": False, "graph": {"name": "merged"}})

    def runner(command: tuple[str, ...], cwd: Path, timeout: float) -> ProcessResult:
        return ProcessResult(returncode=0, stdout=_clang_ast(), stderr="")

    result = ClangSemanticEnricher(
        tmp_path,
        executable="/tools/clang++",
        runner=runner,
    ).enrich_node_link(merged)

    calls = [edge for edge in result["links"] if edge.get("relation") == "calls"]
    assert len(calls) == 1
    assert calls[0]["confidence"] == "EXTRACTED"
    assert calls[0]["semantic_provider"] == "clang"
    assert calls[0]["previous_context"] == "cross_partition"
    assert "_partition_call" not in calls[0]
    assert result["graph"] == {"name": "merged"}
    assert result["semantic_enrichment"]["clang"]["upgraded_calls"] == 1
