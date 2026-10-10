"""`graphify hook`, `hook-check` and `hook-guard`."""
from __future__ import annotations

import sys
from pathlib import Path


def hook() -> None:
    """`graphify hook` (moved verbatim from dispatch_command)."""
    from graphify.hooks import (
        install as hook_install,
        uninstall as hook_uninstall,
        status as hook_status,
    )

    subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
    if subcmd == "install":
        print(hook_install(Path(".")))
    elif subcmd == "uninstall":
        print(hook_uninstall(Path(".")))
    elif subcmd == "status":
        print(hook_status(Path(".")))
    else:
        print("Usage: graphify hook [install|uninstall|status]", file=sys.stderr)
        sys.exit(1)


def hook_check() -> None:
    """`graphify hook-check` (moved verbatim from dispatch_command)."""
    # Codex Desktop rejects hookSpecificOutput.additionalContext on PreToolUse.
    # Keep this as a cross-platform no-op so installed hooks never break Bash
    # tool calls. Graph guidance reaches the agent via AGENTS.md / skill instead.
    sys.exit(0)


def hook_guard() -> None:
    """`graphify hook-guard` (moved verbatim from dispatch_command)."""
    from graphify.cli import _run_hook_guard

    # Shell-agnostic Claude/Codebuddy PreToolUse guard (#522). Replaces the old
    # inline-bash hooks that failed on Windows. Prints an additionalContext nudge
    # toward graphify when a fresh in-project graph exists; always exits 0. In
    # strict mode (opt-in, `hook-guard read --strict`) it blocks the first raw
    # read per session via the JSON permissionDecision payload — never via exit
    # code — and downgrades to the nudge thereafter.
    _run_hook_guard(
        sys.argv[2] if len(sys.argv) > 2 else "",
        strict="--strict" in sys.argv[3:],
    )
    sys.exit(0)
