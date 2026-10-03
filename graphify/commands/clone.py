"""`graphify clone`."""
from __future__ import annotations

import sys
from pathlib import Path


def clone() -> None:
    """`graphify clone` (moved verbatim from dispatch_command)."""
    from graphify.cli import _clone_repo

    if len(sys.argv) < 3:
        print(
            "Usage: graphify clone <github-url> [--branch <branch>] [--out <dir>]",
            file=sys.stderr,
        )
        sys.exit(1)
    url = sys.argv[2]
    branch: str | None = None
    out_dir: Path | None = None
    args = sys.argv[3:]
    i = 0
    while i < len(args):
        if args[i] == "--branch" and i + 1 < len(args):
            branch = args[i + 1]
            i += 2
        elif args[i] == "--out" and i + 1 < len(args):
            out_dir = Path(args[i + 1])
            i += 2
        else:
            i += 1
    local_path = _clone_repo(url, branch=branch, out_dir=out_dir)
    print(local_path)
