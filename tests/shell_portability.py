"""Admit explicit shell executables and preserve native/MSYS file identity.

Shells may report a POSIX spelling for a file created by native Windows Python.
Convert only through the reporting shell's own path mapper; drive-prefix guesses
cannot handle MSYS mounts such as ``/tmp`` and can hide a wrong candidate.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def select_shell_executable(shell: str = "sh") -> str:
    """Select Bash/sh only from configured PATH, then launch its absolute identity."""
    if shell not in {"bash", "sh"}:
        raise AssertionError("only Bash/sh are admitted by shell fixtures")
    configured = os.environ.get("PATH", "")
    if not configured:
        raise AssertionError(f"{shell} is unavailable in configured PATH")
    # A qualified candidate avoids Windows which/CreateProcess adding CWD or
    # system directories before PATH. Explicit empty/dot entries still admit CWD.
    for directory in configured.split(os.pathsep):
        candidate = Path(directory or os.curdir).absolute() / shell
        executable = shutil.which(str(candidate))
        if executable is None:
            continue
        identity = Path(executable)
        if not identity.is_absolute() or not identity.is_file():
            raise AssertionError(f"{shell} selection is not an absolute executable file")
        return str(identity.resolve(strict=True))
    raise AssertionError(f"{shell} is unavailable in configured PATH")


def resolve_shell_path(value: str, *, shell: str = "sh") -> Path:
    """Resolve one existing absolute path in the reporting shell's namespace."""
    if os.name == "nt" and value.startswith("/"):
        executable = select_shell_executable(shell)
        system = subprocess.check_output(
            [executable, "-c", "uname -s"], text=True,
        ).strip()
        if not system.startswith(("MSYS_", "MINGW", "CYGWIN_")):
            raise AssertionError(f"unsupported Windows shell path namespace: {system}")
        # Use this shell installation's mapper, not another cygpath on PATH.
        mapper = Path(executable).with_name("cygpath.exe")
        mapped = subprocess.check_output(
            [str(mapper), "-w", "--", value], text=True,
        ).splitlines()
        if len(mapped) != 1 or not mapped[0]:
            raise AssertionError("shell path conversion did not return one path")
        value = mapped[0]
    path = Path(value)
    if not path.is_absolute():
        raise AssertionError(f"shell reported a relative file identity: {value!r}")
    return path.resolve(strict=True)
