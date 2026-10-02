"""Truthful execution and artifact contracts for language tool adapters."""

from pathlib import Path

import pytest

from graphify.semantic_tool_adapters import (
    SemanticOutputContract,
    semantic_tool_profiles,
    validate_adapter_selection,
)


def test_only_clang_claims_a_direct_translator():
    profiles = {profile.adapter_id: profile for profile in semantic_tool_profiles()}

    assert profiles["clang"].output_contract is SemanticOutputContract.DIRECT_GRAPH_FACTS
    assert all(
        profile.output_contract is SemanticOutputContract.SCIP_JSON_ARTIFACT
        for adapter_id, profile in profiles.items()
        if adapter_id != "clang"
    )


def test_profiles_cover_each_requested_language_ecosystem():
    profiles = {profile.adapter_id: profile for profile in semantic_tool_profiles()}

    assert set(profiles) == {
        "clang", "jdt", "roslyn", "typescript", "gopls",
        "rust_analyzer", "pyright", "php_static_analysis",
    }
    assert profiles["jdt"].artifact_filename == "jdt.scip.json"
    assert profiles["php_static_analysis"].artifact_filename == "php_static_analysis.scip.json"


def test_adapter_selection_is_deduplicated_and_rejects_unknown_ids():
    assert validate_adapter_selection(["pyright", "clang", "pyright"]) == (
        "pyright",
        "clang",
    )
    with pytest.raises(ValueError, match="unknown semantic analyzer"):
        validate_adapter_selection(["attacker"])


def test_profile_artifact_paths_are_fixed_under_semantic_directory(tmp_path: Path):
    profile = next(
        item for item in semantic_tool_profiles() if item.adapter_id == "typescript"
    )

    assert profile.artifact_path(tmp_path) == (
        tmp_path / ".graphify" / "semantic" / "typescript.scip.json"
    ).resolve()
