"""Serialize Codex hook commands for its supported native shell consumers.

Codex selects one session shell rather than a shell per handler. On Windows,
Cmd and PowerShell disagree on quoted executable invocation. An encoded payload
hands the literal selected launcher to OS-owned Windows PowerShell through an
outer command containing no executable-path substitutions. This is transport,
not encryption; the user-scope hook remains machine-specific.
"""
from __future__ import annotations

import base64
import os
import re
import shlex
from pathlib import Path


class HookCommandError(ValueError):
    """A supported literal command cannot be published safely on this host."""


def _windows_powershell_exe() -> str:
    """Admit the explicit OS shell only when both outer parsers accept its token."""
    root = os.environ.get("SystemRoot", "")
    executable = Path(root) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    token = executable.as_posix()
    # The selected Graphify path is encoded and has no such character restriction.
    # This token cannot be quoted uniformly in Cmd and PowerShell, so reject an
    # unusual OS directory instead of performing PATH lookup or interpolation.
    if not root or not executable.is_absolute() or not re.fullmatch(r"[A-Za-z]:/[A-Za-z0-9_./-]+", token):
        raise HookCommandError("the Windows system shell path is not a supported literal token; use a standard Windows installation")
    try:
        available = executable.is_file()
    except OSError:
        raise HookCommandError("cannot inspect Windows PowerShell; restore operating-system shell access and retry") from None
    if not available:
        raise HookCommandError("Windows PowerShell is unavailable; restore the operating-system PowerShell installation and retry")
    return token


def codex_hook_command(executable: str, *, windows: bool) -> str:
    """Keep portable bare commands, otherwise preserve the selected literal path."""
    if executable == "graphify":
        return "graphify hook-check"
    if not windows:
        return f"{shlex.quote(executable)} hook-check"
    shell = _windows_powershell_exe()
    # Single-quoted PowerShell strings only escape apostrophes by doubling them.
    # Encoding prevents the outer Cmd consumer from expanding percent variables
    # and the outer PowerShell consumer from evaluating dollars or backticks.
    literal = executable.replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop'; try { "
        f"& '{literal}' hook-check; exit $LASTEXITCODE"
        " } catch { [Console]::Error.WriteLine('graphify hook: selected executable could not be invoked'); exit 1 }"
    )
    payload = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    command = f"{shell} -NoLogo -NoProfile -NonInteractive -EncodedCommand {payload}"
    # Cmd limits a complete command line to 8191 characters (Microsoft KB830473).
    # Admit at most 8000 here, leaving normal shell-launch room, and also account
    # for the current default Cmd path, /C and Codex's raw outer quotation. This
    # rejects unusually long consumers too, before any hook JSON is accessed.
    cmd_shell = os.environ.get("COMSPEC", str(Path(os.environ.get("SystemRoot", "")) / "System32/cmd.exe"))
    if len(command) > 8000 or len(command) + len(cmd_shell) + 8 > 8191:
        raise HookCommandError("the Windows hook command is too long; reinstall Graphify in a shorter path and retry")
    return command
