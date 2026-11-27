"""#3144: the stale-skill warning must be actionable, and local SKILL.md
edits must not vanish without a trace.

A plain `graphify install` refreshes only the detected platform, so a stale
`.graphify_version` at ANOTHER platform's destination made the warning
permanent: it named no path, its advice ("run graphify install") did not
touch that copy, and only editing the marker by hand cleared it. And a
reinstall replaced a user-edited SKILL.md wholesale — no diff, no prompt,
no backup — while printing a line that read like a successful no-op.
"""
from __future__ import annotations

import subprocess
import sys

import pytest

import graphify.__main__ as mainmod
from graphify import install as install_mod
from graphify.install import __version__
from graphify.install import _copy_skill_file, _platform_skill_destination


# ---------------------------------------------------------------------------
# The warning
# ---------------------------------------------------------------------------

def _stale(tmp_path):
    d = tmp_path / "skills" / "graphify"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: graphify\n---\nbody\n", encoding="utf-8")
    (d / ".graphify_version").write_text("0.8.36", encoding="utf-8")
    return d / "SKILL.md"


def test_the_warning_names_the_stale_destination_and_the_exact_command(tmp_path, capsys):
    mainmod._check_skill_version(_stale(tmp_path), platform_names=["antigravity"])
    err = capsys.readouterr().err
    assert "0.8.36" in err and __version__ in err
    assert str(tmp_path / "skills" / "graphify") in err, "the stale path must be named"
    assert "graphify install --platform antigravity" in err
    assert "only the detected platform" in err


def test_without_a_platform_name_the_generic_command_is_kept(tmp_path, capsys):
    mainmod._check_skill_version(_stale(tmp_path))
    err = capsys.readouterr().err
    assert "graphify install" in err


def test_a_current_skill_stays_silent(tmp_path, capsys):
    skill = _stale(tmp_path)
    (skill.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    mainmod._check_skill_version(skill, platform_names=["claude"])
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# The backup
# ---------------------------------------------------------------------------

@pytest.fixture
def sandbox_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    if sys.platform == "win32":
        monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOME", str(home))
    return home


def test_a_locally_edited_skill_is_backed_up_and_announced(sandbox_home, capsys):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    assert dst.exists()
    original = dst.read_text(encoding="utf-8")
    dst.write_text(original + "\nCUSTOM LOCAL EDIT\n", encoding="utf-8")
    capsys.readouterr()

    _copy_skill_file("claude")
    out = capsys.readouterr().out
    backup = dst.with_suffix(dst.suffix + ".bak")
    assert backup.exists(), "the previous copy must be kept"
    assert "CUSTOM LOCAL EDIT" in backup.read_text(encoding="utf-8")
    assert "CUSTOM LOCAL EDIT" not in dst.read_text(encoding="utf-8")
    assert "previous copy" in out and str(backup) in out


def test_an_unmodified_reinstall_writes_no_backup(sandbox_home, capsys):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    capsys.readouterr()
    _copy_skill_file("claude")
    out = capsys.readouterr().out
    assert not dst.with_suffix(dst.suffix + ".bak").exists()
    assert "previous copy" not in out


def test_the_version_stamp_is_written_beside_the_skill(sandbox_home):
    _copy_skill_file("claude")
    dst = _platform_skill_destination("claude")
    assert (dst.parent / ".graphify_version").read_text(encoding="utf-8") == __version__


# ---------------------------------------------------------------------------
# The hook executable: PATH's graphify is not necessarily this graphify
# ---------------------------------------------------------------------------

def _completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.fixture
def probe(monkeypatch):
    """A clean probe/warning cache: the helper memoises per path per process."""
    monkeypatch.setattr(install_mod, "_HOOK_EXE_VERSIONS", {})
    monkeypatch.setattr(install_mod, "_HOOK_EXE_WARNED", set())
    return install_mod


def test_the_probe_reads_the_version_out_of_the_banner(probe, monkeypatch):
    monkeypatch.setattr(
        probe.subprocess, "run", lambda *a, **k: _completed(stdout="graphify 0.9.111\n")
    )
    assert probe._reported_exe_version("/opt/bin/graphify") == "0.9.111"


def test_the_probe_falls_back_to_stderr_and_to_a_bare_number(probe, monkeypatch):
    monkeypatch.setattr(
        probe.subprocess, "run", lambda *a, **k: _completed(stderr="0.9.111\n")
    )
    assert probe._reported_exe_version("/opt/bin/graphify") == "0.9.111"


@pytest.mark.parametrize(
    "runner",
    [
        lambda *a, **k: _completed(returncode=1),
        lambda *a, **k: _completed(stdout="no version here"),
        lambda *a, **k: (_ for _ in ()).throw(OSError("cannot exec")),
        lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired(cmd="graphify", timeout=5)),
    ],
)
def test_an_unaskable_exe_is_silent(probe, monkeypatch, capsys, runner):
    monkeypatch.setattr(probe.subprocess, "run", runner)
    probe._warn_if_hook_exe_is_stale("/opt/bin/graphify")
    assert capsys.readouterr().err == ""


def test_a_banner_on_a_failed_probe_is_not_trusted(probe, monkeypatch):
    """A copy that exits non-zero while printing a version may be mid-upgrade."""
    monkeypatch.setattr(
        probe.subprocess,
        "run",
        lambda *a, **k: _completed(stdout="graphify 0.0.1\n", returncode=2),
    )
    assert probe._reported_exe_version("/opt/bin/graphify") is None


def test_each_exe_is_probed_once_per_process(probe, monkeypatch):
    """Resolution runs once per artifact; the probe must not cost one start each."""
    calls: list = []

    def run(*args, **kwargs):
        calls.append(args)
        return _completed(stdout="0.0.1\n")

    monkeypatch.setattr(probe.subprocess, "run", run)
    assert probe._reported_exe_version("/opt/bin/graphify") == "0.0.1"
    assert probe._reported_exe_version("/opt/bin/graphify") == "0.0.1"
    assert len(calls) == 1


@pytest.mark.parametrize("exe", ["./local/gf", "gf", "hook-wrapper.sh"])
def test_a_relative_path_is_never_probed(probe, monkeypatch, capsys, exe):
    """Only an absolute resolution can be probed; anything else is not ours to run."""
    probed: list = []
    monkeypatch.setattr(probe, "_reported_exe_version", lambda path: probed.append(path) or "0.0.1")

    probe._warn_if_hook_exe_is_stale(exe)

    assert probed == [], "a bare or relative path must never be executed"
    assert capsys.readouterr().err == ""


def test_a_hook_exe_that_reports_another_version_is_named(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: "0.0.1")
    probe._warn_if_hook_exe_is_stale("/opt/stale/bin/graphify")

    err = capsys.readouterr().err
    assert "0.0.1" in err and probe.__version__ in err, "both versions must be named"
    assert "/opt/stale/bin/graphify" in err, "the executable must be named"
    assert "PATH" in err, "the advice must say what to change"


def test_the_same_exe_is_warned_about_once(probe, monkeypatch, capsys):
    """An install resolves the exe per artifact; the user gets one warning."""
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: "0.0.1")
    for _ in range(3):
        probe._warn_if_hook_exe_is_stale("/opt/stale/bin/graphify")
    assert capsys.readouterr().err.count("warning:") == 1


def test_a_matching_or_unknown_version_stays_silent(probe, monkeypatch, capsys):
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: probe.__version__)
    probe._warn_if_hook_exe_is_stale("/opt/bin/graphify")
    monkeypatch.setattr(probe, "__version__", "unknown")
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: "0.0.1")
    probe._warn_if_hook_exe_is_stale("/opt/bin/graphify")
    assert capsys.readouterr().err == ""


def test_a_bare_command_is_not_probed(probe, monkeypatch, capsys):
    """A project-scope config spells `graphify`; PATH decides at hook time."""
    def _boom(exe):
        raise AssertionError("must not probe a bare command")

    monkeypatch.setattr(probe, "_reported_exe_version", _boom)
    probe._warn_if_hook_exe_is_stale("graphify")
    assert capsys.readouterr().err == ""


def test_resolving_the_exe_warns_when_path_offers_another_graphify(probe, monkeypatch, capsys):
    """The wiring point: whatever `which` returns is what the hooks will run."""
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/opt/stale/bin/graphify")
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: "0.0.1")

    assert probe._resolve_graphify_exe(project=False) == "/opt/stale/bin/graphify"
    assert "0.0.1" in capsys.readouterr().err


def test_a_committed_config_also_warns_about_paths_graphify(probe, monkeypatch, capsys):
    """Project scope spells `graphify`, which PATH resolves at hook time: same trap."""
    monkeypatch.setattr(probe.shutil, "which", lambda name: "/opt/stale/bin/graphify")
    monkeypatch.setattr(probe, "_reported_exe_version", lambda exe: "0.0.1")

    assert probe._resolve_graphify_exe(project=True) == "graphify"
    assert "0.0.1" in capsys.readouterr().err
