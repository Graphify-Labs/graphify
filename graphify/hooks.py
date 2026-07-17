"""Git hooks that keep an embedded Helix generation current."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path


_HOOK_MARKER = "# graphify-hook-v8"
_HOOK_END = "# /graphify-hook-v8"


def _git_root(path: Path) -> Path | None:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    value = result.stdout.strip()
    return Path(value) if result.returncode == 0 and value else None


def _hooks_dir(root: Path) -> Path:
    result = subprocess.run(
        ["git", "-C", str(root), "config", "--get", "core.hooksPath"],
        capture_output=True, text=True, check=False,
    )
    configured = result.stdout.strip()
    if configured:
        path = Path(configured)
        resolved = path if path.is_absolute() else root / path
        return resolved.parent if resolved.name == "_" else resolved
    common = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    git_dir = Path(common)
    if not git_dir.is_absolute():
        git_dir = root / git_dir
    return git_dir / "hooks"


def _script(root: Path, checkout: bool) -> str:
    python = sys.executable
    if re.search(r"[^a-zA-Z0-9/_.@:\\-]", python):
        python = "python3"
    changed = "None" if checkout else "[Path(p) for p in subprocess.run(['git','diff-tree','--no-commit-id','--name-only','-r','HEAD'], capture_output=True, text=True).stdout.splitlines()]"
    body = (
        "from pathlib import Path\n"
        "import subprocess\n"
        "from graphify.watch import _rebuild_code\n"
        f"_rebuild_code(Path({str(root)!r}), changed_paths={changed})\n"
    )
    return (
        "#!/bin/sh\n"
        f"{_HOOK_MARKER}\n"
        f"{shlex.quote(python)} -c {shlex.quote(body)}\n"
        f"{_HOOK_END}\n"
    )


def _install_one(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if _HOOK_MARKER in existing:
            updated = re.sub(
                rf"{re.escape(_HOOK_MARKER)}.*?{re.escape(_HOOK_END)}\n?",
                content.split("\n", 1)[1], existing, flags=re.DOTALL,
            )
            path.write_text(updated, encoding="utf-8")
        else:
            path.write_text(existing.rstrip() + "\n" + content.split("\n", 1)[1], encoding="utf-8")
    else:
        path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return f"installed at {path}"


def _uninstall_one(path: Path) -> str:
    if not path.exists():
        return "not installed"
    content = path.read_text(encoding="utf-8")
    updated = re.sub(
        rf"{re.escape(_HOOK_MARKER)}.*?{re.escape(_HOOK_END)}\n?",
        "", content, flags=re.DOTALL,
    ).strip()
    if not updated or updated == "#!/bin/sh":
        path.unlink()
        return f"removed {path}"
    path.write_text(updated + "\n", encoding="utf-8")
    return f"removed Graphify section from {path}"


def install(path: Path = Path(".")) -> str:
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")
    directory = _hooks_dir(root)
    commit = _install_one(directory / "post-commit", _script(root, False))
    checkout = _install_one(directory / "post-checkout", _script(root, True))
    return f"post-commit: {commit}\npost-checkout: {checkout}"


def uninstall(path: Path = Path(".")) -> str:
    root = _git_root(path)
    if root is None:
        raise RuntimeError(f"No git repository found at or above {path.resolve()}")
    directory = _hooks_dir(root)
    return (
        f"post-commit: {_uninstall_one(directory / 'post-commit')}\n"
        f"post-checkout: {_uninstall_one(directory / 'post-checkout')}"
    )


def status(path: Path = Path(".")) -> str:
    root = _git_root(path)
    if root is None:
        return "Not in a git repository."
    directory = _hooks_dir(root)
    def state(name: str) -> str:
        target = directory / name
        return "installed" if target.exists() and _HOOK_MARKER in target.read_text(encoding="utf-8") else "not installed"
    return f"post-commit: {state('post-commit')}\npost-checkout: {state('post-checkout')}"


__all__ = ["install", "status", "uninstall"]
