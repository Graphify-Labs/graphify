from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify_semantic_providers.registry import ProviderRegistry, builtin_registry


def test_builtin_registry_covers_popular_web_languages() -> None:
    languages = {language for spec in builtin_registry().all() for language in spec.languages}
    assert {
        "rust",
        "typescript",
        "javascript",
        "java",
        "kotlin",
        "csharp",
        "python",
        "go",
        "php",
        "ruby",
    } <= languages


def test_registry_dispatches_javascript_without_typescript_rework() -> None:
    providers = builtin_registry().for_path(Path("src/app.jsx"))
    assert [provider.name for provider in providers] == ["typescript-language-server"]


def test_workspace_auto_selection_requires_project_marker(tmp_path: Path) -> None:
    registry = builtin_registry()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    assert "pyright" not in {spec.name for spec in registry.for_workspace(tmp_path)}

    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    assert "pyright" in {spec.name for spec in registry.for_workspace(tmp_path)}


def test_workspace_marker_globs_cover_csharp_projects(tmp_path: Path) -> None:
    (tmp_path / "Product.csproj").write_text("<Project />\n", encoding="utf-8")
    assert "csharp-ls" in {spec.name for spec in builtin_registry().for_workspace(tmp_path)}


def test_operator_manifest_adds_language_as_data(tmp_path: Path) -> None:
    manifest = tmp_path / "dart.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "dart-analysis-server",
                "languages": ["dart"],
                "extensions": [".dart"],
                "command": ["dart", "language-server", "--protocol=lsp"],
                "binary_env": "GRAPHIFY_SEMANTIC_DART_BINARY",
                "project_markers": ["pubspec.yaml"],
                "initialization_options": {},
            }
        ),
        encoding="utf-8",
    )
    registry = ProviderRegistry()
    spec = registry.load_manifest(manifest)
    assert spec.languages == ("dart",)
    assert registry.for_path(Path("lib/main.dart")) == (spec,)


def test_manifest_rejects_shell_string_and_unknown_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "unsafe.json"
    manifest.write_text(
        json.dumps(
            {
                "name": "unsafe",
                "languages": ["x"],
                "extensions": [".x"],
                "command": "server --stdio; rm -rf /",
                "binary_env": "X",
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown provider manifest fields"):
        ProviderRegistry().load_manifest(manifest)
