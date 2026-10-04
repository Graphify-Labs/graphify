"""Preserve complete file identity across native and MSYS test subprocesses.

Shells may report a POSIX spelling for a file created by native Windows Python.
Convert only through the reporting shell's own path mapper; drive-prefix guesses
cannot handle MSYS mounts such as ``/tmp`` and can hide a wrong candidate.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def resolve_shell_path(value: str, *, shell: str = "sh") -> Path:
    """Resolve one existing absolute path in the reporting shell's namespace."""
    if os.name == "nt" and value.startswith("/"):
        executable = shutil.which(shell)
        if executable is None:
            raise AssertionError(f"{shell} is unavailable for path identity proof")
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
