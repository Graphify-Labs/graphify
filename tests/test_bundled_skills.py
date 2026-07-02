"""Tests for graphify.installer.bundled_skills.

Covers registry structure (count, names, uniqueness), frontmatter validity,
and per-host install path derivation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify.installer import bundled_skills
from graphify.installer.bundled_skills import (
    BundledSkill,
    all_bundled,
    bundled_skill_dir,
    supports_host,
)
from graphify.installer.host_probe import KNOWN_HOSTS, host_skill_dir


class TestBundledSkillsRegistry:
    """Structural checks on the _BUNDLED tuple — fast, catches regressions."""

    def test_count_is_15(self):
        assert len(all_bundled()) == 15

    def test_names_unique(self):
        names = [s.name for s in all_bundled()]
        assert len(names) == len(set(names))

    def test_superpowers_count_is_14(self):
        sp = [s for s in all_bundled() if s.name != "gf-llm-wiki"]
        assert len(sp) == 14

    def test_every_entry_has_gf_prefix(self):
        for s in all_bundled():
            assert s.name.startswith("gf-"), f"{s.name} missing gf- prefix"

    def test_all_source_files_exist(self, package_root: Path):
        """Every source_subpath must resolve to a real file in the repo."""
        for s in all_bundled():
            assert (package_root / s.source_subpath).exists(), (
                f"{s.source_subpath} does not exist under package_root"
            )

    def test_superpowers_license_present(self, package_root: Path):
        assert (package_root / "bundled_skills" / "superpowers" / "LICENSE").exists()


class TestBundledSkillDir:
    """`bundled_skill_dir()` must produce the right path per host."""

    @pytest.mark.parametrize("host_name,expected_suffix", [
        ("claude",      ".claude/skills/gf-brainstorming"),
        ("codex",       ".codex/skills/gf-brainstorming"),
        ("aider",       ".aider/gf-brainstorming"),                # no skills/ parent
        ("pi",          ".pi/agent/skills/gf-brainstorming"),     # extra agent/ prefix
        ("mobilecoder", ".mobilecoder/skills/gf-brainstorming"),
    ])
    def test_path_for_supported_hosts(self, tmp_path, host_name, expected_suffix):
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        result = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path)
        assert str(result).endswith(expected_suffix), (
            f"got {result}, expected suffix {expected_suffix}"
        )

    def test_unknown_skill_name_still_works(self, tmp_path):
        """Function takes any name, not just registered ones."""
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        result = bundled_skill_dir(host, "gf-anything-future", root=tmp_path)
        assert result == tmp_path / ".claude" / "skills" / "gf-anything-future"

    def test_cursor_subpath_falls_back_to_skills_layout(self, tmp_path):
        """cursor has subpath `rules` (not ending in graphify) → defensive fallback."""
        host = next(h for h in KNOWN_HOSTS if h.name == "cursor")
        result = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path)
        assert result == tmp_path / ".cursor" / "skills" / "gf-brainstorming"


class TestSupportsHost:
    """`supports_host()` returns False for cursor/gemini, True otherwise."""

    @pytest.mark.parametrize("host_name", ["claude", "codex", "opencode", "kilo",
                                            "aider", "copilot", "claw", "droid",
                                            "trae", "kiro", "pi", "vscode", "amp",
                                            "agents", "antigravity",
                                            "codebuddy", "hermes", "trae-cn",
                                            "mobilecoder"])
    def test_supports_common_hosts(self, host_name):
        assert supports_host(host_name) is True

    @pytest.mark.parametrize("host_name", ["cursor", "gemini"])
    def test_skips_format_incompatible_hosts(self, host_name):
        assert supports_host(host_name) is False