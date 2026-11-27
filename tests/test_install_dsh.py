"""`graphify dsh install`: skill + hooks.json + cordis overlay, in lockstep.

DeepSeek Harness reads no hook file on its own - the guard only fires once the
`@deepseek-ai/dsh-hooks-claude-code` bridge is mounted on a Claude-shaped
hooks.json - so an install that writes the skill alone is inert. These tests pin
the three-artifact install, the DSH-specific hook shape (lowercase matchers,
seconds timeout, advisory unless `--strict`), that uninstall/merge never touch a
user's own hook entries or YAML, that the install fails loudly (exit 2) when no
profile can actually mount the bridge, and that `graphify dsh doctor` repairs the
bridge and the wiring, or reports read-only under `--check`.
"""
import json
import os
import sys
from pathlib import Path

import pytest

from graphify.install import (
    _DSH_BRIDGE_PACKAGE,
    _DSH_BRIDGE_VERSION,
    _dsh_doctor,
    dispatch_install_cli,
    install,
)

BRIDGE = f"{_DSH_BRIDGE_PACKAGE}@{_DSH_BRIDGE_VERSION}"


def _add_bridge(home: Path, profile: str = "web", version: str = _DSH_BRIDGE_VERSION) -> None:
    """Materialize a dsh profile with the bridge declared AND installed on disk."""
    base = home / "profiles" / profile
    package = base / "node_modules" / "@deepseek-ai" / "dsh-hooks-claude-code"
    package.mkdir(parents=True, exist_ok=True)
    (base / "package.json").write_text(
        json.dumps({"dependencies": {_DSH_BRIDGE_PACKAGE: version}}), encoding="utf-8"
    )
    (package / "package.json").write_text(
        json.dumps({"name": _DSH_BRIDGE_PACKAGE, "version": version}), encoding="utf-8"
    )


def _add_profile(home: Path, profile: str) -> None:
    """A profile that exists but does not declare the bridge."""
    path = home / "profiles" / profile
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text("{}", encoding="utf-8")


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A project root plus an isolated $DSH_HOME that can mount the bridge."""
    dsh_home = tmp_path / "dsh-home"
    monkeypatch.setenv("DSH_HOME", str(dsh_home))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    _add_bridge(dsh_home)
    return project, dsh_home


@pytest.fixture
def bare_scratch(tmp_path, monkeypatch):
    """Same, but with no bridge anywhere: the state a first-time install starts in."""
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
    assert "--strict" in out  # "no enforcement" is a visible choice, not a surprise


def test_strict_install_blocks_once(scratch, monkeypatch):
    """`--strict` writes exactly the flag a strict Claude Code install writes."""
    project, _ = scratch
    monkeypatch.setattr(sys, "argv", ["graphify", "dsh", "install", "--project", "--strict"])
    dispatch_install_cli("dsh")
    guarded = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert all(command.endswith("--strict") for command in guarded)


def test_plain_user_scope_install_carries_no_policy_flags(scratch):
    _, dsh_home = scratch
    install("dsh", project=False)
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert all("--strict" not in command for command in commands)


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
    dsh_home.mkdir(parents=True, exist_ok=True)
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
    dsh_home.mkdir(parents=True, exist_ok=True)
    patch_path = dsh_home / "cordis.patch.yml"
    mangled = "# mine\n# >>> graphify\n- insert: []\n"
    patch_path.write_text(mangled, encoding="utf-8")

    install("dsh", project=False)
    assert patch_path.read_text(encoding="utf-8") == mangled
    out = capsys.readouterr().out
    assert "incomplete graphify fence" in out
    assert "graphify-hooks" in out  # the block is printed to paste in by hand


# --- clean-machine installs and round trips -------------------------------

def test_install_without_platform_reaches_dsh(scratch):
    """`graphify install --platform dsh` must write the same three artifacts."""
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    assert (project / ".dsh" / "hooks.json").is_file()
    assert (project / ".dsh" / "graphify.cordis.yml").is_file()
    assert (project / ".dsh" / "skills" / "graphify" / "SKILL.md").is_file()


def test_dsh_home_defaults_to_home_when_the_env_var_is_unset(tmp_path, monkeypatch, capsys):
    """$DSH_HOME relocates dsh's home; unset, the install must use ~/.dsh.

    Every other test pins DSH_HOME, so the default path - the one every real
    user gets - was never exercised. HOME is the suite's sandbox (conftest
    patches Path.home), so ask for it rather than setting a second one.
    """
    monkeypatch.delenv("DSH_HOME", raising=False)
    home = Path.home()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    _add_bridge(home / ".dsh")

    install("dsh", project=False)
    assert (home / ".dsh" / "hooks.json").is_file()
    assert (home / ".dsh" / "skills" / "graphify" / "SKILL.md").is_file()
    patch = (home / ".dsh" / "cordis.patch.yml").read_text(encoding="utf-8")
    assert f'configPath: "{(home / ".dsh" / "hooks.json").as_posix()}"' in patch


def test_install_uninstall_install_restores_one_fence_and_two_groups(scratch, capsys):
    """A second install after an uninstall must not stack a second fence."""
    _, dsh_home = scratch
    install("dsh", project=False)
    first_patch = (dsh_home / "cordis.patch.yml").read_text(encoding="utf-8")

    from graphify.install import _dsh_uninstall

    _dsh_uninstall(project=False)
    install("dsh", project=False)
    second_patch = (dsh_home / "cordis.patch.yml").read_text(encoding="utf-8")

    assert second_patch == first_patch
    assert second_patch.count("# >>> graphify") == 1
    assert second_patch.count("# <<< graphify") == 1
    assert len(_graphify_groups(_hooks(dsh_home / "hooks.json")["PreToolUse"])) == 2
    assert len(_hooks(dsh_home / "hooks.json")["SessionStart"]) == 1


def test_uninstall_on_a_machine_that_never_installed_writes_nothing(bare_scratch, capsys):
    """The all-platforms `graphify uninstall` sweep must stay silent and inert."""
    from graphify.install import _dsh_uninstall

    _, dsh_home = bare_scratch
    _dsh_uninstall(project=False, report_missing=False)
    assert not dsh_home.exists() or not any(dsh_home.iterdir())
    assert capsys.readouterr().out == ""


def test_install_refuses_to_clobber_a_hooks_json_it_cannot_merge(scratch, capsys):
    """`hooks` that is not an object means the file is not Claude-shaped: stop."""
    project, _ = scratch
    hooks_path = project / ".dsh" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    original = json.dumps({"hooks": ["not", "a", "dict"]}, indent=2)
    hooks_path.write_text(original, encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        install("dsh", project=True, project_dir=project)
    assert error.value.code == 1
    assert hooks_path.read_text(encoding="utf-8") == original


def test_install_platform_dsh_strict_does_not_print_the_claude_only_note(scratch, monkeypatch, capsys):
    """`graphify install --platform dsh --strict` is documented as valid at either scope."""
    _, dsh_home = scratch
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "--platform", "dsh", "--strict"])
    dispatch_install_cli("install")
    captured = capsys.readouterr()
    assert "--strict applies to the project PreToolUse hook" not in captured.err
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert commands and all(command.endswith("--strict") for command in commands)


def test_a_user_scope_exe_path_with_spaces_is_quoted(scratch, monkeypatch):
    """The home patch is committed nowhere, so it names an absolute path; a space
    in that path word-splits the command unless it is quoted."""
    import graphify.install as install_mod

    _, dsh_home = scratch
    monkeypatch.setattr(
        install_mod, "_resolve_graphify_exe", lambda project=False: "/tmp/Application Support/graphify"
    )
    install("dsh", project=False)
    commands = _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    assert all(command.startswith('"/tmp/Application Support/graphify" hook-guard ') for command in commands)


def test_installing_the_second_scope_names_the_duplicate_mount(scratch, capsys):
    """Both scopes mount the same row id, and dsh composes them: say so.

    A `--patch` overlay is applied on top of the home layer, so a machine with
    both installs runs two bridge instances and therefore two guards per tool
    call. The scopes are alternatives; the install must not let that be silent.
    """
    project, _ = scratch
    install("dsh", project=False)
    capsys.readouterr()

    install("dsh", project=True, project_dir=project)
    err = capsys.readouterr().err
    assert "cordis.patch.yml" in err and "run twice" in err

    capsys.readouterr()
    install("dsh", project=False)  # the project overlay now sits in cwd
    err = capsys.readouterr().err
    assert "graphify.cordis.yml" in err and "run twice" in err


def test_the_install_names_a_stale_graphify_on_path(scratch, monkeypatch, capsys):
    """A hook wired to whatever PATH offers can run a graphify without dsh support.

    That copy answers `pass` to every guard call while this install reports
    success, so the guard is silently inert - the exact failure a dsh install
    exists to prevent. The install must say which binary it wired.
    """
    import graphify.install as install_mod

    _, dsh_home = scratch
    monkeypatch.setattr(install_mod, "_HOOK_EXE_WARNED", set())
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: "/opt/stale/bin/graphify")
    monkeypatch.setattr(install_mod, "_reported_exe_version", lambda exe: "0.0.1")

    install("dsh", project=False)

    err = capsys.readouterr().err
    assert "/opt/stale/bin/graphify" in err and "0.0.1" in err
    # ...and the hooks really do name that binary, so the warning describes them.
    assert all(
        "/opt/stale/bin/graphify" in command
        for command in _commands(_hooks(dsh_home / "hooks.json")["PreToolUse"])
    )


def _declare_bridge(home: Path, profile: str = "web", spec: str = _DSH_BRIDGE_VERSION) -> None:
    """A profile that declares the bridge but has no installed copy yet."""
    path = home / "profiles" / profile
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        json.dumps({"dependencies": {_DSH_BRIDGE_PACKAGE: spec}}), encoding="utf-8"
    )


def _fake_dsh(tmp_path: Path, monkeypatch) -> None:
    """Put a `dsh` on PATH that records its argv and 'installs' the bridge."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "dsh-args.log"
    monkeypatch.setenv("FAKE_DSH_LOG", str(log))
    exe = bin_dir / "dsh"
    exe.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" >> "$FAKE_DSH_LOG"\n'
        'profile="$3"\n'
        'dir="$DSH_HOME/profiles/$profile/node_modules/@deepseek-ai/dsh-hooks-claude-code"\n'
        'mkdir -p "$dir"\n'
        'printf \'{"version":"%s"}\' "${5##*@}" > "$dir/package.json"\n',
        encoding="utf-8",
    )
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_resolved_bridge_reports_the_installed_version(scratch, capsys):
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    out = capsys.readouterr().out
    assert f"dsh profile 'web' (installed {_DSH_BRIDGE_VERSION})" in out
    assert "dsh plugin --profile" not in out


def test_missing_bridge_exits_2_and_names_every_profile(bare_scratch, capsys):
    """A written overlay with no bridge is inert: report it as a failed install."""
    project, dsh_home = bare_scratch
    for name in ("web", "headless"):
        _add_profile(dsh_home, name)

    with pytest.raises(SystemExit) as error:
        install("dsh", project=True, project_dir=project)

    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "NOT ACTIVE" in captured.out
    assert "NOT active yet" in captured.err
    for name in ("web", "headless"):
        assert f"dsh plugin --profile {name} add {BRIDGE}" in captured.out


def test_no_profile_at_all_exits_2_with_the_creation_hint(bare_scratch, capsys):
    project, _ = bare_scratch
    with pytest.raises(SystemExit) as error:
        install("dsh", project=True, project_dir=project)
    assert error.value.code == 2
    out = capsys.readouterr().out
    assert "no dsh profile exists yet" in out
    assert f"dsh plugin --profile <name> add {BRIDGE}" in out


def test_stale_bridge_fails_the_install_and_names_the_fix(bare_scratch, capsys):
    """The published `latest` predates the event contract these hooks use."""
    project, dsh_home = bare_scratch
    _add_bridge(dsh_home, version="0.0.1-rc.5")

    with pytest.raises(SystemExit) as error:
        install("dsh", project=True, project_dir=project)

    assert error.value.code == 2
    out = capsys.readouterr().out
    assert "0.0.1-rc.5" in out and "older than the pinned" in out
    assert f"dsh plugin --profile web add {BRIDGE}" in out
    assert "bridge resolved" not in out


def test_declared_bridge_without_an_installed_copy_is_not_resolved(bare_scratch, capsys):
    project, dsh_home = bare_scratch
    _declare_bridge(dsh_home)

    with pytest.raises(SystemExit) as error:
        install("dsh", project=True, project_dir=project)

    assert error.value.code == 2
    out = capsys.readouterr().out
    assert "declared" in out and "no installed copy" in out
    assert "dsh plugin --profile web install" in out
    assert "bridge resolved" not in out


def test_newer_bridge_than_the_pin_is_accepted(bare_scratch, capsys):
    project, dsh_home = bare_scratch
    _add_bridge(dsh_home, version="0.2.4")
    install("dsh", project=True, project_dir=project)
    out = capsys.readouterr().out
    assert "dsh profile 'web' (installed 0.2.4)" in out


def test_doctor_installs_a_missing_bridge(bare_scratch, tmp_path, monkeypatch, capsys):
    """The repair doctor exists for: dsh cannot mount the overlay without it."""
    project, dsh_home = bare_scratch
    _declare_bridge(dsh_home)
    _fake_dsh(tmp_path, monkeypatch)

    assert _dsh_doctor(project) == 0

    log = (tmp_path / "dsh-args.log").read_text(encoding="utf-8").split()
    assert log == ["plugin", "--profile", "web", "add", BRIDGE]
    out = capsys.readouterr().out
    assert "repair 'web'" in out
    assert f"bridge 'web'" in out and "(ok)" in out
    assert "ACTIVE" in out


def test_doctor_upgrades_a_stale_bridge(bare_scratch, tmp_path, monkeypatch, capsys):
    project, dsh_home = bare_scratch
    _add_bridge(dsh_home, version="0.0.1-rc.5")
    _fake_dsh(tmp_path, monkeypatch)

    assert _dsh_doctor(project) == 0

    out = capsys.readouterr().out
    assert "0.0.1-rc.5 is older than the pinned" in out
    assert (dsh_home / "profiles" / "web" / "node_modules" / "@deepseek-ai"
            / "dsh-hooks-claude-code" / "package.json").is_file()
    assert _dsh_doctor(project, check=True) == 0


def test_doctor_repairs_every_profile(bare_scratch, tmp_path, monkeypatch, capsys):
    """dsh boots one profile per run and graphify cannot know which, so all get fixed."""
    project, dsh_home = bare_scratch
    _declare_bridge(dsh_home, "web")
    _declare_bridge(dsh_home, "headless")
    _fake_dsh(tmp_path, monkeypatch)

    assert _dsh_doctor(project) == 0

    log = (tmp_path / "dsh-args.log").read_text(encoding="utf-8").split()
    assert log.count("plugin") == 2                      # one add per profile
    assert log.count("web") == 1 and log.count("headless") == 1
    out = capsys.readouterr().out
    assert "bridge 'web'" in out and "bridge 'headless'" in out


def test_doctor_writes_missing_wiring(scratch, capsys):
    """A resolvable bridge with no overlay/hooks/skill is repaired, not just reported."""
    project, _ = scratch

    assert _dsh_doctor(project) == 0

    assert (project / ".dsh" / "hooks.json").is_file()
    assert (project / ".dsh" / "graphify.cordis.yml").is_file()
    assert (project / ".dsh" / "skills" / "graphify" / "SKILL.md").is_file()
    out = capsys.readouterr().out
    assert "repair wiring" in out
    assert "ACTIVE" in out


def test_doctor_keeps_the_strict_policy_when_repairing(scratch, monkeypatch):
    """The policy lives in hooks.json, so repairing the rest must not reset it."""
    project, _ = scratch
    install("dsh", project=True, strict=True)
    (project / ".dsh" / "graphify.cordis.yml").unlink()

    assert _dsh_doctor(project) == 0
    assert (project / ".dsh" / "graphify.cordis.yml").is_file()
    commands = _commands(_hooks(project / ".dsh" / "hooks.json")["PreToolUse"])
    assert commands and all(command.endswith("--strict") for command in commands)


def test_doctor_without_dsh_cannot_fix_and_says_so(bare_scratch, tmp_path, monkeypatch, capsys):
    project, dsh_home = bare_scratch
    _declare_bridge(dsh_home)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))

    assert _dsh_doctor(project) == 1

    out = capsys.readouterr().out
    assert "cannot repair" in out and "not on PATH" in out
    assert f"dsh plugin --profile web add {BRIDGE}" in out
    assert "NOT ACTIVE" in out


def test_doctor_reports_an_active_install(scratch, capsys):
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    capsys.readouterr()

    assert _dsh_doctor(project) == 0
    out = capsys.readouterr().out
    assert "ACTIVE" in out and _DSH_BRIDGE_VERSION in out
    assert "graphify-hooks" in out


def test_doctor_check_is_read_only(bare_scratch, capsys):
    project, dsh_home = bare_scratch

    assert _dsh_doctor(project, check=True) == 1
    out = capsys.readouterr().out
    assert "(read-only)" in out
    assert "NOT ACTIVE" in out
    assert not dsh_home.exists()          # no profile, session, or cache created
    assert not (project / ".dsh").exists()  # no overlay written


def test_doctor_flags_a_double_mount_without_removing_either(scratch, capsys):
    """Which scope to keep is the user's call, so the repair must not pick one."""
    project, dsh_home = scratch
    install("dsh", project=True, project_dir=project)
    install("dsh", project=False)
    capsys.readouterr()

    assert _dsh_doctor(project) == 1
    assert "twice" in capsys.readouterr().out
    assert (project / ".dsh" / "graphify.cordis.yml").is_file()
    assert "graphify-hooks" in (dsh_home / "cordis.patch.yml").read_text(encoding="utf-8")


def test_doctor_names_a_stale_bridge(bare_scratch, capsys):
    project, dsh_home = bare_scratch
    _add_bridge(dsh_home, version="0.0.1-rc.5")
    with pytest.raises(SystemExit):
        install("dsh", project=True, project_dir=project)
    capsys.readouterr()

    assert _dsh_doctor(project, check=True) == 1
    out = capsys.readouterr().out
    assert "0.0.1-rc.5 (stale" in out


def test_doctor_subcommand_exits_with_its_verdict(scratch, monkeypatch, capsys):
    project, _ = scratch
    install("dsh", project=True, project_dir=project)
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["graphify", "dsh", "doctor"])
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("dsh")
    assert error.value.code == 0


def test_doctor_subcommand_check_is_read_only(scratch, monkeypatch, capsys):
    project, _ = scratch
    (project / ".dsh").mkdir(exist_ok=True)  # no wiring yet

    monkeypatch.setattr(sys, "argv", ["graphify", "dsh", "doctor", "--check"])
    with pytest.raises(SystemExit) as error:
        dispatch_install_cli("dsh")
    assert error.value.code == 1
    assert "(read-only)" in capsys.readouterr().out
    assert not (project / ".dsh" / "hooks.json").exists()
