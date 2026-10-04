"""#1805: a package upgrade must not leave the installed skills behind.

`uv tool upgrade graphifyy` / `pip install -U graphifyy` replace the package
but not the skill copies under ~/.claude, ~/.codex, ~/.config/opencode, ...;
a plain `graphify install` then refreshes only the detected platform, so every
other agent kept the old instructions. The CLI now refreshes every stale
user-scope copy on its first run after an upgrade, and leaves alone the copies
it cannot refresh safely.
"""
from __future__ import annotations

import contextlib
import errno
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
import graphify.install as installmod
from graphify.install import __version__, _PLATFORM_CONFIG, _platform_skill_destination

OLD = "0.0.1"
OLD_BODY = "---\nname: graphify\n---\nold skill body\n"


@pytest.fixture(autouse=True)
def _refresh_enabled(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_NO_AUTO_REFRESH", raising=False)


def _packaged(name: str) -> bytes:
    skill_file = "skill.md" if name == "gemini" else _PLATFORM_CONFIG[name]["skill_file"]
    return (Path(installmod.__file__).parent / skill_file).read_bytes()


def _stale(name: str, version: str = OLD, body: str = OLD_BODY) -> Path:
    """Lay down `name`'s skill as an older release left it."""
    dst = _platform_skill_destination(name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(body, encoding="utf-8")
    (dst.parent / ".graphify_version").write_text(version, encoding="utf-8")
    return dst


def _stamp(dst: Path) -> str:
    return (dst.parent / ".graphify_version").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# What gets refreshed
# ---------------------------------------------------------------------------

def test_every_stale_platform_is_refreshed_not_only_the_detected_one(capsys):
    dsts = {name: _stale(name) for name in ("claude", "codex", "opencode", "gemini")}

    mainmod._refresh_stale_skills()

    out, err = capsys.readouterr()
    for name, dst in dsts.items():
        assert _stamp(dst) == __version__, name
        assert dst.read_bytes() == _packaged(name), name
        assert str(dst.parent) in err
    assert OLD in err and "GRAPHIFY_NO_AUTO_REFRESH" in err
    assert out == "", "stdout must stay clean for --json and the MCP stdio server"


def test_a_local_edit_survives_as_bak(capsys):
    dst = _stale("codex", body=OLD_BODY + "MY LOCAL EDIT\n")

    mainmod._refresh_stale_skills()

    backup = dst.with_suffix(dst.suffix + ".bak")
    assert "MY LOCAL EDIT" in backup.read_text(encoding="utf-8")
    assert "MY LOCAL EDIT" not in dst.read_text(encoding="utf-8")
    assert str(backup) in capsys.readouterr().err


def test_a_platform_that_was_never_installed_is_not_created():
    home = Path.home()
    before = sorted(p.relative_to(home) for p in home.rglob("*"))

    mainmod._refresh_stale_skills()

    assert sorted(p.relative_to(home) for p in home.rglob("*")) == before


def test_a_stamp_without_skill_md_is_left_for_the_repair_warning():
    dst = _stale("codex")
    dst.unlink()

    mainmod._refresh_stale_skills()

    assert not dst.exists()
    assert _stamp(dst) == OLD


# ---------------------------------------------------------------------------
# What is left alone
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_the_env_opt_out_disables_it(monkeypatch, capsys, value):
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", value)
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == OLD
    assert dst.read_text(encoding="utf-8") == OLD_BODY
    assert capsys.readouterr().err == ""


def test_a_falsy_opt_out_value_keeps_it_on(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "0")
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == __version__


def test_a_newer_skill_is_never_downgraded(capsys):
    """#1568: installing from an older package would downgrade the skill."""
    dst = _stale("codex", version="999.0.0")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == "999.0.0"
    assert dst.read_text(encoding="utf-8") == OLD_BODY
    assert capsys.readouterr().err == ""


def test_a_current_skill_is_untouched_and_silent(capsys):
    dst = _stale("codex", version=__version__)

    mainmod._refresh_stale_skills()

    assert dst.read_text(encoding="utf-8") == OLD_BODY
    assert not dst.with_suffix(dst.suffix + ".bak").exists()
    assert capsys.readouterr().err == ""


def test_the_copilot_dir_shared_with_vscode_is_not_guessed():
    """`graphify vscode install` writes a different SKILL.md to the same dir as
    the copilot platform; the stamp can't say which one is there."""
    assert _platform_skill_destination("copilot") == mainmod._vscode_skill_destination()
    dst = _stale("copilot")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == OLD
    assert dst.read_text(encoding="utf-8") == OLD_BODY


def test_a_directory_shared_by_two_platforms_is_not_guessed(monkeypatch):
    """On Windows gemini and agents both install into ~/.agents/skills (#2800)."""
    monkeypatch.setattr(mainmod.platform, "system", lambda: "Windows")
    assert _platform_skill_destination("gemini") == _platform_skill_destination("agents")
    dst = _stale("agents")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == OLD


def test_a_directory_shared_through_a_symlink_is_not_guessed(requires_symlinks):
    """Two platform dirs linked to one real dir hold ONE copy, like the shared
    dirs above - whichever platform refreshed it would overwrite the other's."""
    real = _platform_skill_destination("opencode").parent
    real.mkdir(parents=True)
    link = _platform_skill_destination("codex").parent
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(real, target_is_directory=True)
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == OLD
    assert dst.read_text(encoding="utf-8") == OLD_BODY


@pytest.mark.parametrize("system, variant", [("Linux", "claude"), ("Windows", "windows")])
def test_the_claude_dir_gets_the_host_variant(monkeypatch, system, variant):
    """claude and windows share ~/.claude/skills; refresh writes the variant a
    plain `graphify install` would pick on this OS."""
    monkeypatch.setattr(mainmod.platform, "system", lambda: system)
    dst = _stale("claude")

    mainmod._refresh_stale_skills()

    assert dst.read_bytes() == _packaged(variant)
    assert _stamp(dst) == __version__


# ---------------------------------------------------------------------------
# Failure and the CLI entry point
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("failure", [OSError("read-only file system"), SystemExit(1)])
def test_a_failed_refresh_never_breaks_the_command(monkeypatch, capsys, failure):
    def boom(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(mainmod, "_copy_skill_file", boom)
    dst = _stale("codex")

    mainmod._refresh_stale_skills()  # must not raise

    assert _stamp(dst) == OLD, "an unrefreshed copy keeps its stamp, so the warning still fires"
    assert "could not refresh" in capsys.readouterr().err


def test_one_unresolvable_destination_does_not_cancel_the_others(monkeypatch):
    def boom():
        raise RuntimeError("no home for vscode")

    monkeypatch.setattr(mainmod, "_vscode_skill_destination", boom)
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == __version__


def test_a_refresh_reports_only_the_result_and_the_backup(capsys):
    """_copy_skill_file's per-file install lines are noise on every CLI run;
    only where the previous copy went is worth keeping."""
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2, lines
    assert lines[0] == (
        f"graphify: refreshed skill at {dst.parent} ({OLD} -> {__version__}); "
        f"set GRAPHIFY_NO_AUTO_REFRESH=1 to disable"
    )
    assert str(dst.with_suffix(dst.suffix + ".bak")) in lines[1]


# ---------------------------------------------------------------------------
# Concurrent CLI processes
# ---------------------------------------------------------------------------

def _lock(dst: Path) -> Path:
    return installmod._skill_lock_path(dst.parent)


def _lock_is_free(dst: Path) -> bool:
    with installmod._skill_lock(dst.parent, wait=False) as owned:
        return owned is True


# Another graphify process (a refresh, an install, an uninstall): takes dst's
# skill lock, says so, then either waits for stdin to close or dies on the spot
# without releasing anything.
_HOLD_LOCK = """
import os, sys
from pathlib import Path
import graphify.install as inst
lock = inst._skill_lock(Path(sys.argv[1]), wait=False)  # keep a reference: collecting it releases
assert lock.__enter__() is True
print("locked", flush=True)
if sys.argv[2] == "crash":
    os._exit(1)
sys.stdin.read()
"""


def _hold_lock(dst: Path, mode: str) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLD_LOCK, str(dst.parent), mode],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
    )
    assert proc.stdout.readline().strip() == "locked"
    return proc


def test_a_directory_another_process_is_refreshing_is_skipped():
    """_copy_skill_file stages through fixed .tmp names; a second process
    writing the same dir at once would write through the first."""
    dst = _stale("codex")
    proc = _hold_lock(dst, "hold")
    try:
        mainmod._refresh_stale_skills()
    finally:
        proc.communicate(timeout=30)

    assert _stamp(dst) == OLD


def test_a_process_that_died_holding_the_lock_does_not_block():
    """The OS drops the lock with its holder: no timeout, and the lock file
    it leaves behind means nothing."""
    dst = _stale("codex")
    _hold_lock(dst, "crash").communicate(timeout=30)
    assert _lock(dst).exists()

    mainmod._refresh_stale_skills()

    assert _stamp(dst) == __version__


def test_a_refresh_finished_by_another_process_is_not_redone(monkeypatch, capsys):
    """Stale when first checked, current once the lock is ours: another
    process refreshed the directory in between, so nothing is left to do."""
    dst = _stale("codex")
    real_lock = mainmod._skill_lock

    @contextlib.contextmanager
    def lock_after_the_other_process(skill_dir, **kwargs):
        (skill_dir / ".graphify_version").write_text(__version__, encoding="utf-8")
        with real_lock(skill_dir, **kwargs) as owned:
            yield owned

    monkeypatch.setattr(mainmod, "_skill_lock", lock_after_the_other_process)

    mainmod._refresh_stale_skills()

    assert dst.read_text(encoding="utf-8") == OLD_BODY
    assert capsys.readouterr().err == ""


def test_a_skill_uninstalled_meanwhile_is_not_brought_back(monkeypatch, capsys):
    """Stale when first checked, uninstalled by another process before the
    lock is ours: the refresh must not reinstall what the user just removed."""
    dst = _stale("codex")
    real_lock = mainmod._skill_lock

    @contextlib.contextmanager
    def lock_after_an_uninstall(skill_dir, **kwargs):
        with contextlib.redirect_stdout(None):
            installmod._remove_skill_file("codex")
        with real_lock(skill_dir, **kwargs) as owned:
            yield owned

    monkeypatch.setattr(mainmod, "_skill_lock", lock_after_an_uninstall)

    mainmod._refresh_stale_skills()

    assert not dst.parent.exists()
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("write", [
    lambda: installmod._remove_skill_file("codex"),
    lambda: installmod._copy_skill_file("codex"),
], ids=["uninstall", "install"])
def test_install_and_uninstall_wait_for_a_refresh_in_progress(write):
    """Install and uninstall take the same lock as the refresh, but wait for
    it instead of skipping: they only go ahead once the refresh is done."""
    dst = _stale("codex")
    proc = _hold_lock(dst, "hold")
    worker = threading.Thread(target=write)
    try:
        with contextlib.redirect_stdout(None):
            worker.start()
            worker.join(0.5)
            assert worker.is_alive(), "wrote while another process held the lock"
            assert dst.read_text(encoding="utf-8") == OLD_BODY
            assert _stamp(dst) == OLD
    finally:
        proc.communicate(timeout=30)
        worker.join(30)

    assert not worker.is_alive()


def test_the_lock_file_stays_out_of_the_skill_directory(tmp_path):
    """A project-scope install writes into the user's repository; the lock
    file must not end up there, nor in any user-scope skill directory."""
    dst = installmod._copy_skill_file("claude", project=True, project_dir=tmp_path)
    user_dst = _stale("codex")
    mainmod._refresh_stale_skills()

    for skill_dir in (dst.parent, user_dst.parent):
        assert not any(p.suffix == ".lock" for p in skill_dir.rglob("*"))
    assert not _lock(dst).is_relative_to(tmp_path)


def test_without_file_locking_install_still_works_and_the_refresh_skips(monkeypatch):
    """A file system that refuses to lock (some network mounts): install goes
    ahead as it did before the lock existed, the refresh leaves the skill to
    the warning."""

    def no_locks(_fh):
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(installmod, "_try_skill_lock", no_locks)
    stale = _stale("codex")

    mainmod._refresh_stale_skills()
    assert _stamp(stale) == OLD

    with contextlib.redirect_stdout(None):
        installed = installmod._copy_skill_file("codex")
    assert _stamp(installed) == __version__


def test_the_lock_is_released_after_a_refresh():
    dsts = [_stale(name) for name in ("claude", "codex")]

    mainmod._refresh_stale_skills()

    assert all(_lock_is_free(dst) for dst in dsts)


def test_the_lock_is_released_after_a_failed_refresh(monkeypatch):
    def boom(*_args, **_kwargs):
        raise SystemExit(1)

    monkeypatch.setattr(mainmod, "_copy_skill_file", boom)
    dst = _stale("codex")

    mainmod._refresh_stale_skills()

    assert _lock_is_free(dst)


@pytest.mark.parametrize("name, uninstall", [
    ("codex", lambda _project: installmod._remove_skill_file("codex")),
    ("kilo", lambda _project: installmod._kilo_uninstall_global()),
    ("antigravity", installmod._antigravity_uninstall),
])
def test_uninstall_after_the_lock_was_taken_leaves_no_directory_behind(tmp_path, name, uninstall):
    """The lock file lives outside the skill directory and is never deleted,
    so it cannot keep the directory alive after an uninstall."""
    dst = _stale(name)
    with installmod._skill_lock(dst.parent):
        pass
    assert _lock(dst).exists()

    with contextlib.redirect_stdout(None):
        uninstall(tmp_path)

    assert not dst.parent.exists()
    assert _lock(dst).exists()


def test_uninstall_after_a_refresh_leaves_no_directory_behind():
    dst = _stale("codex")
    dst.write_bytes(_packaged("codex"))  # unedited, so the refresh keeps no .bak
    mainmod._refresh_stale_skills()

    installmod._remove_skill_file("codex")

    assert not dst.parent.exists()


def test_a_stale_gemini_skill_gets_the_warning_too(monkeypatch, capsys):
    """gemini is not in _PLATFORM_CONFIG, so the version check never saw its
    ~/.gemini copy; with the refresh off it must still warn."""
    monkeypatch.setenv("GRAPHIFY_NO_AUTO_REFRESH", "1")
    dst = _stale("gemini")
    monkeypatch.setattr(sys, "argv", ["graphify", "--version"])

    mainmod._run_cli()

    err = capsys.readouterr().err
    assert f"warning: skill at {dst.parent} is from graphify {OLD}" in err
    assert "graphify install --platform gemini" in err


def test_the_first_cli_run_after_an_upgrade_refreshes_and_stays_quiet(monkeypatch, capsys):
    dsts = [_stale(name) for name in ("claude", "codex")]
    monkeypatch.setattr(sys, "argv", ["graphify", "--version"])

    mainmod._run_cli()

    out, err = capsys.readouterr()
    assert out.strip() == f"graphify {__version__}"
    assert all(_stamp(dst) == __version__ for dst in dsts)
    assert "warning: skill at" not in err, "a refreshed copy must not also warn"


def test_what_the_refresh_skips_still_gets_the_warning(monkeypatch, capsys):
    dst = _stale("copilot")
    monkeypatch.setattr(sys, "argv", ["graphify", "--version"])

    mainmod._run_cli()

    err = capsys.readouterr().err
    assert _stamp(dst) == OLD
    assert f"warning: skill at {dst.parent} is from graphify {OLD}" in err


def test_graphify_update_refreshes_before_it_runs(monkeypatch, capsys):
    """Often the first command after an upgrade; it must fix the skills, not
    just warn about them."""
    dst = _stale("codex")
    monkeypatch.setattr(sys, "argv", ["graphify", "update", "."])
    monkeypatch.setattr(mainmod, "dispatch_install_cli", lambda _cmd: False)
    ran = []
    monkeypatch.setattr(mainmod, "dispatch_command", ran.append)

    mainmod._run_cli()

    assert ran == ["update"]
    assert _stamp(dst) == __version__
    assert "warning: skill at" not in capsys.readouterr().err


@pytest.mark.parametrize("cmd", ["install", "uninstall", "hook-check", "hook-guard"])
def test_install_and_hook_commands_skip_the_refresh(monkeypatch, cmd):
    calls = []
    monkeypatch.setattr(mainmod, "_refresh_stale_skills", lambda: calls.append(cmd))
    # Stop right after the pre-dispatch block: no real install/hook work runs.
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda *_a, **_k: None)
    monkeypatch.setattr(sys, "argv", ["graphify", cmd, "--help"])

    class _Stop(Exception):
        pass

    def stop(*_a, **_k):
        raise _Stop

    monkeypatch.setattr(mainmod, "dispatch_install_cli", stop)
    monkeypatch.setattr(mainmod, "dispatch_command", stop)
    try:
        mainmod._run_cli()
    except (_Stop, SystemExit):
        pass
    assert calls == []
