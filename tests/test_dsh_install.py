"""Tests for the DeepSeek Harness (DSH) platform target.

``graphify install --platform dsh`` writes the skill into DSH's skill roots
(``~/.dsh/skills`` for a user install, ``./.dsh/skills`` for ``--project``) and
registers graphify's MCP server (``python -m graphify.serve <graph.json>``) in
DSH's user-global loader patch layer:

    $DSH_HOME/cordis.patch.yml     (default: ~/.dsh/cordis.patch.yml)

DSH composes that file after the profile's own ``cordis.patch.yml``, so the
graph tools appear as ``mcp__graphify__*`` without touching the profile.
DSH has no project-scoped configuration layer, so ``--project`` installs only
the skill; the MCP entry stays user-global and serves the ``graph.json`` of the
project the installer ran in.

The entry is wrapped in marker comments: install is idempotent, uninstall
removes exactly graphify's block, and a user's own entries survive both.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import graphify.__main__ as mainmod
import graphify.install as install_mod


BEGIN = install_mod._DSH_MCP_MARKER_BEGIN
END = install_mod._DSH_MCP_MARKER_END


def _run(cwd: Path, argv, home: Path, monkeypatch, dsh_home: Path | None = None) -> None:
    """Drive main() with argv, cwd at *cwd*, and Path.home redirected to *home*."""
    if dsh_home is not None:
        monkeypatch.setenv("DSH_HOME", str(dsh_home))
    old_cwd = Path.cwd()
    try:
        os.chdir(cwd)
        with patch.object(sys, "argv", ["graphify", *argv]):
            with patch("graphify.__main__.Path.home", return_value=home):
                mainmod.main()
    finally:
        os.chdir(old_cwd)


def _skill(home: Path) -> Path:
    return home / ".dsh" / "skills" / "graphify" / "SKILL.md"


def _patch_file(dsh_home: Path) -> Path:
    return dsh_home / "cordis.patch.yml"


# --- destination map -----------------------------------------------------------


def test_dsh_registered_in_platform_config():
    """dsh reuses the generic agents skill bundle (standard SKILL.md frontmatter)."""
    cfg = mainmod._PLATFORM_CONFIG["dsh"]
    assert cfg["skill_file"] == "skill-agents.md"
    assert cfg["skill_refs"] == "agents"
    assert cfg["claude_md"] is False


def test_deepseek_spellings_alias_dsh():
    """`--platform deepseek` / `deepseek-harness` reach the dsh target."""
    assert install_mod._canonical_platform("dsh") == "dsh"
    assert install_mod._canonical_platform("deepseek") == "dsh"
    assert install_mod._canonical_platform("deepseek-harness") == "dsh"


def test_dsh_user_destination_is_dot_dsh_skills(tmp_path):
    with patch("graphify.__main__.Path.home", return_value=tmp_path):
        dst = mainmod._platform_skill_destination("dsh", project=False)
    assert dst == tmp_path / ".dsh" / "skills" / "graphify" / "SKILL.md"


def test_dsh_project_destination_is_project_dot_dsh(tmp_path):
    dst = mainmod._platform_skill_destination("dsh", project=True, project_dir=tmp_path)
    assert dst == tmp_path / ".dsh" / "skills" / "graphify" / "SKILL.md"


def test_dsh_user_destination_honours_dsh_home(tmp_path, monkeypatch):
    """DSH_HOME moves the skill root exactly like it moves the patch layer."""
    monkeypatch.setenv("DSH_HOME", str(tmp_path / "elsewhere"))
    dst = install_mod._platform_skill_destination("dsh", project=False)
    assert dst == tmp_path / "elsewhere" / "skills" / "graphify" / "SKILL.md"


def test_install_platform_dsh_custom_home_writes_both_roots(tmp_path, monkeypatch):
    """Both the skill and the MCP registration follow DSH_HOME."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = tmp_path / "custom-dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)

    assert (dsh_home / "skills" / "graphify" / "SKILL.md").exists()
    assert (dsh_home / "cordis.patch.yml").exists()
    assert not (home / ".dsh").exists()


# --- user-scope install --------------------------------------------------------


def test_install_platform_dsh_writes_skill_and_mcp_entry(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)

    skill = _skill(home)
    assert skill.exists()
    assert (skill.parent / ".graphify_version").read_text() == mainmod.__version__
    assert (skill.parent / "references" / "extraction-spec.md").exists()

    patch_file = _patch_file(dsh_home)
    text = patch_file.read_text(encoding="utf-8")
    assert BEGIN in text and END in text
    assert "name: '@deepseek-ai/dsh-mcp-client'" in text
    assert "serverName: graphify" in text
    assert "transport: stdio" in text
    assert "graphify.serve" in text
    assert str(Path(sys.executable)) in text
    graph_json = (proj / "graphify-out" / "graph.json").resolve()
    assert f"'{graph_json}'" in text
    # The installer only points at the graph; it never creates one.
    assert not graph_json.exists()


def test_install_platform_dsh_is_idempotent(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)
    first = _patch_file(dsh_home).read_text(encoding="utf-8")
    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)
    second = _patch_file(dsh_home).read_text(encoding="utf-8")

    assert first == second
    assert second.count(BEGIN) == 1
    assert second.count("- id: mcp-graphify") == 1


def test_install_platform_dsh_preserves_user_patch_entries(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    dsh_home.mkdir(parents=True)
    user_entry = (
        "- insert:\n"
        "    - id: my-tool\n"
        "      name: '@local/my-tool'\n"
    )
    _patch_file(dsh_home).write_text(user_entry, encoding="utf-8")

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)
    text = _patch_file(dsh_home).read_text(encoding="utf-8")
    assert user_entry.strip() in text
    assert BEGIN in text

    _run(proj, ["uninstall"], home, monkeypatch, dsh_home)
    after = _patch_file(dsh_home).read_text(encoding="utf-8")
    assert user_entry.strip() in after
    assert BEGIN not in after and END not in after


def test_install_platform_dsh_replaces_empty_document_patch(tmp_path, monkeypatch):
    """A patch file holding only `[]` (the shipped empty-layer form) becomes our
    block — appending a block sequence after `[]` would be invalid YAML."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    dsh_home.mkdir(parents=True)
    _patch_file(dsh_home).write_text("[]\n", encoding="utf-8")

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)

    text = _patch_file(dsh_home).read_text(encoding="utf-8")
    assert BEGIN in text
    assert "[]" not in text.splitlines()
    assert text.lstrip().startswith(BEGIN)


def test_dsh_default_home_is_dot_dsh_without_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    monkeypatch.delenv("DSH_HOME", raising=False)

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch)

    assert (home / ".dsh" / "cordis.patch.yml").exists()
    assert _skill(home).exists()


# --- project-scope install -----------------------------------------------------


def test_install_platform_dsh_project_writes_skill_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--project", "--platform", "dsh"], home, monkeypatch, dsh_home)

    project_skill = proj / ".dsh" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()
    assert (project_skill.parent / "references" / "extraction-spec.md").exists()
    # User scope is untouched and no MCP entry is written for a project install.
    assert not _skill(home).exists()
    assert not _patch_file(dsh_home).exists()


# --- the dedicated subcommand --------------------------------------------------


def test_dsh_subcommand_install_uninstall_roundtrip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["dsh", "install"], home, monkeypatch, dsh_home)
    skill = _skill(home)
    assert skill.exists()
    assert (skill.parent / "references").is_dir()
    assert _patch_file(dsh_home).exists()

    _run(proj, ["dsh", "uninstall"], home, monkeypatch, dsh_home)
    assert not skill.exists()
    # The empty managed layer (and its directory) is removed with it.
    assert not _patch_file(dsh_home).exists()


def test_dsh_uninstall_project_removes_project_skill_only(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["dsh", "install", "--project"], home, monkeypatch, dsh_home)
    project_skill = proj / ".dsh" / "skills" / "graphify" / "SKILL.md"
    assert project_skill.exists()

    _run(proj, ["dsh", "uninstall", "--project"], home, monkeypatch, dsh_home)
    assert not project_skill.exists()


def test_graphify_out_env_is_honoured(tmp_path, monkeypatch):
    """GRAPHIFY_OUT relocates the served graph, as it does for every read command."""
    import graphify.install as install_mod

    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    monkeypatch.setattr(install_mod, "_GRAPHIFY_OUT", "shared-out")

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)

    text = _patch_file(dsh_home).read_text(encoding="utf-8")
    graph_json = (proj / "shared-out" / "graph.json").resolve()
    assert f"'{graph_json}'" in text


def test_mcp_block_quotes_paths_with_spaces(tmp_path, monkeypatch):
    """Single-quoted YAML scalars keep a project path with spaces literal."""
    import graphify.install as install_mod

    home = tmp_path / "home"
    proj = tmp_path / "my project"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)

    text = _patch_file(dsh_home).read_text(encoding="utf-8")
    graph_json = (proj / "graphify-out" / "graph.json").resolve()
    assert f"'{graph_json}'" in text
    assert install_mod._DSH_MCP_SERVER_NAME == "graphify"


# --- hostile values and damaged files -----------------------------------------
#
# The patch file is shared with the user, so a value interpolated into the block
# must never be able to start a new line, and a rewrite must never be able to
# swallow user content. Both are asserted against the emitted bytes.


def _install_into(proj: Path, home: Path, dsh_home: Path, monkeypatch) -> str:
    _run(proj, ["install", "--platform", "dsh"], home, monkeypatch, dsh_home)
    return _patch_file(dsh_home).read_text(encoding="utf-8")


def test_mcp_block_escapes_a_path_with_a_single_quote(tmp_path, monkeypatch):
    """A quote in the project path is doubled, not left to terminate the scalar."""
    home = tmp_path / "home"
    proj = tmp_path / "it's here"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()

    text = _install_into(proj, home, dsh_home, monkeypatch)

    graph_json = (proj / "graphify-out" / "graph.json").resolve()
    quoted = "'" + str(graph_json).replace("'", "''") + "'"
    assert quoted in text
    # The escaped scalar parses back to exactly the path, and the block still
    # ends where the marker says it does.
    arg_line = next(line for line in text.splitlines() if line.strip().startswith("- '") and "graph.json" in line)
    assert arg_line.strip() == "- " + quoted
    assert text.count(BEGIN) == 1 and text.count(END) == 1


def test_yaml_quote_escapes_line_breaks_and_control_characters():
    """A path containing a line break cannot split the block into stray YAML."""
    import graphify.install as install_mod

    escaped = install_mod._yaml_quote("/tmp/evil\ngraphify: null\n")
    assert "\n" not in escaped
    assert escaped == '"/tmp/evil\\ngraphify: null\\n"'
    # Control characters such as a carriage return switch to the escaped form too.
    assert install_mod._yaml_quote("/tmp/cr\r") == '"/tmp/cr\\r"'
    # An ordinary path stays in the readable single-quoted form.
    assert install_mod._yaml_quote("/tmp/plain") == "'/tmp/plain'"


def test_install_keeps_user_placeholder_lines_among_real_entries(tmp_path, monkeypatch):
    """`---`, `null`, and `~` belong to the user once the file has real entries."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    dsh_home.mkdir(parents=True)
    user_content = (
        "- insert:\n"
        "    - id: first\n"
        "      name: null\n"
        "      config:\n"
        "        url: ~\n"
        "---\n"
        "- insert:\n"
        "    - id: second\n"
        "      name: '@local/second'\n"
    )
    _patch_file(dsh_home).write_text(user_content, encoding="utf-8")

    text = _install_into(proj, home, dsh_home, monkeypatch)

    assert user_content.strip() in text
    assert text.index(user_content.strip()) < text.index(BEGIN)
    # And uninstall leaves exactly the user's bytes again.
    _run(proj, ["uninstall"], home, monkeypatch, dsh_home)
    assert _patch_file(dsh_home).read_text(encoding="utf-8") == user_content


def test_install_drops_the_empty_document_only_when_it_is_alone(tmp_path, monkeypatch):
    """A patch file that is only `[]` yields to our block; `[]` among entries stays."""
    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    dsh_home.mkdir(parents=True)
    _patch_file(dsh_home).write_text("---\n[]\n", encoding="utf-8")

    text = _install_into(proj, home, dsh_home, monkeypatch)
    assert "[]" not in text
    assert text.lstrip().startswith(BEGIN)

    # A `[]` next to real entries is user content and survives both directions.
    dsh_home2 = home / "other-dsh"
    dsh_home2.mkdir()
    with_entries = "- insert:\n    - id: keep\n      name: '@local/keep'\n\n[]\n"
    _patch_file(dsh_home2).write_text(with_entries, encoding="utf-8")
    text2 = _install_into(proj, home, dsh_home2, monkeypatch)
    assert with_entries.strip() in text2
    _run(proj, ["uninstall"], home, monkeypatch, dsh_home2)
    assert _patch_file(dsh_home2).read_text(encoding="utf-8") == with_entries


def test_install_recovers_from_a_block_missing_its_end_marker(tmp_path, monkeypatch):
    """A truncated block (crossed with uninstall) cannot delete trailing user text.

    The written block always carries its close marker last, so a begin marker
    with no close can only mean the file was cut short inside graphify's own
    tail. Everything after the begin marker is graphify's; user lines before it
    survive, and the file is rewritten whole.
    """
    import graphify.install as install_mod

    home = tmp_path / "home"
    proj = tmp_path / "proj"
    dsh_home = home / ".dsh"
    home.mkdir()
    proj.mkdir()
    dsh_home.mkdir(parents=True)
    assert install_mod._dsh_strip_mcp_block(BEGIN + "\n- insert:\n") is not None
    assert install_mod._dsh_strip_mcp_block("- insert:\n") is None

    # install rewrites the truncated block instead of appending a second one
    truncated = "- insert:\n    - id: earlier\n      name: '@local/earlier'\n\n" + BEGIN + "\n- insert:\n"
    _patch_file(dsh_home).write_text(truncated, encoding="utf-8")
    text = _install_into(proj, home, dsh_home, monkeypatch)
    assert text.count(BEGIN) == 1
    assert text.count(END) == 1
    assert "- id: earlier" in text

    # uninstall on a truncated block removes the block and keeps the user lines
    _patch_file(dsh_home).write_text(truncated, encoding="utf-8")
    _run(proj, ["uninstall"], home, monkeypatch, dsh_home)
    assert _patch_file(dsh_home).read_text(encoding="utf-8").strip() == (
        "- insert:\n    - id: earlier\n      name: '@local/earlier'"
    )
