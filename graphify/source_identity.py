"""Walked source identity after physical corpus containment has been established.

The caller owns root admission and the per-run realpath cache. This helper only
chooses the relative name: a discovered leaf/directory alias keeps its lexical
suffix, while an alternate spelling of the scan-root anchor remains portable.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


def walked_relative_source(path: Path, root: Path, resolved: Path, *,
                           realpath: Callable[[str, str], Path], cwd: str) -> Path:
    """Reject foreign physical targets before retaining any written alias name.

Inputs are absolute source/root paths; root is the caller's canonical root.
No root/index/cache state is retained here and no accepted endpoint is minted.
The fallback handles platform aliases without a corresponding lexical ancestor.
"""
    relative = resolved.relative_to(root)
    try:
        return path.relative_to(root)
    except ValueError:
        for parent in path.parents:
            try:
                if realpath(str(parent), cwd) == root:
                    return path.relative_to(parent)
            except (OSError, RuntimeError):
                continue
    return relative
