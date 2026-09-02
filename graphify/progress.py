"""Opt-in progress chatter for detect/extract (``--verbose`` / ``GRAPHIFY_VERBOSE``).

Quiet by default so a large corpus does not flood the terminal. Warnings and
errors still print from their call sites. ``--timing`` is independent.
"""
from __future__ import annotations

import os
import sys
from typing import TextIO

_verbose: bool | None = None


def set_verbose(on: bool | None) -> None:
    """Force verbose on/off. ``None`` restores env-only (``GRAPHIFY_VERBOSE``)."""
    global _verbose
    _verbose = on


def verbose_enabled() -> bool:
    if _verbose is True:
        return True
    if _verbose is False:
        return False
    return os.environ.get("GRAPHIFY_VERBOSE", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def vprint(
    msg: str,
    *,
    file: TextIO | None = None,
    prefix: str | None = "[graphify]",
) -> None:
    """Print a progress line when verbose is on. Default stream is stderr."""
    if not verbose_enabled():
        return
    dest = sys.stderr if file is None else file
    text = f"{prefix} {msg}" if prefix else msg
    print(text, file=dest, flush=True)
