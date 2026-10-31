"""Characterize exact file identity at the shell/native fixture boundary."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.shell_portability import resolve_shell_path, select_shell_executable


def test_native_path_keeps_full_identity_with_spaces(tmp_path):
    """A full native path identifies the created file, including spaced parents."""
    target = tmp_path / "tool with spaces" / "python"
    target.parent.mkdir()
    target.touch()
    assert resolve_shell_path(str(target)) == target.resolve()


def test_same_named_sibling_is_not_the_requested_file(tmp_path):
    """Canonicalization must preserve parent identity rather than just basename."""
    requested = tmp_path / "requested" / "python"
    rejected = tmp_path / "rejected" / "python"
    for target in (requested, rejected):
        target.parent.mkdir()
        target.touch()
    assert resolve_shell_path(str(rejected)) != requested.resolve()


def test_relative_identity_is_rejected(tmp_path, monkeypatch):
    """An existing relative file cannot accidentally bind to the test runner cwd."""
    (tmp_path / "python").touch()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError, match="relative file identity"):
        resolve_shell_path("python")


def test_missing_absolute_identity_is_rejected(tmp_path):
    """A nonexistent interpreter candidate cannot satisfy a path-only comparison."""
    with pytest.raises(FileNotFoundError):
        resolve_shell_path(str(tmp_path / "missing-python"))


@pytest.mark.parametrize("shell", ["bash", "sh"])
def test_req_core004_ac03_missing_shell_selection_is_rejected(shell, tmp_path, monkeypatch):
    """An empty or unavailable configured PATH fails before any process launch."""
    for configured in ("", str(tmp_path)):
        monkeypatch.setenv("PATH", configured)
        with pytest.raises(AssertionError, match="unavailable in configured PATH"):
            select_shell_executable(shell)


@pytest.mark.parametrize("selection", ["relative", "directory", "missing"])
def test_req_core004_ac03_invalid_shell_identity_is_rejected(selection, tmp_path, monkeypatch):
    """Lookup transport cannot admit relative, directory, or nonexistent identities."""
    target = tmp_path / "shell"
    target.mkdir() if selection == "directory" else None
    supplied = "shell" if selection == "relative" else str(target)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(shutil, "which", lambda candidate: supplied)
    with pytest.raises(AssertionError, match="absolute executable file"):
        select_shell_executable("bash")


def test_req_core004_ac03_unadmitted_shell_name_is_rejected():
    """Shell fixture admission cannot become a generic executable launcher."""
    with pytest.raises(AssertionError, match="only Bash/sh"):
        select_shell_executable("cmd")


@pytest.mark.parametrize("shell", ["bash", "sh"])
def test_req_core004_ac02_admitted_shell_runs_real_posix_command(shell):
    """The selected absolute Bash/sh executes POSIX syntax without a GNU-only probe."""
    if shutil.which(shell) is None:
        pytest.skip(f"{shell} is unavailable for executable identity proof")
    selected = select_shell_executable(shell)
    assert Path(selected).is_absolute() and Path(selected).is_file()
    result = subprocess.run([selected, "-c", "printf %s admitted-shell"],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "admitted-shell"


@pytest.mark.skipif(os.name != "nt", reason="native Windows executable search boundary")
@pytest.mark.parametrize("shell", ["bash", "sh"])
def test_req_core004_ac02_native_cwd_shadow_requires_explicit_path_admission(
    shell, tmp_path, monkeypatch,
):
    """A real native CWD executable shadows bare launch but never an admitted PATH."""
    selected = select_shell_executable(shell)
    # The harmless system lookup binary is a real competing native executable;
    # its stdout proves which process ran without launching WSL or corpus code.
    shadow = tmp_path / f"{shell}.exe"
    shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32" / "where.exe", shadow)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(Path(selected).parent))
    bare = subprocess.run([shell, shadow.name], capture_output=True, text=True, timeout=15)
    assert bare.returncode == 0 and str(shadow) in bare.stdout
    assert select_shell_executable(shell) == selected
    actual = subprocess.run([select_shell_executable(shell), "-c", "printf %s admitted-shell"],
                            capture_output=True, text=True, timeout=15)
    assert actual.returncode == 0 and actual.stdout == "admitted-shell", actual.stderr
    # CWD is eligible only when it is itself an explicit configured PATH entry.
    for entry in (".", ""):
        monkeypatch.setenv("PATH", entry + os.pathsep + str(Path(selected).parent))
        assert select_shell_executable(shell) == str(shadow.resolve())


@pytest.mark.skipif(os.name != "nt", reason="native Windows executable search boundary")
@pytest.mark.parametrize("consumer", ["hook_bash", "hook_sh", "skillgen_bash"])
def test_req_core004_ac02_real_consumers_resist_native_cwd_shadow(
    consumer, tmp_path, monkeypatch,
):
    """Actual hook/skill launchers use the admitted shell despite a CWD native decoy."""
    from tests.test_hooks import _broken_uv_machine, _detect_run, _shell_verdict, _tool_venv
    from tests.test_skillgen_input_path_injection import _run_step1

    shell = "sh" if consumer == "hook_sh" else "bash"
    selected = select_shell_executable(shell)
    shadow = tmp_path / f"{shell}.exe"
    shutil.copyfile(Path(os.environ["SystemRoot"]) / "System32" / "where.exe", shadow)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", str(Path(selected).parent))
    if consumer == "hook_bash":
        assert _shell_verdict("*", "literal-payload", tmp_path) == "REJECTED"
    elif consumer == "hook_sh":
        home, stubs = _broken_uv_machine(tmp_path)
        mine = _tool_venv(home, "graphifyy", "bin/python", ok=True)
        result = _detect_run(tmp_path, home, stubs)
        assert result.returncode == 0 and result.stdout.startswith("RESOLVED="), result.stderr
        assert resolve_shell_path(result.stdout.removeprefix("RESOLVED=").strip()) == mine.resolve()
    else:
        result = _run_step1("printf %s admitted-shell\n# INPUT_PATH\n", "literal", tmp_path)
        assert result.returncode == 0 and result.stdout == "admitted-shell", result.stderr


@pytest.mark.skipif(os.name != "nt" or shutil.which("sh") is None,
                    reason="native Windows and an MSYS shell required")
def test_msys_mount_mapping_preserves_full_sibling_identity(tmp_path):
    """Real cygpath maps /tmp and spaced parents while keeping decoys distinct."""
    executable = select_shell_executable("sh")
    system = subprocess.check_output([executable, "-c", "uname -s"], text=True).strip()
    if not system.startswith(("MSYS_", "MINGW", "CYGWIN_")):
        pytest.skip("the available Windows shell uses a different path namespace")
    mapper = Path(executable).with_name("cygpath.exe")
    paths = []
    for directory in ("requested with spaces", "rejected with spaces"):
        target = tmp_path / directory / "python"
        target.parent.mkdir()
        target.touch()
        reported = subprocess.check_output(
            [str(mapper), "-u", "--", str(target)], text=True,
        ).strip()
        assert reported.startswith("/"), reported
        paths.append((target, reported))
    requested, rejected = paths
    assert resolve_shell_path(requested[1]) == requested[0].resolve()
    assert resolve_shell_path(rejected[1]) == rejected[0].resolve()
    assert resolve_shell_path(rejected[1]) != requested[0].resolve()
