import os
import subprocess

import pytest

from graphify.hooks import _HOOK_MARKER, install, status, uninstall


def _repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    return tmp_path


def test_install_creates_idempotent_commit_and_checkout_hooks(tmp_path):
    repo = _repo(tmp_path)
    install(repo)
    install(repo)
    for name in ("post-commit", "post-checkout"):
        hook = repo / ".git" / "hooks" / name
        assert hook.is_file()
        assert hook.read_text().count(_HOOK_MARKER) == 1
        if os.name != "nt":
            assert hook.stat().st_mode & 0o111
    assert status(repo).count("installed") == 2


def test_install_preserves_existing_hook_and_uninstall_preserves_it(tmp_path):
    repo = _repo(tmp_path)
    hook = repo / ".git" / "hooks" / "post-commit"
    hook.write_text("#!/bin/sh\necho existing\n")
    install(repo)
    assert "existing" in hook.read_text()
    uninstall(repo)
    assert hook.is_file() and "existing" in hook.read_text()
    assert _HOOK_MARKER not in hook.read_text()
    assert not (repo / ".git" / "hooks" / "post-checkout").exists()


def test_hook_scripts_use_pinned_python_and_native_rebuild(tmp_path):
    repo = _repo(tmp_path)
    install(repo)
    text = (repo / ".git" / "hooks" / "post-commit").read_text()
    assert "_rebuild_code" in text
    assert "graph.helix" not in text  # store resolution stays inside the Python runtime
    assert "graph.json" not in text


def test_install_requires_git_repository(tmp_path):
    with pytest.raises(RuntimeError, match="No git repository"):
        install(tmp_path)
