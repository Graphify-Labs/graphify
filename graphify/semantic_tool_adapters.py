"""Static capability contracts for optional semantic analysis tools."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable


class SemanticOutputContract(str, Enum):
    """The output Graphify can validate for a tool profile."""

    DIRECT_GRAPH_FACTS = "direct_graph_facts"
    SCIP_JSON_ARTIFACT = "scip_json_artifact"


@dataclass(frozen=True)
class SemanticToolProfile:
    """Immutable execution and artifact capability for one ecosystem."""

    adapter_id: str
    languages: frozenset[str]
    executables: tuple[str, ...]
    project_markers: tuple[str, ...]
    output_contract: SemanticOutputContract
    artifact_filename: str

    def artifact_path(self, project_root: Path | str) -> Path:
        return (
            Path(project_root) / ".graphify" / "semantic" / self.artifact_filename
        ).resolve()


_PROFILES: tuple[SemanticToolProfile, ...] = (
    SemanticToolProfile(
        "clang",
        frozenset({"c", "cpp"}),
        ("clang++", "clang"),
        ("compile_commands.json", "build/compile_commands.json", "out/compile_commands.json"),
        SemanticOutputContract.DIRECT_GRAPH_FACTS,
        "clang.scip.json",
    ),
    SemanticToolProfile(
        "jdt",
        frozenset({"java", "kotlin"}),
        ("jdtls",),
        ("pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "jdt.scip.json",
    ),
    SemanticToolProfile(
        "roslyn",
        frozenset({"csharp"}),
        ("csharp-ls", "Microsoft.CodeAnalysis.LanguageServer"),
        ("*.sln", "*.csproj", "**/*.csproj"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "roslyn.scip.json",
    ),
    SemanticToolProfile(
        "typescript",
        frozenset({"javascript", "typescript"}),
        ("typescript-language-server", "tsserver"),
        ("tsconfig.json", "jsconfig.json", "package.json"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "typescript.scip.json",
    ),
    SemanticToolProfile(
        "gopls",
        frozenset({"go"}),
        ("gopls",),
        ("go.mod", "go.work"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "gopls.scip.json",
    ),
    SemanticToolProfile(
        "rust_analyzer",
        frozenset({"rust"}),
        ("rust-analyzer",),
        ("Cargo.toml",),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "rust_analyzer.scip.json",
    ),
    SemanticToolProfile(
        "pyright",
        frozenset({"python"}),
        ("pyright-langserver", "pyright"),
        ("pyrightconfig.json", "pyproject.toml", "setup.cfg"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "pyright.scip.json",
    ),
    SemanticToolProfile(
        "php_static_analysis",
        frozenset({"php"}),
        ("phpstan", "psalm", "psalm-language-server"),
        ("phpstan.neon", "phpstan.neon.dist", "psalm.xml", "psalm.xml.dist", "composer.json"),
        SemanticOutputContract.SCIP_JSON_ARTIFACT,
        "php_static_analysis.scip.json",
    ),
)


def semantic_tool_profiles() -> tuple[SemanticToolProfile, ...]:
    """Return the built-in tool catalog in stable display order."""

    return _PROFILES


def semantic_tool_profile(adapter_id: str) -> SemanticToolProfile:
    for profile in _PROFILES:
        if profile.adapter_id == adapter_id:
            return profile
    raise ValueError(f"unknown semantic analyzer: {adapter_id}")


def validate_adapter_selection(adapter_ids: Iterable[str]) -> tuple[str, ...]:
    """Validate and order a user selection without allowing command injection."""

    known = {profile.adapter_id for profile in _PROFILES}
    selected: list[str] = []
    for raw_adapter_id in adapter_ids:
        adapter_id = str(raw_adapter_id).strip()
        if adapter_id not in known:
            raise ValueError(f"unknown semantic analyzer: {adapter_id}")
        if adapter_id not in selected:
            selected.append(adapter_id)
    return tuple(selected)
