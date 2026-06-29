r"""User-level PATH manipulation on Windows.

We do NOT use ``os.environ`` mutation (it doesn't persist beyond the process)
and we do NOT touch ``HKLM\SYSTEM\...`` (system PATH requires admin and
modifies a global setting). Instead we shell out to PowerShell::

    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")

``User`` target writes to ``HKCU\Environment``, which is what we want. The
new value is the current user PATH with the target path appended (for
add) or filtered out (for remove).
"""

from __future__ import annotations

import subprocess
import sys
from typing import List


class PathWinError(RuntimeError):
    """Raised when PowerShell returns a non-zero exit code."""


def _powershell_set_path(ps_command: str) -> None:
    """Run `ps_command` in PowerShell and raise on failure."""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            ps_command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PathWinError(
            f"PowerShell failed (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def _build_set_command(new: str) -> str:
    """PowerShell that:
       1. Reads current user Path.
       2. Splits on ';' (registry stores it as a single REG_EXPAND_SZ string).
       3. If `new` is not already present, appends it.
       4. Writes back via SetEnvironmentVariable('Path', ..., 'User').
    """
    nw = new.replace("'", "''")
    return (
        f"$cur = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        f"$parts = if ([string]::IsNullOrEmpty($cur)) {{ @() }} else {{ $cur.Split(';') }}; "
        f"if ($parts -notcontains '{nw}') {{ $parts += '{nw}' }}; "
        f"$new = [string]::Join(';', $parts); "
        f"[Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    )


def _build_unset_command(target: str) -> str:
    """PowerShell that removes `target` from the user Path and writes back."""
    tgt = target.replace("'", "''")
    return (
        f"$cur = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        f"if ([string]::IsNullOrEmpty($cur)) {{ return }}; "
        f"$parts = $cur.Split(';') | Where-Object {{ $_ -ne '{tgt}' }}; "
        f"$new = [string]::Join(';', $parts); "
        f"[Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    )


def add_to_user_path(path: str) -> None:
    """Append `path` to the user-level PATH. No-op on non-Windows.

    Idempotent: calling with the same `path` twice is safe (the second
    call is a no-op because the PowerShell filter rejects duplicates).
    """
    if sys.platform != "win32":
        return
    _powershell_set_path(_build_set_command(path))


def remove_from_user_path(path: str) -> None:
    """Remove `path` from the user-level PATH. No-op on non-Windows."""
    if sys.platform != "win32":
        return
    _powershell_set_path(_build_unset_command(path))


def current_user_path() -> str:
    """Return the current user-level PATH (for tests / diagnostics)."""
    if sys.platform != "win32":
        return ""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Environment]::GetEnvironmentVariable('Path', 'User')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PathWinError(
            f"PowerShell failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()