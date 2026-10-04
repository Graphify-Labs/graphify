"""Exercise persisted Codex hook commands at their actual native shell boundary.

REQ-CORE-001-AC01/AC05 protect literal launcher identity, command failure and
existing-hook ownership. Cmd receives Codex's raw outer quotation; Windows
PowerShell receives one command argument. POSIX keeps its existing sh contract.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import graphify.install as installmod
import graphify.codex_hook_command as commandmod


CONSUMERS = ("cmd", "powershell") if os.name == "nt" else ("sh",)


def _dispatch(command, consumer, project, environment):
    """Match the versioned Codex runner's command-line argument transport."""
    if consumer == "cmd":
        # Codex's Windows runner uses raw_arg with this outer quotation.
        arguments = f'"{os.environ["COMSPEC"]}" /C "{command}"'
    elif consumer == "powershell":
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        arguments = [str(shell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command]
    else:
        arguments = ["/bin/sh", "-c", command]
    return subprocess.run(
        arguments, shell=False, cwd=project, input="{}", capture_output=True,
        text=True, timeout=30, env=environment,
    )


def _install_fixture(tmp_path, monkeypatch, directory):
    """Persist a real CLI launcher and a PATH decoy with observable identity."""
    tools = tmp_path / directory
    tools.mkdir()
    if os.name == "nt":
        launcher = tools / "graphify.exe"
        source = Path(sys.executable).parent / "graphify.exe"
        assert source.is_file(), "editable installation must include its CLI launcher"
        shutil.copyfile(source, launcher)
    else:
        launcher = tools / "graphify"
        launcher.write_text(
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m graphify \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    decoy_dir = tmp_path / "decoy-bin"
    decoy_dir.mkdir()
    decoy = decoy_dir / ("graphify.cmd" if os.name == "nt" else "graphify")
    decoy.write_text(
        "@echo PATH_DECOY> PATH_DECOY\n@exit /b 79\n" if os.name == "nt"
        else "#!/bin/sh\nprintf PATH_DECOY > PATH_DECOY\nexit 79\n", encoding="utf-8",
    )
    if os.name != "nt":
        decoy.chmod(0o755)
    environment = {
        **os.environ, "PATH": str(decoy_dir) + os.pathsep + os.environ.get("PATH", ""),
        "GRAPHIFY_NO_AUTO_REFRESH": "1", "GRAPHIFY_NO_TIPS": "1",
        "GRAPHIFY_REDIRECT": "WRONG_DIRECTORY",
    }
    monkeypatch.setattr(installmod.shutil, "which", lambda _name: str(launcher))
    project = tmp_path / "project"
    project.mkdir()
    installmod._install_codex_hook(project)
    settings = json.loads((project / ".codex/hooks.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    return launcher, project, environment, command


@pytest.mark.parametrize("consumer", CONSUMERS)
def test_req_core001_ac01_codex_hook_dispatches_spaced_native_launcher(tmp_path, monkeypatch, consumer):
    """The installed literal executable wins over PATH and an unquoted control."""
    launcher, project, environment, command = _install_fixture(
        tmp_path, monkeypatch, "installed tools & literal",
    )
    assert _dispatch("graphify hook-check", consumer, project, environment).returncode != 0
    sentinel = project / "PATH_DECOY"
    assert sentinel.read_text().strip() == "PATH_DECOY"
    sentinel.unlink()
    assert _dispatch(f"{launcher.as_posix()} hook-check", consumer, project, environment).returncode != 0

    completed = _dispatch(command, consumer, project, environment)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""
    assert not sentinel.exists()


@pytest.mark.parametrize("consumer", CONSUMERS)
@pytest.mark.parametrize("literal_kind", ("expansion", "brackets-unicode"))
def test_req_core001_ac05_literal_expansion_characters_retain_launcher_identity(tmp_path, monkeypatch, consumer, literal_kind):
    """Environment expansion, quote and substitution characters remain data."""
    directory = "literal %GRAPHIFY_REDIRECT% ^ ! $` (tools) '" if literal_kind == "expansion" else "literal [tools] Ω"
    if os.name != "nt" and literal_kind == "expansion":
        directory += " $(touch INJECTED)"
    _, project, environment, command = _install_fixture(tmp_path, monkeypatch, directory)

    completed = _dispatch(command, consumer, project, environment)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == completed.stderr == ""
    assert not (project / "PATH_DECOY").exists()
    assert not (project / "INJECTED").exists()


@pytest.mark.parametrize("consumer", CONSUMERS)
def test_req_core001_ac05_missing_launcher_fails_without_path_fallback(tmp_path, monkeypatch, consumer):
    """Losing the selected executable is terminal and never selects the decoy."""
    launcher, project, environment, command = _install_fixture(tmp_path, monkeypatch, "installed tools")
    launcher.unlink()

    completed = _dispatch(command, consumer, project, environment)

    assert completed.returncode != 0
    assert not (project / "PATH_DECOY").exists()
    if os.name == "nt":
        assert "selected executable could not be invoked" in completed.stderr
        assert str(tmp_path) not in completed.stderr


def test_req_core001_ac05_reinstall_and_uninstall_preserve_unrelated_hooks(tmp_path, monkeypatch):
    """Encoded transport retains visible ownership and the prior JSON backup."""
    _, project, _, _ = _install_fixture(tmp_path, monkeypatch, "installed tools")
    target = project / ".codex/hooks.json"
    unrelated = {"matcher": "Read", "hooks": [{"type": "command", "command": "other-tool check"}]}
    settings = json.loads(target.read_text(encoding="utf-8"))
    settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"] += " "
    settings["hooks"]["PreToolUse"].insert(0, unrelated)
    settings["anotherSetting"] = {"retained": True}
    original = json.dumps(settings, indent=2)
    target.write_text(original, encoding="utf-8")

    installmod._install_codex_hook(project)

    assert target.with_name("hooks.json.graphify-bak").read_text(encoding="utf-8") == original
    installed = target.read_bytes()
    installmod._install_codex_hook(project)
    assert target.read_bytes() == installed
    retained = json.loads(installed)
    assert retained["anotherSetting"] == {"retained": True}
    assert retained["hooks"]["PreToolUse"][0] == unrelated
    assert len(retained["hooks"]["PreToolUse"]) == 2
    installmod._uninstall_codex_hook(project)
    assert json.loads(target.read_bytes())["hooks"]["PreToolUse"] == [unrelated]


@pytest.mark.parametrize("system_root", ("", "C:/missing-windows", "C:/OS %EXPANSION%", "C:/OS;INJECTED", "C:/OS[ambiguous]"))
def test_req_core001_ac05_unsupported_shell_rejects_before_settings_access(tmp_path, monkeypatch, capsys, system_root):
    """A missing or ambiguous OS consumer leaves prior hook JSON untouched."""
    target = tmp_path / ".codex/hooks.json"
    target.parent.mkdir()
    original = b'{"hooks":{"PreToolUse":[]},"retained":true}'
    target.write_bytes(original)
    monkeypatch.setenv("SystemRoot", system_root)
    monkeypatch.setattr(installmod.shutil, "which", lambda _name: "C:/installed tools/graphify.exe")
    # Explicitly exercise native serialization on POSIX as a contract test; no
    # Windows subprocess execution is attributed to this emulated profile.
    monkeypatch.setattr(installmod, "codex_hook_command", lambda executable, **_kw: commandmod.codex_hook_command(executable, windows=True))
    def forbidden_read(_path):
        pytest.fail("rejected transport must not access settings")
    monkeypatch.setattr(installmod, "_read_settings_for_merge", forbidden_read)

    with pytest.raises(SystemExit) as rejected:
        installmod._install_codex_hook(tmp_path)

    assert rejected.value.code == 1
    assert target.read_bytes() == original
    assert not target.with_name("hooks.json.graphify-bak").exists()
    output = capsys.readouterr()
    assert output.out == ""
    assert "cannot install Codex hook" in output.err
    assert "retry" in output.err or "standard Windows installation" in output.err
    assert system_root not in output.err if system_root else True


@pytest.mark.parametrize("consumer", CONSUMERS)
def test_req_core001_ac05_selected_process_failure_preserves_nonzero_exit(tmp_path, monkeypatch, consumer):
    """The selected executable's real failure propagates through native transport."""
    launcher, project, environment, command = _install_fixture(tmp_path, monkeypatch, "installed tools")
    if os.name == "nt":
        # The OS's real where executable has a deterministic missing-pattern
        # failure. This preserves exit 1 through both native shell consumers.
        source = Path(os.environ["SystemRoot"]) / "System32/where.exe"
        shutil.copyfile(source, launcher)
        environment["PATH"] = str(tmp_path / "decoy-bin")
    else:
        launcher.write_text("#!/bin/sh\nexit 73\n", encoding="utf-8")

    completed = _dispatch(command, consumer, project, environment)

    assert completed.returncode == (1 if os.name == "nt" else 73)
    assert not (project / "PATH_DECOY").exists()


def _assert_rejected_settings_retained(tmp_path, monkeypatch, capsys):
    """Invoke the production installer with a prior file and rolling backup."""
    target = tmp_path / ".codex/hooks.json"
    target.parent.mkdir()
    original = b'{"hooks":{"PreToolUse":[]},"retained":true}'
    backup = b'{"earlier":"valid settings"}'
    target.write_bytes(original)
    backup_path = target.with_name("hooks.json.graphify-bak")
    backup_path.write_bytes(backup)
    def forbidden_read(_path):
        pytest.fail("rejected transport must not access settings")
    monkeypatch.setattr(installmod, "_read_settings_for_merge", forbidden_read)
    with pytest.raises(SystemExit) as rejected:
        installmod._install_codex_hook(tmp_path)
    assert rejected.value.code == 1
    assert target.read_bytes() == original
    assert backup_path.read_bytes() == backup
    output = capsys.readouterr()
    assert output.out == ""
    assert "cannot install Codex hook" in output.err
    return output.err


@pytest.mark.skipif(os.name != "nt", reason="real Windows OS shell inspection boundary")
def test_req_core001_ac05_shell_inspection_failure_retains_settings_and_backup(tmp_path, monkeypatch, capsys):
    """An actual stat failure seam rejects without leaking its private body."""
    monkeypatch.setattr(installmod.shutil, "which", lambda _name: "C:/installed tools/graphify.exe")
    def denied_stat(_path):
        raise PermissionError("PRIVATE_OS_PATH_SENTINEL")
    monkeypatch.setattr(commandmod.Path, "is_file", denied_stat)

    error = _assert_rejected_settings_retained(tmp_path, monkeypatch, capsys)

    assert "cannot inspect Windows PowerShell" in error
    assert "retry" in error
    assert "PRIVATE_OS_PATH_SENTINEL" not in error


@pytest.mark.parametrize("cmd_shell", ("C:/Windows/System32/cmd.exe", "C:/" + "w" * 235 + "/cmd.exe"))
def test_req_core001_ac05_command_length_boundary_retains_literal_identity(tmp_path, monkeypatch, capsys, cmd_shell):
    """The maximal admitted payload succeeds and its next growth rejects safely."""
    import base64

    monkeypatch.setattr(commandmod, "_windows_powershell_exe", lambda: "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    monkeypatch.setenv("COMSPEC", cmd_shell)
    selected = "C:/" + "a" * 100 + "/graphify.exe"
    # Grow an independently selected literal until its encoded transport crosses
    # the documented 8000-character admission limit (base64 grows in steps).
    last_command = ""
    rejected = False
    for _ in range(4000):
        try:
            command = commandmod.codex_hook_command(selected, windows=True)
        except commandmod.HookCommandError:
            rejected = True
            break
        last_command = command
        last_selected = selected
        # Keep every synthetic directory component within Windows's filename
        # bound; this is serialization evidence, not a filesystem launch proof.
        growth = "a" if len(selected.split("/")[-2]) < 250 else "/a"
        selected = selected.replace("/graphify.exe", growth + "/graphify.exe")
    assert rejected, "oversized native commands must be rejected"
    expected_limit = min(8000, 8191 - len(cmd_shell) - 8)
    assert expected_limit - 3 <= len(last_command) <= expected_limit
    script = base64.b64decode(last_command.split()[-1]).decode("utf-16-le")
    assert f"& '{last_selected}' hook-check;" in script
    monkeypatch.setattr(installmod.shutil, "which", lambda _name: selected)
    monkeypatch.setattr(installmod, "codex_hook_command", lambda executable, **_kw: commandmod.codex_hook_command(executable, windows=True))

    error = _assert_rejected_settings_retained(tmp_path, monkeypatch, capsys)

    assert "command is too long" in error
    assert "shorter" in error
    assert selected not in error
