"""Tests for hooks.py - git hook install/uninstall."""
import os
import subprocess
from types import SimpleNamespace
from pathlib import Path
import pytest
from graphify.hooks import install, uninstall, status, _hooks_dir, _HOOK_MARKER, _CHECKOUT_MARKER


def _make_git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def test_install_creates_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = install(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    assert hook.exists()
    assert _HOOK_MARKER in hook.read_text()
    assert "installed" in result


def test_install_is_executable(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    if os.name == "nt":
        assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    else:
        assert hook.stat().st_mode & 0o111  # executable bit set


def test_install_idempotent(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = install(repo)
    assert "already installed" in result
    # marker appears only once
    hook = repo / ".git" / "hooks" / "post-commit"
    assert hook.read_text().count(_HOOK_MARKER) == 1


def test_install_appends_to_existing_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/bash\necho existing\n")
    hook.chmod(0o755)
    install(repo)
    content = hook.read_text()
    assert "existing" in content
    assert _HOOK_MARKER in content


def test_uninstall_removes_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = uninstall(repo)
    hook = repo / ".git" / "hooks" / "post-commit"
    assert not hook.exists()
    assert "removed" in result.lower()


def test_uninstall_no_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = uninstall(repo)
    assert "nothing to remove" in result


def test_status_installed(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = status(repo)
    assert "installed" in result


def test_status_not_installed(tmp_path):
    repo = _make_git_repo(tmp_path)
    result = status(repo)
    assert "not installed" in result


def test_no_git_repo_raises(tmp_path):
    with pytest.raises(RuntimeError, match="No git repository"):
        install(tmp_path / "not_a_repo")


def test_install_creates_post_checkout_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    assert hook.exists()
    assert _CHECKOUT_MARKER in hook.read_text()


def test_install_post_checkout_is_executable(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    if os.name == "nt":
        assert hook.read_text(encoding="utf-8").startswith("#!/bin/sh\n")
    else:
        assert hook.stat().st_mode & 0o111


def test_uninstall_removes_post_checkout_hook(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    uninstall(repo)
    hook = repo / ".git" / "hooks" / "post-checkout"
    assert not hook.exists()


def test_status_shows_both_hooks(tmp_path):
    repo = _make_git_repo(tmp_path)
    install(repo)
    result = status(repo)
    assert "post-commit" in result
    assert "post-checkout" in result
    assert result.count("installed") >= 2



def test_hooks_dir_resolves_relative_git_hooks_path(tmp_path, monkeypatch):
    repo = _make_git_repo(tmp_path)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=".git/hooks\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert _hooks_dir(repo) == (repo / ".git" / "hooks").resolve()


def test_hooks_dir_rejects_multiline_git_output(tmp_path, monkeypatch):
    repo = _make_git_repo(tmp_path)

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="--path-format=absolute\n.git/hooks\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert _hooks_dir(repo) == repo / ".git" / "hooks"
    assert not (repo / "--path-format=absolute\n.git").exists()


def test_hooks_dir_accepts_absolute_git_hooks_path(tmp_path, monkeypatch):
    repo = _make_git_repo(tmp_path)
    hooks = tmp_path / "actual-hooks"

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=f"{hooks}\n")

    monkeypatch.setattr("subprocess.run", fake_run)

    assert _hooks_dir(repo) == hooks.resolve()

def test_hook_skips_head_on_exe():
    """Hook script must skip shebang extraction for .exe binaries (Windows)."""
    from graphify.hooks import _PYTHON_DETECT
    assert "*.exe) _SHEBANG=" in _PYTHON_DETECT or '*.exe)' in _PYTHON_DETECT


def test_install_embeds_pinned_interpreter(tmp_path):
    """Hook scripts must embed sys.executable so the hook works without the
    graphify launcher on PATH (uv tool / pipx isolation, #1127).

    When graphify is installed via `uv tool install graphifyy` or `pipx install
    graphifyy`, the interpreter lives in an isolated venv and the launcher is in
    ~/.local/bin.  GUI git clients and CI runners often run with a minimal PATH
    that omits that directory, so `command -v graphify` fails, the python3/python
    fallbacks cannot import graphify (wrong venv), and the hook silently exits 0.
    Pinning sys.executable at install time makes the hook work regardless of PATH.
    """
    import re, sys
    repo = _make_git_repo(tmp_path)
    install(repo)
    commit_hook = (repo / ".git" / "hooks" / "post-commit").read_text()
    checkout_hook = (repo / ".git" / "hooks" / "post-checkout").read_text()
    # Compute the sanitized value the same way install() does.
    expected = sys.executable if not re.search(r"[^a-zA-Z0-9/_.@:\\-]", sys.executable) else ""
    if expected:
        assert expected in commit_hook, "sanitized sys.executable missing from post-commit"
        assert expected in checkout_hook, "sanitized sys.executable missing from post-checkout"
    # The placeholder must be fully substituted -- no __PINNED_PYTHON__ left.
    assert "__PINNED_PYTHON__" not in commit_hook, "placeholder not substituted in post-commit"
    assert "__PINNED_PYTHON__" not in checkout_hook, "placeholder not substituted in post-checkout"


def test_install_fallback_is_loud_not_silent(tmp_path):
    """The detection fallback must emit a message to stderr rather than bare exit 0.

    A silent no-op (the pre-fix behaviour) leaves the user with no indication
    that the hook ran but found nothing, making the bug extremely hard to diagnose.
    """
    from graphify.hooks import _PYTHON_DETECT
    assert "could not locate" in _PYTHON_DETECT, (
        "fallback branch must print a diagnostic message; bare 'exit 0' is silent and unhelpful"
    )


def test_hook_check_no_additionalContext(tmp_path):
    """graphify hook-check must not emit additionalContext — Codex Desktop rejects it."""
    import sys
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "graphify", "hook-check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


# ── #1161: background rebuild must not rely on nohup (missing on Git for Windows) ──

import ast  # noqa: E402
import re  # noqa: E402

from graphify.hooks import (  # noqa: E402
    _HOOK_SCRIPT,
    _CHECKOUT_SCRIPT,
    _REBUILD_BODY_COMMIT,
    _REBUILD_BODY_CHECKOUT,
    _detached_launch,
)

_HOOK_SCRIPTS = [("post-commit", _HOOK_SCRIPT), ("post-checkout", _CHECKOUT_SCRIPT)]


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_do_not_use_nohup(name, script):
    """Git for Windows' bundled shell ships no `nohup`/`setsid`, so the old
    `nohup ... &` launch died with 'nohup: command not found' and the rebuild
    silently never ran (#1161). The generated hooks must not reference either."""
    assert "nohup" not in script, f"{name} still references nohup (#1161)"
    assert "setsid" not in script, f"{name} still references setsid (#1161)"
    assert "disown" not in script, f"{name} still uses disown (#1161)"


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_use_cross_platform_detach(name, script):
    """The replacement detaches via Python: start_new_session on POSIX and
    DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP on Windows (#1161)."""
    assert "subprocess.Popen" in script
    assert "start_new_session=True" in script, f"{name} missing POSIX detach"
    assert "0x00000008" in script, f"{name} missing Windows DETACHED_PROCESS flag"
    assert "0x00000200" in script, f"{name} missing CREATE_NEW_PROCESS_GROUP flag"


def _launcher_payload(script: str) -> str:
    """Extract the `python -c "<payload>"` the hook hands to GRAPHIFY_PYTHON.

    The launcher is the only `-c` invocation whose body begins with
    `import os, subprocess, sys` (the interpreter-detection probes in
    _PYTHON_DETECT use `-c "import graphify"`)."""
    m = re.search(r'-c "(import os, subprocess, sys.*?)"\n', script, re.DOTALL)
    assert m, "launcher payload not found"
    return m.group(1)


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_launcher_payload_is_shell_quote_safe(name, script):
    """The launcher is carried inside a shell double-quoted `-c "..."` argument,
    so it must contain no characters the shell would interpret there: an
    unescaped double-quote, $, backtick or backslash would corrupt the hook."""
    payload = _launcher_payload(script)
    for bad in ('"', "$", "`", "\\"):
        assert bad not in payload, f"{name} launcher payload contains unsafe {bad!r}"


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_launcher_and_rebuild_body_are_valid_python(name, script):
    """Both the launcher and the rebuild body it re-executes must parse, so a
    quoting slip can't ship a hook that crashes the moment git fires it."""
    payload = _launcher_payload(script)
    ast.parse(payload)  # launcher itself
    inner = re.search(r"_src = '''(.*?)'''", payload, re.DOTALL)
    assert inner, f"{name}: embedded rebuild body not found"
    ast.parse(inner.group(1))  # the detached child's source


def test_rebuild_bodies_are_shell_quote_safe():
    """The shared rebuild bodies are embedded verbatim into the launcher, so they
    too must avoid characters unsafe inside a shell double-quoted argument."""
    for body in (_REBUILD_BODY_COMMIT, _REBUILD_BODY_CHECKOUT):
        for bad in ('"', "$", "`", "\\"):
            assert bad not in body
        assert "'''" not in body  # would terminate the launcher's _src literal


@pytest.mark.parametrize(
    "name,body",
    [("post-commit", _REBUILD_BODY_COMMIT), ("post-checkout", _REBUILD_BODY_CHECKOUT)],
)
def test_rebuild_bodies_read_graphify_root(name, body):
    """The rebuild must honour the persisted scan root rather than hardcoding the
    repo top (#1173). Both bodies read <output-dir>/.graphify_root and pass the
    recovered root to _rebuild_code instead of the bare Path('.')."""
    assert ".graphify_root" in body, f"{name} ignores .graphify_root (#1173)"
    # The output dir is resolved from GRAPHIFY_OUT at hook-run time, not hardcoded
    # to graphify-out/, so a renamed output dir is still found (#1423).
    assert "GRAPHIFY_OUT" in body, f"{name} ignores the GRAPHIFY_OUT override (#1423)"
    # The recovered root is what gets rebuilt, not a hardcoded cwd.
    assert "_rebuild_code(_root" in body, f"{name} does not pass the recovered root"
    # Quote-safe inside the shell-double-quoted launcher: single quotes only.
    assert "read_text(encoding='utf-8')" in body, f"{name} root read is not single-quoted"


def test_rebuild_bodies_with_graphify_root_are_valid_python():
    """The .graphify_root snippet must parse so a quoting slip can't ship a hook
    that crashes the moment git fires it (#1173)."""
    for body in (_REBUILD_BODY_COMMIT, _REBUILD_BODY_CHECKOUT):
        ast.parse(body)


def test_detached_launch_targets_graphify_python():
    """The launcher must run via the resolved $GRAPHIFY_PYTHON, not a bare
    `python`, so it uses the same interpreter the detection block selected."""
    snippet = _detached_launch(_REBUILD_BODY_COMMIT)
    assert snippet.startswith('"$GRAPHIFY_PYTHON" -c "')
    assert "nohup" not in snippet


def test_installed_hooks_contain_no_nohup(tmp_path):
    """End-to-end: the files written to .git/hooks must be nohup-free (#1161)."""
    repo = _make_git_repo(tmp_path)
    install(repo)
    for name in ("post-commit", "post-checkout"):
        text = (repo / ".git" / "hooks" / name).read_text(encoding="utf-8")
        assert "nohup" not in text, f"installed {name} still references nohup"
        assert "start_new_session=True" in text


# ── #1385: reject Windows-style hooks paths instead of creating a junk dir ───

def _set_hookspath(repo: Path, value: str) -> None:
    subprocess.run(["git", "-C", str(repo), "config", "--local", "core.hooksPath", value],
                   check=True, capture_output=True)


@pytest.mark.parametrize("winpath", [
    r"C:\Users\u\repo\.git\hooks",
    r"c:/Users/u/.git/hooks",
    r"D:\hooks",
    r"some\back\slashed\path",
])
def test_windows_hookspath_rejected_no_junk_dir(tmp_path, winpath):
    """A Windows-style core.hooksPath must raise (loud failure), not silently
    create a backslash-named junk directory and report success (#1385)."""
    repo = _make_git_repo(tmp_path)
    _set_hookspath(repo, winpath)
    with pytest.raises(RuntimeError, match="Windows path"):
        install(repo)
    # no junk directory got created anywhere under the repo
    junk = [p for p in repo.rglob("*") if "\\" in p.name or p.name.startswith(("C:", "c:", "D:"))]
    assert junk == [], f"junk dir created: {junk}"


def test_posix_custom_hookspath_still_works(tmp_path):
    """A legitimate POSIX core.hooksPath (Husky-style) must still install."""
    repo = _make_git_repo(tmp_path)
    _set_hookspath(repo, ".husky")
    msg = install(repo)
    assert "post-commit" in msg
    assert (repo / ".husky" / "post-commit").exists()


def test_default_hooks_dir_unaffected(tmp_path):
    """No core.hooksPath -> normal .git/hooks install, no rejection."""
    repo = _make_git_repo(tmp_path)
    install(repo)
    assert (repo / ".git" / "hooks" / "post-commit").exists()
