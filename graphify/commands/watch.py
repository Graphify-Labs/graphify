"""`graphify watch` and `check-update`."""
from __future__ import annotations

import sys
from pathlib import Path


def watch() -> None:
    """`graphify watch` (moved verbatim from dispatch_command)."""
    watch_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    if not watch_path.exists():
        print(f"error: path not found: {watch_path}", file=sys.stderr)
        sys.exit(1)
    from graphify.watch import watch as _watch

    try:
        _watch(watch_path)
    except ImportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


def check_update() -> None:
    """`graphify check-update` (moved verbatim from dispatch_command)."""
    if len(sys.argv) < 3:
        print("Usage: graphify check-update <path>", file=sys.stderr)
        sys.exit(1)
    from graphify.watch import check_update

    check_update(Path(sys.argv[2]).resolve())
    sys.exit(0)
