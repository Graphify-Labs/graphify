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


class TestBundledSkillsFrontmatter:
    """Each SKILL.md's frontmatter `name:` must equal BundledSkill.name."""

    def test_all_skills_have_valid_yaml_frontmatter(self, package_root: Path):
        import yaml
        for s in all_bundled():
            text = (package_root / s.source_subpath).read_text(encoding="utf-8")
            assert text.startswith("---\n"), f"{s.source_subpath}: no frontmatter"
            end = text.find("\n---", 4)
            assert end > 0, f"{s.source_subpath}: unterminated frontmatter"
            fm = yaml.safe_load(text[4:end])
            assert isinstance(fm, dict), f"{s.source_subpath}: frontmatter not a YAML mapping"
            assert "name" in fm, f"{s.source_subpath}: missing `name` field"
            assert "description" in fm, f"{s.source_subpath}: missing `description` field"

    def test_frontmatter_name_matches_registry(self, package_root: Path):
        import yaml
        for s in all_bundled():
            text = (package_root / s.source_subpath).read_text(encoding="utf-8")
            end = text.find("\n---", 4)
            fm = yaml.safe_load(text[4:end])
            assert fm["name"] == s.name, (
                f"{s.source_subpath}: frontmatter name `{fm['name']}` != registry `{s.name}`"
            )


class TestCopyBundledSkills:
    """`copy_bundled_skills()` writes SKILL.md for each supported host."""

    def _setup_fake_package(self, tmp_path: Path) -> Path:
        """Build a minimal graphify/ package dir under tmp_path with the
        15 bundled SKILL.md files. Mirrors the real layout.
        """
        pkg = tmp_path / "graphify"
        for s in all_bundled():
            f = pkg / s.source_subpath
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(
                f"---\nname: {s.name}\ndescription: stub\n---\n# {s.name}\n",
                encoding="utf-8",
            )
        # Superpowers LICENSE for the registry's structural test
        (pkg / "bundled_skills" / "superpowers" / "LICENSE").write_text(
            "MIT\n", encoding="utf-8"
        )
        # llm-wiki references/ sidecar
        (pkg / "bundled_skills" / "llm-wiki" / "references").mkdir(parents=True, exist_ok=True)
        (pkg / "bundled_skills" / "llm-wiki" / "references" / "x.md").write_text(
            "ref\n", encoding="utf-8"
        )
        return pkg

    @pytest.mark.parametrize("host_name", ["claude", "codex", "opencode", "kilo",
                                            "aider", "pi", "claw", "droid",
                                            "vscode", "amp", "agents"])
    def test_writes_skills_for_supported_hosts(self, tmp_path, host_name):
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        assert (target / "SKILL.md").exists(), f"missing {target}/SKILL.md"

    def test_writes_llm_wiki_references_sidecar(self, tmp_path):
        """gf-llm-wiki has has_references=True → references/ must be copied."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-llm-wiki", root=tmp_path / "home")
        assert (target / "SKILL.md").exists()
        assert (target / "references" / "x.md").exists()

    def test_does_not_write_references_for_superpowers(self, tmp_path):
        """gf-brainstorming has has_references=False → no references/ written."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        assert not (target / "references").exists()

    @pytest.mark.parametrize("host_name", ["cursor", "gemini"])
    def test_skips_unsupported_hosts(self, tmp_path, host_name):
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        # Nothing under the host marker should have any SKILL.md
        marker = tmp_path / "home" / host.marker
        if marker.exists():
            assert not any(marker.rglob("SKILL.md"))

    def test_always_overwrites_existing(self, tmp_path):
        """Always-overwrite semantics: any pre-existing SKILL.md is replaced."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        target_dir = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        target_dir.mkdir(parents=True)
        (target_dir / "SKILL.md").write_text("# OLD USER CONTENT — should be replaced", encoding="utf-8")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        assert "# OLD USER CONTENT" not in (target_dir / "SKILL.md").read_text(encoding="utf-8")