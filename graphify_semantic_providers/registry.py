"""Pluggable language-provider registry.

Adding a language is data: register a :class:`ProviderSpec` or load a bounded
JSON manifest.  The runner and Graphify merger do not need language-specific
changes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import ProviderSpec


_BUILTINS = (
    ProviderSpec(
        name="rust-analyzer",
        languages=("rust",),
        extensions=(".rs",),
        command=("rust-analyzer",),
        binary_env="GRAPHIFY_SEMANTIC_RUST_BINARY",
        project_markers=("Cargo.toml",),
        description="Rust definitions, references, implementations and call hierarchy.",
    ),
    ProviderSpec(
        name="typescript-language-server",
        languages=("typescript", "javascript"),
        extensions=(".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"),
        command=("typescript-language-server", "--stdio"),
        binary_env="GRAPHIFY_SEMANTIC_TYPESCRIPT_BINARY",
        project_markers=("tsconfig.json", "jsconfig.json", "package.json"),
        description="TypeScript and JavaScript language-service semantics.",
    ),
    ProviderSpec(
        name="eclipse-jdtls",
        languages=("java",),
        extensions=(".java",),
        command=("jdtls",),
        binary_env="GRAPHIFY_SEMANTIC_JAVA_BINARY",
        project_markers=("pom.xml", "build.gradle", "build.gradle.kts"),
        description="Java semantics through Eclipse JDT Language Server.",
    ),
    ProviderSpec(
        name="kotlin-lsp",
        languages=("kotlin",),
        extensions=(".kt", ".kts"),
        command=("kotlin-lsp",),
        binary_env="GRAPHIFY_SEMANTIC_KOTLIN_BINARY",
        project_markers=("build.gradle.kts", "settings.gradle.kts", "pom.xml"),
        description="Kotlin/JVM semantics through JetBrains' official Kotlin LSP.",
    ),
    ProviderSpec(
        name="csharp-ls",
        languages=("csharp",),
        extensions=(".cs",),
        command=("csharp-ls",),
        binary_env="GRAPHIFY_SEMANTIC_CSHARP_BINARY",
        project_markers=("*.sln", "*.slnx", "*.csproj"),
        description="C# semantics through Roslyn-backed csharp-ls.",
    ),
    ProviderSpec(
        name="pyright",
        languages=("python",),
        extensions=(".py", ".pyi"),
        command=("pyright-langserver", "--stdio"),
        binary_env="GRAPHIFY_SEMANTIC_PYTHON_BINARY",
        project_markers=("pyproject.toml", "pyrightconfig.json", "setup.cfg"),
        description="Python type and reference evidence through Pyright.",
    ),
    ProviderSpec(
        name="gopls",
        languages=("go",),
        extensions=(".go",),
        command=("gopls", "serve"),
        binary_env="GRAPHIFY_SEMANTIC_GO_BINARY",
        project_markers=("go.mod", "go.work"),
        description="Go definitions, references and call hierarchy.",
    ),
    ProviderSpec(
        name="phpactor",
        languages=("php",),
        extensions=(".php",),
        command=("phpactor", "language-server"),
        binary_env="GRAPHIFY_SEMANTIC_PHP_BINARY",
        project_markers=("composer.json",),
        description="PHP language-server semantics through open-source Phpactor.",
    ),
    ProviderSpec(
        name="ruby-lsp",
        languages=("ruby",),
        extensions=(".rb", ".rake"),
        command=("ruby-lsp",),
        binary_env="GRAPHIFY_SEMANTIC_RUBY_BINARY",
        project_markers=("Gemfile",),
        description="Ruby language-server semantics.",
    ),
)


class ProviderRegistry:
    """Deterministic provider lookup with explicit duplicate rejection."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> None:
        if spec.name in self._providers:
            raise ValueError(f"provider already registered: {spec.name}")
        self._providers[spec.name] = spec

    def get(self, name: str) -> ProviderSpec:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"unknown provider: {name}") from exc

    def all(self) -> tuple[ProviderSpec, ...]:
        return tuple(self._providers[name] for name in sorted(self._providers))

    def for_path(self, path: Path) -> tuple[ProviderSpec, ...]:
        suffix = path.suffix.lower()
        return tuple(spec for spec in self.all() if suffix in spec.extensions)

    def for_workspace(self, root: Path) -> tuple[ProviderSpec, ...]:
        """Return providers whose project markers exist in ``root``.

        Markers are deliberately shallow and may be exact names or glob
        patterns.  Auto-selection uses them to avoid launching every language
        server for incidental vendored/example files; explicit selection can
        still run a provider without a marker.
        """

        root = root.resolve()
        selected: list[ProviderSpec] = []
        for spec in self.all():
            if not spec.project_markers:
                selected.append(spec)
                continue
            if any(any(root.glob(marker)) for marker in spec.project_markers):
                selected.append(spec)
        return tuple(selected)

    def load_manifest(self, path: Path) -> ProviderSpec:
        """Load one operator-trusted plugin manifest with strict shape limits."""

        raw = path.read_bytes()
        if len(raw) > 64 * 1024:
            raise ValueError("provider manifest exceeds 64 KiB")
        doc = json.loads(raw)
        if not isinstance(doc, dict):
            raise ValueError("provider manifest must be an object")
        allowed = {
            "name",
            "languages",
            "extensions",
            "command",
            "binary_env",
            "project_markers",
            "initialization_options",
            "description",
        }
        unknown = set(doc) - allowed
        if unknown:
            raise ValueError(f"unknown provider manifest fields: {sorted(unknown)}")
        spec = ProviderSpec(
            name=_string(doc, "name"),
            languages=_strings(doc, "languages"),
            extensions=_strings(doc, "extensions"),
            command=_strings(doc, "command"),
            binary_env=_string(doc, "binary_env"),
            project_markers=_strings(doc, "project_markers", required=False),
            initialization_options=_object(doc, "initialization_options"),
            description=str(doc.get("description", "")),
        )
        self.register(spec)
        return spec


def builtin_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    for spec in _BUILTINS:
        registry.register(spec)
    return registry


def _string(doc: dict[str, Any], key: str) -> str:
    value = doc.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider manifest field {key!r} must be a non-empty string")
    return value


def _strings(doc: dict[str, Any], key: str, *, required: bool = True) -> tuple[str, ...]:
    value = doc.get(key)
    if value is None and not required:
        return ()
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise ValueError(f"provider manifest field {key!r} must be a non-empty string array")
    if len(value) > 64:
        raise ValueError(f"provider manifest field {key!r} exceeds 64 entries")
    return tuple(value)


def _object(doc: dict[str, Any], key: str) -> dict[str, Any]:
    value = doc.get(key, {})
    if not isinstance(value, dict):
        raise ValueError(f"provider manifest field {key!r} must be an object")
    return value
