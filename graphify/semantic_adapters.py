"""Contracts and discovery for optional build-aware semantic enrichment.

Tree-sitter remains Graphify's portable syntax layer. Adapters implementing the
protocol in this module may add compiler-resolved facts to the same graph, but
discovery never executes a project tool and never implies that translation has
succeeded. Keeping discovery separate from analysis lets CLI policy, sandboxing,
and future per-tool translators evolve without coupling them to graph building.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import shutil
from typing import Callable, Protocol, Sequence

from graphify.ontology import normalize_relation


class AdapterState(str, Enum):
    """Whether an adapter has the local prerequisites to attempt analysis."""

    READY = "ready"
    FALLBACK_READY = "fallback_ready"
    MISSING_TOOL = "missing_tool"
    MISSING_PROJECT_CONFIG = "missing_project_config"


@dataclass(frozen=True)
class SemanticAdapterSpec:
    """Static activation requirements for one semantic analysis ecosystem."""

    adapter_id: str
    languages: frozenset[str]
    executables: tuple[str, ...]
    project_markers: tuple[str, ...]


@dataclass(frozen=True)
class AdapterStatus:
    """Read-only discovery result; no analyzer process has run yet."""

    adapter_id: str
    languages: frozenset[str]
    state: AdapterState
    executable: str | None = None
    project_marker: str | None = None


@dataclass(frozen=True)
class SemanticAnalysisRequest:
    """Input boundary shared by concrete compiler and language-server adapters."""

    project_root: Path
    source_files: tuple[Path, ...]
    executable: str


@dataclass
class SemanticFactBatch:
    """Universal Graphify facts returned by a concrete semantic adapter.

    Concrete adapters translate their native identities into Graphify node and
    edge dictionaries before returning. Diagnostics are data rather than raised
    errors so one failed language can fall back to tree-sitter independently.
    """

    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)


class SemanticEnrichmentAdapter(Protocol):
    """Small integration contract implemented by each tool-specific translator."""

    @property
    def spec(self) -> SemanticAdapterSpec: ...

    def analyze(self, request: SemanticAnalysisRequest) -> SemanticFactBatch: ...


class SemanticGraphEnricher(Protocol):
    """Executable adapter that can only enrich an existing graph extraction."""

    def enrich(self, extraction: dict) -> dict: ...


_SPECS: tuple[SemanticAdapterSpec, ...] = (
    SemanticAdapterSpec(
        "clang",
        frozenset({"c", "cpp"}),
        ("clang++", "clang"),
        ("compile_commands.json", "build/compile_commands.json", "out/compile_commands.json"),
    ),
    SemanticAdapterSpec(
        "jdt",
        frozenset({"java", "kotlin"}),
        ("jdtls",),
        ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
    ),
    SemanticAdapterSpec(
        "roslyn",
        frozenset({"csharp"}),
        ("csharp-ls", "Microsoft.CodeAnalysis.LanguageServer"),
        ("*.sln", "*.csproj", "**/*.csproj"),
    ),
    SemanticAdapterSpec(
        "typescript",
        frozenset({"javascript", "typescript"}),
        ("typescript-language-server", "tsserver"),
        ("tsconfig.json", "jsconfig.json", "package.json"),
    ),
    SemanticAdapterSpec(
        "gopls",
        frozenset({"go"}),
        ("gopls",),
        ("go.mod", "go.work"),
    ),
    SemanticAdapterSpec(
        "rust_analyzer",
        frozenset({"rust"}),
        ("rust-analyzer",),
        ("Cargo.toml",),
    ),
    SemanticAdapterSpec(
        "pyright",
        frozenset({"python"}),
        ("pyright-langserver", "pyright"),
        ("pyrightconfig.json", "pyproject.toml", "setup.cfg"),
    ),
    SemanticAdapterSpec(
        "php_static_analysis",
        frozenset({"php"}),
        ("phpstan", "psalm", "psalm-language-server"),
        ("phpstan.neon", "phpstan.neon.dist", "psalm.xml", "psalm.xml.dist", "composer.json"),
    ),
)


def semantic_adapter_specs() -> tuple[SemanticAdapterSpec, ...]:
    """Return the immutable built-in adapter catalog."""

    return _SPECS


def _first_executable(
    candidates: Sequence[str],
    locator: Callable[[str], str | None],
) -> str | None:
    for candidate in candidates:
        executable = locator(candidate)
        if executable:
            return executable
    return None


def _first_project_marker(root: Path, patterns: Sequence[str]) -> str | None:
    for pattern in patterns:
        match = next((path for path in root.glob(pattern) if path.is_file()), None)
        if match is not None:
            return match.relative_to(root).as_posix()
    return None


def discover_semantic_adapters(
    project_root: Path | str,
    *,
    locator: Callable[[str], str | None] = shutil.which,
) -> list[AdapterStatus]:
    """Inspect prerequisites for every adapter without executing external code.

    Tool absence is reported before project configuration absence because it is
    the actionable global prerequisite. A present tool still requires an
    ecosystem marker; this avoids claiming semantic coverage solely because a
    language server happens to be installed on the machine.
    """

    root = Path(project_root).resolve()
    statuses: list[AdapterStatus] = []
    for spec in _SPECS:
        executable = _first_executable(spec.executables, locator)
        marker = _first_project_marker(root, spec.project_markers)
        if executable is None:
            state = AdapterState.MISSING_TOOL
        elif marker is None and spec.adapter_id == "clang":
            state = AdapterState.FALLBACK_READY
        elif marker is None:
            state = AdapterState.MISSING_PROJECT_CONFIG
        else:
            state = AdapterState.READY
        statuses.append(AdapterStatus(
            adapter_id=spec.adapter_id,
            languages=spec.languages,
            state=state,
            executable=executable,
            project_marker=marker,
        ))
    return statuses


class SemanticEnrichmentService:
    """Merge analyzer-produced SCIP JSON into deterministic AST extraction.

    Language servers and compilers expose incompatible live protocols. The
    stable boundary is an artifact: each ecosystem writes simplified SCIP JSON
    to ``.graphify/semantic/<adapter-id>.scip.json``. Loading is local,
    deterministic, size-bounded, and fail-soft, so unavailable or malformed
    optional analysis never removes tree-sitter evidence.
    """

    _MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

    def __init__(
        self,
        project_root: Path | str,
        *,
        enrichers: Sequence[SemanticGraphEnricher] | None = None,
        executable_locator: Callable[[str], str | None] = shutil.which,
        process_runner: Callable | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.artifact_root = (self.project_root / ".graphify" / "semantic").resolve()
        self._adapter_ids = frozenset(spec.adapter_id for spec in _SPECS)
        if enrichers is None:
            from graphify.clang_enrichment import ClangSemanticEnricher, run_clang_command

            clang = executable_locator("clang++") or executable_locator("clang")
            enrichers = (
                ClangSemanticEnricher(
                    self.project_root,
                    executable=clang,
                    runner=process_runner or run_clang_command,
                ),
            ) if clang else ()
        self._enrichers = tuple(enrichers)

    def enrich(self, extraction: dict) -> dict:
        """Return a copied extraction with every valid local artifact merged."""

        # Executable adapters operate first so artifact ingestion sees the same
        # graph that compiler confirmation produced. Each adapter owns its
        # fail-soft diagnostics; an unexpected boundary exception is isolated
        # here so optional semantics can never discard the AST baseline.
        working = dict(extraction)
        runner_diagnostics: list[str] = []
        for enricher in self._enrichers:
            try:
                working = enricher.enrich(working)
            except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
                runner_diagnostics.append(
                    f"{type(enricher).__name__}: {type(exc).__name__}: {exc}"
                )
        node_map = {
            str(node.get("id")): dict(node)
            for node in working.get("nodes", [])
            if isinstance(node, dict) and node.get("id")
        }
        edges = [dict(edge) for edge in working.get("edges", []) if isinstance(edge, dict)]
        edge_keys = {self._edge_key(edge) for edge in edges}
        diagnostics: list[str] = runner_diagnostics
        loaded = 0

        for artifact in self._artifacts(diagnostics):
            adapter_id = artifact.name.removesuffix(".scip.json")
            if adapter_id not in self._adapter_ids:
                diagnostics.append(f"{artifact.name}: unknown semantic adapter id")
                continue
            try:
                if artifact.stat().st_size > self._MAX_ARTIFACT_BYTES:
                    raise ValueError("artifact exceeds 64 MiB safety limit")
                payload = json.loads(artifact.read_text(encoding="utf-8"))
                # Import lazily: projects that never opt into compiler artifacts
                # do not pay for, or become coupled to, the SCIP translator.
                from graphify.scip_ingest import ingest_scip_json

                facts = ingest_scip_json(payload)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
                diagnostics.append(f"{artifact.name}: {type(exc).__name__}: {exc}")
                continue

            for node in facts.get("nodes", []):
                if not isinstance(node, dict) or not node.get("id"):
                    continue
                node_id = str(node["id"])
                existing = node_map.get(node_id, {})
                node_map[node_id] = {**existing, **node}
            for edge in facts.get("edges", []):
                if not isinstance(edge, dict):
                    continue
                edge = dict(edge)
                canonical_relation = normalize_relation(str(edge.get("relation", "")))
                if canonical_relation is not None:
                    edge["relation"] = canonical_relation
                key = self._edge_key(edge)
                if key in edge_keys:
                    continue
                edge_keys.add(key)
                edges.append(dict(edge))
            loaded += 1

        result = dict(working)
        result["nodes"] = list(node_map.values())
        result["edges"] = edges
        existing_enrichment = working.get("semantic_enrichment")
        enrichment = dict(existing_enrichment) if isinstance(existing_enrichment, dict) else {}
        enrichment.update({
            "artifacts_loaded": loaded,
            "diagnostics": diagnostics,
        })
        result["semantic_enrichment"] = enrichment
        return result

    def enrich_node_link(self, graph: dict) -> dict:
        """Apply semantic enrichment to persisted ``links``-shaped graph JSON."""

        extraction = dict(graph)
        extraction["edges"] = [
            dict(edge) for edge in graph.get("links", []) if isinstance(edge, dict)
        ]
        enriched = self.enrich(extraction)
        result = dict(graph)
        result["nodes"] = enriched["nodes"]
        result["links"] = enriched["edges"]
        result["semantic_enrichment"] = enriched["semantic_enrichment"]
        return result

    def _artifacts(self, diagnostics: list[str]) -> tuple[Path, ...]:
        if not self.artifact_root.is_dir():
            return ()
        try:
            self.artifact_root.relative_to(self.project_root)
        except ValueError:
            diagnostics.append("semantic artifact directory escapes project root")
            return ()
        artifacts: list[Path] = []
        for candidate in sorted(self.artifact_root.glob("*.scip.json")):
            try:
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(self.artifact_root)
            except (OSError, ValueError):
                diagnostics.append(f"{candidate.name}: artifact escapes semantic directory")
                continue
            if resolved.is_file():
                artifacts.append(resolved)
        return tuple(artifacts)

    @staticmethod
    def _edge_key(edge: dict) -> tuple[str, str, str, str]:
        return (
            str(edge.get("source", "")),
            str(edge.get("target", "")),
            str(edge.get("relation", "")),
            str(edge.get("source_location", "")),
        )
