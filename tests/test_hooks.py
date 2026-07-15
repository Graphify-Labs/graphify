"""Tests for hooks.py - git hook install/uninstall."""
import os
import shutil
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


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_limit_windows_workers_by_default(name, script):
    """Git for Windows/MSYS hooks can expose fragile pipe handles to spawned
    ProcessPoolExecutor children. Hook-triggered rebuilds should default to one
    worker there, while still allowing explicit user overrides."""
    assert '[ -n "${WINDIR:-}" ] || [ -n "${MSYSTEM:-}" ]' in script
    assert 'export GRAPHIFY_MAX_WORKERS="${GRAPHIFY_MAX_WORKERS:-1}"' in script


def _launcher_payload(script: str) -> str:
    """Extract the `python -c "<payload>"` the hook hands to GRAPHIFY_PYTHON.

    The launcher is the only `-c` invocation whose body begins with
    `import os, subprocess, sys` (the interpreter-detection probes in
    _PYTHON_DETECT use `-c "$_GFY_PROBE"`)."""
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
def test_windows_hookspath_rejected_no_junk_dir_on_posix(tmp_path, monkeypatch, winpath):
    """A Windows-style core.hooksPath must raise (loud failure), not silently
    create a backslash-named junk directory and report success on POSIX/WSL (#1385)."""
    monkeypatch.setattr("graphify.hooks.os.name", "posix")
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


# ── foreground hook cost: probes must be cheap and quiet ─────────────────────

def test_probes_use_find_spec_not_full_import():
    """`python -c "import graphify"` executes the FULL package import — 10s+ on a
    cold cache or AV-scanned site-packages — and could run up to four times
    synchronously before the detached launch even started, so every commit
    stalled for tens of seconds. Probes must locate the package with
    importlib.util.find_spec (no execution); the detached rebuild still reports
    a broken install loudly in its log."""
    from graphify.hooks import _PYTHON_DETECT
    assert '-c "import graphify"' not in _PYTHON_DETECT, (
        "interpreter probe still imports the full package in the hook foreground"
    )
    assert "find_spec" in _PYTHON_DETECT


def test_shebang_read_is_null_byte_safe():
    """On Windows, `command -v graphify` can return the launcher path WITHOUT its
    .exe suffix, so the `*.exe)` guard misses and the shebang probe reads a
    BINARY: the shell then warns 'ignored null byte in input' on every commit and
    the extracted garbage always falls through to the slow fallbacks. The read
    must strip NULs before the command substitution sees them."""
    from graphify.hooks import _PYTHON_DETECT
    assert "tr -d '\\000'" in _PYTHON_DETECT, "shebang read is not NUL-safe"


def test_probe_prefers_sibling_python_exe_on_windows_layouts():
    """pip on Windows puts Scripts/graphify(.exe) beside ..\\python.exe (or
    .\\python.exe in a venv). Resolving that directly beats shebang-parsing a
    binary launcher — and works whether or not command -v kept the suffix."""
    from graphify.hooks import _PYTHON_DETECT
    assert "/../python.exe" in _PYTHON_DETECT
    assert "/python.exe" in _PYTHON_DETECT


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_reuse_git_dir_from_env(name, script):
    """git exports GIT_DIR to hooks, so the rev-parse fallback should only run
    when the script is invoked by hand — each extra git exec costs 1s+ on
    AV-scanned Windows machines and lands in the commit's foreground."""
    assert "GIT_DIR=${GIT_DIR:-" in script, f"{name} always re-runs git rev-parse"


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_honor_skip_env(name, script):
    """GRAPHIFY_SKIP_HOOK=1 must suppress BOTH hooks. post-checkout previously
    lacked the check, so the var stopped commit rebuilds but not branch-switch
    ones (#1809)."""
    assert '[ "${GRAPHIFY_SKIP_HOOK:-0}" = "1" ] && exit 0' in script, (
        f"{name} does not honor GRAPHIFY_SKIP_HOOK"
    )


@pytest.mark.parametrize("name,script", _HOOK_SCRIPTS)
def test_hooks_skip_linked_worktrees(name, script):
    """Both hooks must short-circuit in a linked worktree (git-dir != common-dir),
    and must compare ABSOLUTE paths so the primary checkout (where --git-common-dir
    is the relative ".git") is not false-positived and wrongly skipped (#1809, #1806)."""
    assert script.count("_GFY_GITDIR=") == 1, f"{name} guard not present exactly once"
    assert "git rev-parse --git-common-dir" in script
    # absolute-normalized compare, not a raw string compare of git output
    assert 'cd "$(git rev-parse --git-dir 2>/dev/null)" 2>/dev/null && pwd' in script
    assert '[ "$_GFY_GITDIR" != "$_GFY_COMMONDIR" ]' in script


def _worktree_guard_snippet() -> str:
    from graphify.hooks import _WORKTREE_GUARD
    return _WORKTREE_GUARD + "echo RAN\n"


def test_worktree_guard_runs_on_primary_skips_linked(tmp_path):
    """End-to-end against a real `git worktree`: the guard falls through on the
    primary checkout and exits early inside a linked worktree (#1809, #1806)."""
    if shutil.which("git") is None:  # pragma: no cover
        pytest.skip("git not available")
    primary = tmp_path / "primary"
    primary.mkdir()

    def _git(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)

    _git("init", "-q", ".", cwd=primary)
    _git("config", "user.email", "t@t.co", cwd=primary)
    _git("config", "user.name", "t", cwd=primary)
    (primary / "a.txt").write_text("x")
    _git("add", "-A", cwd=primary)
    _git("commit", "-qm", "init", cwd=primary)
    linked = tmp_path / "linked"
    _git("worktree", "add", "-q", str(linked), "-b", "feature", cwd=primary)

    snippet = _worktree_guard_snippet()
    r_primary = subprocess.run(["sh", "-c", snippet], cwd=primary,
                               capture_output=True, text=True)
    r_linked = subprocess.run(["sh", "-c", snippet], cwd=linked,
                              capture_output=True, text=True)
    assert "RAN" in r_primary.stdout, "guard wrongly skipped the primary checkout"
    assert "RAN" not in r_linked.stdout, "guard failed to skip the linked worktree"


# ── #1907: duplicate keys in .git/config must not trigger spurious warnings ──

def _append_duplicate_config_entries(repo: Path) -> None:
    """Append git-legal duplicate keys/sections (as VS Code writes them)."""
    cfg = repo / ".git" / "config"
    cfg.write_text(
        cfg.read_text(encoding="utf-8")
        + '[remote "origin"]\n'
        + "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        + "\tfetch = +refs/heads/*:refs/remotes/origin/*\n"
        + "[core]\n"
        + "\tignorecase = true\n",
        encoding="utf-8",
    )


def test_hooks_dir_no_warning_on_duplicate_config_keys(tmp_path, capsys):
    """git legally allows duplicate keys and repeated sections in .git/config;
    a strict configparser raised DuplicateOptionError/DuplicateSectionError and
    printed a spurious 'could not read core.hooksPath' warning on every hook
    command (#1907). _hooks_dir must resolve cleanly with no stderr noise."""
    repo = _make_git_repo(tmp_path)
    _append_duplicate_config_entries(repo)
    d = _hooks_dir(repo)
    err = capsys.readouterr().err
    assert "could not read core.hooksPath" not in err
    assert d == (repo / ".git" / "hooks").resolve()


def test_hooks_dir_duplicate_config_keys_honor_custom_hookspath(tmp_path, capsys):
    """With duplicate keys present, a custom core.hooksPath must still be
    honored (no fall-through to .git/hooks) and no warning printed (#1907)."""
    repo = _make_git_repo(tmp_path)
    _set_hookspath(repo, ".husky")
    _append_duplicate_config_entries(repo)
    d = _hooks_dir(repo)
    err = capsys.readouterr().err
    assert "could not read core.hooksPath" not in err
    assert d == (repo / ".husky").resolve()


# ── #1902: hook install must register the graph.json union merge driver ─────

def test_install_registers_merge_driver(tmp_path):
    """install() must set merge.graphify.* via git config and add the
    .gitattributes line that README/CHANGELOG 0.7.0 document (#1902)."""
    repo = _make_git_repo(tmp_path)
    result = install(repo)
    res = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "merge.graphify.driver"],
        capture_output=True, text=True,
    )
    assert res.returncode == 0
    driver = res.stdout.strip()
    assert driver
    assert "merge-driver %O %A %B" in driver
    attrs = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert any(
        "graph.json" in line and "merge=graphify" in line
        for line in attrs.splitlines()
    )
    assert "merge driver" in result


def test_install_merge_driver_idempotent(tmp_path):
    """Running install twice must not duplicate the .gitattributes line."""
    repo = _make_git_repo(tmp_path)
    install(repo)
    install(repo)
    lines = (repo / ".gitattributes").read_text(encoding="utf-8").splitlines()
    matches = [l for l in lines if "merge=graphify" in l]
    assert len(matches) == 1


def test_install_preserves_existing_gitattributes(tmp_path):
    """A pre-existing .gitattributes entry must survive install (no clobber)."""
    repo = _make_git_repo(tmp_path)
    (repo / ".gitattributes").write_text("*.png binary\n", encoding="utf-8")
    install(repo)
    content = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert "*.png binary" in content
    assert "merge=graphify" in content


def test_uninstall_removes_merge_driver_keeps_other_attrs(tmp_path):
    """uninstall() must unset merge.graphify.* and remove only the graphify
    .gitattributes line, keeping the file when other entries exist."""
    repo = _make_git_repo(tmp_path)
    (repo / ".gitattributes").write_text("*.png binary\n", encoding="utf-8")
    install(repo)
    uninstall(repo)
    res = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "merge.graphify.driver"],
        capture_output=True, text=True,
    )
    assert res.returncode != 0
    content = (repo / ".gitattributes").read_text(encoding="utf-8")
    assert "*.png binary" in content
    assert "merge=graphify" not in content
