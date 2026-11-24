"""`graphify dsh install`: skill + hooks.json + cordis overlay, in lockstep.

DeepSeek Harness reads no hook file on its own - the guard only fires once the
`@deepseek-ai/dsh-hooks-claude-code` bridge is mounted on a Claude-shaped
hooks.json - so an install that writes the skill alone is inert. These tests pin
the three-artifact install, the DSH-specific hook shape (lowercase matchers,
seconds timeout, advisory unless `--strict`), and that uninstall/merge never
touch a user's own hook entries or YAML.
"""
import json
import sys
from pathlib import Path

import pytest

from graphify.install import (
    _DSH_BRIDGE_PACKAGE,
    _DSH_BRIDGE_VERSION,
    dispatch_install_cli,
    install,
)

BRIDGE = f"{_DSH_BRIDGE_PACKAGE}@{_DSH_BRIDGE_VERSION}"


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A project root plus an isolated $DSH_HOME, cwd switched into the project."""
    dsh_home = tmp_path / "dsh-home"
    monkeypatch.setenv("DSH_HOME", str(dsh_home))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project, dsh_home


def _hooks(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]


def _commands(groups: list) -> "list[str]":
    return [hook["command"] for group in groups for hook in group["hooks"]]


def _graphify_groups(groups: list) -> list:
    return [g for g in groups if any("hook-guard" in h.get("command", "") for h in g["hooks"])]


def test_project_install_writes_skill_hooks_and_overlay(scratch, capsys):
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    out = capsys.readouterr().out

    # 1. The skill and its references sidecar land where dsh discovers them.
    assert (project / ".dsh" / "skills" / "graphify" / "SKILL.md").is_file()
    assert (project / ".dsh" / "skills" / "graphify" / "references" / "query.md").is_file()

    # 2. The hook config is Claude-shaped, with dsh's own vocabulary.
    hooks = _hooks(project / ".dsh" / "hooks.json")
    pre_tool = _graphify_groups(hooks["PreToolUse"])
    assert [g["matcher"] for g in pre_tool] == ["bash|grep", "read|glob"]
    assert any("hook-guard search" in c for c in _commands(pre_tool))
    assert any("hook-guard read" in c for c in _commands(pre_tool))
    for group in pre_tool:
        assert group["hooks"][0]["timeout"] == 10  # seconds, not ms
    assert [g["matcher"] for g in hooks["SessionStart"]] == ["startup|resume|clear|compact"]
    assert any("hook-guard session" in c for c in _commands(hooks["SessionStart"]))

    # A committed config names the bare command, never an absolute path.
    for group in pre_tool:
        assert group["hooks"][0]["command"].startswith("graphify hook-guard ")

    # 3. The overlay mounts the bridge on that config, relative to the repo.
    overlay = (project / ".dsh" / "graphify.cordis.yml").read_text(encoding="utf-8")
    assert overlay == (
        "- insert:\n"
        "  - id: graphify-hooks\n"
        f"    name: '{_DSH_BRIDGE_PACKAGE}'\n"
        "    config:\n"
        '      configPath: "./.dsh/hooks.json"\n'
        "      projectDir: .\n"
    )
    assert f"dsh --patch {(project / '.dsh' / 'graphify.cordis.yml').as_posix()}" in out
    assert BRIDGE in out


def test_plain_install_is_advisory(scratch, capsys):
    """A default install writes no blocking flag - the shape a Claude Code one has."""
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    out = capsys.readouterr().out
    commands = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert all("--strict" not in command for command in commands)
    assert all("--deny-mode" not in command for command in commands)
    assert "--strict" in out  # "no enforcement" is a visible choice, not a surprise


def test_strict_install_blocks_once_and_records_no_mode_flag(scratch, monkeypatch):
    project, _ = scratch
    monkeypatch.setattr(sys, "argv", ["graphify", "dsh", "install", "--project", "--strict"])
    dispatch_install_cli("dsh")
    guarded = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert all(command.endswith("--strict") for command in guarded)
    # `once` is recorded by omission, exactly as a strict Claude Code install does.
    assert all("--deny-mode" not in command for command in guarded)


def test_deny_mode_flag_selects_once(scratch, monkeypatch):
    project, _ = scratch
    monkeypatch.setattr(
        sys, "argv", ["graphify", "dsh", "install", "--project", "--deny-mode", "once"]
    )
    dispatch_install_cli("dsh")
    commands = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert all("--deny-mode once" in command for command in commands)


def test_deny_mode_until_query_is_written_verbatim(scratch, monkeypatch):
    """The repeat mode stays selectable; it is recorded exactly as chosen."""
    project, _ = scratch
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "dsh", "install", "--project", "--strict", "--deny-mode", "until-query"],
    )
    dispatch_install_cli("dsh")
    commands = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert all(command.endswith("--strict --deny-mode until-query") for command in commands)


def test_plain_user_scope_install_carries_no_policy_flags(scratch):
    _, dsh_home = scratch
    install("dsh", project=False)
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert all("--strict" not in command for command in commands)
    assert all("--deny-mode" not in command for command in commands)


def test_unknown_deny_mode_is_refused(scratch, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["graphify", "dsh", "install", "--project", "--deny-mode", "forever"]
    )
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("dsh")
    assert error.value.code == 1


def test_reinstall_keeps_user_hooks_and_is_byte_stable(scratch):
    project, _ = scratch
    hooks_path = project / ".dsh" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    user_group = {"matcher": "mcp__*", "hooks": [{"type": "command", "command": "/bin/true"}]}
    hooks_path.write_text(
        json.dumps(
            {"model": "deepseek-v4", "hooks": {"PreToolUse": [user_group], "PostToolUse": []}},
            indent=2,
        ),
        encoding="utf-8",
    )

    install("dsh", project=True, project_dir=project)
    once = hooks_path.read_bytes()
    settings = json.loads(once)
    assert settings["model"] == "deepseek-v4"           # untouched key survives
    assert settings["hooks"]["PostToolUse"] == []        # unrelated event survives
    assert user_group in settings["hooks"]["PreToolUse"]  # user entry survives
    assert len(_graphify_groups(settings["hooks"]["PreToolUse"])) == 2

    # The .graphify-bak from the first (differing) write is not refreshed by an
    # idempotent re-install: no backup churn, no mtime churn.
    backup = hooks_path.with_name("hooks.json.graphify-bak")
    first_backup = backup.read_bytes()
    install("dsh", project=True, project_dir=project)
    assert hooks_path.read_bytes() == once
    assert backup.read_bytes() == first_backup


def test_uninstall_removes_graphify_entries_only(scratch, capsys, monkeypatch):
    project, _ = scratch
    hooks_path = project / ".dsh" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    user_group = {"matcher": "mcp__*", "hooks": [{"type": "command", "command": "/bin/true"}]}
    hooks_path.write_text(
        json.dumps({"hooks": {"PreToolUse": [user_group], "SessionStart": []}}, indent=2),
        encoding="utf-8",
    )
    install("dsh", project=True, project_dir=project)
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["graphify", "dsh", "uninstall", "--project"])
    dispatch_install_cli("dsh")

    hooks = _hooks(hooks_path)
    assert hooks["PreToolUse"] == [user_group]
    assert hooks["SessionStart"] == []
    assert not (project / ".dsh" / "skills" / "graphify").exists()
    assert not (project / ".dsh" / "graphify.cordis.yml").exists()


def test_user_scope_writes_into_dsh_home(scratch):
    _, dsh_home = scratch
    install("dsh", project=False)

    assert (dsh_home / "skills" / "graphify" / "SKILL.md").is_file()
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert all(command.endswith(("hook-guard read", "hook-guard search")) for command in commands)

    patch = (dsh_home / "cordis.patch.yml").read_text(encoding="utf-8")
    assert patch.startswith("# >>> graphify\n")
    assert patch.rstrip("\n").endswith("# <<< graphify")
    assert f"configPath: \"{(dsh_home / 'hooks.json').as_posix()}\"" in patch
    assert "projectDir" not in patch  # home layer serves whichever repo is open


def test_user_scope_strict_install_blocks(scratch):
    """`--strict` works at user scope too, unlike Claude Code's project-only flag."""
    _, dsh_home = scratch
    install("dsh", project=False, strict=True)
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert all(command.endswith("--strict") for command in commands)


def test_user_scope_uninstall_preserves_the_rest_of_the_patch_layer(scratch):
    _, dsh_home = scratch
    dsh_home.mkdir(parents=True)
    patch_path = dsh_home / "cordis.patch.yml"
    before = "# my own layer\n- insert:\n  - id: my-plugin\n    name: 'x'\n"
    patch_path.write_text(before, encoding="utf-8")

    install("dsh", project=False)
    fenced = patch_path.read_text(encoding="utf-8")
    assert fenced.startswith(before)
    assert "graphify-hooks" in fenced

    from graphify.install import _dsh_uninstall

    _dsh_uninstall(project=False)
    assert patch_path.read_text(encoding="utf-8") == before
    assert not (dsh_home / "hooks.json").exists() or "hook-guard" not in (
        dsh_home / "hooks.json"
    ).read_text(encoding="utf-8")


def test_malformed_fence_is_left_untouched(scratch, capsys):
    _, dsh_home = scratch
    dsh_home.mkdir(parents=True)
    patch_path = dsh_home / "cordis.patch.yml"
    mangled = "# mine\n# >>> graphify\n- insert: []\n"
    patch_path.write_text(mangled, encoding="utf-8")

    install("dsh", project=False)
    assert patch_path.read_text(encoding="utf-8") == mangled
    out = capsys.readouterr().out
    assert "incomplete graphify fence" in out
    assert "graphify-hooks" in out  # the block is printed to paste in by hand


def test_pinned_bridge_command_when_no_profile_resolves_it(scratch, capsys):
    _, dsh_home = scratch
    install("dsh", project=True, project_dir=scratch[0])
    out = capsys.readouterr().out
    assert f"dsh plugin --profile <name> add {BRIDGE}" in out
    assert "never" not in out.split("add ")[1].split("\n")[0] or "latest" not in out

    # A profile that already declares the bridge is reported as resolved instead.
    profile = dsh_home / "profiles" / "web"
    profile.mkdir(parents=True)
    (profile / "package.json").write_text(
        json.dumps({"dependencies": {_DSH_BRIDGE_PACKAGE: _DSH_BRIDGE_VERSION}}),
        encoding="utf-8",
    )
    install("dsh", project=True, project_dir=scratch[0])
    resolved = capsys.readouterr().out
    assert "dsh profile(s): web" in resolved
    assert "dsh plugin --profile" not in resolved


def test_install_without_platform_reaches_dsh(scratch):
    """`graphify install --platform dsh` must write the same three artifacts."""
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    assert (project / ".dsh" / "hooks.json").is_file()
    assert (project / ".dsh" / "graphify.cordis.yml").is_file()
    assert (project / ".dsh" / "skills" / "graphify" / "SKILL.md").is_file()
